"""Soil API - 事件和证据"""

from datetime import datetime

from quart import Blueprint, request, jsonify
from dependency_injector.wiring import inject, Provide

from src.core.dependency import ServerContainer

soil_bp = Blueprint("soil", __name__)


def _parse_datetime(value, field_name):
    if value in (None, ""):
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be an ISO-8601 string")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"{field_name} must be an ISO-8601 string") from exc


@soil_bp.route("/api/v1/soil/events", methods=["POST"])
@inject
async def create_event(soil_service=Provide[ServerContainer.soil_service]):
    data = await request.get_json()
    if not data:
        return jsonify({"error": "Empty request body"}), 400

    idempotency_key = request.headers.get("Idempotency-Key", "")
    if not idempotency_key:
        return jsonify({"error": "Idempotency-Key header required"}), 400

    actor_id = request.headers.get("X-Actor-Id", "system")
    try:
        event_id = await soil_service.append_event(
            event_type=data.get("event_type", "observation"),
            payload=data.get("payload", {}),
            tenant_id=data.get("tenant_id", "default"),
            source_type=data.get("source_type", ""),
            source_ref=data.get("source_ref", ""),
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            subject_id=data.get("subject_id", ""),
            valid_from=_parse_datetime(data.get("valid_from"), "valid_from"),
            valid_until=_parse_datetime(data.get("valid_until"), "valid_until"),
            observed_at=_parse_datetime(data.get("observed_at"), "observed_at"),
            correlation_id=data.get("correlation_id") or data.get("run_id"),
            causation_id=data.get("causation_id"),
            access_scope=data.get("access_scope", "default"),
            trust_level=float(data.get("trust_level", 0.5)),
        )
    except ValueError as exc:
        message = str(exc)
        return jsonify({"error": message}), 409 if message.startswith("IDEMPOTENCY_CONFLICT") else 400
    return jsonify({"event_id": event_id}), 201


@soil_bp.route("/api/v1/soil/events/<event_id>", methods=["GET"])
@inject
async def get_event(event_id, soil_service=Provide[ServerContainer.soil_service]):
    event = await soil_service.get_event(event_id)
    if not event:
        return jsonify({"error": "Event not found"}), 404
    return jsonify(event.model_dump(mode="json"))
