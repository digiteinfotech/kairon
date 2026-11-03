from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_delete_intent():
    client.post(
        f"/api/bot/{pytest.bot}/intents",
        json={"data": "happier"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = client.delete(
        f"/api/bot/{pytest.bot}/intents/happier",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent deleted!"
    assert actual["success"]


def test_api_login_with_account_not_verified():
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@10"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False

    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Please verify your mail"
    value = list(
        AuditLogData.objects(user="integration@demo.ai", action='activity', entity='invalid_login').order_by(
            "-timestamp")
    )[0]
    assert value["entity"] == "invalid_login"
    assert value["timestamp"]
    assert value["data"] == {'message': ['Please verify your mail'], 'username': 'integration@demo.ai'}


def test_account_registration_with_confirmation(monkeypatch):
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integ1@gmail.com",
            "first_name": "Dem",
            "last_name": "User22",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration33",
            "bot": "integration33",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert (
            actual["message"]
            == "Account Registered! A confirmation link has been sent to your mail"
    )
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None

    response = client.post(
        "/api/account/email/confirmation",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20"
        },
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False

    assert actual["message"] == "Account Verified!"
    assert actual["data"] is None
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@10"},
    )
    actual = response.json()
    pytest.add_member_token = actual["data"]["access_token"]
    pytest.add_member_token_type = actual["data"]["token_type"]

    response = client.post(
        "/api/account/bot",
        headers={"Authorization": pytest.add_member_token_type + " " + pytest.add_member_token,
                 'Content-Type': 'application/json'},
        json={"name": "Hi-Hello", "from_template": "Hi-Hello"},
    ).json()
    assert response['message'] == "Bot created"
    assert response['data']['bot_id']

    response = client.get(
        "/api/account/bot",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    pytest.add_member_bot = response["data"]["account_owned"][0]["_id"]


def test_account_registration_with_confirmation_enabled_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.post(
        "/api/account/email/confirmation",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20"
        },
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False

    assert actual["message"] == "This feature is disabled"
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_invalid_token_for_confirmation():
    response = client.post(
        "/api/account/email/confirmation",
        json={"data": "hello"},
    )
    actual = response.json()

    assert actual["message"] == "Invalid token"
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_member(monkeypatch):
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)

    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integration@demo.ai", "role": "tester"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "An invitation has been sent to the user"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integration2@demo.ai", "role": "designer"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "An invitation has been sent to the user"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integrationtest@demo.ai", "role": "designer"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "An invitation has been sent to the user"
    assert response["error_code"] == 0
    assert response["success"]


@responses.activate
def test_add_member_invalid_email():
    api_key = "test"
    email = "integration@demo.ai"
    with patch.dict(
            Utility.environment,
            {"verify": {"email": {"type": "quickemail", "key": api_key, "enable": True}}},
    ):
        responses.add(
            responses.GET,
            "http://api.quickemailverification.com/v1/verify?"
            + urlencode({"apikey": api_key, "email": email}),
            json={
                "result": "valid",
                "reason": "rejected_email",
                "disposable": "true",
                "accept_all": "false",
                "role": "false",
                "free": "false",
                "email": email,
                "user": "test",
                "domain": "quickemailverification.com",
                "mx_record": "us2.mx1.mailhostbox.com",
                "mx_domain": "mailhostbox.com",
                "safe_to_send": "false",
                "did_you_mean": "",
                "success": "true",
                "message": None,
            },
        )

        response = client.post(
            f"/api/user/{pytest.add_member_bot}/member",
            json={"email": email, "role": "tester"},
            headers={
                "Authorization": pytest.add_member_token_type
                                 + " "
                                 + pytest.add_member_token
            },
        ).json()
        assert response["message"] == [
            {
                "loc": ["body", "email"],
                "msg": "Invalid or disposable Email!",
                "type": "value_error",
            }
        ]
        assert response["error_code"] == 422
        assert not response["success"]


def test_add_member_as_owner(monkeypatch):
    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integration@demo.ai", "role": "owner"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == [
        {
            "loc": ["body", "role"],
            "msg": "There can be only 1 owner per bot",
            "type": "value_error",
        }
    ]
    assert response["error_code"] == 422
    assert not response["success"]


def test_list_bot_invites():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@10"},
    ).json()

    response = client.get(
        "/api/user/invites/active",
        headers={
            "Authorization": response["data"]["token_type"]
                             + " "
                             + response["data"]["access_token"]
        },
    ).json()
    assert (
            response["data"]["active_invites"][0]["accessor_email"] == "integration@demo.ai"
    )
    assert response["data"]["active_invites"][0]["role"] == "tester"
    assert response["data"]["active_invites"][0]["bot_name"] == "Hi-Hello"
    assert response["error_code"] == 0
    assert response["success"]


