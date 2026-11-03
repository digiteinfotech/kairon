from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_get_ui_config_empty():
    response = client.get(
        url=f"/api/account/config/ui",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {}
    assert actual["success"]


def test_add_ui_config():
    response = client.put(
        url=f"/api/account/config/ui",
        json={"data": {"has_stepper": True, "has_tour": False, "theme": "white"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["success"]
    assert actual["message"] == "Config saved!"

    response = client.put(
        url=f"/api/account/config/ui",
        json={"data": {"has_stepper": True, "has_tour": False, "theme": "black"}},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["success"]
    assert actual["message"] == "Config saved!"


def test_get_ui_config():
    response = client.get(
        url=f"/api/account/config/ui",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"] == {"has_stepper": True, "has_tour": False, "theme": "black"}
    assert actual["success"]


def test_sso_redirect_url_invalid_type():
    response = client.get(url=f"/api/auth/login/sso/ethereum")
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "ethereum login is not supported"
    assert not actual["success"]


def test_list_sso_not_enabled(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.get(url=f"/api/system/properties", follow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert actual["data"] == {
        "sso": {"facebook": False, "linkedin": False, "google": False},
        "enable_sso_only": True,
        "validate_trusted_device": False,
        "enable_apm": False,
        "enable_notifications": False,
        "validate_recaptcha": False,
        "enable_multilingual": False,
        "properties": {"bot": {"enable_onboarding": True}},
    }


def test_sso_redirect_url_not_enabled():
    response = client.get(url=f"/api/auth/login/sso/google", follow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "google login is not enabled"
    assert not actual["success"]

    response = client.get(url=f"/api/auth/login/sso/linkedin", follow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "linkedin login is not enabled"
    assert not actual["success"]

    response = client.get(url=f"/api/auth/login/sso/facebook", follow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "facebook login is not enabled"
    assert not actual["success"]


def test_sso_redirect_url(monkeypatch):
    discovery_url = (
        "https://accounts.google.com/o/oauth2/v2/auth?response_type=code&client_id="
    )

    async def _mock_get_discovery_doc(*args, **kwargs):
        return {"authorization_endpoint": discovery_url}

    Utility.environment["sso"]["linkedin"]["enable"] = True
    Utility.environment["sso"]["google"]["enable"] = True
    Utility.environment["sso"]["facebook"]["enable"] = True
    monkeypatch.setattr(GoogleSSO, "get_discovery_document", _mock_get_discovery_doc)

    response = client.get(url=f"/api/auth/login/sso/google", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].__contains__(discovery_url)

    response = client.get(url=f"/api/auth/login/sso/linkedin", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].__contains__(
        "https://www.linkedin.com/oauth/v2/authorization?response_type=code&client_id="
    )

    response = client.get(url=f"/api/auth/login/sso/facebook", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].__contains__(
        "https://www.facebook.com/v9.0/dialog/oauth?response_type=code&client_id="
    )


def test_list_sso_enabled():
    Utility.environment["sso"]["linkedin"]["enable"] = True
    Utility.environment["sso"]["google"]["enable"] = True

    response = client.get(url=f"/api/system/properties", follow_redirects=False)
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert actual["data"] == {
        "sso": {"facebook": False, "linkedin": True, "google": True},
        "enable_apm": False,
        "enable_notifications": False,
        "validate_recaptcha": False,
        "enable_sso_only": False,
        "validate_trusted_device": False,
        "enable_multilingual": False,
        "properties": {"bot": {"enable_onboarding": True}},
    }


def test_sso_get_login_token_invalid_type():
    response = client.get(url=f"/api/auth/login/sso/callback/ethereum")
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "ethereum login is not supported"
    assert not actual["success"]


def test_sso_get_login_token(monkeypatch):
    token = "fgyduhsaifusijfisofwh87eyfhw98yqwhfc8wufchwufehwncj"

    async def __mock_verify_and_process(*args, **kwargs):
        return (
            False,
            {
                "email": "new_user@digite.com",
                "first_name": "new",
                "password": SecretStr("123456789"),
            },
            token,
        )

    monkeypatch.setattr(Authentication, "verify_and_process", __mock_verify_and_process)
    response = client.get(
        url=f"/api/auth/login/sso/callback/google?code=123456789", follow_redirects=False
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
    values = list(AuditLogData.objects(user="new_user@digite.com", action='activity', entity='social_login').order_by(
        "-timestamp"))
    audit_log_data = values[0].to_mongo().to_dict()
    assert audit_log_data['user'] == 'new_user@digite.com'
    assert audit_log_data["attributes"] == [{'key': 'email', 'value': 'new_user@digite.com'}]
    assert audit_log_data["action"] == 'activity'
    assert audit_log_data['entity'] == 'social_login'
    assert audit_log_data['data']['username'] == 'new_user@digite.com'
    assert audit_log_data['data']['sso_type'] == 'google'

    response = client.get(
        url=f"/api/auth/login/sso/callback/linkedin?code=123456789",
        follow_redirects=False,
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
    values = list(AuditLogData.objects(user="new_user@digite.com", action='activity', entity='social_login').order_by(
        "-timestamp"))
    audit_log_data = values[0].to_mongo().to_dict()
    assert audit_log_data['user'] == 'new_user@digite.com'
    assert audit_log_data["attributes"] == [{'key': 'email', 'value': 'new_user@digite.com'}]
    assert audit_log_data["action"] == 'activity'
    assert audit_log_data['entity'] == 'social_login'
    assert audit_log_data['data']['username'] == 'new_user@digite.com'
    assert audit_log_data['data']['sso_type'] == 'linkedin'

    response = client.get(
        url=f"/api/auth/login/sso/callback/facebook?code=123456789",
        follow_redirects=False,
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
    values = list(AuditLogData.objects(user="new_user@digite.com", action='activity', entity='social_login').order_by(
        "-timestamp"))
    audit_log_data = values[0].to_mongo().to_dict()
    assert audit_log_data['user'] == 'new_user@digite.com'
    assert audit_log_data["attributes"] == [{'key': 'email', 'value': 'new_user@digite.com'}]
    assert audit_log_data["action"] == 'activity'
    assert audit_log_data['entity'] == 'social_login'
    assert audit_log_data['data']['username'] == 'new_user@digite.com'
    assert audit_log_data['data']['sso_type'] == 'facebook'


def test_trigger_mail_on_new_signup_with_sso(monkeypatch):
    token = "fgyduhsaifusijfisofwh87eyfhw98yqwhfc8wufchwufehwncj"

    async def __mock_verify_and_process(*args, **kwargs):
        return (
            False,
            {
                "email": "new_user@digite.com",
                "first_name": "new",
                "password": SecretStr("123456789"),
            },
            token,
        )

    monkeypatch.setattr(Authentication, "verify_and_process", __mock_verify_and_process)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    Utility.email_conf["email"]["enable"] = True
    response = client.get(
        url=f"/api/auth/login/sso/callback/google?code=123456789", follow_redirects=False
    )
    actual = response.json()
    Utility.email_conf["email"]["enable"] = False
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not Utility.check_empty_string(actual["message"])
    actual = response.json()
    assert actual["data"]["access_token"] == token
    assert actual["data"]["token_type"] == "bearer"
