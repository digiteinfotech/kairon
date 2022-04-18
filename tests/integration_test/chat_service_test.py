import asyncio
import json
import os
from urllib.parse import urlencode, quote_plus

from mock import patch
from mongoengine import connect
from tornado.test.testing_test import AsyncHTTPTestCase

from kairon.api.models import RegisterAccount
from kairon.chat.server import make_app
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.auth import Authentication
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.data.constant import TOKEN_TYPE, INTEGRATION_STATUS
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility
from kairon.train import start_training
import responses

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

token = Authentication.authenticate("test@chat.com", "testChat@12")
token_type = "Bearer"
user = AccountProcessor.get_complete_user_details("test@chat.com")
bot = user['bots']['account_owned'][0]['_id']
start_training(bot, "test@chat.com")
bot2 = AccountProcessor.add_bot("testChat2", user['account'], "test@chat.com")['_id'].__str__()
loop.run_until_complete(MongoProcessor().save_from_path(
    "template/use-cases/Hi-Hello", bot2, user="test@chat.com"
))
start_training(bot2, "test@chat.com")
bot3 = AccountProcessor.add_bot("testChat3", user['account'], "test@chat.com")['_id'].__str__()
ChatDataProcessor.save_channel_config({"connector_type": "slack",
                                       "config": {
                                           "bot_user_oAuth_token": "xoxb-801939352912-801478018484-v3zq6MYNu62oSs8vammWOY8K",
                                           "slack_signing_secret": "79f036b9894eef17c064213b90d1042b"}},
                                      bot, user="test@chat.com")
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
                                           "verity_token": "kairon-messenger-token",
                                       }
                                       },
                                      bot, user="test@chat.com")
responses.stop()


class TestChatServer(AsyncHTTPTestCase):

    def get_app(self):
        return make_app()

    def empty_store(self, *args, **kwargs):
        return None

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
            assert headers[4] == ('Access-Control-Allow-Headers', 'x-requested-with')
            assert headers[5] == ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
            assert headers[6] == ('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload')
            assert headers[7] == ('Content-Security-Policy', "default-src 'self'; frame-ancestors 'self'; form-action 'self';")
            assert headers[8] == ('X-Content-Type-Options', 'no-sniff')
            assert headers[9] == ('Referrer-Policy', 'origin')
            assert headers[10] == ('Permissions-Policy',
                                   'accelerometer=(self), ambient-light-sensor=(self), autoplay=(self), battery=(self), camera=(self), cross-origin-isolated=(self), display-capture=(self), document-domain=(self), encrypted-media=(self), execution-while-not-rendered=(self), execution-while-out-of-viewport=(self), fullscreen=(self), geolocation=(self), gyroscope=(self), keyboard-map=(self), magnetometer=(self), microphone=(self), midi=(self), navigation-override=(self), payment=(self), picture-in-picture=(self), publickey-credentials-get=(self), screen-wake-lock=(self), sync-xhr=(self), usb=(self), web-share=(self), xr-spatial-tracking=(self)')
            assert headers[11] == ('Cache-Control', 'no-store')

    def test_chat_with_user(self):
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
        access_token = Authentication.generate_integration_token(
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
        access_token = Authentication.generate_integration_token(bot, "test@chat.com", name='integration_token_1')
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
        access_token = Authentication.generate_integration_token(
            bot2, "test@chat.com", expiry=5, access_limit=['/api/bot/.+/chat'], name="integration token"
        )
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
        assert actual['data']['response']

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
        access_token = Authentication.create_access_token(
            data={"sub": "test@chat.com", 'access-limit': ['/api/bot/.+/chat']},
        )
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
        assert actual['data']['response']

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
        assert headers[4] == ('Access-Control-Allow-Headers', 'x-requested-with')
        assert headers[5] == ('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        assert headers[6] == ('Strict-Transport-Security', 'max-age=31536000; includeSubDomains; preload')
        assert headers[7] == ('Content-Security-Policy', "default-src 'self'; frame-ancestors 'self'; form-action 'self';")
        assert headers[8] == ('X-Content-Type-Options', 'no-sniff')
        assert headers[9] == ('Referrer-Policy', 'origin')
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