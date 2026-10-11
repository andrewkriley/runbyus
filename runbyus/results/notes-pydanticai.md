# PydanticAI notes

## What we used

- `Agent` + `FunctionModel` for the S1 local read loop (`dns_query`, `pdns_get_record`).
- A second `Agent` for the cloud diagnose step after `router.switch_model`.
- Impactful write is **not** executed by the agent. The adapter writes an approval row and stops. `resume` applies `pdns_update_record` through MCP with `work_item_id:step`.
- Message / phase blobs go in ledger `runtime_state` (SPEC: PydanticAI history in the ledger).
- No Temporal / DBOS. Ledger + resumer was enough for S1.

## Verified

- Durable execution (Temporal or DBOS) is not required for the two runbyus scenarios.
- OpenTelemetry → AO was not wired. The shared `MemoryEmitter` is the only exporter, same as LangGraph, so the comparison stays fair.
- `requires_approval` / `DeferredToolRequests` would be the more native HITL path. We did not need it once the ledger owned the pause.

## Ledger fit

Runtime state is a cache row on the ledger. No second database. Score 5.

## Resume

More adapter code than LangGraph (pause is ledger-owned). After `kill -9`, reopen the ledger and call `resume`. Score 4.

## Model switching

Two agent runs with two models, plus a `route` row. Works, slightly more manual than a graph node. Score 4.

## Weight

`pydantic-ai-slim[mcp]` is the lighter dependency. Score 4.
