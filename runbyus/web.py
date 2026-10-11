"""Local operator web UI for both runbyus stacks."""

from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from runbyus.common.operator import (
    LiveIncomplete,
    decide,
    doctor,
    ingest_product,
    list_items,
    list_product_conversation,
    list_product_feed,
    list_product_session,
    list_product_threads,
    options,
    resume,
    run,
    show,
    start_product_thread,
)
from runbyus.common.targets import DEFAULT_CLOUD, DEFAULT_TARGET

UI_DIR = Path(__file__).with_name("ui")
PRODUCT_DIR = Path(__file__).with_name("product")
MIME = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


class RunbyusHandler(BaseHTTPRequestHandler):
    db_url = ""

    def log_message(self, fmt: str, *args) -> None:
        if os_env_quiet():
            return
        super().log_message(fmt, *args)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            self._send_file(PRODUCT_DIR / "index.html")
            return
        if path in {"/app", "/app/", "/app/index.html"}:
            self._redirect("/")
            return
        if path in {"/healthz", "/health"}:
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if path.startswith("/api/"):
            self._api_get(path, urlparse(self.path).query)
            return
        if path == "/app.js":
            self._send_file(PRODUCT_DIR / "app.js")
            return
        if path == "/product.css":
            self._send_file(PRODUCT_DIR / "style.css")
            return
        if path.startswith("/app/"):
            rel = path[len("/app/") :]
            if ".." in rel:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            candidate = (PRODUCT_DIR / rel).resolve()
            if candidate.is_file() and PRODUCT_DIR.resolve() in candidate.parents:
                self._send_file(candidate)
                return
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        rel = path.lstrip("/")
        if ".." in rel:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        candidate = (UI_DIR / rel).resolve()
        if candidate.is_file() and UI_DIR.resolve() in candidate.parents:
            self._send_file(candidate)
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        try:
            body = self._read_json()
            if path == "/api/product/ingest":
                self._json(
                    HTTPStatus.OK,
                    ingest_product(
                        self.db_url,
                        channel=str(body.get("channel") or ""),
                        text=str(body.get("text") or ""),
                        live=bool(body.get("live")),
                        target=str(body.get("target") or DEFAULT_TARGET),
                        cloud=str(body.get("cloud") or DEFAULT_CLOUD),
                        thread_id=str(body.get("thread_id") or ""),
                        new=bool(body.get("new")),
                    ),
                )
                return
            if path == "/api/product/threads":
                self._json(
                    HTTPStatus.OK,
                    start_product_thread(
                        self.db_url,
                        channel=str(body.get("channel") or "web"),
                    ),
                )
                return
            if path == "/api/run":
                self._json(
                    HTTPStatus.OK,
                    run(
                        self.db_url,
                        scenario=str(body.get("scenario") or ""),
                        runtime=str(body.get("runtime") or ""),
                        live=bool(body.get("live")),
                        target=str(body.get("target") or DEFAULT_TARGET),
                        cloud=str(body.get("cloud") or DEFAULT_CLOUD),
                        message=str(body.get("message") or ""),
                    ),
                )
                return
            if path.endswith("/approve") and path.startswith("/api/product/items/"):
                work_item_id = _item_id(path, "/approve", prefix="/api/product/items/")
                self._json(HTTPStatus.OK, decide(self.db_url, work_item_id, "approved"))
                return
            if path.endswith("/deny") and path.startswith("/api/product/items/"):
                work_item_id = _item_id(path, "/deny", prefix="/api/product/items/")
                self._json(HTTPStatus.OK, decide(self.db_url, work_item_id, "denied"))
                return
            if path.endswith("/resume") and path.startswith("/api/product/items/"):
                work_item_id = _item_id(path, "/resume", prefix="/api/product/items/")
                self._json(
                    HTTPStatus.OK,
                    resume(
                        self.db_url,
                        runtime=str(body.get("runtime") or ""),
                        work_item_id=work_item_id,
                        live=bool(body.get("live")),
                        target=str(body.get("target") or DEFAULT_TARGET),
                        cloud=str(body.get("cloud") or DEFAULT_CLOUD),
                    ),
                )
                return
            if path.endswith("/approve") and path.startswith("/api/items/"):
                work_item_id = _item_id(path, "/approve")
                self._json(HTTPStatus.OK, decide(self.db_url, work_item_id, "approved"))
                return
            if path.endswith("/deny") and path.startswith("/api/items/"):
                work_item_id = _item_id(path, "/deny")
                self._json(HTTPStatus.OK, decide(self.db_url, work_item_id, "denied"))
                return
            if path.endswith("/resume") and path.startswith("/api/items/"):
                work_item_id = _item_id(path, "/resume")
                self._json(
                    HTTPStatus.OK,
                    resume(
                        self.db_url,
                        runtime=str(body.get("runtime") or ""),
                        work_item_id=work_item_id,
                        live=bool(body.get("live")),
                        target=str(body.get("target") or DEFAULT_TARGET),
                        cloud=str(body.get("cloud") or DEFAULT_CLOUD),
                    ),
                )
                return
        except LiveIncomplete as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "live config incomplete", "missing": exc.missing})
            return
        except KeyError:
            self._json(HTTPStatus.NOT_FOUND, {"error": "work item not found"})
            return
        except ValueError as exc:
            self._json(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _api_get(self, path: str, query: str = "") -> None:
        if path == "/api/health":
            self._json(HTTPStatus.OK, {"ok": True})
            return
        if path == "/api/options":
            self._json(HTTPStatus.OK, options())
            return
        if path == "/api/doctor":
            self._json(HTTPStatus.OK, doctor())
            return
        if path == "/api/product/conversation":
            params = parse_qs(query)
            channel = (params.get("channel") or ["web"])[0]
            thread_id = (params.get("thread_id") or [""])[0]
            self._json(
                HTTPStatus.OK,
                list_product_conversation(self.db_url, channel=channel, thread_id=thread_id),
            )
            return
        if path == "/api/product/threads":
            params = parse_qs(query)
            channel = (params.get("channel") or ["web"])[0]
            self._json(HTTPStatus.OK, list_product_threads(self.db_url, channel=channel))
            return
        if path == "/api/product/session":
            params = parse_qs(query)
            thread_id = (params.get("thread_id") or [""])[0]
            self._json(HTTPStatus.OK, list_product_session(self.db_url, thread_id=thread_id))
            return
        if path == "/api/product/feed":
            self._json(HTTPStatus.OK, list_product_feed(self.db_url))
            return
        if path == "/api/items":
            self._json(HTTPStatus.OK, list_items(self.db_url))
            return
        if path.startswith("/api/items/"):
            work_item_id = path.rsplit("/", 1)[-1]
            try:
                self._json(HTTPStatus.OK, show(self.db_url, work_item_id))
            except KeyError:
                self._json(HTTPStatus.NOT_FOUND, {"error": "work item not found"})
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("content-length") or 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        try:
            payload = json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError("invalid json") from exc
        return payload if isinstance(payload, dict) else {}

    def _redirect(self, location: str) -> None:
        self.send_response(HTTPStatus.FOUND)
        self.send_header("location", location)
        self.send_header("content-length", "0")
        self.end_headers()

    def _send_file(self, path: Path) -> None:
        data = path.read_bytes()
        ctype = MIME.get(path.suffix, "application/octet-stream")
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", ctype)
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json(self, status: int, payload: Any) -> None:
        data = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


def os_env_quiet() -> bool:
    import os

    return os.environ.get("RUNBYUS_UI_QUIET") == "1"


def _item_id(path: str, suffix: str, prefix: str = "/api/items/") -> str:
    if not path.startswith(prefix) or not path.endswith(suffix):
        raise ValueError("bad path")
    return path[len(prefix) : -len(suffix)]


def make_server(db_url: str, host: str = "127.0.0.1", port: int = 8765) -> ThreadingHTTPServer:
    class Bound(RunbyusHandler):
        pass

    Bound.db_url = db_url
    return ThreadingHTTPServer((host, port), Bound)


def serve(db_url: str, host: str = "127.0.0.1", port: int = 8765) -> None:
    httpd = make_server(db_url, host, port)
    bound_host, bound_port = httpd.server_address
    print(json.dumps({"ui": f"http://{bound_host}:{bound_port}", "app": f"http://{bound_host}:{bound_port}/", "db": db_url}))
    try:
        httpd.serve_forever()
    finally:
        httpd.server_close()
