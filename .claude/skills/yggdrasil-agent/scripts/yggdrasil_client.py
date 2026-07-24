#!/usr/bin/env python3
"""Small dependency-free client for Claude Code's Yggdrasil task loop."""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


SENSITIVE_PARTS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "credential",
    "password",
    "secret",
    "token",
)
MAX_PAYLOAD_BYTES = 16_384


class ClientError(RuntimeError):
    pass


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): "<redacted>"
            if any(part in str(key).lower() for part in SENSITIVE_PARTS)
            else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


def safe_payload(value: Any) -> Any:
    cleaned = redact(value)
    encoded = json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")).encode()
    if len(encoded) > MAX_PAYLOAD_BYTES:
        raise ClientError(f"Payload exceeds {MAX_PAYLOAD_BYTES} bytes")
    return cleaned


def parse_json(value: str, field_name: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        raise ClientError(f"{field_name} must be valid JSON: {exc}") from exc


class YggdrasilClient:
    def __init__(self) -> None:
        self.base_url = os.getenv("YGGDRASIL_URL", "http://127.0.0.1:6061").rstrip("/")
        self.tenant = os.getenv("YGGDRASIL_TENANT", "default")
        self.actor = os.getenv("YGGDRASIL_ACTOR", "claude-code")
        self.timeout = float(os.getenv("YGGDRASIL_TIMEOUT", "10"))

    def request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        headers: dict[str, str] | None = None,
    ) -> Any:
        body = None
        request_headers = {"Accept": "application/json", **(headers or {})}
        if payload is not None:
            body = json.dumps(safe_payload(payload), ensure_ascii=False).encode()
            request_headers["Content-Type"] = "application/json"
        req = Request(
            f"{self.base_url}{path}",
            data=body,
            headers=request_headers,
            method=method,
        )
        try:
            with urlopen(req, timeout=self.timeout) as response:
                raw = response.read().decode()
        except HTTPError as exc:
            detail = exc.read().decode(errors="replace")
            raise ClientError(f"HTTP {exc.code} {path}: {detail}") from exc
        except (TimeoutError, URLError) as exc:
            reason = getattr(exc, "reason", str(exc))
            raise ClientError(f"Cannot reach {self.base_url}: {reason}") from exc
        return json.loads(raw) if raw else {}

    def health(self) -> Any:
        return self.request("GET", "/api/v1/health")

    def begin(self, intent: str, domain: str | None, max_nodes: int) -> dict[str, Any]:
        run = self.request(
            "POST",
            "/api/v1/runs",
            {"intent": intent, "tenant_id": self.tenant},
        )
        run_id = run["run_id"]
        result: dict[str, Any] = {"run": run, "context": None}
        try:
            response = self.request(
                "POST",
                "/api/v1/yggdrasil/retrieve",
                {"query": intent, "domain_path": domain, "max_nodes": max_nodes},
            )
            context = response.get("data", response)
            result["context"] = context
            nodes = [
                {
                    "revision_id": node.get("revision_id") or node.get("id"),
                    "rank": rank,
                    "score": node.get("score", node.get("strength", 0.0)),
                    "usage_type": "retrieved",
                }
                for rank, node in enumerate(context.get("nodes", []), start=1)
                if node.get("revision_id") or node.get("id")
            ]
            edges = [
                {"revision_id": edge.get("revision_id") or edge.get("id")}
                for edge in context.get("edges", [])
                if edge.get("revision_id") or edge.get("id")
            ]
            result["references"] = self.request(
                "POST",
                f"/api/v1/runs/{run_id}/references",
                {"nodes": nodes, "edges": edges},
            )
        except ClientError as exc:
            result["context_error"] = str(exc)
        return result

    def record(self, run_id: str, event_type: str, payload: Any) -> Any:
        return self.request(
            "POST",
            "/api/v1/soil/events",
            {
                "event_type": event_type,
                "tenant_id": self.tenant,
                "source_type": "claude_code",
                "source_ref": "local-task",
                "run_id": run_id,
                "payload": payload,
            },
            {
                "Idempotency-Key": f"claude-{run_id}-{uuid.uuid4()}",
                "X-Actor-Id": self.actor,
            },
        )

    def feedback(
        self,
        node_id: str | None,
        edge_id: str | None,
        success: bool,
        step: float,
    ) -> Any:
        return self.request(
            "POST",
            "/api/v1/yggdrasil/feedback",
            {"node_id": node_id, "edge_id": edge_id, "success": success, "step": step},
        )

    def action(
        self,
        run_id: str,
        skill_revision_id: str,
        status: str,
        input_payload: Any,
        output_ref: str,
    ) -> Any:
        return self.request(
            "POST",
            f"/api/v1/runs/{run_id}/actions",
            {
                "skill_revision_id": skill_revision_id,
                "status": status,
                "input_payload": input_payload,
                "output_ref": output_ref,
            },
        )

    def finish(
        self,
        run_id: str,
        status: str,
        summary: str,
        used_nodes: list[str],
        used_edges: list[str],
        result_ref: str,
    ) -> dict[str, Any]:
        if len(summary) > 2_000:
            raise ClientError("summary exceeds 2000 characters")
        warnings: list[dict[str, str]] = []
        event = None
        try:
            event = self.record(
                run_id,
                "evaluation",
                {"status": status, "summary": summary, "result_ref": result_ref},
            )
        except ClientError as exc:
            warnings.append({"operation": "record_evaluation", "error": str(exc)})

        feedback_results = []
        success = status == "succeeded"
        for node_id in used_nodes:
            try:
                feedback_results.append(self.feedback(node_id, None, success, 0.05))
            except ClientError as exc:
                warnings.append(
                    {"operation": "feedback_node", "reference_id": node_id, "error": str(exc)}
                )
        for edge_id in used_edges:
            try:
                feedback_results.append(self.feedback(None, edge_id, success, 0.05))
            except ClientError as exc:
                warnings.append(
                    {"operation": "feedback_edge", "reference_id": edge_id, "error": str(exc)}
                )

        # Closing the Run is mandatory even when optional evaluation writes fail.
        finished = self.request(
            "POST",
            f"/api/v1/runs/{run_id}/finish",
            {"status": status, "result_ref": result_ref or None},
        )
        return {
            "event": event,
            "feedback": feedback_results,
            "run": finished,
            "warnings": warnings,
        }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("health")

    begin = commands.add_parser("begin")
    begin.add_argument("--intent", required=True)
    begin.add_argument("--domain")
    begin.add_argument("--max-nodes", type=int, default=20)

    record = commands.add_parser("record")
    record.add_argument("--run-id", required=True)
    record.add_argument("--event-type", default="observation")
    record.add_argument("--payload", required=True)

    action = commands.add_parser("action")
    action.add_argument("--run-id", required=True)
    action.add_argument("--skill-revision-id", required=True)
    action.add_argument("--status", default="completed")
    action.add_argument("--input-payload", default="{}")
    action.add_argument("--output-ref", default="")

    feedback = commands.add_parser("feedback")
    feedback.add_argument("--node-id")
    feedback.add_argument("--edge-id")
    feedback.add_argument("--success", action=argparse.BooleanOptionalAction, default=True)
    feedback.add_argument("--step", type=float, default=0.05)

    finish = commands.add_parser("finish")
    finish.add_argument("--run-id", required=True)
    finish.add_argument("--status", choices=("succeeded", "failed", "cancelled"), required=True)
    finish.add_argument("--summary", required=True)
    finish.add_argument("--used-node", action="append", default=[])
    finish.add_argument("--used-edge", action="append", default=[])
    finish.add_argument("--result-ref", default="")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    client = YggdrasilClient()
    if args.command == "health":
        result = client.health()
    elif args.command == "begin":
        result = client.begin(args.intent, args.domain, args.max_nodes)
    elif args.command == "record":
        result = client.record(args.run_id, args.event_type, parse_json(args.payload, "payload"))
    elif args.command == "action":
        result = client.action(
            args.run_id,
            args.skill_revision_id,
            args.status,
            parse_json(args.input_payload, "input-payload"),
            args.output_ref,
        )
    elif args.command == "feedback":
        if not args.node_id and not args.edge_id:
            raise ClientError("feedback requires --node-id or --edge-id")
        result = client.feedback(args.node_id, args.edge_id, args.success, args.step)
    else:
        result = client.finish(
            args.run_id,
            args.status,
            args.summary,
            args.used_node,
            args.used_edge,
            args.result_ref,
        )
    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ClientError as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        raise SystemExit(1)
