import os
from unittest.mock import patch

from deepdiff import DeepDiff
from mongoengine import connect

from kairon import Utility
from kairon.shared.actions.data_objects import Actions, HttpActionConfig, PyscriptActionConfig, LiveAgentActionConfig
from kairon.shared.actions.models import ActionType, ActionParameterType, DbActionOperationType
from kairon.shared.admin.data_objects import LLMSecret
from kairon.shared.callback.data_objects import CallbackConfig
from kairon.shared.data.data_validation import DataValidation

os.environ["system_file"] = "./tests/testing_data/system.yaml"
Utility.load_environment()
Utility.load_system_metadata()

import pytest

from kairon.shared.data.action_serializer import ActionSerializer
from kairon.shared.data.data_objects import *


bot_id_download = "66fb95f3629a37edd68e0cbc"
user_download = "spandan.mondal@nimblework.com"

valid_http_action_config = {
    "action_name": "a_api_action",
    "http_url": "https://jsonplaceholder.typicode.com/posts/1",
    "request_method": "GET",
    "content_type": "json",
    "params_list": [],
    "headers": [],
    "response": {
        "value": "${data}",
        "dispatch": True,
        "evaluation_type": "expression",
        "dispatch_type": "text"
    },
    "set_slots": [],
    "bot": bot_id_download,
    "user": user_download,
    "status": True
}

valid_http_action_config2 = {
    "action_name": "a_api_action2",
    "http_url": "https://jsonplaceholder.typicode.com/posts/2",
    "request_method": "GET",
    "content_type": "json",
    "params_list": [],
    "headers": [],
    "response": {
        "value": "${data}",
        "dispatch": True,
        "evaluation_type": "expression",
        "dispatch_type": "text"
    },
    "set_slots": [],
    "bot": bot_id_download,
    "user": user_download,
    "status": True
}

invalid_http_action_config_field_missing = {
    "action_name": "a_api_action_field_missing",
    "request_method": "GET",
    "params_list": [],
    "headers": [],
    "response": {
        "value": "${data}",
        "dispatch": True,
        "evaluation_type": "expression",
        "dispatch_type": "text"
    },
    "set_slots": [],
    "bot": bot_id_download,
    "user": user_download,
    "status": True
}

valid_pyscript_action_config = {
    "name": "a_pyscript_action",
    "source_code": "bot_response = \"hello world form pyscript!!\"",
    "dispatch_response": True,
    "bot": bot_id_download,
    "user": user_download,
    "status": True
}

invalid_pyscript_action_config_field_missing = {
    "name": "a_pyscript_action_field_missing",
    "dispatch_response": True,
    "bot": bot_id_download,
    "user": user_download,
    "status": True
}

invalid_pyscript_action_config_compiler_error = {
    "name": "a_pyscript_action",
    "source_code": "if for:\n bot_response = \"hello world form pyscript!!\"",
    "dispatch_response": True,
    "bot": bot_id_download,
    "user": user_download,
    "status": True
}

action_no_name = {
    "source_code": "bot_response = \"hello world form pyscript!!\"",
    "dispatch_response": True,
    "bot": bot_id_download,
    "user": user_download
}

valid_callback_config = {
    "name": "cb1",
    "pyscript_code": "bot_response = f\"callback data: {metadata}, {req}\"",
    "validation_secret": "gAAAAABm-mHUvuS1_vBsGRd5RKLX4Vek5kG05Y8iIUPB788yC75Y15HPaxIdDOnlE4i_HlLV046f2owJSb8CR2YoXXBc8hrnxoft3qdJ7qcdDH_Br5QJIi8ABp1KETumBbYgjKCWTdXr",
    "execution_mode": "async",
    "expire_in": 0,
    "shorten_token": False,
    "token_hash": "019247a8285a77d4bb6581d78379d6c6",
    "standalone": False,
    "standalone_id_path": "",
    "bot": bot_id_download
}

invalid_callback_config_missing_field = {
    "name": "cb1",
    "standalone": False,
    "standalone_id_path": "",
    "bot": bot_id_download
}


