import os
import re

import mock
import pytest
import requests
import responses
from mongoengine import connect

from kairon.exceptions import AppException
from kairon.shared.constants import PluginTypes
from kairon.shared.plugins.factory import PluginFactory
from kairon.shared.utils import Utility


class TestUtility:

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_email_configuration()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        yield None

    @responses.activate
    def test_ipinfo_plugin(self, monkeypatch):
        ip = "192.222.100.106"
        token = "abcgd563"
        enable = True
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
        url = f"https://ipinfo.io/{ip}?token={token}"
        expected = {
            "ip": "140.82.201.129",
            "city": "Mumbai",
            "region": "Maharashtra",
            "country": "IN",
            "loc": "19.0728,72.8826",
            "org": "AS13150 CATO NETWORKS LTD",
            "postal": "400070",
            "timezone": "Asia/Kolkata"
        }
        responses.add("GET", url, json=expected)
        response = PluginFactory.get_instance(PluginTypes.ip_info).execute(ip=ip)
        assert response == expected

    def test_enable_plugin(self):
        ip = "192.222.100.106"
        response = PluginFactory.get_instance(PluginTypes.ip_info).execute(ip=ip)
        assert not response

    @responses.activate
    def test_token_plugin(self, monkeypatch):
        ip = "192.222.100.106"
        token = "abcgd563"
        enable = True
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
        url = f"https://ipinfo.io/{ip}?token={token}"
        responses.add("GET", url, status=400)
        response = PluginFactory.get_instance(PluginTypes.ip_info).execute(ip)
        assert not response

    def test_plugin_type(self):
        valid_plugins = [plugin for plugin in PluginTypes]
        with pytest.raises(AppException, match=re.escape(f"location is not a valid event. Accepted event types: {valid_plugins}")):
            PluginFactory.get_instance("location")

    def test_empty_ip(self, monkeypatch):
        ip = {"ip": " "}
        enable = True
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
        with pytest.raises(AppException, match="ip is required"):
            PluginFactory.get_instance(PluginTypes.ip_info).execute(**ip)

    @responses.activate
    def test_gpt_plugin(self):
        prompt = "Rephrase: Kairon is envisioned as a web based microservices driven suite that helps train Rasa contextual AI assistants at scale."
        gpt_response = {'id': 'cmpl-6Hh86Qkqq0PJih2YSl9JaNkPEuy4Y', 'object': 'text_completion', 'created': 1669675386,
                        'model': 'text-davinci-002', 'choices': [{
                'text': "Greetings and welcome to kairon!!",
                'index': 0, 'logprobs': None, 'finish_reason': 'stop'}],
                        'usage': {'prompt_tokens': 43, 'completion_tokens': 38, 'total_tokens': 81}}
        responses.add(
            "POST",
            Utility.environment["plugins"]["gpt"]["url"],
            status=200, json=gpt_response,
            match=[responses.json_params_matcher(
                {'model': 'text-davinci-003', 'prompt': prompt, 'temperature': 0.7, 'max_tokens': 40})],
        )
        response = PluginFactory.get_instance(PluginTypes.gpt).execute(
            key="asdfghjkl",
            prompt=prompt
        )
        assert response == gpt_response

    @responses.activate
    def test_gpt_plugin_error(self):
        prompt = "Rephrase: Kairon is envisioned as a web based microservices driven suite that helps train Rasa contextual AI assistants at scale."
        gpt_response = {"error": {"message": "'100' is not of type 'integer' - 'max_tokens'", "type": "invalid_request_error", "param": None, "code": None} }
        responses.add(
            "POST",
            Utility.environment["plugins"]["gpt"]["url"],
            status=400, json=gpt_response,
            match=[responses.json_params_matcher(
                {'model': 'text-davinci-003', 'prompt': prompt, 'temperature': 0.7, 'max_tokens': 40})],
        )
        response = PluginFactory.get_instance(PluginTypes.gpt).execute(
            key="asdfghjkl",
            prompt=prompt
        )
        assert response == gpt_response

    def test_gpt_plugin_empty_key_prompt(self):
        with pytest.raises(AppException, match="key and prompt are required to trigger gpt"):
            PluginFactory.get_instance(PluginTypes.gpt).execute(
                key="asdfghjkl",
                prompt=None
            )
        with pytest.raises(AppException, match="key and prompt are required to trigger gpt"):
            PluginFactory.get_instance(PluginTypes.gpt).execute(
                key="asdfghjkl",
                prompt=" "
            )
        with pytest.raises(AppException, match="key and prompt are required to trigger gpt"):
            PluginFactory.get_instance(PluginTypes.gpt).execute(
                key=" ",
                prompt="asdfghjkl"
            )
        with pytest.raises(AppException, match="key and prompt are required to trigger gpt"):
            PluginFactory.get_instance(PluginTypes.gpt).execute(
                key=None,
                prompt="asdfghjkl"
            )

    def test_gpt_plugin_connection_error(self):
        prompt = "Rephrase: Kairon is envisioned as a web based microservices driven suite that helps train Rasa contextual AI assistants at scale."

        def __mock_connection_error(*args, **kwargs):
            raise requests.exceptions.ConnectTimeout()

        with mock.patch("kairon.shared.utils.requests.request") as mocked:
            mocked.side_effect = __mock_connection_error
            response = PluginFactory.get_instance(PluginTypes.gpt).execute(
                key="asdfghjkl",
                prompt=prompt
            )
            assert response == {'error': 'Failed to connect to service: api.openai.com'}
