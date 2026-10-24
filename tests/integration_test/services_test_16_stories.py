from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_add_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "test_greet", "type": "INTENT"},
                {"name": "utter_test_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    pytest.story_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_story_with_name_already_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "greet",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "test_greet", "type": "INTENT"},
                {"name": "utter_test_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Story with the name already exists"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_add_story_invalid_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "TEST",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "type"],
            "msg": "value is not a valid enumeration member; permitted: 'STORY', 'RULE', 'MULTIFLOW'",
            "type": "type_error.enum",
            "ctx": {"enum_values": ["STORY", "RULE", "MULTIFLOW"]},
        }
    ]


def test_add_story_empty_event():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={"name": "test_add_story_empty_event", "type": "STORY", "steps": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Steps are required to form Flow",
            "type": "value_error",
        }
    ]

def test_add_story_lone_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_lone_intent",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "greet_again", "type": "INTENT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Intent should be followed by utterance or action",
            "type": "value_error",
        }
    ]


def test_add_story_consecutive_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_consecutive_intents",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Found 2 consecutive intents",
            "type": "value_error",
        }
    ]


def test_add_story_multiple_actions():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_consecutive_actions",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "HTTP_ACTION"},
                {"name": "utter_greet_again", "type": "HTTP_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"


def test_add_story_utterance_as_first_step():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_consecutive_intents",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "BOT"},
                {"name": "utter_greet", "type": "HTTP_ACTION"},
                {"name": "utter_greet_again", "type": "HTTP_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "First step should be an intent",
            "type": "value_error",
        }
    ]


def test_add_story_missing_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [{"name": "greet"}, {"name": "utter_greet", "type": "BOT"}],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps", 0, "type"],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]


def test_add_story_invalid_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "data"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "ctx": {
                "enum_values": [
                    "INTENT",
                    "SLOT",
                    "FORM_START",
                    "FORM_END",
                    "BOT",
                    "HTTP_ACTION",
                    "ACTION",
                    "SLOT_SET_ACTION",
                    "FORM_ACTION",
                    "GOOGLE_SEARCH_ACTION",
                    "EMAIL_ACTION",
                    "JIRA_ACTION",
                    "ZENDESK_ACTION",
                    "PIPEDRIVE_LEADS_ACTION",
                    "HUBSPOT_FORMS_ACTION",
                    "RAZORPAY_ACTION",
                    "TWO_STAGE_FALLBACK_ACTION",
                    "PYSCRIPT_ACTION",
                    "PROMPT_ACTION",
                    "DATABASE_ACTION",
                    "WEB_SEARCH_ACTION",
                    "LIVE_AGENT_ACTION",
                    "STOP_FLOW_ACTION",
                    "CALLBACK_ACTION",
                    "SCHEDULE_ACTION",
                    "PARALLEL_ACTION",
                    "VOICE_CALL_ACTION",
                    "KAIRON_VOICE_DISCONNECT",
                    "STORE_PAGE_ACTION",
                    "AGENT_ACTION"
                ]
            },
            "loc": ["body", "steps", 0, "type"],
            "msg": "value is not a valid enumeration member; permitted: 'INTENT', 'SLOT', 'FORM_START', 'FORM_END', 'BOT', 'HTTP_ACTION', 'ACTION', 'SLOT_SET_ACTION', 'FORM_ACTION', 'GOOGLE_SEARCH_ACTION', 'EMAIL_ACTION', 'JIRA_ACTION', 'ZENDESK_ACTION', 'PIPEDRIVE_LEADS_ACTION', 'HUBSPOT_FORMS_ACTION', 'RAZORPAY_ACTION', 'TWO_STAGE_FALLBACK_ACTION', 'PYSCRIPT_ACTION', 'PROMPT_ACTION', 'DATABASE_ACTION', 'WEB_SEARCH_ACTION', 'LIVE_AGENT_ACTION', 'STOP_FLOW_ACTION', 'CALLBACK_ACTION', 'SCHEDULE_ACTION', 'PARALLEL_ACTION', 'VOICE_CALL_ACTION', 'KAIRON_VOICE_DISCONNECT', 'STORE_PAGE_ACTION', 'AGENT_ACTION'",
            "type": "type_error.enum",
        }
    ]


def test_add_multiflow_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "more_queries",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "QQAA",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "QQAA",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNXX",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_queries",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "MnveRRhd",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_queries",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_more_queries",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "MnveRRhd",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    pytest.multiflow_story_id = actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_multiflow_story_with_slot_values():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_path_with_slot",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "more_queries",
                            "type": "SLOT",
                            "value": "Yes",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "QQAA",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "QQAA",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNXX",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_queries",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "MnveRRhd",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_queries",
                        "type": "SLOT",
                        "value": "Yes",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_more_queries",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "MnveRRhd",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_multiflow_story_with_path():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_multiflow_with_path_type",
            "steps": [
                {
                    "step": {
                        "name": "hobby",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_hobby",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_hobby",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "frontend",
                            "type": "SLOT",
                            "value": "Yes",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "backend",
                            "type": "HTTP_ACTION",
                            "node_id": "4",
                            "component_id": "QQAA",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "backend",
                        "type": "HTTP_ACTION",
                        "node_id": "4",
                        "component_id": "QQAA",
                    },
                    "connections": [
                        {
                            "name": "utter_backend",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNXX",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_backend",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_frontend",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "MnveRRhd",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "frontend",
                        "type": "SLOT",
                        "value": "Yes",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_frontend",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "MnveRRhd",
                        }
                    ],
                },
            ],
            "metadata": [
                {"node_id": "5", "flow_type": "RULE"},
                {"node_id": "6", "flow_type": "STORY"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_multiflow_story_with_name_already_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "more_queries",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "MNbcg",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_queries",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_queries",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_more_queries",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "MNbcg",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Multiflow Story with the name already exists"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_add_multiflow_story_no_steps():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={"name": "test_path", "steps": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Steps are required to form Flow",
            "type": "value_error",
        }
    ]
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_add_multiflow_story_lone_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_add_multiflow_story_lone_intent",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "queries",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "MNbcg",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "queries",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    assert actual["message"] == "Leaf nodes cannot be intent"


def test_add_multiflow_story_missing_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {"name": "hi", "node_id": "1", "component_id": "MNbcg"},
                    "connections": [
                        {
                            "name": "utter_hi",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "queries",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "5",
                            "component_id": "MNbcg",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "5",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "queries",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]

    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps", 0, "step", "type"],
            "msg": "field required",
            "type": "value_error.missing",
        }
    ]


def test_add_multiflow_story_invalid_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "hi",
                        "type": "data",
                        "node_id": "1",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_hi",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcg",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    assert actual["message"] == [
        {
            "loc": ["body", "steps", 0, "step", "type"],
            "msg": "value is not a valid enumeration member; permitted: 'INTENT', 'SLOT', 'FORM_START', 'FORM_END', "
                   "'BOT', 'HTTP_ACTION', 'ACTION', 'SLOT_SET_ACTION', 'FORM_ACTION', 'GOOGLE_SEARCH_ACTION', "
                   "'EMAIL_ACTION', 'JIRA_ACTION', 'ZENDESK_ACTION', 'PIPEDRIVE_LEADS_ACTION', "
                   "'HUBSPOT_FORMS_ACTION', 'RAZORPAY_ACTION', 'TWO_STAGE_FALLBACK_ACTION', 'PYSCRIPT_ACTION', "
                   "'PROMPT_ACTION', 'DATABASE_ACTION', 'WEB_SEARCH_ACTION', 'LIVE_AGENT_ACTION', 'STOP_FLOW_ACTION', "
                   "'CALLBACK_ACTION', 'SCHEDULE_ACTION', 'PARALLEL_ACTION', 'VOICE_CALL_ACTION', 'KAIRON_VOICE_DISCONNECT', 'STORE_PAGE_ACTION', 'AGENT_ACTION'",
            "type": "type_error.enum",
            "ctx": {
                "enum_values": [
                    "INTENT",
                    "SLOT",
                    "FORM_START",
                    "FORM_END",
                    "BOT",
                    "HTTP_ACTION",
                    "ACTION",
                    "SLOT_SET_ACTION",
                    "FORM_ACTION",
                    "GOOGLE_SEARCH_ACTION",
                    "EMAIL_ACTION",
                    "JIRA_ACTION",
                    "ZENDESK_ACTION",
                    "PIPEDRIVE_LEADS_ACTION",
                    "HUBSPOT_FORMS_ACTION",
                    "RAZORPAY_ACTION",
                    "TWO_STAGE_FALLBACK_ACTION",
                    "PYSCRIPT_ACTION",
                    "PROMPT_ACTION",
                    "DATABASE_ACTION",
                    "WEB_SEARCH_ACTION",
                    "LIVE_AGENT_ACTION",
                    "STOP_FLOW_ACTION",
                    "CALLBACK_ACTION",
                    "SCHEDULE_ACTION",
                    "PARALLEL_ACTION",
                    "VOICE_CALL_ACTION",
                    "KAIRON_VOICE_DISCONNECT",
                    "STORE_PAGE_ACTION",
                    "AGENT_ACTION"
                ]
            },
        }
    ]


def test_update_story():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_path",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow updated successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_update_story_with_name_already_exists():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_add_story_consecutive_actions",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Story with the name already exists"
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_story_invalid_event_type():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_path",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "data"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "ctx": {
                "enum_values": [
                    "INTENT",
                    "SLOT",
                    "FORM_START",
                    "FORM_END",
                    "BOT",
                    "HTTP_ACTION",
                    "ACTION",
                    "SLOT_SET_ACTION",
                    "FORM_ACTION",
                    "GOOGLE_SEARCH_ACTION",
                    "EMAIL_ACTION",
                    "JIRA_ACTION",
                    "ZENDESK_ACTION",
                    "PIPEDRIVE_LEADS_ACTION",
                    "HUBSPOT_FORMS_ACTION",
                    "RAZORPAY_ACTION",
                    "TWO_STAGE_FALLBACK_ACTION",
                    "PYSCRIPT_ACTION",
                    "PROMPT_ACTION",
                    "DATABASE_ACTION",
                    "WEB_SEARCH_ACTION",
                    "LIVE_AGENT_ACTION",
                    "STOP_FLOW_ACTION",
                    "CALLBACK_ACTION",
                    "SCHEDULE_ACTION",
                    "PARALLEL_ACTION",
                    "VOICE_CALL_ACTION",
                    "KAIRON_VOICE_DISCONNECT",
                    "STORE_PAGE_ACTION",
                    "AGENT_ACTION"
                ]
            },
            "loc": ["body", "steps", 0, "type"],
            "msg": "value is not a valid enumeration member; permitted: 'INTENT', 'SLOT', 'FORM_START', 'FORM_END', 'BOT', 'HTTP_ACTION', 'ACTION', 'SLOT_SET_ACTION', 'FORM_ACTION', 'GOOGLE_SEARCH_ACTION', 'EMAIL_ACTION', 'JIRA_ACTION', 'ZENDESK_ACTION', 'PIPEDRIVE_LEADS_ACTION', 'HUBSPOT_FORMS_ACTION', 'RAZORPAY_ACTION', 'TWO_STAGE_FALLBACK_ACTION', 'PYSCRIPT_ACTION', 'PROMPT_ACTION', 'DATABASE_ACTION', 'WEB_SEARCH_ACTION', 'LIVE_AGENT_ACTION', 'STOP_FLOW_ACTION', 'CALLBACK_ACTION', 'SCHEDULE_ACTION', 'PARALLEL_ACTION', 'VOICE_CALL_ACTION', 'KAIRON_VOICE_DISCONNECT', 'STORE_PAGE_ACTION', 'AGENT_ACTION'",
            "type": "type_error.enum",
        }
    ]