@pytest.fixture(autouse=True, scope='class')
def setup():
    connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))


def test_get_item_name():
    assert ActionSerializer.get_item_name(valid_http_action_config) == "a_api_action"
    assert ActionSerializer.get_item_name(valid_pyscript_action_config) == "a_pyscript_action"
    with pytest.raises(Exception):
        ActionSerializer.get_item_name(action_no_name)
    assert ActionSerializer.get_item_name(valid_http_action_config, False) == "a_api_action"
    assert not ActionSerializer.get_item_name(action_no_name, False)


def test_get_collection_infos():
    action_info, other_collection_info = ActionSerializer.get_collection_infos()

    assert isinstance(action_info, dict)
    assert isinstance(other_collection_info, dict)

    action_info_keys = action_info.keys()
    other_collection_info_keys = other_collection_info.keys()
    test_action_keys = ['http_action', 'two_stage_fallback', 'email_action', 'zendesk_action', 'jira_action', 'form_validation_action', 'slot_set_action', 'google_search_action', 'pipedrive_leads_action', 'prompt_action', 'web_search_action', 'razorpay_action', 'pyscript_action', 'database_action', 'live_agent_action', 'callback_action', 'schedule_action', 'parallel_action']
    test_other_collection_keys = ['callbackconfig']

    for k in test_action_keys:
        assert k in action_info_keys
        assert action_info[k].get('db_model') is not None

    for k in test_other_collection_keys:
        assert k in other_collection_info_keys
        assert other_collection_info[k].get('db_model') is not None

    assert len(action_info_keys) == 18
    assert len(other_collection_info_keys) == 1


def test_is_action():
    assert ActionSerializer.is_action(ActionType.http_action.value) == True
    assert ActionSerializer.is_action(ActionType.two_stage_fallback.value) == True
    assert ActionSerializer.is_action("callbackconfig") == False
    assert ActionSerializer.is_action(None) == False


def test_data_validator_validate_http_action():
    bot = "my_test_bot"
    action_param_types = {param.value for param in ActionParameterType}

    # Test case 1: Valid params_list and headers
    data = {
        "params_list": [{"key": "param1", "parameter_type": list(action_param_types)[0], "value": "value1"}],
        "headers": [{"key": "header1", "parameter_type": list(action_param_types)[0], "value": "value1"}],
        "action_name": "http_action"
    }
    assert not DataValidation.validate_http_action(bot, data)

    # Test case 2: Invalid params_list (missing key)
    data["params_list"][0]["key"] = None
    assert DataValidation.validate_http_action(bot, data) == ['Invalid params_list for http action: http_action']

    # Test case 3: Invalid headers (missing key)
    data["params_list"][0]["key"] = "param1"
    data["headers"][0]["key"] = None
    assert DataValidation.validate_http_action(bot, data) == ['Invalid headers for http action: http_action']

    # Test case 4: Invalid params_list (invalid parameter_type)
    data["headers"][0]["key"] = "header1"
    data["params_list"][0]["parameter_type"] = "invalid_type"
    assert DataValidation.validate_http_action(bot, data) == ['Invalid params_list for http action: http_action']

    # Test case 5: Invalid headers (invalid parameter_type)
    data["params_list"][0]["parameter_type"] = list(action_param_types)[0]
    data["headers"][0]["parameter_type"] = "invalid_type"
    assert DataValidation.validate_http_action(bot, data) == ['Invalid headers for http action: http_action']


