"""Wire the shared runbyus core for one process."""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable
from pathlib import Path

from runbyus.common.approvals import Approvals
from runbyus.common.emitter import MemoryEmitter
from runbyus.common.ledger import Ledger
from runbyus.common.llm import ScriptedLlm
from runbyus.common.models import Classification, WorkItem
from runbyus.common.policy import Policy, load_policy
from runbyus.common.router import Router
from runbyus.common.tools.mcp_client import McpSession, module_command, workdir_from_db_url
from runbyus.common.tools.mock_list.store import ListStore
from runbyus.common.tools.mock_pdns.store import PdnsStore

REPO_ROOT = Path(__file__).resolve().parents[2]


class Harness:
    def __init__(
        self,
        ledger: Ledger,
        policy: Policy,
        workdir: Path,
        cleanup_dir: Path | None,
        runtime_name: str,
        classifier: Callable[[str], Classification] | None = None,
        llm=None,
    ):
        self.ledger = ledger
        self.policy = policy
        self.workdir = workdir
        self._cleanup_dir = cleanup_dir
        self.runtime_name = runtime_name
        self.llm = llm or ScriptedLlm()
        self.emitter = MemoryEmitter(policy, ledger)
        self.router = Router(ledger, policy, self.emitter, classifier=classifier)
        self.approvals = Approvals(ledger)
        self.pdns = PdnsStore(workdir / "pdns.sqlite")
        self.grocery = ListStore(workdir / "list.sqlite")
        env = {
            "PYTHONPATH": str(REPO_ROOT),
            "RUNBYUS_PDNS_DB": str(workdir / "pdns.sqlite"),
            "RUNBYUS_LIST_DB": str(workdir / "list.sqlite"),
        }
        self.pdns_mcp = McpSession(module_command("runbyus.common.tools.mock_pdns.server"), env)
        self.list_mcp = McpSession(module_command("runbyus.common.tools.mock_list.server"), env)
        self.runtime = self._make_runtime(runtime_name)

    @classmethod
    def build(
        cls,
        db_url: str | None = None,
        classifier: Callable[[str], Classification] | None = None,
        runtime: str = "",
        llm=None,
    ) -> "Harness":
        cleanup_dir = None
        if db_url is None:
            cleanup_dir = Path(tempfile.mkdtemp(prefix="runbyus-"))
            db_url = f"sqlite:///{cleanup_dir / 'ledger.sqlite'}"
            workdir = cleanup_dir
        else:
            fallback = Path(tempfile.mkdtemp(prefix="runbyus-"))
            workdir = workdir_from_db_url(db_url, fallback)
            if workdir == fallback:
                cleanup_dir = fallback
            else:
                shutil.rmtree(fallback, ignore_errors=True)
                workdir.mkdir(parents=True, exist_ok=True)
        ledger = Ledger.connect(db_url)
        ledger.apply_schema()
        ledger.seed_policy()
        from runbyus.common.runtime import resolve_runtime

        return cls(
            ledger,
            load_policy(),
            workdir,
            cleanup_dir,
            resolve_runtime(runtime),
            classifier,
            llm=llm,
        )

    def _make_runtime(self, name: str):
        if name == "pydanticai":
            from runbyus.pydanticai.adapter import PydanticAIRuntime

            return PydanticAIRuntime(self)
        from runbyus.langgraph.adapter import LangGraphRuntime

        return LangGraphRuntime(self)

    def use_runtime(self, name: str) -> None:
        if self.runtime_name == name and self.runtime is not None:
            return
        self.runtime_name = name
        self.runtime = self._make_runtime(name)

    def ingest_web(self, text: str) -> WorkItem:
        return self._ingest(text, channel="web", space="infra", label="infra", agent="infra")

    def ingest_telegram(self, text: str) -> WorkItem:
        return self._ingest(text, channel="telegram", space="family", label="shared", agent="family")

    def product_thread(self, channel: str):
        title = f"product:{channel}"
        existing = self.ledger.find_thread_by_title(title)
        if existing is not None:
            return existing
        channels = ["web"] if channel == "web" else ["web", "telegram"]
        return self.ledger.create_thread(
            space_id=self.policy.space_id("p1"),
            label_id=self.policy.label_id("personal"),
            principal_id="prn_01",
            title=title,
            enabled_channels=channels,
        )

    def ingest_turn(
        self,
        text: str,
        channel: str,
        space: str,
        label: str,
        agent: str,
        thread_id: str = "",
        new: bool = False,
    ) -> WorkItem:
        thread = self._resolve_product_thread(channel, text, thread_id=thread_id, new=new)
        self.ledger.add_message(thread.id, "principal", "prn_01", channel, text)
        item = self.ledger.create_work_item(
            thread_id=thread.id,
            space_id=self.policy.space_id(space),
            label_id=self.policy.label_id(label),
            principal_id="prn_01",
            trigger_kind="human",
            trigger_source=channel,
            agent=agent,
        )
        self.emitter.message(item, text, channel=channel)
        return item

    def start_product_thread(self, channel: str):
        channels = ["web"] if channel == "web" else ["web", "telegram"]
        return self.ledger.create_thread(
            space_id=self.policy.space_id("p1"),
            label_id=self.policy.label_id("personal"),
            principal_id="prn_01",
            title="New chat",
            enabled_channels=channels,
        )

    def latest_web_thread(self):
        best = None
        best_ts = ""
        for thread in self.ledger.list_threads():
            if "web" not in thread.enabled_channels or "telegram" in thread.enabled_channels:
                continue
            messages = self.ledger.list_messages(thread.id)
            stamp = messages[-1].created_at if messages else thread.created_at
            if stamp >= best_ts:
                best = thread
                best_ts = stamp
        return best

    def _resolve_product_thread(self, channel: str, text: str, thread_id: str = "", new: bool = False):
        chosen = (thread_id or "").strip()
        title = (text or "").strip()[:80] or "New chat"
        if chosen:
            thread = self.ledger.get_thread(chosen)
            if thread.title in {"", "New chat", f"product:{channel}"}:
                return self.ledger.set_thread_title(thread.id, title)
            return thread
        if channel == "telegram":
            return self.product_thread("telegram")
        if new:
            return self.ledger.create_thread(
                space_id=self.policy.space_id("p1"),
                label_id=self.policy.label_id("personal"),
                principal_id="prn_01",
                title=title,
                enabled_channels=["web"],
            )
        existing = self.latest_web_thread()
        if existing is None:
            return self.ledger.create_thread(
                space_id=self.policy.space_id("p1"),
                label_id=self.policy.label_id("personal"),
                principal_id="prn_01",
                title=title,
                enabled_channels=["web"],
            )
        if existing.title in {"", "New chat", "product:web"}:
            return self.ledger.set_thread_title(existing.id, title)
        return existing

    def _ingest(self, text: str, channel: str, space: str, label: str, agent: str) -> WorkItem:
        space_id = self.policy.space_id(space)
        label_id = self.policy.label_id(label)
        channels = ["web"] if channel == "web" else ["web", "telegram"]
        thread = self.ledger.create_thread(
            space_id=space_id,
            label_id=label_id,
            principal_id="prn_01",
            title=text[:80],
            enabled_channels=channels,
        )
        self.ledger.add_message(thread.id, "principal", "prn_01", channel, text)
        item = self.ledger.create_work_item(
            thread_id=thread.id,
            space_id=space_id,
            label_id=label_id,
            principal_id="prn_01",
            trigger_kind="human",
            trigger_source=channel,
            agent=agent,
        )
        return item

    def call_tool(self, work_item: WorkItem, server: str, name: str, arguments: dict) -> dict:
        session = self.pdns_mcp if server == "pdns" else self.list_mcp
        result = session.call_tool(name, arguments)
        self.emitter.tool(work_item, name, arguments, result)
        return result

    def close(self) -> None:
        for obj in (self.pdns_mcp, self.list_mcp, self.pdns, self.grocery, self.ledger):
            try:
                obj.close()
            except Exception:
                pass
        if self._cleanup_dir is not None:
            shutil.rmtree(self._cleanup_dir, ignore_errors=True)

    def __enter__(self) -> "Harness":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def open_harness(
    db_url: str | None = None,
    classifier: Callable[[str], Classification] | None = None,
    runtime: str = "",
    llm=None,
) -> Harness:
    return Harness.build(db_url=db_url, classifier=classifier, runtime=runtime, llm=llm)
