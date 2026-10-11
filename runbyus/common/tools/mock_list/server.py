"""stdio MCP server for the fake grocery list."""

from __future__ import annotations

import os

from runbyus.common.tools.mcp_stdio import serve
from runbyus.common.tools.mock_list.store import TOOLS, ListStore


def main() -> None:
    path = os.environ.get("RUNBYUS_LIST_DB", "list.sqlite")
    store = ListStore(path)
    serve(TOOLS, store.dispatch)


if __name__ == "__main__":
    main()