def test_data_validator_validate_form_validation_action():
    bot = "my_test_bot"

    # Test case 1: Valid validation_semantic and slot_set
    data = {
        "name" : "test_action",
        "validation_semantic": "valid_semantic",
        "slot_set": {"type": "current", "value": ""}
    }
    assert not DataValidation.validate_form_validation_action(bot, data)

    # Test case 2: Invalid validation_semantic (not a string)
    data["validation_semantic"] = 123
    assert DataValidation.validate_form_validation_action(bot, data) == ['Invalid validation semantic: test_action']

    # Test case 3: Invalid slot_set (missing type)
    data["validation_semantic"] = "valid_semantic"
    data["slot_set"]["type"] = None
    assert DataValidation.validate_form_validation_action(bot, data) == ['slot_set should have type current as default!', 'Invalid slot_set type!']

    # Test case 4: Invalid slot_set (type current with value)
    data["slot_set"]["type"] = "current"
    data["slot_set"]["value"] = "value"
    assert DataValidation.validate_form_validation_action(bot, data) == ['slot_set with type current should not have any value!']

    # Test case 5: Invalid slot_set (type slot without value)
    data["slot_set"]["type"] = "slot"
    data["slot_set"]["value"] = None
    assert DataValidation.validate_form_validation_action(bot, data) == ['slot_set with type slot should have a valid slot value!']

    # Test case 6: Invalid slot_set (invalid type)
    data["slot_set"]["type"] = "invalid_type"
    data["slot_set"]["value"] = "value"
    assert DataValidation.validate_form_validation_action(bot, data) == ['Invalid slot_set type!']


def test_data_validator_validate_database_action():
    bot = "my_test_bot"
    db_action_operation_types = {qtype.value for qtype in DbActionOperationType}

    # Test case 1: Valid payload
    data = {
        "payload": [{"query_type": list(db_action_operation_types)[0], "type": "type1", "value": "value1"}]
    }
    assert not DataValidation.validate_database_action(bot, data)

    # Test case 2: Invalid payload (missing query_type)
    data["payload"][0]["query_type"] = None
    assert DataValidation.validate_database_action(bot, data) == ["Payload 0 must contain fields 'query_type' and 'type'!", 'Unknown query_type found: None in payload 0']

    # Test case 3: Invalid payload (missing type)
    data["payload"][0]["query_type"] = list(db_action_operation_types)[0]
    data["payload"][0]["type"] = None
    assert DataValidation.validate_database_action(bot, data) == ["Payload 0 must contain fields 'query_type' and 'type'!"]


    # Test case 4: Invalid payload (invalid query_type)
    data["payload"][0]["type"] = 'type1'
    data["payload"][0]["value"] = "value1"
    data["payload"][0]["query_type"] = "invalid_query_type"
    assert DataValidation.validate_database_action(bot, data) == ["Unknown query_type found: invalid_query_type in payload 0", ]


def test_data_validator_validate_python_script_compile_time():
    # Test case 1: Valid Python script
    script = "print('Hello, World!')"
    assert DataValidation.validate_python_script_compile_time(script) is None

    # Test case 2: Invalid Python script (SyntaxError)
    script = "print('Hello, World!"
    assert DataValidation.validate_python_script_compile_time(script) == "unterminated string literal (detected at line 1)"


def test_data_validator_validate_pyscript_action():
    bot = "my_test_bot"

    # Test case 1: Valid Python script
    data = {"source_code": "print('Hello, World!')"}
    assert not DataValidation.validate_pyscript_action(bot, data)

    # Test case 2: Invalid Python script (SyntaxError)
    data["source_code"] = "print('Hello, World!"
    assert DataValidation.validate_pyscript_action(bot, data) == ["Error in python script: unterminated string literal (detected at line 1)"]

    # Test case 3: Missing source_code
    data = {}
    assert DataValidation.validate_pyscript_action(bot, data) == ['Script is required for pyscript action!']


def test_data_validator_validate_callback_config():
    bot = "my_test_bot"

    # Test case 1: Valid Python script
    data = {"pyscript_code": "print('Hello, World!')"}
    assert not DataValidation.validate_callback_config(bot, data)

    # Test case 2: Invalid Python script (SyntaxError)
    data["pyscript_code"] = "print('Hello, World!"
    assert DataValidation.validate_callback_config(bot, data) == ["Error in python script: unterminated string literal (detected at line 1)"]

    # Test case 3: Missing pyscript_code
    data = {}
    assert DataValidation.validate_callback_config(bot, data) == ['pyscript_code is required']


