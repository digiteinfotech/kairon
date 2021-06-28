import json
import os
from datetime import datetime

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

    def get_history_conversations(self):
        json_data = json.load(
            open("tests/testing_data/history/conversations_history.json")
        )
        for event in json_data[0]['events'][15:]:
            event['timestamp'] = float(datetime.utcnow().strftime("%s"))
        return json_data[0], None

    def get_tracker_and_domain_data(self, *args, **kwargs):
        domain = Domain.from_file("tests/testing_data/initial/domain.yml")
        return domain, MongoTrackerStore(domain, host="mongodb://192.168.100.140:27169"), None

    @pytest.fixture
    def mock_get_tracker_and_domain(self, monkeypatch):
        monkeypatch.setattr(
            ChatHistory, "get_tracker_and_domain", self.get_tracker_and_domain_data
        )

    @pytest.fixture
    def mock_fallback_user_data(self, monkeypatch):
        def db_client(*args, **kwargs):
            client = MongoClient()
            db = client.get_database("conversation")
            conversations = db.get_collection("conversations")
            history, _ = self.get_history_conversations()
            conversations.insert(history)
            return client, "conversation", "conversations", None

        monkeypatch.setattr(ChatHistory, "get_mongo_connection", db_client)

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
        return {"tracker_endpoint": {"url": "mongodb://localhost:27169", "db": "conversation"}}

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

    def test_visitor_hit_fallback(self, mock_fallback_user_data, monkeypatch):
        def _mock_load_config(*args, **kwargs):
            return {"policies": [{"name": "RulePolicy", 'core_fallback_action_name': 'action_default_fallback'}]}
        monkeypatch.setattr(MongoProcessor, 'load_config', _mock_load_config)
        hit_fall_back, message = ChatHistory.visitor_hit_fallback("5b029887-bed2-4bbb-aa25-bd12fda26244")
        assert hit_fall_back["fallback_count"] == 1
        assert hit_fall_back["total_count"] == 4
        assert message is None

    def test_visitor_hit_fallback_action_not_configured(self, mock_fallback_user_data, monkeypatch):
        def _mock_load_config(*args, **kwargs):
            return {"policies": [{"name": "RulePolicy"}]}
        monkeypatch.setattr(MongoProcessor, 'load_config', _mock_load_config)
        hit_fall_back, message = ChatHistory.visitor_hit_fallback("5b029887-bed2-4bbb-aa25-bd12fda26244")
        assert hit_fall_back["fallback_count"] == 1
        assert hit_fall_back["total_count"] == 4
        assert message is None

    def test_visitor_hit_fallback_custom_action(self, mock_fallback_user_data, monkeypatch):
        def _mock_load_config(*args, **kwargs):
            return {"policies": [{"name": "RulePolicy", 'core_fallback_action_name': 'utter_location_query'}]}
        monkeypatch.setattr(MongoProcessor, 'load_config', _mock_load_config)
        hit_fall_back, message = ChatHistory.visitor_hit_fallback("5b029887-bed2-4bbb-aa25-bd12fda26244")
        assert hit_fall_back["fallback_count"] == 1
        assert hit_fall_back["total_count"] == 4
        assert message is None

    def test_visitor_hit_fallback_nlu_fallback_configured(self, mock_fallback_user_data):
        steps = [
            {"name": "nlu_fallback", "type": "INTENT"},
            {"name": "utter_please_rephrase", "type": "BOT"}
        ]
        rule = {'name': 'fallback_rule', 'steps': steps, 'type': 'RULE'}
        MongoProcessor().add_complex_story(rule, "5b029887-bed2-4bbb-aa25-bd12fda26244", 'test')
        hit_fall_back, message = ChatHistory.visitor_hit_fallback("5b029887-bed2-4bbb-aa25-bd12fda26244")
        assert hit_fall_back["fallback_count"] == 2
        assert hit_fall_back["total_count"] == 4
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

    def test_engaged_users_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            engaged_user, message = ChatHistory.engaged_users("tests")
            assert not engaged_user
            assert message is None

    def test_engaged_users(self, mock_mongo_client):
        engaged_user, message = ChatHistory.engaged_users("tests")
        assert engaged_user['engaged_users'] == 0
        assert message is None

    def test_new_user_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            count_user, message = ChatHistory.new_users("tests")
            assert not count_user
            assert message is None

    def test_new_user(self, mock_mongo_client):
        count_user, message = ChatHistory.new_users("tests")
        assert count_user['new_users'] == 0
        assert message is None

    def test_successful_conversation_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            conversation_steps, message = ChatHistory.successful_conversations("tests")
            assert not conversation_steps
            assert message is None

    def test_successful_conversation(self, mock_mongo_client):
        conversation_steps, message = ChatHistory.successful_conversations("tests")
        assert conversation_steps['successful_conversations'] == 0
        assert message is None

    def test_user_retention_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            retention, message = ChatHistory.user_retention("tests")
            assert not retention
            assert message is None

    def test_user_retention(self, mock_mongo_client):
        retention, message = ChatHistory.user_retention("tests")
        assert retention['user_retention'] == 0
        assert message is None

    def test_engaged_users_range_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            engaged_user, message = ChatHistory.engaged_users_range("tests")
            assert not engaged_user
            assert message is None

    def test_engaged_users_range(self, mock_mongo_client):
        engaged_user, message = ChatHistory.engaged_users_range("tests")
        assert engaged_user["engaged_user_range"] == {}
        assert message is None

    def test_new_user_range_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            count_user, message = ChatHistory.new_users_range("tests")
            assert not count_user
            assert message is None

    def test_new_user_range(self, mock_mongo_client):
        count_user, message = ChatHistory.new_users_range("tests")
        assert count_user['new_user_range'] == {}
        assert message is None

    def test_successful_conversation_range_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            conversation_steps, message = ChatHistory.successful_conversation_range("tests")
            assert not conversation_steps
            assert message is None

    def test_successful_conversation_range(self, mock_mongo_client):
        conversation_steps, message = ChatHistory.successful_conversation_range("tests")
        assert conversation_steps["success_conversation_range"] == {}
        assert message is None

    def test_user_retention_range_error(self, mock_mongo_processor):
        with pytest.raises(Exception):
            retention, message = ChatHistory.user_retention_range("tests")
            assert not retention
            assert message is None

    def test_user_retention_range(self, mock_mongo_client):
        retention, message = ChatHistory.user_retention_range("tests")
        assert retention['retention_range'] == {}
        assert message is None
