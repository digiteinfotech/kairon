import os

os.environ["system_file"] = "./tests/testing_data/system.yaml"

import subprocess
import sys
import uuid
from unittest import mock

import pytest
from mongoengine import connect

from kairon.shared.utils import Utility
Utility.load_system_metadata()

from kairon.crm import lead_dispatch
from kairon.crm.models import CRMClientDetails, CRMOnboardingStatus
from kairon.exceptions import AppException

SECRET = "dispatch_test_secret_value"


def _save_tenant(bot, secret=SECRET, site_name="tenant-a.localhost"):
    CRMClientDetails(
        bot=bot, company_name=f"Dispatch Co {bot}", abbr="DC", default_currency="USD", country="US", user="tester",
        onboarding_status=CRMOnboardingStatus.COMPLETED.value, site_name=site_name,
        lead_webhook_secret=Utility.encrypt_message(secret) if secret else None,
    ).save()


class TestLeadDispatch:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    def test_build_target_url_without_port(self):
        url = lead_dispatch.build_target_url("http://bench.internal", "tenant-a.localhost")
        assert url == "http://tenant-a.localhost/api/method/kairon_connector.api.v1.webhook.receive_event"

    def test_build_target_url_keeps_port_and_scheme(self):
        url = lead_dispatch.build_target_url("https://bench.internal:8443", "tenant-a.localhost")
        assert url == "https://tenant-a.localhost:8443/api/method/kairon_connector.api.v1.webhook.receive_event"

    def test_resolve_lead_target_uses_configured_base_and_the_bots_own_secret(self):
        bot, other = f"bot_{uuid.uuid4().hex[:8]}", f"bot_{uuid.uuid4().hex[:8]}"
        _save_tenant(bot, secret=SECRET, site_name="tenant-a.localhost")
        _save_tenant(other, secret="another_tenants_secret", site_name="tenant-b.localhost")
        env = {"crm": {"bench": {"base_url": "http://bench.internal:8080"}}}
        with mock.patch.dict(Utility.environment, env, clear=False):
            url, secret = lead_dispatch.resolve_lead_target(bot, "tenant-a.localhost")
        assert url.startswith("http://tenant-a.localhost:8080/")
        assert secret == SECRET and secret != "another_tenants_secret"

    def test_missing_secret_raises_without_leaking_anything(self):
        bot = f"bot_{uuid.uuid4().hex[:8]}"
        _save_tenant(bot, secret=None)
        with pytest.raises(AppException) as exc:
            lead_dispatch.get_lead_webhook_secret(bot)
        assert "not configured" in str(exc.value)

    def test_unknown_bot_raises(self):
        with pytest.raises(AppException):
            lead_dispatch.get_lead_webhook_secret(f"bot_{uuid.uuid4().hex[:8]}")


class TestRuntimeImportBoundary:
    """The action server imports the lead action for every conversation. It must not drag in the provisioning stack
    (CRM processor/routes, ERPNext client, Docker/Bench executor, provisioners)."""

    FORBIDDEN = ("kairon.crm.processor", "kairon.crm.routes", "kairon.crm.services")

    @pytest.mark.parametrize("module", [
        "kairon.actions.definitions.erpnext_crm_lead",
        "kairon.crm.lead_dispatch",
    ])
    def test_runtime_modules_do_not_load_provisioning_stack(self, module):
        code = (
            "import os, sys; os.environ['system_file'] = './tests/testing_data/system.yaml'\n"
            f"import {module}\n"
            f"bad = sorted(m for m in sys.modules if m.startswith({self.FORBIDDEN!r}))\n"
            "print('LOADED:' + ','.join(bad))\n"
        )
        out = subprocess.run([sys.executable, "-W", "ignore", "-c", code], capture_output=True, text=True, timeout=120)
        assert out.returncode == 0, out.stderr[-500:]
        assert "LOADED:" in out.stdout
        assert out.stdout.strip().splitlines()[-1] == "LOADED:", out.stdout[-300:]

    @pytest.mark.parametrize("path", [
        "kairon/actions/definitions/erpnext_crm_lead.py",
        "kairon/actions/definitions/factory.py",
        "kairon/crm/lead_dispatch.py",
    ])
    def test_static_imports_of_runtime_files_avoid_provisioning_stack(self, path):
        """Cheap static guard that also covers the action factory (whose full import loads every action)."""
        import ast
        tree = ast.parse(open(path).read())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
            elif isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
        bad = [m for m in imported if m.startswith(self.FORBIDDEN)]
        assert not bad, bad
