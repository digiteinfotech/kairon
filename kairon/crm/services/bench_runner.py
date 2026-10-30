"""
Bench execution boundary for tenant provisioning.

Default (`crm.bench.execution_mode: docker`, env BENCH_EXECUTION_MODE) is unchanged: every Bench action is
`docker exec <container> ...` from the Kairon process, which cannot work on AWS Fargate. In `runner` mode the
provisioners instead call an infrastructure-owned, authenticated HTTP Bench runner through `HttpBenchRunner`. **No such
runner exists in this repository**; this module is Kairon's client side of the contract below and is tested against a
stand-in only. The runner-side obligations are listed in docs/crm_redesign_design.md section 12.

Contract (named operations, never a raw command line):
  POST {url}/v1/operations  {"operation", "site", "params", "secrets", "idempotency_key"} -> 202 {"job_id"}
  GET  {url}/v1/jobs/{job_id}                -> 200 {"state": "queued|running|succeeded|failed", "result": {}, "error": ""}
Operations: health, site_exists, list_apps, new_site, install_app, drop_site, set_admin_password, set_encryption_key,
set_homepage, prepare_tenant, finalize_tenant, reload_workers. `site` is omitted for global operations (health,
reload_workers).
Security properties REQUIRED OF THE RUNNER (Kairon cannot enforce them): verify X-Kairon-Signature =
HMAC-SHA256(secret, "<X-Kairon-Timestamp>." + raw body) in constant time; reject timestamps older/newer than 300 s;
remember X-Kairon-Request-Id for at least 10 minutes and reject repeats (replay); reject unknown operations, sites that do
not match the tenant naming rule, and params outside each operation's schema; treat `secrets` as write-only (never log,
persist, echo or put in job results); honour `idempotency_key` per operation (same key => same job, no second site);
serve TLS inside the VPC only; hold the database root credentials itself.
Kairon side: `params` may never contain credential-like keys; secrets travel only in `secrets`; requests are retried only for
transport errors and 408/425/429/5xx (3 attempts, backoff); 401/403/other 4xx are never retried; job polling is bounded.
"""
import hashlib
import hmac
import json
import re
import time
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional, Text

import requests
from loguru import logger

from kairon.exceptions import AppException

OPERATIONS = ("health", "site_exists", "list_apps", "new_site", "install_app", "drop_site", "set_admin_password",
              "set_encryption_key", "set_homepage", "prepare_tenant", "finalize_tenant", "reload_workers")
GLOBAL_OPERATIONS = ("health", "reload_workers")
READ_ONLY_OPERATIONS = ("health", "site_exists", "list_apps")   # never replayed from a cached job: they must observe now
EXECUTION_MODES = ("docker", "runner")
SITE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_]{0,59}\.localhost$")
TERMINAL_OK, TERMINAL_FAIL = "succeeded", "failed"
TRANSIENT_STATUS = {408, 425, 429, 500, 502, 503, 504}


@dataclass
class BenchResult:
    ok: bool
    result: Dict[Text, Any]
    error: Optional[Text] = None


