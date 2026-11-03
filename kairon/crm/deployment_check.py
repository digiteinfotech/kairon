"""
Read-only CRM deployment readiness check. Run it in the environment being deployed
(`python -m kairon crm_lead_analysis check`, exit code 1 when a required check fails). It never prints or returns a secret,
never calls the LLM provider and never changes data.
"""
from typing import Dict, List, Text

from kairon.crm.analytics.qualifier import ANALYTICS_LLM_TYPE, DEFAULT_MODEL
from kairon.crm.services.bench_runner import execution_mode, get_bench_runner
from kairon.exceptions import AppException
from kairon.shared.utils import Utility

MIN_SHARED_SECRET_LENGTH = 32     # same floor Metering enforces for METERING_JWT_SECRET


def _check(name: Text, ok: bool, detail: Text, required: bool = True) -> Dict:
    return {"name": name, "ok": bool(ok), "required": required, "detail": detail}


def run_checks() -> List[Dict]:
    env, checks = Utility.environment, []

    # 2. Platform LLM: the Analytics Pipeline's own secret and an enabled model. The key is never read out.
    from kairon.shared.admin.data_objects import LLMSecret
    model = (env.get("crm", {}).get("lead_analysis") or {}).get("model") or DEFAULT_MODEL
    try:
        secret = LLMSecret.objects(llm_type=ANALYTICS_LLM_TYPE).first()
        models = list(secret.models or []) if secret else []
        checks.append(_check("platform_llm_secret", bool(secret), f"LLMSecret '{ANALYTICS_LLM_TYPE}' "
                             f"{'present' if secret else 'MISSING in this database'}"))
        checks.append(_check("llm_model_enabled", model in models, f"model '{model}' "
                             f"{'is' if model in models else 'is NOT'} in the platform secret's models ({len(models)} listed)"))
    except Exception as e:
        checks.append(_check("platform_llm_secret", False, f"could not read the database: {type(e).__name__}"))

    llm_url = str(env.get("llm", {}).get("url") or "")
    loopback = "localhost" in llm_url or "127.0.0.1" in llm_url
    # Conversation text is sent to this server, so it must be remote-capable (not loopback) and encrypted in transit.
    checks.append(_check("llm_server_url", bool(llm_url) and not loopback and llm_url.lower().startswith("https://"),
                         "LLM server URL is " + ("unset" if not llm_url else "a loopback address (not valid in ECS)" if loopback
                                                 else "set" if llm_url.lower().startswith("https://")
                                                 else "not https:// (conversation text would travel unencrypted)"), required=False))

    # 2a. Tenant hostnames must be unique, and the index that enforces it should exist.
    try:
        from kairon.crm.models import CRMClientDetails
        duplicates = CRMClientDetails.duplicate_site_names()
        checks.append(_check("site_name_unique", not duplicates,
                             f"{len(duplicates)} site name(s) are used by more than one tenant record; resolve them before "
                             "`python -m kairon crm_lead_analysis ensure-indexes`" if duplicates else "no duplicate tenant site names"))
        indexed = CRMClientDetails.has_site_name_index()
        checks.append(_check("site_name_index", indexed, "unique site_name index " + ("present" if indexed else
                             "missing: run `python -m kairon crm_lead_analysis ensure-indexes`"), required=False))
    except Exception as e:
        checks.append(_check("site_name_unique", False, f"could not read the database: {type(e).__name__}"))

    # 2b. The scheduled platform job needs a task definition under any non-standalone executor (Lambda/ECS look it up by name).
    executor = str((env.get("events", {}).get("executor") or {}).get("type") or "standalone")
    task = (env.get("events", {}).get("task_definition") or {}).get("crm_lead_analysis")
    checks.append(_check(
        "crm_lead_analysis_task_definition", executor == "standalone" or bool(task),
        f"executor '{executor}': " + ("not needed" if executor == "standalone" else
                                      "CRM_LEAD_ANALYSIS_TASK_DEFINITION is set" if task else
                                      "CRM_LEAD_ANALYSIS_TASK_DEFINITION is NOT set; the scheduled job would fail to start")))

    # 3. Bench execution mode and runner configuration.
    try:
        mode = execution_mode()
        get_bench_runner()
        checks.append(_check("bench_execution", True, f"mode '{mode}' configured"
                             + ("" if mode == "runner" else " (docker: not usable on ECS Fargate)"), required=True))
        checks.append(_check("bench_runner_for_ecs", mode == "runner",
                             "docker mode needs the Docker socket; ECS Fargate requires runner mode and an infrastructure-owned runner",
                             required=False))
    except AppException as e:
        checks.append(_check("bench_execution", False, str(e)))

    # 4. Invitation mail, tracker and event server wiring.
    checks.append(_check("email_enabled", bool(Utility.email_conf.get("email", {}).get("enable")),
                         "EMAIL_ENABLE must be true for administrator invitations (otherwise they stay FAILED)", required=False))
    checks.append(_check("tracker_url", bool((env.get("tracker") or {}).get("url")), "TRACKER_URL (conversation store)"))
    checks.append(_check("event_server_url", bool((env.get("events") or {}).get("server_url")), "EVENT_SERVER_ENDPOINT"))
    checks.append(_check("tenant_url_scheme", str(((env.get("crm") or {}).get("bench") or {}).get("tenant_url_scheme") or "http") == "https",
                         "BENCH_TENANT_URL_SCHEME should be https (invitation links are refused over http)", required=False))

    # 4b. Shared secrets between Kairon and Metering. Only lengths and names are inspected; values are never reported.
    crm = env.get("crm") or {}
    staff_secret = str((crm.get("staff_auth") or {}).get("jwt_secret") or "")
    if staff_secret:
        checks.append(_check("staff_jwt_secret_strength", len(staff_secret) >= MIN_SHARED_SECRET_LENGTH,
                             f"CRM_STAFF_JWT_SECRET must be at least {MIN_SHARED_SECRET_LENGTH} characters (it signs staff tokens)",
                             required=False))
        checks.append(_check("staff_allowlist", bool(str(crm.get("staff_allowlist") or "").strip()),
                             "staff tokens are enabled but CRM_STAFF_ALLOWLIST is empty, so every staff token is rejected",
                             required=False))
    metering = crm.get("metering") or {}
    if metering.get("url") or metering.get("event_secret"):
        checks.append(_check("metering_event_secret", len(str(metering.get("event_secret") or "")) >= MIN_SHARED_SECRET_LENGTH,
                             f"CRM_METERING_EVENT_SECRET must be set and at least {MIN_SHARED_SECRET_LENGTH} characters "
                             "(it signs every event sent to Metering)", required=False))
        checks.append(_check("metering_url_https", str(metering.get("url") or "").lower().startswith("https://"),
                             "CRM_METERING_URL should be https:// outside local development", required=False))

    # 5. The platform job (lead analysis, invitation retries and reconciliation) must be registered on the event server (read from the shared job store).
    try:
        from pymongo import MongoClient
        sched = env["events"]["scheduler"]["collection"]
        client = MongoClient(env["database"]["url"], serverSelectionTimeoutMS=3000)
        job = client[env["events"]["queue"]["name"]][sched].find_one({"_id": "crm_lead_analysis"})
        checks.append(_check("platform_job_registered", job is not None,
                             "crm_lead_analysis " + ("registered" if job else "NOT registered: run `python -m kairon crm_lead_analysis schedule`")))
    except Exception as e:
        checks.append(_check("platform_job_registered", False, f"could not read the job store: {type(e).__name__}"))
    return checks


def summarize(checks: List[Dict]) -> Dict:
    return {"ready": all(c["ok"] for c in checks if c["required"]), "checks": checks}
