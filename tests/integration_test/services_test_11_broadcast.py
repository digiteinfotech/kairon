from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_add_schedule_action_with_invalid_params_list_values():
    schedule_action_data = {
        "name": "test_schedule_action",
        "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
        "timezone": None,
        "schedule_action": "test_pyscript",
        "response_text": "action scheduled",
        "params_list": [
            {
                "value": "param_1",
                "parameter_type": "value",
                "count": 0
            }
        ],
        "dispatch_bot_response": True
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/schedule",
        json=schedule_action_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert not actual["data"]
    assert actual["message"] ==  [
        {'loc': ['body', 'params_list', 0, 'key'], 'msg': 'field required', 'type': 'value_error.missing'}, 
        {'loc': ['body', 'params_list', 0, '__root__'], 'msg': 'key cannot be empty', 'type': 'value_error'}
    ]
    assert actual["error_code"] == 422



def test_add_schedule_action():
    schedule_action_data = {
        "name": "test_schedule_action",
        "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
        "timezone": None,
        "schedule_action": "test_pyscript",
        "response_text": "action scheduled",
        "params_list": [
            {
                "key": "param_key",
                "value": "param_1",
                "parameter_type": "value",
                "count": 0
            }
        ],
        "dispatch_bot_response": True
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/schedule",
        json=schedule_action_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"

def test_add_schedule_action_with_type():
    schedule_action_data = {
        "name": "test_schedule_action2",
        "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
        "timezone": None,
        "schedule_action": "flow_name",
        "response_text": "action scheduled",
        "params_list": [
            {
                "key": "param_key",
                "value": "param_1",
                "parameter_type": "value",
                "count": 0
            }
        ],
        "schedule_action_type": 'flow',
        "dispatch_bot_response": True
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/schedule",
        json=schedule_action_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action added!"

    actions = ScheduleAction.objects(bot=pytest.bot)
    action_data = []
    for act in actions:
        a = {
            'name': act.name,
            'type': act.schedule_action_type
        }
        action_data.append(a)
    expected = [{'name': 'test_schedule_action', 'type': 'pyscript'}, {'name': 'test_schedule_action2', 'type': 'flow'}]
    assert action_data == expected

    ScheduleAction.objects(bot=pytest.bot, name='test_schedule_action2').delete()


def test_add_schedule_action_exists():
    schedule_action_data = {
        "name": "test_schedule_action",
        "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
        "timezone": None,
        "schedule_action": "test_pyscript",
        "response_text": "action scheduled",
        "params_list": [],
        "dispatch_bot_response": True
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/action/schedule",
        json=schedule_action_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] == False
    assert actual["error_code"] == 422
    assert actual["message"] == "Action exists!"


def test_list_schedule_action():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/schedule",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    data = actual["data"]
    for item in data:
        item.pop('_id')
    assert data == [
        {
            'name': 'test_schedule_action', 
            'schedule_time': {'value': '2024-08-06T09:00:00.000+0530', 'parameter_type': 'value'}, 
            'timezone': 'UTC', 
            'schedule_action': 'test_pyscript',
            'schedule_action_type': 'pyscript',
            'response_text': 'action scheduled',
            'params_list': [
                {
                    '_cls': 'CustomActionRequestParameters', 
                    'key': 'param_key', 
                    'encrypt': False, 
                    'value': 'param_1',
                    'parameter_type': 'value'
                }
            ], 
            'dispatch_bot_response': True
        }
    ]


def test_update_schedule_action_update_scheduled_action():
    schedule_action_data = {
        "name": "test_schedule_action",
        "schedule_time": {"value": "2024-08-06T09:00:00.000+0530", "parameter_type": "value"},
        "timezone": None,
        "schedule_action": "test_pyscript_new",
        "response_text": "action scheduled, will be notified",
        "params_list": [
            {
                "key": "updated_key",
                "value": "param_2",
                "parameter_type": "value",
                "count": 0
            }
        ],
        "dispatch_bot_response": True
    }

    response = client.put(
        f"/api/bot/{pytest.bot}/action/schedule",
        json=schedule_action_data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Action updated!"
    action = ScheduleAction.objects(bot=pytest.bot, name="test_schedule_action", status=True).get()
    action = action.to_mongo().to_dict()
    assert action.get("schedule_action") == "test_pyscript_new"
    assert action.get("response_text") == "action scheduled, will be notified"


def test_list_schedule_action_after_update():
    response = client.get(
        f"/api/bot/{pytest.bot}/action/schedule",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["message"]
    data = actual["data"]
    for item in data:
        item.pop('_id')
    assert data == [
        {
            'name': 'test_schedule_action', 
            'schedule_time': {'value': '2024-08-06T09:00:00.000+0530', 'parameter_type': 'value'}, 
            'timezone': 'UTC', 
            'schedule_action': 'test_pyscript_new',
            'schedule_action_type': 'pyscript',
            'response_text': 'action scheduled, will be notified', 
            'params_list': [
                {
                    '_cls': 'CustomActionRequestParameters', 
                    'key': 'updated_key',
                    'encrypt': False, 
                    'value': 'param_2', 
                    'parameter_type': 'value'
                }
            ], 
            'dispatch_bot_response': True
        }
    ]


def test_initiate_bsp_onboarding_for_broadcast(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(whatsapp="360dialog", bot=pytest.bot, user="test_user")

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://kairon-api.digite.com"
    )
    monkeypatch.setitem(
        Utility.environment["channels"]["360dialog"], "partner_id", "f167CmPA"
    )

    with patch(
            "kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_account"
    ) as mock_get_account:
        mock_get_account.return_value = "dfghj5678"
        with patch(
                "kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.generate_waba_key"
        ) as mock_generate_waba_key:
            mock_generate_waba_key.return_value = "dfghjk5678"
            response = client.post(
                f"/api/bot/{pytest.bot}/channels/whatsapp/360dialog/onboarding?clientId=kairon&client=sdfgh5678&channels=['sdfghjk678']",
                headers={
                    "Authorization": pytest.token_type + " " + pytest.access_token
                },
            )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Channel added"
    assert actual["data"].startswith(
        f"http://kairon-api.digite.com/api/bot/whatsapp/{pytest.bot}/e"
    )


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_broadcast_message(mock_event_server):
    config = {
        "name": "test_broadcast",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "status": False,
        "recipients_config": {"recipients": "919876543210,919012345678"},
        "template_config": [
            {
                "template_id": "sales_template",
            }
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast added!"
    pytest.broadcast_msg_id = actual["data"]["msg_broadcast_id"]
    assert pytest.broadcast_msg_id


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_broadcast_message_without_collection(mock_event_server):
    config = {
        "name": "broadcast_with_collection_config",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": ""},
        "collection_config": {
            "number_field": "mobile_number",
            "filters_list": [
                {
                    "column": "age",
                    "condition": "lte",
                    "value": "26"
                },
                {
                    "column": "age",
                    "condition": "gt",
                    "value": "22"
                },
                {
                    "column": "name",
                    "condition": "nin",
                    "value": [
                        "Mahesh",
                        "Hitesh"
                    ]
                }
            ],
            "field_mapping": {
                "brochure_pdf": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "{name}"
                            }
                        ]
                    },
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "{status}"
                            }
                        ]
                    }
                ]
            }
        },
        "retry_count": 0,
        "template_config": [
            {
                'language': 'hi',
                "template_id": "brochure_pdf",
            }
        ]
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'collection_config', 'collection'],
                                 'msg': 'field required', 'type': 'value_error.missing'}]


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_broadcast_message_without_number_field(mock_event_server):
    config = {
        "name": "broadcast_with_collection_config",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": ""},
        "collection_config": {
            "collection": "crop_details",
            "filters_list": [
                {
                    "column": "age",
                    "condition": "lte",
                    "value": "26"
                },
                {
                    "column": "age",
                    "condition": "gt",
                    "value": "22"
                },
                {
                    "column": "name",
                    "condition": "nin",
                    "value": [
                        "Mahesh",
                        "Hitesh"
                    ]
                }
            ],
            "field_mapping": {
                "brochure_pdf": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "{name}"
                            }
                        ]
                    },
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "{status}"
                            }
                        ]
                    }
                ]
            }
        },
        "retry_count": 0,
        "template_config": [
            {
                'language': 'hi',
                "template_id": "brochure_pdf",
            }
        ]
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'collection_config', 'number_field'],
                                 'msg': 'field required', 'type': 'value_error.missing'}]


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_broadcast_message_without_filters_list(mock_event_server):
    config = {
        "name": "broadcast_without_filters_list",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": ""},
        "collection_config": {
            "collection": "crop_details",
            "number_field": "mobile_number",
            "filters_list": [],
            "field_mapping": {
                "brochure_pdf": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "{name}"
                            }
                        ]
                    },
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "{status}"
                            }
                        ]
                    }
                ]
            }
        },
        "retry_count": 0,
        "template_config": [
            {
                'language': 'hi',
                "template_id": "brochure_pdf",
            }
        ]
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast added!"
    pytest.broadcast_msg_id3 = actual["data"]["msg_broadcast_id"]
    assert pytest.broadcast_msg_id3


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_broadcast_message_without_field_mapping(mock_event_server):
    config = {
        "name": "broadcast_with_collection_config",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": ""},
        "collection_config": {
            "collection": "crop_details",
            "number_field": "mobile_number",
            "filters_list": [
                {
                    "column": "age",
                    "condition": "lte",
                    "value": "26"
                },
                {
                    "column": "age",
                    "condition": "gt",
                    "value": "22"
                },
                {
                    "column": "name",
                    "condition": "nin",
                    "value": [
                        "Mahesh",
                        "Hitesh"
                    ]
                }
            ],
        },
        "retry_count": 0,
        "template_config": [
            {
                'language': 'hi',
                "template_id": "brochure_pdf",
            }
        ]
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'collection_config', 'field_mapping'],
                                 'msg': 'field required', 'type': 'value_error.missing'}]


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_broadcast_message_with_collection_config(mock_event_server):
    config = {
        "name": "broadcast_with_collection_config",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": ""},
        "collection_config": {
            "collection": "crop_details",
            "number_field": "mobile_number",
            "filters_list": [
                {
                    "column": "age",
                    "condition": "lte",
                    "value": "26"
                },
                {
                    "column": "age",
                    "condition": "gt",
                    "value": "22"
                },
                {
                    "column": "name",
                    "condition": "nin",
                    "value": [
                        "Mahesh",
                        "Hitesh"
                    ]
                }
            ],
            "field_mapping": {
                "brochure_pdf": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "{name}"
                            }
                        ]
                    },
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "{status}"
                            }
                        ]
                    }
                ]
            }
        },
        "retry_count": 0,
        "template_config": [
            {
                'language': 'hi',
                "template_id": "brochure_pdf",
            }
        ]
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast added!"
    pytest.broadcast_msg_id2 = actual["data"]["msg_broadcast_id"]
    assert pytest.broadcast_msg_id2


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_resend_broadcast_message(mock_event_server):
    from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings

    settings = MessageBroadcastSettings.objects(id=pytest.broadcast_msg_id, bot=pytest.bot, status=True).get()
    settings.status = False
    settings.save()

    config = {
        "name": "test_broadcast",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "919876543210,919012345678"},
        "template_config": [
            {
                "template_id": "sales_template",
            }
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/resend/{pytest.broadcast_msg_id}",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Resending Broadcast!"


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_resend_broadcast_message_with_retry_limit_exceeded(mock_event_server, monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", llm_settings=LLMSettings(enable_faq=True),
                           retry_broadcasting_limit=3)

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings

    settings = MessageBroadcastSettings.objects(id=pytest.broadcast_msg_id, bot=pytest.bot, status=False).get()
    settings.retry_count = 3
    settings.save()

    config = {
        "name": "test_broadcast",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "919876543210,919012345678"},
        "template_config": [
            {
                "template_id": "sales_template",
            }
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/resend/{pytest.broadcast_msg_id}",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual["message"] == "Retry Broadcasting limit reached!"


def test_list_broadcast():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["schedules"][0].pop("timestamp")
    actual["data"]["schedules"][0].pop("user")
    actual["data"]["schedules"][1].pop("timestamp")
    actual["data"]["schedules"][1].pop("user")
    print(actual["data"])
    assert actual["data"] == {
        "schedules": [
            {
                '_id': pytest.broadcast_msg_id3,
                'name': 'broadcast_without_filters_list',
                'connector_type': 'whatsapp',
                'broadcast_type': 'static',
                'bsp_type': '360dialog',
                'recipients_config': {'recipients': ''},
                'template_config': [{'template_id': 'brochure_pdf', 'language': 'hi'}],
                'collection_config': {
                    'collection': 'crop_details',
                    'number_field': 'mobile_number',
                    'filters_list': [],
                    'field_mapping': {
                        'brochure_pdf': [
                            {'type': 'header', 'parameters': [{'type': 'text', 'text': '{name}'}]},
                            {'type': 'body', 'parameters': [{'type': 'text', 'text': '{status}'}]}
                        ]
                    }
                },
                'retry_count': 0,
                'bot': pytest.bot,
                'status': True
            },
            {
                '_id': pytest.broadcast_msg_id2,
                'name': 'broadcast_with_collection_config',
                'connector_type': 'whatsapp',
                'broadcast_type': 'static',
                'bsp_type': '360dialog',
                'recipients_config': {'recipients': ''},
                'template_config': [
                    {'template_id': 'brochure_pdf', 'language': 'hi'}
                ],
                'collection_config': {
                    'collection': 'crop_details',
                    'number_field': 'mobile_number',
                    'filters_list': [
                        {'column': 'age', 'condition': 'lte', 'value': '26'},
                        {'column': 'age', 'condition': 'gt', 'value': '22'},
                        {'column': 'name', 'condition': 'nin', 'value': ['Mahesh', 'Hitesh']}
                    ],
                    'field_mapping': {
                        'brochure_pdf': [
                            {'type': 'header', 'parameters': [{'type': 'text', 'text': '{name}'}]},
                            {'type': 'body', 'parameters': [{'type': 'text', 'text': '{status}'}]}
                        ]
                    }
                },
                'retry_count': 0,
                'bot': pytest.bot,
                'status': True
            }
        ]
    }


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_update_broadcast_with_collection_config(mock_event_server):
    config = {
        "name": "update_broadcast_with_collection_config",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": ""},
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "21 11 * * *",
            "timezone": "Asia/Kolkata",
        },
        "collection_config": {
            "collection": "crop_details",
            "number_field": "contact_number",
            "filters_list": [
                {
                    "column": "age",
                    "condition": "gte",
                    "value": "26"
                },
                {
                    "column": "age",
                    "condition": "lt",
                    "value": "22"
                },
                {
                    "column": "name",
                    "condition": "nin",
                    "value": [
                        "Mahesh",
                        "Hitesh"
                    ]
                }
            ],
            "field_mapping": {
                "brochure_pdf": [
                    {
                        "type": "header",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "{crop}"
                            }
                        ]
                    },
                    {
                        "type": "body",
                        "parameters": [
                            {
                                "type": "text",
                                "text": "{status}"
                            }
                        ]
                    }
                ]
            }
        },
        "retry_count": 0,
        "template_config": [
            {
                'language': 'hi',
                "template_id": "brochure_pdf",
            }
        ]
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.broadcast_msg_id2}",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast updated!"


