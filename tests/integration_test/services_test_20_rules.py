from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_get_mail_channel_logs():
    MailResponseLog(
        sender_id="chocoboyxp@gmail.com",
        uid=4337,
        responses=[
            {
                "recipient_id": "spandan.mondal@nimblework.com",
                "text": "How may i help you?"
            }
        ],
        slots={
            "doc_url": "None",
            "document": "None",
            "video": "None",
            "audio": "None",
            "image": "None",
            "kairon_action_response": "None",
            "bot": "67e24b3847fb806ba96ff494",
            "session_started_metadata": "{'channel': 'mail', 'tabname': 'default', 'is_integration_user': False, 'bot': '64a43ce6af92e374371ed5bd', 'account': 1048, 'channel_type': 'chat_client'}",
            "bot_response": "How may i help you?"
        },
        bot=pytest.bot,
        user="spandan.mondal@nimblework.com",
        status=MailStatus.SUCCESS.value
    ).save()

    response = client.get(
        f"/api/bot/{pytest.bot}/logs/mail_channel",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    print(response.json())
    from_date = utc_now().date() - timedelta(days=1)
    to_date = utc_now().date() + timedelta(days=1)
    search_response = client.get(
        f"/api/bot/{pytest.bot}/logs/mail_channel/search"
        f"?from_date={from_date}&to_date={to_date}&status=success",
        headers={"Authorization": f"{pytest.token_type} {pytest.access_token}"},
    )
    response_json = search_response.json()
    print("actions:", response_json)
    assert response_json["success"] is True
    assert response_json["error_code"] == 0
    data = response_json["data"]
    assert "logs" in data
    assert isinstance(data["logs"], list)


def test_feedback():
    request = {
        "rating": 5.0,
        "scale": 5.0,
        "feedback": "The product is better than rasa.",
    }
    response = client.post(
        f"/api/account/feedback",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Thanks for your feedback!"


def test_add_rule():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"
    assert actual["data"]["_id"]
    pytest.story_id = actual["data"]["_id"]


def test_add_rule_with_name_already_exists():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "ask the user to rephrase whenever they send a message with low nlu confidence",
            "type": "RULE",
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
    assert actual["data"] is None
    assert actual["message"] == "Rule with the name already exists"


def test_add_rule_invalid_type():
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


def test_add_rule_empty_event():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={"name": "test_add_rule_empty_event", "type": "RULE", "steps": []},
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


def test_add_rule_lone_intent():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_lone_intent",
            "type": "RULE",
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


def test_add_rule_consecutive_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_consecutive_intents",
            "type": "RULE",
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


def test_add_rule_multiple_actions():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_consecutive_actions",
            "type": "RULE",
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


def test_add_rule_utterance_as_first_step():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_add_rule_consecutive_intents",
            "type": "RULE",
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


def test_add_rule_missing_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
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


def test_add_rule_invalid_event_type():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
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

def test_update_rule_with_tag():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
            "flow_tags": ["agentic_flow"]
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow updated successfully"
    assert actual["data"]["_id"]



def test_update_rule():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow updated successfully"
    assert actual["data"]["_id"]


def test_update_rule_with_name_already_exists():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_add_rule_consecutive_actions",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_nonsense", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["message"] == "Rule with the name already exists"
    assert actual["data"] is None
    assert not actual["success"]
    assert actual["error_code"] == 422


def test_update_rule_invalid_event_type():
    response = client.put(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}",
        json={
            "name": "test_path",
            "type": "RULE",
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


def test_delete_rule():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path1",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
            ],
        },
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow added successfully"
    pytest.story_id = actual["data"]["_id"]

    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}/RULE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Flow deleted successfully"


def test_delete_non_existing_rule():
    response = client.delete(
        f"/api/bot/{pytest.bot}/stories/{pytest.story_id}/RULE",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Flow does not exists"


def test_add_rule_with_multiple_intents():
    response = client.post(
        f"/api/bot/{pytest.bot}/stories",
        json={
            "name": "test_path",
            "type": "RULE",
            "steps": [
                {"name": "greet", "type": "INTENT"},
                {"name": "utter_greet", "type": "BOT"},
                {"name": "location", "type": "INTENT"},
                {"name": "utter_location", "type": "BOT"},
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
            "msg": "Found rules 'test_path' that contain more than intent.\nPlease use stories for this case",
            "type": "value_error",
        }
    ]
    assert actual["data"] is None


@responses.activate
def test_validate():
    event_url = urljoin(
        Utility.environment["events"]["server_url"],
        f"/api/events/execute/{EventClass.data_importer}",
    )
    responses.add(
        "POST",
        event_url,
        json={"success": True, "message": "Event triggered successfully!"},
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/validate",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not actual["data"]
    assert actual["message"] == "Event triggered! Check logs."
    complete_end_to_end_event_execution(
        pytest.bot, "test_user", EventClass.data_importer
    )


@responses.activate
def test_upload_missing_data():
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
            (
                "domain.yml",
                BytesIO(open("tests/testing_data/all/domain.yml", "rb").read()),
            ),
        ),
        (
            "training_files",
            (
                "stories.yml",
                BytesIO(open("tests/testing_data/all/data/stories.yml", "rb").read()),
            ),
        ),
        (
            "training_files",
            (
                "config.yml",
                BytesIO(open("tests/testing_data/all/config.yml", "rb").read()),
            ),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "test_user", EventClass.data_importer
    )


@responses.activate
def test_upload_valid_and_invalid_data():
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
        ("training_files", ("nlu_1.yml", b"")),
        (
            "training_files",
            ("domain_5.yml", open("tests/testing_data/all/domain.yml", "rb")),
        ),
        (
            "training_files",
            ("stories.yml", open("tests/testing_data/all/data/stories.yml", "rb")),
        ),
        (
            "training_files",
            ("config_6.yml", open("tests/testing_data/all/config.yml", "rb")),
        ),
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "test_user", EventClass.data_importer
    )


def test_upload_with_http_error():
    config = Utility.load_yaml("./tests/testing_data/yml_training_files/config.yml")
    config.get("pipeline").append({"name": "XYZ"})
    files = (
        ("training_files", ("config.yml", json.dumps(config).encode())),
        (
            "training_files",
            ("actions.yml", open("tests/testing_data/error/actions.yml", "rb")),
        ),
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 4
    assert actual["data"]["total"] == 4
    assert actual["data"]["logs"][0]["status"] == STATUSES.FAIL.value
    assert actual["data"]["logs"][0]["event_status"] == EVENT_STATUS.COMPLETED.value
    assert actual["data"]["logs"][0]["is_data_uploaded"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert actual["data"]["logs"][0]["start_timestamp"]
    assert (
            "Required fields {'request_method'} not found"
            in str(actual["data"]["logs"][0]["actions"][0]["data"][0])
    )
    assert actual["data"]["logs"][0]["config"]["data"] == ["Invalid component XYZ"]


def test_upload_actions_and_config():
    files = (
        (
            "training_files",
            (
                "config.yml",
                open("tests/testing_data/yml_training_files/config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "actions.yml",
                open("tests/testing_data/yml_training_files/actions.yml", "rb"),
            ),
        ),
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]["logs"]) == 5
    assert actual["data"]["total"] == 5
    assert actual['data']["logs"][0]['status'] == STATUSES.SUCCESS.value
    assert actual['data']["logs"][0]['event_status'] == EVENT_STATUS.COMPLETED.value
    assert actual['data']["logs"][0]['is_data_uploaded']
    assert actual['data']["logs"][0]['start_timestamp']
    assert actual['data']["logs"][0]['end_timestamp']
    print(actual['data']["logs"][0]['actions'])
    assert actual['data']["logs"][0]['actions'] == [{'type': 'http_actions', 'count': 17, 'data': []},
                                                    {'type': 'two_stage_fallbacks', 'count': 0, 'data': []},
                                                    {'type': 'email_actions', 'count': 0, 'data': []},
                                                    {'type': 'zendesk_actions', 'count': 0, 'data': []},
                                                    {'type': 'jira_actions', 'count': 0, 'data': []},
                                                    {'type': 'form_validation_actions', 'count': 1, 'data': []},
                                                    {'type': 'slot_set_actions', 'count': 0, 'data': []},
                                                    {'type': 'google_search_actions', 'count': 1, 'data': []},
                                                    {'type': 'pipedrive_leads_actions', 'count': 0, 'data': []},
                                                    {'type': 'prompt_actions', 'count': 0, 'data': []},
                                                    {'type': 'web_search_actions', 'count': 0, 'data': []},
                                                    {'type': 'razorpay_actions', 'count': 0, 'data': []},
                                                    {'type': 'pyscript_actions', 'count': 0, 'data': []},
                                                    {'type': 'database_actions', 'count': 0, 'data': []},
                                                    {'type': 'live_agent_actions', 'count': 0, 'data': []},
                                                    {'type': 'callback_actions', 'count': 0, 'data': []},
                                                    {'type': 'schedule_actions', 'count': 0, 'data': []},
                                                    {'type': 'parallel_actions', 'count': 0, 'data': []},
                                                    {'type': 'voice_call_actions', 'count': 0, 'data': []},
                                                    {'type': 'store_page_actions', 'count': 0, 'data': []},
                                                    {'type': 'agent_actions', 'count': 0, 'data': []}]
    assert not actual['data']["logs"][0]['config']['data']

    response = client.get(
        f"/api/bot/{pytest.bot}/action/httpaction",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert len(actual["data"]) == 17


@patch(
    "kairon.shared.importer.processor.DataImporterLogProcessor.is_limit_exceeded",
    autospec=True,
)
@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_upload_multiflow_stories(mock_is_limit_exceeded, mock_event_server):
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
            (
                "domain.yml",
                open("tests/testing_data/yml_training_files/domain.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "nlu.yml",
                open("tests/testing_data/yml_training_files/data/nlu.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "stories.yml",
                open("tests/testing_data/yml_training_files/data/stories.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "rules.yml",
                open("tests/testing_data/yml_training_files/data/rules.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "actions.yml",
                open("tests/testing_data/yml_training_files/actions.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "chat_client_config.yml",
                open(
                    "tests/testing_data/yml_training_files/chat_client_config.yml", "rb"
                ),
            ),
        ),
        (
            "training_files",
            (
                "config.yml",
                open("tests/testing_data/yml_training_files/config.yml", "rb"),
            ),
        ),
        (
            "training_files",
            (
                "multiflow_stories.yml",
                open(
                    "tests/testing_data/yml_training_files/multiflow_stories.yml", "rb"
                ),
            ),
        ),
    )
    mock_is_limit_exceeded.return_value = False
    response = client.post(
        f"/api/bot/{pytest.bot}/upload",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        files=files,
    )
    actual = response.json()
    assert actual["message"] == "Upload in progress! Check logs."
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["success"]
    complete_end_to_end_event_execution(
        pytest.bot, "test_user", EventClass.data_importer
    )

    response = client.get(
        f"/api/bot/{pytest.bot}/importer/logs?start_idx=0&page_size=10",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()

    assert actual["success"]
    assert actual["error_code"] == 0
    assert set(actual["data"]["logs"][0]["files_received"]) == {
        "rules",
        "stories",
        "nlu",
        "domain",
        "config",
        "actions",
        "chat_client_config",
        "multiflow_stories",
    }


def test_get_editable_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert not DeepDiff(
        actual["data"],
        {
            "nlu_confidence_threshold": 0.75,
            "action_fallback": "action_small_talk",
            "action_fallback_threshold": 0.3,
            "ted_epochs": 5,
            "nlu_epochs": 5,
            "response_epochs": 5,
        },
        ignore_order=True,
    )


def test_set_epoch_and_fallback():
    request = {
        "nlu_epochs": 200,
        "response_epochs": 100,
        "ted_epochs": 150,
        "nlu_confidence_threshold": 0.7,
        "action_fallback_threshold": 0.3,
        "action_fallback": "action_default_fallback",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/response/utter_default",
        json={"data": "Sorry I didnt get that. Can you rephrase?"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"]["_id"]
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Response added!"

    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved"


def test_get_config_all():
    response = client.get(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]


def test_set_epoch_and_fallback_modify_action_only():
    request = {"nlu_confidence_threshold": 0.3, "action_fallback": "utter_default"}
    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Config saved"


def test_set_epoch_and_fallback_empty_pipeline_and_policies():
    request = {"nlu_confidence_threshold": 20}
    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=request,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "nlu_confidence_threshold"],
            "msg": "Please choose a threshold between 0.3 and 0.9",
            "type": "value_error",
        }
    ]


def test_set_epoch_and_fallback_empty_request():
    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "At least one field is required"


def test_set_epoch_and_fallback_negative_epochs():
    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"nlu_epochs": 0},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "nlu_epochs"],
            "msg": "Choose a positive number as epochs",
            "type": "value_error",
        }
    ]

    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"response_epochs": -1, "ted_epochs": 0, "nlu_epochs": 200},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0] == {
        "loc": ["body", "response_epochs"],
        "msg": "Choose a positive number as epochs",
        "type": "value_error",
    }
    assert actual["message"][1] == {
        "loc": ["body", "ted_epochs"],
        "msg": "Choose a positive number as epochs",
        "type": "value_error",
    }


def test_set_epoch_and_fallback_max_epochs():
    epoch_max_limit = Utility.environment["model"]["config_properties"][
        "epoch_max_limit"
    ]
    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"nlu_epochs": epoch_max_limit + 1},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "nlu_epochs"],
            "msg": f"Please choose a epoch between 1 and {epoch_max_limit}",
            "type": "value_error",
        }
    ]

    response = client.put(
        f"/api/bot/{pytest.bot}/config/properties",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={
            "response_epochs": -1,
            "ted_epochs": epoch_max_limit + 1,
            "nlu_epochs": 200,
        },
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0] == {
        "loc": ["body", "response_epochs"],
        "msg": "Choose a positive number as epochs",
        "type": "value_error",
    }
    assert actual["message"][1] == {
        "loc": ["body", "ted_epochs"],
        "msg": f"Please choose a epoch between 1 and {epoch_max_limit}",
        "type": "value_error",
    }


