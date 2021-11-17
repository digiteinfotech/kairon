import asyncio
import json
import os

from mock import patch
from mongoengine import connect
from tornado.test.testing_test import AsyncHTTPTestCase

from kairon.api.models import RegisterAccount
from kairon.chat.server import make_app
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.auth import Authentication
from kairon.shared.data.processor import MongoProcessor
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
                                                                          "account": "ChatTesting"}).dict(),
                                                       "sysadmin"))

token = Authentication.authenticate("test@chat.com", "testChat@12")
token_type = "Bearer"
user = AccountProcessor.get_complete_user_details("test@chat.com")
bot = user['bot'][0]
start_training(bot, "test@chat.com")
bot2 = AccountProcessor.add_bot("testChat2", user['account'], "test@chat.com")['_id'].__str__()
loop.run_until_complete(MongoProcessor().save_from_path(
    "template/use-cases/Hi-Hello", bot2, user="test@chat.com"
))
start_training(bot2, "test@chat.com")


class TestChatServer(AsyncHTTPTestCase):

    def setUp(self) -> None:
        super(TestChatServer, self).setUp()

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
            )
            actual = json.loads(response.body.decode("utf8"))
            self.assertEqual(response.code, 200)
            assert actual["success"]
            assert actual["error_code"] == 0
            assert actual["data"]
            assert Utility.check_empty_string(actual["message"])

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
            f"/api/bot/test/chat",
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

    def test_chat_with_different_bot_not_trained(self):
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
        assert actual["message"] == "Bot has not been trained yet!"

    def test_chat_different_bot(self):
        with patch.object(Utility, "get_local_mongo_store") as mocked:
            mocked.side_effect = self.empty_store
            patch.dict(Utility.environment['action'], {"url": None})
            response = self.fetch(
                f"/api/bot/{bot2}/chat",
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

    def test_chat_with_limited_access(self):
        access_token = Authentication.create_access_token(
            data={"sub": "test@chat.com", 'access-limit': ['/api/bot/.+/chat']},
            is_integration=True
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

    def test_chat_with_limited_access_without_integration(self):
        access_token = Authentication.create_access_token(
            data={"sub": "test@chat.com", 'access-limit': ['/api/bot/.+/chat']},
            is_integration=False
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
            is_integration=True
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
