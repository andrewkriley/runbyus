# runbyus

A ledger-backed assistant with two runtime adapters on one harness. Design lives in [andrewkriley/runbyme](https://github.com/andrewkriley/runbyme). This repo is the runnable concept: SPEC §3 ledger as source of truth, channel ≠ space, scripted S1/S2, product chat with history and in-product session / trace / span inspect.

Default runtime is PydanticAI. LangGraph stays in-tree for a later switch (`RUNBYUS_RUNTIME` / `--runtime`). Tools stay on mock DNS and mock list servers.

```bash
uv sync
uv run python -m unittest discover -s tests -v
uv run python -m runbyus doctor
uv run python -m runbyus ui
```

Open `http://127.0.0.1:8765`. The page is the product assistant. Scripted S1/S2 needs no keys.

## Concept

- Channel is a door. The router picks space (`p1` chat / `family` add-list / `infra` DNS) and model.
- Web history is a left rail of SPEC §3 threads. Pickup continues that `thread_id`.
- Inspect shows session / traces / spans from the ledger-backed `MemoryEmitter`.
- Live local step is one OpenAI-spec listener (`local`). Cloud diagnose is Anthropic or OpenAI.
- A second channel named `telegram` exists in the ledger and tests. This extract does not ship a Bot API poller.

See [CONCEPT.md](CONCEPT.md) and [docs/decisions.md](docs/decisions.md). Operator CLI notes: [runbyus/README.md](runbyus/README.md).

## Contracts

- Test-driven. Scripted tests are the default path.
- Secrets stay in environment variables. Never commit values. Names are in [`.env.example`](.env.example).
- Web UI uses pinned [andrewkriley/design-system](https://github.com/andrewkriley/design-system) CSS variables. Do not fetch GitHub at runtime.
- GitHub Actions `hygiene` scans the tree (and paths) and fails on lab hostnames and product-family names. The scanner is tested against examples that must match.
