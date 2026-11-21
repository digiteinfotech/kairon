from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training

def test_healthcheck():
    response = client.get("/healthcheck")
    actual = response.json()
    assert response.status_code == 200
    assert actual["message"] == "health check ok"


def test_api_wrong_login():
    response = client.post(
        "/api/auth/login", data={"username": "test@demo.ai", "password": "Welcome@1"}
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
    value = list(AuditLogData.objects(user="test@demo.ai", action='activity', entity='invalid_login'))
    assert value[0]["entity"] == "invalid_login"
    assert value[0]["timestamp"]
    assert len(value) == 1


@mock.patch("kairon.shared.utils.Utility.validate_recaptcha", autospec=True)
@mock.patch("kairon.shared.utils.MailUtility.trigger_smtp", autospec=True)
def test_book_a_demo(trigger_smtp_mock, validate_recaptcha_mock, monkeypatch):
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl1234567890"
    )
    data = {
        "first_name": "sample",
        "last_name": "test",
        "email": "sampletest@gmail.com",
        "contact": "9876543210",
        "additional_info": "Thank You",
    }
    form_data = {"data": data, "recaptcha_response": "1234567890"}

    with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
        mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.post("/api/user/demo", json=form_data).json()
    assert (
            response["message"]
            == "Thank You for your interest in Kairon. We will reach out to you soon."
    )
    assert not response["data"]
    assert response["error_code"] == 0
    assert response["success"]


@mock.patch("kairon.shared.utils.MailUtility.trigger_smtp", autospec=True)
def test_book_a_demo_with_invalid_recaptcha_response(trigger_smtp_mock, monkeypatch):
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl1234567890"
    )
    data = {
        "first_name": "sample",
        "last_name": "test",
        "email": "sampletest@gmail.com",
        "contact": "9876543210",
        "additional_info": "Thank You",
    }
    form_data = {"data": data, "recaptcha_response": ""}

    with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
        mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.post("/api/user/demo", json=form_data).json()
    assert response["message"] == "recaptcha_response is required"
    assert not response["data"]
    assert response["error_code"] == 422
    assert not response["success"]


@responses.activate
@mock.patch("kairon.shared.utils.MailUtility.trigger_smtp", autospec=True)
def test_book_a_demo_with_validate_recaptcha_failed(trigger_smtp_mock):
    data = {
        "first_name": "sample",
        "last_name": "test",
        "email": "sampletest@gmail.com",
        "contact": "9876543210",
        "additional_info": "Thank You",
    }
    form_data = {"data": data, "recaptcha_response": "1234567890"}

    with patch.dict(
            Utility.environment["security"],
            {"validate_recaptcha": True, "recaptcha_secret": "asdfghjkl1234567890"},
    ):
        with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
            mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}

            responses.add(
                responses.POST,
                "https://www.google.com/recaptcha/api/siteverify?secret=asdfghjkl1234567890&response=1234567890&remoteip=testclient",
                json={"success": False},
            )

            response = client.post("/api/user/demo", json=form_data).json()
    assert response["message"] == "Failed to validate recaptcha"
    assert not response["data"]
    assert response["error_code"] == 422
    assert not response["success"]