def test_list_broadcast_after_update():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["schedules"][0].pop("timestamp")
    actual["data"]["schedules"][0].pop("user")
    actual["data"]["schedules"][1].pop("timestamp")
    actual["data"]["schedules"][1].pop("user")
    assert actual["data"] == {
        "schedules": [
            {
                '_id': pytest.broadcast_msg_id3,
                'name': 'broadcast_without_filters_list',
                'connector_type': 'whatsapp',
                'broadcast_type': 'static',
                'bsp_type': '360dialog',
                'recipients_config': {'recipients': ''},
                'template_config': [{'template_id': 'brochure_pdf', 'language': 'hi'}],
                'collection_config': {
                    'collection': 'crop_details',
                    'number_field': 'mobile_number',
                    'filters_list': [],
                    'field_mapping': {
                        'brochure_pdf': [
                            {'type': 'header', 'parameters': [{'type': 'text', 'text': '{name}'}]},
                            {'type': 'body', 'parameters': [{'type': 'text', 'text': '{status}'}]}
                        ]
                    }
                },
                'retry_count': 0,
                'bot': pytest.bot,
                'status': True
            },
            {
                '_id': pytest.broadcast_msg_id2,
                'name': 'update_broadcast_with_collection_config',
                'connector_type': 'whatsapp',
                'broadcast_type': 'static',
                'bsp_type': '360dialog',
                'recipients_config': {'recipients': ''},
                "scheduler_config": {
                    "expression_type": "cron",
                    "schedule": "21 11 * * *",
                    "timezone": "Asia/Kolkata",
                },
                'template_config': [
                    {'template_id': 'brochure_pdf', 'language': 'hi'}
                ],
                'collection_config': {
                    'collection': 'crop_details',
                    'number_field': 'contact_number',
                    'filters_list': [
                        {'column': 'age', 'condition': 'gte', 'value': '26'},
                        {'column': 'age', 'condition': 'lt', 'value': '22'},
                        {'column': 'name', 'condition': 'nin', 'value': ['Mahesh', 'Hitesh']}
                    ],
                    'field_mapping': {
                        'brochure_pdf': [
                            {'type': 'header', 'parameters': [{'type': 'text', 'text': '{crop}'}]},
                            {'type': 'body', 'parameters': [{'type': 'text', 'text': '{status}'}]}
                        ]
                    }
                },
                'retry_count': 0,
                'bot': pytest.bot,
                'status': True
            }
        ]
    }