class HttpBenchRunner:

    def __init__(self, url: Text, secret: Text, request_timeout: int = 15, job_timeout: int = 1200,
                 poll_interval: float = 3.0, max_retries: int = 3, sleep=time.sleep, clock=time.monotonic):
        if not url or not secret:
            raise AppException("Bench runner URL and secret are required (crm.bench.runner.url / .secret).")
        self.url, self.secret = url.rstrip("/"), secret
        self.request_timeout, self.job_timeout = request_timeout, job_timeout
        self.poll_interval, self.max_retries = poll_interval, max_retries
        self._sleep, self._clock = sleep, clock

    def _signed(self, method: Text, path: Text, body: Optional[Dict] = None):
        raw = json.dumps(body, separators=(",", ":")).encode() if body is not None else b""
        ts = str(int(time.time()))
        sig = hmac.new(self.secret.encode(), f"{ts}.".encode() + raw, hashlib.sha256).hexdigest()
        headers = {"Content-Type": "application/json", "X-Kairon-Timestamp": ts,
                   "X-Kairon-Signature": f"sha256={sig}", "X-Kairon-Request-Id": f"req_{uuid.uuid4().hex}"}
        return requests.request(method, f"{self.url}{path}", data=raw or None, headers=headers,
                                timeout=self.request_timeout)

    def _call(self, method: Text, path: Text, body: Optional[Dict] = None):
        """Bounded retries for transient transport/5xx errors only; the operation's idempotency key makes them safe."""
        last = None
        for attempt in range(self.max_retries):
            try:
                response = self._signed(method, path, body)
                if response.status_code in TRANSIENT_STATUS:
                    last = f"HTTP {response.status_code}"
                elif response.status_code in (401, 403):
                    raise AppException("The Bench runner rejected the request (authentication failed).")
                elif response.status_code >= 400:
                    raise AppException(f"The Bench runner refused the request (HTTP {response.status_code}).")
                else:
                    return response.json()
            except requests.RequestException as e:
                last = type(e).__name__
            self._sleep(min(2 ** attempt, 10))
        raise AppException(f"The Bench runner is unavailable ({last}).")

    def run(self, operation: Text, site: Optional[Text] = None, params: Optional[Dict] = None,
            idempotency_key: Optional[Text] = None, secrets: Optional[Dict] = None) -> BenchResult:
        if operation not in OPERATIONS:
            raise AppException(f"Unsupported Bench operation '{operation}'.")
        if operation in GLOBAL_OPERATIONS:
            site = None
        elif not SITE_PATTERN.match(site or ""):
            raise AppException("Invalid tenant site name.")
        if any(k in (params or {}) for k in ("password", "admin_password", "db_password", "db_root_password")):
            raise AppException("Credentials must not be sent to the Bench runner; it holds them itself.")
        job = self._call("POST", "/v1/operations", {
            "operation": operation, "site": site, "params": params or {}, "secrets": secrets or {},
            "idempotency_key": idempotency_key or (f"{uuid.uuid4().hex}:{operation}" if operation in READ_ONLY_OPERATIONS
                                                   else f"{operation}:{site}")})
        job_id = job.get("job_id")
        if not job_id or not re.match(r"^[A-Za-z0-9_-]{1,64}$", str(job_id)):
            raise AppException("The Bench runner returned an invalid job id.")
        deadline = self._clock() + self.job_timeout
        while self._clock() < deadline:
            state = self._call("GET", f"/v1/jobs/{job_id}")
            if state.get("state") == TERMINAL_OK:
                return BenchResult(True, state.get("result") or {})
            if state.get("state") == TERMINAL_FAIL:
                logger.warning(f"[BenchRunner] {operation} failed for {site}")
                return BenchResult(False, {}, str(state.get("error") or "failed")[:300])
            self._sleep(self.poll_interval)
        raise AppException(f"The Bench runner did not finish '{operation}' within {self.job_timeout} s.")


def execution_mode() -> Text:
    """Validated `crm.bench.execution_mode`; anything but docker/runner is a configuration error, never a silent default."""
    from kairon.shared.utils import Utility
    bench = (Utility.environment.get("crm") or {}).get("bench") or {}
    mode = str(bench.get("execution_mode") or "docker").strip().lower()
    if mode not in EXECUTION_MODES:
        raise AppException(f"Invalid BENCH_EXECUTION_MODE '{mode}'. Use one of: {', '.join(EXECUTION_MODES)}.")
    return mode


def get_bench_runner() -> Optional[HttpBenchRunner]:
    """None in docker mode. In runner mode, a client built from validated configuration; missing or unsafe settings fail closed."""
    from kairon.shared.utils import Utility
    if execution_mode() == "docker":
        return None
    runner_cfg = ((Utility.environment.get("crm") or {}).get("bench") or {}).get("runner") or {}
    url, secret = (runner_cfg.get("url") or "").strip(), runner_cfg.get("secret") or ""
    if not url or not secret:
        raise AppException("BENCH_EXECUTION_MODE=runner requires BENCH_RUNNER_URL and BENCH_RUNNER_SECRET.")
    allow_http = str(runner_cfg.get("allow_insecure_http") or "").lower() in ("1", "true", "yes")
    if not url.startswith("https://") and not (allow_http and url.startswith("http://")):
        raise AppException("BENCH_RUNNER_URL must be https:// (BENCH_RUNNER_ALLOW_INSECURE_HTTP=true is for local development only).")
    return HttpBenchRunner(url, secret, job_timeout=int(runner_cfg.get("job_timeout_seconds") or 1200))
