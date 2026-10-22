"""
Provisioning through the HTTP Bench runner. [mock]: the runner is a stateful stand-in implementing the documented contract
(no real runner exists in this repository); [real]: the provisioners, pre-flight, BenchExecutor and the HTTP client's
signing/retry logic. `subprocess` is patched to fail so any leftover docker call is caught.
"""
import os
import uuid

os.environ["system_file"] = "./tests/testing_data/system.yaml"

from unittest.mock import MagicMock, patch

import pytest
from loguru import logger
from mongoengine import connect, disconnect

from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.crm.services import bench_runner
from kairon.crm.services.bench_executor import BenchExecutor
from kairon.crm.services.bench_runner import BenchResult, HttpBenchRunner, get_bench_runner
from kairon.crm.services.preflight_validator import PreFlightValidator
from kairon.crm.services.provisioners.crm_provisioner import CRMProvisioner
from kairon.crm.services.provisioners.erpnext_provisioner import ERPNextProvisioner
from kairon.crm.services.provisioners.upgrade_provisioner import AppUpgradeProvisioner
from kairon.crm.services.provisioning_models import ProvisioningPlan
from kairon.exceptions import AppException
from kairon.shared.utils import Utility

SITE = "acme_co.localhost"


@pytest.fixture(autouse=True, scope="module")
def db():
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
    yield
    disconnect()


@pytest.fixture
def bench_env():
    bench = Utility.environment.setdefault("crm", {}).setdefault("bench", {})
    saved = dict(bench)
    bench.update({"container_name": None, "execution_mode": "runner",
                  "runner": {"url": "https://runner.internal", "secret": "s3cret-for-tests"}})
    yield bench
    bench.clear(); bench.update(saved)


class FakeRunnerServer:
    """Implements the contract: operations, per-key idempotency, scripted failures. Records every call."""

    def __init__(self, existing_sites=(), apps=("frappe", "erpnext", "crm", "hrms", "kairon_connector"), fail=None, healthy=True):
        self.calls, self.jobs, self.sites, self.apps = [], {}, set(existing_sites), set(apps)
        self.fail, self.healthy = fail or {}, healthy

    def run(self, operation, site=None, params=None, idempotency_key=None, secrets=None):
        idempotency_key = idempotency_key or f"{uuid.uuid4().hex}:{operation}"     # what HttpBenchRunner does for read-only calls
        self.calls.append({"operation": operation, "site": site, "params": params or {}, "secrets": secrets or {}, "key": idempotency_key})
        if idempotency_key in self.jobs:
            return self.jobs[idempotency_key]
        if operation in self.fail:
            result = BenchResult(False, {}, self.fail[operation])
        elif operation == "health":
            result = BenchResult(self.healthy, {}, None if self.healthy else "degraded")
        elif operation == "site_exists":
            result = BenchResult(True, {"exists": site in self.sites})
        elif operation == "list_apps":
            result = BenchResult(True, {"apps": sorted(self.apps)})
        else:
            if operation == "new_site":
                self.sites.add(site)
            if operation == "drop_site":
                self.sites.discard(site)
            result = BenchResult(True, {})
        self.jobs[idempotency_key] = result
        return result

    def ops(self):
        return [c["operation"] for c in self.calls]


@pytest.fixture
def no_docker():
    with patch("subprocess.run", side_effect=AssertionError("docker/subprocess must not be used in runner mode")), \
            patch("subprocess.Popen", side_effect=AssertionError("docker/subprocess must not be used in runner mode")):
        yield


def make_doc(company="Acme Co", provisioning_id="run-1"):
    CRMClientDetails.objects(company_name=company).delete()
    return CRMClientDetails(company_name=company, abbr="AC", default_currency="INR", country="India", bot="runner_bot",
                            user="owner@acme.com", provisioning_id=provisioning_id,
                            onboarding_status=CRMOnboardingStatus.PROJECT_CREATED.value).save()


def tier1(server):
    plan = ProvisioningPlan(strategy_key="crm", tier=1, apps=["crm"], home_page="crm", default_roles=["Sales User"])
    with patch("kairon.crm.services.provisioners.base_provisioner.get_bench_runner", return_value=server):
        return CRMProvisioner(plan, Utility.environment["crm"]["bench"])


