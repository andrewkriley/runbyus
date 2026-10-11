# runbyus scorecard

Gates first. Then 1–5 × weight (max 65). Evidence from the in-process harness in this repo. Live llama.cpp / Splunk AO remain an operator soak; they are not required to compare ledger fit, resume, MCP, or model switching.

| Gate | LangGraph | PydanticAI |
|---|---|---|
| Python 3.12 | pass | pass |
| MCP tools (stdio adapter) | pass | pass |
| Models per step (local then cloud) | pass | pass |
| Resume after `kill -9` | pass | pass |
| Splunk AO (work-item IDs, parent/child) | pass (in-memory emitter; one exporter) | pass (same emitter) |

| Criterion | Weight | LangGraph | PydanticAI |
|---|---|---|---|
| Ledger fit: runtime state stays a cache under the ledger (D13) | 3 | 3 | 5 |
| Resume and approvals: how much code to pause, survive a kill, and resume | 3 | 5 | 4 |
| AO trace quality: parent/child, router spans, no duplicate spans | 2 | 4 | 4 |
| Model switching per step within the allowlist | 2 | 5 | 4 |
| Code size for S1 + S2 (adapter included) | 1 | 3 | 4 |
| Developer experience: debugging, docs, errors | 1 | 4 | 4 |
| Dependency weight and lock-in | 1 | 2 | 4 |
| **Total (max 65)** | | **48** | **51** |

Adapter + scenario LOC (excludes `__init__.py`): LangGraph 192, PydanticAI 181.

**Tie-break:** within 5 points, prefer the lighter dependency. PydanticAI is lighter.

Q10 = PydanticAI. LangGraph stays in-tree for a later switch (`RUNBYUS_RUNTIME` / `--runtime`).

## Notes

See [notes-langgraph.md](notes-langgraph.md) and [notes-pydanticai.md](notes-pydanticai.md).