@mock.patch("kairon.shared.utils.Utility.validate_recaptcha", autospec=True)
@mock.patch("kairon.shared.utils.MailUtility.trigger_smtp", autospec=True)
def test_book_a_demo_with_valid_data(trigger_smtp_mock, validate_recaptcha_mock, monkeypatch):
    monkeypatch.setitem(Utility.environment['security'], 'validate_recaptcha', True)
    monkeypatch.setitem(Utility.environment['security'], 'recaptcha_secret', 'asdfghjkl1234567890')
    data = {
        "first_name": "Mahesh",
        "last_name": 'Sattala',
        "email": "mahesh.sattala@digite.com",
        "phone": "+919876543210",
        "message": "Thank You",
        "recaptcha_response": "Svw2mPVxM0SkO4_2yxTcDQQ7iKNUDeDhGf4l6C2i"
    }
    form_data = {"data": data, "recaptcha_response": "1234567890"}

    with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
        mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.post(
            "/api/user/demo",
            json=form_data
        ).json()
    assert response['message'] == 'Thank You for your interest in Kairon. We will reach out to you soon.'
    assert not response['data']
    assert response['error_code'] == 0
    assert response['success']
    demo_request_logs = DemoRequestLogs.objects(first_name="Mahesh", last_name="Sattala",
                                                email="mahesh.sattala@digite.com").get().to_mongo().to_dict()
    assert demo_request_logs['first_name'] == "Mahesh"
    assert demo_request_logs['last_name'] == "Sattala"
    assert demo_request_logs['email'] == "mahesh.sattala@digite.com"
    assert demo_request_logs['phone'] == "+919876543210"
    assert demo_request_logs['status'] == "request_received"
    assert demo_request_logs['message'] == "Thank You"
    assert demo_request_logs['recaptcha_response'] == "Svw2mPVxM0SkO4_2yxTcDQQ7iKNUDeDhGf4l6C2i"


def test_account_registration_without_privacy_policy_and_terms_consent_and_accepted_ai_guidelines(monkeypatch):
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration",
            "bot": "integration",
            "accepted_privacy_policy": False,
            "accepted_terms": False,
            "accepted_ai_guidelines": False
        },
    )
    actual = response.json()
    assert actual["message"] == "Should be agreed to: privacy policy, terms and conditions, ai guidelines"
    assert not actual["success"]
    assert not actual["data"]
    assert actual["error_code"] == 422
    values = list(UserActivityLog.objects(user="integration@demo.ai", type='user_consent').order_by(
        "-timestamp"))
    user_activity_log = values[0].to_mongo().to_dict()
    print(user_activity_log)
    assert user_activity_log['type'] == 'user_consent'
    assert user_activity_log['user'] == 'integration@demo.ai'
    assert user_activity_log['timestamp']
    assert user_activity_log['account'] == -1
    assert user_activity_log['message'] == ['Privacy Policy, Terms and Conditions and AI Guidelines consent']
    assert user_activity_log['data']['username'] == 'integration@demo.ai'
    assert user_activity_log['data']['accepted_privacy_policy'] is False
    assert user_activity_log['data']['accepted_terms'] is False
    assert user_activity_log['data']['accepted_ai_guidelines'] is False
    assert user_activity_log['data']['terms_and_policy_version'] == 1.0


def test_account_registration_without_privacy_policy_and_accepted_ai_guidelines(monkeypatch):
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration",
            "bot": "integration",
            "accepted_privacy_policy": False,
            "accepted_terms": True,
            "accepted_ai_guidelines": False
        },
    )
    actual = response.json()
    assert actual["message"] == "Should be agreed to: privacy policy, ai guidelines"
    assert not actual["success"]
    assert not actual["data"]
    assert actual["error_code"] == 422
    values = list(UserActivityLog.objects(user="integration@demo.ai", type='user_consent').order_by(
        "-timestamp"))
    user_activity_log = values[0].to_mongo().to_dict()
    print(user_activity_log)
    assert user_activity_log['type'] == 'user_consent'
    assert user_activity_log['user'] == 'integration@demo.ai'
    assert user_activity_log['account'] == -1
    assert user_activity_log['timestamp']
    assert user_activity_log['message'] == ['Privacy Policy, Terms and Conditions and AI Guidelines consent']
    assert user_activity_log['data']['username'] == 'integration@demo.ai'
    assert user_activity_log['data']['accepted_privacy_policy'] is False
    assert user_activity_log['data']['accepted_terms'] is True
    assert user_activity_log['data']['accepted_ai_guidelines'] is False
    assert user_activity_log['data']['terms_and_policy_version'] == 1.0