@pytest.mark.parametrize(
    "llm_prompts, expected_errors",
    [
        # Test: Valid prompts (no errors expected)
        (
            [
                {"type": "system", "source": "static", "data": "name", "name": "Prompt1", "hyperparameters": {"similarity_threshold": 0.5, "top_results": 5}},
                {"type": "user", "source": "slot", "data": "name", "name": "Prompt1"}
            ],
            []
        ),
        # Test: Invalid similarity_threshold (out of range)
        (
            [
                {"type": "system", "source": "static", "data": "name", "name": "Prompt1", "hyperparameters": {"similarity_threshold": 1.5}},
                {"type": "user", "source": "slot", "data": "name", "name": "Prompt2"}
            ],
            ["similarity_threshold should be within 0.3 and 1.0 and of type int or float!"]
        ),
        # Test: Missing data for action source
        (
            [
                {"type": "system", "source": "static", "data": "name", "name": "Prompt1"},
                {"type": "user", "source": "action", "name": "Prompt2"}
            ],
            ["Data must contain action name"]
        ),
        # Test: Invalid type value
        (
            [
                {"type": "invalid", "source": "static", "data": "name", "name": "Prompt3"}
            ],
            ["Invalid prompt type",  "System prompt is required"]
        ),
        # Test: Multiple system prompts
        (
            [
                {"type": "system", "source": "static", "data": "name", "name": "Prompt1"},
                {"type": "system", "source": "static", "data": "name", "name": "Prompt2"}
            ],
            ["Only one system prompt can be present"]
        ),
        # Test: Missing system prompt
        (
            [
                {"type": "user", "source": "slot", "data": "name", "name": "Prompt4"}
            ],
            ["System prompt is required"]
        ),
        # Test: Invalid source value
        (
            [
                {"type": "system", "source": "invalid_source", "data": "name", "name": "Prompt5"}
            ],
            ["Invalid prompt source", 'System prompt must have static source']
        ),
        # Test: Invalid top_results value (greater than 30)
        (
            [
                {"type": "system", "source": "static", "data": "name", "name": "Prompt1", "hyperparameters": {"top_results": 50}}
            ],
            ["top_results should not be greater than 30 and of type int!"]
        ),
        # Test: Empty name field
        (
            [
                {"type": "system", "source": "static", "data": "name", "name": ""}
            ],
            ["Name cannot be empty"]
        )
    ]
)
def test_data_validation_llm_prompt(llm_prompts, expected_errors):
    assert DataValidation.validate_llm_prompts(llm_prompts) == expected_errors


def test_modify_callback_config():
    bot = 'test_bot'
    data = {}

    result = DataValidation.modify_callback_config(bot, data)

    assert 'token_hash' in result
    assert 'validation_secret' in result


def test_validate_prompt_action():
    bot = "my_test_bot"

    llm_secret = LLMSecret(
        llm_type="openai",
        api_key='value',
        models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
        bot=bot,
        user='user'
    )
    llm_secret.save()

    # Test case 1: Valid prompt action
    data = {
        "num_bot_responses": 3,
        "llm_prompts": [
            {
                "type": "system",
                "source": "static",
                "data": "Hello, World!",
                "name": "Prompt1",
                "hyperparameters": {
                    "similarity_threshold": 0.5,
                    "top_results": 5
                }
            }
        ],
        "hyperparameters": {
            "similarity_threshold": 0.5,
            "top_results": 5,
            "model": "gpt-3.5-turbo",
        },
        "llm_type": "openai"
    }
    assert not DataValidation.validate_prompt_action(bot, data)

    # Test case 2: Invalid num_bot_responses (greater than 5)
    data["num_bot_responses"] = 6
    assert DataValidation.validate_prompt_action(bot, data) == ['num_bot_responses should not be greater than 5 and of type int: None']

    # Test case 3: Invalid llm_prompts (invalid type)
    data["num_bot_responses"] = 3
    data["llm_prompts"][0]["type"] = "invalid_type"
    assert DataValidation.validate_prompt_action(bot, data) == ['Invalid prompt type', 'System prompt is required']

    # Test case 4: Invalid hyperparameters (similarity_threshold out of range)
    data["llm_prompts"][0]["type"] = "system"
    data["llm_prompts"][0]["hyperparameters"]["similarity_threshold"] = 1.5
    data["hyperparameters"]["similarity_threshold"] = 0.2
    assert DataValidation.validate_prompt_action(bot, data) == ["similarity_threshold should be within 0.3 and 1.0 and of type int or float!"]

    LLMSecret.objects.delete()