def test_get_synonyms():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert "data" in actual
    assert len(actual["data"]) == 0
    assert actual["success"]
    assert actual["error_code"] == 0
    assert Utility.check_empty_string(actual["message"])


def test_add_synonym_values():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym",
        json={"data": "bot_add"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym added!"
    assert actual["data"]["_id"]

    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        json={"value": ["any"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym values added!"
    assert all(
        key in item.keys() for item in actual["data"] for key in ["_id", "value"]
    )

    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/value",
        json={"data": "any1"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym value added!"
    assert actual["data"]["_id"]

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert all(item["value"] in ["any", "any1"] for item in actual["data"])
    assert all(
        key in item.keys()
        for item in actual["data"]
        for key in ["_id", "synonym", "value"]
    )


def test_get_specific_synonym_values():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 2


def test_add_synonyms_duplicate():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        json={"value": ["any"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Synonym value already exists"


def test_add_synonyms_value_empty():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        json={"value": []},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]["msg"] == "value field cannot be empty"


def test_add_synonyms_empty():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/%20/values",
        json={"value": ["h"]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Synonym name cannot be an empty!"


def test_edit_synonyms():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    response = client.put(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/value/{actual['data'][0]['_id']}",
        json={"data": "any4"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym value updated!"

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"])
    assert any(item["value"] == "any4" for item in actual["data"])


def test_delete_synonym_one_value():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()

    response = client.delete(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/value/{actual['data'][0]['_id']}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym value removed!"

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert len(actual["data"]) == 1


def test_delete_synonym():
    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"]
    assert all(
        key in item.keys() for item in actual["data"] for key in ["_id", "synonym"]
    )

    synonym_id = actual["data"][0]["_id"]
    synonym_name = actual["data"][0]["synonym"]
    response = client.delete(
        f"/api/bot/{pytest.bot}/entity/synonym/{synonym_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Synonym removed!"

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonyms",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] == []

    response = client.get(
        f"/api/bot/{pytest.bot}/entity/synonym/{synonym_name}/values",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["data"] == []


def test_add_synonyms_empty_value_element():
    response = client.post(
        f"/api/bot/{pytest.bot}/entity/synonym/bot_add/values",
        json={"value": ["df", ""]},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"][0]["msg"] == "value cannot be an empty string"
