import asyncio
import json
import os
from unittest import mock
from urllib.parse import urlencode, quote_plus

import pytest
import responses
from mock import patch
from mongoengine import connect
from rasa.core.agent import Agent
from rasa.utils.endpoints import EndpointConfig
from slack.web.slack_response import SlackResponse
from starlette.exceptions import HTTPException
from starlette.testclient import TestClient

from kairon.api.models import RegisterAccount
from kairon.chat.agent.agent import KaironAgent
from kairon.chat.agent.message_processor import KaironMessageProcessor
from kairon.chat.handlers.channels.messenger import MessengerHandler
from kairon.chat.server import app
from kairon.chat.utils import ChatUtils
from kairon.exceptions import AppException
from kairon.shared.account.activity_log import UserActivityLogger
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.auth import Authentication
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import UserActivityType
from kairon.shared.data.constant import INTEGRATION_STATUS
from kairon.shared.data.constant import TOKEN_TYPE
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.live_agent.processor import LiveAgentsProcessor
from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.metering_processor import MeteringProcessor
from kairon.shared.utils import Utility
from kairon.train import start_training

os.environ["system_file"] = "./tests/testing_data/system.yaml"
os.environ['ASYNC_TEST_TIMEOUT'] = "3600"
Utility.load_environment()
connect(**Utility.mongoengine_connection())

loop = asyncio.new_event_loop()
loop.run_until_complete(AccountProcessor.account_setup(RegisterAccount(**{"email": "test@chat.com",
                                                                          "first_name": "Test",
                                                                          "last_name": "Chat",
                                                                          "password": "testChat@12",
                                                                          "confirm_password": "testChat@12",
                                                                          "account": "ChatTesting"}).dict()))
loop.run_until_complete(AccountProcessor.account_setup(RegisterAccount(**{"email": "resetpaswrd@chat.com",
                                                                          "first_name": "Reset",
                                                                          "last_name": "Password",
                                                                          "password": "resetPswrd@12",
                                                                          "confirm_password": "resetPswrd@12",
                                                                          "account": "ResetPassword"}).dict()))

token, _, _, _ = Authentication.authenticate("test@chat.com", "testChat@12")
token_type = "Bearer"
user = AccountProcessor.get_complete_user_details("test@chat.com")
bot = user['bots']['account_owned'][0]['_id']
bot_account = user['bots']['account_owned'][0]['account']
chat_client_config = MongoProcessor().get_chat_client_config(bot, "test@chat.com").to_mongo().to_dict()
start_training(bot, "test@chat.com")
bot2 = AccountProcessor.add_bot("testChat2", user['account'], "test@chat.com")['_id'].__str__()
loop.run_until_complete(MongoProcessor().save_from_path(
    "template/use-cases/Hi-Hello", bot2, user="test@chat.com"
))
start_training(bot2, "test@chat.com")
bot3 = AccountProcessor.add_bot("testChat3", user['account'], "test@chat.com")['_id'].__str__()

with patch('slack.web.client.WebClient.team_info') as mock_slack_team_info:
    mock_slack_team_info.return_value = SlackResponse(
        client=None,
        http_verb="POST",
        api_url="https://slack.com/api/team.info",
        req_args={},
        data={
            "ok": True,
            "team": {
                "id": "T03BNQE7HLY",
                "name": "helicopter",
                "avatar_base_url": "https://ca.slack-edge.com/",
                "is_verified": False
            }
        },
        headers=dict(),
        status_code=200,
        use_sync_aiohttp=False,
    ).validate()
    ChatDataProcessor.save_channel_config({
        "connector_type": "slack", "config": {
            "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
            "slack_signing_secret": "79f036b9894eef17c064213b90d1042b", "client_id": "sdfghj34567890",
            "client_secret": "asdf3456789gfghjkl", "is_primary": True}}, bot, user="test@chat.com")
ChatDataProcessor.save_channel_config({
    "connector_type": "whatsapp",
    "config": {"app_secret": "jagbd34567890", "access_token": "ERTYUIEFDGHGFHJKLFGHJKGHJ", "verify_token": "valid"}},
    bot, user="test@chat.com"
)
settings = BotSettings.objects(bot=bot2, status=True).get()
settings.whatsapp = "360dialog"
settings.save()

ChatDataProcessor.save_channel_config({
    "connector_type": "whatsapp",
    "config": {
        'client_name': 'kairon', 'client_id': 'skds23Ga', 'channel_id': 'dfghjkl', 'partner_id': 'test_partner',
        'bsp_type': '360dialog', 'api_key': 'kHCwksdsdsMVYVx0doabaDyRLUQJUAK', 'waba_account_id': 'Cyih7GWA'
    }}, bot2, user="test@chat.com"
)
responses.start()
encoded_url = urlencode({'url': f"https://test@test.com/api/bot/telegram/{bot}/test"}, quote_via=quote_plus)
responses.add("GET",
              json={"result": True},
              url=f"https://api.telegram.org/botxoxb-801939352912-801478018484/setWebhook?{encoded_url}")
Utility.environment['model']['agent']['url'] = 'https://test@test.com/api/bot/telegram/tests/test'


def __mock_endpoint(*args):
    return f"https://test@test.com/api/bot/telegram/{bot}/test"


with patch('kairon.shared.data.utils.DataUtility.get_channel_endpoint', __mock_endpoint):
    ChatDataProcessor.save_channel_config({"connector_type": "telegram",
                                           "config": {
                                               "access_token": "xoxb-801939352912-801478018484",
                                               "username_for_bot": "test"}},
                                          bot, user="test@chat.com")
ChatDataProcessor.save_channel_config({"connector_type": "hangouts",
                                       "config": {
                                           "project_id": "1234568"}
                                       },
                                      bot, user="test@chat.com")

ChatDataProcessor.save_channel_config({"connector_type": "messenger",
                                       "config": {
                                           "app_secret": "cdb69bc72e2ccb7a869f20cbb6b0229a",
                                           "page_access_token": "EAAGa50I7D7cBAJ4AmXOhYAeOOZAyJ9fxOclQmn52hBwrOJJWBOxuJNXqQ2uN667z4vLekSEqnCQf41hcxKVZAe2pAZBrZCTENEj1IBe1CHEcG7J33ZApED9Tj9hjO5tE13yckNa8lP3lw2IySFqeg6REJR3ZCJUvp2h03PQs4W5vNZBktWF3FjQYz5vMEXLPzAFIJcZApBtq9wZDZD",
                                           "verify_token": "kairon-messenger-token",
                                       }
                                       },
                                      bot, user="test@chat.com")
responses.stop()


def empty_store(*args, **kwargs):
    return None


def __mock_getbusinessdata_workingenabled(*args, **kwargs):
    business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
    output_json = business_workingdata.get("working_enabled_true")
    return output_json


def __mock_getbusinessdata_workingdisabled(*args, **kwargs):
    business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
    output_json = business_workingdata.get("working_enabled_false")
    return output_json


def __mock_validate_businessworkinghours(*args, **kwargs):
    return False


def __mock_validate_businessworkinghours_true(*args, **kwargs):
    return True


def mock_agent_response(*args, **kwargs):
    return {'nlu': {'text': '!@#$%^&*()', 'intent': {'name': 'nlu_fallback', 'confidence': 0.7}, 'entities': [],
                    'intent_ranking': [{'name': 'nlu_fallback', 'confidence': 0.7},
                                       {'id': 7699795435555413769, 'name': 'bot_challenge',
                                        'confidence': 0.3011210560798645},
                                       {'id': -8614851775639803374, 'name': 'mood_unhappy',
                                        'confidence': 0.28137511014938354},
                                       {'id': -7686226624851022724, 'name': 'deny',
                                        'confidence': 0.2647826075553894},
                                       {'id': -963050110453472522, 'name': 'affirm',
                                        'confidence': 0.0759304016828537},
                                       {'id': -4665925488010208305, 'name': 'goodbye',
                                        'confidence': 0.028776828199625015},
                                       {'id': -8510124799033185183, 'name': 'mood_great',
                                        'confidence': 0.025189757347106934},
                                       {'id': 7378347921649253395, 'name': 'greet',
                                        'confidence': 0.022824246436357498}],
                    'response_selector': {'all_retrieval_intents': [], 'default': {
                        'response': {'id': None, 'responses': None, 'response_templates': None, 'confidence': 0.0,
                                     'intent_response_key': None, 'utter_action': 'utter_None',
                                     'template_name': 'utter_None'}, 'ranking': []}},
                    'slots': ['kairon_action_response: None', 'bot: 6275ebcba06e09a1b818c70a',
                              'session_started_metadata: None']},
            'action': [{"action_name": 'utter_please_rephrase'}, {"action_name": 'action_listen'}],
            'response': [{'recipient_id': 'test@chat.com',
                          'text': "I'm sorry, I didn't quite understand that. Could you rephrase?"}],
            'events': None}


client = TestClient(app)


def test_index():
    response = client.get("/")
    response = response.json()
    assert response["error_code"] == 0
    assert response["message"] == 'Chat server running!'


def test_get_chat_client_config():
    response = client.get(
        f"/api/bot/{bot}/chat/client/config/{token}",
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])


def test_get_chat_client_config_exception():
    response = client.get(
        f"/api/bot/{bot}/chat/client/config/invalid_token",
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Invalid token"


def test_get_chat_client_config_raise_error():
    with patch.object(MongoProcessor, "get_client_config_using_uid") as mocked:
        mocked.side_effect = HTTPException(status_code=404, detail="404 Not Found")
        response = client.get(
            f"/api/bot/{bot}/chat/client/config/{token}",
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 404
        assert actual["data"] is None
        assert actual["message"] == "404 Not Found"


def test_get_chat_client_config_with_invalid_domain():
    with patch.object(Utility, "validate_request") as validate_request_mock:
        validate_request_mock.return_value = False
        response = client.get(
            f"/api/bot/{bot}/chat/client/config/{token}",
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 403
        assert actual["data"] is None
        assert not Utility.check_empty_string(actual["message"])
        assert actual["message"] == "Domain not registered for kAIron client"


def test_chat():
    with patch.object(Utility, "get_local_mongo_store") as mocked:
        mocked.side_effect = empty_store
        patch.dict(Utility.environment['action'], {"url": None})
        response = client.post(
            f"/api/bot/{bot}/chat",
            json={"data": "Hi"},
            headers={"Authorization": token_type + " " + token},
            timeout=0,
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"]
        assert Utility.check_empty_string(actual["message"])
        actual_headers = [(k.lower(), v) for k, v in response.headers.items() if k.lower() != 'content-length']
        expected_headers = [('content-type', 'application/json'),
                            ('server', 'Secure'),
                            ('strict-transport-security', 'includeSubDomains; preload; max-age=31536000'),
                            ('x-frame-options', 'SAMEORIGIN'), ('x-xss-protection', '0'),
                            ('x-content-type-options', 'nosniff'), ('content-security-policy',
                                                                    "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'"),
                            ('referrer-policy', 'no-referrer'), ('cache-control', 'must-revalidate'), (
                            'permissions-policy',
                            'accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()'),
                            ('cross-origin-embedder-policy', 'require-corp'),
                            ('cross-origin-opener-policy', 'same-origin'),
                            ('cross-origin-resource-policy', 'same-origin')]
        for header in expected_headers:
            assert header in actual_headers
        data = MeteringProcessor.get_logs(bot_account, metric_type=MetricType.test_chat, bot=bot)
        assert len(data["logs"]) > 0
        assert len(data["logs"]) == data["total"]
        assert data['logs'][0]['account'] == bot_account
        assert MeteringProcessor.get_metric_count(bot_account, metric_type=MetricType.test_chat,
                                                  channel_type="chat_client") > 0


def test_chat_with_user():
    access_token = chat_client_config['config']['headers']['authorization']['access_token']
    token_type = chat_client_config['config']['headers']['authorization']['token_type']
    with patch.object(Utility, "get_local_mongo_store") as mocked:
        mocked.side_effect = empty_store
        patch.dict(Utility.environment['action'], {"url": None})

        response = client.post(
            f"/api/bot/{bot}/chat",
            json={"data": "Hi"},
            headers={"Authorization": token_type + " " + token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"]
        assert Utility.check_empty_string(actual["message"])

        response = client.post(
            f"/api/bot/{bot}/chat",
            json={"data": "Hi"},
            headers={"Authorization": f"{token_type} {access_token}"},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"]
        assert Utility.check_empty_string(actual["message"])
        assert MeteringProcessor.get_metric_count(bot_account, metric_type=MetricType.test_chat,
                                                  channel_type="chat_client") >= 2


def test_chat_empty_data():
    with patch.object(Utility, "get_local_mongo_store") as mocked:
        mocked.side_effect = empty_store
        patch.dict(Utility.environment['action'], {"url": None})

        response = client.post(
            f"/api/bot/{bot}/chat",
            json={"data": ""},
            headers={"Authorization": token_type + " " + token},
        )
        actual = response.json()
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert actual["data"] is None
        assert actual["message"] == [{'loc': ['body', 'data'], 'msg': 'data cannot be empty!', 'type': 'value_error'}]


def test_chat_with_data_not_present():
    response = client.post(
        f"/api/bot/{bot}/chat",
        json={"name": "nupur"},
        headers={"Authorization": token_type + " " + token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    print(actual["message"])
    assert actual["message"] == [{'loc': ['body', 'data'], 'msg': 'field required', 'type': 'value_error.missing'}]


def test_chat_invalid_json():
    response = client.post(
        f"/api/bot/{bot}/chat",
        data='',
        headers={"Authorization": token_type + " " + token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [{'loc': ['body'], 'msg': 'field required', 'type': 'value_error.missing'}]


def test_chat_string_with_blank_spaces():
    response = client.post(
        f"/api/bot/{bot}/chat",
        json={"data": "  "},
        headers={"Authorization": token_type + " " + token},
    )
    actual = response.json()
    data = MeteringProcessor.get_logs(bot_account, metric_type=MetricType.test_chat, bot=bot)
    assert data
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == [{'loc': ['body', 'data'], 'msg': 'data cannot be empty!', 'type': 'value_error'}]


def test_chat_with_user_with_metadata():
    with patch.object(Utility, "get_local_mongo_store") as mocked:
        mocked.side_effect = empty_store
        patch.dict(Utility.environment['action'], {"url": None})

        with patch.object(KaironMessageProcessor, "handle_message") as mocked_handle_message:
            mocked_handle_message.return_value = {
                "nlu": "intent_prediction",
                "action": "action_prediction",
                "response": "response_data",
                "slots": "slot_data",
                "events": "event_data",
            }

            request_body = {
                "data": "Hi",
                "metadata": {
                    "name": "test_chat",
                    "tabname": "coaching"
                }
            }

            response = client.post(
                f"/api/bot/{bot}/chat",
                json=request_body,
                headers={"Authorization": token_type + " " + token},
            )
            actual = response.json()
            assert actual['success']
            assert actual['error_code'] == 0
            metadata = mocked_handle_message.call_args
            assert metadata.args[0].metadata['name'] == 'test_chat'
            assert metadata.args[0].metadata['tabname'] == 'coaching'


def test_chat_with_user_with_invalid_metadata():
    request_body = {
        "data": "Hi",
        "metadata": 20
    }

    response = client.post(
        f"/api/bot/{bot}/chat",
        json=request_body,
        headers={"Authorization": token_type + " " + token},
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["message"] == [
        {'loc': ['body', 'metadata'], 'msg': 'value is not a valid dict', 'type': 'type_error.dict'}]
    assert actual["data"] is None


def test_chat_fetch_from_cache():
    with patch.object(Utility, "get_local_mongo_store") as mocked:
        mocked.side_effect = empty_store
        patch.dict(Utility.environment['action'], {"url": None})

        response = client.post(
            f"/api/bot/{bot}/chat",
            json={"data": "Hi"},
            headers={"Authorization": token_type + " " + token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"]
        assert Utility.check_empty_string(actual["message"])


def test_chat_model_not_trained():
    response = client.post(
        f"/api/bot/{bot3}/chat",
        json={"data": "Hi"},
        headers={
            "Authorization": f"{token_type} {token}"
        },
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Bot has not been trained yet!"


def test_chat_with_different_bot_not_allowed():
    response = client.post(
        f"/api/bot/test/chat",
        json={"data": "Hi"},
        headers={
            "Authorization": token_type + " " + token
        },
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Access to bot is denied"


def test_chat_with_different_bot_using_token_for_different_bot():
    access_token, _ = Authentication.generate_integration_token(
        bot, "test@chat.com", name='integration_token_for_chat_service')
    response = client.post(
        f"/api/bot/{bot2}/chat",
        json={"data": "Hi"},
        headers={"Authorization": token_type + " " + access_token},
        timeout=0,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert not actual["data"]
    assert actual["message"] == 'Access to bot is denied'


def test_chat_with_bot_using_deleted_token():
    access_token, _ = Authentication.generate_integration_token(bot, "test@chat.com", name='integration_token_1')
    Authentication.update_integration_token('integration_token_1', bot,
                                            "test@chat.com", INTEGRATION_STATUS.DELETED.value)
    response = client.post(
        f"/api/bot/{bot}/chat",
        json={"data": "Hi"},
        headers={"Authorization": token_type + " " + access_token},
        timeout=0
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert not actual["data"]
    assert actual["message"] == 'Access to bot is denied'


def test_chat_different_bot():
    with patch.object(Utility, "get_local_mongo_store") as mocked:
        mocked.side_effect = empty_store
        patch.dict(Utility.environment['action'], {"url": None})
        response = client.post(
            f"/api/bot/{bot2}/chat",
            json={"data": "Hi"},
            headers={"Authorization": token_type + " " + token},
            timeout=0
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"]
        assert Utility.check_empty_string(actual["message"])


def test_chat_with_limited_access():
    action_response = {
        "events": [{"event": "slot", "timestamp": None, "name": "kairon_action_response", "value": "Michael"}],
        "responses": [{"text": "Welcome to kairon", "buttons": [], "elements": [], "custom": {}, "template": None,
                       "response": None, "image": None, "attachment": None}]
    }

    access_token, _ = Authentication.generate_integration_token(
        bot2, "test@chat.com", expiry=5, access_limit=['/api/bot/.+/chat'], name="integration token"
    )
    with patch.object(EndpointConfig, "request") as mocked:
        mocked.return_value = action_response
        response = client.post(
            f"/api/bot/{bot2}/chat",
            json={"data": "Hi"},
            headers={
                "Authorization": f"{token_type} {access_token}", 'X-USER': 'testUser'
            },
        )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert actual["data"]["response"] == [{'recipient_id': 'testUser', 'text': 'Welcome to kairon'}]
    data = MeteringProcessor.get_logs(bot_account, metric_type=MetricType.prod_chat, bot=bot2)
    assert len(data["logs"]) > 0
    assert len(data["logs"]) == data["total"]
    assert MeteringProcessor.get_metric_count(bot_account, metric_type=MetricType.prod_chat,
                                              channel_type="chat_client") > 0

    response = client.post(
        f"/api/bot/{bot2}/chat",
        json={"data": "Hi"},
        headers={
            "Authorization": f"{token_type} {access_token}"
        },
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert not actual["data"]
    assert actual['message'] == 'Alias user missing for integration'


def test_chat_with_limited_access_without_integration():
    action_response = {
        "events": [{"event": "slot", "timestamp": None, "name": "kairon_action_response", "value": "Michael"}],
        "responses": [{"text": None, "buttons": [], "elements": [], "custom": {}, "template": None,
                       "response": "utter_greet", "image": None, "attachment": None}]
    }

    access_token = Authentication.create_access_token(
        data={"sub": "test@chat.com", 'access-limit': ['/api/bot/.+/chat']},
    )
    with patch.object(EndpointConfig, "request") as mocked:
        mocked.return_value = action_response
        response = client.post(
            f"/api/bot/{bot2}/chat",
            json={"data": "Hi"},
            headers={
                "Authorization": f"{token_type} {access_token}", 'X-USER': 'testUser'
            },
        )
    actual = response.json()
    assert actual["data"]["response"][0]


def test_chat_limited_access_prevent_chat():
    access_token = Authentication.create_access_token(
        data={"sub": "test@chat.com", 'access-limit': ['/api/bot/.+/intent']},
        token_type=TOKEN_TYPE.INTEGRATION.value
    )
    response = client.post(
        f"/api/bot/{bot}/chat",
        json={"data": "Hi"},
        headers={
            "Authorization": f"{token_type} {access_token}", 'X-USER': "testUser"
        },
    )
    actual = response.json()
    assert actual["message"] == "Access denied for this endpoint"


@patch('kairon.shared.utils.Utility.get_local_mongo_store')
def test_reload(mock_store):
    mock_store.return_value = None
    response = client.get(
        f"/api/bot/{bot}/reload",
        headers={
            "Authorization": token_type + " " + token
        },
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"] is None
    assert actual["message"] == "Reloading Model!"
    actual_headers = [(k.lower(), v) for k, v in response.headers.items() if k.lower() != 'content-length']
    print(actual_headers)
    expected_headers = [('content-type', 'application/json'),
                        ('server', 'Secure'),
                        ('strict-transport-security', 'includeSubDomains; preload; max-age=31536000'),
                        ('x-frame-options', 'SAMEORIGIN'),
                        ('x-content-type-options', 'nosniff'), ('content-security-policy',
                                                                "default-src 'self'; frame-ancestors 'self'; form-action 'self'; base-uri 'self'; connect-src 'self'; frame-src 'self'; style-src 'self' https: 'unsafe-inline'; img-src 'self' https:; script-src 'self' https: 'unsafe-inline'"),
                        ('referrer-policy', 'no-referrer'), ('cache-control', 'must-revalidate'), (
                            'permissions-policy',
                            'accelerometer=(), autoplay=(), camera=(), document-domain=(), encrypted-media=(), fullscreen=(), vibrate=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), midi=(), payment=(), picture-in-picture=(), sync-xhr=(), usb=()'),
                        ('cross-origin-embedder-policy', 'require-corp'),
                        ('cross-origin-opener-policy', 'same-origin'),
                        ('cross-origin-resource-policy', 'same-origin')]
    for header in expected_headers:
        assert header in actual_headers


def test_reload_exception():
    response = client.get(
        f"/api/bot/{bot}/reload",
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 401
    assert actual["data"] is None
    assert actual["message"] == "Not authenticated"


@patch('kairon.chat.handlers.channels.slack.SlackHandler.is_request_from_slack_authentic')
@patch('kairon.shared.utils.Utility.get_local_mongo_store')
def test_slack_auth_bot_challenge(mock_store, mock_slack):
    mock_store.return_value = empty_store
    mock_slack.return_value = True
    headers = {'User-Agent': 'Slackbot 1.0 (+https://api.slack.com/robots)',
               'Content-Length': '826',
               'Accept': '*/*',
               'Accept-Encoding': 'gzip,deflate',
               'Cache-Control': 'max-age=259200',
               'Content-Type': 'application/json',
               'X-Forwarded-For': '3.237.67.113',
               'X-Forwarded-Proto': 'http',
               'X-Slack-Request-Timestamp': '1644676934',
               'X-Slack-Retry-Reason': 'http_error',
               'X-Slack-Signature': 'v0=65e62a2a81ebac3825a7aeec1f7033977e31f6ccff988ec11aaf06884553834a'}
    patch.dict(Utility.environment['action'], {"url": None})
    response = client.post(
        f"/api/bot/slack/{bot}/{token}",
        headers=headers,
        json={"token": "RrNd3SaNJNaP28TTauAYCmJw",
                         "challenge": "sjYDB2ccaT5wpcGyawz6BTDbiujZCBiVwSQR87t3Q3yqgoHFkkTy",
                         "type": "url_verification"}
    )
    actual = response.json()
    assert actual == "sjYDB2ccaT5wpcGyawz6BTDbiujZCBiVwSQR87t3Q3yqgoHFkkTy"


@patch('slack.web.client.WebClient.team_info')
@patch('slack.web.client.WebClient.oauth_v2_access')
def test_slack_install_app_using_oauth(mock_slack_oauth, mock_slack_team_info):
    mock_slack_team_info.return_value = SlackResponse(
        client=client,
        http_verb="POST",
        api_url="https://slack.com/api/team.info",
        req_args={},
        data={
            "ok": True,
            "team": {
                "id": "T03BNQE7HLZ",
                "name": "airbus",
                "avatar_base_url": "https://ca.slack-edge.com/",
                "is_verified": False
            }
        },
        headers=dict(),
        status_code=200,
        use_sync_aiohttp=False,
    ).validate()
    mock_slack_oauth.return_value = SlackResponse(
        client=client,
        http_verb="POST",
        api_url="https://slack.com/api/team.info",
        req_args={},
        data={
            "ok": True,
            "access_token": "xoxb-987654321098-801939352912-v3zq6MYNu62oSs8vammWOY8K",
            "team": {
                "id": "T03BNQE7HLZ",
                "name": "airbus",
                "avatar_base_url": "https://ca.slack-edge.com/",
                "is_verified": False
            }
        },
        headers=dict(),
        status_code=200,
        use_sync_aiohttp=False,
    ).validate()
    encoded_url_ = urlencode({'code': "98765432109765432asdfghjkl", "state": ""}, quote_via=quote_plus)
    response = client.get(
        f"/api/bot/slack/{bot}/{token}?{encoded_url_}", allow_redirects=False
    )
    assert 'https://app.slack.com/client/T03BNQE7HLZ' == response.headers["location"]
    assert response.status_code == 303


def test_slack_invalid_auth():
    headers = {'User-Agent': 'Slackbot 1.0 (+https://api.slack.com/robots)',
               'Content-Length': '826',
               'Accept': '*/*',
               'Accept-Encoding': 'gzip,deflate',
               'Cache-Control': 'max-age=259200',
               'Content-Type': 'application/json',
               'X-Forwarded-For': '3.237.67.113',
               'X-Forwarded-Proto': 'http',
               'X-Slack-Request-Timestamp': '1644676934',
               'X-Slack-Retry-Num': '1',
               'X-Slack-Retry-Reason': 'http_error',
               'X-Slack-Signature': 'v0=65e62a2a81ebac3825a7aeec1f7033977e31f6ccff988ec11aaf06884553834a'}
    patch.dict(Utility.environment['action'], {"url": None})
    response = client.post(
        f"/api/bot/slack/{bot}/123",
        headers=headers,
        json={"token": "RrNd3SaNJNaP28TTauAYCmJw", "team_id": "TPKTMACSU", "api_app_id": "APKTXRPMK",
                         "event": {"client_msg_id": "77eafc15-4e7a-46d1-b03f-bf953fa801dc", "type": "message",
                                   "text": "Hi", "user": "UPKTMK5BJ", "ts": "1644670603.521219",
                                   "team": "TPKTMACSU", "blocks": [{"type": "rich_text", "block_id": "ssu6",
                                                                    "elements": [{"type": "rich_text_section",
                                                                                  "elements": [{"type": "text",
                                                                                                "text": "Hi"}]}]}],
                                   "channel": "DPKTY81UM", "event_ts": "1644670603.521219", "channel_type": "im"},
                         "type": "event_callback", "event_id": "Ev032U6W5N1G", "event_time": 1644670603,
                         "authed_users": ["UPKE20JE8"], "authorizations": [
                {"enterprise_id": None, "team_id": "TPKTMACSU", "user_id": "UPKE20JE8", "is_bot": True,
                 "is_enterprise_install": False}], "is_ext_shared_channel": False,
                         "event_context": "4-eyJldCI6Im1lc3NhZ2UiLCJ0aWQiOiJUUEtUTUFDU1UiLCJhaWQiOiJBUEtUWFJQTUsiLCJjaWQiOiJEUEtUWTgxVU0ifQ"}
    )
    actual = response.json()
    assert actual["error_code"] == 401
    assert actual == {"data": None, "success": False, "error_code": 401, "message": "Could not validate credentials"}


@patch('kairon.chat.handlers.channels.telegram.TelegramOutput')
@patch('kairon.shared.utils.Utility.get_local_mongo_store')
def test_telegram_auth_failed_telegram_verify(mock_store, mock_telegram_out):
    mock_store.return_value = empty_store
    mock_telegram_out.get_me.return_value = "test"
    patch.dict(Utility.environment['action'], {"url": None})
    response = client.post(
        f"/api/bot/telegram/{bot}/{token}",
        json={"update_id": 483117514, "message": {"message_id": 14,
                                                             "from": {"id": 1422280657, "is_bot": False,
                                                                      "first_name": "Fahad Ali",
                                                                      "language_code": "en"},
                                                             "chat": {"id": 1422280657, "first_name": "Fahad Ali",
                                                                      "type": "private"}, "date": 1645433258,
                                                             "text": "hi"}}
    )
    actual = response.json()
    assert actual == "failed"


def test_hangout_invalid_auth():
    patch.dict(Utility.environment['action'], {"url": None})
    response = client.post(
        f"/api/bot/hangouts/{bot}/123",
        json={
            "type": "MESSAGE",
            "message": {
                "sender": {
                    "displayName": "Test"
                },
                "text": "Hello!"
            },
            "space": {
                "type": "ROOM"
            }
        })
    actual = response.json()
    assert actual == {"data": None, "success": False, "error_code": 401, "message": "Could not validate credentials"}


@patch('kairon.chat.handlers.channels.hangouts.id_token.verify_token')
@patch('kairon.shared.utils.Utility.get_local_mongo_store')
def test_hangout_auth_failed_hangout_verify(mock_store, mock_verify_token):
    mock_store.return_value = empty_store
    mock_verify_token.side_effect = ValueError("test")
    patch.dict(Utility.environment['action'], {"url": None})
    with pytest.raises(Exception):
        response = client.post(
            f"/api/bot/hangouts/{bot}/{token}",
            headers={"Authorization": "Bearer Test"},
            json={
                "type": "MESSAGE",
                "message": {
                    "sender": {
                        "displayName": "Test"
                    },
                    "text": "Hello!"
                },
                "space": {
                    "type": "ROOM"
                }
            })
        actual = response.json()
        assert actual["error_code"] == 401


@patch('kairon.chat.handlers.channels.hangouts.id_token.verify_token')
def test_hangout_auth_hangout_verify(mock_verify_token):
    mock_verify_token.return_value = {"iss": "chat@system.gserviceaccount.com"}
    response = client.post(
            f"/api/bot/hangouts/{bot}/{token}",
            headers={"Authorization": "Bearer Test"},
            json={
                "type": "MESSAGE",
                "message": {
                    "sender": {
                        "displayName": "Test"
                    },
                    "text": None
                },
                "space": {
                    "type": "ROOM",
                    "displayName": "bot"
                }
            })
    actual = response.json()
    assert actual == {"status": "OK"}

    response = client.get(
        f"/api/bot/hangouts/{bot}/{token}",
        headers={"Authorization": "Bearer Test"},
        json={
            "type": "MESSAGE",
            "message": {
                "sender": {
                    "displayName": "Test"
                },
                "text": None
            },
            "space": {
                "type": "ROOM",
                "displayName": "bot"
            }
        })
    actual = response.json()
    assert actual == {"status": "ok"}


def test_messenger_invalid_auth():
    patch.dict(Utility.environment['action'], {"url": None})
    response = client.post(
        f"/api/bot/messenger/{bot}/123",
        headers={"X-Hub-Signature": "invalid"},
        json={
            "object": "page",
            "entry": [{
                "id": "104610528288640",
                "time": 1646648478575,
                "messaging": [{
                    "sender": {
                        "id": "4237571439620831"
                    },
                    "recipient": {
                        "id": "104610528288640"
                    },
                    "timestamp": 1646647205156,
                    "message": {
                        "mid": "m_J-gcviaJSGp427f7jzL2PBygi_iiuvCXf2eCu2qb-kr9onZGEYfSoC7TctL84humv0mbtH7GsQ0vmELAGS74Ew",
                        "text": "hi",
                        "nlp": {
                            "intents": [],
                            "entities": {
                                "wit$location:location": [{
                                    "id": "624173841772436",
                                    "name": "wit$location",
                                    "role": "location",
                                    "start": 0,
                                    "end": 2,
                                    "body": "hi",
                                    "confidence": 0.3146,
                                    "entities": [],
                                    "suggested": True,
                                    "value": "hi",
                                    "type": "value"
                                }]
                            },
                            "traits": {
                                "wit$sentiment": [{
                                    "id": "5ac2b50a-44e4-466e-9d49-bad6bd40092c",
                                    "value": "positive",
                                    "confidence": 0.7336
                                }],
                                "wit$greetings": [{
                                    "id": "5900cc2d-41b7-45b2-b21f-b950d3ae3c5c",
                                    "value": "true",
                                    "confidence": 0.9999
                                }]
                            },
                            "detected_locales": [{
                                "locale": "mr_IN",
                                "confidence": 0.7365
                            }]
                        }
                    }
                }]
            }]
        })
    actual = response.json()
    assert actual == {"data": None, "success": False, "error_code": 401, "message": "Could not validate credentials"}


def test_instagram_invalid_auth():
    patch.dict(Utility.environment['action'], {"url": None})
    response = client.post(
        f"/api/bot/instagram/{bot}/123",
        headers={"X-Hub-Signature": "invalid"},
        json={
            "object": "page",
            "entry": [{
                "id": "104610528288640",
                "time": 1646648478575,
                "messaging": [{
                    "sender": {
                        "id": "4237571439620831"
                    },
                    "recipient": {
                        "id": "104610528288640"
                    },
                    "timestamp": 1646647205156,
                    "message": {
                        "mid": "m_J-gcviaJSGp427f7jzL2PBygi_iiuvCXf2eCu2qb-kr9onZGEYfSoC7TctL84humv0mbtH7GsQ0vmELAGS74Ew",
                        "text": "hi",
                        "nlp": {
                            "intents": [],
                            "entities": {
                                "wit$location:location": [{
                                    "id": "624173841772436",
                                    "name": "wit$location",
                                    "role": "location",
                                    "start": 0,
                                    "end": 2,
                                    "body": "hi",
                                    "confidence": 0.3146,
                                    "entities": [],
                                    "suggested": True,
                                    "value": "hi",
                                    "type": "value"
                                }]
                            },
                            "traits": {
                                "wit$sentiment": [{
                                    "id": "5ac2b50a-44e4-466e-9d49-bad6bd40092c",
                                    "value": "positive",
                                    "confidence": 0.7336
                                }],
                                "wit$greetings": [{
                                    "id": "5900cc2d-41b7-45b2-b21f-b950d3ae3c5c",
                                    "value": "true",
                                    "confidence": 0.9999
                                }]
                            },
                            "detected_locales": [{
                                "locale": "mr_IN",
                                "confidence": 0.7365
                            }]
                        }
                    }
                }]
            }]
        })
    actual = response.json()
    assert actual == {"data": None, "success": False, "error_code": 401, "message": "Could not validate credentials"}


def test_whatsapp_invalid_token():
    response = client.post(
        f"/api/bot/whatsapp/{bot}/123",
        headers={"hub.verify_token": "invalid", "hub.challenge": "return test"}
    )
    actual = response.json()
    assert actual == {"data": None, "success": False, "error_code": 401, "message": "Could not validate credentials"}


def test_whatsapp_channel_not_configured():
    access_token, _ = Authentication.generate_integration_token(
        bot3, "test@chat.com", expiry=5, access_limit=['/api/bot/whatsapp/.+/.+'], name="whatsapp integration"
    )

    response = client.post(
        f"/api/bot/whatsapp/{bot3}/{access_token}",
        headers={"hub.verify_token": "valid", "X-USER": "udit"},
        json={
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "910123456789",
                            "phone_number_id": "12345678"
                        },
                        "contacts": [{
                            "profile": {
                                "name": "udit"
                            },
                            "wa_id": "wa-123456789"
                        }],
                        "messages": [{
                            "from": "910123456789",
                            "id": "wappmsg.ID",
                            "timestamp": "21-09-2022 12:05:00",
                            "text": {
                                "body": "hi"
                            },
                            "type": "text"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        })
    actual = response.json()
    assert actual == {"success":False, "message":"Channels matching query does not exist.", "data":None, "error_code":422}


def test_whatsapp_invalid_hub_signature():
    def _mock_validate_hub_signature(*args, **kwargs):
        return False

    with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
        response = client.post(
            f"/api/bot/whatsapp/{bot}/{token}",
            headers={"hub.verify_token": "valid"},
            json={
                "object": "whatsapp_business_account",
                "entry": [{
                    "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                    "changes": [{
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "910123456789",
                                "phone_number_id": "12345678"
                            },
                            "contacts": [{
                                "profile": {
                                    "name": "udit"
                                },
                                "wa_id": "wa-123456789"
                            }],
                            "messages": [{
                                "from": "910123456789",
                                "id": "wamid.ID",
                                "timestamp": "21-09-2022 12:05:00",
                                "text": {
                                    "body": "hi"
                                },
                                "type": "text"
                            }]
                        },
                        "field": "messages"
                    }]
                }]
            })
    actual = response.json()
    assert actual == 'not validated'


@responses.activate
def test_whatsapp_valid_text_message_request():
    def _mock_validate_hub_signature(*args, **kwargs):
        return True

    responses.add(
        "POST", "https://graph.facebook.com/v13.0/12345678/messages", json={}
    )
    with mock.patch.object(EndpointConfig, "request") as mock_action_execution:
        mock_action_execution.return_value = {"responses": [{"response": "Welcome to kairon!"}], "events": []}

        with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
            response = client.post(
                f"/api/bot/whatsapp/{bot}/{token}",
                headers={"hub.verify_token": "valid"},
                json={
                    "object": "whatsapp_business_account",
                    "entry": [{
                        "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                        "changes": [{
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "910123456789",
                                    "phone_number_id": "12345678"
                                },
                                "contacts": [{
                                    "profile": {
                                        "name": "udit"
                                    },
                                    "wa_id": "wa-123456789"
                                }],
                                "messages": [{
                                    "from": "910123456789",
                                    "id": "wappmsg.ID",
                                    "timestamp": "21-09-2022 12:05:00",
                                    "text": {
                                        "body": "hi"
                                    },
                                    "type": "text"
                                }]
                            },
                            "field": "messages"
                        }]
                    }]
                })
        mock_action_execution.assert_awaited_once()

    actual = response.json()
    assert actual == 'success'
    assert MeteringProcessor.get_metric_count(user['account'], metric_type=MetricType.prod_chat,
                                              channel_type="whatsapp") > 0


@responses.activate
@mock.patch("kairon.chat.handlers.channels.whatsapp.Whatsapp.process_message", autospec=True)
def test_whatsapp_exception_when_try_to_handle_webhook_for_whatsapp_message(mock_process_message):
    def _mock_validate_hub_signature(*args, **kwargs):
        return True

    responses.add(
        "POST", "https://graph.facebook.com/v13.0/12345678/messages", json={}
    )
    mock_process_message.side_effect = Exception
    with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
        response = client.post(
            f"/api/bot/whatsapp/{bot}/{token}",
            headers={"hub.verify_token": "valid"},
            json={
                "object": "whatsapp_business_account",
                "entry": [{
                    "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                    "changes": [{
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "910123456789",
                                "phone_number_id": "12345678"
                            },
                            "contacts": [{
                                "profile": {
                                    "name": "udit"
                                },
                                "wa_id": "wa-123456789"
                            }],
                            "messages": [{
                                "from": "910123456789",
                                "id": "wappmsg.ID",
                                "timestamp": "21-09-2022 12:05:00",
                                "text": {
                                    "body": "hi"
                                },
                                "type": "text"
                            }]
                        },
                        "field": "messages"
                    }]
                }]
            })
    actual = response.json()
    assert actual == 'success'


@responses.activate
def test_whatsapp_valid_button_message_request():
    def _mock_validate_hub_signature(*args, **kwargs):
        return True

    responses.add(
        "POST", "https://graph.facebook.com/v13.0/12345678/messages", json={}
    )

    with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
        with mock.patch("kairon.chat.handlers.channels.whatsapp.Whatsapp._handle_user_message",
                        autospec=True) as whatsapp_msg_handler:
            response = client.post(
                f"/api/bot/whatsapp/{bot}/{token}",
                headers={"hub.verify_token": "valid"},
                json={
                    "object": "whatsapp_business_account",
                    "entry": [{
                        "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                        "changes": [{
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "910123456789",
                                    "phone_number_id": "12345678"
                                },
                                "contacts": [{
                                    "profile": {
                                        "name": "udit"
                                    },
                                    "wa_id": "wa-123456789"
                                }],
                                "messages": [{
                                    "from": "910123456789",
                                    "id": "wappmsg.ID",
                                    "timestamp": "21-09-2022 12:05:00",
                                    "button": {
                                        "text": "buy now",
                                        "payload": "buy kairon for 1 billion"
                                    },
                                    "type": "button"
                                }]
                            },
                            "field": "messages"
                        }]
                    }]
                })
    actual = response.json()
    assert actual == 'success'
    assert len(whatsapp_msg_handler.call_args[0]) == 5
    assert whatsapp_msg_handler.call_args[0][1] == 'buy now'
    assert whatsapp_msg_handler.call_args[0][2] == '910123456789'
    metadata = whatsapp_msg_handler.call_args[0][3]
    metadata.pop("timestamp")
    assert metadata == {'from': '910123456789', 'id': 'wappmsg.ID',
                        'button': {'text': 'buy now', 'payload': 'buy kairon for 1 billion'}, 'type': 'button',
                        'is_integration_user': True, 'bot': bot, 'account': 1, 'channel_type': 'whatsapp',
                        'tabname': 'default',
                        'bsp_type': 'meta', 'display_phone_number': '910123456789', 'phone_number_id': '12345678'}
    assert whatsapp_msg_handler.call_args[0][4] == bot


@responses.activate
def test_whatsapp_valid_attachment_message_request():
    def _mock_validate_hub_signature(*args, **kwargs):
        return True

    responses.add(
        "POST", "https://graph.facebook.com/v13.0/12345678/messages", json={}
    )
    responses.add(
        "GET", "https://graph.facebook.com/v13.0/sdfghj567",
        json={
            "messaging_product": "whatsapp",
            "url": "http://kairon-media.url",
            "id": "sdfghj567"
        }
    )

    with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
        with mock.patch("kairon.chat.handlers.channels.whatsapp.Whatsapp._handle_user_message",
                        autospec=True) as whatsapp_msg_handler:
            response = client.post(
                f"/api/bot/whatsapp/{bot}/{token}",
                headers={"hub.verify_token": "valid"},
                json={
                    "object": "whatsapp_business_account",
                    "entry": [{
                        "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                        "changes": [{
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "910123456789",
                                    "phone_number_id": "12345678"
                                },
                                "contacts": [{
                                    "profile": {
                                        "name": "udit"
                                    },
                                    "wa_id": "wa-123456789"
                                }],
                                "messages": [{
                                    "from": "910123456789",
                                    "id": "wappmsg.ID",
                                    "timestamp": "21-09-2022 12:05:00",
                                    "document": {
                                        "id": "sdfghj567"
                                    },
                                    "type": "document"
                                }]
                            },
                            "field": "messages"
                        }]
                    }]
                })
    actual = response.json()
    assert actual == 'success'
    assert len(whatsapp_msg_handler.call_args[0]) == 5
    assert whatsapp_msg_handler.call_args[0][1] == '/k_multimedia_msg{"document": "sdfghj567"}'
    assert whatsapp_msg_handler.call_args[0][2] == '910123456789'
    metadata = whatsapp_msg_handler.call_args[0][3]
    metadata.pop("timestamp")
    assert metadata == {'from': '910123456789', 'id': 'wappmsg.ID', 'document': {'id': 'sdfghj567'},
                        'type': 'document', 'is_integration_user': True, 'bot': bot, 'account': 1,
                        'channel_type': 'whatsapp', 'bsp_type': 'meta', 'display_phone_number': '910123456789',
                        'phone_number_id': '12345678', 'tabname': 'default'}
    assert whatsapp_msg_handler.call_args[0][4] == bot


@responses.activate
def test_whatsapp_valid_order_message_request():
    def _mock_validate_hub_signature(*args, **kwargs):
        return True

    with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
        with mock.patch("kairon.chat.handlers.channels.whatsapp.Whatsapp._handle_user_message",
                        autospec=True) as whatsapp_msg_handler:
            response = client.post(
                f"/api/bot/whatsapp/{bot}/{token}",
                headers={"hub.verify_token": "valid"},
                json={
                    "object": "whatsapp_business_account",
                    "entry": [{
                        "id": "108103872212677",
                        "changes": [{
                            "value": {
                                "messaging_product": "whatsapp",
                                "metadata": {
                                    "display_phone_number": "919876543210",
                                    "phone_number_id": "108578266683441"
                                },
                                "contacts": [{
                                    "profile": {
                                        "name": "Hitesh"
                                    },
                                    "wa_id": "919876543210"
                                }],
                                "messages": [{
                                    "from": "919876543210",
                                    "id": "wamid.HBgMOTE5NjU3DMU1MDIyQFIAEhggNzg5MEYwNEIyNDA1Q0IxMzU2QkI0NDc3RTVGMzYxNUEA",
                                    "timestamp": "1691598412",
                                    "type": "order",
                                    "order": {
                                        "catalog_id": "538971028364699",
                                        "product_items": [{
                                            "product_retailer_id": "akuba13e44",
                                            "quantity": 1,
                                            "item_price": 200,
                                            "currency": "INR"
                                        }, {
                                            "product_retailer_id": "0z10aj0bmq",
                                            "quantity": 1,
                                            "item_price": 600,
                                            "currency": "INR"
                                        }]
                                    }
                                }]
                            },
                            "field": "messages"
                        }]
                    }]
                })
    actual = response.json()
    assert actual == 'success'
    assert len(whatsapp_msg_handler.call_args[0]) == 5
    assert whatsapp_msg_handler.call_args[0][1] == '/k_order_msg{"order": {\"catalog_id\": \"538971028364699\", \"product_items\": [{\"product_retailer_id\": \"akuba13e44\", \"quantity\": 1, \"item_price\": 200, \"currency\": \"INR\"}, {\"product_retailer_id\": \"0z10aj0bmq\", \"quantity\": 1, \"item_price\": 600, \"currency\": \"INR\"}]}'
    assert whatsapp_msg_handler.call_args[0][2] == '919876543210'
    metadata = whatsapp_msg_handler.call_args[0][3]
    metadata.pop("timestamp")
    assert metadata == {'from': '919876543210',
                        'id': 'wamid.HBgMOTE5NjU3DMU1MDIyQFIAEhggNzg5MEYwNEIyNDA1Q0IxMzU2QkI0NDc3RTVGMzYxNUEA',
                        'type': 'order', 'order': {'catalog_id': '538971028364699',
                                                   'product_items': [{'product_retailer_id': 'akuba13e44',
                                                                      'quantity': 1, 'item_price': 200,
                                                                      'currency': 'INR'},
                                                                     {'product_retailer_id': '0z10aj0bmq',
                                                                      'quantity': 1, 'item_price': 600,
                                                                      'currency': 'INR'}]},
                        'is_integration_user': True, 'bot': bot, 'account': 1,
                        'channel_type': 'whatsapp', 'bsp_type': 'meta', 'tabname': 'default',
                        'display_phone_number': '919876543210', 'phone_number_id': '108578266683441'}
    assert whatsapp_msg_handler.call_args[0][4] == bot


@responses.activate
def test_whatsapp_valid_unsupported_message_request():
    def _mock_validate_hub_signature(*args, **kwargs):
        return True

    responses.add(
        "POST", "https://graph.facebook.com/v13.0/12345678/messages", json={}
    )

    with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
        response = client.post(
            f"/api/bot/whatsapp/{bot}/{token}",
            headers={"hub.verify_token": "valid"},
            json={
                "object": "whatsapp_business_account",
                "entry": [{
                    "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                    "changes": [{
                        "value": {
                            "messaging_product": "whatsapp",
                            "metadata": {
                                "display_phone_number": "910123456789",
                                "phone_number_id": "12345678"
                            },
                            "contacts": [{
                                "profile": {
                                    "name": "udit"
                                },
                                "wa_id": "wa-123456789"
                            }],
                            "messages": [{
                                "from": "910123456789",
                                "id": "wappmsg.ID",
                                "timestamp": "21-09-2022 12:05:00",
                                "text": {
                                    "body": "hi"
                                },
                                "type": "text"
                            }]
                        },
                        "field": "messages"
                    }]
                }]
            })
    actual = response.json()
    assert actual == 'success'


@responses.activate
def test_whatsapp_bsp_valid_text_message_request():
    responses.add(
        "POST", "https://waba-v2.360dialog.io/v1/messages", json={}
    )
    responses.add(
        "PUT", 'https://waba-v2.360dialog.io/v1/messages/ABEGkZZXBVAiAhAJeqFQ3Yfld16XGKKsgUYK', json={}
    )
    response = client.post(
        f"/api/bot/whatsapp/{bot2}/{token}",
        json={
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "910123456789",
                            "phone_number_id": "12345678"
                        },
                        "contacts": [{
                            "profile": {
                                "name": "udit"
                            },
                            "wa_id": "wa-123456789"
                        }],
                        "messages": [{
                            "from": "910123456789",
                            "id": "wappmsg.ID",
                            "timestamp": "21-09-2022 12:05:00",
                            "text": {
                                "body": "hi"
                            },
                            "type": "text"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        })
    actual = response.json()
    assert actual == 'success'
    responses.reset()


@responses.activate
def test_whatsapp_bsp_valid_button_message_request():
    responses.add(
        "POST", "https://waba-v2.360dialog.io/v1/messages", json={}
    )
    responses.add(
        "PUT", 'https://waba-v2.360dialog.io/v1/messages/ABEGkZZXBVAiAhAJeqFQ3Yfld16XGKKsgUYK', json={}
    )
    response = client.post(
        f"/api/bot/whatsapp/{bot2}/{token}",
        json={
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "910123456789",
                            "phone_number_id": "12345678"
                        },
                        "contacts": [{
                            "profile": {
                                "name": "udit"
                            },
                            "wa_id": "wa-123456789"
                        }],
                        "messages": [{
                            "from": "910123456789",
                            "id": "wappmsg.ID",
                            "timestamp": "21-09-2022 12:05:00",
                            "button": {
                                "text": "buy now",
                                "payload": "buy kairon for 1 billion"
                            },
                            "type": "button"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        })
    actual = response.json()
    assert actual == 'success'
    responses.reset()


@responses.activate
def test_whatsapp_bsp_valid_attachment_message_request():
    responses.add(
        "POST", "https://waba-v2.360dialog.io/v1/messages", json={}
    )
    responses.add(
        "PUT", 'https://waba-v2.360dialog.io/v1/messages/ABEGkZZXBVAiAhAJeqFQ3Yfld16XGKKsgUYK', json={}
    )

    response = client.post(
        f"/api/bot/whatsapp/{bot2}/{token}",
        headers={"hub.verify_token": "valid"},
        json={
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "WHATSAPP_BUSINESS_ACCOUNT_ID",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "910123456789",
                            "phone_number_id": "12345678"
                        },
                        "contacts": [{
                            "profile": {
                                "name": "udit"
                            },
                            "wa_id": "wa-123456789"
                        }],
                        "messages": [{
                            "from": "910123456789",
                            "id": "wappmsg.ID",
                            "timestamp": "21-09-2022 12:05:00",
                            "document": {"id": "sdfghj567"},
                            "type": "document"
                        }]
                    },
                    "field": "messages"
                }]
            }]
        })
    actual = response.json()
    assert actual == 'success'
    responses.reset()


@responses.activate
def test_whatsapp_bsp_valid_order_message_request():
    responses.add(
        "POST", "https://waba-v2.360dialog.io/messages", json={}
    )

    response = client.post(
        f"/api/bot/whatsapp/{bot2}/{token}",
        headers={"hub.verify_token": "valid"},
        json={
            "object": "whatsapp_business_account",
            "entry": [{
                "id": "108103872212677",
                "changes": [{
                    "value": {
                        "messaging_product": "whatsapp",
                        "metadata": {
                            "display_phone_number": "919876543210",
                            "phone_number_id": "108578266683441"
                        },
                        "contacts": [{
                            "profile": {
                                "name": "Hitesh"
                            },
                            "wa_id": "919876543210"
                        }],
                        "messages": [{
                            "from": "919876543210",
                            "id": "wamid.HBoMOTE5NjU3MDU1MDIyFQIAEhggNzg5MEYwNEIyNDA1Q0IxMzU4QkI0NDc3RTVGMzYxNUEA",
                            "timestamp": "1691598412",
                            "type": "order",
                            "order": {
                                "catalog_id": "538971028364699",
                                "product_items": [{
                                    "product_retailer_id": "akuba13e44",
                                    "quantity": 1,
                                    "item_price": 200,
                                    "currency": "INR"
                                }, {
                                    "product_retailer_id": "0z10aj0bmq",
                                    "quantity": 1,
                                    "item_price": 600,
                                    "currency": "INR"
                                }]
                            }
                        }]
                    },
                    "field": "messages"
                }]
            }]
        })
    actual = response.json()
    assert actual == 'success'
    responses.reset()


def add_live_agent_config(bot_id, email):
    config = {
        "agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
        "override_bot": False, "trigger_on_intents": ["nlu_fallback"],
        "trigger_on_actions": ["action_default_fallback"]
    }
    responses.reset()
    responses.start()
    responses.add(
        "GET",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json={"payload": []}
    )
    responses.add(
        "POST",
        f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
        json={"inbox_identifier": "tSaxZWrxyFowmFHzWwhMwi5y"}
    )
    LiveAgentsProcessor.save_config(config, bot_id, email)
    responses.stop()


@patch("rasa.core.tracker_store.TrackerStore.serialise_tracker")
@patch("kairon.live_agent.chatwoot.ChatwootLiveAgent.getBusinesshours")
@patch("kairon.live_agent.chatwoot.ChatwootLiveAgent.validate_businessworkinghours")
def test_chat_with_chatwoot_agent_fallback(mock_validatebusinesshours, mock_getbusinesshrs, mock_tracker):
    add_live_agent_config(bot, user["email"])
    responses.reset()
    responses.start()
    responses.add(
        "POST", 'https://app.chatwoot.com/public/api/v1/inboxes/tSaxZWrxyFowmFHzWwhMwi5y/contacts',
        json={
            "source_id": "09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71",
            "pubsub_token": "M31nmFCfo2wc5FonU3qGjonB",
            "id": 16951464,
            "name": 'test@chat.com',
            "email": None
        }
    )
    responses.add(
        "POST",
        'https://app.chatwoot.com/public/api/v1/inboxes/tSaxZWrxyFowmFHzWwhMwi5y/contacts/09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71/conversations',
        json={
            "id": 2,
            "inbox_id": 14036,
            "contact_last_seen_at": 0,
            "status": "open",
            "agent_last_seen_at": 0,
            "messages": [],
            "contact": {
                "id": 16951464,
                "name": "test@chat.com",
                "email": None,
                "phone_number": None,
                "account_id": 69469,
                "created_at": "2022-05-04T15:40:58.190Z",
                "updated_at": "2022-05-04T15:40:58.190Z",
                "additional_attributes": {},
                "identifier": None,
                "custom_attributes": {},
                "last_activity_at": None,
                "label_list": []
            }
        }
    )
    responses.add(
        "POST",
        'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
        json={
            "id": 7487848,
            "content": "hello",
            "inbox_id": 14036,
            "conversation_id": 2,
            "message_type": 0,
            "content_type": "text",
            "content_attributes": {},
            "created_at": 1651679560,
            "private": False,
            "source_id": None,
            "sender": {
                "additional_attributes": {},
                "custom_attributes": {},
                "email": None,
                "id": 16951464,
                "identifier": None,
                "name": "test@chat.com",
                "phone_number": None,
                "thumbnail": "",
                "type": "contact"
            }
        }
    )

    mock_events_data = '{"events": [{"event": "session_started"}, {"event": "user", "text": "hi"}, {"event": "bot", "text": "welcome to kairon!", "data": {}}]}'
    mock_tracker.return_value = mock_events_data

    with patch.object(Utility, "get_local_mongo_store") as mocked:
        mocked.side_effect = empty_store
        patch.dict(Utility.environment['action'], {"url": None})
        with patch.object(Agent, "handle_message") as mock_agent:
            mock_agent.side_effect = mock_agent_response
            mock_getbusinesshrs.side_effect = __mock_getbusinessdata_workingenabled
            mock_validatebusinesshours.side_effect = __mock_validate_businessworkinghours_true
            response = client.post(
                f"/api/bot/{bot}/chat",
                json={"data": "!@#$%^&*()"},
                headers={"Authorization": token_type + " " + token},
                timeout=0,
            )
            responses.stop()
            actual = response.json()
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"]
            assert Utility.check_empty_string(actual["message"])
            assert isinstance(actual["data"]["nlu"], dict)
            assert actual["data"]["nlu"]["intent"]
            assert actual["data"]["nlu"]["entities"] == []
            assert actual["data"]["nlu"]["intent_ranking"]
            assert actual["data"]["nlu"]["response_selector"]
            assert actual["data"]["nlu"]["slots"]
            assert isinstance(actual["data"]["action"], list)
            assert actual["data"]["response"]
            assert actual["data"]["agent_handoff"] == {'initiate': True, 'type': 'chatwoot',
                                                       'additional_properties': {
                                                           'destination': 2,
                                                           'pubsub_token': 'M31nmFCfo2wc5FonU3qGjonB',
                                                           'websocket_url': 'wss://app.chatwoot.com/cable',
                                                           'inbox_id': 14036
                                                       }}

            data = MeteringProcessor.get_logs(user["account"], bot=bot, metric_type="agent_handoff")
            assert len(data["logs"]) > 0
            assert len(data["logs"]) == data["total"]
            assert MeteringProcessor.get_metric_count(user['account'], metric_type=MetricType.agent_handoff) > 0


@patch("rasa.core.tracker_store.TrackerStore.serialise_tracker")
@patch("kairon.live_agent.chatwoot.ChatwootLiveAgent.getBusinesshours")
def test_chat_with_chatwoot_agent_fallback_existing_contact(mock_businesshours, mock_tracker):
    with patch.object(Utility, "get_local_mongo_store") as mocked:
        mocked.side_effect = empty_store
        patch.dict(Utility.environment['action'], {"url": None})
        with patch.object(KaironAgent, "handle_message") as mock_agent:
            mock_agent.side_effect = mock_agent_response
            mock_businesshours.side_effect = __mock_getbusinessdata_workingdisabled
            responses.reset()
            responses.start()
            responses.add(
                "POST", 'https://app.chatwoot.com/public/api/v1/inboxes/tSaxZWrxyFowmFHzWwhMwi5y/contacts',
                json={
                    "source_id": "09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71",
                    "pubsub_token": "M31nmFCfo2wc5FonU3qGjonB",
                    "id": 16951464,
                    "name": 'test@chat.com',
                    "email": None
                }
            )
            responses.add(
                "POST",
                'https://app.chatwoot.com/public/api/v1/inboxes/tSaxZWrxyFowmFHzWwhMwi5y/contacts/09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71/conversations',
                json={
                    "id": 3,
                    "inbox_id": 14036,
                    "contact_last_seen_at": 0,
                    "status": "open",
                    "agent_last_seen_at": 0,
                    "messages": [],
                    "contact": {
                        "id": 16951464,
                        "name": "test@chat.com",
                        "email": None,
                        "phone_number": None,
                        "account_id": 69469,
                        "created_at": "2022-05-04T15:40:58.190Z",
                        "updated_at": "2022-05-04T15:40:58.190Z",
                        "additional_attributes": {},
                        "identifier": None,
                        "custom_attributes": {},
                        "last_activity_at": None,
                        "label_list": []
                    }
                }
            )
            responses.add(
                "POST",
                'https://app.chatwoot.com/api/v1/accounts/12/conversations/3/messages',
                json={
                    "id": 7487848,
                    "content": "who can i contact?",
                    "inbox_id": 14036,
                    "conversation_id": 3,
                    "message_type": 0,
                    "content_type": "text",
                    "content_attributes": {},
                    "created_at": 1651679560,
                    "private": False,
                    "source_id": None,
                    "sender": {
                        "additional_attributes": {},
                        "custom_attributes": {},
                        "email": None,
                        "id": 16951464,
                        "identifier": None,
                        "name": "test@chat.com",
                        "phone_number": None,
                        "thumbnail": "",
                        "type": "contact"
                    }
                }
            )

            mock_events_data = '{"events": [{"event": "session_started"}, {"event": "user", "text": "hi"}, {"event": "bot", "text": "welcome to kairon!", "data": {}}]}'
            mock_tracker.return_value = mock_events_data

            response = client.post(
                f"/api/bot/{bot}/chat",
                json={"data": "@#$%^&*()_"},
                headers={"Authorization": token_type + " " + token},
                timeout=0,
            )
            responses.stop()
            actual = response.json()
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"]
            assert Utility.check_empty_string(actual["message"])
            assert isinstance(actual["data"]["nlu"], dict)
            assert actual["data"]["nlu"]["intent"]
            assert actual["data"]["nlu"]["entities"] == []
            assert actual["data"]["nlu"]["intent_ranking"]
            assert actual["data"]["nlu"]["response_selector"]
            assert actual["data"]["nlu"]["slots"]
            assert isinstance(actual["data"]["action"], list)
            assert actual["data"]["response"]
            assert actual["data"]["agent_handoff"] == {'initiate': True, 'type': 'chatwoot',
                                                       'additional_properties': {
                                                           'destination': 3,
                                                           'pubsub_token': 'M31nmFCfo2wc5FonU3qGjonB',
                                                           'websocket_url': 'wss://app.chatwoot.com/cable',
                                                           'inbox_id': 14036
                                                       }}
            data = MeteringProcessor.get_logs(user["account"], bot=bot, metric_type="agent_handoff")
            assert len(data["logs"]) > 0
            assert len(data["logs"]) == data["total"]
            assert MeteringProcessor.get_metric_count(user['account'], metric_type=MetricType.agent_handoff) == 2


def test_chat_with_live_agent():
    responses.reset()
    responses.start()
    responses.add(
        "POST",
        'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
        json={
            "id": 7487848,
            "content": "hello, please resolve my ticket",
            "inbox_id": 14036,
            "conversation_id": 2,
            "message_type": 0,
            "content_type": "text",
            "content_attributes": {},
            "created_at": 1651679560,
            "private": False,
            "source_id": None,
            "sender": {
                "additional_attributes": {},
                "custom_attributes": {},
                "email": None,
                "id": 16951464,
                "identifier": None,
                "name": "test@chat.com",
                "phone_number": None,
                "thumbnail": "",
                "type": "contact"
            }
        }
    )
    response = client.post(
        f"/api/bot/{bot}/agent/live/2",
        json={"data": "hello, please resolve my ticket"},
        headers={"Authorization": token_type + " " + token},
        timeout=0,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]
    assert Utility.check_empty_string(actual["message"])
    responses.stop()


def test_chat_with_live_agent_failed_to_send_message():
    responses.reset()
    responses.start()
    responses.add(
        "POST",
        'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
        status=503,
        body="Temporarily unable to handle a request"
    )
    response = client.post(
        f"/api/bot/{bot}/agent/live/2",
        json={"data": "need help"},
        headers={"Authorization": token_type + " " + token},
        timeout=0,
    )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == "Failed to send message: Service Unavailable"
    responses.stop()


def test_chat_with_live_agent_with_integration_token():
    access_token = chat_client_config['config']['headers']['authorization']['access_token']
    token_type = chat_client_config['config']['headers']['authorization']['token_type']
    responses.reset()
    responses.start()
    responses.add(
        "POST",
        'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
        json={
            "id": 7487848,
            "content": "need help",
            "inbox_id": 14036,
            "conversation_id": 2,
            "message_type": 0,
            "content_type": "text",
            "content_attributes": {},
            "created_at": 1651679560,
            "private": False,
            "source_id": None,
            "sender": {
                "additional_attributes": {},
                "custom_attributes": {},
                "email": None,
                "id": 16951464,
                "identifier": None,
                "name": "test@chat.com",
                "phone_number": None,
                "thumbnail": "",
                "type": "contact"
            }
        }
    )
    response = client.post(
        f"/api/bot/{bot}/agent/live/2",
        json={"data": "need help"},
        headers={"Authorization": f"{token_type} {access_token}", "X-USER": "test@chat.com"},
        timeout=0,
    )
    actual = response.json()
    assert actual["success"]
    assert actual["error_code"] == 0
    assert actual["data"]["response"]
    assert Utility.check_empty_string(actual["message"])
    responses.stop()


def test_chat_with_chatwoot_agent_fallback_failed_to_initiate():
    with patch.object(Utility, "get_local_mongo_store") as mocked:
        mocked.side_effect = empty_store
        patch.dict(Utility.environment['action'], {"url": None})
        with patch.object(KaironAgent, "handle_message") as mock_agent:
            mock_agent.side_effect = mock_agent_response
            responses.reset()
            responses.start()
            responses.add(
                "POST", 'https://app.chatwoot.com/public/api/v1/inboxes/tSaxZWrxyFowmFHzWwhMwi5y/contacts',
                json={
                    "source_id": "09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71",
                    "pubsub_token": "M31nmFCfo2wc5FonU3qGjonB",
                    "id": 16951464,
                    "name": 'test@chat.com',
                    "email": None
                }
            )
            responses.add(
                "POST",
                'https://app.chatwoot.com/public/api/v1/inboxes/tSaxZWrxyFowmFHzWwhMwi5y/contacts/09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71/conversations',
                status=503,
                body="Temporarily unable to handle a request"
            )

            response = client.post(
                f"/api/bot/{bot}/chat",
                json={"data": "!@#$%^&*()"},
                headers={"Authorization": token_type + " " + token},
                timeout=0,
            )
            actual = response.json()
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"]
            assert Utility.check_empty_string(actual["message"])
            assert isinstance(actual["data"]["nlu"], dict)
            assert actual["data"]["nlu"]["intent"]
            assert actual["data"]["nlu"]["entities"] == []
            assert actual["data"]["nlu"]["intent_ranking"]
            assert actual["data"]["nlu"]["response_selector"]
            assert actual["data"]["nlu"]["slots"]
            assert isinstance(actual["data"]["action"], list)
            assert actual["data"]["response"]
            assert actual["data"]["agent_handoff"] == {'initiate': False, 'type': 'chatwoot',
                                                       'additional_properties': None}
            responses.reset()
            responses.stop()
            data = MeteringProcessor.get_logs(user["account"], bot=bot, metric_type="agent_handoff")
            assert len(data["logs"]) == 3
            assert len(data["logs"]) == data["total"]
            assert data["logs"][0]['exception'] == 'Failed to create conversation: Service Unavailable'