def with_runner(server):
    return patch("kairon.crm.services.preflight_validator.get_bench_runner", return_value=server)


# ------------------------------------------------------------------ provisioning flows

def test_tier1_provisioning_runs_entirely_through_the_runner_in_order(bench_env, no_docker):
    make_doc()
    server = FakeRunnerServer()
    p = tier1(server)
    with with_runner(server):
        out = p.provision("Acme Co", "AC", "INR", "India", "admin-pass-1234", "runner_bot")
    assert out["status"] == "success" and server.ops() == [
        "health", "site_exists", "list_apps", "new_site", "install_app", "set_encryption_key", "set_homepage",
        "prepare_tenant", "finalize_tenant", "reload_workers"]
    assert server.calls[3]["params"] == {"db_name": "frappe_crm_acme_co", "apps": ["crm"]} and server.calls[3]["site"] == SITE
    assert server.calls[4]["params"] == {"app": "kairon_connector"}
    assert CRMClientDetails.objects(company_name="Acme Co").first().onboarding_status == "SITE_CREATED"


def test_tier2_provisioning_installs_apps_in_the_documented_order(bench_env, no_docker):
    make_doc()
    server = FakeRunnerServer()
    plan = MagicMock(apps=["erpnext", "crm", "hrms"], home_page="workspace/Selling", default_roles=["Sales User"])
    with patch("kairon.crm.services.provisioners.base_provisioner.get_bench_runner", return_value=server):
        p = ERPNextProvisioner(plan, Utility.environment["crm"]["bench"])
    with with_runner(server), patch("kairon.crm.services.erpnext_client.ERPNextClient") as client:
        client.return_value = MagicMock()
        p.provision("Acme Co", "AC", "INR", "India", "admin-pass-1234", "runner_bot")
    installs = [c["params"]["app"] for c in server.calls if c["operation"] == "install_app"]
    assert installs == ["erpnext", "kairon_connector", "hrms"]                # crm first (new_site), then erpnext, connector, extras
    assert server.calls[3]["params"]["apps"] == ["crm"]


def test_credentials_travel_only_in_secrets_and_never_in_params_keys_or_logs(bench_env, no_docker):
    make_doc()
    server = FakeRunnerServer()
    p = tier1(server)
    sink = []
    handler = logger.add(lambda m: sink.append(str(m)), level="DEBUG")
    try:
        with with_runner(server):
            p.provision("Acme Co", "AC", "INR", "India", "admin-pass-1234", "runner_bot")
    finally:
        logger.remove(handler)
    for call in server.calls:
        assert "admin-pass-1234" not in str(call["params"]) and "admin-pass-1234" not in call["key"]
    assert [c["operation"] for c in server.calls if c["secrets"]] == ["new_site"]
    assert server.calls[3]["secrets"] == {"admin_password": "admin-pass-1234"}
    assert not any("admin-pass-1234" in line for line in sink)


def test_idempotency_keys_name_the_provisioning_run(bench_env, no_docker):
    make_doc(provisioning_id="run-A")
    server = FakeRunnerServer()
    with with_runner(server):
        tier1(server).provision("Acme Co", "AC", "INR", "India", "pw", "runner_bot")
    assert all(c["key"].startswith("run-A:") for c in server.calls if c["operation"] not in ("health", "site_exists", "list_apps"))
    keys = [c["key"] for c in server.calls if c["operation"] == "new_site"]
    assert keys == [f"run-A:new_site:{SITE}"]


def test_new_site_failure_rolls_back_through_the_runner_and_reports_the_reason(bench_env, no_docker):
    make_doc()
    server = FakeRunnerServer(fail={"new_site": "database unreachable"})
    p = tier1(server)
    with with_runner(server), pytest.raises(AppException, match=r"Bench new-site failed: database unreachable"):
        p.provision("Acme Co", "AC", "INR", "India", "pw", "runner_bot")
    assert "drop_site" in server.ops() and "install_app" not in server.ops()


