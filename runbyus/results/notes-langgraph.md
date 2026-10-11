# LangGraph notes

## What we used

- `StateGraph` with nodes for route, local reads, cloud diagnose, propose, apply, and the family list path.
- `interrupt()` in `propose` plus `Command(resume=...)` on `AgentRuntime.resume`.
- `thread_id = work_item_id` (SPEC §8).
- `SqliteSaver` next to the ledger file; `MemorySaver` only for a pure in-memory process.
- Tools go through the shared MCP stdio client. No LangGraph AO callback — the shared `MemoryEmitter` is the only exporter.

## Verified

- Checkpoint durability: we persist only what the checkpointer writes at the interrupt and at exit. We did not turn on per-step durability.
- Postgres checkpointer: not used in unit tests. `compose.yaml` is there for a live ledger; a later pass can point `PostgresSaver` at its own schema if the operator wants a live soak.
- `SplunkAOCallback` vs our emitter: we used the emitter only.

## Ledger fit

The checkpointer is a real second store. That is the D13 tension: resume is cheap and native, but graph state is not the ledger. Score 3.

## Resume

Least adapter code of the two. `interrupt` / `Command` is the feature. Survives `kill -9` when the sqlite checkpointer file is next to the ledger. Score 5.

## Model switching

A dedicated `cloud_diagnose` node calls `router.switch_model`. Natural fit. Score 5.

## Weight

`langgraph` + `langgraph-checkpoint-sqlite` plus the graph runtime. Heavier lock-in. Score 2.
