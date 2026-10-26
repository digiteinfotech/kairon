"""
Parity fixture recorder (pytest plugin).

Records one JSON fixture per passing test node of the Python action-server suite,
without editing any test file. Opt in with ``--record-fixtures`` or
``KAIRON_RECORD_FIXTURES=1``; when not enabled the plugin is never registered and
the test run is unchanged.

Per node it captures (see tests/parity/fixture-schema.md):
  * mongo.seed     - documents present when the first inbound request is sent
                     (bot-scoped) plus documents created before it during the test
  * exchanges      - every inbound request sent through starlette's TestClient and
                     the response it returned (the /webhook call)
  * upstream       - every outbound call answered by a ``responses`` or
                     ``aioresponses`` mock, with the canned reply (or the raised error)
  * mongo.written  - documents inserted / updated / deleted after the first inbound
                     request until the end of the test body

Before writing, volatile values (run-time timestamps, ObjectIds, UUIDs, JWTs, request
ids) are replaced by placeholder tokens (tests/parity/normalize.py), so recording the same
suite twice yields byte-identical fixtures; ``--record-raw`` / ``KAIRON_RECORD_RAW=1`` skips
that and writes raw values (``normalized: false``). BSON values are canonical extended JSON (bson.json_util.CANONICAL_JSON_OPTIONS).
"""
import base64
import hashlib
import json
import os
import re
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest
from bson import json_util

SCHEMA_VERSION = 1
ENV_FLAG = "KAIRON_RECORD_FIXTURES"
ENV_DIR = "KAIRON_RECORD_DIR"
ENV_DATABASES = "KAIRON_RECORD_DATABASES"
ENV_RAW = "KAIRON_RECORD_RAW"
PLUGIN_NAME = "kairon-parity-recorder"
DEFAULT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")
SYSTEM_DATABASES = {"admin", "local", "config"}

# Overridable for tests: callable returning a pymongo-compatible client (or None).
CLIENT_PROVIDER: Optional[Callable[[], Any]] = None
# Overridable for tests: callable(client) -> list of database names to snapshot.
DATABASES_PROVIDER: Optional[Callable[[Any], List[str]]] = None


# --------------------------------------------------------------------------- hooks

def pytest_addoption(parser):
    group = parser.getgroup("parity", "parity fixture recorder")
    group.addoption("--record-fixtures", action="store_true", default=False,
                    help="record one parity fixture JSON per passing test node")
    group.addoption("--record-fixtures-dir", action="store", default=None,
                    help=f"output directory for recorded fixtures (default {DEFAULT_DIR})")
    group.addoption("--record-raw", action="store_true", default=False,
                    help="write raw fixtures (skip placeholder normalization)")


def is_enabled(config) -> bool:
    flag = os.environ.get(ENV_FLAG, "").strip().lower() in {"1", "true", "yes", "on"}
    try:
        opt = config.getoption("--record-fixtures")
    except ValueError:
        opt = False
    return bool(opt or flag)


def pytest_configure(config):
    if not is_enabled(config) or config.pluginmanager.has_plugin(PLUGIN_NAME):
        return
    try:
        out_dir = config.getoption("--record-fixtures-dir")
    except ValueError:
        out_dir = None
    out_dir = out_dir or os.environ.get(ENV_DIR) or DEFAULT_DIR
    try:
        raw = config.getoption("--record-raw")
    except ValueError:
        raw = False
    raw = bool(raw or os.environ.get(ENV_RAW, "").strip().lower() in {"1", "true", "yes", "on"})
    config.pluginmanager.register(FixtureRecorder(out_dir, normalize=not raw), PLUGIN_NAME)


# ----------------------------------------------------------------------- encoding

def to_canonical(value: Any) -> Any:
    """Encode a BSON-capable value as canonical extended JSON (python object form)."""
    return json.loads(json_util.dumps(value, json_options=json_util.CANONICAL_JSON_OPTIONS))


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return to_canonical(value)


