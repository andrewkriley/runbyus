"""Run S1 until the impactful write pauses, then sleep (for kill -9)."""

from __future__ import annotations

import os
import time

from runbyus.common.harness import open_harness
from runbyus.langgraph.s1 import run as langgraph_s1
from runbyus.pydanticai.s1 import run as pydanticai_s1


def main() -> None:
    db_url = os.environ["RUNBYUS_DB_URL"]
    runtime = os.environ["RUNBYUS_RUNTIME"]
    run = langgraph_s1 if runtime == "langgraph" else pydanticai_s1
    with open_harness(db_url=db_url, runtime=runtime) as harness:
        item = run(harness, until="awaiting_approval")
        print(f"AWAITING {item.id}", flush=True)
        time.sleep(3600)


if __name__ == "__main__":
    main()