@patch('kairon.shared.live_agent.live_agent.LiveAgentHandler.is_live_agent_service_available')
def test_live_agent_action_validation_fail(mock_live_agent_check):
    mock_live_agent_check.return_value = False
    bot = "test_bot"
    actions = {
        "live_agent_action": [{
    "bot": "test_bot",
    "user": "aniket.kharkia@nimblework.com",
    "name": "live_agent_action"}]
    }
    other_collections = {}
    val = ActionSerializer.validate(bot, actions, other_collections)

    assert not val[0]
    assert val[1]["live_agent_action"] == ["Please Enable Live Agent for bot before uploading"]

@patch('kairon.shared.live_agent.live_agent.LiveAgentHandler.is_live_agent_service_available')
def test_live_agent_action_validation_pass(mock_live_agent_check):
    mock_live_agent_check.return_value = True
    bot = "test_bot"
    actions = {
        "live_agent_action": [{"bot": "test_bot",
    "user": "aniket.kharkia@nimblework.com",
    "name": "live_agent_action"}]
    }
    other_collections = {}
    val = ActionSerializer.validate(bot, actions, other_collections)

    assert val[0]
    assert not val[1]["live_agent_action"]

def test_action_serializer_validate():
    bot = "my_test_bot"

    # Test case 1: Valid actions and other_collections
    actions = {
        "http_action": [
            valid_http_action_config
        ],
        "pyscript_action": [
            valid_pyscript_action_config
        ]
    }
    other_collections = {
        str(CallbackConfig.__name__).lower(): [
            valid_callback_config
        ]
    }
    val = ActionSerializer.validate(bot, actions, other_collections)
    assert val[0]
    for k in val[1].keys():
        assert not val[1][k]

    assert val[2][str(CallbackConfig.__name__).lower()] == 1
    assert val[2]['http_action'] == 1
    assert val[2]['pyscript_action'] == 1

    # Test case 2: Invalid actions (not a dictionary)
    actions = ["http_action"]
    val = ActionSerializer.validate(bot, actions, other_collections)
    assert val[0]
    assert val[1] == {'action.yml': ['Expected dictionary with action types as keys']}

    # Test case 3: Invalid actions (invalid action type)
    actions = {
        "invalid_action_type": []
    }
    val = ActionSerializer.validate(bot, actions, other_collections)
    assert not val[0]
    assert val[1]['invalid_action_type'] == ['Invalid action type: invalid_action_type.']

    # Test case 4: not a list
    actions = {
        "http_action": {}
    }
    val = ActionSerializer.validate(bot, actions, other_collections)
    assert not val[0]
    assert val[1]['http_action'] == ['Expected list of actions for http_action.']

    # Test case 5: Invalid action data
    actions = {
        "http_action": [
            invalid_http_action_config_field_missing
        ],
        "pyscript_action": [
            invalid_pyscript_action_config_field_missing
        ]
    }
    val = ActionSerializer.validate(bot, actions, other_collections)
    assert not val[0]
    assert val[1]['http_action'] == [{ 'a_api_action_field_missing': " Required fields {'http_url'} not found."}]
    assert val[1]['pyscript_action'] == [{'a_pyscript_action_field_missing': " Required fields {'source_code'} not found."}]

    # Test case 6: unknown other collection type
    oc2 = {
        "unknown": [
            valid_callback_config
        ]
    }
    val = ActionSerializer.validate(bot, actions, oc2)
    assert not val[0]
    assert val[1]['unknown'] == ['Invalid collection type: unknown.']

    # Test case 7: other collection entry type not list
    oc2 = {
        str(CallbackConfig.__name__).lower(): {
            'data': valid_callback_config
        }
    }

    val = ActionSerializer.validate(bot, actions, oc2)
    assert not val[0]
    assert val[1][str(CallbackConfig.__name__).lower()] == ['Expected list of data for callbackconfig.']

    # test case 8: duplicate entries for action
    actions = {
        "http_action": [
            valid_http_action_config,
            valid_http_action_config
        ]
    }

    val = ActionSerializer.validate(bot, actions, other_collections)
    assert not val[0]
    assert val[1]['http_action'] == [{'a_api_action': 'Duplicate Name found for other action.'}]

    # test case 9: invalid other collection
    actions = {
        "http_action": [
            valid_http_action_config
        ],
        "pyscript_action": [
            valid_pyscript_action_config
        ]
    }
    other_collections = {
        str(CallbackConfig.__name__).lower(): [
            invalid_callback_config_missing_field
        ]
    }

    val = ActionSerializer.validate(bot, actions, other_collections)
    assert not val[0]
    assert "Required fields" in val[1][str(CallbackConfig.__name__).lower()][0]['cb1']


