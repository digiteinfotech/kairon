"""Deployment readiness check: configuration validation, with no secret ever reported."""
import os

os.environ["system_file"] = "./tests/testing_data/system.yaml"

import pytest
from mongoengine import connect, disconnect

from kairon.crm.deployment_check import run_checks, summarize
from kairon.shared.admin.data_objects import LLMSecret
from kairon.shared.utils import Utility


@pytest.fixture(autouse=True)
def env():
    Utility.load_environment()
    Utility.load_email_configuration()
    connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
    LLMSecret.objects(llm_type="openrouter", user="deploycheck").delete()
    bench = Utility.environment.setdefault("crm", {}).setdefault("bench", {})
    sched = Utility.environment["events"]["scheduler"]
    saved = (dict(bench), sched.get("analytics_min_trigger_interval"), dict(Utility.environment["crm"].get("lead_analysis") or {}))
    yield
    bench.clear(); bench.update(saved[0]); sched["analytics_min_trigger_interval"] = saved[1]
    Utility.environment["crm"]["lead_analysis"] = saved[2]
    LLMSecret.objects(llm_type="openrouter", user="deploycheck").delete()
    disconnect()


def by_name(checks):
    return {c["name"]: c for c in checks}


def test_interval_not_configured_is_reported_with_the_remedy():
    Utility.environment["events"]["scheduler"]["analytics_min_trigger_interval"] = None
    c = by_name(run_checks())["analytics_min_trigger_interval"]
    assert not c["ok"] and "ANALYTICS_MIN_TRIGGER_INTERVAL=300" in c["detail"]


@pytest.mark.parametrize("value,ok", [(300, True), (60, True), ("abc", False), (0, False), (86340, False)])
def test_interval_values(value, ok):
    Utility.environment["events"]["scheduler"]["analytics_min_trigger_interval"] = value
    assert by_name(run_checks())["analytics_min_trigger_interval"]["ok"] is ok


def test_platform_llm_secret_and_model_are_checked_without_exposing_the_key():
    Utility.environment["crm"]["lead_analysis"] = {"model": "openai/gpt-4o-mini"}
    LLMSecret.objects(llm_type="openrouter").delete()
    checks = by_name(run_checks())
    assert not checks["platform_llm_secret"]["ok"] and not checks["llm_model_enabled"]["ok"]
    LLMSecret(llm_type="openrouter", api_key=Utility.encrypt_message("SUPER-SECRET-KEY"), models=["other/model"], user="deploycheck").save()
    checks = by_name(run_checks())
    assert checks["platform_llm_secret"]["ok"] and not checks["llm_model_enabled"]["ok"]
    LLMSecret.objects(llm_type="openrouter", user="deploycheck").update(set__models=["openai/gpt-4o-mini"])
    report = run_checks()
    assert by_name(report)["llm_model_enabled"]["ok"]
    assert "SUPER-SECRET-KEY" not in str(report) and "gAAAA" not in str(report)


def test_bench_configuration_problems_are_reported_not_raised():
    bench = Utility.environment["crm"]["bench"]
    bench["execution_mode"] = "runner"; bench["runner"] = {"url": "", "secret": ""}
    c = by_name(run_checks())["bench_execution"]
    assert not c["ok"] and "BENCH_RUNNER_URL" in c["detail"]
    bench["execution_mode"] = "podman"
    assert not by_name(run_checks())["bench_execution"]["ok"]
    bench["execution_mode"] = "docker"
    checks = by_name(run_checks())
    assert checks["bench_execution"]["ok"] and not checks["bench_runner_for_ecs"]["ok"]      # optional: advises runner for ECS
    bench["execution_mode"] = "runner"; bench["runner"] = {"url": "https://r.internal", "secret": "x"}
    checks = by_name(run_checks())
    assert checks["bench_execution"]["ok"] and checks["bench_runner_for_ecs"]["ok"]


def test_ready_depends_only_on_required_checks():
    report = summarize([{"name": "a", "ok": True, "required": True, "detail": ""},
                        {"name": "b", "ok": False, "required": False, "detail": ""}])
    assert report["ready"] is True
    assert summarize([{"name": "a", "ok": False, "required": True, "detail": ""}])["ready"] is False


def test_shared_secret_checks_report_names_never_values():
    crm = Utility.environment.setdefault("crm", {})
    saved = (crm.get("staff_auth"), crm.get("staff_allowlist"), crm.get("metering"))
    try:
        crm["staff_auth"] = {"jwt_secret": "short-staff-secret"}
        crm["staff_allowlist"] = None
        crm["metering"] = {"url": "http://metering.internal", "event_secret": "short-event-secret"}
        checks = by_name(run_checks())
        for name in ("staff_jwt_secret_strength", "staff_allowlist", "metering_event_secret", "metering_url_https"):
            assert not checks[name]["ok"] and checks[name]["required"] is False
        assert "short-staff-secret" not in str(checks) and "short-event-secret" not in str(checks)

        crm["staff_auth"] = {"jwt_secret": "s" * 40}
        crm["staff_allowlist"] = "@digite.com"
        crm["metering"] = {"url": "https://metering.example.com", "event_secret": "e" * 40}
        checks = by_name(run_checks())
        assert all(checks[n]["ok"] for n in ("staff_jwt_secret_strength", "staff_allowlist",
                                             "metering_event_secret", "metering_url_https"))
    finally:
        crm["staff_auth"], crm["staff_allowlist"], crm["metering"] = saved


def test_shared_secret_checks_are_skipped_when_the_features_are_not_configured():
    crm = Utility.environment.setdefault("crm", {})
    saved = (crm.get("staff_auth"), crm.get("metering"))
    try:
        crm["staff_auth"], crm["metering"] = {"jwt_secret": None}, {"url": None, "event_secret": None}
        names = by_name(run_checks())
        assert "staff_jwt_secret_strength" not in names and "metering_event_secret" not in names
    finally:
        crm["staff_auth"], crm["metering"] = saved


@pytest.mark.parametrize("url,ok", [("https://llm.example.com", True), ("http://llm.example.com", False),
                                   ("http://localhost", False), ("https://127.0.0.1:8443", False), ("", False)])
def test_llm_server_url_must_be_remote_and_https(url, ok):
    llm = Utility.environment.setdefault("llm", {})
    saved = llm.get("url")
    try:
        llm["url"] = url
        check = by_name(run_checks())["llm_server_url"]
        assert check["ok"] is ok and check["required"] is False
    finally:
        llm["url"] = saved
