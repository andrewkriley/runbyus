"""Operator CLI for scripted and live runbyus runs."""

from __future__ import annotations

import argparse
import json
import os
import sys

from runbyus.common.operator import (
    LiveIncomplete,
    decide,
    doctor,
    resolve_db,
    resume,
    run,
    show,
)
from runbyus.common.runtime import RUNTIMES
from runbyus.common.targets import CLOUD_IDS, DEFAULT_CLOUD, DEFAULT_TARGET, TARGET_IDS


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="runbyus", description="Run the runbyus stacks")
    sub = parser.add_subparsers(dest="cmd", required=True)

    run_p = sub.add_parser("run", help="Start S1 or S2 on one runtime")
    run_p.add_argument("scenario", choices=("s1", "s2"))
    run_p.add_argument("--runtime", choices=RUNTIMES, default="")
    run_p.add_argument("--db", default=os.environ.get("RUNBYUS_DB_URL", ""))
    run_p.add_argument("--live", action="store_true")
    run_p.add_argument("--target", choices=TARGET_IDS, default=DEFAULT_TARGET)
    run_p.add_argument("--cloud", choices=CLOUD_IDS, default=DEFAULT_CLOUD)

    sub.add_parser("doctor", help="Check live model env without printing secrets")

    ap = sub.add_parser("approve", help="Approve a paused work item")
    ap.add_argument("work_item_id")
    ap.add_argument("--db", default=os.environ.get("RUNBYUS_DB_URL", ""))
    ap.add_argument("--by", default="prn_01")

    dn = sub.add_parser("deny", help="Deny a paused work item")
    dn.add_argument("work_item_id")
    dn.add_argument("--db", default=os.environ.get("RUNBYUS_DB_URL", ""))
    dn.add_argument("--by", default="prn_01")

    rs = sub.add_parser("resume", help="Resume after approve")
    rs.add_argument("--runtime", choices=RUNTIMES, default="")
    rs.add_argument("--work-item", required=True)
    rs.add_argument("--db", default=os.environ.get("RUNBYUS_DB_URL", ""))
    rs.add_argument("--live", action="store_true")
    rs.add_argument("--target", choices=TARGET_IDS, default=DEFAULT_TARGET)
    rs.add_argument("--cloud", choices=CLOUD_IDS, default=DEFAULT_CLOUD)

    sh = sub.add_parser("show", help="Print one work item as JSON")
    sh.add_argument("work_item_id")
    sh.add_argument("--db", default=os.environ.get("RUNBYUS_DB_URL", ""))

    ui = sub.add_parser("ui", help="Open the operator web UI for both stacks")
    ui.add_argument("--host", default=os.environ.get("RUNBYUS_UI_HOST", "127.0.0.1"))
    ui.add_argument("--port", type=int, default=int(os.environ.get("RUNBYUS_UI_PORT", "8765")))
    ui.add_argument("--db", default=os.environ.get("RUNBYUS_DB_URL", ""))

    args = parser.parse_args(argv)
    if args.cmd == "doctor":
        return _doctor()
    if args.cmd == "run":
        return _run(args)
    if args.cmd == "approve":
        return _decide(args, "approved")
    if args.cmd == "deny":
        return _decide(args, "denied")
    if args.cmd == "resume":
        return _resume(args)
    if args.cmd == "show":
        return _show(args)
    if args.cmd == "ui":
        return _ui(args)
    return 2


def _doctor() -> int:
    report = doctor()
    print(json.dumps(report, indent=2))
    return 0 if report["ready"] else 2


def _run(args) -> int:
    db = resolve_db(args.db)
    try:
        payload = run(db, args.scenario, args.runtime, args.live, args.target, args.cloud)
    except LiveIncomplete as exc:
        print("live config incomplete: " + ", ".join(exc.missing), file=sys.stdout)
        return 2
    print(
        json.dumps(
            {
                "scenario": payload["scenario"],
                "runtime": payload["runtime"],
                "live": payload["live"],
                "target": payload["target"],
                "cloud": payload["cloud"],
                "work_item_id": payload["work_item_id"],
                "state": payload["state"],
                "db": db,
            }
        )
    )
    return 0


def _decide(args, decision: str) -> int:
    db = resolve_db(args.db)
    approval = decide(db, args.work_item_id, decision, args.by, channel="cli")
    print(json.dumps(approval))
    return 0


def _resume(args) -> int:
    db = resolve_db(args.db)
    try:
        payload = resume(db, args.runtime, args.work_item, args.live, args.target, args.cloud)
    except LiveIncomplete as exc:
        print("live config incomplete: " + ", ".join(exc.missing), file=sys.stdout)
        return 2
    print(
        json.dumps(
            {
                "work_item_id": payload["work_item_id"],
                "state": payload["state"],
                "runtime": args.runtime,
            }
        )
    )
    return 0


def _show(args) -> int:
    db = resolve_db(args.db)
    payload = show(db, args.work_item_id)
    print(
        json.dumps(
            {
                "work_item_id": payload["work_item_id"],
                "state": payload["state"],
                "agent": payload["agent"],
                "routes": payload["routes"],
                "approval": (
                    {
                        "id": payload["approval"]["id"],
                        "tool": payload["approval"]["tool"],
                        "decision": payload["approval"]["decision"],
                    }
                    if payload["approval"]
                    else None
                ),
            }
        )
    )
    return 0


def _ui(args) -> int:
    from runbyus.web import serve

    serve(resolve_db(args.db), host=args.host, port=args.port)
    return 0
