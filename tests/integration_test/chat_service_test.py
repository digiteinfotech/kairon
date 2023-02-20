import asyncio
import json
import os
from urllib.parse import urlencode, quote_plus

from mock import patch
from mongoengine import connect
from rasa.core.agent import Agent
from rasa.utils.endpoints import EndpointConfig
from slack.web.slack_response import SlackResponse
from tornado.test.testing_test import AsyncHTTPTestCase

from kairon.api.models import RegisterAccount
from kairon.chat.agent.agent import KaironAgent
from kairon.chat.handlers.channels.messenger import MessengerHandler
from kairon.chat.server import make_app
from kairon.chat.utils import ChatUtils
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.auth import Authentication
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.data.constant import TOKEN_TYPE, INTEGRATION_STATUS
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.live_agent.processor import LiveAgentsProcessor
from kairon.shared.metering.constants import MetricType
from kairon.shared.metering.metering_processor import MeteringProcessor
from kairon.shared.utils import Utility
from kairon.train import start_training
import responses
from kairon.shared.account.data_objects import UserActivityLog
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.auth import Authentication
from kairon.shared.data.utils import DataUtility
from kairon.shared.data.constant import ACCESS_ROLES, TOKEN_TYPE
from kairon.shared.chat.data_objects import Channels

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


