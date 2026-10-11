# Decision log

Append only. This file is the public extract history.

| # | Area | Decision | Status | Date |
|---|---|---|---|---|
| P1 | Harness | The runnable concept and design notes live in this repo. | Agreed | 2026-10-10 |
| P2 | Ledger | Unit tests use SQLite with the SPEC §3 schema. Compose is Postgres. Same tables. | Agreed | 2026-10-10 |
| P3 | Models | Tests inject scripted / FunctionModel steps. Live keys stay in environment variables. | Agreed | 2026-10-10 |
| P4 | Q10 | Runtime winner is PydanticAI. LangGraph stays in-tree for a later switch. | Agreed | 2026-10-11 |
| P5 | Live models | `--live` uses OpenAI-spec `/v1` for the local step and Anthropic or OpenAI for diagnose. Scripted path remains the test default. | Agreed | 2026-10-10 |
| P6 | Local target | Live local step is one named listener: `local`. Default `http://127.0.0.1:8000/v1`. | Agreed | 2026-10-10 |
| P7 | Cloud diagnose | Live diagnose is Anthropic Messages or OpenAI Chat Completions. Default `anthropic`. OpenAI model must support Chat Completions tools (default `gpt-4o`). | Agreed | 2026-10-10 |
| P8 | UI | First-party console (`python -m runbyus ui`) drives both adapters on the same harness. | Agreed | 2026-10-10 |
| P9 | Default runtime | Product default is `pydanticai`. Later switch is `RUNBYUS_RUNTIME` or `--runtime`, not a settings page. Resume only on the runtime that paused the work item. | Agreed | 2026-10-11 |
| P10 | Product assistant | `/` is the chat. `/app` 302s home. Channel is a door. Router picks space, label, provider, and model. Generic chat is `p1` / personal. | Agreed | 2026-10-11 |
| P11 | Web history | Web chats are SPEC §3 threads. New chat mints a thread. Pickup continues that `thread_id`. Default send without `thread_id` continues the latest web thread. | Agreed | 2026-10-11 |
| P12 | In-product AO | Inspect shows session / traces / spans from `MemoryEmitter` on the ledger. Session is `thread_id`. Trace is a work item. Spans stay `router` / `tool` / `message`. Not a second exporter. | Agreed | 2026-10-11 |
| P13 | Second door | `telegram` is a channel name in the ledger, API, and S2 tests. This extract does not ship a Bot API poller. | Agreed | 2026-10-11 |
