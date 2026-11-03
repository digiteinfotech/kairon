from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training


@responses.activate
def test_idp_provider_fields():
    response = client.get(
        "/api/idp/provider/fields",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    actual_data = Utility.system_metadata["providers"]

    assert response["data"] == actual_data
    assert len(response["data"]["oidc"]["azure_oidc"]["required_fields"]) == 4


@responses.activate
def test_add_organization():
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.post(
        "/api/account/organization",
        json={"data": {"name": "sample"}},
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    result = response.json()
    assert result["data"]["org_id"] is not None
    assert result["message"] == "organization added"


@responses.activate
def test_get_organization():
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.get(
        "/api/account/organization",
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    result = response.json()
    assert result["data"] is not None
    assert result["data"]["name"] == "sample"
    assert result["data"]["user"] == "integration1234567890@demo.ai"


@responses.activate
def test_update_organization():
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.post(
        "/api/account/organization",
        json={"data": {"name": "updated_sample"}},
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    result = response.json()
    assert result["message"] == "organization added"


@responses.activate
def test_get_organization_after_update():
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.get(
        "/api/account/organization",
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    result = response.json()
    assert result["data"] is not None
    assert result["data"]["name"] == "updated_sample"
    assert result["data"]["user"] == "integration1234567890@demo.ai"


@responses.activate
def test_delete_organization(monkeypatch):
    def _delete_idp(*args, **kwargs):
        return

    monkeypatch.setattr(IDPProcessor, "delete_idp", _delete_idp)
    email = "integration1234567890@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login = response.json()
    response = client.delete(
        f"/api/account/organization/updated_sample",
        headers={
            "Authorization": login["data"]["token_type"]
                             + " "
                             + login["data"]["access_token"]
        },
    )
    result = response.json()
    assert result["data"] is None
    assert result["message"] == "Organization deleted"


def test_get_model_testing_logs_accuracy():
    response = client.get(
        f"/api/user/test/accuracy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    assert response["data"] is not None
    assert response["success"] is True
    assert response["error_code"] == 0


@mock.patch('kairon.shared.account.activity_log.UserActivityLogger.is_login_within_cooldown_period', autospec=True)
def test_delete_account(mock_password_reset):
    def _password_reset(*args, **kwargs):
        return

    mock_password_reset.return_value = _password_reset
    response_log = client.post(
        "/api/auth/login",
        data={"username": "integration@demo.ai", "password": "Welcome@10"},
    )
    actual = response_log.json()
    UserEmailConfirmation(email="integration@demo.ai").save()
    UserActivityLog(
        type="user_consent",
        user="integration@demo.ai",
        message=['Privacy Policy, Terms and Conditions and AI Guidelines consent'],
        data={
            "username": "integration@demo.ai",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "terms_and_policy_version": 1.0
        }
    ).save()
    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token_delete = actual["data"]["access_token"]
    pytest.token_type_delete = actual["data"]["token_type"]
    response = client.delete(
        "/api/account/delete",
        headers={
            "Authorization": pytest.token_type_delete + " " + pytest.access_token_delete
        },
    ).json()
    assert response["success"]
    assert response["message"] == "Account deleted"
    assert response["error_code"] == 0
    assert UserEmailConfirmation.objects(email="integration@demo.ai").count() == 0
    assert UserActivityLog.objects(user="integration@demo.ai", type='user_consent').count() == 0


def test_delete_account_already_deleted():
    response = client.delete(
        "/api/account/delete",
        headers={
            "Authorization": pytest.token_type_delete + " " + pytest.access_token_delete
        },
    ).json()
    assert not response["success"]
    assert response["message"] == "User does not exist!"


def test_get_responses_post_passwd_reset(monkeypatch):
    email = "active_session@demo.ai"
    regsiter_response = client.post(
        "/api/account/registration",
        json={
            "email": email,
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration",
            "bot": "integration",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = regsiter_response.json()
    login_response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    login_actual = login_response.json()
    pytest.access_token = login_actual["data"]["access_token"]
    pytest.token_type = login_actual["data"]["token_type"]

    response = client.post(
        "/api/account/bot",
        json={"name": "covid-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response["data"]['bot_id']
    assert response['message'] == "Bot created"

    bot_response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()

    pytest.bot = bot_response["data"]["account_owned"][0]["_id"]
    token = Authentication.create_access_token(data={"mail_id": email})

    def get_token(*args, **kwargs):
        return token

    monkeypatch.setattr(Authentication, "create_access_token", get_token)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    passwrd_change_response = client.post(
        "/api/account/password/change",
        json={
            "data": token,
            "password": "Welcome@21",
            "confirm_password": "Welcome@21",
        },
    )

    utter_response = client.get(
        f"/api/bot/{pytest.bot}/response/utter_greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = utter_response.json()
    message = actual["message"]
    error_code = actual['error_code']
    assert message == 'Session expired. Please login again!'
    assert error_code == 401


def test_create_access_token_with_iat():
    access_token = Authentication.create_access_token(
        data={"sub": "test@chat.com", "access-limit": ["/api/bot/.+/intent"]},
        token_type=TOKEN_TYPE.LOGIN.value,
    )
    payload = Utility.decode_limited_access_token(access_token)
    assert payload.get("iat") is not None


def test_overwrite_password_for_matching_passwords(monkeypatch):
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    response = client.post(
        "/api/account/password/change",
        json={
            "data": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20",
            "password": "Welcome@20",
            "confirm_password": "Welcome@20",
        },
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Success! Your password has been changed"
    assert actual["data"] is None


def test_login_new_password():
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@20"},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]


def test_login_old_password():
    response = client.post(
        "/api/auth/login",
        data={"username": "integ1@gmail.com", "password": "Welcome@10"},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["message"] == "Incorrect username or password"
    assert actual["data"] is None
    value = list(AuditLogData.objects(user="integ1@gmail.com", action='activity', entity='invalid_login').order_by(
        "-timestamp"))[
        0
    ]
    assert value["entity"] == "invalid_login"
    assert value["timestamp"]
    assert value["data"] == {'message': ['Incorrect username or password'], 'username': 'integ1@gmail.com'}


def test_get_responses_change_passwd_with_same_passwrd(monkeypatch):
    email = "samepasswrd@demo.ai"
    regsiter_response = client.post(
        "/api/account/registration",
        json={
            "email": email,
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "samepasswrd",
            "bot": "samepasswrd",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    token = Authentication.create_access_token(data={"mail_id": email})

    def get_token(*args, **kwargs):
        return token

    monkeypatch.setattr(Authentication, "create_access_token", get_token)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    Utility.environment["user"]["reset_password_cooldown_period"] = 0
    passwrd_change_response = client.post(
        "/api/account/password/change",
        json={"data": token, "password": "Welcome@10", "confirm_password": "Welcome@10"},
    )
    response = passwrd_change_response.json()
    message = response.get("message")
    assert message == "You have already used this password, try another!"


def test_get_responses_change_passwd_with_same_passwrd_rechange(monkeypatch):
    Utility.environment["user"]["reset_password_cooldown_period"] = 0
    email = "samepasswrd2@demo.ai"
    regsiter_response = client.post(
        "/api/account/registration",
        json={
            "email": email,
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "samepasswrd2",
            "bot": "samepasswrd2",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    token = Authentication.create_access_token(data={"mail_id": email})

    def get_token(*args, **kwargs):
        return token

    monkeypatch.setattr(Authentication, "create_access_token", get_token)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    passwrd_change_response = client.post(
        "/api/account/password/change",
        json={
            "data": token,
            "password": "Welcome@21",
            "confirm_password": "Welcome@21",
        },
    )
    passwrd_firstchange = passwrd_change_response.json()
    assert passwrd_firstchange["success"]
    assert passwrd_firstchange["error_code"] == 0
    assert passwrd_firstchange["message"] == "Success! Your password has been changed"
    assert passwrd_firstchange["data"] is None

    passwrd_rechange_response = client.post(
        "/api/account/password/change",
        json={
            "data": token,
            "password": "Welcome@21",
            "confirm_password": "Welcome@21",
        },
    )
    response = passwrd_rechange_response.json()
    message = response.get("message")
    assert message == "You have already used this password, try another!"


def test_idp_provider_fields_unauth():
    response = client.get(
        "/api/idp/provider/fields",
        headers={"Authorization": pytest.token_type + " worng_token"},
    ).json()

    assert response["error_code"] == 401


def test_allowed_origin_default():
    response = client.post(
        "/api/auth/login", data={"username": "test@demo.ai", "password": "Welcome@10"}
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "User does not exist!"
    assert response.headers == {
        "content-length": "79",
        "content-type": "application/json",
        "vary": "Origin",
        "cache-control": "must-revalidate",
        "content-security-policy": "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'",
        "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
        "permissions-policy": "accelerometer=(), autoplay=(), fullscreen=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), usb=()",
        "referrer-policy": "no-referrer",
        "server": "Secure",
        "x-content-type-options": "nosniff",
        "cross-origin-embedder-policy": "require-corp",
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-resource-policy": "same-origin",
        "access-control-allow-origin": "*",
    }


def test_allowed_origin(monkeypatch):
    monkeypatch.setitem(Utility.environment["cors"], "origin", "http://digite.com")

    response = client.post(
        "/api/auth/login",
        data={"username": "test@demo.ai", "password": "Welcome@10"},
        headers={"origin": "http://digite.com"},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert not actual["success"]
    assert actual["message"] == "User does not exist!"
    assert response.headers == {
        "content-length": "79",
        "content-type": "application/json",
        "access-control-allow-origin": "http://digite.com",
        "access-control-allow-credentials": "true",
        "access-control-expose-headers": "content-disposition",
        "vary": "Origin",
        "cache-control": "must-revalidate",
        "content-security-policy": "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'",
        "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
        "permissions-policy": "accelerometer=(), autoplay=(), fullscreen=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), usb=()",
        "referrer-policy": "no-referrer",
        "server": "Secure",
        "x-content-type-options": "nosniff",
        "cross-origin-embedder-policy": "require-corp",
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-resource-policy": "same-origin",
    }


def test_get_client_ip():
    headers = {"X-Forwarded-For": "10.0.0.1"}
    response = client.post(
        "/api/auth/login",
        data={"username": "test@demo.ai", "password": "Welcome@10"},
        headers=headers,
    )
    assert Utility.get_client_ip(response.request) == "10.0.0.1"

    headers = {"X-Forwarded-For": "10.0.0.2, 10.0.1.1"}
    response = client.post(
        "/api/auth/login",
        data={"username": "test@demo.ai", "password": "Welcome@10"},
        headers=headers,
    )
    assert Utility.get_client_ip(response.request) == "10.0.0.2, 10.0.1.1"

    headers = {"X-Real-IP": "10.0.0.3"}
    response = client.post(
        "/api/auth/login",
        data={"username": "test@demo.ai", "password": "Welcome@10"},
        headers=headers,
    )
    assert Utility.get_client_ip(response.request) == "10.0.0.3"


def test_allow_only_sso_login(monkeypatch):
    user = "test@demo.in"
    organization = "new_test"
    feature_type = FeatureMappings.ONLY_SSO_LOGIN.value
    value = True
    OrgProcessor.upsert_user_org_mapping(
        user=user, org=organization, feature=feature_type, value=value
    )

    response = client.post(
        "/api/auth/login",
        data={"username": user, "password": "Welcome@10"},
    )
    actual = response.json()
    assert (
            actual["message"]
            == "Login with your org SSO url, Login with username/password not allowed"
    )


def test_idp_callback(monkeypatch):
    def _validate_org_settings(*args, **kwargs):
        return

    def _get_idp_token(*args, **kwargs):
        return {
            "email": "new_idp_user@demo.in",
            "given_name": "test",
            "family_name": "user",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        }

    monkeypatch.setattr(IDPProcessor, "get_idp_token", _get_idp_token)
    monkeypatch.setattr(OrgProcessor, "validate_org_settings", _validate_org_settings)

    realm_name = "test"
    response = client.get(
        f"/api/auth/login/idp/callback/{realm_name}?session_state=asikndhfnnin-jinsdn-sdnknsdn&code=kjaskjkajb-wkejhwejwe",
    )
    result = response.json()
    assert result["data"]["access_token"] is not None
    assert result["data"]["token_type"] == "bearer"
    assert result["message"] == "User Authenticated"


def test_api_login_with_SSO_only_flag():
    user = "idp_user@demo.in"
    organization = "new_test"
    feature_type = FeatureMappings.ONLY_SSO_LOGIN.value
    value = True
    OrgProcessor.upsert_user_org_mapping(
        user=user, org=organization, feature=feature_type, value=value
    )

    email = "idp_user@demo.in"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()
    assert (
            actual["message"]
            == "Login with your org SSO url, Login with username/password not allowed"
    )
    assert actual["error_code"] == 422
    assert actual["success"] == False


def test_list_system_metadata():
    response = client.get(url=f"/api/system/metadata", follow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]) == 21

def test_leave_bot_successfully_1(monkeypatch):
    response = client.post(
        "/api/account/registration",
        json={
            "email": "mayank_owner@digite.com",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "mayank_owner",
            "bot": "mayank_owner",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    response = client.post(
        "/api/account/registration",
        json={
            "email": "mayank_tester@digite.com",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "mayank_tester",
            "bot": "mayank_tester",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    response = client.post(
        "/api/account/registration",
        json={
            "email": "mayank_admin@digite.com",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "mayank_admin",
            "bot": "mayank_admin",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    response = client.post(
        "/api/auth/login",
        data={"username": "mayank_owner@digite.com", "password": "Welcome@10"},
    )

    actual = response.json()
    assert "access_token" in actual["data"]
    assert actual["success"]

    response = client.post(
        "/api/account/bot",
        json={"name": "mayank-test-bot"},
        headers={
            "Authorization": f"{actual['data']['token_type']}" + " " + f"{actual['data']['access_token']}"
        },
    ).json()
    pytest.mayank_bot = response['data']['bot_id']

    response = client.post(
        f"/api/user/{pytest.mayank_bot}/member",
        json={"email": "mayank_tester@digite.com", "role": "tester"},
        headers={
            "Authorization": f"{actual['data']['token_type']}" + " " + f"{actual['data']['access_token']}"
        },
    ).json()

    response = client.post(
        "/api/auth/login",
        data={"username": "mayank_tester@digite.com", "password": "Welcome@10"},
    )
    actual = response.json()

    response = client.get(
        "/api/account/bot",
        headers={
            "Authorization": f"{actual['data']['token_type']}" + " " + f"{actual['data']['access_token']}"
        },
    ).json()
    assert len(response["data"]["shared"]) == 1

    response = client.delete(
        f"/api/user/{pytest.mayank_bot}/leave",
        headers={
            "Authorization": f"{actual['data']['token_type']}" + " " + f"{actual['data']['access_token']}"
        },
    ).json()
    assert response["message"] == "Successfully left the bot"
    assert response["error_code"] == 0
    assert response["success"]

def test_leave_bot_owner_forbidden():
    response = client.post(
        "/api/auth/login",
        data={"username": "mayank_owner@digite.com", "password": "Welcome@10"},
    )
    actual = response.json()
    assert "access_token" in actual["data"]
    assert actual["success"]

    # Step 2: Attempt to leave the bot
    response = client.delete(
        f"/api/user/{pytest.mayank_bot}/leave",
        headers={
            "Authorization": f"{actual['data']['token_type']}"+ " " + f"{actual['data']['access_token']}"
        },
    ).json()

    # Step 3: Validate response
    assert response["message"] == "Owner cannot leave the bot"
    assert response["error_code"] == 422
    assert not response["success"]

def test_leave_bot_with_integration_tokens():
    response = client.post(
        "/api/auth/login",
        data={"username": "mayank_owner@digite.com", "password": "Welcome@10"},
    )

    actual = response.json()
    assert "access_token" in actual["data"]
    assert actual["success"]

    response = client.post(
        f"/api/user/{pytest.mayank_bot}/member",
        json={"email": "mayank_admin@digite.com", "role": "admin"},
        headers={
            "Authorization": f"{actual['data']['token_type']}" + " " + f"{actual['data']['access_token']}"
        },
    ).json()

    response = client.post(
        "/api/auth/login",
        data={"username": "mayank_admin@digite.com", "password": "Welcome@10"},
    )
    actual = response.json()
    assert "access_token" in actual["data"]
    assert actual["success"]


    response = client.post(
        f"/api/auth/{pytest.mayank_bot}/integration/token",
        json={"name": "integration 100", "expiry_minutes": 1440, "role": "designer"},
        headers={
            "Authorization": f"{actual['data']['token_type']}" + " " + f"{actual['data']['access_token']}"
        },
    )
    token = response.json()
    print(token)
    response = client.delete(
        f"/api/user/{pytest.mayank_bot}/leave",
        headers={
            "Authorization": actual["data"]["token_type"] + " " + actual["data"]["access_token"]
        },
    )
    actual = response.json()
    assert actual["message"] == "You must delete all your integration tokens before leaving the bot"
    assert actual["error_code"] == 422
    assert not actual["success"]

def test_leave_non_existent_bot_1():
    response = client.post(
        "/api/auth/login",
        data={"username": "mayank_tester@digite.com", "password": "Welcome@10"},
    )
    actual = response.json()
    assert "access_token" in actual["data"]
    assert actual["success"]
    response = client.delete(
        "/api/user/000000abcdefgh/leave",
        headers={
            "Authorization": f"{actual['data']['token_type']}" + " " + f"{actual['data']['access_token']}"
        },
    )
    actual = response.json()
    assert actual["message"] == "Access to bot is denied"
    assert actual["error_code"] == 422
    assert not actual["success"]



def test_redoc_headers():
    response = client.get("/redoc")
    assert response.status_code == 200
    assert response.headers == {
        "content-length": "497",
        "content-type": "text/html; charset=utf-8",
        "vary": "Origin, Accept-Encoding",
        "content-encoding": "gzip",
        "cache-control": "must-revalidate",
        "content-security-policy": "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'; worker-src blob:",
        "strict-transport-security": "max-age=31536000; includeSubDomains; preload",
        "permissions-policy": "accelerometer=(), autoplay=(), fullscreen=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), usb=()",
        "referrer-policy": "no-referrer",
        "server": "Secure",
        "x-content-type-options": "nosniff",
        "cross-origin-embedder-policy": "require-corp",
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-resource-policy": "same-origin",
        "access-control-allow-origin": "*",
    }