def test_account_registration_without_terms_and_conditions_consent(monkeypatch):
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration",
            "bot": "integration",
            "accepted_privacy_policy": True,
            "accepted_terms": False,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Should be agreed to: terms and conditions"
    assert not actual["success"]
    assert not actual["data"]
    assert actual["error_code"] == 422
    values = list(UserActivityLog.objects(user="integration@demo.ai", type='user_consent').order_by(
        "-timestamp"))
    user_activity_log = values[0].to_mongo().to_dict()
    print(user_activity_log)
    assert user_activity_log['type'] == 'user_consent'
    assert user_activity_log['user'] == 'integration@demo.ai'
    assert user_activity_log['account'] == -1
    assert user_activity_log['timestamp']
    assert user_activity_log['message'] == ['Privacy Policy, Terms and Conditions and AI Guidelines consent']
    assert user_activity_log['data']['username'] == 'integration@demo.ai'
    assert user_activity_log['data']['accepted_privacy_policy'] is True
    assert user_activity_log['data']['accepted_terms'] is False
    assert user_activity_log['data']['accepted_ai_guidelines'] is True
    assert user_activity_log['data']['terms_and_policy_version'] == 1.0


def test_account_registration_error():
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "welcome@1",
            "confirm_password": "welcome@1",
            "account": "integration",
            "bot": "integration",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == [
        {'loc': ['body', 'password'], 'msg': 'Password length must be 10\nMissing 1 uppercase letter',
         'type': 'value_error'}]
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None


