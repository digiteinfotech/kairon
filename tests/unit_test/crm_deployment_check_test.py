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
