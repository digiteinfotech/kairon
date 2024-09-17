import os
import re
from unittest import mock

import pytest
import responses
from bson import ObjectId
from mongoengine import connect, ValidationError

from kairon import Utility
from kairon.exceptions import AppException
from kairon.shared.custom_widgets.processor import CustomWidgetsProcessor
from kairon.shared.data.processor import MongoProcessor
from mongomock import MongoClient


class TestCustomWidgetsProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())

    def test_add_custom_widget(self):
        bot = "test_bot"
        user = "test_user"
        expected_config = {
            "name": "agtech weekly trends", "http_url": "http://agtech.com/trends/1",
            "request_parameters": [{"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                                   {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"}],
            "headers": [{"key": "client", "value": "kairon", "parameter_type": "value"},
                        {"key": "authorization", "value": "AUTH_TOKEN", "parameter_type": "key_vault"}],

        }
        widget_id = CustomWidgetsProcessor.save_config(expected_config, bot, user)
        saved_config = list(CustomWidgetsProcessor.get_config(bot))
        saved_config = [config for config in saved_config if config["_id"] == widget_id][0]
        pytest.widget_id = saved_config.pop("_id")
        expected_config["request_method"] = "GET"
        expected_config["timeout"] = 5
        expected_config.pop("user")
        assert saved_config == expected_config

    def test_add_custom_widget_already_exists(self):
            bot = "test_bot"
            user = "test_user"
            expected_config = {
                "name": "agtech weekly trends", "http_url": "http://agtech.com/trends/1",
                "request_parameters": [{"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                                       {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"}],
                "headers": [{"key": "client", "value": "kairon", "parameter_type": "value"},
                            {"key": "authorization", "value": "AUTH_TOKEN", "parameter_type": "key_vault"}],

            }
            with pytest.raises(AppException, match="Widget with name exists!"):
                CustomWidgetsProcessor.save_config(expected_config, bot, user)

    def test_add_custom_widget_invalid_config(self):
        bot = "test_bot1"
        user = "test_user"
        expected_config = {
            "name": "agtech weekly trends", "http_url": "http://agtech.com/trends/1",
            "request_parameters": [{"key": "", "value": "tomato", "parameter_type": "value"},
                                   {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"}],
            "headers": [{"key": "client", "value": "kairon", "parameter_type": "value"},
                        {"key": "authorization", "value": "AUTH_TOKEN", "parameter_type": "key_vault"}],

        }

        with pytest.raises(ValidationError, match="key in parameters cannot be empty!"):
            CustomWidgetsProcessor.save_config(expected_config, bot, user)

        expected_config["request_parameters"][0]["key"] = "crop_type"
        expected_config["headers"][1]["value"] = ""
        with pytest.raises(ValidationError, match="Provide key from key vault as value!"):
            CustomWidgetsProcessor.save_config(expected_config, bot, user)

    def test_edit_custom_widget(self):
        bot = "test_bot"
        user = "test_user"
        expected_config = {
            "name": "agtech monthly trends", "http_url": "http://agtech.com/trends/monthly",
            "request_parameters": [{"key": "crop", "value": "CROP_TYPE", "parameter_type": "key_vault"},
                                   {"key": "org", "value": "kairon", "parameter_type": "value"}],
            "headers": [{"key": "client", "value": "kairon", "parameter_type": "key_vault"},
                        {"key": "authorization", "value": "asdfghjkliuytrerghj", "parameter_type": "value"}],
            "request_method": "POST"
        }
        CustomWidgetsProcessor.edit_config(pytest.widget_id, expected_config, bot, user)
        saved_config = list(CustomWidgetsProcessor.get_config(bot))
        saved_config = [config for config in saved_config if config["_id"] == pytest.widget_id][0]
        saved_config.pop("_id")
        expected_config["timeout"] = 5
        expected_config["bot"] = bot
        expected_config["user"] = user
        expected_config.pop("user")
        assert saved_config == expected_config

    def test_edit_custom_widget_not_exists(self):
        bot = "test_bot"
        user = "test_user"
        expected_config = {
            "name": "agtech monthly trends", "http_url": "http://agtech.com/trends/monthly",
            "request_parameters": [{"key": "crop", "value": "CROP_TYPE", "parameter_type": "key_vault"},
                                   {"key": "org", "value": "kairon", "parameter_type": "value"}],
            "headers": [{"key": "client", "value": "kairon", "parameter_type": "key_vault"},
                        {"key": "authorization", "value": "asdfghjkliuytrerghj", "parameter_type": "value"}],
            "request_method": "POST"

        }
        with pytest.raises(AppException, match="Widget does not exists!"):
            CustomWidgetsProcessor.edit_config(ObjectId().__str__(), expected_config, bot, user)

    def test_get_custom_widget_not_exists(self):
        bot = "test_bot_"
        assert list(CustomWidgetsProcessor.get_config(bot)) == []

    def test_list_widgets(self):
        bot = "test_bot"
        assert CustomWidgetsProcessor.list_widgets(bot) == [pytest.widget_id]

    def test_list_widgets_not_exists(self):
        bot = "test"
        assert CustomWidgetsProcessor.list_widgets(bot) == []

    def test_delete_widget(self):
        bot = "test_bot"
        CustomWidgetsProcessor.delete_config(pytest.widget_id, bot, "test")
        assert list(CustomWidgetsProcessor.get_config(bot)) == []

    def test_delete_widget_not_exists(self):
        bot = "test_bot"
        with pytest.raises(AppException, match="Widget does not exists!"):
            CustomWidgetsProcessor.delete_config(pytest.widget_id, bot, "test")

    @responses.activate
    def test_trigger_widget(self):
        bot = "test_bot"
        user = "test_user"
        processor = MongoProcessor()
        config = {
            "name": "agtech weekly trends", "http_url": "http://agtech.com/trends/1",
            "request_parameters": [{"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                                   {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"}],
            "headers": [{"key": "client", "value": "kairon", "parameter_type": "value"},
                        {"key": "authorization", "value": "AUTH_TOKEN", "parameter_type": "key_vault"}],
            "request_method": "POST"
        }
        widget_id = CustomWidgetsProcessor.save_config(config, bot, user)
        processor.add_secret("ORG_NAME", "kairon", bot, user)
        processor.add_secret("AUTH_TOKEN", "sdfghjk456789", bot, user)

        expected_resp = {"data": {"name": config["name"], "data": [{"1": 200, "2": 300, "3": 400, "4": 500, "5": 600}]}}

        responses.add(
            "POST", config["http_url"],
            json=expected_resp,
            match=[
                responses.matchers.json_params_matcher({"crop_type": "tomato", "org": "kairon"}),
                responses.matchers.header_matcher({"client": "kairon", "authorization": "sdfghjk456789"})],
        )

        actual_response, msg = CustomWidgetsProcessor.trigger_widget(widget_id, bot, user)
        assert actual_response == expected_resp
        assert not msg

        logs = list(CustomWidgetsProcessor.get_logs(bot))
        assert logs[0].pop("timestamp")
        assert logs == [
            {'name': 'agtech weekly trends', 'request_method': 'POST', 'http_url': 'http://agtech.com/trends/1',
             'headers': {'client': 'kairon', 'authorization': '***********89'},
             'request_parameters': {'crop_type': 'tomato', 'org': '****on'}, 'response': {
                'data': {'name': 'agtech weekly trends', 'data': [{'1': 200, '2': 300, '3': 400, '4': 500, '5': 600}]}},
             'requested_by': user, 'bot': bot}]

    def test_delete_secret_attached_to_custom_widget(self):
        bot = "test_bot"
        processor = MongoProcessor()
        with pytest.raises(AppException, match=re.escape("Key is attached to custom widget: ['agtech weekly trends']")):
            processor.delete_secret("AUTH_TOKEN", bot)

    @responses.activate
    def test_trigger_widget_dynamic_request(self):
        bot = "test_bot_dynamic_params"
        user = "test_user"
        processor = MongoProcessor()
        config = {
            "name": "agtech weekly trends", "http_url": "http://agtech.com/trends/1",
            "dynamic_parameters": 'return {"crop_type": "chili", "org": "agtech"}',
            "headers": [{"key": "client", "value": "agtech", "parameter_type": "value"},
                        {"key": "authorization", "value": "AUTH_TOKEN", "parameter_type": "key_vault"}],
            "request_method": "POST"
        }
        widget_id = CustomWidgetsProcessor.save_config(config, bot, user)
        processor.add_secret("ORG_NAME", "agtech", bot, user)
        processor.add_secret("AUTH_TOKEN", "sdfghjk456789", bot, user)

        expected_resp = {"data": {"name": config["name"], "data": [{"1": 200, "2": 300, "3": 400, "4": 500, "5": 600}]}}

        responses.add(
            method=responses.POST,
            url=Utility.environment['evaluator']['url'],
            json={"success": True, "data": {"crop_type": "chili", "org": "agtech"}},
            status=200,
            match=[
                responses.matchers.json_params_matcher(
                    {'script': 'return {"crop_type": "chili", "org": "agtech"}', 'data': {"context": {"key_vault": {"ORG_NAME": "agtech", "AUTH_TOKEN": "sdfghjk456789"}}}})],
        )

        responses.add(
            "POST", config["http_url"],
            json=expected_resp,
            match=[
                responses.matchers.json_params_matcher({"crop_type": "chili", "org": "agtech"}),
                responses.matchers.header_matcher({"client": "agtech", "authorization": "sdfghjk456789"})],
        )

        actual_response, msg = CustomWidgetsProcessor.trigger_widget(widget_id, bot, user)
        assert actual_response == expected_resp
        assert not msg

        logs = list(CustomWidgetsProcessor.get_logs(bot))
        assert logs[0].pop("timestamp")
        print(logs)
        assert logs == [
            {'name': 'agtech weekly trends', 'request_method': 'POST', 'http_url': 'http://agtech.com/trends/1',
             'headers': {'client': 'agtech', 'authorization': '***********89'},
             'request_parameters': {'crop_type': 'chili', 'org': '****ch'}, 'response': {
                'data': {'name': 'agtech weekly trends', 'data': [{'1': 200, '2': 300, '3': 400, '4': 500, '5': 600}]}},
             'requested_by': user, 'bot': bot}]

    @responses.activate
    def test_trigger_widget_without_request_parameters_and_headers(self):
        bot = "test_bot_2"
        user = "test_user"
        processor = MongoProcessor()
        config = {
            "name": "agtech weekly trends without request parameters", "http_url": "http://agtech.com/trends/1",
            "headers": [{"key": "client", "value": "kairon", "parameter_type": "value"},
                        {"key": "authorization", "value": "AUTH_TOKEN", "parameter_type": "key_vault"}],
            "request_method": "POST"
        }
        widget_id = CustomWidgetsProcessor.save_config(config, bot, user)
        processor.add_secret("ORG_NAME", "kairon", bot, user)
        processor.add_secret("AUTH_TOKEN", "sdfghjk456789", bot, user)

        expected_resp = {"data": {"name": config["name"], "data": [{"1": 200, "2": 300, "3": 400, "4": 500, "5": 600}]}}

        responses.add(
            "POST", config["http_url"],
            json=expected_resp,
            match=[
                responses.matchers.header_matcher({"client": "kairon", "authorization": "sdfghjk456789"})],
        )

        actual_response, msg = CustomWidgetsProcessor.trigger_widget(widget_id, bot, user)
        assert not msg
        assert actual_response == expected_resp

        logs = list(CustomWidgetsProcessor.get_logs(bot))
        assert logs[0].pop("timestamp")
        assert logs == [
            {'name': 'agtech weekly trends without request parameters', 'request_method': 'POST', 'http_url': 'http://agtech.com/trends/1',
             'headers': {'client': 'kairon', 'authorization': '***********89'},
             'request_parameters': {}, 'response': {
                'data': {'name': 'agtech weekly trends without request parameters', 'data': [{'1': 200, '2': 300, '3': 400, '4': 500, '5': 600}]}},
             'requested_by': user, 'bot': bot}]

        config = {
            "name": "agtech weekly trends without request parameters", "http_url": "http://agtech.com/trends/1",
            "request_method": "POST"
        }
        CustomWidgetsProcessor.edit_config(widget_id, config, bot, user)

        responses.add(
            "POST", config["http_url"],
            json=expected_resp,
        )
        actual_response, msg = CustomWidgetsProcessor.trigger_widget(widget_id, bot, user)
        assert actual_response == expected_resp
        assert not msg

    @responses.activate
    def test_trigger_widget_with_get_url(self):
        bot = "test_bot_3"
        user = "test_user"
        processor = MongoProcessor()
        config = {
            "name": "agtech weekly trends", "http_url": "http://agtech.com/trends/1",
            "request_parameters": [{"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                                   {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"}],
            "headers": [{"key": "client", "value": "kairon", "parameter_type": "value"},
                        {"key": "authorization", "value": "AUTH_TOKEN", "parameter_type": "key_vault"}],
        }
        pytest.widget_id3 = CustomWidgetsProcessor.save_config(config, bot, user)
        processor.add_secret("ORG_NAME", "kairon", bot, user)
        processor.add_secret("AUTH_TOKEN", "sdfghjk456789", bot, user)

        expected_resp = {"data": {"name": config["name"], "data": [{"1": 200, "2": 300, "3": 400, "4": 500, "5": 600}]}}

        responses.add(
            "GET", config["http_url"],
            json=expected_resp,
            match=[
                responses.matchers.query_param_matcher({"crop_type": "tomato", "org": "kairon"}),
                responses.matchers.header_matcher({"client": "kairon", "authorization": "sdfghjk456789"})],
        )

        actual_response, msg = CustomWidgetsProcessor.trigger_widget(pytest.widget_id3, bot, user)
        assert actual_response == expected_resp
        assert not msg

        logs = list(CustomWidgetsProcessor.get_logs(bot))
        assert logs[0].pop("timestamp")
        assert logs == [
            {'name': 'agtech weekly trends', 'request_method': 'GET', 'http_url': 'http://agtech.com/trends/1',
             'headers': {'client': 'kairon', 'authorization': '***********89'},
             'request_parameters': {'crop_type': 'tomato', 'org': '****on'}, 'response': {
                'data': {'name': 'agtech weekly trends', 'data': [{'1': 200, '2': 300, '3': 400, '4': 500, '5': 600}]}},
             'requested_by': user, 'bot': bot}]

    @mock.patch("kairon.shared.utils.Utility.execute_http_request", autospec=True)
    def test_trigger_widget_failure(self, mock_request):
        bot = "test_bot_4"
        user = "test_user"
        processor = MongoProcessor()
        config = {
            "name": "agtech weekly trends", "http_url": "http://agtech.com/trends/1",
            "request_parameters": [{"key": "crop_type", "value": "tomato", "parameter_type": "value"},
                                   {"key": "org", "value": "ORG_NAME", "parameter_type": "key_vault"}],
            "headers": [{"key": "client", "value": "kairon", "parameter_type": "value"},
                        {"key": "authorization", "value": "AUTH_TOKEN", "parameter_type": "key_vault"}],
        }
        widget_id = CustomWidgetsProcessor.save_config(config, bot, user)
        processor.add_secret("ORG_NAME", "kairon", bot, user)
        processor.add_secret("AUTH_TOKEN", "sdfghjk456789", bot, user)

        def _mock_error(*args, **kwargs):
            import requests

            raise requests.exceptions.ConnectTimeout("Connection timed out!")

        mock_request.side_effect = _mock_error

        with pytest.raises(AppException, match='Connection timed out!'):
            CustomWidgetsProcessor.trigger_widget(widget_id, bot, user)

        actual_response, msg = CustomWidgetsProcessor.trigger_widget(widget_id, bot, user, raise_err=False)
        assert not actual_response
        assert msg == 'Connection timed out!'

        logs = list(CustomWidgetsProcessor.get_logs(bot))
        assert logs[0].pop("timestamp")
        assert logs[1].pop("timestamp")
        assert logs == [
            {'name': 'agtech weekly trends', 'request_method': 'GET', 'http_url': 'http://agtech.com/trends/1',
             'headers': {'client': 'kairon', 'authorization': '***********89'},
             'request_parameters': {'crop_type': 'tomato', 'org': '****on'},
             'requested_by': user, 'bot': bot, 'exception': 'Connection timed out!'},
            {'name': 'agtech weekly trends', 'request_method': 'GET', 'http_url': 'http://agtech.com/trends/1',
             'headers': {'client': 'kairon', 'authorization': '***********89'},
             'request_parameters': {'crop_type': 'tomato', 'org': '****on'},
             'requested_by': user, 'bot': bot, 'exception': 'Connection timed out!'}
        ]

    def test_trigger_widget_not_exists(self):
        bot = "test_bot_5"
        user = "test_user"

        with pytest.raises(AppException, match='Widget does not exists!'):
            CustomWidgetsProcessor.trigger_widget(ObjectId().__str__(), bot, user)

        logs = list(CustomWidgetsProcessor.get_logs(bot))
        assert logs[0].pop("timestamp")
        assert logs == [{'requested_by': user, 'bot': bot, 'exception': "Widget does not exists!"}]

    @responses.activate
    def test_trigger_widget_with_filters(self):
        bot = "test_bot_3"
        user = "test_user"

        expected_resp = {"data": [{"1": 200, "2": 300, "3": 400, "4": 500, "5": 600}]}
        filters = {"start_date": "11-11-2021", "end_date": "21-11-2021"}
        expected_query_parameters = {"crop_type": "tomato", "org": "kairon"}
        expected_query_parameters.update(filters)

        responses.add(
            "GET", "http://agtech.com/trends/1",
            json=expected_resp,
            match=[
                responses.matchers.query_param_matcher(expected_query_parameters),
                responses.matchers.header_matcher({"client": "kairon", "authorization": "sdfghjk456789"})],
        )

        actual_response, msg = CustomWidgetsProcessor.trigger_widget(pytest.widget_id3, bot, user, filters)
        assert actual_response == expected_resp
        assert not msg

        logs = list(CustomWidgetsProcessor.get_logs(bot))
        assert logs[0].pop("timestamp")
        assert logs[0] == {'name': 'agtech weekly trends', 'request_method': 'GET',
                           'http_url': 'http://agtech.com/trends/1',
                           'headers': {'client': 'kairon', 'authorization': '***********89'},
                           'request_parameters': {'crop_type': 'tomato', 'org': '****on', "start_date": "11-11-2021",
                                                  "end_date": "21-11-2021"},
                           'response': {'data': [{'1': 200, '2': 300, '3': 400, '4': 500, '5': 600}]},
                           'requested_by': user, 'bot': bot}

        saved_config = list(CustomWidgetsProcessor.get_config(bot))
        config = [config for config in saved_config if config["_id"] == pytest.widget_id3][0]
        config["request_method"] = "POST"
        CustomWidgetsProcessor.edit_config(pytest.widget_id3, config, bot, user)

        responses.add(
            "POST", "http://agtech.com/trends/1",
            json=expected_resp,
            match=[
                responses.matchers.json_params_matcher(expected_query_parameters),
                responses.matchers.header_matcher({"client": "kairon", "authorization": "sdfghjk456789"})],
        )
        actual_response, msg = CustomWidgetsProcessor.trigger_widget(pytest.widget_id3, bot, user, filters)
        assert actual_response == expected_resp
        assert not msg

        logs = list(CustomWidgetsProcessor.get_logs(bot))
        assert logs[0].pop("timestamp")
        assert logs[0] == {'name': 'agtech weekly trends', 'request_method': 'POST',
                           'http_url': 'http://agtech.com/trends/1',
                           'headers': {'client': 'kairon', 'authorization': '***********89'},
                           'request_parameters': {'crop_type': 'tomato', 'org': '****on', "start_date": "11-11-2021",
                                                  "end_date": "21-11-2021"},
                           'response': {'data': [{'1': 200, '2': 300, '3': 400, '4': 500, '5': 600}]},
                           'requested_by': user, 'bot': bot}
        assert len(logs) == 3
