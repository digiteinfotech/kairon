from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



@patch("kairon.shared.utils.SMTP", autospec=True)
def test_add_email_action(mock_smtp):
    request = {
        "action_name": "email_config",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test"},
        "from_email": {"value": "from_email", "parameter_type": "slot"},
        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_add_email_action_from_different_parameter_type(mock_smtp):
    request = {
        "action_name": "email_config_with_slot",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test", "parameter_type": "slot"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"

    request = {
        "action_name": "email_config_with_key_vault",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test", "parameter_type": "key_vault"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_add_email_action_from_invalid_parameter_type(mock_smtp):
    request = {
        "action_name": "email_config_invalid_parameter_type",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test", "parameter_type": "intent"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {
        "action_name": "email_config_invalid_parameter_type",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "", "parameter_type": "slot"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {
        "action_name": "email_config_invalid_parameter_type",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "", "parameter_type": "key_vault"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_add_email_action_from_invalid_parameter_type_1(mock_smtp):
    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "to_email", "parameter_type": "intent"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "", "parameter_type": "slot"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'to_email', '__root__'],
                                  'msg': 'Provide name of the slot as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide name of the slot as value")

    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "key_vault"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "", "parameter_type": "value"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'to_email', '__root__'],
                                  'msg': 'Provide list of emails as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide list of emails as value")

    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "intent"},
               "to_email": {"value": "to_email", "parameter_type": "slot"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "", "parameter_type": "slot"},
               "to_email": {"value": ["test@demo.com"], "parameter_type": "value"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'from_email', '__root__'],
                                  'msg': 'Provide name of the slot as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide name of the slot as value")

    request = {"action_name": "email_config_invalid_parameter_type",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "key_vault"},
               "from_email": {"value": "", "parameter_type": "value"},
               "to_email": {"value": ["test@demo.com"], "parameter_type": "value"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Invalid From or To email address'


def test_list_email_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/email",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 3
    [action.pop("_id") for action in actual["data"]]
    assert actual["data"] == [
        {
            "action_name": "email_config",
            "smtp_url": "test.test.com",
            "smtp_port": 25,
            'dispatch_bot_response': True,
            "smtp_password": {
                "_cls": "CustomActionRequestParameters",
                "key": "smtp_password",
                "encrypt": False,
                "value": "test",
                "parameter_type": "value",
            },
           'from_email': {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                          'value': 'from_email', 'parameter_type': 'slot'},
           'subject': 'Test Subject',
           'to_email': {'_cls': 'CustomActionParameters', 'encrypt': False,
                        'value': ['test@test.com', 'test1@test.com'], 'parameter_type': 'value'},
           'response': 'Test Response',
            'tls': False
        },
        {
            "action_name": "email_config_with_slot",
            "smtp_url": "test.test.com",
            "smtp_port": 25,
            'dispatch_bot_response': True,
            "smtp_password": {
                "_cls": "CustomActionRequestParameters",
                "key": "smtp_password",
                "encrypt": False,
                "value": "test",
                "parameter_type": "slot",
            },
           'from_email': {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                          'value': 'test@demo.com', 'parameter_type': 'value'},
           'subject': 'Test Subject',
           'to_email': {'_cls': 'CustomActionParameters', 'encrypt': False, 'value': 'to_email',
                        'parameter_type': 'slot'},
            'response': 'Test Response',
            "tls": False,
        },
        {
            "action_name": "email_config_with_key_vault",
            "smtp_url": "test.test.com",
            "smtp_port": 25,
            'dispatch_bot_response': True,
            "smtp_password": {
                "_cls": "CustomActionRequestParameters",
                "key": "smtp_password",
                "encrypt": False,
                "value": "test",
                "parameter_type": "key_vault",
            },
            'from_email': {'_cls': 'CustomActionRequestParameters', 'encrypt': False,
                           'value': 'test@demo.com', 'parameter_type': 'value'},
            'subject': 'Test Subject',
            'to_email': {'_cls': 'CustomActionParameters', 'encrypt': False, 'value': 'to_email',
                         'parameter_type': 'slot'},
            'response': 'Test Response',
            "tls": False,
        },
    ]


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_edit_email_action(mock_smtp):
    request = {
        "action_name": "email_config",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_edit_email_action_different_parameter_type(mock_smtp):
    request = {
        "action_name": "email_config_with_slot",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test", "parameter_type": "slot"},
        "from_email": {"value": "from_email", "parameter_type": "slot"},
        "to_email": {"value": ["test@test.com", "test1@test.com"], "parameter_type": "value"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"

    request = {
        "action_name": "email_config_with_key_vault",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test", "parameter_type": "key_vault"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_edit_email_action_invalid_parameter_type(mock_smtp):
    request = {
        "action_name": "email_config_with_slot",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {'value': "test", "parameter_type": "slot"},
        "from_email": {"value": "test@demo.com", "parameter_type": "intent"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_edit_email_action_invalid_parameter_type_1(mock_smtp):
    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "to_email", "parameter_type": "intent"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "", "parameter_type": "slot"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'to_email', '__root__'],
                                  'msg': 'Provide name of the slot as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide name of the slot as value")

    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "key_vault"},
               "from_email": {"value": "test@demo.com", "parameter_type": "value"},
               "to_email": {"value": "test@demo.com", "parameter_type": "value"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'to_email', '__root__'],
                                  'msg': 'Provide list of emails as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide list of emails as value")

    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "test@demo.com", "parameter_type": "intent"},
               "to_email": {"value": "to_email", "parameter_type": "slot"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "slot"},
               "from_email": {"value": "", "parameter_type": "slot"},
               "to_email": {"value": ["test@demo.com"], "parameter_type": "value"},
               "subject": "Test Subject",
               "response": "Test Response",
               "tls": False
               }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'from_email', '__root__'],
                                  'msg': 'Provide name of the slot as value', 'type': 'value_error'}]
    assert str(actual['message']).__contains__("Provide name of the slot as value")

    request = {"action_name": "email_config_with_slot",
               "smtp_url": "test.test.com",
               "smtp_port": 25,
               "smtp_userid": None,
               "smtp_password": {'value': "test", "parameter_type": "key_vault"},
               "from_email": {"value": "", "parameter_type": "value"},
               "to_email": {"value": ["test@demo.com"], "parameter_type": "value"},
               "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Invalid From or To email address'


@patch("kairon.shared.utils.SMTP", autospec=True)
def test_edit_email_action_does_not_exists(mock_smtp):
    request = {
        "action_name": "email_config1",
        "smtp_url": "test.test.com",
        "smtp_port": 25,
        "smtp_userid": None,
        "smtp_password": {"value": "test"},
        "from_email": {"value": "test@demo.com", "parameter_type": "value"},
        "to_email": {"value": "to_email", "parameter_type": "slot"},
        "subject": "Test Subject",
        "response": "Test Response",
        "tls": False,
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/email",
        json=request,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "email_config1" not found'


def test_delete_email_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/non_existant",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "non_existant" not found'


def test_delete_email_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/email_config",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_list_google_search_action_one():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1


def test_add_google_search_action():
    action = {
        "name": "google_custom_search",
        "api_key": {"value": "12345678"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_google_search_exists():
    action = {
        "name": "google_custom_search",
        "api_key": {"value": "12345678"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"


def test_add_google_search_invalid_parameters():
    action = {
        "name": "google_custom_search",
        "api_key": {"value": "12345678"},
        "search_engine_id": "asdfg:123456",
        "num_results": 0,
        "failure_response": "I have failed to process your request",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "num_results"],
            "msg": "num_results must be greater than or equal to 1!",
            "type": "value_error",
        }
    ]


def test_add_google_search_different_parameter_types():
    action = {
        "name": "google_custom_search_slot",
        "api_key": {"value": "12345678", "parameter_type": "slot"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"

    action = {
        "name": "google_custom_search_key_vault",
        "api_key": {"value": "12345678", "parameter_type": "key_vault"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_google_search_invalid_parameter_types():
    action = {
        "name": "google_custom_search_slot",
        "api_key": {"value": "12345678", "parameter_type": "chat_log"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_edit_google_search_action_not_exists():
    action = {
        "name": "custom_search",
        "api_key": {"value": "12345678"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"] == 'Google search action with name "custom_search" not found'
    )


def test_edit_google_search_action():
    action = {
        "name": "google_custom_search",
        "api_key": {"value": "1234567889"},
        "search_engine_id": "asdfg:12345689",
        "failure_response": "Failed to perform search",
        "website": "https://nimblework.com",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_edit_google_search_action_different_parameter_types():
    action = {
        "name": "google_custom_search_slot",
        "api_key": {"value": "1234567889", "parameter_type": "key_vault"},
        "search_engine_id": "asdfg:12345689",
        "failure_response": "Failed to perform search",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"

    action = {
        "name": "google_custom_search_key_vault",
        "api_key": {"value": "1234567889", "parameter_type": "slot"},
        "search_engine_id": "asdfg:12345689",
        "failure_response": "Failed to perform search",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_edit_google_search_action_invalid_parameter_type():
    action = {
        "name": "google_custom_search_key_vault",
        "api_key": {"value": "12345678", "parameter_type": "user_message"},
        "search_engine_id": "asdfg:123456",
        "failure_response": "I have failed to process your request",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_list_google_search_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/googlesearch",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 4
    actual["data"][0].pop("_id")
    assert actual["data"][1]["name"] == "google_custom_search"
    assert actual["data"][1]["api_key"] == {
        "_cls": "CustomActionRequestParameters",
        "encrypt": False,
        "key": "api_key",
        "parameter_type": "value",
        "value": "1234567889",
    }
    assert actual["data"][1]["search_engine_id"] == "asdfg:12345689"
    assert actual["data"][1]["failure_response"] == "Failed to perform search"
    assert actual["data"][1]["website"] == "https://nimblework.com"
    assert actual["data"][1]["num_results"] == 1
    assert actual["data"][1]["dispatch_response"]
    assert not actual["data"][1].get("set_slot")


def test_delete_google_search_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/google_custom_search",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_delete_google_search_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/google_custom_search",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "google_custom_search" not found'


def test_add_web_search_action():
    action = {
        "name": "public_custom_search",
        "dispatch_response": False,
        "set_slot": "public_search_result",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_web_search_exists():
    action = {
        "name": "public_custom_search",
        "dispatch_response": False,
        "set_slot": "public_search_result",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"


def test_add_web_search_invalid_parameters_top_n():
    action = {
        "name": "public_custom_search_two",
        "topn": 0,
        "dispatch_response": False,
        "set_slot": "public_search_result",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "topn"],
            "msg": "topn must be greater than or equal to 1!",
            "type": "value_error",
        }
    ]


def test_add_web_search_invalid_parameters_name():
    action = {
        "name": "",
        "topn": 1,
        "dispatch_response": False,
        "set_slot": "public_search_result",
        "failure_response": "I have failed to process your request",
        "website": "https://www.google.com",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "name"], "msg": "name is required", "type": "value_error"}
    ]


def test_edit_web_search_action_not_exists():
    action = {
        "name": "custom_search",
        "failure_response": "I have failed to process your request",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"] == 'Public search action with name "custom_search" not found'
    )


def test_edit_web_search_action():
    action = {
        "name": "public_custom_search",
        "dispatch_response": False,
        "set_slot": "public_search_result",
        "failure_response": "Failed to perform public search",
        "website": "https://nimblework.com",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/websearch",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_list_web_search_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/websearch",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1
    actual["data"][0].pop("_id")
    assert actual["data"][0]["name"] == "public_custom_search"
    assert actual["data"][0]["failure_response"] == "Failed to perform public search"
    assert actual["data"][0]["website"] == "https://nimblework.com"
    assert actual["data"][0]["topn"] == 1
    assert not actual["data"][0]["dispatch_response"]
    assert actual["data"][0].get("set_slot")


def test_delete_web_search_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/public_custom_search",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_delete_web_search_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/public_custom_search",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "public_custom_search" not found'


def test_list_hubspot_forms_action_no_actions():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 0


def test_add_hubspot_forms_action():
    action = {
        "name": "action_hubspot_forms",
        "portal_id": "12345678",
        "form_guid": "asdfg:123456",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "slot"},
            {"key": "firstname", "value": "firstname_slot", "parameter_type": "slot"},
        ],
        "response": "Form submitted",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added"


def test_add_hubspot_forms_action_invalid_param_type():
    action = {
        "name": "action_hubspot_forms",
        "portal_id": "12345678",
        "form_guid": "asdfg:123456",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "header"},
            {"key": "firstname", "value": "firstname_slot", "parameter_type": "slot"},
        ],
        "response": "Form submitted",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'fields', 0, 'parameter_type'],
                                  'msg': "value is not a valid enumeration member; permitted: 'value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log', 'key_vault'",
                                  'type': 'type_error.enum', 'ctx': {
            'enum_values': ['value', 'slot', 'sender_id', 'user_message', 'latest_message', 'intent', 'chat_log',
                            'key_vault']}}]


def test_add_hubspot_forms_exists():
    action = {
        "name": "action_hubspot_forms",
        "portal_id": "12345678",
        "form_guid": "asdfg:123456",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "slot"},
            {"key": "firstname", "value": "firstname_slot", "parameter_type": "slot"},
        ],
        "response": "Form submitted",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"


def test_edit_hubspot_forms_action_not_exists():
    action = {
        "name": "hubspot_forms_action",
        "portal_id": "12345678",
        "form_guid": "asdfg:123456",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "slot"},
            {"key": "firstname", "value": "firstname_slot", "parameter_type": "slot"},
        ],
        "response": "Form submitted",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == 'Action with name "hubspot_forms_action" not found'


def test_edit_hubspot_forms_action():
    action = {
        "name": "action_hubspot_forms",
        "portal_id": "123456785787",
        "form_guid": "asdfg:12345678787",
        "fields": [
            {"key": "email", "value": "email_slot", "parameter_type": "slot"},
            {"key": "fullname", "value": "fullname_slot", "parameter_type": "slot"},
            {"key": "company", "value": "digite", "parameter_type": "value"},
            {"key": "phone", "value": "phone_slot", "parameter_type": "slot"},
        ],
        "response": "Hubspot Form submitted",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated"


def test_list_hubspot_forms_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/hubspot/forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 1
    actual["data"][0].pop("_id")
    assert actual["data"][0]["name"] == "action_hubspot_forms"
    assert actual["data"][0]["portal_id"] == "123456785787"
    assert actual["data"][0]["form_guid"] == "asdfg:12345678787"
    assert actual["data"][0]["fields"] == [
        {
            "_cls": "HttpActionRequestBody",
            "key": "email",
            "value": "email_slot",
            "parameter_type": "slot",
            "encrypt": False,
        },
        {
            "_cls": "HttpActionRequestBody",
            "key": "fullname",
            "value": "fullname_slot",
            "parameter_type": "slot",
            "encrypt": False,
        },
        {
            "_cls": "HttpActionRequestBody",
            "key": "company",
            "value": "digite",
            "parameter_type": "value",
            "encrypt": False,
        },
        {
            "_cls": "HttpActionRequestBody",
            "key": "phone",
            "value": "phone_slot",
            "parameter_type": "slot",
            "encrypt": False,
        },
    ]
    assert actual["data"][0]["response"] == "Hubspot Form submitted"


def test_delete_hubspot_forms_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/action_hubspot_forms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_get_kairon_two_stage_fallback_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []
    assert not actual["message"]


def test_add_kairon_two_stage_fallback_action_error():
    action = {"trigger_rules": []}
    response = client.post(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "One of text_recommendations or trigger_rules should be defined",
            "type": "value_error",
        }
    ]

    action = {
        "text_recommendations": {"count": -1},
        "trigger_rules": [{"text": "hi", "payload": "greet"}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "count cannot be negative",
            "type": "value_error",
        }
    ]


def test_edit_kairon_two_stage_fallback_action_not_exists():
    action = {
        "trigger_rules": [{"text": "Hi", "payload": "kairon_two_stage_fallback_action"}]
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"] == f'Action with name "{KAIRON_TWO_STAGE_FALLBACK}" not found'
    )


def test_add_kairon_two_stage_fallback_action():
    action = {
        "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                            " Or else please rephrase your question.",
        "text_recommendations": {"count": 0, "use_intent_ranking": True},
        "trigger_rules": [{"text": "Hi", "payload": "greet"}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"


def test_add_kairon_two_stage_fallback_action_exists():
    action = {"trigger_rules": [{"text": "Hi", "payload": "greet"}]}
    response = client.post(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"


def test_edit_kairon_two_stage_fallback_action_action():
    action = {
        "fallback_message": "I could not understand you! Did you mean any of the suggestions below?"
                            " Or else please rephrase your question.",
        "text_recommendations": {"count": 4},
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        json=action,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated!"


def test_get_kairon_two_stage_fallback_action_1():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"][0].get("timestamp") is None
    actual["data"][0].pop("_id")
    assert actual["data"] == [
        {
            "name": "kairon_two_stage_fallback",
            "text_recommendations": {"count": 4, "use_intent_ranking": False},
            "trigger_rules": [],
            "fallback_message": "I could not understand you! Did you mean any of the suggestions"
                                " below? Or else please rephrase your question.",
        }
    ]


def test_delete_kairon_two_stage_fallback_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/{KAIRON_TWO_STAGE_FALLBACK}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_get_kairon_two_stage_fallback_action_2():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/fallback/two_stage",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == []
