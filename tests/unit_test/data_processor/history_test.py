import ujson as json
import os
from datetime import datetime

from unittest import mock
import mongomock
import pytest

from kairon.exceptions import AppException
from kairon.history.processor import HistoryProcessor
from kairon.shared.data.history_log_processor import HistoryDeletionLogProcessor
from kairon.shared.utils import Utility
from mongoengine import connect
import time
from pymongo.errors import ServerSelectionTimeoutError
from mongomock import MongoClient


def load_history_data():
    db_url = "mongodb://test_kairon:27016/conversation"
    client = MongoClient(db_url)
    collection = client.get_database().get_collection("tests")
    items = json.load(open("./tests/testing_data/history/conversations_history.json", "r"))
    for item in items:
        item['event']['timestamp'] = time.time()
        if item.get('timestamp'):
            item['timestamp'] = time.time()
    collection.insert_many(items)
    return db_url, client


def load_jumbled_events_data():
    db_url = "mongodb://test_kairon:27016/conversation"
    client = MongoClient(db_url)
    collection = client.get_database().get_collection("tests")
    items = json.load(open("./tests/testing_data/history/jumbled_events.json", "r"))
    for item in items:
        item['event']['timestamp'] = time.time()
    collection.insert_many(items)
    return db_url, client


def load_flattened_history_data():
    db_url = "mongodb://test_kairon:27016/conversation"
    client = MongoClient(db_url)
    collection = client.get_database().get_collection("tests_flattened")
    items = json.load(open("./tests/testing_data/history/flattened_conversations.json", "r"))
    for item in items:
        item['timestamp'] = time.time()
    collection.insert_many(items)
    return db_url, client


db_url, mongoclient = load_history_data()
db_url_flattened, mongoclient_flattened = load_flattened_history_data()
db_url_jumbled_events, mongoclient_jumbled_events = load_jumbled_events_data()


class TestHistory:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.environment['tracker']['url'] = db_url

    @pytest.fixture
    def get_connection_delete_history(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @mock.patch('kairon.history.processor.HistoryProcessor.delete_user_history', autospec=True)
    def test_delete_user_history(self, mock_history):
        till_date = datetime.utcnow().date()
        collection = '5ebc195d5b04bcbaa45c70cc'
        sender_id = 'fshaikh@digite.com'
        HistoryProcessor.delete_user_history(collection=collection, sender_id=sender_id, till_date=till_date)
        assert True

    @mock.patch('kairon.history.processor.HistoryProcessor.archive_user_history', autospec=True)
    @mock.patch('kairon.history.processor.HistoryProcessor.delete_user_conversations', autospec=True)
    def test_delete_user_history_with_mock_functions(self, mock_delete_history, mock_archive_user_history):
        till_date = datetime.utcnow().date()
        collection = '5ebc195d5b04bcbaa45c70cc'
        sender_id = 'fshaikh@digite.com'
        HistoryProcessor.delete_user_history(collection=collection, sender_id=sender_id, till_date=till_date)
        assert True

    @mock.patch('kairon.history.processor.HistoryProcessor.delete_user_conversations', autospec=True)
    def test_delete_user_conversations(self, mock_history):
        till_date_timestamp = Utility.get_timestamp_from_date(datetime.utcnow().date())
        collection = '5ebc195d5b04bcbaa45c70cc'
        sender_id = 'fshaikh@digite.com'
        HistoryProcessor.delete_user_conversations(collection=collection, sender_id=sender_id,
                                                   till_date_timestamp=till_date_timestamp)
        assert True

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_delete_bot_history(self, mock_client):
        till_date = datetime.utcnow().date()
        mock_client.return_value = mongoclient
        collection = '5f1928bda7c0280ca4869da3'
        msg = HistoryProcessor.delete_bot_history(collection=collection, till_date=till_date)

        assert msg == "Deleting User history!"

    def test_is_event_in_progress(self, get_connection_delete_history):
        assert not HistoryDeletionLogProcessor.is_event_in_progress('5f1928bda7c0280ca4869da3')

    def test_is_event_in_progress_with_aborted(self, get_connection_delete_history):
        till_date = datetime.utcnow().date()
        HistoryDeletionLogProcessor.add_log('5f1928bda7c0280ca4869da3', 'test_user',
                                            till_date, status='Aborted')
        assert not HistoryDeletionLogProcessor.is_event_in_progress('5f1928bda7c0280ca4869da3', False)

    def test_is_event_in_progress_failure(self, get_connection_delete_history):
        till_date = datetime.utcnow().date()
        HistoryDeletionLogProcessor.add_log('5f1928bda7c0280ca4869da3', 'test_user',
                                            till_date, status='In progress')
        assert HistoryDeletionLogProcessor.is_event_in_progress('5f1928bda7c0280ca4869da3', False)

        with pytest.raises(AppException, match='Event already in progress! Check logs.'):
            HistoryDeletionLogProcessor.is_event_in_progress('5f1928bda7c0280ca4869da3')

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_fetch_chat_users_db_error(self, mock_client):
        mock_client.side_effect = AppException("Could not connect to tracker: ")
        with pytest.raises(AppException) as e:
            users = HistoryProcessor.fetch_chat_users(collection="tests")
            assert len(users) == 0
            assert str(e).__contains__('Could not connect to tracker: ')

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_fetch_chat_users(self, mock_client):
        mock_client.return_value = mongoclient
        users = HistoryProcessor.fetch_chat_users(collection="tests")
        assert len(users) == 2

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_fetch_chat_users_empty(self, mock_client):
        mock_client.return_value = mongoclient
        users = HistoryProcessor.fetch_chat_users(collection="tests")
        assert len(users) == 2

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_fetch_chat_history_error(self, mock_client):
        mock_client.side_effect = AppException("")
        with pytest.raises(AppException):
            history, message = HistoryProcessor.fetch_chat_history(sender="123", collection="tests")
            assert len(history) == 0
            assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_fetch_chat_history_empty(self, mock_client):
        mock_client.return_value = mongoclient
        history, message = HistoryProcessor.fetch_chat_history(sender="123", collection="tests")
        assert len(history) == 0
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_fetch_chat_history(self, mock_client):
        mock_client.return_value = mongoclient_flattened

        history, message = HistoryProcessor.fetch_chat_history(
            sender='mathew.anil@digite.com', collection="tests_flattened"
        )
        assert len(history) == 12
        assert history[0]["sender_id"]
        assert history[0]["timestamp"]
        assert history[0]["data"]["name"]
        assert history[0]["data"]["template"]
        assert history[0]["data"]["template_params"] is None
        assert history[1]["sender_id"]
        assert history[1]["timestamp"]
        assert history[1]["data"]["user_input"]
        assert history[1]["data"]["intent"]
        assert history[1]["data"]["confidence"]
        assert history[1]["data"]["action"]
        assert history[1]["data"]['bot_response_text']
        assert history[1]["data"]['bot_response_data']
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_visitor_hit_fallback_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError('Failed to connect')
        hit_fall_back, message = HistoryProcessor.visitor_hit_fallback("test")
        assert hit_fall_back['fallback_count'] == 0
        assert hit_fall_back['total_count'] == 0
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_visitor_hit_fallback(self, mock_client):
        mock_client.return_value = mongoclient
        hit_fall_back, message = HistoryProcessor.visitor_hit_fallback("tests")
        assert hit_fall_back["fallback_count"] == 2
        assert hit_fall_back["total_count"] == 273
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_visitor_hit_fallback_action_not_configured(self, mock_client):
        mock_client.return_value = mongoclient
        hit_fall_back, message = HistoryProcessor.visitor_hit_fallback("tests")
        assert hit_fall_back["fallback_count"] == 2
        assert hit_fall_back["total_count"] == 273
        assert message is None is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_visitor_hit_fallback_custom_action(self, mock_client):
        mock_client.return_value = mongoclient
        hit_fall_back, message = HistoryProcessor.visitor_hit_fallback("tests",
                                                                       fallback_intent="utter_location_query")
        assert hit_fall_back["fallback_count"] == 0
        assert hit_fall_back["total_count"] == 273
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_visitor_hit_fallback_nlu_fallback_configured(self, mock_client):
        mock_client.return_value = mongoclient
        hit_fall_back, message = HistoryProcessor.visitor_hit_fallback("tests",
                                                                       fallback_intent="utter_please_rephrase")

        assert hit_fall_back["fallback_count"] == 100
        assert hit_fall_back["total_count"] == 273
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_conversation_steps_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        conversation_steps, message = HistoryProcessor.conversation_steps("tests")
        assert conversation_steps == []
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_conversation_steps_empty(self, mock_client):
        mock_client.return_value = mongoclient
        conversation_steps, message = HistoryProcessor.conversation_steps("test")
        assert not conversation_steps
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_conversation_steps(self, mock_client):
        mock_client.return_value = mongoclient
        conversation_steps, message = HistoryProcessor.conversation_steps("tests")
        assert len(conversation_steps) == 17
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_with_metrics(self, mock_client):
        mock_client.return_value = mongoclient
        users, message = HistoryProcessor.user_with_metrics("tests")
        assert users
        assert users[0]['latest_event_time']
        assert users[0]['steps']
        assert users[0]['sender_id']
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_engaged_users_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        engaged_user, message = HistoryProcessor.engaged_users("tests")
        assert engaged_user['engaged_users'] == 0
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_engaged_users(self, mock_client):
        mock_client.return_value = mongoclient
        engaged_user, message = HistoryProcessor.engaged_users("tests")
        assert engaged_user['engaged_users'] == 7
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_new_user_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        count_user, message = HistoryProcessor.new_users("tests")
        assert count_user['new_users'] == 0
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_new_user(self, mock_client):
        mock_client.return_value = mongoclient
        count_user, message = HistoryProcessor.new_users("tests")
        assert count_user['new_users'] == 5
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_successful_conversation_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        conversation_steps, message = HistoryProcessor.successful_conversations("tests")
        assert conversation_steps['successful_conversations'] == 0
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_successful_conversation(self, mock_client):
        mock_client.return_value = mongoclient
        conversation_steps, message = HistoryProcessor.successful_conversations("tests")
        assert conversation_steps['successful_conversations'] == 271
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_retention_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        retention, message = HistoryProcessor.user_retention("tests")
        assert retention['user_retention'] == 0
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_retention(self, mock_client):
        mock_client.return_value = mongoclient
        retention, message = HistoryProcessor.user_retention("tests")
        assert round(retention['user_retention']) == round(63)
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_engaged_users_range_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        engaged_user, message = HistoryProcessor.engaged_users_range("tests")
        assert engaged_user["engaged_user_range"] == {}
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_engaged_users_range(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        engaged_user, message = HistoryProcessor.engaged_users_range("tests")
        assert engaged_user["engaged_user_range"] == {}
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_new_user_range_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        count_user, message = HistoryProcessor.new_users_range("tests")
        assert count_user['new_user_range'] == {}
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_new_user_range(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        count_user, message = HistoryProcessor.new_users_range("tests")
        assert count_user['new_user_range'] == {}
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_successful_conversation_range_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        conversation_steps, message = HistoryProcessor.successful_conversation_range("tests")
        assert conversation_steps['successful'] == []
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_successful_conversation_range(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        conversation_steps, message = HistoryProcessor.successful_conversation_range("tests")
        assert conversation_steps['successful'] == []
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_retention_range_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        retention, message = HistoryProcessor.user_retention_range("tests")
        assert retention['retention_range'] == {}
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_retention_range(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        retention, message = HistoryProcessor.user_retention_range("tests")
        assert retention['retention_range'] == {}
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_fallback_range_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        f_count, message = HistoryProcessor.fallback_count_range("tests")
        assert f_count["fallback_count_rate"] == {}
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_fallback_range(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        f_count, message = HistoryProcessor.fallback_count_range("tests")
        assert f_count["fallback_count_rate"] == {}
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_flatten_conversation_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        f_count, message = HistoryProcessor.flatten_conversations("tests")
        assert f_count["conversation_data"] == []
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_flatten_conversation_range(self, mock_client):
        mock_client.return_value = mongoclient_flattened
        f_count, message = HistoryProcessor.flatten_conversations("tests")
        assert f_count["conversation_data"] == []
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_total_conversation_range_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        conversation_steps, message = HistoryProcessor.total_conversation_range("tests")
        assert conversation_steps["total_conversation_range"] == {}
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_total_conversation_range(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        conversation_steps, message = HistoryProcessor.total_conversation_range("tests")
        assert conversation_steps["total_conversation_range"] == {}
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_top_intent_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        with pytest.raises(Exception):
            HistoryProcessor.top_n_intents("tests")

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_top_intent(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        top_n, message = HistoryProcessor.top_n_intents("tests")
        assert top_n == []
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_top_action_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        with pytest.raises(Exception):
            HistoryProcessor.top_n_actions("tests")

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_top_action(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        top_n, message = HistoryProcessor.top_n_actions("tests")
        assert top_n == []
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_conversation_step_range_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        conversation_steps, message = HistoryProcessor.average_conversation_step_range("tests")
        assert conversation_steps["average_conversation_steps"] == {}
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_conversation_step_range(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        conversation_steps, message = HistoryProcessor.average_conversation_step_range("tests")
        assert conversation_steps["average_conversation_steps"] == {}
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_wordcloud_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        with pytest.raises(Exception):
            HistoryProcessor.word_cloud("tests")

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_wordcloud(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        conversation, message = HistoryProcessor.word_cloud("tests")
        assert conversation == ""
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_wordcloud_data(self, mock_client):
        mock_client.return_value = mongoclient
        conversation, message = HistoryProcessor.word_cloud("tests")
        assert conversation
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_wordcloud_data_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        with pytest.raises(Exception):
            HistoryProcessor.word_cloud("conversations", u_bound=.5, l_bound=.6)

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_input_count_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        input_count, message = HistoryProcessor.user_input_count("tests")
        assert input_count == []
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_input_count(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        user_input, message = HistoryProcessor.user_input_count("tests")
        assert user_input == []
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_dropoff_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        user_list, message = HistoryProcessor.user_fallback_dropoff("tests")
        assert user_list["Dropoff_list"] == {}
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_dropoff(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        user_list, message = HistoryProcessor.user_fallback_dropoff("tests")
        assert user_list["Dropoff_list"] == {}
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_intent_dropoff_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        intent_dropoff, message = HistoryProcessor.intents_before_dropoff("tests")
        assert intent_dropoff == {}
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_user_intent_dropoff(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        intent_dropoff, message = HistoryProcessor.intents_before_dropoff("tests")
        assert intent_dropoff == {}
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_unsuccessful_session_count_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        user_list, message = HistoryProcessor.unsuccessful_session("tests")
        assert user_list == {}
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_unsuccessful_session_count(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        user_list, message = HistoryProcessor.unsuccessful_session("tests")
        assert user_list == {}
        assert message is None

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_total_sessions_error(self, mock_client):
        mock_client.side_effect = ServerSelectionTimeoutError("Failed to connect")
        user_list, message = HistoryProcessor.session_count("tests")
        assert user_list == {}
        assert message == "Failed to connect"

    @mock.patch('kairon.history.processor.MongoClient', autospec=True)
    def test_total_sessions(self, mock_client):
        mock_client.return_value = mongomock.MongoClient(Utility.environment['tracker']['url'])
        user_list, message = HistoryProcessor.session_count("tests")
        assert user_list == {}
        assert message is None
