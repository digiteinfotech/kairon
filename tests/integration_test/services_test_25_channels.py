from tests.integration_test.services_support import *  # noqa: F403
from tests.integration_test.services_support import setup, fast_rasa_training



def test_disable_integration_token():
    response = client.put(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 3", "status": "inactive"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Integration status updated!"


def test_list_integrations_after_disable():
    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["name"] == "integration 1"
    assert actual["data"][0]["user"] == "integ1@gmail.com"
    assert actual["data"][0]["iat"]
    assert actual["data"][0]["status"] == "active"
    assert actual["data"][0]["role"] == "designer"
    assert actual["data"][1]["name"] == "integration 3"
    assert actual["data"][1]["user"] == "integ1@gmail.com"
    assert actual["data"][1]["iat"]
    assert actual["data"][1]["status"] == "inactive"
    assert actual["data"][1]["role"] == "designer"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_use_inactive_token():
    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": pytest.disable_token,
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert actual["message"] == "Access to bot is denied"
    assert not actual["success"]
    assert actual["error_code"] == 401

    response = client.put(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 3", "status": "active", "role": "tester"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0

    response = client.get(
        f"/api/bot/{pytest.bot}/intents",
        headers={
            "Authorization": pytest.disable_token,
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]


def test_delete_integration_token():
    response = client.put(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 3", "status": "deleted"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Integration status updated!"

    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert len(actual["data"]) == 1


def test_integration_token_from_one_bot_on_another_bot():
    response = client.post(
        "/api/account/bot",
        json={"name": "demo-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert response["message"] == "Bot created"
    assert response["error_code"] == 0
    assert response["success"]

    response = client.get(
        "/api/account/bot",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    ).json()
    assert len(response["data"]["account_owned"]) == 1
    assert len(response["data"]["shared"]) == 3
    bot1 = response["data"]["account_owned"][0]["_id"]
    bot2 = response["data"]["shared"][0]["_id"]

    response = client.post(
        f"/api/auth/{bot2}/integration/token",
        json={"name": "integration 4", "expiry_minutes": 1440},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    token = response.json()
    assert token["success"]
    assert token["error_code"] == 0
    assert token["data"]["access_token"]
    assert token["data"]["token_type"]

    response = client.get(
        f"/api/bot/{bot1}/intents",
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert actual["message"] == "Access to bot is denied"
    assert not actual["success"]
    assert actual["error_code"] == 401

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
    assert (
            actual["message"]
            == "['owner', 'admin', 'designer', 'tester'] access is required to perform this operation on the bot"
    )
    assert not actual["success"]
    assert actual["error_code"] == 401

    response = client.post(
        f"/api/bot/{pytest.bot}/chat",
        json={"data": "hi"},
        headers={
            "Authorization": token["data"]["token_type"]
                             + " "
                             + token["data"]["access_token"],
            "X-USER": "integration",
        },
    )
    actual = response.json()
    assert actual["error_code"] != 401


def test_integration_limit_reached(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(bot=pytest.bot, user="integration@demo.ai", integrations_per_user_limit=2)

    monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)

    response = client.post(
        f"/api/auth/{pytest.bot}/integration/token",
        json={"name": "integration 4", "expiry_minutes": 1440},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    token = response.json()
    assert not token["success"]
    assert token["error_code"] == 422
    assert token["message"] == "Integrations limit reached!"
    assert not token["data"]


def test_list_integrations():
    response = client.get(
        f"/api/auth/{pytest.bot}/integration/token/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["data"][0]["name"] == "integration 1"
    assert actual["data"][0]["user"] == "integ1@gmail.com"
    assert actual["data"][0]["iat"]
    assert actual["data"][0]["status"] == "active"
    assert actual["data"][1]["name"] == "integration 4"
    assert actual["data"][1]["user"] == "integ1@gmail.com"
    assert actual["data"][1]["iat"]
    assert actual["data"][1]["expiry"]
    assert actual["data"][1]["status"] == "active"
    assert actual["success"]
    assert actual["error_code"] == 0


def test_add_channel_config_error():
    data = {
        "connector_type": "custom",
        "config": {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
            "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",
            "client_id": "3396830255712.3396861654876869879",
            "client_secret": "cf92180a7634d90bf42a217408376878",
        },
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/add",
        json=data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "Invalid channel type custom",
            "type": "value_error",
        }
    ]

    data = {
        "connector_type": "slack",
        "config": {"slack_signing_secret": "79f036b9894eef17c064213b90d1042b"},
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/add",
        json=data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "Missing ['bot_user_oAuth_token', 'slack_signing_secret', 'client_id', 'client_secret'] all or any in config",
            "type": "value_error",
        }
    ]

    data = {
        "connector_type": "slack",
        "config": {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K"
        },
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/add",
        json=data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "Missing ['bot_user_oAuth_token', 'slack_signing_secret', 'client_id', 'client_secret'] all or any in config",
            "type": "value_error",
        }
    ]

    data = {
        "connector_type": "slack",
        "config": {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
            "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",
            "client_id": "3396830255712.3396861654876869879",
            "client_secret": "cf92180a7634d90bf42a217408376878",
            "is_primary": False,
        },
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/add",
        json=data,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "Cannot edit secondary slack app. Please delete and install the app again using oAuth."
    )


def test_add_bot_with_template_name(monkeypatch):
    from kairon.shared.admin.data_objects import BotSecrets

    def mock_reload_model(*args, **kwargs):
        mock_reload_model.called_with = (args, kwargs)
        return None

    monkeypatch.setattr(Utility, "reload_model", mock_reload_model)
    monkeypatch.setitem(Utility.environment["llm"], "key", "secret_value")

    response = client.post(
        "/api/account/bot",
        json={"name": "hi-hello-gpt-bot", "from_template": "Hi-Hello-GPT"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response["message"] == "Bot created"
    assert response["error_code"] == 0
    assert response["success"]
    assert response["data"]["bot_id"]
    bot_id = response["data"]["bot_id"]
    response = client.get(
        url=f"/api/bot/{bot_id}/actions",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not DeepDiff(
        actual["data"],
        {
            "prompt_action": ["kairon_faq_action"],
            "web_search_action": ["google_search_action"],
            "utterances": ["utter_please_rephrase", "utter_default"],
            "http_action": [],
            "slot_set_action": [],
            "form_validation_action": [],
            "email_action": [],
            "google_search_action": [],
            "jira_action": [],
            "zendesk_action": [],
            "pipedrive_leads_action": [],
            "hubspot_forms_action": [],
            "two_stage_fallback": [],
            "kairon_bot_response": [],
            "razorpay_action": [],
            "database_action": [],
            "actions": [],
            "pyscript_action": [],
            "live_agent_action": [],
            "callback_action": [],
            "schedule_action": [],
            "parallel_action": [],
            "voice_call_action": [],
            "kairon_voice_disconnect": [],
            "store_page_action": [],
            "agent_action": []
        },
        ignore_order=True,
    )
    bot_secret = (
        BotSecrets.objects(bot=bot_id, secret_type="gpt_key").get().to_mongo().to_dict()
    )
    assert bot_secret["secret_type"] == "gpt_key"
    assert Utility.decrypt_message(bot_secret["value"]) == "secret_value"
    assert len(mock_reload_model.called_with[0]) == 2
    assert mock_reload_model.called_with[0][0] == bot_id
    assert mock_reload_model.called_with[0][1] == "integ1@gmail.com"


def test_set_templates_with_sysadmin_as_user():
    response = client.post(
        f"/api/bot/{pytest.bot}/templates/use-case",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json={"data": "Hi-Hello-GPT"},
    )

    actual = response.json()
    assert actual["data"] is None
    assert actual["error_code"] == 0
    assert actual["message"] == "Data applied!"
    assert actual["success"]

    stories = Stories.objects(bot=pytest.bot)
    stories = [{k: v for k, v in story.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
               story in stories]

    assert stories == [
        {'block_name': 'greet', 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': 'greet', 'type': 'user', 'entities': []},
                    {'name': 'google_search_action', 'type': 'action'},
                    {'name': 'kairon_faq_action', 'type': 'action'}],
         'user': 'sysadmin', 'status': True, 'template_type': 'CUSTOM'},
        {'block_name': 'goodbye', 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': 'goodbye', 'type': 'user', 'entities': []},
                    {'name': 'google_search_action', 'type': 'action'},
                    {'name': 'kairon_faq_action', 'type': 'action'}],
         'user': 'sysadmin', 'status': True, 'template_type': 'CUSTOM'}
    ]

    intents = Intents.objects(bot=pytest.bot)
    intents = [{k: v for k, v in intent.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
               intent in intents]

    assert intents == [
        {'name': 'greet', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'goodbye', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'nlu_fallback', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False}
    ]

    training_examples = TrainingExamples.objects(bot=pytest.bot)
    training_examples = [{k: v for k, v in example.to_mongo().to_dict().items() if k not in
                          ['_id', 'bot', 'timestamp']} for example in training_examples]

    assert training_examples == [
        {'intent': 'goodbye', 'text': 'bye', 'user': 'sysadmin', 'status': True},
        {'intent': 'goodbye', 'text': 'goodbye', 'user': 'sysadmin', 'status': True},
        {'intent': 'goodbye', 'text': 'see you around', 'user': 'sysadmin', 'status': True},
        {'intent': 'goodbye', 'text': 'see you later', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'hey', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'hello', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'hi', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'good morning', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'good evening', 'user': 'sysadmin', 'status': True},
        {'intent': 'greet', 'text': 'hey there', 'user': 'sysadmin', 'status': True}
    ]


def test_add_channel_config(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost:5056"
    )
    data = {
        "connector_type": "slack",
        "config": {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
            "slack_signing_secret": "79f036b9894eef17c064213b90d1042b",
            "client_id": "3396830255712.3396861654876869879",
            "client_secret": "cf92180a7634d90bf42a217408376878",
        },
    }
    with patch("slack_sdk.web.client.WebClient.team_info") as mock_slack_resp:
        mock_slack_resp.return_value = SlackResponse(
            client=None,
            http_verb="POST",
            api_url="https://slack.com/api/team.info",
            req_args={},
            data={
                "ok": True,
                "team": {
                    "id": "T03BNQE7HLX",
                    "name": "helicopter",
                    "avatar_base_url": "https://ca.slack-edge.com/",
                    "is_verified": False,
                },
            },
            headers=dict(),
            status_code=200,
        ).validate()
        response = client.post(
            f"/api/bot/{pytest.bot}/channels/add",
            json=data,
            headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Channel added"
    assert actual["data"].startswith(
        f"http://localhost:5056/api/bot/slack/{pytest.bot}/e"
    )


def test_add_bot_with_template_with_sysadmin_as_user(monkeypatch):
    def mock_reload_model(*args, **kwargs):
        mock_reload_model.called_with = (args, kwargs)
        return None

    monkeypatch.setattr(Utility, "reload_model", mock_reload_model)
    monkeypatch.setitem(Utility.environment["llm"], "key", "secret_value")

    response = client.post(
        "/api/account/bot",
        json={"name": "gpt-bot", "from_template": "Hi-Hello-GPT"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response["message"] == "Bot created"
    assert response["data"] is not None
    assert response["error_code"] == 0
    assert response["success"]
    bot_id = response["data"]["bot_id"]

    stories = Stories.objects(bot=bot_id)
    stories = [{k: v for k, v in story.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
               story in stories]

    assert stories == [
        {'block_name': 'greet', 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': 'greet', 'type': 'user', 'entities': []},
                    {'name': 'google_search_action', 'type': 'action'},
                    {'name': 'kairon_faq_action', 'type': 'action'}],
         'user': 'sysadmin', 'status': True, 'template_type': 'CUSTOM'},
        {'block_name': 'goodbye', 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': 'goodbye', 'type': 'user', 'entities': []},
                    {'name': 'google_search_action', 'type': 'action'},
                    {'name': 'kairon_faq_action', 'type': 'action'}],
         'user': 'sysadmin', 'status': True, 'template_type': 'CUSTOM'}
    ]

    rules = Rules.objects(bot=bot_id)
    rules = [{k: v for k, v in rule.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
             rule in rules]

    assert rules == [
        {'block_name': 'ask the user to rephrase whenever they send a message with low nlu confidence',
         'condition_events_indices': [], 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': '...', 'type': 'action'},
                    {'name': 'nlu_fallback', 'type': 'user', 'entities': []},
                    {'name': 'google_search_action', 'type': 'action'},
                    {'name': 'kairon_faq_action', 'type': 'action'}],
         'user': 'sysadmin', 'status': True, 'template_type': 'CUSTOM', 'flow_tags': ['chatbot_flow']}
    ]

    utterances = Utterances.objects(bot=bot_id)
    utterances = [{k: v for k, v in utterance.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
                  utterance in utterances]

    assert utterances == [
        {'name': 'utter_please_rephrase', 'user': 'sysadmin', 'status': True},
        {'name': 'utter_default', 'user': 'sysadmin', 'status': True}
    ]

    intents = Intents.objects(bot=bot_id)
    intents = [{k: v for k, v in intent.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
               intent in intents]

    assert intents == [
        {'name': 'greet', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'goodbye', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'nlu_fallback', 'user': 'sysadmin', 'status': True, 'is_integration': False, 'use_entities': False}
    ]

    responses = Responses.objects(bot=bot_id)
    responses = [{k: v for k, v in response.to_mongo().to_dict().items() if k not in
                  ['_id', 'bot', 'timestamp']} for response in responses]

    assert responses == [
        {'name': 'utter_please_rephrase',
         'text': {'text': "I'm sorry, I didn't quite understand that. Could you rephrase?"},
         'user': 'sysadmin', 'status': True},
        {'name': 'utter_default', 'text': {'text': "Sorry I didn't get that. Can you rephrase?"},
         'user': 'sysadmin', 'status': True}
    ]


def test_add_bot_without_template(monkeypatch):
    def mock_reload_model(*args, **kwargs):
        mock_reload_model.called_with = (args, kwargs)
        return None

    monkeypatch.setattr(Utility, "reload_model", mock_reload_model)
    monkeypatch.setitem(Utility.environment["llm"], "key", "secret_value")

    response = client.post(
        "/api/account/bot",
        json={"name": "normal-bot"},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response = response.json()
    assert response["message"] == "Bot created"
    assert response["data"] is not None
    assert response["error_code"] == 0
    assert response["success"]
    bot_id = response["data"]["bot_id"]

    rules = Rules.objects(bot=bot_id)
    rules = [{k: v for k, v in rule.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
             rule in rules]

    assert rules == [
        {'block_name': 'ask the user to rephrase whenever they send a message with low nlu confidence',
         'condition_events_indices': [], 'start_checkpoints': ['STORY_START'], 'end_checkpoints': [],
         'events': [{'name': '...', 'type': 'action'}, {'name': 'nlu_fallback', 'type': 'user'},
                    {'name': 'utter_please_rephrase', 'type': 'action'}],
         'user': 'integ1@gmail.com', 'status': True, 'template_type': 'CUSTOM', 'flow_tags': ['chatbot_flow']},
        {'block_name': 'bye', 'condition_events_indices': [], 'start_checkpoints': ['STORY_START'],
         'end_checkpoints': [],
         'events': [{'name': '...', 'type': 'action'}, {'name': 'bye', 'type': 'user'},
                    {'name': 'utter_bye', 'type': 'action'}], 'user': 'integ1@gmail.com',
         'status': True, 'template_type': 'Q&A',  'flow_tags': ['chatbot_flow']},
        {'block_name': 'greet', 'condition_events_indices': [], 'start_checkpoints': ['STORY_START'],
         'end_checkpoints': [],
         'events': [{'name': '...', 'type': 'action'}, {'name': 'greet', 'type': 'user'},
                    {'name': 'utter_greet', 'type': 'action'}],
         'user': 'integ1@gmail.com', 'status': True, 'template_type': 'Q&A',  'flow_tags': ['chatbot_flow']}
    ]

    utterances = Utterances.objects(bot=bot_id)
    utterances = [{k: v for k, v in utterance.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
                  utterance in utterances]

    assert utterances == [
        {'name': 'utter_please_rephrase', 'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_default', 'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_bye', 'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_greet', 'user': 'integ1@gmail.com', 'status': True}
    ]

    intents = Intents.objects(bot=bot_id)
    intents = [{k: v for k, v in intent.to_mongo().to_dict().items() if k not in ['_id', 'bot', 'timestamp']} for
               intent in intents]

    assert intents == [
        {'name': 'bye', 'user': 'integ1@gmail.com', 'status': True, 'is_integration': False, 'use_entities': False},
        {'name': 'greet', 'user': 'integ1@gmail.com', 'status': True, 'is_integration': False, 'use_entities': False}
    ]

    training_examples = TrainingExamples.objects(bot=bot_id)
    training_examples = [{k: v for k, v in training_example.to_mongo().to_dict().items() if k not in
                          ['_id', 'bot', 'timestamp']} for training_example in training_examples]

    assert training_examples == [
        {'intent': 'bye', 'text': 'good bye', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'bye', 'text': 'bye', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'bye', 'text': 'See you later!', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'bye', 'text': 'Goodbye!', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Hi', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Hello', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Greetings', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Hi there', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Good day', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Howdy', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Hey there', 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': "What's up?", 'user': 'integ1@gmail.com', 'status': True},
        {'intent': 'greet', 'text': 'Hullo', 'user': 'integ1@gmail.com', 'status': True}
    ]

    responses = Responses.objects(bot=bot_id)
    responses = [{k: v for k, v in response.to_mongo().to_dict().items() if k not in
                  ['_id', 'bot', 'timestamp']} for response in responses]

    assert responses == [
        {'name': 'utter_please_rephrase',
         'text': {'text': "I'm sorry, I didn't quite understand that. Could you rephrase?"},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_default', 'text': {'text': "Sorry I didn't get that. Can you rephrase?"},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_bye', 'text': {'text': "Take care, I'm here for you if you need anything."},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_bye', 'text': {'text': 'Adieu, always here for you.'},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_bye', 'text': {'text': "See you later, I'm here to help."},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_greet', 'text': {'text': "I'm your AI Assistant, ready to assist"},
         'user': 'integ1@gmail.com', 'status': True},
        {'name': 'utter_greet', 'text': {'text': 'Let me be your AI Assistant and provide you with service'},
         'user': 'integ1@gmail.com', 'status': True}
    ]


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
def test_add_template_error(mock_get_partner_auth_token):
    mock_get_partner_auth_token.return_value = "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"
    data = {
        "name": "Introduction template",
        "category": "UTILITY",
        "components": [
            {
                "format": "TEXT",
                "text": "New request",
                "type": "HEADER"
            },
            {
                "type": "BODY",
                "text": "Hi {{1}}, thanks for getting in touch with {{2}}. We will process your request get back to you shortly",
                "example": {
                    "body_text": [
                        [
                            "Nupur",
                            "360dialog"
                        ]
                    ]
                }
            },
            {
                "text": "WhatsApp Business API provided by 360dialog",
                "type": "FOOTER"
            }
        ],
        "language": "es_ES",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog",
        json={'data': data},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Channel not found!"
    assert actual["data"] == None


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
def test_edit_template_error(mock_get_partner_auth_token):
    mock_get_partner_auth_token.return_value = "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"
    data = {
        "components": [
            {
                "format": "TEXT",
                "text": "New request",
                "type": "HEADER"
            },
            {
                "type": "BODY",
                "text": "Hi {{1}}, thanks for getting in touch with {{2}}. Let us know your queries!",
                "example": {
                    "body_text": [
                        [
                            "Nupur",
                            "360dialog"
                        ]
                    ]
                }
            },
            {
                "text": "WhatsApp Business API provided by 360dialog",
                "type": "FOOTER"
            }
        ],
        "allow_category_change": False
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/test_one_id",
        json={'data': data},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Channel not found!"
    assert actual["data"] == None


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.get_partner_auth_token", autospec=True)
def test_delete_template_error(mock_get_partner_auth_token):
    mock_get_partner_auth_token.return_value = "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"
    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/test_one_id",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Channel not found!"
    assert actual["data"] == None


def test_list_whatsapp_templates_error():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Channel not found!"


def test_get_channel_logs():
    from kairon.shared.chat.data_objects import ChannelLogs
    ChannelLogs(
        type=ChannelTypes.WHATSAPP.value,
        status='read',
        data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1691598412',
              'origin': {'type': 'business_initated'}},
        initiator='business_initated',
        campaign_id='6779002886649302',
        message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
        bot=pytest.bot,
        user='integration@demo.ai'
    ).save()
    ChannelLogs(
        type=ChannelTypes.WHATSAPP.value,
        status='delivered',
        data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1621598412',
              'origin': {'type': 'business_initated'}},
        initiator='business_initated',
        campaign_id='6779002886649302',
        message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
        bot=pytest.bot,
        user='integration@demo.ai'
    ).save()
    ChannelLogs(
        type=ChannelTypes.WHATSAPP.value,
        status='sent',
        data={'id': 'CONVERSATION_ID', 'expiration_timestamp': '1631598412',
              'origin': {'type': 'business_initated'}},
        initiator='business_initated',
        campaign_id='6779002886649302',
        message_id='wamid.HBgLMTIxMTU1NTc5NDcVAgARGBIyRkQxREUxRDJFQUJGMkQ3NDIZ',
        bot=pytest.bot,
        user='integration@demo.ai'
    ).save()
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/whatsapp/metrics",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == [
        {
            'campaign_metrics': [
                {
                    'retry_count': 0,
                    'statuses': {'delivered': 1, 'read': 1, 'sent': 1}
                }
            ],
            'campaign_id': '6779002886649302'
        }
    ]


@responses.activate
def test_initiate_bsp_onboarding_without_channels(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(whatsapp="360dialog", bot=pytest.bot, user="test_user")

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://kairon-api.digite.com"
    )
    monkeypatch.setitem(
        Utility.environment["channels"]["360dialog"], "partner_id", "f167CmPA"
    )
    url = "https://hub.360dialog.io/api/v2/token"
    responses.add("POST", json={}, url=url, status=500)

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/360dialog/onboarding?clientId=kairon&client=sdfgh5678&channels=[]",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"].startswith(
        "Failed to save channel config, onboarding unsuccessful!"
    )
    assert actual["data"] is None


@responses.activate
def test_initiate_bsp_onboarding_failure(monkeypatch):
    def _mock_get_bot_settings(*args, **kwargs):
        return BotSettings(whatsapp="360dialog", bot=pytest.bot, user="test_user")

    monkeypatch.setattr(MongoProcessor, "get_bot_settings", _mock_get_bot_settings)
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://kairon-api.digite.com"
    )
    monkeypatch.setitem(
        Utility.environment["channels"]["360dialog"], "partner_id", "f167CmPA"
    )
    url = "https://hub.360dialog.io/api/v2/token"
    responses.add("POST", json={}, url=url, status=500)

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/360dialog/onboarding?clientId=kairon&client=sdfgh5678&channels=['sdfghjk678']",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"].startswith("Failed to get partner auth token: ")
    assert actual["data"] is None


def test_initiate_bsp_onboarding_disabled(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["channels"]["360dialog"], "partner_id", "f167CmPA"
    )
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/360dialog/onboarding?clientId=kairon&client=sdfgh5678&channels=['sdfghjk678']",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert (
            actual["message"]
            == "Feature disabled for this account. Please contact support!"
    )
    assert actual["data"] is None


def test_initiate_bsp_onboarding(monkeypatch):
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


def test_post_process(monkeypatch):
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
            with patch(
                    "kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.set_webhook_url",
                    autospec=True,
            ):
                response = client.post(
                    f"/api/bot/{pytest.bot}/channels/whatsapp/360dialog/post_process",
                    headers={
                        "Authorization": pytest.token_type + " " + pytest.access_token
                    },
                )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Credentials refreshed!"
    assert actual["data"].startswith(
        f"http://kairon-api.digite.com/api/bot/whatsapp/{pytest.bot}/e"
    )


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.add_template", autospec=True)
def test_add_template(mock_add_template):
    data = {
        "name": "Introduction template",
        "category": "MARKETING",
        "components": [
            {
                "format": "TEXT",
                "text": "New request",
                "type": "HEADER"
            },
            {
                "type": "BODY",
                "text": "Hi {{1}}, thanks for getting in touch with {{2}}. We will process your request get back to you shortly",
                "example": {
                    "body_text": [
                        [
                            "Nupur",
                            "360dialog"
                        ]
                    ]
                }
            },
            {
                "text": "WhatsApp Business API provided by 360dialog",
                "type": "FOOTER"
            }
        ],
        "language": "es_ES",
        "allow_category_change": True
    }
    api_resp = {
        "id": "594425479261596",
        "status": "PENDING",
        "category": "MARKETING"
    }
    mock_add_template.return_value = api_resp

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog",
        json={'data': data},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == {'id': '594425479261596', 'status': 'PENDING', 'category': 'MARKETING'}


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.edit_template", autospec=True)
def test_edit_template(mock_edit_template):
    data = {
        "components": [
            {
                "format": "TEXT",
                "text": "New request",
                "type": "HEADER"
            },
            {
                "type": "BODY",
                "text": "Hi {{1}}, thanks for getting in touch with {{2}}. Let us know your queries!",
                "example": {
                    "body_text": [
                        [
                            "Nupur",
                            "360dialog"
                        ]
                    ]
                }
            },
            {
                "text": "WhatsApp Business API provided by 360dialog",
                "type": "FOOTER"
            }
        ],
        "allow_category_change": False
    }
    api_resp = {
        "success": True
    }
    mock_edit_template.return_value = api_resp

    response = client.put(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/test_id",
        json={'data': data},
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == [{'success': True}]


@patch("kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.delete_template", autospec=True)
def test_delete_template(mock_delete_template):
    api_resp = {
        "meta": {
            "developer_message": "template name=Introduction template was deleted",
            "http_code": 200,
            "success": True
        }
    }
    mock_delete_template.return_value = api_resp

    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/test_id",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] == api_resp


@patch(
    "kairon.shared.channels.whatsapp.bsp.dialog360.BSP360Dialog.list_templates",
    autospec=True,
)
def test_list_templates(mock_list_templates):
    api_resp = {
        "waba_templates": [
            {
                "category": "MARKETING",
                "components": [
                    {
                        "example": {"body_text": [["Peter"]]},
                        "text": "Hi {{1}},\n\nWe are thrilled to share that *kAIron* has now been integrated with WhatsApp through the *WhatsApp Business Solution Provide*r (BSP). \n\nThis integration will expand kAIron's ability to engage with a larger audience, increase sales acceleration, and provide better customer support.\n\nWith this integration, sending customized templates and broadcasting general, sales, or marketing information over WhatsApp will be much quicker and more efficient. \n\nStay tuned for more exciting updates from Team kAIron! ",
                        "type": "BODY",
                    }
                ],
                "id": "GVsEkeI2PIiARwVXQEDVWT",
                "language": "en",
                "modified_at": "2023-03-02T13:39:27Z",
                "modified_by": {"user_id": "system", "user_name": "system"},
                "name": "kairon_new_features",
                "namespace": "092819ec_f801_461b_b975_3a2d464f50a8",
                "partner_id": "9Mg0AiPA",
                "waba_account_id": "Cyih7GWA",
            }
        ]
    }
    mock_list_templates.return_value = api_resp["waba_templates"]

    response = client.get(
        f"/api/bot/{pytest.bot}/channels/whatsapp/templates/360dialog/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["templates"] == api_resp["waba_templates"]


def test_get_channel_endpoint(monkeypatch):
    monkeypatch.setitem(
        Utility.environment["model"]["agent"], "url", "http://localhost:5056"
    )
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/slack/endpoint",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"].startswith(
        f"http://localhost:5056/api/bot/slack/{pytest.bot}/e"
    )


def test_get_channels_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    assert len(actual["data"]) == 2
    pytest.slack_channel_id = actual["data"][0]["_id"]
    actual["data"][0].pop("_id")
    actual["data"][1].pop("_id")
    assert actual["data"] == [
        {
            "bot": pytest.bot,
            "connector_type": "slack",
            "config": {
                "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vamm*****",
                "slack_signing_secret": "79f036b9894eef17c064213b90d*****",
                "client_id": "3396830255712.33968616548768*****",
                "client_secret": "cf92180a7634d90bf42a2174083*****",
                "is_primary": True,
                "team": {"id": "T03BNQE7HLX", "name": "helicopter"},
            },
            "meta_config": {},
        },
        {
            "bot": pytest.bot,
            "connector_type": "whatsapp",
            "config": {
                "client_name": "k*****",
                "client_id": "sdfgh5678",
                "channel_id": "sdfghjk678",
                "partner_id": "f167CmPA",
                "waba_account_id": "dfghj5678",
                "api_key": "dfghjk5678",
                "bsp_type": "360dialog",
            },
            "meta_config": {},
        },
    ]


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_scheduled_broadcast(mock_event_server):
    config = {
        "name": "first_scheduler",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "57 22 * * *",
            "timezone": "UTC",
        },
        "recipients_config": {"recipients": "918958030541, "},
        "template_config": [
            {
                "template_id": "brochure_pdf",
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
    pytest.first_scheduler_id = actual["data"]["msg_broadcast_id"]
    assert pytest.first_scheduler_id


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_scheduled_broadcast_with_invalid_cron(mock_event_server):
    config = {
        "name": "first_scheduler",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "mayank",
            "timezone": "UTC",
        },
        "recipients_config": {"recipients": "918958030541,"},
        "template_config": [
            {"template_id": "brochure_pdf"}
        ],
    }

    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )

    actual = response.json()
    assert actual["success"] is False

    assert any(
        "Invalid cron expression: 'mayank'" in str(msg.get("msg", ""))
        for msg in actual["message"]
    )


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_one_time_broadcast(mock_event_server):
    config = {
        "name": "one_time_schedule",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "918958030541,"},
        "template_config": [
            {
                "template_id": "brochure_pdf",
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
    pytest.one_time_schedule_id = actual["data"]["msg_broadcast_id"]
    assert pytest.one_time_schedule_id


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_one_time_schedule_broadcast(mock_event_server):
    ist = pytz.timezone("Asia/Kolkata")
    dt_ist = datetime.now(ist) + timedelta(hours=1)
    run_at = int(dt_ist.astimezone(pytz.UTC).timestamp())

    config = {
        "name": "one_time_schedule_broadcast",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "916200035185,"},
        "scheduler_config": {
            "schedule": run_at,
            "expression_type": "epoch",
            "timezone": "Asia/Calcutta"
        },
        "template_config": [
            {
                "template_id": "brochure_pdf",
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
    pytest.one_time_schedule_broadcast_id = actual["data"]["msg_broadcast_id"]
    assert pytest.one_time_schedule_broadcast_id

@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_one_time_schedule_missing_run_at(mock_event_server):
    config = {
        "name": "missing_run_at",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "916200035185,"},
        "scheduler_config": {
            "expression_type": "epoch",
            "timezone": "Asia/Calcutta"
        },
        "template_config": [{"template_id": "brochure_pdf"}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    response=response.json()
    print(response)
    assert response["error_code"]== 422
    errors = response["message"]

    assert any("schedule time is required for all schedules!" in err.get("msg", "") for err in errors)

@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_one_time_schedule_past_run_at(mock_event_server):
    past_epoch = int((utc_now() - timedelta(hours=1)).timestamp())
    config = {
        "name": "past_run_at",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "916200035185,"},
        "scheduler_config": {
            "schedule": past_epoch,
            "expression_type": "epoch",
            "timezone": "Asia/Calcutta"
        },
        "template_config": [{"template_id": "brochure_pdf"}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    print(response.json())
    response=response.json()
    assert response["error_code"]== 422
    errors = response["message"]
    assert any("epoch time (schedule) must be in the future relative to the provided timezone" in err["msg"] for err in errors)


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_one_time_schedule_missing_timezone(mock_event_server):
    ist = pytz.timezone("Asia/Kolkata")
    dt_ist = datetime.now(ist) + timedelta(hours=1)
    run_at = int(dt_ist.astimezone(pytz.UTC).timestamp())
    config = {
        "name": "missing_timezone",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "916200035185,"},
        "scheduler_config": {
            "expression_type":"epoch",
            "schedule": run_at,
        },
        "template_config": [{"template_id": "brochure_pdf"}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    print(response.json())
    response=response.json()
    assert response["error_code"]== 422
    errors = response["message"]
    assert any("timezone is required for all schedules!" in err["msg"] for err in errors)

@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_one_time_schedule_with_invalid_expression_type(mock_event_server):
    ist = pytz.timezone("Asia/Kolkata")
    dt_ist = datetime.now(ist) + timedelta(hours=1)
    run_at = int(dt_ist.astimezone(pytz.UTC).timestamp())
    config = {
        "name": "missing_timezone",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "916200035185,"},
        "scheduler_config": {
            "schedule": run_at,
            "timezone": "Asia/Calcutta",
            "expression_type":"mayank"
        },
        "template_config": [{"template_id": "brochure_pdf"}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    print(response.json())
    response=response.json()
    assert response["error_code"]== 422
    errors = response["message"]
    assert any("expression_type must be either cron or epoch" in err["msg"] for err in errors)

@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_one_time_schedule_with_invalid_epoch_string(mock_event_server):
    ist = pytz.timezone("Asia/Kolkata")
    dt_ist = datetime.now(ist) + timedelta(hours=1)
    run_at = int(dt_ist.astimezone(pytz.UTC).timestamp())
    config = {
        "name": "missing_timezone",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "916200035185,"},
        "scheduler_config": {
            "schedule": "mayank",
            "timezone": "Asia/Calcutta",
            "expression_type":"epoch"
        },
        "template_config": [{"template_id": "brochure_pdf"}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    print(response.json())
    response=response.json()
    assert response["error_code"]== 422
    errors = response["message"]
    assert any("schedule must be a valid integer epoch time for 'epoch' expression_type" in err["msg"] for err in errors)



@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_one_time_schedule_with_invalid_timezone(mock_event_server):
    ist = pytz.timezone("Asia/Kolkata")
    dt_ist = datetime.now(ist) + timedelta(hours=1)
    run_at = int(dt_ist.astimezone(pytz.UTC).timestamp())
    config = {
        "name": "missing_timezone",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "916200035185,"},
        "scheduler_config": {
            "schedule": run_at,
            "timezone": "mayank",
            "expression_type":"epoch"
        },
        "template_config": [{"template_id": "brochure_pdf"}],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    print(response.json())
    response=response.json()
    assert response["error_code"]== 422
    errors = response["message"]
    assert any("Unknown timezone: mayank" in err["msg"] for err in errors)


@patch("kairon.shared.utils.Utility.request_event_server", side_effect=Exception("Event server failed"))
def test_add_one_time_schedule_integration_failure(mock_request_event_server):
    ist = pytz.timezone("Asia/Kolkata")
    dt_ist = datetime.now(ist) + timedelta(minutes=10)
    run_at = int(dt_ist.astimezone(pytz.UTC).timestamp())

    config = {
        "name": "one_time_schedule_broadcast_error",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "916200035185,"},
        "scheduler_config": {
            "schedule": run_at,
            "expression_type": "epoch",
            "timezone": "Asia/Calcutta"
        },
        "template_config": [
            {"template_id": "brochure_pdf"}
        ],
    }


    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    body = response.json()
    print(body)
    assert body["success"] is False
    assert "Event server failed" in body["message"]


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_update_message_broadcast_one_time_scheduled_broadcast(mock_event_server):
    config = {
        "name": "one_time_schedule_broadcast",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "916200035185,"},
        "scheduler_config": {
            "schedule": 2524608000,
            "expression_type": "epoch",
            "timezone": "Asia/Calcutta"
        },
        "template_config": [
            {
                "template_id": "brochure_pdf",
            }
        ],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.one_time_schedule_broadcast_id}",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(response.json())
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast updated!"


def test_list_broadcast_config_after_update():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)

    assert actual["success"]
    assert actual["error_code"] == 0

    for sched in actual["data"]["schedules"]:
        sched.pop("_id", None)
        sched.pop("timestamp", None)
        sched.pop("bot", None)
        sched.pop("user", None)

    print(actual["data"])
    assert actual["data"]["schedules"][2] == {'name': 'one_time_schedule_broadcast', 'connector_type': 'whatsapp', 'broadcast_type': 'static',
         'bsp_type': '360dialog',
         'scheduler_config': {'expression_type': 'epoch', 'schedule': 2524608000, 'timezone': 'Asia/Calcutta'},
         'recipients_config': {'recipients': '916200035185,'},
         'template_config': [{'template_id': 'brochure_pdf', 'language': 'en'}], 'collection_config': {},
         'retry_count': 0, 'status': True
                                              }


def test_broadcast_config_error():
    config = {
        "name": "one_time_schedule",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "* * * * *",
            "timezone": "UTC",
        },
        "recipients_config": {"recipients": "918958030541,"},
        "template_config": [
            {
                "template_id": "brochure_pdf",
            }
        ],
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "scheduler_config", "__root__"],
            "msg": "Recurrence interval must be at least 86340 seconds!",
            "type": "value_error",
        }
    ]

    config["scheduler_config"] = {
        "expression_type": "cron",
        "schedule": "57 22 * * *",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "scheduler_config", "__root__"],
            "msg": "timezone is required for all schedules!",
            "type": "value_error",
        }
    ]

    config["scheduler_config"]["schedule"] = ""
    config["scheduler_config"]["timezone"] = "UTC"
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "scheduler_config", "__root__"],
            "msg": f"schedule time is required for all schedules!",
            "type": "value_error",
        }
    ]

    config["scheduler_config"] = {
        "expression_type": "cron",
        "schedule": "30 5 * * *",
        "timezone": "UTC",
    }
    config["broadcast_type"] = "dynamic"
    config["template_name"] = "consent"
    config["language_code"] = "en"
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "pyscript is required for dynamic broadcasts!",
            "type": "value_error",
        },
    ]

    config["broadcast_type"] = "static"
    config.pop("template_config")
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {
            "loc": ["body", "__root__"],
            "msg": "recipients_config and template_config is required for static broadcasts!",
            "type": "value_error",
        }
    ]


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_update_broadcast(mock_event_server):
    config = {
        "name": "first_scheduler_dynamic",
        "broadcast_type": "dynamic",
        "connector_type": "whatsapp",
        "template_name": "consent",
        "language_code": "en",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "21 11 * * *",
            "timezone": "Asia/Kolkata",
        },
        "pyscript": "send_msg('template_name', '9876543210')",
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.first_scheduler_id}",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast updated!"

@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_update_one_time_scheduled_broadcast(mock_event_server):
    ist = pytz.timezone("Asia/Kolkata")
    dt_ist = datetime.now(ist) + timedelta(hours=1)
    run_at = int(dt_ist.astimezone(pytz.UTC).timestamp())
    config = {
        "name": "one_time_schedule_broadcast",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "916200035185,"},
        "scheduler_config": {
            "schedule": run_at,
            "expression_type": "epoch",
            "timezone": "Asia/Calcutta"
        },
        "template_config": [
            {
                "template_id": "brochure_pdf",
            }
        ],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.one_time_schedule_broadcast_id}",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(response.json())
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast updated!"


def test_update_one_time_broadcast_failure():
    config = {
        "name": "one_time_schedule",
        "broadcast_type": "static",
        "connector_type": "whatsapp",
        "recipients_config": {"recipients": "918958030541,"},
        "template_config": [
            {
                "template_id": "brochure_pdf",
            }
        ],
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.one_time_schedule_id}",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "scheduler_config with a valid schedule is required!"


def test_list_broadcast_config():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    print(actual)

    assert actual["success"]
    assert actual["error_code"] == 0

    for sched in actual["data"]["schedules"]:
        sched.pop("_id", None)
        sched.pop("timestamp", None)
        sched.pop("bot", None)
        sched.pop("user", None)
        if sched.get("scheduler_config") and sched["scheduler_config"].get("expression_type") == "epoch":
            sched["scheduler_config"].pop("schedule", None)

    assert actual["data"] == {
        "schedules": [
            {
                "name": "first_scheduler_dynamic",
                "connector_type": "whatsapp",
                "broadcast_type": "dynamic",
                "bsp_type": "360dialog",
                "collection_config": {},
                "scheduler_config": {
                    "expression_type": "cron",
                    "schedule": "21 11 * * *",
                    "timezone": "Asia/Kolkata",
                },
                "retry_count": 0,
                "pyscript": "send_msg('template_name', '9876543210')",
                "status": True,
                "template_config": [],
            },
            {
                "name": "one_time_schedule",
                "connector_type": "whatsapp",
                "broadcast_type": "static",
                "bsp_type": "360dialog",
                "collection_config": {},
                "recipients_config": {"recipients": "918958030541,"},
                "retry_count": 0,
                "template_config": [{"template_id": "brochure_pdf", "language": "en"}],
                "status": True,
            },
            {
                "name": "one_time_schedule_broadcast",
                "connector_type": "whatsapp",
                "broadcast_type": "static",
                "bsp_type": "360dialog",
                "collection_config": {},
                "recipients_config": {"recipients": "916200035185,"},
                "retry_count": 0,
                "status": True,
                "template_config": [{"template_id": "brochure_pdf", "language": "en"}],
                "scheduler_config": {"expression_type":"epoch",
                                     "timezone": "Asia/Calcutta"},
            },
        ]
    }


@patch("kairon.shared.utils.Utility.delete_scheduled_event", autospec=True)
def test_delete_broadcast(mock_event_server):
    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.first_scheduler_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast removed!"
    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.one_time_schedule_broadcast_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Broadcast removed!"


def test_delete_broadcast_not_exists():
    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/{pytest.first_scheduler_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == "Notification settings not found!"


def test_list_broadcast_():
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/list",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["schedules"][0].pop("timestamp")
    actual["data"]["schedules"][0].pop("user")
    assert actual["data"] == {
        "schedules": [
            {
                "_id": pytest.one_time_schedule_id,
                "name": "one_time_schedule",
                "connector_type": "whatsapp",
                "broadcast_type": "static",
                "bsp_type": "360dialog",
                "collection_config": {},
                "recipients_config": {"recipients": "918958030541,"},
                "retry_count": 0,
                "template_config": [{"template_id": "brochure_pdf", "language": "en"}],
                "bot": pytest.bot,
                "status": True,
            }
        ]
    }


def test_list_broadcast_logs():
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
            "broadcast_id": pytest.first_scheduler_id,
            "recipients": ["918958030541", ""],
            "timestamp": timestamp,
        }
    ).save()
    timestamp = timestamp + timedelta(minutes=2)
    MessageBroadcastLogs(
        **{
            "reference_id": ref_id,
            "log_type": "send",
            "bot": pytest.bot,
            "status": STATUSES.SUCCESS.value,
            "api_response": {
                "contacts": [
                    {"input": "+55123456789", "status": "valid", "wa_id": "55123456789"}
                ]
            },
            "recipient": "9876543210",
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
        }
    ).save()
    response = client.get(
        f"/api/bot/{pytest.bot}/channels/broadcast/message/logs?log_type=common",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    actual["data"]["logs"][0].pop("timestamp")
    assert actual["data"]["logs"] == [
        {
            "reference_id": ref_id,
            "log_type": "common",
            "bot": pytest.bot,
            "status": EVENT_STATUS.COMPLETED.value,
            "user": "test_user",
            "broadcast_id": pytest.first_scheduler_id
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
    assert actual["data"] == {
        "logs": [
            {
                "reference_id": ref_id,
                "log_type": "send",
                "bot": pytest.bot,
                "status": STATUSES.SUCCESS.value,
                "api_response": {
                    "contacts": [
                        {
                            "input": "+55123456789",
                            "status": "valid",
                            "wa_id": "55123456789",
                        }
                    ]
                },
                "recipient": "9876543210"
            },
            {
                "reference_id": ref_id,
                "log_type": "common",
                "bot": pytest.bot,
                "status": EVENT_STATUS.COMPLETED.value,
                "user": "test_user",
                "broadcast_id": pytest.first_scheduler_id
            },
        ],
        "total_count": 2,
    }

def test_get_bot_settings():
    response = client.get(
        f"/api/bot/{pytest.bot}/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    actual["data"].pop("bot")
    actual["data"].pop("user")
    actual["data"].pop("timestamp")
    actual["data"].pop("status")
    assert actual['data'] == {'is_billed': False, 'chat_token_expiry': 30,
                              'data_generation_limit_per_day': 3,
                              'data_importer_limit_per_day': 5,
                              'enable_voice': False,
                              'force_import': False,
                              'ignore_utterances': False,
                              'llm_settings': {'enable_faq': False, 'provider': 'openai'},
                              'analytics': {'fallback_intent': 'nlu_fallback'},
                              'multilingual_limit_per_day': 2,
                              'max_actions_per_parallel_action': 5,
                              'notification_scheduling_limit': 4,
                              'refresh_token_expiry': 60,
                              'rephrase_response': False,
                              'live_agent_enabled': False,
                              'pos_enabled': False,
                              'test_limit_per_day': 5,
                              'training_limit_per_day': 5, 'dynamic_broadcast_execution_timeout': 21600,
                              'website_data_generator_depth_search_limit': 2,
                              'whatsapp': 'meta',
                              'cognition_collections_limit': 3,
                              'cognition_columns_per_collection_limit': 5,
                              'content_importer_limit_per_day': 5,
                              'system_limits': {'file_upload_limit': 5},
                              'integrations_per_user_limit': 3,
                              'retry_broadcasting_limit': 3,
                              'max_template_per_broadcast': 5,
                              'catalog_sync_limit_per_day': 5,
                              'max_instagram_user_posts': 5,
                              'media_size_limit': 10,
                              'store_page_token_expiry': 15}


@patch("kairon.shared.utils.Utility.request_event_server", autospec=True)
def test_add_scheduled_dynamic_broadcast(mock_event_server):
    config = {
        "name": "first_scheduler_dynamic",
        "broadcast_type": "dynamic",
        "connector_type": "whatsapp",
        "template_name": "consent",
        "language_code": "en",
        "scheduler_config": {
            "expression_type": "cron",
            "schedule": "21 11 * * *",
            "timezone": "Asia/Kolkata",
        },
        "pyscript": "send_msg('template_name', '9876543210')",
    }
    response = client.post(
        f"/api/bot/{pytest.bot}/channels/broadcast/message",
        json=config,
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == 'Broadcast added!'
    assert actual["data"]


def test_update_analytics_settings_with_empty_value():
    bot_settings = {
        "analytics": {'fallback_intent': ''},
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=bot_settings
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'analytics', 'fallback_intent'],
                                  'msg': 'fallback_intent field cannot be empty', 'type': 'value_error'}]


def test_update_analytics_settings_with_none():
    bot_settings = {
        "analytics": {'fallback_intent': None},
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=bot_settings
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [{'loc': ['body', 'analytics', 'fallback_intent'],
                                  'msg': 'none is not an allowed value', 'type': 'type_error.none.not_allowed'}]


def test_update_analytics_settings():
    bot_settings = {
        "analytics": {'fallback_intent': 'utter_please_rephrase'},
    }
    response = client.put(
        f"/api/bot/{pytest.bot}/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
        json=bot_settings
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Bot Settings updated"
    response = client.get(
        f"/api/bot/{pytest.bot}/settings",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] is None
    actual["data"].pop("bot")
    actual["data"].pop("user")
    actual["data"].pop("timestamp")
    actual["data"].pop("status")
    assert actual['data'] == {'is_billed': False, 'chat_token_expiry': 30,
                              'data_generation_limit_per_day': 3,
                              'data_importer_limit_per_day': 5,
                              'enable_voice': False,
                              'force_import': False,
                              'ignore_utterances': False,
                              'llm_settings': {'enable_faq': False, 'provider': 'openai'},
                              'analytics': {'fallback_intent': 'utter_please_rephrase'},
                              'multilingual_limit_per_day': 2,
                              'max_actions_per_parallel_action': 5,
                              'notification_scheduling_limit': 4,
                              'refresh_token_expiry': 60,
                              'rephrase_response': False,
                              'test_limit_per_day': 5,
                              'training_limit_per_day': 5, 'dynamic_broadcast_execution_timeout': 21600,
                              'website_data_generator_depth_search_limit': 2,
                              'whatsapp': 'meta',
                              'live_agent_enabled': False,
                              'pos_enabled': False,
                              'cognition_collections_limit': 3,
                              'content_importer_limit_per_day': 5,
                              'system_limits': {'file_upload_limit': 5},
                              'cognition_columns_per_collection_limit': 5,
                              'integrations_per_user_limit': 3,
                              'retry_broadcasting_limit': 3,
                              'max_template_per_broadcast': 5,
                              'catalog_sync_limit_per_day': 5,
                              'max_instagram_user_posts': 5,
                              'media_size_limit': 10,
                              'store_page_token_expiry': 15}


def test_delete_channels_config():
    response = client.delete(
        f"/api/bot/{pytest.bot}/channels/{pytest.slack_channel_id}",
        headers={"Authorization": pytest.token_type + " " + pytest.access_token},
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["message"] == "Channel deleted"