def test_login_limit_exceeded():
    response_one = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@3010"},
    ).json()
    response_two = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@3010"},
    ).json()
    response_three = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@3010"},
    ).json()
    response = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@3010"},
    ).json()

    assert not response['success']
    assert response['message'].__contains__("Account frozen due to too many unsuccessful login attempts.")
    assert response['data'] is None
    assert response['error_code'] == 422


def test_search_users(monkeypatch):
    def __mock_list_bot_invites(*args, **kwargs):
        for item in ["integration@demo.ai", "integration2@demo.com"]:
            yield item

    monkeypatch.setattr(AccountProcessor, "search_user", __mock_list_bot_invites)

    response = client.post(
        f"/api/user/search",
        json={"data": "inte"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["data"]["matching_users"] == [
        "integration@demo.ai",
        "integration2@demo.com",
    ]
    assert response["error_code"] == 0
    assert response["success"]


def test_transfer_ownership_to_user_not_a_member(monkeypatch):
    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
    response = client.put(
        f"/api/user/{pytest.add_member_bot}/owner/change",
        json={"data": "integration@demo.ai"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User is yet to accept the invite"
    assert response["error_code"] == 422
    assert not response["success"]


def test_accept_bot_invite(monkeypatch):
    def __mock_verify_token(*args, **kwargs):
        return {"mail_id": "integration@demo.ai"}

    monkeypatch.setattr(Utility, "verify_token", __mock_verify_token)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    monkeypatch.setattr(AccountProcessor, "get_user_details", mock_sync_noop)
    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
    response = client.post(
        f"/api/user/{pytest.add_member_bot}/invite/accept",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoidXNlckBrYWlyb24uY"
        },
    ).json()
    assert response["message"] == "Invitation accepted"
    assert response["error_code"] == 0
    assert response["success"]


def test_accept_bot_invite_logged_in_user_with_email_enabled(monkeypatch):
    response = client.post(
        "/api/auth/login",
        data={"username": "integrationtest@demo.ai", "password": "Welcome@10"},
    )
    actual = response.json()
    assert all(
        [
            True if actual["data"][key] else False
            for key in ["access_token", "token_type"]
        ]
    )
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        "/api/user/invites/active",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    ).json()
    assert (
            response["data"]["active_invites"][0]["accessor_email"]
            == "integrationtest@demo.ai"
    )
    assert response["data"]["active_invites"][0]["role"] == "designer"
    assert response["data"]["active_invites"][0]["bot_name"] == "Hi-Hello"

    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    monkeypatch.setattr(AccountProcessor, "check_email_confirmation", mock_sync_noop)
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member/invite/accept",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    ).json()
    Utility.email_conf["email"]["enable"] = False
    assert response["message"] == "Invitation accepted"
    assert response["error_code"] == 0
    assert response["success"]


def test_accept_bot_invite_logged_in_user():
    response = client.post(
        "/api/auth/login",
        data={"username": "integration2@demo.ai", "password": "Welcome@10"},
    )
    actual = response.json()
    assert all(
        [
            True if actual["data"][key] else False
            for key in ["access_token", "token_type"]
        ]
    )
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        "/api/user/invites/active",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    ).json()
    assert (
            response["data"]["active_invites"][0]["accessor_email"]
            == "integration2@demo.ai"
    )
    assert response["data"]["active_invites"][0]["role"] == "designer"
    assert response["data"]["active_invites"][0]["bot_name"] == "Hi-Hello"

    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member/invite/accept",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    ).json()
    assert response["message"] == "Invitation accepted"
    assert response["error_code"] == 0
    assert response["success"]


def test_list_bot_invites_none():
    response = client.get(
        f"/api/user/invites/active",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["data"]["active_invites"] == []
    assert response["error_code"] == 0
    assert response["success"]


def test_add_member_email_disabled():
    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integration_email_false@demo.ai", "role": "designer"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User added"
    assert response["error_code"] == 0
    assert response["success"]


def test_list_members():
    response = client.get(
        f"/api/user/{pytest.add_member_bot}/member",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["error_code"] == 0
    assert response["success"]
    assert response["data"][0]["accessor_email"] == "integ1@gmail.com"
    assert response["data"][0]["role"] == "owner"
    assert response["data"][1]["status"]
    assert response["data"][1]["accessor_email"] == "integration@demo.ai"
    assert response["data"][1]["role"] == "tester"
    assert response["data"][1]["status"]
    assert response["data"][2]["accessor_email"] == "integration2@demo.ai"
    assert response["data"][2]["role"] == "designer"
    assert response["data"][2]["status"]
    assert response["data"][3]["accessor_email"] == "integrationtest@demo.ai"
    assert response["data"][3]["role"] == "designer"
    assert response["data"][3]["status"]
    assert response["data"][4]["accessor_email"] == "integration_email_false@demo.ai"
    assert response["data"][4]["role"] == "designer"
    assert response["data"][4]["status"]


def test_transfer_ownership(monkeypatch):
    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    response = client.put(
        f"/api/user/{pytest.add_member_bot}/owner/change",
        json={"data": "integration@demo.ai"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "Ownership transferred"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.get(
        f"/api/user/{pytest.add_member_bot}/member",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["error_code"] == 0
    assert response["success"]
    assert response["data"][0]["accessor_email"] == "integ1@gmail.com"
    assert response["data"][0]["role"] == "admin"
    assert response["data"][1]["status"]
    assert response["data"][1]["accessor_email"] == "integration@demo.ai"
    assert response["data"][1]["role"] == "owner"
    assert response["data"][1]["status"]
    assert response["data"][2]["accessor_email"] == "integration2@demo.ai"
    assert response["data"][2]["role"] == "designer"
    assert response["data"][2]["status"]
    assert response["data"][3]["accessor_email"] == "integrationtest@demo.ai"
    assert response["data"][3]["role"] == "designer"
    assert response["data"][3]["status"]
    assert response["data"][4]["accessor_email"] == "integration_email_false@demo.ai"
    assert response["data"][4]["role"] == "designer"
    assert response["data"][4]["status"]


def test_list_members_2():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    bot = response["data"]["account_owned"][1]["_id"]
    response = client.get(
        f"/api/user/{bot}/member",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["error_code"] == 422
    assert not response["success"]
    assert not response["data"]
    assert response["message"] == "Access to bot is denied"


def test_update_member_role_not_exists(monkeypatch):
    response = client.post(
        "/api/account/registration",
        json={
            "email": "user@kairon.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "user@kairon.ai",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    response = client.put(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "user@kairon.ai", "role": "admin", "status": "inactive"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User not yet invited to collaborate"
    assert response["error_code"] == 422
    assert not response["success"]


def test_update_member_role(monkeypatch):
    response = client.put(
        f"/api/user/{pytest.add_member_bot}/member",
        json={
            "email": "integration_email_false@demo.ai",
            "role": "admin",
            "status": "inactive",
        },
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User does not exist!"
    assert response["error_code"] == 422
    assert not response["success"]

    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration_email_false@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration_email_false@demo.ai",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    response = client.put(
        f"/api/user/{pytest.add_member_bot}/member",
        json={
            "email": "integration_email_false@demo.ai",
            "role": "admin",
            "status": "inactive",
        },
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User access updated"
    assert response["error_code"] == 0
    assert response["success"]


def test_delete_member():
    response = client.delete(
        f"/api/user/{pytest.add_member_bot}/member/integration_email_false@demo.ai",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User removed"
    assert response["error_code"] == 0
    assert response["success"]


def test_add_deleted_member_and_updated_role():
    response = client.post(
        f"/api/user/{pytest.add_member_bot}/member",
        json={"email": "integration_email_false@demo.ai", "role": "designer"},
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User added"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.put(
        f"/api/user/{pytest.add_member_bot}/member",
        json={
            "email": "integration_email_false@demo.ai",
            "role": "admin",
            "status": "inactive",
        },
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User access updated"
    assert response["error_code"] == 0
    assert response["success"]


def test_remove_self():
    response = client.delete(
        f"/api/user/{pytest.add_member_bot}/member/integ1@gmail.com",
        headers={
            "Authorization": pytest.add_member_token_type
                             + " "
                             + pytest.add_member_token
        },
    ).json()
    assert response["message"] == "User cannot remove himself"
    assert response["error_code"] == 422
    assert not response["success"]


def test_add_intents_no_bot():
    response = client.post(
        "/api/bot/ /intents",
        json={"data": "greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Bot is required"


def test_add_intents_not_authorised():
    response = client.post(
        "/api/bot/5ea8127db7c285f4055129a4/intents",
        json={"data": "greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Access to bot is denied"


def test_add_intents_inactive_bot(monkeypatch):
    def _mock_bot(*args, **kwargs):
        return {"status": False}

    async def _mock_user(*args, **kwargs):
        return User(
            email="test",
            first_name="test",
            last_name="test",
            account=2,
            status=True,
            is_integration_user=False,
        )

    def _mock_role(*args, **kwargs):
        return {"role": "admin"}

    monkeypatch.setattr(AccountProcessor, "get_bot", _mock_bot)
    monkeypatch.setattr(Authentication, "get_current_user", _mock_user)
    monkeypatch.setattr(AccountProcessor, "fetch_role_for_user", _mock_role)

    response = client.post(
        "/api/bot/5ea8127db7c285f4055129a4/intents",
        json={"data": "greet"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Inactive Bot Please contact system admin!"


def test_add_intents_invalid_auth_token():
    token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJuYW1lIjoiSm9obiBEb2UiLCJpYXQiOjE1MTYyMzkwMjJ9.hqWGSaFpvbrXkOWc6lrnffhNWR19W_S1YKFBx2arWBk"
    response = client.post(
        "/api/bot/ /intents",
        json={"data": "greet"},
        headers={"Authorization": token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["message"] == "Could not validate credentials"


def test_add_intents_invalid_auth_token_2():
    token = "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
    response = client.post(
        "/api/bot/ /intents",
        json={"data": "greet"},
        headers={"Authorization": token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["message"] == "Could not validate credentials"


def test_add_intents_to_different_bot():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    pytest.bot_2 = response["data"]["account_owned"][1]["_id"]

    response = client.post(
        f"/api/bot/{pytest.bot_2}/intents",
        json={"data": "greeting"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"


def test_add_training_examples_to_different_bot():
    response = client.post(
        f"/api/bot/{pytest.bot_2}/training_examples/greet",
        json={"data": ["Heya"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    response = client.get(
        f"/api/bot/{pytest.bot_2}/training_examples/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 10


def test_add_response_different_bot():
    response = client.post(
        f"/api/bot/{pytest.bot_2}/response/utter_greet",
        json={"data": "Hi! How are you?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"
    response = client.get(
        f"/api/bot/{pytest.bot_2}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 3


def test_add_story_to_different_bot():
    response = client.post(
        f"/api/bot/{pytest.bot_2}/stories",
        json={
            "name": "greet user",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greeting", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


@patch('kairon.api.app.routers.bot.bot.MailReadEvent.__init__', return_value=None)
@patch('kairon.api.app.routers.bot.bot.MailReadEvent.validate')
@patch('kairon.api.app.routers.bot.bot.MailReadEvent.enqueue')
def test_trigger_mail_channel_read(mock_enque, mock_validate, mock_init):
    response = client.get(
        f"/api/bot/{pytest.bot}/mail_channel/read_mailbox",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    mock_validate.assert_called_once()
    mock_enque.assert_called_once()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "mail channel read triggered"



@responses.activate
def test_train_on_different_bot(monkeypatch):
    def _mock_training_limit(*arge, **kwargs):
        return False

    monkeypatch.setattr(
        ModelProcessor, "is_daily_training_limit_exceeded", _mock_training_limit
    )

    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_training}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    response = client.post(
        f"/api/bot/{pytest.bot_2}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."
    complete_end_to_end_event_execution(
        pytest.bot_2, "integration@demo.ai", EventClass.model_training
    )


def test_train_insufficient_data(monkeypatch):
    def _mock_training_limit(*arge, **kwargs):
        return False

    monkeypatch.setattr(
        ModelProcessor, "is_daily_training_limit_exceeded", _mock_training_limit
    )

    response = client.post(
        "/api/account/bot",
        json={"name": "sample-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    pytest.bot_sample = response["data"]["account_owned"][3]["_id"]

    response_story = client.get(
        f"/api/bot/{pytest.bot_sample}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response_story.json()
    rule_one = actual["data"][1]["_id"]
    rule_two = actual["data"][2]["_id"]

    response_delete_story_one = client.delete(
        f"/api/bot/{pytest.bot_sample}/stories/{rule_one}/RULE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response_delete_story_two = client.delete(
        f"/api/bot/{pytest.bot_sample}/stories/{rule_two}/RULE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.post(
        f"/api/bot/{pytest.bot_sample}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert (
            actual["message"]
            == "Please add at least 2 flows and 2 intents before training the bot!"
    )


def test_delete_bot():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    bot = response["data"]["account_owned"][1]["_id"]

    response = client.delete(
        f"/api/account/bot/{bot}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["message"] == "Bot removed"
    assert response["error_code"] == 0
    assert response["success"]


def test_login_for_verified():
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@10"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False

    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]


def test_list_bots_for_different_user():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["shared"]) == 1
    pytest.bot = response["data"]["shared"][0]["_id"]


def test_reset_password_for_valid_id(monkeypatch):
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/password/reset",
        json={"data": "integ1@gmail.com"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert (
            actual["message"]
            == "If the email address is registered with us, you'll receive a password reset email shortly."
    )
    assert actual["data"] is None


def test_reset_password_enabled_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.post(
        "/api/account/password/reset",
        json={"data": "integ1@gmail.com"},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "This feature is disabled"
    assert actual["data"] is None


def test_reset_password_for_invalid_id():
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/password/reset",
        json={"data": "sasha.41195@gmail.com"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "If the email address is registered with us, you'll receive a password reset email shortly."
    assert actual["data"] is None


def test_list_bots_for_different_user_2():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["shared"]) == 1
    pytest.bot = response["data"]["shared"][0]["_id"]
    pytest.account = response["data"]["shared"][0]["account"]


def test_send_link_for_valid_id(monkeypatch):
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/email/confirmation/link",
        json={"data": "integration@demo.ai"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Success! Confirmation link sent"
    assert actual["data"] is None


def test_send_link_enabled_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.post(
        "/api/account/email/confirmation/link",
        json={"data": "integration@demo.ai"},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "This feature is disabled"
    assert actual["data"] is None


def test_send_link_for_confirmed_id():
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/email/confirmation/link",
        json={"data": "integ1@gmail.com"},
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Email already confirmed!"
    assert actual["data"] is None


def test_overwrite_password_for_non_matching_passwords():
    Utility.email_conf["email"]["enable"] = True
    response = client.post(
        "/api/account/password/change",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20",
            "password": "Welcome@2",
            "confirm_password": "Welcume@2",
        },
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None


def test_overwrite_password_enabled_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.post(
        "/api/account/password/change",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20",
            "password": "Welcome@20",
            "confirm_password": "Welcome@20",
        },
    )
    actual = response.json()
    assert actual["message"] == "This feature is disabled"
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None


def test_add_and_delete_intents_by_integration_user():
    response = client.post(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 1", "role": "designer"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]

    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
        json={"data": "integration_intent"},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.delete(
        f"/api/bot/{pytest.bot}/intents/integration_intent",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration1",
        },
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent deleted!"
    assert actual["success"]


def test_add_non_integration_intent_and_delete_intent_by_integration_user():
    response = client.post(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 3", "role": "designer"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]
    pytest.disable_token = (
        f'{token["data"]["token_type"]} {token["data"]["access_token"]}'
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "non_integration_intent"},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"

    response = client.delete(
        f"/api/bot/{pytest.bot}/intents/non_integration_intent",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration1",
        },
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 422
    assert actual["message"] == "This intent cannot be deleted by an integration user"
    assert not actual["success"]
