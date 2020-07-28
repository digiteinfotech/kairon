import json

import pytest
from mongoengine import connect
from rasa.core.domain import Domain
from rasa.core.tracker_store import MongoTrackerStore, DialogueStateTracker

from bot_trainer.data_processor.history import ChatHistory
from bot_trainer.data_processor.processor import MongoProcessor
from bot_trainer.utils import Utility
import os
from mongomock import MongoClient

class TestHistory:
    @pytest.fixture(autouse=True)
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_evironment()
        connect(host=Utility.environment['database']["url"])

    def tracker_keys(self, *args, **kwargs):
        return [
            "5b029887-bed2-4bbb-aa25-bd12fda26244",
            "b868d6ee-f98f-4c1b-b284-ce034aaad01f",
            "b868d6ee-f98f-4c1b-b284-ce034aaad61f",
            "b868d6ee-f98f-4c1b-b284-ce4534aaad61f",
            "49931985-2b51-4db3-89d5-a50767e6d98e",
            "2e409e7c-06f8-4de8-8c88-93b4cf0b7211",
            "2fed7769-b647-4088-8ed9-a4f4f3653f25",
        ]

    def user_history(self, *args, **kwargs):
        json_data = json.load(open("tests/testing_data/history/conversation.json"))
        domain = Domain.from_file("tests/testing_data/initial/domain.yml")
        return (
            DialogueStateTracker.from_dict(
                "5e564fbcdcf0d5fad89e3acd", json_data["events"], domain.slots
            )
            .as_dialogue()
            .events,
            None
        )

    def history_conversations(self, *args, **kwargs):
        json_data = json.load(
            open("tests/testing_data/history/conversations_history.json")
        )
        return json_data, None

    @pytest.fixture
    def mock_tracker(self, monkeypatch):
        monkeypatch.setattr(MongoTrackerStore, "keys", self.tracker_keys)

    def get_tracker_and_domain_data(self, *args, **kwargs):
        domain = Domain.from_file("tests/testing_data/initial/domain.yml")
        return domain, MongoTrackerStore(domain, host="mongodb://192.168.100.140:27019"), None

    @pytest.fixture
    def mock_get_tracker_and_domain(self, monkeypatch):
        monkeypatch.setattr(
            ChatHistory, "get_tracker_and_domain", self.get_tracker_and_domain_data
        )

    @pytest.fixture
    def mock_chat_history_empty(self, monkeypatch):
        def fetch_user_history(*args, **kwargs):
            return [], None

        def get_conversations(*args, **kwargs):
            return [], None

        monkeypatch.setattr(ChatHistory, "fetch_user_history", fetch_user_history)
        monkeypatch.setattr(ChatHistory, "get_conversations", get_conversations)

    @pytest.fixture
    def mock_chat_history(self, monkeypatch):
        monkeypatch.setattr(ChatHistory, "fetch_user_history", self.user_history)
        monkeypatch.setattr(
            ChatHistory, "get_conversations", self.history_conversations
        )

    def endpoint_details(self, *args, **kwargs):
        return {"tracker_endpoint": {"url": "mongodb://localhost:27019", "db": "conversation"}}

    @pytest.fixture
    def mock_mongo_processor(self, monkeypatch):
        monkeypatch.setattr(MongoProcessor, "get_endpoints", self.endpoint_details)

    def test_fetch_chat_users_db_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            users = ChatHistory.fetch_chat_users(bot="tests")
            assert len(users) == 0


    def test_fetch_chat_users_error(self, mock_get_tracker_and_domain):
        with pytest.raises(Exception):
            users, message = ChatHistory.fetch_chat_users(bot="tests")
            assert len(users) == 0
            assert message is None

    def test_fetch_chat_history_error(self, mock_get_tracker_and_domain):
        with pytest.raises(Exception):
            history, message = ChatHistory.fetch_chat_history(sender="123", bot="tests")
            assert len(history) == 0
            assert message is None

    def test_fetch_chat_history_empty(self, mock_chat_history_empty):
        history, message = ChatHistory.fetch_chat_history(sender="123", bot="tests")
        assert len(history) == 0
        assert message is None

    def test_fetch_chat_history(self, mock_chat_history):
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

    def test_visitor_hit_fallback(self, monkeypatch):
        def client(*args, **kwargs):
            return MongoClient(), "conversation"

        monkeypatch.setattr(ChatHistory, "get_mongo_connection", client)
        hit_fall_back, message = ChatHistory.visitor_hit_fallback("tests")
        assert hit_fall_back["fallback_count"] == 0
        assert hit_fall_back["total_count"] == 0
        assert message is None

    def test_conversation_time_error(self, mock_get_tracker_and_domain):
        with pytest.raises(Exception):
            conversation_time, message = ChatHistory.conversation_time("tests")
            assert not conversation_time
            assert message is None

    def test_conversation_time_empty(self, mock_chat_history_empty):
        conversation_time, message = ChatHistory.conversation_time("tests")
        assert not conversation_time
        assert message is None

    def test_conversation_time(self, mock_chat_history):
        conversation_time, message = ChatHistory.conversation_time("tests")
        assert conversation_time
        assert message is None

    def test_conversation_steps_error(self, mock_get_tracker_and_domain):
        with pytest.raises(Exception):
            conversation_steps, message = ChatHistory.conversation_steps("tests")
            assert not conversation_steps
            assert message is None

    def test_conversation_steps_empty(self, mock_chat_history_empty):
        conversation_steps, message = ChatHistory.conversation_steps("tests")
        assert not conversation_steps
        assert message is None

    def test_conversation_steps(self, mock_chat_history):
        conversation_steps, message = ChatHistory.conversation_steps("tests")
        assert conversation_steps
        assert message is None

    def test_user_with_metrics(self, monkeypatch):
        def client(*args, **kwargs):
            return MongoClient(), "conversation"
        monkeypatch.setattr(ChatHistory, "get_mongo_connection", client)
        users = ChatHistory.user_with_metrics("tests")
        assert users == []