def test_connector_install_failure_stops_provisioning(bench_env, no_docker):
    make_doc()
    server = FakeRunnerServer(fail={"install_app": "pip error"})
    with with_runner(server), pytest.raises(AppException, match="kairon_connector install failed: pip error"):
        tier1(server).provision("Acme Co", "AC", "INR", "India", "pw", "runner_bot")
    assert "prepare_tenant" not in server.ops()


def test_post_creation_steps_are_best_effort_like_the_docker_path(bench_env, no_docker):
    make_doc()
    server = FakeRunnerServer(fail={"prepare_tenant": "boom", "reload_workers": "boom"})
    with with_runner(server):
        out = tier1(server).provision("Acme Co", "AC", "INR", "India", "pw", "runner_bot")
    assert out["status"] == "success" and server.ops()[-2:] == ["finalize_tenant", "reload_workers"]


# ------------------------------------------------------------------ pre-flight

def test_preflight_refuses_existing_site_missing_apps_and_unhealthy_runner(bench_env, no_docker):
    plan = MagicMock(apps=["crm", "erpnext"])
    with with_runner(FakeRunnerServer(existing_sites=[SITE])), pytest.raises(AppException, match="already exists"):
        PreFlightValidator.validate_infrastructure("", SITE, plan)
    with with_runner(FakeRunnerServer(apps=["frappe"])), pytest.raises(AppException, match="required apps not available: crm, erpnext|crm, erpnext"):
        PreFlightValidator.validate_infrastructure("", SITE, plan)
    with with_runner(FakeRunnerServer(healthy=False)), pytest.raises(AppException, match="not healthy"):
        PreFlightValidator.validate_infrastructure("", SITE, plan)
    with with_runner(FakeRunnerServer()):
        PreFlightValidator.validate_infrastructure("", SITE, plan)           # passes
    with with_runner(FakeRunnerServer(existing_sites=[SITE])):
        PreFlightValidator.validate_infrastructure("", SITE, plan, is_upgrade=True)   # an upgrade expects the site


# ------------------------------------------------------------------ configuration

def test_runner_mode_requires_url_and_secret_and_https(bench_env):
    bench_env["runner"] = {"url": "", "secret": ""}
    with pytest.raises(AppException, match="requires BENCH_RUNNER_URL and BENCH_RUNNER_SECRET"):
        get_bench_runner()
    bench_env["runner"] = {"url": "https://r", "secret": ""}
    with pytest.raises(AppException, match="requires"):
        get_bench_runner()
    bench_env["runner"] = {"url": "http://r", "secret": "x"}
    with pytest.raises(AppException, match="must be https"):
        get_bench_runner()
    bench_env["runner"] = {"url": "http://r", "secret": "x", "allow_insecure_http": "true"}
    assert isinstance(get_bench_runner(), HttpBenchRunner)
    bench_env["runner"] = {"url": "https://r", "secret": "x"}
    assert isinstance(get_bench_runner(), HttpBenchRunner)


@pytest.mark.parametrize("mode", ["Runner ", "podman", "http"])
def test_invalid_mode_is_an_explicit_error_not_a_silent_default(bench_env, mode):
    bench_env["execution_mode"] = mode
    if mode.strip().lower() == "runner":
        assert get_bench_runner() is not None      # case/whitespace tolerant
    else:
        with pytest.raises(AppException, match="Invalid BENCH_EXECUTION_MODE"):
            get_bench_runner()


def test_default_and_explicit_docker_mode_keep_the_docker_path(bench_env):
    bench_env.pop("execution_mode")
    assert get_bench_runner() is None
    bench_env["execution_mode"] = "docker"
    assert get_bench_runner() is None
    plan = MagicMock(apps=["crm"], home_page="crm", default_roles=[])
    bench_env["container_name"] = "frappe-backend-1"
    p = CRMProvisioner(plan, bench_env)
    assert p.runner is None and p.container_name == "frappe-backend-1"
    with patch("subprocess.run", return_value=MagicMock(returncode=0, stdout="", stderr="")) as run:
        p._bench_new_site(SITE, "db", "admin-pass", "crm", "T")
    cmd = run.call_args[0][0]
    assert cmd[:4] == ["docker", "exec", "frappe-backend-1", "bench"] and "new-site" in cmd and "admin-pass" in cmd


