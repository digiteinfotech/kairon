"""[mock] HttpBenchRunner against a stand-in for the (not yet existing) infrastructure Bench runner."""
import hashlib
import hmac
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from kairon.crm.services.bench_runner import HttpBenchRunner
from kairon.exceptions import AppException

SECRET = "runner-secret-for-tests"


def resp(status=200, body=None):
    r = MagicMock(status_code=status)
    r.json.return_value = body or {}
    return r


def runner(**kw):
    return HttpBenchRunner("https://runner.internal", SECRET, sleep=lambda s: None, **kw)


def test_requests_are_signed_and_job_is_polled_to_success():
    calls = []

    def fake(method, url, data=None, headers=None, timeout=None):
        calls.append((method, url, data, headers))
        return resp(202, {"job_id": "job_1"}) if method == "POST" else resp(200, {"state": "succeeded", "result": {"site": "a.localhost"}})

    with patch("requests.request", side_effect=fake):
        out = runner().run("new_site", "acme.localhost", {"apps": ["crm"]}, idempotency_key="run-1:new_site")
    assert out.ok and out.result == {"site": "a.localhost"}
    method, url, data, headers = calls[0]
    assert url == "https://runner.internal/v1/operations"
    expected = hmac.new(SECRET.encode(), f"{headers['X-Kairon-Timestamp']}.".encode() + data, hashlib.sha256).hexdigest()
    assert headers["X-Kairon-Signature"] == "sha256=" + expected and headers["X-Kairon-Request-Id"].startswith("req_")
    assert json.loads(data)["idempotency_key"] == "run-1:new_site" and SECRET not in data.decode()


def test_unknown_operation_bad_site_and_credentials_are_refused_before_any_request():
    with patch("requests.request") as rq:
        for args, kwargs in ((("rm_rf", "acme.localhost"), {}), (("new_site", "../etc"), {}), (("new_site", "Acme.localhost"), {}),
                             (("new_site", "acme.localhost"), {"params": {"admin_password": "x"}})):
            with pytest.raises(AppException):
                runner().run(*args, **kwargs)
    rq.assert_not_called()


def test_transient_errors_are_retried_with_a_bound_then_reported():
    with patch("requests.request", side_effect=requests.ConnectionError("down")) as rq:
        with pytest.raises(AppException, match="unavailable"):
            runner(max_retries=3).run("site_exists", "acme.localhost")
    assert rq.call_count == 3


def test_transient_5xx_then_success():
    seq = [resp(503), resp(202, {"job_id": "j"}), resp(200, {"state": "succeeded", "result": {}})]
    with patch("requests.request", side_effect=seq):
        assert runner().run("site_exists", "acme.localhost").ok


def test_auth_failure_is_not_retried():
    with patch("requests.request", return_value=resp(401)) as rq:
        with pytest.raises(AppException, match="authentication"):
            runner().run("site_exists", "acme.localhost")
    assert rq.call_count == 1


def test_failed_job_reports_error_and_slow_job_times_out():
    with patch("requests.request", side_effect=[resp(202, {"job_id": "j"}), resp(200, {"state": "failed", "error": "db down"})]):
        out = runner().run("new_site", "acme.localhost")
    assert not out.ok and out.error == "db down"
    ticks = iter(range(0, 10000, 400))
    slow = HttpBenchRunner("https://r", SECRET, job_timeout=1200, sleep=lambda s: None, clock=lambda: next(ticks))
    seq = [resp(202, {"job_id": "j"})] + [resp(200, {"state": "running"})] * 10
    with patch("requests.request", side_effect=seq):
        with pytest.raises(AppException, match="did not finish"):
            slow.run("new_site", "acme.localhost")


def test_invalid_job_id_and_missing_configuration_are_rejected():
    with patch("requests.request", return_value=resp(202, {"job_id": "../x"})):
        with pytest.raises(AppException, match="invalid job id"):
            runner().run("new_site", "acme.localhost")
    with pytest.raises(AppException):
        HttpBenchRunner("", "")


def test_runner_mode_with_incomplete_configuration_fails_preflight_before_any_docker_call():
    from kairon.shared.utils import Utility
    from kairon.crm.services.preflight_validator import PreFlightValidator
    bench = Utility.environment.setdefault("crm", {}).setdefault("bench", {})
    saved = dict(bench)
    bench["execution_mode"] = "runner"
    bench["runner"] = {"url": "", "secret": ""}
    try:
        with patch("subprocess.run") as run:
            with pytest.raises(AppException, match="requires BENCH_RUNNER_URL and BENCH_RUNNER_SECRET"):
                PreFlightValidator.validate_infrastructure("c", "a.localhost", MagicMock(apps=["crm"]))
        run.assert_not_called()
    finally:
        bench.clear(); bench.update(saved)


def test_read_only_operations_get_a_fresh_idempotency_key_each_time_and_mutations_a_stable_one():
    import json as _json
    keys = []

    def fake(method, url, data=None, headers=None, timeout=None):
        if method == "POST":
            keys.append(_json.loads(data)["idempotency_key"])
            return resp(202, {"job_id": "j"})
        return resp(200, {"state": "succeeded", "result": {}})

    with patch("requests.request", side_effect=fake):
        runner().run("site_exists", "acme.localhost"); runner().run("site_exists", "acme.localhost")
        runner().run("new_site", "acme.localhost"); runner().run("new_site", "acme.localhost")
    assert keys[0] != keys[1] and keys[2] == keys[3] == "new_site:acme.localhost"
