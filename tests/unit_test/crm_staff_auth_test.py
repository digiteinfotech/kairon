"""Metering staff tokens on the CRM routes, and the plain enable/disable toggle. [real] FastAPI dependency chain."""
import os

os.environ["system_file"] = "./tests/testing_data/system.yaml"

import time
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi.testclient import TestClient
from mongoengine import connect, disconnect

from kairon.api.app.main import app
from kairon.crm import auth as crm_auth
from kairon.shared.account.data_objects import Bot
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.utils import Utility

SECRET = "metering-secret-for-tests-0123456789ab"
BOT = "staff_auth_bot"
client = TestClient(app)


def staff_token(sub="staff@kairon.com", secret=SECRET, aud="kairon-metering", typ="metering-staff", exp=600, alg="HS256", **extra):
    now = datetime.now(timezone.utc)
    claims = {"sub": sub, "type": typ, "aud": aud, "iat": now, "exp": now + timedelta(seconds=exp), **extra}
    return jwt.encode(claims, secret, algorithm=alg)


@pytest.fixture(autouse=True)
def setup():
    Utility.load_environment()
    connect(**Utility.mongoengine_connection(Utility.environment["database"]["url"]))
    crm = Utility.environment.setdefault("crm", {})
    saved = (crm.get("staff_auth"), crm.get("staff_allowlist"))
    crm["staff_auth"] = {"jwt_secret": SECRET}
    crm["staff_allowlist"] = "staff@kairon.com, @digite.com"
    BotSettings.objects(bot=BOT).delete()
    BotSettings(bot=BOT, user="owner@x.com", enable_crm=False).save()
    from unittest.mock import patch
    with patch("kairon.crm.auth.AccountProcessor.get_bot_and_validate_status", return_value={"account": 7}):
        yield
    crm["staff_auth"], crm["staff_allowlist"] = saved
    BotSettings.objects(bot=BOT).delete()
    disconnect()


def get(path, token=None):
    return client.get(f"/api/bot/{BOT}/crm/{path}", headers={"Authorization": f"Bearer {token}"} if token else {}).json()


def test_listed_staff_token_reads_and_toggles_crm_without_a_kairon_login():
    token = staff_token()
    assert get("enabled", token)["data"] == {"enabled": False}
    on = client.put(f"/api/bot/{BOT}/crm/enabled", json={"enabled": True}, headers={"Authorization": f"Bearer {token}"}).json()
    assert on["success"] and on["data"] == {"enabled": True}
    assert BotSettings.objects(bot=BOT).first().enable_crm is True
    assert get("enabled", token)["data"] == {"enabled": True}
    off = client.put(f"/api/bot/{BOT}/crm/enabled", json={"enabled": False}, headers={"Authorization": f"Bearer {token}"}).json()
    assert off["data"] == {"enabled": False} and BotSettings.objects(bot=BOT).first().enable_crm is False


def test_domain_entries_in_the_allowlist_match():
    assert get("enabled", staff_token(sub="Anyone@Digite.com"))["success"] is True


@pytest.mark.parametrize("kwargs", [
    {"sub": "mallory@evil.com"},                    # valid token, not listed
    {"sub": "x@digite.com.evil.com"},               # suffix trick
    {"secret": "some-other-secret-0123456789abcdef"},
    {"aud": "someone-else"},
    {"typ": "kairon-user"},
    {"exp": -10},                                   # expired
])
def test_invalid_or_unlisted_staff_tokens_get_no_access(kwargs):
    body = get("enabled", staff_token(**kwargs))
    assert body["success"] is False and body["error_code"] in (401, 403)
    assert BotSettings.objects(bot=BOT).first().enable_crm is False


def test_alg_none_and_missing_claims_are_rejected():
    forged = jwt.encode({"sub": "staff@kairon.com", "type": "metering-staff", "aud": "kairon-metering"}, key="", algorithm="none")
    assert get("enabled", forged)["success"] is False
    no_exp = jwt.encode({"sub": "staff@kairon.com", "type": "metering-staff", "aud": "kairon-metering",
                         "iat": int(time.time())}, SECRET, algorithm="HS256")
    assert get("enabled", no_exp)["success"] is False


def test_empty_allowlist_rejects_every_staff_token_fail_closed():
    Utility.environment["crm"]["staff_allowlist"] = None
    body = get("enabled", staff_token())
    assert body["success"] is False and "not enabled" in body["message"]


def test_staff_verification_is_off_when_no_secret_is_configured():
    Utility.environment["crm"]["staff_auth"] = {"jwt_secret": None}
    assert crm_auth.verify_staff_token(staff_token()) is None
    assert get("enabled", staff_token())["success"] is False


def test_no_token_and_garbage_token_are_unauthenticated():
    assert get("enabled")["error_code"] == 401
    assert get("enabled", "not.a.jwt")["success"] is False


def test_staff_token_does_not_open_non_crm_routes():
    r = client.get(f"/api/bot/{BOT}/settings", headers={"Authorization": f"Bearer {staff_token()}"}).json()
    assert r["success"] is False                     # general bot routes still require a Kairon login


def test_toggle_requires_existing_settings():
    BotSettings.objects(bot=BOT).delete()
    r = client.put(f"/api/bot/{BOT}/crm/enabled", json={"enabled": True}, headers={"Authorization": f"Bearer {staff_token()}"}).json()
    assert r["success"] is False and "not found" in r["message"].lower()