def test_action_serializer_deserialize():
    bot = "my_test_bot"
    user = "test_user@test_user.com"

    # Test case 1: Valid actions and other_collections
    actions = {
        "http_action": [
            valid_http_action_config,
        ],
        "pyscript_action": [
            valid_pyscript_action_config
        ]
    }

    other_collections = {
        str(CallbackConfig.__name__).lower(): [
            valid_callback_config
        ]
    }

    ActionSerializer.deserialize(bot, user, actions, other_collections)
    actions_added = Actions.objects(bot=bot, user=user)
    assert len(list(actions_added)) == 2
    names = [action.name for action in actions_added]
    assert "a_api_action" in names
    assert "a_pyscript_action" in names

    http_action = HttpActionConfig.objects(bot=bot, user=user).get()
    assert http_action.action_name == "a_api_action"

    callback = CallbackConfig.objects(bot=bot).get()
    assert callback.name == "cb1"


def test_action_serializer_deserialize_single_instance_append():
    bot = "my_test_bot"
    user = "test_user@test_user.com"

    actions = {
        "live_agent_action": [
            {
                'name': 'live_agent_action',
            }
        ]
    }

    other_collections = {}

    # Case : action doesn't exist
    ActionSerializer.deserialize(bot, user, actions, other_collections)

    actions_added = Actions.objects(bot=bot, user=user)
    action_names = [action.name for action in actions_added]
    print(action_names)
    assert len(list(actions_added)) == 3
    names = [action.name for action in actions_added]
    assert "live_agent_action" in names

    # Case : action already exists

    ActionSerializer.deserialize(bot, user, actions, other_collections)
    assert len(list(actions_added)) == 3
    la_action_count = Actions.objects(bot=bot, user=user, name="live_agent_action").count()
    assert la_action_count == 1
    live_agent_action = LiveAgentActionConfig.objects(bot=bot, user=user).get()
    assert live_agent_action.name == "live_agent_action"

def test_action_serializer_deserialize_overwrite():
    bot = "my_test_bot"
    user = "test_user@test_user.com"

    # Test case 1: Valid actions and other_collections
    actions = {
        "http_action": [
            valid_http_action_config,
        ],
        "pyscript_action": [
            valid_pyscript_action_config
        ]
    }

    other_collections = {
        str(CallbackConfig.__name__).lower(): [
            valid_callback_config
        ]
    }

    Actions.objects(bot=bot, user=user).delete()
    HttpActionConfig.objects(bot=bot, user=user).delete()
    PyscriptActionConfig.objects(bot=bot, user=user).delete()
    CallbackConfig.objects(bot=bot).delete()

    ActionSerializer.deserialize(bot, user, actions, other_collections,True)
    actions_added = Actions.objects(bot=bot, user=user)
    assert len(list(actions_added)) == 2
    names = [action.name for action in actions_added]
    assert "a_api_action" in names
    assert "a_pyscript_action" in names

    http_action = HttpActionConfig.objects(bot=bot, user=user).get()
    assert http_action.action_name == "a_api_action"

    callback = CallbackConfig.objects(bot=bot).get()
    assert callback.name == "cb1"