@responses.activate
def test_recaptcha_verified_request(monkeypatch):
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl1234567890"
    )

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl1234567890&response=1234567890",
        json={"success": True},
    )
    response = client.post(
        "/api/account/registration",
        json={
            "recaptcha_response": "1234567890",
            "email": "integration1234567890@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration1234567890",
            "bot": "integration",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl1234567890&response=1234567890&remoteip=58.0.127.89",
        json={"success": True},
    )
    response = client.post(
        "/api/account/registration",
        json={
            "recaptcha_response": "1234567890",
            "remote_ip": "58.0.127.89",
            "email": "integration1234567@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration1234567",
            "bot": "integration",
            "add_trusted_device": True,
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"


@responses.activate
def test_recaptcha_verified_request_invalid(monkeypatch):
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl1234567890"
    )

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl1234567890&response=1234567890",
        json={"success": False},
    )

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl1234567890&response=987654321",
        json={"success": True},
        status=204,
    )

    response = client.post(
        "/api/account/registration",
        json={
            "recaptcha_response": "1234567890",
            "email": "integration1234567890@demo.ai",
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
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "Failed to validate recaptcha",
        "data": None,
        "error_code": 422,
    }

    response = client.post(
        "/api/account/registration",
        json={
            "recaptcha_response": "987654321",
            "email": "integration1234567890@demo.ai",
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
    actual = response.json()
    assert not actual["success"]
    assert actual["message"]
    assert actual["data"] is None
    assert actual["error_code"] == 422

    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration1234567890@demo.ai",
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
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "recaptcha_response is required",
        "data": None,
        "error_code": 422,
    }


@responses.activate
def test_account_registation_temporary_email():
    email = "test@temporay.com"
    api_key = "test"
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
        actual = response.json()
        assert actual["message"] == [
            {
                "loc": ["body", "email"],
                "msg": "Invalid or disposable Email!",
                "type": "value_error",
            }
        ]


@responses.activate
def test_account_registation_invalid_email():
    email = "test@temporay.com"
    api_key = "test"
    with patch.dict(
            Utility.environment,
            {"verify": {"email": {"type": "quickemail", "key": api_key, "enable": True}}},
    ):
        responses.add(
            responses.GET,
            "http://api.quickemailverification.com/v1/verify?"
            + urlencode({"apikey": api_key, "email": email}),
            json={
                "result": "invalid",
                "reason": "rejected_email",
                "disposable": "false",
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
        actual = response.json()
        assert actual["message"] == [
            {
                "loc": ["body", "email"],
                "msg": "Invalid or disposable Email!",
                "type": "value_error",
            }
        ]


@responses.activate
def test_account_registation_invalid_email_quick_email_valid():
    email = "test@temporay.com"
    api_key = "test"
    with patch.dict(
            Utility.environment,
            {
                "verify": {
                    "email": {"type": "quickemail", "key": api_key, "enable": True}
                }
            },
    ):
        responses.add(
            responses.GET,
            "http://api.quickemailverification.com/v1/verify?"
            + urlencode({"apikey": api_key, "email": email}),
            json={
                "result": "valid",
                "reason": "rejected_email",
                "disposable": "false",
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
            "/api/account/registration",
            json={
                "email": email,
                "first_name": "Email",
                "last_name": "Validation",
                "password": "Welcome@12",
                "confirm_password": "Welcome@12",
                "account": "email_validation",
                "bot": "email_validation",
                "accepted_privacy_policy": True,
                "accepted_terms": True,
                "accepted_ai_guidelines": True
            },
        )
        actual = response.json()
        assert actual["message"] == "Account Registered!"


def test_account_registration(monkeypatch):
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
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
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    response = client.post(
        "/api/account/registration",
        json={
            "email": "INTEGRATIONTEST@DEMO.AI",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integrationtest",
            "bot": "integrationtest",
            "fingerprint": "asdfghj4567890",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"

    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    response = client.post(
        "/api/account/registration",
        json={
            "email": "INTEGRATION2@DEMO.AI",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration2",
            "bot": "integration2",
            "fingerprint": "asdfghj4567890",
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == "Account Registered!"
    assert response.headers == {
        "content-length": "75",
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


def test_account_registration_enable_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    response = client.post(
        "/api/account/registration",
        json={
            "email": "integration@demo.ai",
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
    actual = response.json()
    assert actual["message"] == "This feature is disabled"
    assert actual["error_code"] == 422
    assert not actual["success"]


def test_api_wrong_password():
    response = client.post(
        "/api/auth/login",
        data={"username": "INTEGRATION@DEMO.AI", "password": "welcome@1"},
    )
    actual = response.json()
    assert actual["error_code"] == 401
    assert not actual["success"]
    assert actual["message"] == "Incorrect username or password"
    value = list(AuditLogData.objects(user="integration@demo.ai", action='activity', entity='invalid_login'))

    assert value[0]["entity"] == "invalid_login"
    assert value[0]["timestamp"]
    assert len(value) == 1


@responses.activate
def test_api_login_with_recaptcha(monkeypatch):
    email = "integration@demo.ai"
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl123456"
    )

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl123456&response=asdfghjkl2345",
        json={"success": True},
    )
    response = client.post(
        "/api/auth/login",
        data={
            "username": email,
            "password": "Welcome@10",
            "recaptcha_response": "asdfghjkl2345",
        },
    )
    actual = response.json()
    assert all(
        [
            True if actual["data"][key] else False
            for key in ["access_token", "token_type"]
        ]
    )


@responses.activate
def test_api_login_with_recaptcha_failed(monkeypatch):
    email = "integration@demo.ai"
    monkeypatch.setitem(Utility.environment["security"], "validate_recaptcha", True)
    monkeypatch.setitem(
        Utility.environment["security"], "recaptcha_secret", "asdfghjkl123456"
    )

    responses.add(
        "POST",
        f"{Utility.environment['security']['recaptcha_url']}?secret=asdfghjkl123456&response=asdfghjkl23",
        json={"success": False},
    )
    response = client.post(
        "/api/auth/login",
        data={
            "username": email,
            "password": "Welcome@10",
            "recaptcha_response": "asdfghjkl23",
        },
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "Failed to validate recaptcha",
        "data": None,
        "error_code": 422,
    }

    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()
    assert actual == {
        "success": False,
        "message": "recaptcha_response is required",
        "data": None,
        "error_code": 422,
    }


def test_api_login(monkeypatch):
    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
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
    pytest.access_token = actual["data"]["access_token"]
    pytest.token_type = actual["data"]["token_type"]

    response = client.post(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token, 'Content-Type': 'application/json'},
        json={"name": "Hi-Hello", "from_template": "Hi-Hello"},
    ).json()
    assert response['message'] == "Bot created"
    assert response['data']['bot_id']

    pytest.username = email
    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["data"]["user"]["_id"]
    assert response["data"]["user"]["email"] == "integration@demo.ai"
    assert (
            response["data"]["user"]["bots"]["account_owned"][0]["user"]
            == "integration@demo.ai"
    )
    assert response["data"]["user"]["bots"]["account_owned"][0]["timestamp"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["name"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["_id"]
    assert not response["data"]["user"]["bots"]["shared"]
    assert response["data"]["user"]["timestamp"]
    assert response["data"]["user"]["status"]
    assert response["data"]["user"]["account_name"] == "integration"
    assert response["data"]["user"]["first_name"] == "Demo"
    assert response["data"]["user"]["last_name"] == "User"
    assert response["data"]["user"]["accepted_privacy_policy"] is True
    assert response["data"]["user"]["accepted_terms"] is True
    assert response["data"]["user"]["show_updated_terms_and_policy"] is False

    email = "integrationtest@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
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

    email = "integration2@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
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

    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "User Authenticated"
    assert actual["data"]
    assert actual["data"]["token_type"] == "bearer"
    assert actual["data"]["access_token"]
    assert actual["data"]["refresh_token"]
    assert actual["data"]["access_token_expiry"]
    assert actual["data"]["refresh_token_expiry"]
    refresh_token = actual["data"]["refresh_token"]
    access_token = actual["data"]["access_token"]

    response = client.get(
        f"/api/auth/token/refresh",
        headers={"Authorization": pytest.token_type + " " + access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Only refresh tokens can be used to generate new token!"

    response = client.get(
        f"/api/auth/token/refresh",
        headers={"Authorization": pytest.token_type + " " + refresh_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["access_token"]
    assert actual["data"]["token_type"]
    assert actual["data"]["refresh_token"]
    assert (
            actual["message"]
            == "This token will be shown only once. Please copy this somewhere safe."
               "It is your responsibility to keep the token secret. "
               "If leaked, others may have access to your system."
    )


def test_get_user_details_with_latest_version(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "terms_and_policy_version", 2.0)
    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = response.json()
    print(response)
    assert response["success"]
    assert response["error_code"] == 0
    assert response["data"]["user"]["_id"]
    assert response["data"]["user"]["email"] == "integration@demo.ai"
    assert (
            response["data"]["user"]["bots"]["account_owned"][0]["user"]
            == "integration@demo.ai"
    )
    assert response["data"]["user"]["bots"]["account_owned"][0]["timestamp"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["name"]
    assert response["data"]["user"]["bots"]["account_owned"][0]["_id"]
    assert not response["data"]["user"]["bots"]["shared"]
    assert response["data"]["user"]["timestamp"]
    assert response["data"]["user"]["status"]
    assert response["data"]["user"]["account_name"] == "integration"
    assert response["data"]["user"]["first_name"] == "Demo"
    assert response["data"]["user"]["last_name"] == "User"
    assert response["data"]["user"]["accepted_privacy_policy"] is True
    assert response["data"]["user"]["accepted_terms"] is True
    assert response["data"]["user"]["show_updated_terms_and_policy"] is True


def test_add_user_consent_details():
    response = client.post(
        "/api/user/consent/details",
        json={
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Consent Details added!"

    values = list(UserActivityLog.objects(user="integration@demo.ai", type='user_consent').order_by(
        "-timestamp"))
    user_activity_log = values[0].to_mongo().to_dict()
    print(user_activity_log)
    assert user_activity_log['type'] == 'user_consent'
    assert user_activity_log['user'] == 'integration@demo.ai'
    assert user_activity_log['account'] == -1
    assert user_activity_log['timestamp']
    assert user_activity_log['message'] == ['Privacy Policy, Terms and Conditions and AI Guidelines consent']
    assert user_activity_log['data']['username'] == 'integration@demo.ai'
    assert user_activity_log['data']['accepted_privacy_policy'] is True
    assert user_activity_log['data']['accepted_terms'] is True
    assert user_activity_log['data']['accepted_ai_guidelines'] is True
    assert user_activity_log['data']['terms_and_policy_version'] == 1.0


def test_add_user_consent_details_without_terms_and_accepted_ai_guidelines():
    response = client.post(
        "/api/user/consent/details",
        json={
            "accepted_privacy_policy": True,
            "accepted_terms": False,
            "accepted_ai_guidelines": False
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Should be agreed to: terms and conditions, ai guidelines"


def test_add_user_consent_details_without_privacy_policy_and_accepted_ai_guidelines():
    response = client.post(
        "/api/user/consent/details",
        json={
            "accepted_privacy_policy": False,
            "accepted_terms": True,
            "accepted_ai_guidelines": False
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Should be agreed to: privacy policy, ai guidelines"


def test_add_user_consent_details_without_both_privacy_policy_and_terms():
    response = client.post(
        "/api/user/consent/details",
        json={
            "accepted_privacy_policy": False,
            "accepted_terms": False,
            "accepted_ai_guidelines": True
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Should be agreed to: privacy policy, terms and conditions"


@responses.activate
def test_augment_questions_without_authenticated():
    response = client.post(
        "/api/augment/questions",
        json={"data": "TESTING TEXTDATA"},
    )

    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["data"] is None
    assert actual["message"] == "Not authenticated"


@responses.activate
def test_augment_questions():
    responses.add(
        responses.POST,
        url="http://localhost:8000/questions",
        match=[responses.matchers.json_params_matcher({"data": "TESTING TEXTDATA"})],
        json={
            "success": True,
            "data": {"question": "How can I help you?"},
            "message": None,
            "error_code": 0,
        },
        status=200,
    )
    response = client.post(
        "/api/augment/questions",
        json={"data": "TESTING TEXTDATA"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == {"question": "How can I help you?"}
    assert Utility.check_empty_string(actual["message"])


def test_api_login_enabled_with_fingerprint(monkeypatch):
    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()
    assert actual["message"] == "fingerprint is required"
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_trusted_device_on_signup_error(monkeypatch):
    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    response = client.post(
        "/api/account/registration",
        json={
            "recaptcha_response": "1234567890",
            "remote_ip": "58.0.127.89",
            "email": "integration1234567@demo.ai",
            "first_name": "Demo",
            "last_name": "User",
            "password": "Welcome@10",
            "confirm_password": "Welcome@10",
            "account": "integration1234567",
            "bot": "integration",
            "fingerprint": None,
            "accepted_privacy_policy": True,
            "accepted_terms": True,
            "accepted_ai_guidelines": True
        },
    )
    actual = response.json()
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "fingerprint is required",
            "type": "value_error",
        }
    ]
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None


def test_add_trusted_device_disabled(monkeypatch):
    monkeypatch.setattr(AccountProcessor, "check_email_confirmation", mock_sync_noop)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)
    response = client.post(
        "/api/account/device/trusted",
        json={"data": "0987654321234567890"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["message"] == "Trusted devices are disabled!"
    assert not response["data"]
    assert response["error_code"] == 422
    assert not response["success"]


def test_add_trusted_device(monkeypatch):
    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
    monkeypatch.setattr(AccountProcessor, "check_email_confirmation", mock_sync_noop)
    monkeypatch.setattr(MailUtility, "trigger_smtp", mock_smtp)

    with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
        mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.post(
            "/api/account/device/trusted",
            json={"data": "0987654321234567890"},
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        ).json()
    assert (
            response["message"]
            == "A confirmation link has been sent to your registered mail address"
    )
    assert not response["data"]
    assert response["error_code"] == 0
    assert response["success"]


def test_add_trusted_device_email_disabled(monkeypatch):
    monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
    with patch("kairon.shared.plugins.ipinfo.IpInfoTracker.execute") as mock_geo:
        mock_geo.return_value = {"City": "Mumbai", "Network": "CATO"}
        response = client.post(
            "/api/account/device/trusted",
            json={"data": "098765432123456456734567"},
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        ).json()
    assert response["message"] == "Trusted device added!"
    assert response["error_code"] == 0
    assert response["success"]


def test_list_trusted_device():
    response = client.get(
        "/api/account/device/trusted",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["trusted_devices"]) == 1
    assert not response["data"]["trusted_devices"][0].get("fingerprint")
    assert response["data"]["trusted_devices"][0]["is_confirmed"]
    assert response["data"]["trusted_devices"][0]["geo_location"] == {
        "City": "Mumbai",
        "Network": "CATO",
    }
    assert response["data"]["trusted_devices"][0]["geo_location"]
    assert response["data"]["trusted_devices"][0]["confirmation_timestamp"]
    assert response["error_code"] == 0
    assert response["success"]


def test_confirm_trusted_device():
    payload = {"mail_id": "integration@demo.ai", "fingerprint": "0987654321234567890"}
    token = Utility.generate_token_payload(payload, minutes_to_expire=120)
    response = client.post(
        "/api/account/device/trusted/confirm", json={"data": token}
    ).json()
    assert response["message"] == "Trusted device added!"
    assert response["error_code"] == 0
    assert response["success"]


def test_list_trusted_device_2():
    response = client.get(
        "/api/account/device/trusted",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["trusted_devices"]) == 2
    assert not response["data"]["trusted_devices"][0].get("fingerprint")
    assert response["data"]["trusted_devices"][0]["is_confirmed"]
    assert response["data"]["trusted_devices"][0]["geo_location"] == {
        "City": "Mumbai",
        "Network": "CATO",
    }
    assert response["data"]["trusted_devices"][0]["geo_location"]
    assert response["data"]["trusted_devices"][0]["confirmation_timestamp"]
    assert response["error_code"] == 0
    assert response["success"]


def test_verify_is_trusted():
    response = client.post(
        "/api/account/device/trusted/verify",
        json={"data": "098765432123456456734567"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["data"] == {"is_trusted_device": True}
    assert response["error_code"] == 0
    assert response["success"]

    response = client.post(
        "/api/account/device/trusted/verify",
        json={"data": "76645657"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["data"] == {"is_trusted_device": False}
    assert response["error_code"] == 0
    assert response["success"]


def test_remove_trusted_device():
    response = client.delete(
        "/api/account/device/trusted/098765432123456456734567",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert not response["data"]
    assert response["error_code"] == 0
    assert response["success"]

    response = client.get(
        "/api/account/device/trusted",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["trusted_devices"]) == 1


def test_api_login_enabled_sso_only(monkeypatch):
    monkeypatch.setitem(Utility.environment["app"], "enable_sso_only", True)
    email = "integration@demo.ai"
    response = client.post(
        "/api/auth/login",
        data={"username": email, "password": "Welcome@10"},
    )
    actual = response.json()
    assert actual["message"] == "This feature is disabled"
    assert not actual["success"]
    assert actual["error_code"] == 422

def test_add_bot():
    response = client.post(
        "/api/account/bot",
        json={"name": "covid-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.headers == {
        "content-length": "100",
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
    response = response.json()
    assert response["message"] == "Bot created"
    assert response["error_code"] == 0
    assert response["success"]
    assert response["data"]["bot_id"]


def test_list_bots():
    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    pytest.bot = response["data"]["account_owned"][0]["_id"]
    assert response["data"]["account_owned"][0]["user"] == "integration@demo.ai"
    assert response["data"]["account_owned"][0]["timestamp"]
    assert response["data"]["account_owned"][0]["name"] == "Hi-Hello"
    assert response["data"]["account_owned"][0]["_id"]
    assert response["data"]["account_owned"][1]["user"] == "integration@demo.ai"
    assert response["data"]["account_owned"][1]["timestamp"]
    assert response["data"]["account_owned"][1]["name"] == "covid-bot"
    assert response["data"]["account_owned"][1]["_id"]
    assert response["data"]["shared"] == []