def encode_body(raw: Any) -> Dict[str, Any]:
    """Body envelope: {"encoding": "empty|json|text|form|base64", "value": ...}."""
    if raw is None or raw == b"" or raw == "":
        return {"encoding": "empty", "value": None}
    if isinstance(raw, dict):
        return {"encoding": "form", "value": _jsonable(raw)}
    if isinstance(raw, (bytes, bytearray)):
        try:
            text = bytes(raw).decode("utf-8")
        except UnicodeDecodeError:
            return {"encoding": "base64", "value": base64.b64encode(bytes(raw)).decode("ascii")}
    elif isinstance(raw, str):
        text = raw
    else:
        return {"encoding": "text", "value": str(raw)}
    try:
        return {"encoding": "json", "value": json.loads(text)}
    except ValueError:
        return {"encoding": "text", "value": text}


def encode_headers(headers: Any) -> List[List[str]]:
    if not headers:
        return []
    items = headers.items() if hasattr(headers, "items") else headers
    return [[str(k), str(v)] for k, v in items]


def fixture_filename(node_id: str) -> str:
    slug = re.sub(r"[^A-Za-z0-9._-]+", "_", node_id).strip("_")[:150]
    digest = hashlib.sha1(node_id.encode("utf-8")).hexdigest()[:10]
    return f"{slug}-{digest}.json"


def dump_fixture(fixture: Dict[str, Any]) -> str:
    return json.dumps(fixture, indent=2, ensure_ascii=False) + "\n"


# ----------------------------------------------------------------------- mongo

def _default_client():
    try:
        from mongoengine.connection import get_connection
        return get_connection()
    except Exception:
        return None


def _default_databases(client) -> List[str]:
    env = os.environ.get(ENV_DATABASES)
    if env:
        return [d.strip() for d in env.split(",") if d.strip()]
    names = []
    try:
        from mongoengine.connection import get_db
        names.append(get_db().name)
    except Exception:
        pass
    try:
        from kairon.shared.utils import Utility
        names.append(Utility.environment["events"]["queue"]["name"])
    except Exception:
        pass
    names = [n for n in dict.fromkeys(names) if n]
    if not names:
        names = [n for n in client.list_database_names() if n not in SYSTEM_DATABASES]
    return names


Snapshot = Dict[Tuple[str, str, str], Dict[str, Any]]


def take_snapshot(client, databases: List[str]) -> Snapshot:
    snap: Snapshot = {}
    for db_name in databases:
        db = client[db_name]
        for coll in sorted(db.list_collection_names()):
            if coll.startswith("system."):
                continue
            for doc in db[coll].find():
                key = json_util.dumps(doc.get("_id"), json_options=json_util.CANONICAL_JSON_OPTIONS)
                snap[(db_name, coll, key)] = doc
    return snap


def _canon_doc(doc) -> str:
    return json_util.dumps(doc, json_options=json_util.CANONICAL_JSON_OPTIONS)


def _group(entries) -> Dict[str, Dict[str, list]]:
    out: Dict[str, Dict[str, list]] = {}
    for (db, coll, key), value in sorted(entries, key=lambda e: e[0]):
        out.setdefault(db, {}).setdefault(coll, []).append(value)
    return out


def _doc_bot(doc) -> Optional[str]:
    bot = doc.get("bot") if isinstance(doc, dict) else None
    return str(bot) if bot is not None else None


def compute_seed(start: Snapshot, at_request: Snapshot, bots: List[str]) -> Dict[str, Any]:
    entries = []
    for key, doc in at_request.items():
        changed = key not in start or _canon_doc(start[key]) != _canon_doc(doc)
        if changed or (bots and _doc_bot(doc) in bots):
            entries.append((key, to_canonical(doc)))
    return _group(entries)


def compute_written(before: Snapshot, after: Snapshot) -> Dict[str, Any]:
    written: Dict[str, Dict[str, Dict[str, list]]] = {}

    def slot(db, coll):
        return written.setdefault(db, {}).setdefault(coll, {"inserted": [], "updated": [], "deleted": []})

    for key in sorted(after):
        db, coll, _ = key
        if key not in before:
            slot(db, coll)["inserted"].append(to_canonical(after[key]))
        elif _canon_doc(before[key]) != _canon_doc(after[key]):
            slot(db, coll)["updated"].append(to_canonical(after[key]))
    for key in sorted(before):
        if key not in after:
            db, coll, _ = key
            slot(db, coll)["deleted"].append(to_canonical(before[key].get("_id")))
    return written


