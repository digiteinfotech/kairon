import os
import re

import pytest
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
        ip = {"ip": "192.222.100.106"}
        token = "abcgd563"
        enable = True
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
        url = f"https://ipinfo.io/{ip.get('ip')}?token={token}"
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
        response = PluginFactory.get_instance(PluginTypes.ip_info).execute(**ip)
        assert response == expected

    def test_enable_plugin(self):
        ip = {"ip": "192.222.100.106"}
        response = PluginFactory.get_instance(PluginTypes.ip_info).execute(**ip)
        assert not response

    def test_token_plugin(self, monkeypatch):
        ip = {"ip": "192.222.100.106"}
        token = "abcgd563"
        enable = True
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
        url = f"https://ipinfo.io/{ip.get('ip')}?token={token}"
        responses.add("GET", url, status= 400)
        response = PluginFactory.get_instance(PluginTypes.ip_info).execute(**ip)
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
