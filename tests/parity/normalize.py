"""
Placeholder normalization and schema validation for parity fixtures (parity-harness R1, R2).

normalize_fixture() replaces volatile values (run-time timestamps, ObjectIds, UUIDs, JWTs,
request ids) with the placeholder tokens documented in fixture-schema.md, so that recording
the same suite twice yields byte-identical fixtures. The recorder applies it before writing
unless --record-raw is given.

Command line (exit status 1 when any fixture violates the schema):

    PYTHONPATH=$PWD .venv310/bin/python -m tests.parity.normalize --validate tests/parity/fixtures
    PYTHONPATH=$PWD .venv310/bin/python -m tests.parity.normalize tests/parity/fixtures   # normalize + validate
"""
import argparse
import base64
import copy
import json
import os
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixture-schema.json")
ENV_WINDOW_DAYS = "KAIRON_RECORD_VOLATILE_WINDOW_DAYS"
DEFAULT_WINDOW_DAYS = 366

REQUEST_ID_HEADER = re.compile(r"^x-(kairon-)?request-id$", re.IGNORECASE)
REQUEST_ID_FIELDS = {"request_id"}

JWT_RE = re.compile(r"eyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*")
UUID_RE = re.compile(r"(?<![0-9A-Fa-f-])[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
                     r"(?![0-9A-Fa-f-])")
UUID_HEX_RE = re.compile(r"(?<![0-9A-Fa-f])[0-9a-f]{32}(?![0-9A-Fa-f])")
OBJECT_ID_RE = re.compile(r"(?<![0-9A-Fa-f])[0-9a-f]{24}(?![0-9A-Fa-f])")
DATETIME_RE = re.compile(r"(?<!\d)\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d{1,9})?)?(Z|[+-]\d{2}:?\d{2})?(?!\d)")
EPOCH_RE = re.compile(r"(?<![\d.])(\d{13}|\d{10}(\.\d+)?)(?![\d.])")
NUMBER_KEYS = ("$numberLong", "$numberDouble", "$numberInt")


def window_seconds() -> float:
    try:
        days = float(os.environ.get(ENV_WINDOW_DAYS, DEFAULT_WINDOW_DAYS))
    except ValueError:
        days = DEFAULT_WINDOW_DAYS
    return days * 86400