def test_update_multiflow_story_with_tag():
    response = client.put(
        f"/api/bot/{pytest.bot}/v2/stories/{pytest.multiflow_story_id}",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "greeting",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_greeting",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcZZg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greeting",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "MNbcZZg",
                    },
                    "connections": [
                        {
                            "name": "more_query",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "uhsjJ",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "MgGFD",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "MgGFD",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_query",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "IIUUUYY",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_query",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "uhsjJ",
                    },
                    "connections": [
                        {
                            "name": "utter_more_query",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "IIUUUYY",
                        }
                    ],
                },
            ],
            "flow_tags": ["agentic_flow", "chatbot_flow"]
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Story flow updated successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_update_multiflow_story():
    response = client.put(
        f"/api/bot/{pytest.bot}/v2/stories/{pytest.multiflow_story_id}",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "greeting",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_greeting",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "MNbcZZg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greeting",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "MNbcZZg",
                    },
                    "connections": [
                        {
                            "name": "more_query",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "uhsjJ",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "MgGFD",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "MgGFD",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "MNbcg",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "MNbcg",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_query",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "IIUUUYY",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_query",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "uhsjJ",
                    },
                    "connections": [
                        {
                            "name": "utter_more_query",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "IIUUUYY",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["message"] == "Story flow updated successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0


def test_update_multiflow_story_with_name_already_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "another_test_path",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "63g0SIHe0vlF7BpABhUBlcOW",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "637k8PnBABFMoKiUJqQTCBRP",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "637k8PnBABFMoKiUJqQTCBRP",
                    },
                    "connections": [
                        {
                            "name": "more_queries",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "63NUrDSW34K8XzuabEwO7SJH",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "63zr5t71RcH6WZCP5kNGpZYv",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "63zr5t71RcH6WZCP5kNGpZYv",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "630r3YIqp2UhggEsIvC8Q8pC",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "630r3YIqp2UhggEsIvC8Q8pC",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_queries",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "63vwObDTOE2KLCP1FejFbSm8",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_queries",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "63NUrDSW34K8XzuabEwO7SJH",
                    },
                    "connections": [
                        {
                            "name": "utter_more_queries",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "63vwObDTOE2KLCP1FejFbSm8",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.put(
        f"/api/bot/{pytest.bot}/v2/stories/{pytest.multiflow_story_id}",
        json={
            "name": "another_test_path",
            "steps": [
                {
                    "step": {
                        "name": "greeting",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "NNNNHHG",
                    },
                    "connections": [
                        {
                            "name": "utter_greeting",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "NNNNHHG",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greeting",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "NNNNHHG",
                    },
                    "connections": [
                        {
                            "name": "more_query",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "NNNNHHG",
                        },
                        {
                            "name": "goodbye",
                            "type": "INTENT",
                            "node_id": "4",
                            "component_id": "NNNNHHG",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "goodbye",
                        "type": "INTENT",
                        "node_id": "4",
                        "component_id": "NNNNHHG",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNNNHHG",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNNNHHG",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_query",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "NNNNHHG",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_query",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "NNNNHHG",
                    },
                    "connections": [
                        {
                            "name": "utter_more_query",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "NNNNHHG",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["message"] == "Multiflow Story with the name already exists"
    assert actual["data"] is None
    assert actual["error_code"] == 422


def test_update_multiflow_story_invalid_event_type():
    response = client.put(
        f"/api/bot/{pytest.bot}/v2/stories/{pytest.multiflow_story_id}",
        json={
            "name": "test_path",
            "steps": [
                {
                    "step": {
                        "name": "hiie",
                        "type": "data",
                        "node_id": "1",
                        "component_id": "63Xx6ZbMOcBcq5Ltb1XoC3R5",
                    },
                    "connections": [
                        {
                            "name": "utter_hiie",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "63nzrQFKnrc97QOI2renluu9",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422

    assert actual["message"] == [
        {
            "loc": ["body", "steps", 0, "step", "type"],
            "msg": "value is not a valid enumeration member; permitted: 'INTENT', 'SLOT', 'FORM_START', "
                   "'FORM_END', 'BOT', 'HTTP_ACTION', 'ACTION', 'SLOT_SET_ACTION', 'FORM_ACTION', "
                   "'GOOGLE_SEARCH_ACTION', 'EMAIL_ACTION', 'JIRA_ACTION', 'ZENDESK_ACTION', "
                   "'PIPEDRIVE_LEADS_ACTION', 'HUBSPOT_FORMS_ACTION', 'RAZORPAY_ACTION', "
                   "'TWO_STAGE_FALLBACK_ACTION', 'PYSCRIPT_ACTION', 'PROMPT_ACTION', 'DATABASE_ACTION', "
                   "'WEB_SEARCH_ACTION', 'LIVE_AGENT_ACTION', 'STOP_FLOW_ACTION', 'CALLBACK_ACTION', 'SCHEDULE_ACTION', 'PARALLEL_ACTION', 'VOICE_CALL_ACTION', 'KAIRON_VOICE_DISCONNECT', 'STORE_PAGE_ACTION', 'AGENT_ACTION'",
            "type": "type_error.enum",
            "ctx": {
                "enum_values": [
                    "INTENT",
                    "SLOT",
                    "FORM_START",
                    "FORM_END",
                    "BOT",
                    "HTTP_ACTION",
                    "ACTION",
                    "SLOT_SET_ACTION",
                    "FORM_ACTION",
                    "GOOGLE_SEARCH_ACTION",
                    "EMAIL_ACTION",
                    "JIRA_ACTION",
                    "ZENDESK_ACTION",
                    "PIPEDRIVE_LEADS_ACTION",
                    "HUBSPOT_FORMS_ACTION",
                    "RAZORPAY_ACTION",
                    "TWO_STAGE_FALLBACK_ACTION",
                    "PYSCRIPT_ACTION",
                    "PROMPT_ACTION",
                    "DATABASE_ACTION",
                    "WEB_SEARCH_ACTION",
                    "LIVE_AGENT_ACTION",
                    "STOP_FLOW_ACTION",
                    "CALLBACK_ACTION",
                    "SCHEDULE_ACTION",
                    "PARALLEL_ACTION",
                    "VOICE_CALL_ACTION",
                    "KAIRON_VOICE_DISCONNECT",
                    "STORE_PAGE_ACTION",
                    "AGENT_ACTION"
                ]
            },
        }
    ]


def test_get_multiflow_stories():
    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    #
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])
    get_story = [
        x
        for x in actual["data"]
        if x["type"] == "MULTIFLOW" and x["name"] == "test_path"
    ]
    assert len(get_story) == 1
    get_story = get_story[0]
    assert get_story["type"] == "MULTIFLOW"
    assert get_story["name"] == "test_path"
    assert get_story["steps"] == [
        {
            "step": {
                "name": "greeting",
                "type": "INTENT",
                "node_id": "1",
                "component_id": "MNbcg",
            },
            "connections": [
                {
                    "name": "utter_greeting",
                    "type": "BOT",
                    "node_id": "2",
                    "component_id": "MNbcZZg",
                }
            ],
        },
        {
            "step": {
                "name": "utter_greeting",
                "type": "BOT",
                "node_id": "2",
                "component_id": "MNbcZZg",
            },
            "connections": [
                {
                    "name": "more_query",
                    "type": "INTENT",
                    "node_id": "3",
                    "component_id": "uhsjJ",
                },
                {
                    "name": "goodbye",
                    "type": "INTENT",
                    "node_id": "4",
                    "component_id": "MgGFD",
                },
            ],
        },
        {
            "step": {
                "name": "goodbye",
                "type": "INTENT",
                "node_id": "4",
                "component_id": "MgGFD",
            },
            "connections": [
                {
                    "name": "utter_goodbye",
                    "type": "BOT",
                    "node_id": "5",
                    "component_id": "MNbcg",
                }
            ],
        },
        {
            "step": {
                "name": "utter_goodbye",
                "type": "BOT",
                "node_id": "5",
                "component_id": "MNbcg",
            },
            "connections": [],
        },
        {
            "step": {
                "name": "utter_more_query",
                "type": "BOT",
                "node_id": "6",
                "component_id": "IIUUUYY",
            },
            "connections": [],
        },
        {
            "step": {
                "name": "more_query",
                "type": "INTENT",
                "node_id": "3",
                "component_id": "uhsjJ",
            },
            "connections": [
                {
                    "name": "utter_more_query",
                    "type": "BOT",
                    "node_id": "6",
                    "component_id": "IIUUUYY",
                }
            ],
        },
    ]


def test_delete_multiflow_story():
    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.multiflow_story_id}/MULTIFLOW",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow deleted successfully"


def test_delete_multiflow_non_existing_story():
    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.multiflow_story_id}/MULTIFLOW",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Flow does not exists"


def test_delete_story():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path1",
            "type": "STORY",
            "template_type": "Q&A",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet_delete", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["success"]
    assert actual["error_code"] == 0
    pytest.story_id = actual["data"]["_id"]

    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}/STORY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow deleted successfully"


def test_delete_non_existing_story():
    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}/STORY",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Flow does not exists"


def test_get_stories():
    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])
    assert actual["data"][0]["template_type"] == "CUSTOM"
    assert actual["data"][1]["template_type"] == "CUSTOM"
    assert actual["data"][16]["template_type"] == "Q&A"
    assert actual["data"][17]["template_type"] == "Q&A"
    assert actual["data"][19].get("template_type")


def test_get_utterance_from_intent():
    response = client.get(
        f"/api/bot/{pytest.bot}/utterance_from_intent/greet",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["name"] == "utter_offer_help"
    assert actual["data"]["type"] == UTTERANCE_TYPE.BOT
    assert Utility.check_empty_string(actual["message"])


def test_get_utterance_from_not_exist_intent():
    response = client.get(
        f"/api/bot/{pytest.bot}/utterance_from_intent/greeting",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["name"] is None
    assert actual["data"]["type"] is None
    assert Utility.check_empty_string(actual["message"])


def test_add_story_stop_flow_action():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_stop_flow_action",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_goodbye", "type": "BOT"},
                {"name": "utter_goodbye", "type": "BOT"},
                {"name": "stop", "type": "STOP_FLOW_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    story = next((item for item in actual['data'] if item['name'] == 'test_add_story_stop_flow_action'), None)
    assert story is not None
    assert story['steps'][-1]['name'] == 'stop_flow_action'
    assert story['steps'][-1]['type'] == 'STOP_FLOW_ACTION'


def test_add_story_stop_flow_action_not_at_end():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_stop_flow_action_not_at_end",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_goodbye", "type": "BOT"},
                {"name": "stop", "type": "STOP_FLOW_ACTION"},
                {"name": "utter_goodbye", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Stop Flow Action should only be at the end of the flow",
            "type": "value_error",
        }
    ]


def test_add_story_stop_flow_action_after_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_story_stop_flow_action_after_intent",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "stop", "type": "STOP_FLOW_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "steps"],
            "msg": "Stop Flow Action should not be after intent",
            "type": "value_error",
        }
    ]

@responses.activate
def test_upload_stop_flow_action():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/stop_flow_action/upload_story/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/stop_flow_action/upload_story/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/stop_flow_action/upload_story/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/stop_flow_action/upload_story/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/stop_flow_action/upload_story/chat_client_config.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    story = next((story_item for story_item in actual["data"] if story_item["name"] == "story_with_stop_flow_action"), None)

    assert story is not None
    assert story["steps"][-1]["name"] == "stop_flow_action"
    assert story["steps"][-1]["type"] == "STOP_FLOW_ACTION"


def test_download_story_with_stop_flow_action():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_download_story_with_stop_flow_action",
            "type": "STORY",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_goodbye", "type": "BOT"},
                {"name": "stop_flow_action", "type": "STOP_FLOW_ACTION"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/download/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    file_bytes = BytesIO(response.content)

    zip_file = ZipFile(file_bytes, mode="r")
    with zip_file.open("data/stories.yml") as file:
        stories_yaml = yaml.safe_load(file.read().decode("utf-8"))
    with zip_file.open("domain.yml") as file:
        domain_yaml = yaml.safe_load(file.read().decode("utf-8"))

    story = next((story_item for story_item in stories_yaml["stories"] if story_item["story"] == "test_download_story_with_stop_flow_action"), None)
    assert story is not None
    assert story["steps"][-1]["action"] == "action_listen"
    assert domain_yaml["actions"][-1] == "action_listen"


@responses.activate
def test_add_multiflow_story_stop_flow_action():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_add_multiflow_story_stop_flow_action",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "stop_flow",
                            "type": "STOP_FLOW_ACTION",
                            "node_id": "3",
                            "component_id": "NNXX",
                        },
                        {
                            "name": "utter_bye",
                            "type": "BOT",
                            "node_id": "4",
                            "component_id": "NNXXY",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "stop_flow",
                        "type": "STOP_FLOW_ACTION",
                        "node_id": "3",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_bye",
                        "type": "BOT",
                        "node_id": "4",
                        "component_id": "NNXXY",
                    },
                    "connections": [
                        {
                            "name": "utter_bye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNXXY",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_bye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNXXY",
                    },
                    "connections": None,
                }
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    story = next((item for item in actual['data'] if item['name'] == 'test_add_multiflow_story_stop_flow_action'), None)
    assert story is not None

    stop_flow_step = next((step for step in story['steps'] if
                           step['step']['name'] == 'stop_flow' and step['step']['type'] == 'STOP_FLOW_ACTION'), None)

    assert stop_flow_step is not None
    assert stop_flow_step['connections'] == []


def test_add_multiflow_story_stop_flow_action_not_at_end():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_stop_path",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "more_queries",
                            "type": "INTENT",
                            "node_id": "3",
                            "component_id": "MNbcg",
                        },
                        {
                            "name": "stop_flow",
                            "type": "STOP_FLOW_ACTION",
                            "node_id": "4",
                            "component_id": "QQAA",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "stop_flow",
                        "type": "STOP_FLOW_ACTION",
                        "node_id": "4",
                        "component_id": "QQAA",
                    },
                    "connections": [
                        {
                            "name": "utter_goodbye",
                            "type": "BOT",
                            "node_id": "5",
                            "component_id": "NNXX",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_goodbye",
                        "type": "BOT",
                        "node_id": "5",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_more_queries",
                        "type": "BOT",
                        "node_id": "6",
                        "component_id": "MnveRRhd",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "more_queries",
                        "type": "INTENT",
                        "node_id": "3",
                        "component_id": "MNbcg",
                    },
                    "connections": [
                        {
                            "name": "utter_more_queries",
                            "type": "BOT",
                            "node_id": "6",
                            "component_id": "MnveRRhd",
                        }
                    ],
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual['success']
    assert actual['message'] == 'STOP_FLOW_ACTION should be a leaf node!'
    assert actual["error_code"] == 422


def test_add_multiflow_story_stop_flow_action_after_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_stop_path",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "stop_flow",
                            "type": "STOP_FLOW_ACTION",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "stop_flow",
                        "type": "STOP_FLOW_ACTION",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": None,
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual['success']
    assert actual['message'] == 'STOP_FLOW_ACTION cannot be a successor of an intent!'
    assert actual["error_code"] == 422

@responses.activate
@patch.object(ModelProcessor, "is_daily_training_limit_exceeded")
def test_upload_stop_flow_action_multiflow(mock_training_limit):
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    files = (
        (
            "training_files",
            ("nlu.yml", open("tests/testing_data/stop_flow_action/upload_multiflow_story/data/nlu.yml", "rb")),
        ),
        (
            "training_files",
            ("rules.yml", open("tests/testing_data/stop_flow_action/upload_multiflow_story/data/rules.yml", "rb")),
        ),
        (
            "training_files",
            ("domain.yml", open("tests/testing_data/stop_flow_action/upload_multiflow_story/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/stop_flow_action/upload_multiflow_story/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config.yml", open("tests/testing_data/stop_flow_action/upload_multiflow_story/config.yml", "rb")),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open("tests/testing_data/stop_flow_action/upload_multiflow_story/chat_client_config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "actions.yml",
                open("tests/testing_data/stop_flow_action/upload_multiflow_story/actions.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "multiflow_stories.yml",
                open("tests/testing_data/stop_flow_action/upload_multiflow_story/multiflow_stories.yml", "rb"),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload?import_data=true&overwrite=true",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.data_importer
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/stories",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    for story in actual["data"]:
        if story.get("type") == "MULTIFLOW":
            for substep in story["steps"]:
                if substep.get("step", {}).get("name") == "stop_flow_action":
                    assert substep["connections"] == []


    mock_training_limit.return_value = False
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
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.model_training
    )


def test_download_multiflow_story_with_stop_flow_action():
    response = client.post(
        f"/api/bot/{pytest.bot}/v2/stories",
        json={
            "name": "test_download_multiflow_story_with_stop_flow_action",
            "steps": [
                {
                    "step": {
                        "name": "greet",
                        "type": "INTENT",
                        "node_id": "1",
                        "component_id": "Mnvehd",
                    },
                    "connections": [
                        {
                            "name": "utter_greet",
                            "type": "BOT",
                            "node_id": "2",
                            "component_id": "PLhfhs",
                        }
                    ],
                },
                {
                    "step": {
                        "name": "utter_greet",
                        "type": "BOT",
                        "node_id": "2",
                        "component_id": "PLhfhs",
                    },
                    "connections": [
                        {
                            "name": "stop_flow_action",
                            "type": "STOP_FLOW_ACTION",
                            "node_id": "3",
                            "component_id": "NNXX",
                        },
                        {
                            "name": "utter_bye",
                            "type": "BOT",
                            "node_id": "4",
                            "component_id": "NNXXY",
                        },
                    ],
                },
                {
                    "step": {
                        "name": "stop_flow_action",
                        "type": "STOP_FLOW_ACTION",
                        "node_id": "3",
                        "component_id": "NNXX",
                    },
                    "connections": None,
                },
                {
                    "step": {
                        "name": "utter_bye",
                        "type": "BOT",
                        "node_id": "4",
                        "component_id": "NNXXY",
                    },
                    "connections": None,
                },
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Story flow added successfully"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/download/data",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    file_bytes = BytesIO(response.content)
    zip_file = ZipFile(file_bytes, mode="r")

    with zip_file.open("multiflow_stories.yml") as file:
        multi_stories_content = yaml.safe_load(file.read().decode("utf-8"))
    with zip_file.open("domain.yml") as file:
        domain_content = yaml.safe_load(file.read().decode("utf-8"))

    events = next(block['events'] for block in multi_stories_content['multiflow_story'] if block['block_name'] == 'test_download_multiflow_story_with_stop_flow_action')

    for event in events:
        if event["step"]["name"] == "stop_flow_action":
            assert event["connections"] == []

    for event in events:
        if event["step"]["name"] == "utter_greet":
            assert any(conn["name"] == "stop_flow_action" for conn in event["connections"])

    assert domain_content['actions'][-1] == 'stop_flow_action'



@patch('kairon.shared.data.processor.MongoProcessor.get_flows_by_tag')
def test_get_flows_by_tag(mock_tag_list):
    mock_tag_list.return_value = {
        'rule': ['rule1', 'rule2'],
        'multiflow': ['multiflow1', 'multiflow2']
    }

    response = client.get(f"/api/bot/{pytest.bot}/flow_tag/agentic_flow",
                          headers={"Authorization": pytest.token_type + " " + pytest.access_token})

    assert response.status_code == 200
    data_out = response.json()
    print(data_out)
    assert data_out == {
        'data': {
            'rule': ['rule1', 'rule2'],
            'multiflow': ['multiflow1', 'multiflow2']
        },
        'error_code': 0,
        'success': True,
        'message': None
    }
    mock_tag_list.assert_called_once_with(pytest.bot, 'agentic_flow')


@responses.activate
def test_train_on_updated_data(monkeypatch):
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
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "frontend",
            "type": "text",
            "influence_conversation": True,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert "data" in actual
    assert actual["message"] == "Slot added successfully!"
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.post(
        f"/api/bot/{pytest.bot}/slots",
        json={
            "name": "more_queries",
            "type": "text",
            "influence_conversation": True,
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model training started."
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.model_training
    )


def test_download_model_training_logs(monkeypatch):
    start_date = utc_now() - timedelta(days=1)
    end_date = utc_now() + timedelta(days=1)
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/download/model_training?start_date={start_date}&end_date={end_date}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.content


@pytest.fixture
def mock_is_training_inprogress_exception(monkeypatch):
    def _inprogress_execption_response(*args, **kwargs):
        raise AppException("Previous model training in progress.")

    monkeypatch.setattr(
        ModelProcessor, "is_training_inprogress", _inprogress_execption_response
    )


def test_train_inprogress(mock_is_training_inprogress_exception):
    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is False
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Previous model training in progress."


@pytest.fixture
def mock_is_training_inprogress(monkeypatch):
    def _inprogress_response(*args, **kwargs):
        return False

    monkeypatch.setattr(ModelProcessor, "is_training_inprogress", _inprogress_response)


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_train_daily_limit_exceed(mock_request_event_server, monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.training_limit_per_day = 2
    bot_settings.save()
    response = client.post(
        f"/api/bot/{pytest.bot}/train",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Daily model training limit exceeded."


def test_get_model_training_history():
    response = client.get(
        f"/api/bot/{pytest.bot}/train/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"] is True
    assert actual["error_code"] == 0
    assert actual["data"]
    assert "training_history" in actual["data"]


def test_model_testing_limit_exceeded(monkeypatch):
    monkeypatch.setitem(Utility.environment["model"]["test"], "limit_per_day", 0)
    response = client.post(
        url=f"/api/bot/{pytest.bot}/test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Daily limit exceeded."
    assert not actual["success"]


@responses.activate
def test_model_testing_event(monkeypatch):
    bot_settings = BotSettings.objects(bot=pytest.bot).get()
    bot_settings.test_limit_per_day = 5
    bot_settings.save()
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_testing}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )
    response = client.post(
        url=f"/api/bot/{pytest.bot}/test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["message"] == "Testing in progress! Check logs."
    assert actual["success"]


@responses.activate
def test_model_testing_in_progress():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.model_testing}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    response = client.post(
        url=f"/api/bot/{pytest.bot}/test",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 422
    assert actual["message"] == "Event already in progress! Check logs."
    assert not actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "integration@demo.ai", EventClass.model_testing
    )


def test_get_model_testing_logs():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/logs/test?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["success"]

    response = client.get(
        url=f"/api/bot/{pytest.bot}/logs/test?log_type=stories&reference_id={actual['data']['logs'][0]['reference_id']}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["success"]

def test_get_model_testing_logs_new():
    response = client.get(
        url=f"/api/bot/{pytest.bot}/logs/model_test?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["success"]

def test_search_model_testing_logs():
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/model_test/search",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
          )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]

def test_search_model_testing_logs_for_from_date_and_to_date():
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/model_test/search?from_date=2025-08-01&to_date=2025-08-31",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
          )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]

def test_search_model_testing_logs_for_is_augmented_False():
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/model_test/search?is_augmented=False",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
          )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]

def test_search_model_testing_logs_is_augmented_True():
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/model_test/search?is_augmented=True",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
          )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]






def test_download_model_testing_logs(monkeypatch):
    start_date = utc_now() - timedelta(days=1)
    end_date = utc_now() + timedelta(days=1)
    response = client.get(
        f"/api/bot/{pytest.bot}/logs/download/model_testing?start_date={start_date}&end_date={end_date}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    assert response.content


def test_deploy_missing_configuration():
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Please configure the bot endpoint for deployment!"


def endpoint_response(*args, **kwargs):
    return {"bot_endpoint": {"url": "http://localhost:5000"}}


@pytest.fixture
def mock_endpoint(monkeypatch):
    monkeypatch.setattr(MongoProcessor, "get_endpoints", endpoint_response)


@pytest.fixture
def mock_endpoint_with_token(monkeypatch):
    def _endpoint_response(*args, **kwargs):
        return {
            "bot_endpoint": {
                "url": "http://localhost:5000",
                "token": "AGTSUDH!@#78JNKLD",
                "token_type": "Bearer",
            }
        }

    monkeypatch.setattr(MongoProcessor, "get_endpoints", _endpoint_response)


def test_deploy_connection_error(mock_endpoint):
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Host is not reachable"


@responses.activate
def test_deploy(mock_endpoint):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        status=204,
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model was successfully replaced."


@responses.activate
def test_deployment_history():
    response = client.get(
        f"/api/bot/{pytest.bot}/deploy/history",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["deployment_history"]) == 3
    assert actual["message"] is None


@responses.activate
def test_deploy_with_token(mock_endpoint_with_token):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        json="Model was successfully replaced.",
        headers={
            "Content-type": "application/json",
            "Accept": "text/plain",
            "Authorization": "Bearer AGTSUDH!@#78JNKLD",
        },
        status=200,
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Model was successfully replaced."


@responses.activate
def test_deploy_bad_request(mock_endpoint):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        json={
            "version": "1.0.0",
            "status": "failure",
            "reason": "BadRequest",
            "code": 400,
        },
        status=200,
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "BadRequest"


@responses.activate
def test_deploy_server_error(mock_endpoint):
    responses.add(
        responses.PUT,
        "http://localhost:5000/model",
        json={
            "version": "1.0.0",
            "status": "ServerError",
            "message": "An unexpected error occurred.",
            "code": 500,
        },
        status=200,
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/deploy",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "An unexpected error occurred."

def test_integration_token():
    response = client.post(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 1", "expiry_minutes": 1440, "role": "designer"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]
    assert (
            token["message"]
            == """This token will be shown only once. Please copy this somewhere safe. 
            It is your responsibility to keep the token secret. If leaked, others may have access to your system."""
    )

    response = client.get(
        "/api/user/details",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    ).json()
    assert len(response["data"]["user"]["bots"]["account_owned"]) == 1
    assert len(response["data"]["user"]["bots"]["shared"]) == 0

    response = client.get(
        "/api/account/bot",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    ).json()
    assert len(response["data"]["account_owned"]) == 1
    assert len(response["data"]["shared"]) == 0

    response = client.get(
        "/api/user/details",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["user"]["bots"]["account_owned"]) == 2

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 4
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])
    response = client.post(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
        json={"data": "integration"},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Intent added successfully!"


def test_integration_token_missing_x_user():
    response = client.post(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 2"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["access_token"]
    assert actual["data"]["token_type"]
    assert (
            actual["message"]
            == """This token will be shown only once. Please copy this somewhere safe. 
            It is your responsibility to keep the token secret. If leaked, others may have access to your system."""
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": actual["data"]["token_type"]
                             + " "
                             + actual["data"]["access_token"]
        },
    )
    actual = response.json()
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Alias user missing for integration"
