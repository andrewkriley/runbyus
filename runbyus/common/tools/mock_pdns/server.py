"""stdio MCP server for the fake PowerDNS store."""

from __future__ import annotations

import os

from runbyus.common.tools.mcp_stdio import serve
from runbyus.common.tools.mock_pdns.store import TOOLS, PdnsStore


def main() -> None:
    path = os.environ.get("RUNBYUS_PDNS_DB", "pdns.sqlite")
    store = PdnsStore(path)
    serve(TOOLS, store.dispatch)


if __name__ == "__main__":
    main()