class Normalizer:
    """
    One instance per fixture. A value is "generated at run time" when the time it encodes
    (date, epoch, ObjectId or uuid7 timestamp) lies within the window around reference_time.
    uuid4 values carry no time and are always volatile. Indexed tokens are assigned in
    traversal order, so the same original value gets the same index everywhere in the fixture.
    """

    def __init__(self, reference_time: Optional[float] = None, window: Optional[float] = None):
        self.now = time.time() if reference_time is None else reference_time
        self.window = window_seconds() if window is None else window
        self.indexes: Dict[str, Dict[str, int]] = {"OBJECT_ID": {}, "UUID": {}, "UUID_HEX": {}}
        self.request_ids: List[str] = []
        self.replaced: List[str] = []  # original volatile strings, used to detect binaries embedding them

    # ------------------------------------------------------------------ predicates
    def recent(self, seconds: float) -> bool:
        return abs(seconds - self.now) <= self.window

    def recent_epoch(self, number: float) -> bool:
        if 1e9 <= abs(number) < 1e11:
            return self.recent(number)
        if 1e12 <= abs(number) < 1e14:
            return self.recent(number / 1000)
        return False

    def volatile_object_id(self, hex_id: str) -> bool:
        return self.recent(int(hex_id[:8], 16))

    def volatile_uuid(self, hex32: str) -> bool:
        version, variant = hex32[12], hex32[16].lower()
        if variant not in "89ab":
            return False
        if version == "4":
            return True
        if version == "7":
            return self.recent(int(hex32[:12], 16) / 1000)
        return False

    def volatile_datetime(self, text: str) -> bool:
        from dateutil.parser import isoparse
        try:
            value = isoparse(text.replace(" ", "T", 1))
        except (ValueError, OverflowError):
            return False
        if value.tzinfo is None:
            # naive values may be local or UTC; accept either reading
            from datetime import timezone
            utc = value.replace(tzinfo=timezone.utc).timestamp()
            return self.recent(utc) or self.recent(value.timestamp())
        return self.recent(value.timestamp())

    # ------------------------------------------------------------------ tokens
    def indexed(self, kind: str, original: str) -> str:
        table = self.indexes[kind]
        key = original.lower()
        if key not in table:
            table[key] = len(table) + 1
        self.replaced.append(original)
        return "{{%s:%d}}" % (kind, table[key])

    def string(self, text: str) -> str:
        for rid in self.request_ids:
            if rid and rid in text:
                self.replaced.append(rid)
                text = text.replace(rid, "{{REQUEST_ID}}")

        def jwt(m):
            self.replaced.append(m.group(0))
            return "{{JWT}}"
        text = JWT_RE.sub(jwt, text)

        def uuid(m):
            raw = m.group(0)
            return self.indexed("UUID", raw) if self.volatile_uuid(raw.replace("-", "")) else raw
        text = UUID_RE.sub(uuid, text)

        def uuid_hex(m):
            raw = m.group(0)
            return self.indexed("UUID_HEX", raw) if self.volatile_uuid(raw) else raw
        text = UUID_HEX_RE.sub(uuid_hex, text)

        def object_id(m):
            raw = m.group(0)
            return self.indexed("OBJECT_ID", raw) if self.volatile_object_id(raw) else raw
        text = OBJECT_ID_RE.sub(object_id, text)

        def date_time(m):
            return "{{DATETIME}}" if self.volatile_datetime(m.group(0)) else m.group(0)
        text = DATETIME_RE.sub(date_time, text)

        def epoch(m):
            return "{{EPOCH}}" if self.recent_epoch(float(m.group(0))) else m.group(0)
        return EPOCH_RE.sub(epoch, text)

    # ------------------------------------------------------------------ traversal
    def collect_request_ids(self, value: Any, key: Optional[str] = None):
        if isinstance(value, dict):
            for k, v in value.items():
                self.collect_request_ids(v, k)
        elif isinstance(value, list):
            if len(value) == 2 and all(isinstance(v, str) for v in value) and REQUEST_ID_HEADER.match(value[0]):
                self._add_request_id(value[1])
            else:
                for v in value:
                    self.collect_request_ids(v)
        elif isinstance(value, str) and key in REQUEST_ID_FIELDS:
            self._add_request_id(value)

    def _add_request_id(self, value: str):
        # very short values would replace unrelated substrings
        if value and len(value) >= 8 and value not in self.request_ids:
            self.request_ids.append(value)
            # longest first so a request id containing another is replaced whole
            self.request_ids.sort(key=len, reverse=True)

    def walk(self, value: Any, binaries: List[Dict[str, Any]]) -> Any:
        if isinstance(value, dict):
            keys = set(value.keys())
            if keys == {"$oid"} and isinstance(value["$oid"], str):
                oid = value["$oid"]
                return self.indexed("OBJECT_ID", oid) if self.volatile_object_id(oid) else value
            if keys == {"$date"}:
                return "{{TIMESTAMP}}" if self.recent(self._date_seconds(value["$date"])) else value
            if len(keys) == 1 and next(iter(keys)) in NUMBER_KEYS:
                try:
                    number = float(next(iter(value.values())))
                except (TypeError, ValueError):
                    return value
                return "{{EPOCH}}" if self.recent_epoch(number) else value
            if keys == {"$binary"}:
                binaries.append(value)
                return value
            return {k: self.walk(v, binaries) for k, v in value.items()}
        if isinstance(value, list):
            return [self.walk(v, binaries) for v in value]
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            return "{{EPOCH}}" if self.recent_epoch(value) else value
        if isinstance(value, str):
            return self.string(value)
        return value

    @staticmethod
    def _date_seconds(date_value: Any) -> float:
        try:
            if isinstance(date_value, dict):
                return int(date_value.get("$numberLong")) / 1000
            if isinstance(date_value, (int, float)):
                return date_value / 1000
            from dateutil.parser import isoparse
            return isoparse(date_value).timestamp()
        except (TypeError, ValueError, OverflowError):
            return float("nan")

    def finish_binaries(self, binaries: List[Dict[str, Any]]):
        """A binary (e.g. a scheduler job_state pickle) embedding a replaced value becomes {{BINARY}}."""
        needles = [v.encode("utf-8") for v in dict.fromkeys(self.replaced) if v]
        for binary in binaries:
            payload = binary["$binary"]
            try:
                raw = base64.b64decode(payload["base64"]) if isinstance(payload, dict) else base64.b64decode(payload)
            except (ValueError, TypeError, KeyError):
                continue
            if any(n in raw for n in needles):
                if isinstance(payload, dict):
                    payload["base64"] = "{{BINARY}}"
                else:
                    binary["$binary"] = "{{BINARY}}"