def test_chat_with_bot_after_reset_passwrd():
    user = AccountProcessor.get_complete_user_details("resetpaswrd@chat.com")
    bot = user['bots']['account_owned'][0]['_id']
    access_token = Authentication.create_access_token(
        data={"sub": "resetpaswrd@chat.com", 'access-limit': ['/api/bot/.+/chat']},
    )
    UserActivityLogger.add_log(account=1, a_type=UserActivityType.reset_password.value, email='resetpaswrd@chat.com', bot=bot)
    response = client.post(
        f"/api/bot/{bot}/chat",
        json={"data": "Hi"},
        headers={
            "Authorization": f"{token_type} {access_token}", 'X-USER': 'testUser'
        },
    )
    actual = response.json()
    message = actual.get("message")
    error_code = actual.get("error_code")
    assert error_code == 401
    assert message == 'Session expired. Please login again.'


def test_reload_after_reset_passwrd():
    user = AccountProcessor.get_complete_user_details("resetpaswrd@chat.com")
    bot = user['bots']['account_owned'][0]['_id']
    access_token, _, _, _ = Authentication.authenticate("resetpaswrd@chat.com", "resetPswrd@12")
    UserActivityLogger.add_log(account=1, a_type=UserActivityType.reset_password.value, email='resetpaswrd@chat.com', bot=bot)
    reload_response = client.get(
        f"/api/bot/{bot}/reload",
        headers={
            "Authorization": token_type + " " + access_token
        },
    )
    reload_actual = reload_response.json()
    message = reload_actual.get("message")
    error_code = reload_actual.get("error_code")
    assert error_code == 401
    assert message == 'Session expired. Please login again.'


def test_live_agent_after_reset_passwrd():
    user = AccountProcessor.get_complete_user_details("resetpaswrd@chat.com")
    bot = user['bots']['account_owned'][0]['_id']
    access_token, _, _, _ = Authentication.authenticate("resetpaswrd@chat.com", "resetPswrd@12")
    UserActivityLogger.add_log(account=1, a_type=UserActivityType.reset_password.value, email='resetpaswrd@chat.com', bot=bot)
    live_response = client.post(
        f"/api/bot/{bot}/agent/live/2",
        json={"data": "need help"},
        headers={"Authorization": token_type + " " + access_token},
        timeout=0,
    )
    live_actual = live_response.json()
    message = live_actual.get("message")
    error_code = live_actual.get("error_code")
    assert error_code == 401
    assert message == 'Session expired. Please login again.'


def test_get_chat_history():
    access_token = chat_client_config['config']['headers']['authorization']['access_token']
    token_type = chat_client_config['config']['headers']['authorization']['token_type']
    events = [
        {
            "event": "session_started",
            "timestamp": 1656992881.55342
        },
        {
            "event": "user",
            "timestamp": 1656992882.02479,
            "text": "hi"
        },
        {
            "event": "bot",
            "timestamp": 1656992882.16756,
            "text": "Welcome to SE bot"
        },
        {
            "event": "user",
            "timestamp": 1656993828.00259,
            "text": "what are the medium priority items"
        },
        {
            "event": "bot",
            "timestamp": 1656993958.06978,
            "text": "I have failed to process your request"
        }
    ]

    with patch.object(ChatUtils, "get_last_session_conversation") as mocked:
        mocked.return_value = events, "connected to db"
        response = client.get(
            f"/api/bot/{bot}/conversation",
            headers={"Authorization": token_type + " " + token},
            timeout=0,
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"] == events
        assert actual["data"]
        assert actual["message"]

        response = client.get(
            f"/api/bot/{bot}/conversation",
            headers={"Authorization": f"{token_type} {access_token}"},
            timeout=0,
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"] == events
        assert actual["data"]
        assert actual["message"]


def test_get_chat_history_empty():
    events = []

    with patch.object(ChatUtils, "get_last_session_conversation") as mocked:
        mocked.return_value = events, "connected to db"
        response = client.get(
            f"/api/bot/{bot}/conversation",
            headers={"Authorization": token_type + " " + token},
        )
        actual = response.json()
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"] == events
        assert actual["message"]


def test_get_chat_history_user_exception():
    def _raise_err(*args, **kwargs):
        raise AppException("Mongo object out of memory")

    with patch.object(ChatUtils, "get_last_session_conversation") as mocked:
        mocked.side_effect = _raise_err
        response = client.get(
            f"/api/bot/{bot3}/conversation",
            headers={
                "Authorization": f"{token_type} {token}"
            },
        )
    actual = response.json()
    assert not actual["success"]
    assert actual["error_code"] == 422
    assert actual["data"] is None
    assert actual["message"] == 'Mongo object out of memory'


def test_get_chat_history_http_error():
    user = AccountProcessor.get_complete_user_details("resetpaswrd@chat.com")
    bot = user['bots']['account_owned'][0]['_id']
    access_token, _, _, _ = Authentication.authenticate("resetpaswrd@chat.com", "resetPswrd@12")
    UserActivityLogger.add_log(account=1, a_type=UserActivityType.reset_password.value, email='resetpaswrd@chat.com', bot=bot)
    reload_response = client.get(
        f"/api/bot/{bot}/conversation",
        headers={
            "Authorization": token_type + " " + access_token
        },
    )
    reload_actual = reload_response.json()
    message = reload_actual.get("message")
    error_code = reload_actual.get("error_code")
    assert error_code == 401
    assert message == "Session expired. Please login again."


@patch("kairon.live_agent.chatwoot.ChatwootLiveAgent.getBusinesshours")
@patch("kairon.live_agent.chatwoot.ChatwootLiveAgent.validate_businessworkinghours")
def test_chat_with_chatwoot_agent_outof_workinghours(mock_validatebusiness, mock_getbusiness):
    add_live_agent_config(bot, user["email"])
    responses.reset()
    responses.start()
    responses.add(
        "POST", 'https://app.chatwoot.com/public/api/v1/inboxes/tSaxZWrxyFowmFHzWwhMwi5y/contacts',
        json={
            "source_id": "09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71",
            "pubsub_token": "M31nmFCfo2wc5FonU3qGjonB",
            "id": 16951464,
            "name": 'test@chat.com',
            "email": None
        }
    )
    responses.add(
        "POST",
        'https://app.chatwoot.com/public/api/v1/inboxes/tSaxZWrxyFowmFHzWwhMwi5y/contacts/09c15b5f-c4a4-4d15-ba45-ce99bc7b1e71/conversations',
        json={
            "id": 2,
            "inbox_id": 14036,
            "contact_last_seen_at": 0,
            "status": "open",
            "agent_last_seen_at": 0,
            "messages": [],
            "contact": {
                "id": 16951464,
                "name": "test@chat.com",
                "email": None,
                "phone_number": None,
                "account_id": 69469,
                "created_at": "2022-05-04T15:40:58.190Z",
                "updated_at": "2022-05-04T15:40:58.190Z",
                "additional_attributes": {},
                "identifier": None,
                "custom_attributes": {},
                "last_activity_at": None,
                "label_list": []
            }
        }
    )
    responses.add(
        "POST",
        'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
        json={
            "id": 7487848,
            "content": "hello",
            "inbox_id": 14036,
            "conversation_id": 2,
            "message_type": 0,
            "content_type": "text",
            "content_attributes": {},
            "created_at": 1651679560,
            "private": False,
            "source_id": None,
            "sender": {
                "additional_attributes": {},
                "custom_attributes": {},
                "email": None,
                "id": 16951464,
                "identifier": None,
                "name": "test@chat.com",
                "phone_number": None,
                "thumbnail": "",
                "type": "contact"
            }
        }
    )
    with patch.object(Utility, "get_local_mongo_store") as mocked:
        mocked.side_effect = empty_store
        patch.dict(Utility.environment['action'], {"url": None})
        with patch.object(Agent, "handle_message") as mock_agent:
            mock_agent.side_effect = mock_agent_response
            mock_getbusiness.side_effect = __mock_getbusinessdata_workingenabled
            mock_validatebusiness.side_effect = __mock_validate_businessworkinghours
            response = client.post(
                f"/api/bot/{bot}/chat",
                json={"data": "!@#$%^&*()"},
                headers={"Authorization": token_type + " " + token},
                timeout=0,
            )
            responses.stop()
            actual = response.json()
            assert actual["data"]["agent_handoff"][
                       "businessworking"] == "We are unavailable at the moment. In case of any query related to Sales, gifting or enquiry of order, please connect over following whatsapp number +912929393 ."