def _bots_from_request(body: Dict[str, Any]) -> List[str]:
    bots = []
    if body.get("encoding") == "json" and isinstance(body.get("value"), dict):
        value = body["value"]
        tracker = value.get("tracker") or {}
        slots = tracker.get("slots") or {} if isinstance(tracker, dict) else {}
        for candidate in (slots.get("bot") if isinstance(slots, dict) else None, value.get("bot")):
            if candidate:
                bots.append(str(candidate))
    return list(dict.fromkeys(bots))


# ----------------------------------------------------------------------- capture

class NodeCapture:
    def __init__(self, node_id: str, client, databases: List[str]):
        self.node_id = node_id
        self.client = client
        self.databases = databases
        self.exchanges: List[Dict[str, Any]] = []
        self.upstream: List[Dict[str, Any]] = []
        self.snap_start: Snapshot = {}
        self.snap_request: Optional[Snapshot] = None
        self.snap_end: Snapshot = {}
        self.bots: List[str] = []
        self.mongo_available = client is not None
        if self.mongo_available:
            self.snap_start = self._snap()

    def _snap(self) -> Snapshot:
        try:
            return take_snapshot(self.client, self.databases)
        except Exception:
            self.mongo_available = False
            return {}

    def before_inbound(self, request_body: Dict[str, Any]):
        if self.snap_request is None:
            self.bots = _bots_from_request(request_body)
            self.snap_request = self._snap() if self.mongo_available else {}

    def finish(self):
        if self.mongo_available:
            self.snap_end = self._snap()

    def add_upstream(self, client_name: str, method: str, url: str, headers, body) -> Dict[str, Any]:
        entry = {
            "seq": len(self.upstream),
            "client": client_name,
            "request": {"method": str(method).upper(), "url": str(url),
                        "headers": encode_headers(headers), "body": body},
            "response": None,
            "error": None,
        }
        self.upstream.append(entry)
        return entry

    def build(self) -> Dict[str, Any]:
        if self.snap_request is None:
            # No inbound request (e.g. unit tests calling actions directly): nothing marks
            # the end of setup, so every write during the test body counts as written.
            seed = {}
            written = compute_written(self.snap_start, self.snap_end) if self.mongo_available else {}
        else:
            seed = compute_seed(self.snap_start, self.snap_request, self.bots) if self.mongo_available else {}
            written = compute_written(self.snap_request, self.snap_end) if self.mongo_available else {}
        return {
            "schema_version": SCHEMA_VERSION,
            "node_id": self.node_id,
            "normalized": False,
            "mongo": {
                "available": self.mongo_available,
                "databases": list(self.databases) if self.mongo_available else [],
                "seed": seed,
                "written": written,
            },
            "exchanges": self.exchanges,
            "upstream": self.upstream,
        }


def _response_record(status, headers, raw_body) -> Dict[str, Any]:
    return {"status": int(status), "headers": encode_headers(headers), "body": encode_body(raw_body)}


def _error_record(exc: BaseException) -> Dict[str, Any]:
    return {"type": f"{type(exc).__module__}.{type(exc).__qualname__}", "message": str(exc)}