def test_action_serialize_duplicate_data():
    bot = "my_test_bot"
    user = "test_user@test_user.com"

    actions = {
        "http_action": [
            valid_http_action_config,
            valid_http_action_config2
        ],
        "pyscript_action": [
            valid_pyscript_action_config
        ]
    }

    other_collections = {
        str(CallbackConfig.__name__).lower(): [
            valid_callback_config
        ]
    }

    actions_added = Actions.objects(bot=bot, user=user)
    assert len(list(actions_added)) == 2
    ActionSerializer.deserialize(bot, user, actions, other_collections)
    actions_added = Actions.objects(bot=bot, user=user)
    assert len(list(actions_added)) == 3
    names = [action.name for action in actions_added]
    assert "a_api_action" in names
    assert "a_api_action2" in names
    assert "a_pyscript_action" in names

    http_action = HttpActionConfig.objects(bot=bot, user=user)
    assert len(list(http_action)) == 2


def test_action_serializer_serialize():
    bot = "my_test_bot"
    user = "test_user@test_user.com"

    actions, others = ActionSerializer.serialize(bot)
    assert actions
    assert others

    assert len(actions['http_action']) == 2
    assert len(actions['pyscript_action']) == 1

    assert len(others[str(CallbackConfig.__name__).lower()]) == 1


def test_action_save_collection_data_list_unknown_data():
    bot = "my_test_bot"
    user = "test_user@test_user.com"

    with pytest.raises(AppException, match="Action type not found"):
        ActionSerializer.save_collection_data_list('unknown1', bot, user,  [{'data1': 'value1'}])


def test_prompt_action_validation_missing_model():
    bot = "my_test_bot"
    data = {
        "num_bot_responses": 3,
        "llm_prompts": [
            {
                "type": "system",
                "source": "static",
                "data": "Hello, World!",
                "name": "Prompt1",
                "hyperparameters": {
                    "similarity_threshold": 0.5,
                    "top_results": 5
                }
            }
        ],
        "hyperparameters": {
            "similarity_threshold": 0.5,
            "top_results": 5,
        },
    }
    errors =  DataValidation.validate_prompt_action(bot, data)
    assert errors == ['model is required in hyperparameters!']




def test_get_model_llm_type_map_dynamic():
    result = DataValidation.get_model_llm_type_map()
    expected_categories = {
        'openai': ['gpt-3.5', 'gpt-4.1'],
        'aws-anthropic': ['bedrock/us.anthropic', 'claude'],
        'anthropic': ['bedrock/us.anthropic', 'claude'],
        'gemini': ['gemini/'],
        'perplexity': ['perplexity/llama'],
        'aws-nova': ['bedrock/converse/us.amazon.nova']
    }

    for model_name, provider in result.items():
        assert provider in expected_categories, f"Unexpected provider: {provider}"
        assert any(model_name.startswith(prefix) for prefix in expected_categories[provider]), (
            f"Model {model_name} does not match provider {provider}"
        )




def test_add_llm_type_based_on_model():
    bot = "my_test_bot"

    llm_secret = LLMSecret(
        llm_type="openai",
        api_key='value',
        models=["gpt-3.5-turbo", "gpt-4.1-mini", "gpt-4.1"],
        bot=bot,
        user='user'
    )
    llm_secret.save()

    data = {
        "num_bot_responses": 3,
        "llm_prompts": [
            {
                "type": "system",
                "source": "static",
                "data": "Hello, World!",
                "name": "Prompt1",
                "hyperparameters": {
                    "similarity_threshold": 0.5,
                    "top_results": 5
                }
            }
        ],
        "hyperparameters": {
            "similarity_threshold": 0.5,
            "top_results": 5,
            "model": "gpt-4.1-mini",
        },
    }
    assert not DataValidation.validate_prompt_action(bot, data)
    assert data['llm_type'] == 'openai'

    LLMSecret.objects.delete()
