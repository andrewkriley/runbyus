# Concept

runbyus is a personal agent platform: one ledger, one harness, two runtime adapters, a product chat, and scripted scenarios that prove the design without live models.

Design doctrine lives in [andrewkriley/runbyme](https://github.com/andrewkriley/runbyme). This repository is the public extract of the runnable harness.

## Ledger is the source of truth

SPEC §3 records live in SQLite (unit tests) or Postgres (`compose.yaml`). Runtime state is a cache under the ledger. Resume after a process kill reopens the same file. Approvals, routes, messages, threads, and AO traces persist there.

`MemoryEmitter` is the only observability wrapper. Session is `thread_id`. Trace is a work item. Spans stay `router` / `tool` / `message` with label redaction. Inspect reads those rows. There is no second exporter.

## Channel is not space

A channel is a door. `web` and `telegram` are channel names in the ledger and API. The router (`rules` → classifier → `switch_model`) picks space, label, provider, and model.

| Space | Typical trigger | Tools |
|---|---|---|
| `p1` | generic chat | none |
| `family` | `add milk` | mock list |
| `infra` | flaky DNS | mock PowerDNS |

Web chats are many SPEC §3 threads (New chat / pickup). A send without `thread_id` continues the latest web thread. The `telegram` channel stays one product thread in tests. This extract does not include a Telegram Bot API poller.

## Dual adapters, one winner

S1 (infra DNS, approval, resume) and S2 (family add-list) run on both PydanticAI and LangGraph. The scorecard picked PydanticAI. LangGraph stays for a later `RUNBYUS_RUNTIME` switch. Resume only on the runtime that paused the work item. There is no settings-page model picker.

## Live path

`--live` calls one local OpenAI-spec `/v1` endpoint, then Anthropic Messages or OpenAI Chat Completions for diagnose. Tools stay on the mock MCP servers. Copy [`.env.example`](.env.example). `python -m runbyus doctor` prints names, never secret values.

Default local target:

| `--target` | Default URL | Default model |
|---|---|---|
| `local` | `http://127.0.0.1:8000/v1` | `local-model` |

Cloud diagnose: `--cloud anthropic` (default) or `--cloud openai` (`gpt-4o` unless `RUNBYUS_OPENAI_MODEL` changes).

## Product UI

`/` is the assistant. `/app` 302s home. Three columns: history rail, chat + composer, session / trace / span inspect. Approvals stay in the thread.

## What this extract is not

Not a production host. Not a Cloudflare Worker. Not LangChain. Not a second AO backend. Mock DNS IPs in tests are `10.0.0.1` / `10.0.0.9`.