class TestChatServer(AsyncHTTPTestCase):

    def get_app(self):
        return make_app()

    def empty_store(self, *args, **kwargs):
        return None

    def __mock_getbusinessdata_workingenabled(self,*args, **kwargs):
        business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
        output_json = business_workingdata.get("working_enabled_true")
        return output_json

    def __mock_getbusinessdata_workingdisabled(self,*args, **kwargs):
        business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
        output_json = business_workingdata.get("working_enabled_false")
        return output_json

    def __mock_validate_businessworkinghours(self,*args, **kwargs):
        return False

    def __mock_validate_businessworkinghours_true(self,*args, **kwargs):
        return True

    def mock_agent_response(self, *args, **kwargs):
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

    def test_index(self):
        response = self.fetch("/")
        self.assertEqual(response.code, 200)
        self.assertEqual(response.body.decode("utf8"), 'Kairon Server Running')

    def test_chat(self):
        with patch.object(Utility, "get_local_mongo_store") as mocked:
            mocked.side_effect = self.empty_store
            patch.dict(Utility.environment['action'], {"url": None})
            response = self.fetch(
                f"/api/bot/{bot}/chat",
                method="POST",
                body=json.dumps({"data": "Hi"}).encode('utf-8'),
                headers={"Authorization": token_type + " " + token},
                connect_timeout=0,
                request_timeout=0
            )
            actual = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"]
            assert Utility.check_empty_string(actual["message"])
            headers = list(response.headers.get_all())
            assert headers[0] == ('Server', 'Secure')
            assert headers[1] == ('Content-Type', 'application/json')
            assert headers[3] == ('Access-Control-Allow-Origin', '*')
            assert headers[4] == ('Access-Control-Allow-Headers', '*')
            assert headers[5] == ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
            assert headers[6] == ('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload')
            assert headers[7] == ('Content-Security-Policy', "default-src 'self'; frame-ancestors 'self'; form-action 'self';")
            assert headers[8] == ('X-Content-Type-Options', 'no-sniff')
            assert headers[9] == ('Referrer-Policy', 'no-referrer')
            assert headers[10] == ('Permissions-Policy',
                                   'accelerometer=(self), ambient-light-sensor=(self), autoplay=(self), battery=(self), camera=(self), cross-origin-isolated=(self), display-capture=(self), document-domain=(self), encrypted-media=(self), execution-while-not-rendered=(self), execution-while-out-of-viewport=(self), fullscreen=(self), geolocation=(self), gyroscope=(self), keyboard-map=(self), magnetometer=(self), microphone=(self), midi=(self), navigation-override=(self), payment=(self), picture-in-picture=(self), publickey-credentials-get=(self), screen-wake-lock=(self), sync-xhr=(self), usb=(self), web-share=(self), xr-spatial-tracking=(self)')
            assert headers[11] == ('Cache-Control', 'no-store')
            data = MeteringProcessor.get_logs(user['account'], metric_type=MetricType.test_chat, bot=bot)
            assert len(data["logs"]) > 0
            assert len(data["logs"]) == data["total"]
            assert MeteringProcessor.get_metric_count(user['account'], metric_type=MetricType.test_chat, channel_type="chat_client") > 0

    def test_chat_with_user(self):
        access_token = chat_client_config['config']['headers']['authorization']['access_token']
        token_type = chat_client_config['config']['headers']['authorization']['token_type']
        with patch.object(Utility, "get_local_mongo_store") as mocked:
            mocked.side_effect = self.empty_store
            patch.dict(Utility.environment['action'], {"url": None})

            response = self.fetch(
                f"/api/bot/{bot}/chat",
                method="POST",
                body=json.dumps({"data": "Hi"}).encode("utf8"),
                headers={"Authorization": token_type + " " + token},
            )
            actual = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"]
            assert Utility.check_empty_string(actual["message"])

            response = self.fetch(
                f"/api/bot/{bot}/chat",
                method="POST",
                body=json.dumps({"data": "Hi"}).encode("utf8"),
                headers={"Authorization":  f"{token_type} {access_token}"},
            )
            actual = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"]
            assert Utility.check_empty_string(actual["message"])
            assert MeteringProcessor.get_metric_count(user['account'], metric_type=MetricType.test_chat,
                                                      channel_type="chat_client") >= 2

    def test_chat_fetch_from_cache(self):
        with patch.object(Utility, "get_local_mongo_store") as mocked:
            mocked.side_effect = self.empty_store
            patch.dict(Utility.environment['action'], {"url": None})

            response = self.fetch(
                f"/api/bot/{bot}/chat",
                method="POST",
                body=json.dumps({"data": "Hi"}).encode("utf8"),
                headers={"Authorization": token_type + " " + token},
            )
            actual = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"]
            assert Utility.check_empty_string(actual["message"])

    def test_chat_model_not_trained(self):
        response = self.fetch(
            f"/api/bot/{bot3}/chat",
            method="POST",
            body=json.dumps({"data": "Hi"}).encode("utf8"),
            headers={
                "Authorization": f"{token_type} {token}"
            },
        )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert actual["data"] is None
        assert actual["message"] == "Bot has not been trained yet!"

    def test_chat_with_different_bot_not_allowed(self):
        response = self.fetch(
            f"/api/bot/test/chat",
            method="POST",
            body=json.dumps({"data": "Hi"}).encode("utf8"),
            headers={
                "Authorization": token_type + " " + token
            },
        )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert actual["data"] is None
        assert actual["message"] == "Access to bot is denied"

    def test_chat_with_different_bot_using_token_for_different_bot(self):
        access_token, _ = Authentication.generate_integration_token(
            bot, "test@chat.com", name='integration_token_for_chat_service')
        response = self.fetch(
            f"/api/bot/{bot2}/chat",
            method="POST",
            body=json.dumps({"data": "Hi"}).encode("utf8"),
            headers={"Authorization": token_type + " " + access_token},
            connect_timeout=0,
            request_timeout=0
        )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert not actual["data"]
        assert actual["message"] == 'Access to bot is denied'

    def test_chat_with_bot_using_deleted_token(self):
        access_token, _ = Authentication.generate_integration_token(bot, "test@chat.com", name='integration_token_1')
        Authentication.update_integration_token('integration_token_1', bot,
                                                "test@chat.com", INTEGRATION_STATUS.DELETED.value)
        response = self.fetch(
            f"/api/bot/{bot}/chat",
            method="POST",
            body=json.dumps({"data": "Hi"}).encode("utf8"),
            headers={"Authorization": token_type + " " + access_token},
            connect_timeout=0,
            request_timeout=0
        )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert not actual["data"]
        assert actual["message"] == 'Access to bot is denied'

    def test_chat_different_bot(self):
        with patch.object(Utility, "get_local_mongo_store") as mocked:
            mocked.side_effect = self.empty_store
            patch.dict(Utility.environment['action'], {"url": None})
            response = self.fetch(
                f"/api/bot/{bot2}/chat",
                method="POST",
                body=json.dumps({"data": "Hi"}).encode("utf8"),
                headers={"Authorization": token_type + " " + token},
                connect_timeout=0,
                request_timeout=0
            )
            actual = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"]
            assert Utility.check_empty_string(actual["message"])

    def test_chat_with_limited_access(self):
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
            response = self.fetch(
                f"/api/bot/{bot2}/chat",
                method="POST",
                body=json.dumps({"data": "Hi"}).encode("utf8"),
                headers={
                    "Authorization": f"{token_type} {access_token}", 'X-USER': 'testUser'
                },
            )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        self.assertEqual(actual["data"]["response"], [{'recipient_id': 'testUser', 'text': 'Welcome to kairon'}])
        assert actual['data']['response']
        data = MeteringProcessor.get_logs(user['account'], metric_type=MetricType.prod_chat, bot=bot2)
        assert len(data["logs"]) > 0
        assert len(data["logs"]) == data["total"]
        assert MeteringProcessor.get_metric_count(user['account'], metric_type=MetricType.prod_chat,
                                                  channel_type="chat_client") > 0

        response = self.fetch(
            f"/api/bot/{bot2}/chat",
            method="POST",
            body=json.dumps({"data": "Hi"}).encode("utf8"),
            headers={
                "Authorization": f"{token_type} {access_token}"
            },
        )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert actual['message'] == 'Alias user missing for integration'

    def test_chat_with_limited_access_without_integration(self):
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
            response = self.fetch(
                f"/api/bot/{bot2}/chat",
                method="POST",
                body=json.dumps({"data": "Hi"}).encode("utf8"),
                headers={
                    "Authorization": f"{token_type} {access_token}", 'X-USER': 'testUser'
                },
            )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert actual["data"]["response"][0]

    def test_chat_limited_access_prevent_chat(self):
        access_token = Authentication.create_access_token(
            data={"sub": "test@chat.com", 'access-limit': ['/api/bot/.+/intent']},
            token_type=TOKEN_TYPE.INTEGRATION.value
        )
        response = self.fetch(
            f"/api/bot/{bot}/chat",
            method="POST",
            body=json.dumps({"data": "Hi"}).encode("utf8"),
            headers={
                "Authorization": f"{token_type} {access_token}", 'X-USER': "testUser"
            },
        )
        actual = json.loads(response.body.decode("utf8"))
        assert actual["message"] == "Access denied for this endpoint"

    def test_reload(self):
        response = self.fetch(
            f"/api/bot/{bot}/reload",
            method="GET",
            headers={
                "Authorization": token_type + " " + token
            },
        )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"] is None
        assert actual["message"] == "Reloading Model!"
        headers = list(response.headers.get_all())
        assert headers[0] == ('Server', 'Secure')
        assert headers[1] == ('Content-Type', 'application/json')
        assert headers[3] == ('Access-Control-Allow-Origin', '*')
        assert headers[4] == ('Access-Control-Allow-Headers', '*')
        assert headers[5] == ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        assert headers[6] == ('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload')
        assert headers[7] == ('Content-Security-Policy', "default-src 'self'; frame-ancestors 'self'; form-action 'self';")
        assert headers[8] == ('X-Content-Type-Options', 'no-sniff')
        assert headers[9] == ('Referrer-Policy', 'no-referrer')
        assert headers[10] == ('Permissions-Policy',
                               'accelerometer=(self), ambient-light-sensor=(self), autoplay=(self), battery=(self), camera=(self), cross-origin-isolated=(self), display-capture=(self), document-domain=(self), encrypted-media=(self), execution-while-not-rendered=(self), execution-while-out-of-viewport=(self), fullscreen=(self), geolocation=(self), gyroscope=(self), keyboard-map=(self), magnetometer=(self), microphone=(self), midi=(self), navigation-override=(self), payment=(self), picture-in-picture=(self), publickey-credentials-get=(self), screen-wake-lock=(self), sync-xhr=(self), usb=(self), web-share=(self), xr-spatial-tracking=(self)')
        assert headers[11] == ('Cache-Control', 'no-store')

    def test_reload_exception(self):
        response = self.fetch(
            f"/api/bot/{bot}/reload",
            method="GET"
        )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert actual["data"] is None
        assert actual["message"] == "Could not validate credentials"

    @patch('kairon.chat.handlers.channels.slack.SlackHandler.is_request_from_slack_authentic')
    @patch('kairon.shared.utils.Utility.get_local_mongo_store')
    def test_slack_auth_bot_challenge(self, mock_store, mock_slack):
        mock_store.return_value = self.empty_store
        mock_slack.return_value = True
        headers = {'User-Agent': 'Slackbot 1.0 (+https://api.slack.com/robots)',
                   'Content-Length': 826,
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
        response = self.fetch(
            f"/api/bot/slack/{bot}/{token}",
            method="POST",
            headers=headers,
            body=json.dumps({"token": "RrNd3SaNJNaP28TTauAYCmJw",
                             "challenge": "sjYDB2ccaT5wpcGyawz6BTDbiujZCBiVwSQR87t3Q3yqgoHFkkTy",
                             "type": "url_verification"},
                            )
        )
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 200)
        assert actual == "sjYDB2ccaT5wpcGyawz6BTDbiujZCBiVwSQR87t3Q3yqgoHFkkTy"

    @patch('slack.web.client.WebClient.team_info')
    @patch('slack.web.client.WebClient.oauth_v2_access')
    def test_slack_install_app_using_oauth(self, mock_slack_oauth, mock_slack_team_info):
        mock_slack_team_info.return_value = SlackResponse(
            client=self,
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
            client=self,
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
        response = self.fetch(
            f"/api/bot/slack/{bot}/{token}?{encoded_url_}",
            method="GET",
        )
        print(response)
        assert 'https://app.slack.com/client/T03BNQE7HLZ' == response.effective_url
        self.assertEqual(response.code, 200)

    def test_slack_invalid_auth(self):
        headers = {'User-Agent': 'Slackbot 1.0 (+https://api.slack.com/robots)',
                   'Content-Length': 826,
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
        response = self.fetch(
            f"/api/bot/slack/{bot}/123",
            method="POST",
            headers=headers,
            body=json.dumps({"token": "RrNd3SaNJNaP28TTauAYCmJw", "team_id": "TPKTMACSU", "api_app_id": "APKTXRPMK",
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
                             "event_context": "4-eyJldCI6Im1lc3NhZ2UiLCJ0aWQiOiJUUEtUTUFDU1UiLCJhaWQiOiJBUEtUWFJQTUsiLCJjaWQiOiJEUEtUWTgxVU0ifQ"})
        )
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 422)
        assert actual == '{"data": null, "success": false, "error_code": 401, "message": "Could not validate credentials"}'

    @patch('kairon.chat.handlers.channels.telegram.TelegramOutput')
    @patch('kairon.shared.utils.Utility.get_local_mongo_store')
    def test_telegram_auth_failed_telegram_verify(self, mock_store, mock_telegram_out):
        mock_store.return_value = self.empty_store
        mock_telegram_out.get_me.return_value = "test"
        patch.dict(Utility.environment['action'], {"url": None})
        response = self.fetch(
            f"/api/bot/telegram/{bot}/{token}",
            method="POST",
            body=json.dumps({"update_id": 483117514, "message": {"message_id": 14,
                                                                 "from": {"id": 1422280657, "is_bot": False,
                                                                          "first_name": "Fahad Ali",
                                                                          "language_code": "en"},
                                                                 "chat": {"id": 1422280657, "first_name": "Fahad Ali",
                                                                          "type": "private"}, "date": 1645433258,
                                                                 "text": "hi"}})
        )
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 200)
        assert actual == "failed"

    def test_hangout_invalid_auth(self):
        patch.dict(Utility.environment['action'], {"url": None})
        response = self.fetch(
            f"/api/bot/hangouts/{bot}/123",
            method="POST",
            body=json.dumps({
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
            }))
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 422)
        assert actual == '{"data": null, "success": false, "error_code": 401, "message": "Could not validate credentials"}'

    @patch('kairon.shared.utils.Utility.get_local_mongo_store')
    def test_hangout_auth_failed_hangout_verify(self, mock_store):
        mock_store.return_value = self.empty_store
        patch.dict(Utility.environment['action'], {"url": None})
        response = self.fetch(
            f"/api/bot/hangouts/{bot}/{token}",
            method="POST",
            headers={"Authorization": "Bearer Test"},
            body=json.dumps({
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
            }))
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 422)

    def test_messenger_invalid_auth(self):
        patch.dict(Utility.environment['action'], {"url": None})
        response = self.fetch(
            f"/api/bot/messenger/{bot}/123",
            headers={"X-Hub-Signature": "invalid"},
            method="POST",
            body=json.dumps({
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
            }))
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 422)
        assert actual == '{"data": null, "success": false, "error_code": 401, "message": "Could not validate credentials"}'

    def test_instagram_invalid_auth(self):
        patch.dict(Utility.environment['action'], {"url": None})
        response = self.fetch(
            f"/api/bot/instagram/{bot}/123",
            headers={"X-Hub-Signature": "invalid"},
            method="POST",
            body=json.dumps({
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
            }))
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 422)
        assert actual == '{"data": null, "success": false, "error_code": 401, "message": "Could not validate credentials"}'

    def test_whatsapp_invalid_token(self):
        response = self.fetch(
            f"/api/bot/whatsapp/{bot}/123",
            headers={"hub.verify_token": "invalid", "hub.challenge": "return test"},
            method="GET")
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 422)
        assert actual == '{"data": null, "success": false, "error_code": 401, "message": "Could not validate credentials"}'

    def test_whatsapp_channel_not_configured(self):
        access_token, _ = Authentication.generate_integration_token(
            bot2, "test@chat.com", expiry=5, access_limit=['/api/bot/.+/chat'], name="whatsapp integration"
        )

        response = self.fetch(
            f"/api/bot/whatsapp/{bot2}/{access_token}",
            headers={"hub.verify_token": "valid"},
            method="POST",
            body=json.dumps({
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
            }))
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 422)
        assert actual == '{"data": null, "success": false, "error_code": 401, "message": "Access denied for this endpoint"}'

    def test_whatsapp_invalid_hub_signature(self):
        def _mock_validate_hub_signature(*args, **kwargs):
            return False

        with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
            response = self.fetch(
                f"/api/bot/whatsapp/{bot}/{token}",
                headers={"hub.verify_token": "valid"},
                method="POST",
                body=json.dumps({
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
                }))
        actual = response.body.decode("utf8")
        assert actual == 'not validated'

    @responses.activate
    def test_whatsapp_valid_text_message_request(self):
        def _mock_validate_hub_signature(*args, **kwargs):
            return True

        responses.add(
            "POST", "https://graph.facebook.com/v13.0/12345678/messages", json={}
        )
        with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
            response = self.fetch(
                f"/api/bot/whatsapp/{bot}/{token}",
                headers={"hub.verify_token": "valid"},
                method="POST",
                body=json.dumps({
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
                }))
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 200)
        assert actual == 'success'
        assert MeteringProcessor.get_metric_count(user['account'], metric_type=MetricType.prod_chat,
                                                  channel_type="whatsapp") > 0

    @responses.activate
    def test_whatsapp_valid_button_message_request(self):
        def _mock_validate_hub_signature(*args, **kwargs):
            return True

        responses.add(
            "POST", "https://graph.facebook.com/v13.0/12345678/messages", json={}
        )

        with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
            response = self.fetch(
                f"/api/bot/whatsapp/{bot}/{token}",
                headers={"hub.verify_token": "valid"},
                method="POST",
                body=json.dumps({
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
                }))
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 200)
        assert actual == 'success'

    @responses.activate
    def test_whatsapp_valid_attachment_message_request(self):
        def _mock_validate_hub_signature(*args, **kwargs):
            return True

        responses.add(
            "POST", "https://graph.facebook.com/v13.0/12345678/messages", json={}
        )
        responses.add(
            "POST", "https://graph.facebook.com/v13.0/sdfghj567", json={}
        )

        with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
            response = self.fetch(
                f"/api/bot/whatsapp/{bot}/{token}",
                headers={"hub.verify_token": "valid"},
                method="POST",
                body=json.dumps({
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
                                        "id": "sdfghj567"
                                    },
                                    "type": "doument"
                                }]
                            },
                            "field": "messages"
                        }]
                    }]
                }))
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 200)
        assert actual == 'success'

    @responses.activate
    def test_whatsapp_valid_unsupported_message_request(self):
        def _mock_validate_hub_signature(*args, **kwargs):
            return True

        responses.add(
            "POST", "https://graph.facebook.com/v13.0/12345678/messages", json={}
        )

        with patch.object(MessengerHandler, "validate_hub_signature", _mock_validate_hub_signature):
            response = self.fetch(
                f"/api/bot/whatsapp/{bot}/{token}",
                headers={"hub.verify_token": "valid"},
                method="POST",
                body=json.dumps({
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
                }))
        actual = response.body.decode("utf8")
        self.assertEqual(response.code, 200)
        assert actual == 'success'

    @staticmethod
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

    @patch("kairon.live_agent.chatwoot.ChatwootLiveAgent.getBusinesshours")
    @patch("kairon.live_agent.chatwoot.ChatwootLiveAgent.validate_businessworkinghours")
    def test_chat_with_chatwoot_agent_fallback(self, mock_validatebusinesshours, mock_getbusinesshrs):
        self.add_live_agent_config(bot, user["email"])
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
            mocked.side_effect = self.empty_store
            patch.dict(Utility.environment['action'], {"url": None})
            with patch.object(Agent, "handle_message") as mock_agent:
                mock_agent.side_effect = self.mock_agent_response
                mock_getbusinesshrs.side_effect = self.__mock_getbusinessdata_workingenabled
                mock_validatebusinesshours.side_effect = self.__mock_validate_businessworkinghours_true
                response = self.fetch(
                    f"/api/bot/{bot}/chat",
                    method="POST",
                    body=json.dumps({"data": "!@#$%^&*()"}).encode('utf-8'),
                    headers={"Authorization": token_type + " " + token},
                    connect_timeout=0,
                    request_timeout=0
                )
                responses.stop()
                actual = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
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
                                                               'inbox_id':14036
                                                           }}

                data = MeteringProcessor.get_logs(user["account"], bot=bot, metric_type="agent_handoff")
                assert len(data["logs"]) > 0
                assert len(data["logs"]) == data["total"]
                assert MeteringProcessor.get_metric_count(user['account'], metric_type=MetricType.agent_handoff) > 0

    @patch("kairon.live_agent.chatwoot.ChatwootLiveAgent.getBusinesshours")
    def test_chat_with_chatwoot_agent_fallback_existing_contact(self, mock_businesshours):
        with patch.object(Utility, "get_local_mongo_store") as mocked:
            mocked.side_effect = self.empty_store
            patch.dict(Utility.environment['action'], {"url": None})
            with patch.object(KaironAgent, "handle_message") as mock_agent:
                mock_agent.side_effect = self.mock_agent_response
                mock_businesshours.side_effect = self.__mock_getbusinessdata_workingdisabled
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

                response = self.fetch(
                    f"/api/bot/{bot}/chat",
                    method="POST",
                    body=json.dumps({"data": "@#$%^&*()_"}).encode('utf-8'),
                    headers={"Authorization": token_type + " " + token},
                    connect_timeout=0,
                    request_timeout=0
                )
                responses.stop()
                actual = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
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

    def test_chat_with_live_agent(self):
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
        response = self.fetch(
            f"/api/bot/{bot}/agent/live/2",
            method="POST",
            body=json.dumps({"data": "hello, please resolve my ticket"}).encode('utf-8'),
            headers={"Authorization": token_type + " " + token},
            connect_timeout=0,
            request_timeout=0
        )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"]
        assert Utility.check_empty_string(actual["message"])
        responses.stop()

    def test_chat_with_live_agent_failed_to_send_message(self):
        responses.reset()
        responses.start()
        responses.add(
            "POST",
            'https://app.chatwoot.com/api/v1/accounts/12/conversations/2/messages',
            status=503,
            body="Temporarily unable to handle a request"
        )
        response = self.fetch(
            f"/api/bot/{bot}/agent/live/2",
            method="POST",
            body=json.dumps({"data": "need help"}).encode('utf-8'),
            headers={"Authorization": token_type + " " + token},
            connect_timeout=0,
            request_timeout=0
        )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert actual["data"] is None
        assert actual["message"] == "Failed to send message: Service Unavailable"
        responses.stop()

    def test_chat_with_live_agent_with_integration_token(self):
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
        response = self.fetch(
            f"/api/bot/{bot}/agent/live/2",
            method="POST",
            body=json.dumps({"data": "need help"}).encode('utf-8'),
            headers={"Authorization": f"{token_type} {access_token}", "X-USER": "test@chat.com"},
            connect_timeout=0,
            request_timeout=0
        )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert actual["success"]
        assert actual["error_code"] == 0
        assert actual["data"]
        assert Utility.check_empty_string(actual["message"])
        responses.stop()

    def test_chat_with_chatwoot_agent_fallback_failed_to_initiate(self):
        with patch.object(Utility, "get_local_mongo_store") as mocked:
            mocked.side_effect = self.empty_store
            patch.dict(Utility.environment['action'], {"url": None})
            with patch.object(KaironAgent, "handle_message") as mock_agent:
                mock_agent.side_effect = self.mock_agent_response
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

                response = self.fetch(
                    f"/api/bot/{bot}/chat",
                    method="POST",
                    body=json.dumps({"data": "!@#$%^&*()"}).encode('utf-8'),
                    headers={"Authorization": token_type + " " + token},
                    connect_timeout=0,
                    request_timeout=0
                )
                actual = json.loads(response.body.decode("utf8"))
                self.assertEqual(response.code, 200)
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

    def test_chat_with_bot_after_reset_passwrd(self):
        user = AccountProcessor.get_complete_user_details("resetpaswrd@chat.com")
        bot = user['bots']['account_owned'][0]['_id']
        access_token = Authentication.create_access_token(
            data={"sub": "resetpaswrd@chat.com", 'access-limit': ['/api/bot/.+/chat']},
        )
        UserActivityLog(account=1, user="resetpaswrd@chat.com", type="reset_password", bot=bot).save()
        response = self.fetch(
            f"/api/bot/{bot}/chat",
            method="POST",
            body=json.dumps({"data": "Hi"}).encode("utf8"),
            headers={
                "Authorization": f"{token_type} {access_token}", 'X-USER': 'testUser'
            },
        )
        actual = json.loads(response.body.decode("utf8"))
        message = actual.get("message")
        error_code = actual.get("error_code")
        assert error_code == 401
        assert message == 'Session expired. Please login again.'

    def test_reload_after_reset_passwrd(self):
        user = AccountProcessor.get_complete_user_details("resetpaswrd@chat.com")
        bot = user['bots']['account_owned'][0]['_id']
        access_token, _, _, _ = Authentication.authenticate("resetpaswrd@chat.com", "resetPswrd@12")
        UserActivityLog(account=1, user="resetpaswrd@chat.com", type="reset_password", bot=bot).save()
        reload_response = self.fetch(
            f"/api/bot/{bot}/reload",
            method="GET",
            headers={
                "Authorization": token_type + " " + access_token
            },
        )
        reload_actual = json.loads(reload_response.body.decode("utf8"))
        message = reload_actual.get("message")
        error_code = reload_actual.get("error_code")
        assert error_code == 401
        assert message == 'Session expired. Please login again.'

    def test_live_agent_after_reset_passwrd(self):
        user = AccountProcessor.get_complete_user_details("resetpaswrd@chat.com")
        bot = user['bots']['account_owned'][0]['_id']
        access_token, _, _, _ = Authentication.authenticate("resetpaswrd@chat.com", "resetPswrd@12")
        UserActivityLog(account=1, user="resetpaswrd@chat.com", type="reset_password", bot=bot).save()
        live_response = self.fetch(
            f"/api/bot/{bot}/agent/live/2",
            method="POST",
            body=json.dumps({"data": "need help"}).encode('utf-8'),
            headers={"Authorization": token_type + " " + access_token},
            connect_timeout=0,
            request_timeout=0
        )
        live_actual = json.loads(live_response.body.decode("utf8"))
        message = live_actual.get("message")
        error_code = live_actual.get("error_code")
        assert error_code == 401
        assert message == 'Session expired. Please login again.'

    def test_get_chat_history(self):
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
            response = self.fetch(
                f"/api/bot/{bot}/conversation",
                method="GET",
                headers={"Authorization": token_type + " " + token},
                connect_timeout=0,
                request_timeout=0
            )
            actual = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"] == events
            assert actual["data"]
            assert actual["message"]

            response = self.fetch(
                f"/api/bot/{bot}/conversation",
                method="GET",
                headers={"Authorization":  f"{token_type} {access_token}"},
                connect_timeout=0,
                request_timeout=0
            )
            actual = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"] == events
            assert actual["data"]
            assert actual["message"]

    def test_get_chat_history_empty(self):
        events = []

        with patch.object(ChatUtils, "get_last_session_conversation") as mocked:
            mocked.return_value = events, "connected to db"
            response = self.fetch(
                f"/api/bot/{bot}/conversation",
                method="GET",
                headers={"Authorization": token_type + " " + token},
            )
            actual = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"] == events
            assert actual["message"]

    def test_get_chat_history_user_exception(self):
        def _raise_err(*args, **kwargs):
            raise Exception("Mongo object out of memory")

        with patch.object(ChatUtils, "get_last_session_conversation") as mocked:
            mocked.side_effect = _raise_err
            response = self.fetch(
                f"/api/bot/{bot3}/conversation",
                method="GET",
                headers={
                    "Authorization": f"{token_type} {token}"
                },
            )
        actual = json.loads(response.body.decode("utf8"))
        self.assertEqual(response.code, 200)
        assert not actual["success"]
        assert actual["error_code"] == 422
        assert actual["data"] is None
        assert actual["message"] == 'Mongo object out of memory'

    def test_get_chat_history_http_error(self):
        user = AccountProcessor.get_complete_user_details("resetpaswrd@chat.com")
        bot = user['bots']['account_owned'][0]['_id']
        access_token, _, _, _ = Authentication.authenticate("resetpaswrd@chat.com", "resetPswrd@12")
        UserActivityLog(account=1, user="resetpaswrd@chat.com", type="reset_password", bot=bot).save()
        reload_response = self.fetch(
            f"/api/bot/{bot}/conversation",
            method="GET",
            headers={
                "Authorization": token_type + " " + access_token
            },
        )
        reload_actual = json.loads(reload_response.body.decode("utf8"))
        message = reload_actual.get("message")
        error_code = reload_actual.get("error_code")
        assert error_code == 401
        assert message == "Session expired. Please login again."

    def test_save_channel_config_msteams(self):
        channel_url = ChatDataProcessor.save_channel_config({
            "connector_type": "msteams", "config": {
                "app_id": "app123",
                "app_secret": "appsecret123"
            }}, bot, "test@chat.com")
        msteams = ChatDataProcessor.get_channel_endpoint("msteams", bot)
        hashcode = channel_url.split("/", -1)[-1]
        dbhashcode = msteams.split("/", -1)[-1]
        assert hashcode == dbhashcode

    def test_get_channel_end_point_msteams(self):
        channel_url = ChatDataProcessor.save_channel_config({
            "connector_type": "msteams", "config": {
                "app_id": "app123",
                "app_secret": "appsecret123"
            }}, bot, "test@chat.com")
        channel = Channels.objects(bot=bot, connector_type="msteams").get()
        response = DataUtility.get_channel_endpoint(channel)
        second_hashcode = response.split("/", -1)[-1]
        scnd_msteams = ChatDataProcessor.get_channel_config("msteams", bot, mask_characters=False)
        dbcode = scnd_msteams["meta_config"]["secrethash"]
        assert second_hashcode == dbcode

    def test_save_channel_meta_msteams(self):
        channel_url = ChatDataProcessor.save_channel_config({
            "connector_type": "msteams", "config": {
                "app_id": "app123",
                "app_secret": "appsecret123"
            }}, bot, "test@chat.com")
        token, _ = Authentication.generate_integration_token(
            bot, "test@chat.com", role=ACCESS_ROLES.CHAT.value,
            access_limit=[f"/api/bot/msteams/{bot}/.+"],
            token_type=TOKEN_TYPE.CHANNEL.value)
        channel = Channels.objects(bot=bot, connector_type="msteams").get()
        hashcode = DataUtility.save_channel_metadata(config=channel, token=token)
        channel_config = ChatDataProcessor.get_channel_config("msteams", bot, mask_characters=False)
        dbhashcode = channel_config["meta_config"]["secrethash"]
        assert hashcode == dbhashcode

    def test_get_channel_end_point_whatsapp(self):
        def _mock_generate_integration_token(*arge, **kwargs):
            return "testtoken", "ignore"

        with patch.object(Authentication, "generate_integration_token", _mock_generate_integration_token):
            channel_url = ChatDataProcessor.save_channel_config({
                "connector_type": "whatsapp", "config": {
                    "app_secret": "app123",
                    "access_token": "appsecret123", "verify_token": "integrate_1"
                }}, bot, "test@chat.com")
            channel = Channels.objects(bot=bot, connector_type="whatsapp").get()
            response = DataUtility.get_channel_endpoint(channel)
            last_urlpart = response.split("/", -1)[-1]
            assert last_urlpart == "testtoken"

    @patch("kairon.live_agent.chatwoot.ChatwootLiveAgent.getBusinesshours")
    @patch("kairon.live_agent.chatwoot.ChatwootLiveAgent.validate_businessworkinghours")
    def test_chat_with_chatwoot_agent_outof_workinghours(self, mock_validatebusiness, mock_getbusiness):
        self.add_live_agent_config(bot, user["email"])
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
            mocked.side_effect = self.empty_store
            patch.dict(Utility.environment['action'], {"url": None})
            with patch.object(Agent, "handle_message") as mock_agent:
                mock_agent.side_effect = self.mock_agent_response
                mock_getbusiness.side_effect = self.__mock_getbusinessdata_workingenabled
                mock_validatebusiness.side_effect = self.__mock_validate_businessworkinghours
                response = self.fetch(
                    f"/api/bot/{bot}/chat",
                    method="POST",
                    body=json.dumps({"data": "!@#$%^&*()"}).encode('utf-8'),
                    headers={"Authorization": token_type + " " + token},
                    connect_timeout=0,
                    request_timeout=0
                )
                responses.stop()
                actual = json.loads(response.body.decode("utf8"))
                assert actual["data"]["agent_handoff"]["businessworking"]=="We are unavailable at the moment. In case of any query related to Sales, gifting or enquiry of order, please connect over following whatsapp number +912929393 ."