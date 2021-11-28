import json
import os
from datetime import datetime

import pytest
from mongomock import MongoClient
from pymongo.collection import Collection
from pymongo.errors import ServerSelectionTimeoutError

from kairon.exceptions import AppException
from kairon.history.processor import HistoryProcessor
from kairon.shared.utils import Utility


class TestHistory:

    @pytest.fixture(autouse=True)
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/tracker.yaml"
        Utility.load_environment()

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
            event['timestamp'] = datetime.utcnow().timestamp()
        return json_data[0], None

    @pytest.fixture
    def mock_db_timeout(self, monkeypatch):
        def _mock_db_timeout(*args, **kwargs):
            raise ServerSelectionTimeoutError('Failed to connect')

        monkeypatch.setattr(Collection, 'aggregate', _mock_db_timeout)
        monkeypatch.setattr(Collection, 'find', _mock_db_timeout)

    @pytest.fixture
    def mock_fallback_user_data(self, monkeypatch):
        def db_client(*args, **kwargs):
            client = MongoClient(Utility.environment['tracker']['url'])
            db = client.get_database("conversation")
            conversations = db.get_collection("conversations")
            history, _ = self.get_history_conversations()
            conversations.insert(history)
            return client, 'Loading host:mongodb://test_kairon:27016, db:conversation, collection:conversations '

        monkeypatch.setattr(HistoryProcessor, "get_mongo_connection", db_client)

    @pytest.fixture
    def mock_mongo_client(self, monkeypatch):
        def db_client(*args, **kwargs):
            client = MongoClient(Utility.environment['tracker']['url'])
            db = client.get_database("conversation")
            conversations = db.get_collection("conversations")
            history, _ = self.history_conversations()
            conversations.insert_many(history)
            return client, 'Loading host:mongodb://test_kairon:27016, db:conversation, collection:conversations'

        monkeypatch.setattr(HistoryProcessor, "get_mongo_connection", db_client)

    def test_fetch_chat_users_db_error(self, mock_db_timeout):
        with pytest.raises(AppException) as e:
            users = HistoryProcessor.fetch_chat_users(collection="tests")
            assert len(users) == 0
            assert str(e).__contains__('Could not connect to tracker: ')

    def test_fetch_chat_users(self, mock_mongo_client):
        users = HistoryProcessor.fetch_chat_users(collection="tests")
        assert len(users) == 2

    def test_fetch_chat_users_empty(self, mock_mongo_client):
        users = HistoryProcessor.fetch_chat_users(collection="tests")
        assert len(users) == 2

    def test_fetch_chat_history_error(self, mock_db_timeout):
        with pytest.raises(AppException):
            history, message = HistoryProcessor.fetch_chat_history(sender="123", collection="tests")
            assert len(history) == 0
            assert message

    def test_fetch_chat_history_empty(self, mock_mongo_client):
        history, message = HistoryProcessor.fetch_chat_history(sender="123", collection="tests")
        assert len(history) == 0
        assert message

    def test_fetch_chat_history(self, monkeypatch):
        def events(*args, **kwargs):
            json_data = json.load(open("tests/testing_data/history/conversation.json"))
            return json_data['events'], 'Loading host:mongodb://test_kairon:27016, db:conversation, ' \
                                        'collection:conversations '

        monkeypatch.setattr(HistoryProcessor, "fetch_user_history", events)

        history, message = HistoryProcessor.fetch_chat_history(
            sender="5e564fbcdcf0d5fad89e3acd", collection="tests"
        )
        assert len(history) == 12
        assert history[0]["event"]
        assert history[0]["time"]
        assert history[0]["date"]
        assert history[0]["text"]
        assert history[0]["intent"]
        assert history[0]["confidence"]
        assert message

    def test_visitor_hit_fallback_error(self, mock_db_timeout):
        hit_fall_back, message = HistoryProcessor.visitor_hit_fallback("tests")
        assert hit_fall_back["fallback_count"] == 0
        assert hit_fall_back["total_count"] == 0
        print(message)
        assert message

    def test_visitor_hit_fallback(self, mock_fallback_user_data, monkeypatch):
        hit_fall_back, message = HistoryProcessor.visitor_hit_fallback("conversations")
        assert hit_fall_back["fallback_count"] == 1
        assert hit_fall_back["total_count"] == 4
        assert message

    def test_visitor_hit_fallback_action_not_configured(self, mock_fallback_user_data, monkeypatch):
        hit_fall_back, message = HistoryProcessor.visitor_hit_fallback("conversations")
        assert hit_fall_back["fallback_count"] == 1
        assert hit_fall_back["total_count"] == 4
        assert message

    def test_visitor_hit_fallback_custom_action(self, mock_fallback_user_data):
        hit_fall_back, message = HistoryProcessor.visitor_hit_fallback("conversations",
                                                                       fallback_action='utter_location_query')
        assert hit_fall_back["fallback_count"] == 1
        assert hit_fall_back["total_count"] == 4
        assert message

    def test_visitor_hit_fallback_nlu_fallback_configured(self, mock_fallback_user_data):
        hit_fall_back, message = HistoryProcessor.visitor_hit_fallback("conversations",
                                                                       fallback_action="action_default_fallback",
                                                                       nlu_fallback_action="utter_please_rephrase")

        assert hit_fall_back["fallback_count"] == 2
        assert hit_fall_back["total_count"] == 4
        assert message

    def test_conversation_time_error(self, mock_db_timeout):
        conversation_time, message = HistoryProcessor.conversation_time("tests")
        assert not conversation_time
        assert message

    def test_conversation_time_empty(self, mock_mongo_client):
        conversation_time, message = HistoryProcessor.conversation_time("tests")
        assert not conversation_time
        assert message

    def test_conversation_time(self, mock_mongo_client):
        conversation_time, message = HistoryProcessor.conversation_time("tests")
        assert conversation_time == []
        assert message

    def test_conversation_steps_error(self, mock_db_timeout):
        conversation_steps, message = HistoryProcessor.conversation_steps("tests")
        assert not conversation_steps
        assert message

    def test_conversation_steps_empty(self, mock_mongo_client):
        conversation_steps, message = HistoryProcessor.conversation_steps("tests")
        assert not conversation_steps
        assert message

    def test_conversation_steps(self, mock_mongo_client):
        conversation_steps, message = HistoryProcessor.conversation_steps("tests")
        assert conversation_steps == []
        assert message

    def test_user_with_metrics(self, mock_mongo_client):
        users, message = HistoryProcessor.user_with_metrics("tests")
        assert users == []
        assert message

    def test_engaged_users_error(self, mock_db_timeout):
        engaged_user, message = HistoryProcessor.engaged_users("tests")
        assert engaged_user['engaged_users'] == 0
        assert message

    def test_engaged_users(self, mock_mongo_client):
        engaged_user, message = HistoryProcessor.engaged_users("tests")
        assert engaged_user['engaged_users'] == 0
        assert message

    def test_new_user_error(self, mock_db_timeout):
        count_user, message = HistoryProcessor.new_users("tests")
        assert count_user['new_users'] == 0
        assert message

    def test_new_user(self, mock_mongo_client):
        count_user, message = HistoryProcessor.new_users("tests")
        assert count_user['new_users'] == 0
        assert message

    def test_successful_conversation_error(self, mock_db_timeout):
        conversation_steps, message = HistoryProcessor.successful_conversations("tests")
        assert conversation_steps['successful_conversations'] == 0
        assert message

    def test_successful_conversation(self, mock_mongo_client):
        conversation_steps, message = HistoryProcessor.successful_conversations("tests")
        assert conversation_steps['successful_conversations'] == 0
        assert message

    def test_user_retention_error(self, mock_db_timeout):
        retention, message = HistoryProcessor.user_retention("tests")
        assert retention['user_retention'] == 0
        assert message

    def test_user_retention(self, mock_mongo_client):
        retention, message = HistoryProcessor.user_retention("tests")
        assert retention['user_retention'] == 0
        assert message

    def test_engaged_users_range_error(self, mock_db_timeout):
        engaged_user, message = HistoryProcessor.engaged_users_range("tests")
        assert engaged_user["engaged_user_range"] == {}
        assert message

    def test_engaged_users_range(self, mock_mongo_client):
        engaged_user, message = HistoryProcessor.engaged_users_range("tests")
        assert engaged_user["engaged_user_range"] == {}
        assert message

    def test_new_user_range_error(self, mock_db_timeout):
        count_user, message = HistoryProcessor.new_users_range("tests")
        assert count_user['new_user_range'] == {}
        assert message

    def test_new_user_range(self, mock_mongo_client):
        count_user, message = HistoryProcessor.new_users_range("tests")
        assert count_user['new_user_range'] == {}
        assert message

    def test_successful_conversation_range_error(self, mock_db_timeout):
        conversation_steps, message = HistoryProcessor.successful_conversation_range("tests")
        assert conversation_steps['successful_sessions'] == {}
        assert message

    def test_successful_conversation_range(self, mock_mongo_client):
        conversation_steps, message = HistoryProcessor.successful_conversation_range("tests")
        assert conversation_steps['successful_sessions'] == {}
        assert message

    def test_user_retention_range_error(self, mock_db_timeout):
        retention, message = HistoryProcessor.user_retention_range("tests")
        assert retention['retention_range'] == {}
        assert message

    def test_user_retention_range(self, mock_mongo_client):
        retention, message = HistoryProcessor.user_retention_range("tests")
        assert retention['retention_range'] == {}
        assert message

    def test_fallback_range_error(self, mock_db_timeout):
        f_count, message = HistoryProcessor.fallback_count_range("tests")
        assert f_count["fallback_count_rate"] == {}
        assert message

    def test_fallback_range(self, mock_mongo_client):
        f_count, message = HistoryProcessor.fallback_count_range("tests")
        assert f_count["fallback_count_rate"] == {}
        assert message

    def test_flatten_conversation_error(self, mock_db_timeout):
        f_count, message = HistoryProcessor.flatten_conversations("tests")
        assert f_count["conversation_data"] == []
        assert message

    def test_flatten_conversation_range(self, mock_mongo_client):
        f_count, message = HistoryProcessor.flatten_conversations("tests")
        assert f_count["conversation_data"] == []
        assert message

    def test_total_conversation_range_error(self, mock_db_timeout):
        conversation_steps, message = HistoryProcessor.total_conversation_range("tests")
        assert conversation_steps["total_conversation_range"] == {}
        assert message

    def test_total_conversation_range(self, mock_mongo_client):
        conversation_steps, message = HistoryProcessor.total_conversation_range("tests")
        assert conversation_steps["total_conversation_range"] == {}
        assert message

    def test_top_intent_error(self, mock_db_timeout):
        with pytest.raises(Exception):
            HistoryProcessor.top_n_intents("tests")

    def test_top_intent(self, mock_mongo_client):
        top_n, message = HistoryProcessor.top_n_intents("tests")
        assert top_n == []
        assert message

    def test_top_action_error(self, mock_db_timeout):
        with pytest.raises(Exception):
            HistoryProcessor.top_n_actions("tests")

    def test_top_action(self, mock_mongo_client):
        top_n, message = HistoryProcessor.top_n_actions("tests")
        assert top_n == []
        assert message

    def test_conversation_step_range_error(self, mock_db_timeout):
        conversation_steps, message = HistoryProcessor.average_conversation_step_range("tests")
        assert conversation_steps["average_conversation_steps"] == {}
        assert message

    def test_conversation_step_range(self, mock_mongo_client):
        conversation_steps, message = HistoryProcessor.average_conversation_step_range("tests")
        assert conversation_steps["average_conversation_steps"] == {}
        assert message

    def test_wordcloud_error(self, mock_db_timeout):
        with pytest.raises(Exception):
            HistoryProcessor.word_cloud("tests")

    def test_wordcloud(self, mock_mongo_client):
        conversation, message = HistoryProcessor.word_cloud("tests")
        assert conversation == ""
        assert message

    def test_wordcloud_data(self, mock_fallback_user_data):
        conversation, message = HistoryProcessor.word_cloud("conversations")
        assert conversation
        assert message

    def test_wordcloud_data_error(self, mock_fallback_user_data):
        with pytest.raises(Exception):
            HistoryProcessor.word_cloud("conversations", u_bound=.5, l_bound=.6)

    def test_user_input_count_error(self, mock_db_timeout):
        input_count, message = HistoryProcessor.user_input_count("tests")
        assert input_count == []
        assert message

    def test_user_input_count(self, mock_mongo_client):
        user_input, message = HistoryProcessor.user_input_count("tests")
        assert user_input == []
        assert message

    def test_conversation_time_range_error(self, mock_db_timeout):
        conversation_time, message = HistoryProcessor.average_conversation_time_range("tests")
        assert conversation_time["Conversation_time_range"] == {}
        assert message

    def test_conversation_time_range(self, mock_mongo_client):
        conversation_time, message = HistoryProcessor.average_conversation_time_range("tests")
        assert conversation_time["Conversation_time_range"] == {}
        assert message

    def test_user_dropoff_error(self, mock_db_timeout):
        user_list, message = HistoryProcessor.user_fallback_dropoff("tests")
        assert user_list["Dropoff_list"] == {}
        assert message

    def test_user_dropoff(self, mock_mongo_client):
        user_list, message = HistoryProcessor.user_fallback_dropoff("tests")
        assert user_list["Dropoff_list"] == {}
        assert message

    def test_user_intent_dropoff_error(self, mock_db_timeout):
        intent_dropoff, message = HistoryProcessor.intents_before_dropoff("tests")
        assert intent_dropoff == {}
        assert message

    def test_user_intent_dropoff(self, mock_mongo_client):
        intent_dropoff, message = HistoryProcessor.intents_before_dropoff("tests")
        assert intent_dropoff == {}
        assert message

    def test_unsuccessful_session_count_error(self, mock_db_timeout):
        user_list, message = HistoryProcessor.unsuccessful_session("tests")
        assert user_list == {}
        assert message

    def test_unsuccessful_session_count(self, mock_mongo_client):
        user_list, message = HistoryProcessor.unsuccessful_session("tests")
        assert user_list == {}
        assert message

    def test_total_sessions_error(self, mock_db_timeout):
        user_list, message = HistoryProcessor.session_count("tests")
        assert user_list == {}
        assert message

    def test_total_sessions(self, mock_mongo_client):
        user_list, message = HistoryProcessor.session_count("tests")
        assert user_list == {}
        assert message