def test_runner_mode_never_asks_docker_for_a_container(bench_env, no_docker):
    assert bench_runner.execution_mode() == "runner"
    from kairon.crm.services.docker_utils import resolve_container_name
    assert resolve_container_name({"container_name": None}) == ""


# ------------------------------------------------------------------ other call sites

def test_set_admin_password_goes_through_the_runner_with_the_password_as_a_secret(bench_env, no_docker):
    server = FakeRunnerServer()
    with patch("kairon.crm.services.bench_runner.get_bench_runner", return_value=server):
        BenchExecutor().set_admin_password(SITE, "new-admin-pass")
    call = server.calls[0]
    assert call["operation"] == "set_admin_password" and call["secrets"] == {"admin_password": "new-admin-pass"}
    assert "new-admin-pass" not in str(call["params"]) + call["key"]


def test_set_admin_password_failure_is_reported(bench_env, no_docker):
    with patch("kairon.crm.services.bench_runner.get_bench_runner", return_value=FakeRunnerServer(fail={"set_admin_password": "denied"})):
        with pytest.raises(AppException, match="denied"):
            BenchExecutor().set_admin_password(SITE, "x")


def test_docker_only_features_are_refused_clearly_in_runner_mode(bench_env, no_docker):
    server = FakeRunnerServer()
    plan = MagicMock(apps=["crm", "erpnext"], home_page="x", default_roles=[])
    with patch("kairon.crm.services.provisioners.base_provisioner.get_bench_runner", return_value=server):
        up = AppUpgradeProvisioner(plan, Utility.environment["crm"]["bench"])
    CRMClientDetails.objects(company_name="Acme Co").delete()
    CRMClientDetails(company_name="Acme Co", abbr="AC", default_currency="INR", country="India", bot="runner_bot", user="u",
                     site_name=SITE, onboarding_status="COMPLETED", tier=1).save()
    with pytest.raises(AppException, match="not supported in BENCH_EXECUTION_MODE=runner"):
        up.provision("Acme Co", "AC", "INR", "India", "pw", "runner_bot")
    with pytest.raises(AppException, match="not supported in BENCH_EXECUTION_MODE=runner"):
        BenchExecutor().create_crm_user("runner_bot", "a@b.co", "Sales User")


def test_erpnext_client_container_fallbacks_do_not_touch_docker_in_runner_mode(bench_env, no_docker):
    from kairon.crm.services.erpnext_client import ERPNextClient
    client = ERPNextClient("http://localhost:8080", SITE)
    client.session = MagicMock()
    client.session.post.return_value = MagicMock(status_code=200, json=lambda: {"message": {}})
    client.session.get.return_value = MagicMock(status_code=200, json=lambda: {"data": []})
    client.clear_cache()                      # container path is skipped, HTTP path used; no subprocess call (patched to fail)


# ------------------------------------------------------------------ HTTP client through a stateful fake server

def test_http_client_end_to_end_idempotency_replay_of_the_same_key_returns_the_same_job():
    state = {"jobs": {}, "n": 0}

    def fake(method, url, data=None, headers=None, timeout=None):
        import json as _json
        r = MagicMock()
        if method == "POST":
            body = _json.loads(data)
            job = state["jobs"].setdefault(body["idempotency_key"], f"job_{len(state['jobs'])}")
            state["n"] += 1
            r.status_code, r.json = 202, (lambda j=job: {"job_id": j})
        else:
            r.status_code, r.json = 200, (lambda: {"state": "succeeded", "result": {"exists": False}})
        return r

    client = HttpBenchRunner("https://runner.internal", "k", sleep=lambda s: None)
    with patch("requests.request", side_effect=fake):
        a = client.run("site_exists", SITE, idempotency_key="run-1:site_exists:x")
        b = client.run("site_exists", SITE, idempotency_key="run-1:site_exists:x")
    assert a.ok and b.ok and len(state["jobs"]) == 1
