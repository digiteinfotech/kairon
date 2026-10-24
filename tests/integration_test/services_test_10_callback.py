from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training





def test_callback_config_add_syntax_error():
    request_body = {
        "name": "callback_1",
        "pyscript_code": "bot_response = Hello World!'",
        "validation_secret": "string",
        "execution_mode": "async"
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert not actual['success']
    assert actual['error_code'] == 422
    assert actual['message'] == 'source code syntax error: unterminated string literal (detected at line 1)'

def test_callback_config_add():
    request_body = {
        "name": "callback_1",
        "pyscript_code": "bot_response = 'Hello World!'",
        "validation_secret": "string",
        "execution_mode": "async"
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    
    actual = response.json()
    actual['data'].pop('validation_secret')
    actual['data'].pop('bot')
    assert actual == {'success': True, 'message': 'Callback added successfully!',
                      'data': {'name': 'callback_1',
                               'pyscript_code': "bot_response = 'Hello World!'",
                               'response_type': 'kairon_json',
                                'expire_in': 0,
                               'shorten_token': False,
                               'standalone': False,
                               'standalone_id_path': '',
                               'redirect_enabled': False,
                               "redirect": {},
                      'execution_mode': 'async' }, 'error_code': 0}


def test_callback_config_add_standalone():
    request_body = {
        "name": "callback_2",
        "pyscript_code": "bot_response = 'Hello World!'",
        "validation_secret": "string",
        "execution_mode": "async",
        "standalone": True,
        "standalone_id_path": "data.id"
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    actual['data'].pop('validation_secret')
    actual['data'].pop('bot')
    assert actual == {'success': True, 'message': 'Callback added successfully!',
                      'data': {'name': 'callback_2',
                               'pyscript_code': "bot_response = 'Hello World!'",
                               'response_type': 'kairon_json',
                               'expire_in': 0,
                               'shorten_token': False,
                               'standalone': True,
                               'standalone_id_path': 'data.id',
                               'redirect_enabled': False,
                               "redirect": {},
                               'execution_mode': 'async'}, 'error_code': 0}


def test_callback_get_standalone_url():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/callback_standalone_url/callback_2",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.status_code == 200
    actual = response.json()
    assert actual['success']
    assert actual['error_code'] == 0
    assert isinstance(actual['data'], str)
    assert '/callback/s/' in actual['data']
    

def test_callback_config_add_standalone_fail_no_path():
    request_body = {
        "name": "callback_3",
        "pyscript_code": "bot_response = 'Hello World!'",
        "validation_secret": "string",
        "execution_mode": "async",
        "standalone": True
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual == {'success': False, 'message': 'Standalone id path is required!',
                      'data': None, 'error_code': 422}


def test_callback_config_add_standalone_with_redirect():
    request_body = {
        "name": "callback_redirect_standalone",
        "pyscript_code": "bot_response = 'Hello World!'",
        "validation_secret": "string",
        "execution_mode": "sync",
        "standalone": True,
        "standalone_id_path": "data.id",
        'redirect_enabled': True,
        "redirect": {
            "type": "slot",
            "value": "redirect_url"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual == {
        "success": False,
        "message": "Redirect is not supported for standalone callbacks!",
        "data": None,
        "error_code": 422
    }


def test_callback_config_add_async_with_redirect():
    request_body = {
        "name": "callback_redirect_async",
        "pyscript_code": "bot_response = 'Hello World!'",
        "validation_secret": "string",
        "execution_mode": "async",
        'redirect_enabled': True,
        "redirect": {
            "type": "slot",
            "value": "redirect_url"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual == {
        "success": False,
        "message": "Redirect is not supported for async callbacks!",
        "data": None,
        "error_code": 422
    }


def test_callback_config_add_invalid_redirect_type():
    request_body = {
        "name": "callback_invalid_redirect",
        "pyscript_code": "bot_response = 'Hello World!'",
        "validation_secret": "string",
        "execution_mode": "sync",
        'redirect_enabled': True,
        "redirect": {
            "type": "invalid_type",
            "value": "redirect_url"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual == {
        "success": False,
        "message": "Invalid redirect type!",
        "data": None,
        "error_code": 422
    }


def test_callback_config_add_redirect_without_value():
    request_body = {
        "name": "callback_redirect_no_value",
        "pyscript_code": "bot_response = 'Hello World!'",
        "validation_secret": "string",
        "execution_mode": "sync",
        'redirect_enabled': True,
        "redirect": {
            "type": "slot"
        }
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual == {
        "success": False,
        "message": "Only redirect_url slot is supported for redirect!",
        "data": None,
        "error_code": 422
    }


def test_callback_config_edit_syntex_error():
    request_body = {
        "name": "callback_1",
        "pyscript_code": "bot_response is if = 'Hello World2!'",
        "validation_secret": "string",
        "execution_mode": "async"
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert not actual['success']
    assert actual['error_code'] == 422
    assert actual['message'] == 'source code syntax error: invalid syntax'

def test_callback_config_edit():
    request_body = {
        "name": "callback_1",
        "pyscript_code": "bot_response = 'Hello World2!'",
        "validation_secret": "string",
        "execution_mode": "async"
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    actual['data'].pop('validation_secret')
    actual['data'].pop('bot')
    assert actual == {'success': True, 'message': 'Callback updated successfully!',
                      'data': {'name': 'callback_1', 'pyscript_code': "bot_response = 'Hello World2!'",
                               'response_type': 'kairon_json',
                               'expire_in': 0,
                               'shorten_token': False,
                               'standalone': False,
                               'standalone_id_path': '',
                               'redirect_enabled': False,
                               "redirect": {},
                               'execution_mode': 'async'}, 'error_code': 0}


def test_callback_config_get():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/callback_list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['success']
    assert actual['error_code'] == 0
    assert len(actual['data']) == 2
    assert 'callback_1' in actual['data']
    assert 'callback_2' in actual['data']

def test_callback_config_edit_partial_update_with_redirect_enabled():
    request_body = {
        "name": "callback_1",
        "pyscript_code": "bot_response = 'Updated!'",
        "validation_secret": "string",
        "execution_mode": "async",
        "redirect_enabled": True,
        "redirect": {
            "type": "value",
            "value": "https://example.com"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['success'] is False
    assert actual['error_code'] == 422
    assert actual['message'] == "Redirect is not supported for async callbacks!"
    assert actual['data'] is None


def test_callback_config_edit_disable_redirect():
    request_body = {
        "name": "callback_1",
        "pyscript_code": "bot_response = 'Hello World2!'",
        "validation_secret": "string",
        "execution_mode": "async",
        "redirect_enabled": False,
        "redirect": {}
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual['success']
    assert actual['data']['redirect_enabled'] is False
    assert actual['data']['redirect'] == {}


def test_callback_config_edit_redirect_while_enabled():
    request_body = {
        "name": "callback_1",
        "pyscript_code": "bot_response = 'Hello World2!'",
        "validation_secret": "string",
        "execution_mode": "sync",
        "redirect_enabled": True,
        "redirect": {
            "type": "value",
            "value": "https://example.com"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual['success']
    assert actual['data']['redirect_enabled'] is True
    assert actual['data']['redirect'] == {
        "type": "value",
        "value": "https://example.com"
    }


def test_callback_config_edit_sync_to_async_with_redirect_enabled():
    request_body = {
        "name": "callback_1",
        "pyscript_code": "bot_response = 'Hello World2!'",
        "validation_secret": "string",
        "execution_mode": "async",
        "redirect_enabled": True,
        "redirect": {
            "type": "value",
            "value": "https://example.com"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert not actual['success']
    assert actual['error_code'] == 422
    assert "redirect" in actual['message'].lower()


def test_callback_config_edit_standalone_with_redirect_enabled():
    request_body = {
        "name": "callback_1",
        "pyscript_code": "bot_response = 'Hello World2!'",
        "validation_secret": "string",
        "execution_mode": "sync",
        "standalone": True,
        "redirect_enabled": True,
        "redirect": {
            "type": "value",
            "value": "https://example.com"
        }
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert not actual['success']
    assert actual['error_code'] == 422
    assert "redirect" in actual['message'].lower()


def test_callback_single_config_get():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/callback/callback_1",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['success']
    assert actual['error_code'] == 0
    assert actual['data']['name'] == 'callback_1'
    assert actual['data']['pyscript_code'] == "bot_response = 'Hello World2!'"

def test_callback_config_delete():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/callback/callback_2",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual == {'success': True, 'message': 'Callback deleted successfully!', 'data': None, 'error_code': 0}


def test_callback_action_add_fail_no_callback_config():
    request_body = {
        "name": "callback_action1",
        "callback_name": "callback_12",
        "dynamic_url_slot_name": "string",
        "metadata_list": [],
        "bot_response": "string",
        "dispatch_bot_response": True,
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback/action",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual == {'success': False, 'message': "Callback with name 'callback_12' not found!", 'data': None, 'error_code': 422}



def test_callback_action_add():
    request_body = {
        "name": "callback_1",
        "pyscript_code": "bot_response = 'Hello World!'",
        "validation_secret": "string",
        "execution_mode": "async"
    }

    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    request_body = {
            "name": "callback_action1",
            "callback_name": "callback_1",
            "dynamic_url_slot_name": "string",
            "metadata_list": [],
            "bot_response": "string",
            "dispatch_bot_response": True,
    }
    
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/callback/action",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    
    actual = response.json()
    assert actual['success']
    assert actual['message'] == 'Callback action added successfully!'
    data = actual['data']
    assert data['name'] == 'callback_action1'
    assert data['callback_name'] == 'callback_1'


def test_callback_action_update():
    request_body = {
        "name": "callback_action1",
        "callback_name": "callback_1",
        "dynamic_url_slot_name": "new_slot_name",
        "metadata_list": [],
        "bot_response": "string",
        "dispatch_bot_response": True,
    }

    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/callback/action",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['success']
    assert actual['message'] == 'Callback action updated successfully!'


def test_callback_action_get():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/callback/action/callback_action1",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['success']
    assert actual['error_code'] == 0
    assert actual['data']['name'] == 'callback_action1'
    assert actual['data']['callback_name'] == 'callback_1'
    assert actual['data']['dynamic_url_slot_name'] == 'new_slot_name'


def test_callback_action_get_all():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/callback_actions",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual['success']
    assert actual['error_code'] == 0
    assert isinstance(actual['data'], list)
    assert len(actual['data']) == 1
    assert actual['data'][0]['name'] == 'callback_action1'

def test_callback_get_logs():
    new_log = CallbackLog(
        bot=pytest.bot,
        callback_name="callback_action1",
        channel="channel",
        identifier="identifier",
        pyscript_code="pyscript_code",
        sender_id="sender_id",
        log="callback_log",
        request_data={},
        metadata={},
        callback_url="callback_url",
        callback_source="callback_source",
        status=CallbackRecordStatusType.FAILED.value,
        timestamp=utc_now()).save()

    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/callback_logs",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual['success']
    assert actual['error_code'] == 0
    assert isinstance(actual['data']['logs'], list)
    assert len(actual['data']['logs']) == 1
    assert actual['data']['total_number_of_pages'] == 1

    response = client.get(
        url=f"/api/bot/{pytest.bot}/logs/callback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    assert actual['success']
    assert actual['error_code'] == 0
    assert isinstance(actual['data']['logs'], list)
    assert len(actual['data']['logs']) == 1

    from_date = utc_now().date() - timedelta(days=1)
    to_date = utc_now().date() + timedelta(days=1)

    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/callback/search?from_date={from_date}&to_date={to_date}",
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"},
    )

    response_json = search_response.json()
    print("callback", response_json)
    assert response_json["success"] is True
    assert response_json["error_code"] == 0

    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)
    assert data['total'] == 1

def test_callback_action_delete():
    response = client.delete(
        url=f"/api/bot/{pytest.bot}/action/callback/action/callback_action1",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual == {'success': True, 'message': 'Callback action deleted successfully!', 'data': None, 'error_code': 0}



def test_add_pyscript_action_empty_name():
    script = "bot_response='hello world'"
    request_body = {
        "name": "",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {"loc": ["body", "name"], "msg": "name is required", "type": "value_error"}
    ]
    assert not actual["success"]


def test_add_pyscript_action_empty_source_code():
    request_body = {
        "name": "test_add_pyscript_action_empty_source_code",
        "source_code": "",
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "source_code"],
            "msg": "source_code is required",
            "type": "value_error",
        }
    ]
    assert not actual["success"]


def test_add_pyscript_action_with_utter():
    script = "bot_response='hello world'"
    request_body = {
        "name": "utter_pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Action name cannot start with utter_"
    assert not actual["success"]


def test_add_pyscript_action_syntex_error():
    script = """
    data = [1, 2, 3, 4, 5]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    request_body = {
        "name": "test_add_pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "source code syntax error: unexpected indent"
    assert not actual["success"]

def test_add_pyscript_action():
    script= "bot_response='hello world'"
    request_body = {
        "name": "test_add_pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]

def test_add_pyscript_action_name_already_exist():
    script= "bot_response='hello world'"
    request_body = {
        "name": "test_add_pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"
    assert not actual["success"]


def test_add_pyscript_action_case_insensitivity():
    script= "bot_response='hello world'"
    request_body = {
        "name": "TEST_ADD_PYSCRIPT_ACTION_CASE_INSENSITIVITY",
        "source_code": script,
        "dispatch_response": True,
        "set_slots": [
            {"name": "data", "value": "${data.data}", "evaluation_type": "expression"}
        ],
    }
    response = client.post(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"
    assert actual["success"]


def test_update_pyscript_action_does_not_exist():
    script= "bot_response='hello world'"
    request_body = {
        "name": "test_update_pyscript_action",
        "source_code": script,
        "dispatch_response": False,
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert (
            actual["message"] == 'Action with name "test_update_pyscript_action" not found'
    )
    assert not actual["success"]


def test_update_pyscript_action_syntex_error():
    script = """
    data = [1, 2, 3, 4, 5, 6, 7]
    total = 0
    for i in data:
        total += i
    print(total)
    """
    request_body = {
        "name": "test_add_pyscript_action",
        "source_code": script,
        "dispatch_response": True,
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "source code syntax error: unexpected indent"
    assert not actual["success"]


def test_update_pyscript_action():
    script = "bot_response='hello world'"
    request_body = {
        "name": "test_add_pyscript_action",
        "source_code": script,
        "dispatch_response": True,
    }
    response = client.put(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        json=request_body,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated!"
    assert actual["success"]

def test_list_pyscript_actions():
    script1 = "bot_response='hello world'"
    script2 = "bot_response='hello world'"
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]) == 2
    assert actual["data"][0]["name"] == "test_add_pyscript_action"
    assert actual["data"][0]["source_code"] == script1
    assert actual["data"][0]["dispatch_response"]
    assert actual["data"][1]["name"] == "test_add_pyscript_action_case_insensitivity"
    assert actual["data"][1]["source_code"] == script2
    assert actual["data"][1]["dispatch_response"]


def test_delete_pyscript_action_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/test_delete_pyscript_action_not_exists",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == 'Action with name "test_delete_pyscript_action_not_exists" not found'
    )


def test_delete_pyscript_action():
    response = client.delete(
        f"/api/bot/{pytest.bot}/action/test_add_pyscript_action",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action deleted"


def test_list_pyscript_actions_after_action_deleted():
    script2 = "bot_response='hello world'"
    response = client.get(
        url=f"/api/bot/{pytest.bot}/action/pyscript",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]
    assert len(actual["data"]) == 1
    assert actual["data"][0]["name"] == "test_add_pyscript_action_case_insensitivity"
    assert actual["data"][0]["source_code"] == script2
    assert actual["data"][0]["dispatch_response"]
