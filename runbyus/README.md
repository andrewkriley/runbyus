# Runtime runbyus

LangGraph vs PydanticAI on the same shared harness. This tree is the phase-2 concept.

Mock tools only. The runbyus never touches real DNS or real lists.

## Scripted tests (CI)

```bash
uv sync
uv run python -m unittest discover -s tests -v
```

No local listener, Anthropic, or OpenAI required.

## Operator CLI (both stacks)

Workdir default is `$PWD/.runbyus/` (gitignored).

Scripted (same behaviour as the unit tests — no model keys):

```bash
uv run python -m runbyus run s1 --runtime langgraph
uv run python -m runbyus approve wi_...
uv run python -m runbyus resume --runtime langgraph --work-item wi_...
uv run python -m runbyus show wi_...

uv run python -m runbyus run s2 --runtime pydanticai
```

Repeat with `--runtime pydanticai` / `langgraph`.

## Operator web UI

Product assistant is `/`. `/app` 302s home. Channel is the door, router picks space and model. Web history is a left rail of SPEC §3 threads; pickup continues that `thread_id`. Inspect shows session / traces / spans from the ledger-backed `MemoryEmitter`. Same harness as the CLI. Q10 = PydanticAI. LangGraph stays in-tree for a later switch.

```bash
uv run python -m runbyus ui
```

Open `http://127.0.0.1:8765`. Scripted S1/S2 needs no keys. Live needs the names in [`.env.example`](../.env.example) in the process environment.

`--host` / `--port` override the bind. CLI default is `127.0.0.1:8765`.

## Live models (OpenAI-spec local + cloud diagnose)

`--live` calls a real OpenAI-compatible `/v1` endpoint for local reads, then Anthropic Messages or OpenAI Chat Completions for the diagnose / propose step. Tools stay on the mock MCP servers.

1. Copy [`.env.example`](../.env.example) and export values. Never commit them.
2. Check what is missing (prints names only):

```bash
uv run python -m runbyus doctor
```

3. Run:

```bash
uv run python -m runbyus run s1 --runtime langgraph --live
uv run python -m runbyus approve wi_...
uv run python -m runbyus resume --runtime langgraph --work-item wi_... --live
```

Same commands with `--runtime pydanticai`. S2 does not need `--live` (rules route, no model).

`--live --target local` is the only local listener. Default URL is `http://127.0.0.1:8000/v1`.
`--live --cloud` picks the diagnose provider. Default is `anthropic`. Use `--cloud openai` for OpenAI Chat Completions (`gpt-4o` unless you change `RUNBYUS_OPENAI_MODEL`).

Anthropic is `https://api.anthropic.com/v1/messages`.
OpenAI is `https://api.openai.com/v1/chat/completions`. Same diagnose slot: propose `pdns_update_record`, then approve.

## Scorecard

[`results/scorecard.md`](results/scorecard.md). Q10 = PydanticAI. LangGraph stays in-tree for a later switch (`RUNBYUS_RUNTIME` / `--runtime`). Channel is the door. Router picks space and model. Web history pickups a SPEC §3 thread. Inspect shows session / traces / spans.