def _blind_key(document: Any, reference_time: float, window: float) -> str:
    """Sort key: the document normalized without indexes (volatile values all look alike)."""
    blind = Normalizer(reference_time, window)
    normalized = blind.walk(copy.deepcopy(document), [])
    text = json.dumps(normalized, sort_keys=True, ensure_ascii=False)
    return re.sub(r"\{\{(OBJECT_ID|UUID|UUID_HEX):\d+\}\}", r"{{\1}}", text)


def _sort_documents(fixture: Dict[str, Any], reference_time: float, window: float):
    """Raw recordings sort documents by raw _id, which differs between runs; reorder by content."""
    mongo = fixture.get("mongo") or {}

    def order(docs):
        if isinstance(docs, list):
            docs.sort(key=lambda d: _blind_key(d, reference_time, window))

    for collections in (mongo.get("seed") or {}).values():
        for docs in collections.values():
            order(docs)
    for collections in (mongo.get("written") or {}).values():
        for writes in collections.values():
            for docs in writes.values():
                order(docs)


def normalize_fixture(fixture: Dict[str, Any], reference_time: Optional[float] = None,
                      window: Optional[float] = None) -> Dict[str, Any]:
    """Returns a normalized copy of a raw fixture (an already normalized fixture is returned unchanged)."""
    if fixture.get("normalized") is True:
        return copy.deepcopy(fixture)
    normalizer = Normalizer(reference_time, window)
    result = copy.deepcopy(fixture)
    _sort_documents(result, normalizer.now, normalizer.window)
    normalizer.collect_request_ids(result)
    binaries: List[Dict[str, Any]] = []
    out = {}
    for key, value in result.items():
        out[key] = value if key in ("schema_version", "node_id", "normalized") else normalizer.walk(value, binaries)
    normalizer.finish_binaries(binaries)
    out["normalized"] = True
    return out


# ---------------------------------------------------------------------- validation

def load_schema() -> Dict[str, Any]:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def validator():
    import jsonschema
    schema = load_schema()
    cls = jsonschema.validators.validator_for(schema)
    cls.check_schema(schema)
    return cls(schema)


def validate_fixture(fixture: Any, schema_validator=None) -> List[str]:
    """Schema violations as '<json path>: <message>' strings (empty when valid)."""
    schema_validator = schema_validator or validator()
    errors = sorted(schema_validator.iter_errors(fixture), key=lambda e: list(e.absolute_path))
    return [f"/{'/'.join(str(p) for p in e.absolute_path)}: {e.message}" for e in errors]


def _fixture_files(paths: List[str]) -> List[str]:
    files = []
    for path in paths:
        if os.path.isdir(path):
            files.extend(os.path.join(path, f) for f in sorted(os.listdir(path)) if f.endswith(".json"))
        else:
            files.append(path)
    return files


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m tests.parity.normalize",
                                     description="Normalize parity fixtures and validate them against the schema.")
    parser.add_argument("paths", nargs="+", help="fixture files or directories")
    parser.add_argument("--validate", action="store_true", help="only validate; do not rewrite files")
    args = parser.parse_args(argv)

    from tests.parity.recorder import dump_fixture
    schema_validator = validator()
    failed = 0
    files = _fixture_files(args.paths)
    for path in files:
        try:
            with open(path, encoding="utf-8") as fh:
                fixture = json.load(fh)
        except (OSError, ValueError) as e:
            print(f"INVALID {path}: {e}")
            failed += 1
            continue
        if not args.validate and isinstance(fixture, dict) and fixture.get("normalized") is False:
            reference_time = os.path.getmtime(path)
            fixture = normalize_fixture(fixture, reference_time)
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(dump_fixture(fixture))
        errors = validate_fixture(fixture, schema_validator)
        if errors:
            failed += 1
            print(f"INVALID {path}")
            for error in errors:
                print(f"  {error}")
    print(f"{len(files) - failed}/{len(files)} fixtures valid")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