@patch("kairon.shared.utils.Utility.delete_scheduled_event", autospec=True)
def test_delete_message_broadcast(mock_event_server):
    from kairon.shared.chat.broadcast.data_objects import MessageBroadcastSettings

    settings = MessageBroadcastSettings.objects(id=pytest.broadcast_msg_id, bot=pytest.bot, status=False).get()
    settings.status = True
    settings.save()

    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.broadcast_msg_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast removed!"

def test_get_broadcast_logs_with_resend_broadcasts():
    from kairon.shared.chat.broadcast.data_objects import MessageBroadcastLogs

    ref_id = ObjectId().__str__()
    timestamp = utc_now()
    MessageBroadcastLogs(
        **{
            "reference_id": ref_id,
            "log_type": "common",
            "bot": pytest.bot,
            "status": EVENT_STATUS.COMPLETED.value,
            "user": "test_user",
            "broadcast_id": pytest.broadcast_msg_id,
            "recipients": ["919876543210", "918958030541"],
            "timestamp": timestamp,
        }
    ).save()
    timestamp = timestamp + timedelta(minutes=2)
    MessageBroadcastLogs(
        **{
            "reference_id": ref_id,
            "log_type": "resend",
            "bot": pytest.bot,
            "status": STATUSES.SUCCESS.value,
            "api_response": {
                "contacts": [
                    {"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}
                ]
            },
            "recipient": "919876543210",
            "template_params": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {
                                "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                "filename": "Brochure.pdf",
                            },
                        }
                    ],
                }
            ],
            "timestamp": timestamp,
            "retry_count": 1
        }
    ).save()
    MessageBroadcastLogs(
        **{
            "reference_id": ref_id,
            "log_type": "resend",
            "bot": pytest.bot,
            "status": STATUSES.SUCCESS.value,
            "api_response": {
                "contacts": [
                    {"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}
                ]
            },
            "recipient": "918958030541",
            "template_params": [
                {
                    "type": "header",
                    "parameters": [
                        {
                            "type": "document",
                            "document": {
                                "link": "https://drive.google.com/uc?export=download&id=1GXQ43jilSDelRvy1kr3PNNpl1e21dRXm",
                                "filename": "Brochure.pdf",
                            },
                        }
                    ],
                }
            ],
            "timestamp": timestamp,
            "retry_count": 2
        }
    ).save()
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/logs?log_type=resend&retry_count=1&reference_id={ref_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["logs"][0].pop("timestamp")
    assert actual["data"]["logs"] == [
        {
            'reference_id': ref_id,
            'log_type': 'resend',
            'bot': pytest.bot,
            'status': STATUSES.SUCCESS.value,
            'api_response': {
                'contacts': [
                    {
                        'input': '+55123456789',
                        'status': 'valid',
                        'wa_id': '55123456789'
                    }
                ]
            },
            'recipient': '919876543210',
            'retry_count': 1
        }
    ]
    assert actual["data"]["total_count"] == 1

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/logs?reference_id={ref_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["logs"][0].pop("timestamp")
    actual["data"]["logs"][1].pop("timestamp")
    actual["data"]["logs"][2].pop("timestamp")
    assert actual["data"] == {
        'logs': [
            {
                'reference_id': ref_id,
                'log_type': 'resend',
                'bot': pytest.bot,
                'status': STATUSES.SUCCESS.value,
                'api_response': {
                    'contacts': [
                        {
                            'input': '+55123456789',
                            'status': 'valid',
                            'wa_id': '55123456789'
                        }
                    ]
                },
                'recipient': '918958030541',
                'retry_count': 2
            },
            {
                'reference_id': ref_id,
                'log_type': 'resend',
                'bot': pytest.bot,
                'status': STATUSES.SUCCESS.value,
                'api_response': {
                    'contacts': [
                        {
                            'input': '+55123456789',
                            'status': 'valid',
                            'wa_id': '55123456789'
                        }
                    ]
                },
                'recipient': '919876543210',
                'retry_count': 1
            },
            {
                'reference_id': ref_id,
                'log_type': 'common',
                'bot': pytest.bot,
                'status': EVENT_STATUS.COMPLETED.value,
                'user': 'test_user',
                'broadcast_id': pytest.broadcast_msg_id
            }
        ],
        'total_count': 3
    }
