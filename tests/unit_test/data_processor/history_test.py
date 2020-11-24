import json
import os

import pytest
from mongoengine import connect
from mongomock import MongoClient
from rasa.core.tracker_store import MongoTrackerStore
from rasa.shared.core.domain import Domain

from kairon.data_processor.history import ChatHistory
from kairon.data_processor.processor import MongoProcessor
from kairon.utils import Utility


class TestHistory:
    @pytest.fixture(autouse=True)
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment['database']["url"])

    def history_conversations(self, *args, **kwargs):
        json_data = json.load(
            open("tests/testing_data/history/conversations_history.json")
        )
        return json_data[0]['events'], None

    def get_tracker_and_domain_data(self, *args, **kwargs):
        domain = Domain.from_file("tests/testing_data/initial/domain.yml")
        return domain, MongoTrackerStore(domain, host="mongodb://192.168.100.140:27019"), None

    @pytest.fixture
    def mock_get_tracker_and_domain(self, monkeypatch):
        monkeypatch.setattr(
            ChatHistory, "get_tracker_and_domain", self.get_tracker_and_domain_data
        )

    @pytest.fixture
    def mock_mongo_client(self, monkeypatch):
        def db_client(*args, **kwargs):
            client = MongoClient()
            db = client.get_database("conversation")
            conversations = db.get_collection("conversations")
            history, _ = self.history_conversations()
            conversations.insert_many(history)
            return client, "conversation", "conversations", None

        monkeypatch.setattr(ChatHistory, "get_mongo_connection", db_client)

    @pytest.fixture
    def mock_mongo_client_empty(self, monkeypatch):
        def client(*args, **kwargs):
            client = MongoClient()
            return client, "conversation", "conversations", None

        monkeypatch.setattr(ChatHistory, "get_mongo_connection", client)

    def endpoint_details(self, *args, **kwargs):
        return {"tracker_endpoint": {"url": "mongodb://localhost:27019", "db": "conversation"}}

    @pytest.fixture
    def mock_mongo_processor(self, monkeypatch):
        monkeypatch.setattr(MongoProcessor, "get_endpoints", self.endpoint_details)

    def test_fetch_chat_users_db_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            users = ChatHistory.fetch_chat_users(bot="tests")
            assert len(users) == 0

    def test_fetch_chat_users(self, mock_mongo_client):
        users = ChatHistory.fetch_chat_users(bot="tests")
        assert len(users) == 2

    def test_fetch_chat_users_empty(self, mock_mongo_client_empty):
        users = ChatHistory.fetch_chat_users(bot="tests")
        assert len(users) == 2

    def test_fetch_chat_users_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            users, message = ChatHistory.fetch_chat_users(bot="tests")
            assert len(users) == 0
            assert message is None

    def test_fetch_chat_history_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            history, message = ChatHistory.fetch_chat_history(sender="123", bot="tests")
            assert len(history) == 0
            assert message is None

    def test_fetch_chat_history_empty(self, mock_mongo_client_empty):
        history, message = ChatHistory.fetch_chat_history(sender="123", bot="tests")
        assert len(history) == 0
        assert message is None

    def test_fetch_chat_history(self, monkeypatch):
        def events(*args, **kwargs):
            json_data = json.load(open("tests/testing_data/history/conversation.json"))
            return json_data['events'], None
        monkeypatch.setattr(ChatHistory, "fetch_user_history", events)

        history, message = ChatHistory.fetch_chat_history(
            sender="5e564fbcdcf0d5fad89e3acd", bot="tests"
        )
        assert len(history) == 12
        assert history[0]["event"]
        assert history[0]["time"]
        assert history[0]["date"]
        assert history[0]["text"]
        assert history[0]["is_exists"] == False or history[0]["is_exists"]
        assert history[0]["intent"]
        assert history[0]["confidence"]
        assert message is None

    def test_visitor_hit_fallback_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            hit_fall_back, message = ChatHistory.visitor_hit_fallback("tests")
            assert hit_fall_back["fallback_count"] == 0
            assert hit_fall_back["total_count"] == 0
            assert message is None

    def test_visitor_hit_fallback(self, mock_mongo_client):
        hit_fall_back, message = ChatHistory.visitor_hit_fallback("tests")
        assert hit_fall_back["fallback_count"] == 0
        assert hit_fall_back["total_count"] == 0
        assert message is None

    def test_conversation_time_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            conversation_time, message = ChatHistory.conversation_time("tests")
            assert not conversation_time
            assert message is None

    def test_conversation_time_empty(self, mock_mongo_client_empty):
        conversation_time, message = ChatHistory.conversation_time("tests")
        assert not conversation_time
        assert message is None

    def test_conversation_time(self, mock_mongo_client):
        conversation_time, message = ChatHistory.conversation_time("tests")
        assert conversation_time == []
        assert message is None

    def test_conversation_steps_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            conversation_steps, message = ChatHistory.conversation_steps("tests")
            assert not conversation_steps
            assert message is None

    def test_conversation_steps_empty(self, mock_mongo_client_empty):
        conversation_steps, message = ChatHistory.conversation_steps("tests")
        assert not conversation_steps
        assert message is None

    def test_conversation_steps(self, mock_mongo_client):
        conversation_steps, message = ChatHistory.conversation_steps("tests")
        assert conversation_steps == []
        assert message is None

    def test_user_with_metrics(self, mock_mongo_client):
        users, message = ChatHistory.user_with_metrics("tests")
        assert users == []
        assert message is None