class FixtureRecorder:
    """pytest plugin object; registered only when recording is enabled."""

    def __init__(self, out_dir: str, normalize: bool = True):
        self.out_dir = out_dir
        self.normalize = normalize
        self.current: Optional[NodeCapture] = None
        self._patches: List[Tuple[Any, str, Any]] = []
        self._reports: Dict[str, Dict[str, Any]] = {}
        self._built: Dict[str, Dict[str, Any]] = {}

    # ---- patching
    def _patch(self, owner, name, replacement):
        self._patches.append((owner, name, owner.__dict__[name]))
        setattr(owner, name, replacement)

    def _install(self):
        recorder = self
        try:
            from starlette.testclient import TestClient
            orig_request = TestClient.__dict__["request"]

            def request(client_self, method, url, *args, **kwargs):
                cap = recorder.current
                if cap is None:
                    return orig_request(client_self, method, url, *args, **kwargs)
                body = encode_body(_inbound_body(kwargs))
                cap.before_inbound(body)
                response = orig_request(client_self, method, url, *args, **kwargs)
                sent = response.request
                cap.exchanges.append({
                    "request": {
                        "method": sent.method,
                        "path": sent.url.path,
                        "query": sent.url.query.decode("utf-8") if isinstance(sent.url.query, bytes)
                        else str(sent.url.query),
                        "headers": encode_headers(sent.headers.multi_items()),
                        "body": encode_body(sent.content),
                    },
                    "response": _response_record(response.status_code, response.headers.multi_items(),
                                                 response.content),
                })
                return response

            self._patch(TestClient, "request", request)
        except ImportError:
            pass

        try:
            import responses as responses_lib
            orig_on_request = responses_lib.RequestsMock.__dict__["_on_request"]

            def _on_request(mock_self, adapter, request, *args, **kwargs):
                cap = recorder.current
                if cap is None or kwargs.get("retries") is not None:
                    return orig_on_request(mock_self, adapter, request, *args, **kwargs)
                entry = cap.add_upstream("requests", request.method, request.url, request.headers,
                                         encode_body(request.body))
                try:
                    resp = orig_on_request(mock_self, adapter, request, *args, **kwargs)
                except BaseException as exc:
                    entry["error"] = _error_record(exc)
                    raise
                entry["response"] = _response_record(resp.status_code, resp.headers, resp.content)
                return resp

            self._patch(responses_lib.RequestsMock, "_on_request", _on_request)
        except ImportError:
            pass

        try:
            from aioresponses import aioresponses as aio_cls
            orig_match = aio_cls.__dict__["match"]

            async def match(mock_self, method, url, *args, **kwargs):
                cap = recorder.current
                if cap is None:
                    return await orig_match(mock_self, method, url, *args, **kwargs)
                entry = cap.add_upstream("aiohttp", method, url, kwargs.get("headers"),
                                         _aiohttp_body(kwargs))
                try:
                    resp = await orig_match(mock_self, method, url, *args, **kwargs)
                except BaseException as exc:
                    entry["error"] = _error_record(exc)
                    raise
                if resp is None:
                    entry["error"] = {"type": "aiohttp.ClientConnectionError",
                                      "message": f"Connection refused: {method} {url}"}
                    return resp
                raw = await resp.read()
                entry["response"] = _response_record(resp.status, resp.headers.items(), raw)
                return resp

            self._patch(aio_cls, "match", match)
        except ImportError:
            pass

    def _uninstall(self):
        while self._patches:
            owner, name, original = self._patches.pop()
            setattr(owner, name, original)

    # ---- hooks
    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_call(self, item):
        provider = CLIENT_PROVIDER or _default_client
        client = provider()
        databases = []
        if client is not None:
            try:
                databases = (DATABASES_PROVIDER or _default_databases)(client)
            except Exception:
                client = None
        self.current = NodeCapture(item.nodeid, client, databases)
        self._install()
        try:
            yield
        finally:
            self._uninstall()
            cap, self.current = self.current, None
            cap.finish()
            self._built[item.nodeid] = cap.build()

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_makereport(self, item, call):
        outcome = yield
        report = outcome.get_result()
        state = self._reports.setdefault(item.nodeid, {"ok": True, "call_passed": False})
        if report.failed or report.skipped or hasattr(report, "wasxfail"):
            state["ok"] = False
        if report.when == "call" and report.passed and not hasattr(report, "wasxfail"):
            state["call_passed"] = True

    def pytest_runtest_logfinish(self, nodeid, location):
        state = self._reports.pop(nodeid, {"ok": False, "call_passed": False})
        fixture = self._built.pop(nodeid, None)
        path = os.path.join(self.out_dir, fixture_filename(nodeid))
        if state["ok"] and state["call_passed"] and fixture is not None:
            if self.normalize:
                from tests.parity.normalize import normalize_fixture
                fixture = normalize_fixture(fixture)
            os.makedirs(self.out_dir, exist_ok=True)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(dump_fixture(fixture))
        elif os.path.exists(path):
            os.remove(path)


def _inbound_body(kwargs) -> Any:
    if kwargs.get("json") is not None:
        return json.dumps(kwargs["json"])
    return kwargs.get("content") or kwargs.get("data")


def _aiohttp_body(kwargs) -> Dict[str, Any]:
    if kwargs.get("json") is not None:
        return {"encoding": "json", "value": _jsonable(kwargs["json"])}
    return encode_body(kwargs.get("data"))
