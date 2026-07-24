# API Contract

The client targets these endpoints under `YGGDRASIL_URL`:

| Operation | Endpoint |
|---|---|
| Health | `GET /api/v1/health` |
| Start Run | `POST /api/v1/runs` |
| Retrieve | `POST /api/v1/yggdrasil/retrieve` |
| Record references | `POST /api/v1/runs/{run_id}/references` |
| Record action | `POST /api/v1/runs/{run_id}/actions` |
| Feedback | `POST /api/v1/yggdrasil/feedback` |
| Soil event | `POST /api/v1/soil/events` |
| Finish Run | `POST /api/v1/runs/{run_id}/finish` |

Soil writes require `Idempotency-Key` and `X-Actor-Id`. The client generates both.

The legacy retrieval response is enveloped as `{"data": {"nodes": [], "edges": [], "markdown": ""}}`. Run references accept stable legacy IDs in the `revision_id` field until all callers use Tree/Ring revision IDs.

Environment variables:

- `YGGDRASIL_URL`: server origin, default `http://127.0.0.1:6061`.
- `YGGDRASIL_TENANT`: tenant ID, default `default`.
- `YGGDRASIL_ACTOR`: actor ID, default `claude-code`.
- `YGGDRASIL_TIMEOUT`: request timeout in seconds, default `10`.
