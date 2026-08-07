import io
import os
from datetime import datetime,timedelta
from unittest import mock
from unittest.mock import patch

import pytest
import responses
from mongoengine import connect, ValidationError

from kairon.exceptions import AppException
from kairon.shared.auth import Authentication
from kairon.shared.channels.whatsapp.bsp.base import WhatsappBusinessServiceProviderBase
from kairon.shared.channels.whatsapp.bsp.dialog360 import BSP360Dialog
from kairon.shared.channels.whatsapp.bsp.factory import BusinessServiceProviderFactory
from kairon.shared.channels.whatsapp.bsp.gupshup import BSPGupshup
from kairon.shared.chat.data_objects import Channels
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.chat.user_media import UserMedia
from kairon.shared.constants import WhatsappBSPTypes, ChannelTypes
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.data_objects import BotSettings, UserMediaData
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.models import UserMediaUploadStatus, UserMediaUploadType
from kairon.shared.utils import Utility
from mongomock import MongoClient


class TestBusinessServiceProvider:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        db_url = Utility.environment['database']["url"]
        pytest.db_url = db_url
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    @responses.activate
    def test_get_auth_token(self, monkeypatch):
        partner_username = "udit"
        partner_password = "Test@test"
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], "partner_username", partner_username)
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], "partner_password", partner_password)
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        url = f"{base_url}/api/v2/token"
        api_resp = {
            "token_type": "bearer", "access_token": "sdfghjkl;34567890-"
        }
        responses.add("POST", json=api_resp, url=url,
                      match=[
                          responses.matchers.json_params_matcher({"username": partner_username, "password": partner_password})])
        actual = BSP360Dialog.get_partner_auth_token()
        assert actual == api_resp.get("token_type") + " " + api_resp.get("access_token")

    @responses.activate
    def test_get_auth_token_error(self):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        url = f"{base_url}/api/v2/token"
        responses.add("POST", json={}, url=url, status=500)
        with pytest.raises(AppException, match=r"Failed to get partner auth token: *"):
            BSP360Dialog.get_partner_auth_token()

    @responses.activate
    def test_get_account(self, monkeypatch):
        channel_id = "skds23Ga"
        partner_id = "jhgajfdk"

        def _get_partners_auth_token(*args, **kwargs):
            return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

        monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], "partner_id", partner_id)
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        url = f'{base_url}/api/v2/partners/{partner_id}/channels?filters={{"id":"{channel_id}"}}'
        api_resp = {
            "count": 3,
            "filters": {},
            "limit": 1000,
            "offset": 0,
            "partner_channels": [
                {
                    "waba_account": {
                        "client_id": "3CpBg3xvCL",
                        "consents": {},
                        "created_at": "2023-02-28T14:36:45Z",
                        "created_by": {
                            "user_id": "system",
                            "user_name": "system"
                        },
                        "id": "DWLgd6WA",
                        "name": "SandboxTest",
                        "namespace": "1212e9fb_86f2_493d_8d24_cbf159a9b876",
                    },
                    "waba_account_id": "DWLgd6WA"
                }
            ],
            "sort": [
                "id"
            ],
            "total": 3
        }
        responses.add("GET", json=api_resp, url=url)
        actual = BSP360Dialog("test", "test").get_account(channel_id)
        assert actual == api_resp["partner_channels"][0]["waba_account"]["id"]

    @responses.activate
    def test_get_account_failure(self, monkeypatch):
        channel_id = "skds23Ga"
        partner_id = "jhgajfdk"

        def _get_partners_auth_token(*args, **kwargs):
            return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

        monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], "partner_id", partner_id)

        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        url = f'{base_url}/api/v2/partners/{partner_id}/channels?filters={{"id":"{channel_id}"}}'
        responses.add("GET", json={}, url=url, status=500)
        with pytest.raises(AppException, match=r"Failed to retrieve account info: *"):
            BSP360Dialog("test", "test").get_account(channel_id)

    @responses.activate
    def test_get_account_auth_failure(self, monkeypatch):
        channel_id = "skds23Ga"
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        url = f"{base_url}/api/v2/token"
        responses.add("POST", json={}, url=url, status=401)
        with pytest.raises(AppException, match=r"Failed to get partner auth token: *"):
            BSP360Dialog("test", "test").get_account(channel_id)

    @responses.activate
    def test_set_webhook_url(self, monkeypatch):
        def _get_partners_auth_token(*args, **kwargs):
            return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

        monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)

        webhook_url = "https://kaironlocalchat.digite.com/api/bot/waba_partner/62bc24b493a0d6b7a46328f5/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY"
        api_key = "kHCwksdsdsMVYVx0doabaDyRLUQJUAK"
        url = "https://waba-v2.360dialog.io/v1/configs/webhook"
        responses.add("POST",
                      json={
                          "url": "https://kaironlocalchat.digite.com/api/bot/waba_partner/62bc24b493a0d6b7a46328f5/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY",
                      }, url=url)
        webhook_url = BSP360Dialog.set_webhook_url(api_key, webhook_url)
        assert webhook_url == "https://kaironlocalchat.digite.com/api/bot/waba_partner/62bc24b493a0d6b7a46328f5/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY"

    @responses.activate
    def test_set_webhook_url_failure(self):
        url = "https://waba-v2.360dialog.io/v1/configs/webhook"
        responses.add("POST", json={}, url=url, status=500)
        webhook_url = "https://kaironlocalchat.digite.com/api/bot/waba_partner/62bc24b493a0d6b7a46328f5/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY"
        api_key = "kHCwksdsdsMVYVx0doabaDyRLUQJUAK"
        with pytest.raises(AppException, match=r"Failed to set webhook url: *"):
            BSP360Dialog.set_webhook_url(api_key, webhook_url)

    @responses.activate
    def test_generate_waba_key(self, monkeypatch):
        def _get_partners_auth_token(*args, **kwargs):
            return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

        monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], "partner_id", 'f167CmPA')
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], "partner_username", 'testuser')
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], "partner_password", 'testpassword')
        url = "https://hub.360dialog.io/api/v2/partners/f167CmPA/channels/skds23Ga/api_keys"
        responses.add("POST",
                      json={
                          "address": "https://waba-v2.360dialog.io",
                          "api_key": "kHCwksdsdsMVYVx0doabaDyRLUQJUAK",
                          "app_id": "104148",
                          "id": "201126"
                      }, url=url)
        api_key = BSP360Dialog.generate_waba_key("skds23Ga")
        assert api_key == "kHCwksdsdsMVYVx0doabaDyRLUQJUAK"

    @responses.activate
    def test_generate_waba_key_failure(self, monkeypatch):
        url = "https://hub.360dialog.io/api/v2/token"
        responses.add("POST", json={}, url=url, status=500)
        with pytest.raises(AppException, match=r"Failed to get partner auth token: *"):
            BSP360Dialog.generate_waba_key("skds23Ga")

        def _get_partners_auth_token(*args, **kwargs):
            return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

        monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], "partner_id", 'f167CmPA')
        url = "https://hub.360dialog.io/api/v2/partners/f167CmPA/channels/skds23Ga/api_keys"
        response_data = {
            "meta": {
                "success": False,
                "http_code": 404,
                "developer_message": "Some error"
            }
        }
        responses.add("POST", json=response_data, url=url, status=404)

        actual_resp = BSP360Dialog.generate_waba_key("skds23Ga")
        assert actual_resp is None

    def test_save_channel_config_without_channels(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328f5"
        user = "test_user"
        clientId = "kairon"
        client = "skds23Ga"
        channels = []
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], 'partner_id', "test_id")

        with pytest.raises(AppException, match=r"Failed to save channel config, onboarding unsuccessful!"):
            BSP360Dialog(bot, user).save_channel_config(clientId, client, channels)

    def test_save_channel_config_bsp_disabled(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328f5"
        user = "test_user"
        clientId = "kairon"
        client = "skds23Ga"
        channels = ['dfghjkl']

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        def _generate_waba_key(*args, **kwargs):
            return "kHCwksdsdsMVYVx0doabaDyRLUQJUAK"

        def _get_waba_account_id(*args, **kwargs):
            return "Cyih7GWA"

        monkeypatch.setitem(Utility.environment['model']['agent'], 'url', "http://kairon-api.digite.com")
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], 'partner_id', "test_id")
        monkeypatch.setattr(Authentication, 'generate_integration_token', _get_integration_token)
        monkeypatch.setattr(BSP360Dialog, 'generate_waba_key', _generate_waba_key)
        monkeypatch.setattr(BSP360Dialog, 'get_account', _get_waba_account_id)

        with pytest.raises(ValidationError, match="Feature disabled for this account. Please contact support!"):
            BSP360Dialog(bot, user).save_channel_config(clientId, client, channels)

    def test_save_channel_config(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328f5"
        user = "test_user"
        clientId = "kairon"
        client = "skds23Ga"
        channels = ['dfghjkl']

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        def _generate_waba_key(*args, **kwargs):
            return "kHCwksdsdsMVYVx0doabaDyRLUQJUAK"

        def _get_waba_account_id(*args, **kwargs):
            return "Cyih7GWA"

        def _mock_get_bot_settings(*args, **kwargs):
            return BotSettings(whatsapp="360dialog", bot=bot, user=user)

        monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
        monkeypatch.setitem(Utility.environment['model']['agent'], 'url', "http://kairon-api.digite.com")
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], 'partner_id', "test_id")
        monkeypatch.setattr(Authentication, 'generate_integration_token', _get_integration_token)
        monkeypatch.setattr(BSP360Dialog, 'generate_waba_key', _generate_waba_key)
        monkeypatch.setattr(BSP360Dialog, 'get_account', _get_waba_account_id)

        endpoint = BSP360Dialog(bot, user).save_channel_config(clientId, client, channels)
        assert endpoint == 'http://kairon-api.digite.com/api/bot/whatsapp/62bc24b493a0d6b7a46328f5/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY'
        config = ChatDataProcessor.get_channel_config("whatsapp", bot, mask_characters=False)
        assert config['config'] == {'client_name': 'kairon', 'client_id': 'skds23Ga', 'channel_id': 'dfghjkl',
                                    'partner_id': 'test_id', 'bsp_type': '360dialog',
                                    'api_key': 'kHCwksdsdsMVYVx0doabaDyRLUQJUAK', 'waba_account_id': 'Cyih7GWA'}

    def test_save_channel_config_with_partner_id(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328ff"
        user = "test_user"
        clientId = "kairon"
        client = "skds23Ga"
        channels = ['dfghjkl']
        partner_id = "new_partner_id"

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        def _generate_waba_key(*args, **kwargs):
            return "kHCwksdsdsMVYVx0doabaDyRLUQJUAK"

        def _get_waba_account_id(*args, **kwargs):
            return "Cyih7GWA"

        def _mock_get_bot_settings(*args, **kwargs):
            return BotSettings(whatsapp="360dialog")

        monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
        monkeypatch.setitem(Utility.environment['model']['agent'], 'url', "http://kairon-api.digite.com")
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], 'partner_id', "test_id")
        monkeypatch.setattr(Authentication, 'generate_integration_token', _get_integration_token)
        monkeypatch.setattr(BSP360Dialog, 'generate_waba_key', _generate_waba_key)
        monkeypatch.setattr(BSP360Dialog, 'get_account', _get_waba_account_id)

        endpoint = BSP360Dialog(bot, user).save_channel_config(clientId, client, channels, partner_id)
        assert endpoint == 'http://kairon-api.digite.com/api/bot/whatsapp/62bc24b493a0d6b7a46328ff/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY'
        config = ChatDataProcessor.get_channel_config("whatsapp", bot, mask_characters=False)
        assert config['config'] == {'client_name': 'kairon', 'client_id': 'skds23Ga', 'channel_id': 'dfghjkl',
                                    'partner_id': partner_id, 'bsp_type': '360dialog',
                                    'api_key': 'kHCwksdsdsMVYVx0doabaDyRLUQJUAK', 'waba_account_id': 'Cyih7GWA'}

    def test_save_channel_config_with_string_list_channel_ids(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328ff"
        user = "test_user"
        clientId = "kairon"
        client = "skds23Ga"
        channels = "[dfghjkl,afghlml,sfghlkl]"
        partner_id = "new_partner_id"

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        def _generate_waba_key(*args, **kwargs):
            return "kHCwksdsdsMVYVx0doabaDyRLUQJUAK"

        def _get_waba_account_id(*args, **kwargs):
            return "Cyih7GWA"

        def _mock_get_bot_settings(*args, **kwargs):
            return BotSettings(whatsapp="360dialog")

        monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
        monkeypatch.setitem(Utility.environment['model']['agent'], 'url', "http://kairon-api.digite.com")
        monkeypatch.setitem(Utility.environment["channels"]["360dialog"], 'partner_id', "test_id")
        monkeypatch.setattr(Authentication, 'generate_integration_token', _get_integration_token)
        monkeypatch.setattr(BSP360Dialog, 'generate_waba_key', _generate_waba_key)
        monkeypatch.setattr(BSP360Dialog, 'get_account', _get_waba_account_id)

        endpoint = BSP360Dialog(bot, user).save_channel_config(clientId, client, channels, partner_id)
        assert endpoint == 'http://kairon-api.digite.com/api/bot/whatsapp/62bc24b493a0d6b7a46328ff/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY'
        config = ChatDataProcessor.get_channel_config("whatsapp", bot, mask_characters=False)
        assert config['config'] == {'client_name': 'kairon', 'client_id': 'skds23Ga', 'channel_id': 'dfghjkl',
                                    'partner_id': partner_id, 'bsp_type': '360dialog',
                                    'api_key': 'kHCwksdsdsMVYVx0doabaDyRLUQJUAK', 'waba_account_id': 'Cyih7GWA'}


    @responses.activate
    def test_add_template(self, monkeypatch):
        with mock.patch.dict(Utility.environment, {'channels': {"360dialog": {"partner_id": "new_partner_id"}}}):
            responses.reset()
            bot = "62bc24b493a0d6b7a46328ff"
            data = {
                "name": "Introduction template",
                "category": "MARKETING",
                "components": [
                    {
                        "format": "TEXT",
                        "text": "New request",
                        "type": "HEADER"
                    },
                    {
                        "type": "BODY",
                        "text": "Hi {{1}}, thanks for getting in touch with {{2}}. We will process your request get back to you shortly",
                        "example": {
                            "body_text": [
                                [
                                    "Nupur",
                                    "360dialog"
                                ]
                            ]
                        }
                    },
                    {
                        "text": "WhatsApp Business API provided by 360dialog",
                        "type": "FOOTER"
                    }
                ],
                "language": "es_ES",
                "allow_category_change": True
            }
            api_resp = {
                "id": "594425479261596",
                "status": "PENDING",
                "category": "MARKETING"
            }


            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
            url = f"{base_url}/v1/configs/templates"
            responses.add("POST", json=api_resp, url=url, status=201)
            template = BSP360Dialog(bot, "test").add_template(data, bot, "test")
            assert template == {'category': 'MARKETING', 'id': '594425479261596', 'status': 'PENDING'}
            count = AuditLogData.objects(attributes=[{"key": "bot", "value": bot}], user="test", action="activity").count()
            assert count == 1

    @responses.activate
    def test_add_template_with_missing_keys(self):
        bot = "62bc24b493a0d6b7a46328ff"
        data = {
            "name": "Introduction template",
            "category": "UTILITY",
            "language": "es_ES",
            "allow_category_change": True
        }
        with pytest.raises(AppException, match="Missing components in request body!"):
            BSP360Dialog(bot, "test").add_template(data, bot, "test")

    def test_add_template_error(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328fg"
        data = {
            "name": "Introduction template",
            "category": "UTILITY",
            "components": [
                {
                    "format": "TEXT",
                    "text": "New request",
                    "type": "HEADER"
                },
                {
                    "type": "BODY",
                    "text": "Hi {{1}}, thanks for getting in touch with {{2}}. We will process your request get back to you shortly",
                    "example": {
                        "body_text": [
                            [
                                "Nupur",
                                "360dialog"
                            ]
                        ]
                    }
                },
                {
                    "text": "WhatsApp Business API provided by 360dialog",
                    "type": "FOOTER"
                }
            ],
            "language": "es_ES",
        }

        with pytest.raises(AppException, match="Channel not found!"):
            BSP360Dialog(bot, "user").add_template(data, bot, "user")

    @responses.activate
    def test_add_template_failure(self, monkeypatch):
        with mock.patch.dict(Utility.environment, {'channels': {"360dialog": {"partner_id": "new_partner_id"}}}):
            bot = "62bc24b493a0d6b7a46328ff"
            data = {
                "name": "Introduction template",
                "category": "MARKETING",
                "components": [
                    {
                        "format": "TEXT",
                        "text": "New request",
                        "type": "HEADER"
                    },
                    {
                        "type": "BODY",
                        "text": "Hi {{1}}, thanks for getting in touch with {{2}}. We will process your request get back to you shortly",
                        "example": {
                            "body_text": [
                                [
                                    "Nupur",
                                    "360dialog"
                                ]
                            ]
                        }
                    },
                    {
                        "text": "WhatsApp Business API provided by 360dialog",
                        "type": "FOOTER"
                    }
                ],
                "language": "es_ES",
                "allow_category_change": True
            }
            def _get_partners_auth_token(*args, **kwargs):
                return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

            monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)
            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
            url = f"{base_url}/v1/configs/templates"
            responses.add("POST", json={}, url=url, status=500)

            with pytest.raises(AppException, match=r"Failed to add template: *"):
                BSP360Dialog(bot, "user").add_template(data, bot, "user")

    @responses.activate
    def test_edit_template(self, monkeypatch):
        with mock.patch.dict(Utility.environment, {'channels': {"360dialog": {"partner_id": "new_partner_id"}}}):
            bot = "62bc24b493a0d6b7a46328ff"
            template_id = "test_id"
            partner_id = "new_partner_id"
            waba_account_id = "Cyih7GWA"
            data = {
                "components": [
                    {
                        "format": "TEXT",
                        "text": "New request",
                        "type": "HEADER"
                    },
                    {
                        "type": "BODY",
                        "text": "Hi {{1}}, thanks for getting in touch with {{2}}. Let us know your queries!",
                        "example": {
                            "body_text": [
                                [
                                    "Nupur",
                                    "360dialog"
                                ]
                            ]
                        }
                    },
                    {
                        "text": "WhatsApp Business API provided by 360dialog",
                        "type": "FOOTER"
                    }
                ],
                "allow_category_change": False
            }
            api_resp = {
                "success": True
            }

            def _get_partners_auth_token(*args, **kwargs):
                return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

            monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)

            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
            url = f"{base_url}/v1/partners/{partner_id}/waba_accounts/{waba_account_id}/waba_templates/{template_id}"
            responses.add("PATCH", json=api_resp, url=url)
            template = BSP360Dialog(bot, "test").edit_template(data, template_id)
            assert template == {'success': True}

    @responses.activate
    def test_edit_template_with_non_editable_keys(self):
        bot = "62bc24b493a0d6b7a46328ff"
        template_id = "test_id"
        partner_id = "new_partner_id"
        channel_id = "dfghjkl"
        data = {
            "name": "Introduction template",
            "category": "UTILITY",
            "language": "es_ES",
        }
        with pytest.raises(AppException, match='Only "components" and "allow_category_change" fields can be edited!'):
            BSP360Dialog(bot, "test").edit_template(data, template_id)

    @responses.activate
    def test_edit_template_channel_not_found(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328fg"
        template_id = "test_id"
        data = {
            "components": [
                {
                    "format": "TEXT",
                    "text": "New request",
                    "type": "HEADER"
                },
                {
                    "type": "BODY",
                    "text": "Hi {{1}}, thanks for getting in touch with {{2}}. Let us know your queries!",
                    "example": {
                        "body_text": [
                            [
                                "Nupur",
                                "360dialog"
                            ]
                        ]
                    }
                },
                {
                    "text": "WhatsApp Business API provided by 360dialog",
                    "type": "FOOTER"
                }
            ],
            "allow_category_change": False
        }

        with pytest.raises(AppException, match="Channel not found!"):
            BSP360Dialog(bot, "user").edit_template(data, template_id)

    @responses.activate
    def test_edit_template_failure(self, monkeypatch):
        with mock.patch.dict(Utility.environment, {'channels': {"360dialog": {"partner_id": "new_partner_id"}}}):
            bot = "62bc24b493a0d6b7a46328ff"
            template_id = "test_id"
            partner_id = "new_partner_id"
            waba_account_id = "Cyih7GWA"
            data = {
                "components": [
                    {
                        "format": "TEXT",
                        "text": "New request",
                        "type": "HEADER"
                    },
                    {
                        "type": "BODY",
                        "text": "Hi {{1}}, thanks for getting in touch with {{2}}. Let us know your queries!",
                        "example": {
                            "body_text": [
                                [
                                    "Nupur",
                                    "360dialog"
                                ]
                            ]
                        }
                    },
                    {
                        "text": "WhatsApp Business API provided by 360dialog",
                        "type": "FOOTER"
                    }
                ],
                "allow_category_change": True
            }

            def _get_partners_auth_token(*args, **kwargs):
                return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

            monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)
            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
            url = f"{base_url}/v1/partners/{partner_id}/waba_accounts/{waba_account_id}/waba_templates/{template_id}"
            responses.add("PATCH", json={}, url=url, status=500)

            with pytest.raises(AppException, match=r"Failed to edit template: Internal Server Error"):
                BSP360Dialog(bot, "user").edit_template(data, template_id)

    @responses.activate
    def test_delete_template(self, monkeypatch):
        with mock.patch.dict(Utility.environment, {'channels': {"360dialog": {"partner_id": "new_partner_id"}}}):
            bot = "62bc24b493a0d6b7a46328ff"
            template_name = "test_id"
            api_resp = {
                "meta": {
                    "developer_message": "template name=Introduction template was deleted",
                    "http_code": 200,
                    "success": True
                }
            }

            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
            url = f"{base_url}/v1/configs/templates/{template_name}"
            responses.add("DELETE", json=api_resp, url=url)
            template = BSP360Dialog(bot, "test").delete_template(template_name)
            assert template == {'meta': {'developer_message': 'template name=Introduction template was deleted', 'http_code': 200, 'success': True}}

    @responses.activate
    def test_delete_template_failure(self, monkeypatch):
        with mock.patch.dict(Utility.environment, {'channels': {"360dialog": {"partner_id": "new_partner_id"}}}):
            bot = "62bc24b493a0d6b7a46328ff"
            template_id = "test_id"

            def _get_partners_auth_token(*args, **kwargs):
                return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

            monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)
            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
            url = f"{base_url}/v1/configs/templates/{template_id}"
            responses.add("DELETE", json={}, url=url, status=500)

            with pytest.raises(AppException, match=r"Failed to delete template: *"):
                BSP360Dialog(bot, "user").delete_template(template_id)

    def test_delete_template_error(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328fg"
        template_id = "test_id"

        with pytest.raises(AppException, match="Channel not found!"):
            BSP360Dialog(bot, "user").delete_template(template_id)

    @responses.activate
    def test_get_template(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328ff"
        template_id = "test_id"
        partner_id = "new_partner_id"
        account_id = "Cyih7GWA"
        api_resp = {
            "count": 1,
            "filters": {},
            "limit": 50,
            "offset": 0,
            "sort": [
                "business_templates.name"
            ],
            "total": 1,
            "waba_templates": [
                {
                    "category": "MARKETING",
                    "components": [
                        {
                            "example": {
                                "body_text": [
                                    [
                                        "Peter"
                                    ]
                                ]
                            },
                            "text": "Hi {{1}},\n\nWe are thrilled to share that *kAIron* has now been integrated with WhatsApp through the *WhatsApp Business Solution Provide*r (BSP). \n\nThis integration will expand kAIron's ability to engage with a larger audience, increase sales acceleration, and provide better customer support.\n\nWith this integration, sending customized templates and broadcasting general, sales, or marketing information over WhatsApp will be much quicker and more efficient. \n\nStay tuned for more exciting updates from Team kAIron! ",
                            "type": "BODY"
                        }
                    ],
                    "id": "GVsEkeI2PIiARwVXQEDVWT",
                    "language": "en",
                    "modified_at": "2023-03-02T13:39:27Z",
                    "modified_by": {
                        "user_id": "system",
                        "user_name": "system"
                    },
                    "name": "kairon_new_features",
                    "namespace": "092819ec_f801_461b_b975_3a2d464f50a8",
                    "partner_id": "9Mg0AiPA",
                    "waba_account_id": "Cyih7GWA"
                }
            ]
        }

        def _get_partners_auth_token(*args, **kwargs):
            return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

        monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)

        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
        url = f"{base_url}/v1/configs/templates?filters=%7B%22id%22:%20%22test_id%22%7D&sort=business_templates.name"
        responses.add("GET", json=api_resp, url=url)
        template = BSP360Dialog(bot, "test").get_template(template_id)
        assert template == [{'category': 'MARKETING', 'components': [{'example': {'body_text': [['Peter']]},
                                                                      'text': "Hi {{1}},\n\nWe are thrilled to share that *kAIron* has now been integrated with WhatsApp through the *WhatsApp Business Solution Provide*r (BSP). \n\nThis integration will expand kAIron's ability to engage with a larger audience, increase sales acceleration, and provide better customer support.\n\nWith this integration, sending customized templates and broadcasting general, sales, or marketing information over WhatsApp will be much quicker and more efficient. \n\nStay tuned for more exciting updates from Team kAIron!\xa0",
                                                                      'type': 'BODY'}], 'id': 'GVsEkeI2PIiARwVXQEDVWT',
                             'language': 'en', 'modified_at': '2023-03-02T13:39:27Z',
                             'modified_by': {'user_id': 'system', 'user_name': 'system'}, 'name': 'kairon_new_features',
                             'namespace': '092819ec_f801_461b_b975_3a2d464f50a8', 'partner_id': '9Mg0AiPA',
                             'waba_account_id': 'Cyih7GWA'}]

    @responses.activate
    def test_get_template_failure(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328ff"
        template_id = "test_id"
        partner_id = "new_partner_id"
        account_id = "Cyih7GWA"

        def _get_partners_auth_token(*args, **kwargs):
            return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

        monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["waba_base_url"]
        url = f"{base_url}/v1/configs/templates?filters=%7B%22id%22:%20%22test_id%22%7D&sort=business_templates.name"
        responses.add("GET", json={}, url=url, status=500)

        with pytest.raises(AppException, match=r"Failed to get template: *"):
            BSP360Dialog(bot, "user").get_template(template_id)

    def test_get_template_error(self, monkeypatch):
        bot = "62bc24b493a0d6b7a46328fg"
        template_id = "test_id"

        with pytest.raises(AppException, match="Channel not found!"):
            BSP360Dialog(bot, "user").get_template(template_id)

    def test_post_process(self, monkeypatch):
        def _generate_waba_key(*args, **kwargs):
            return "kHCwksdsdsMVYVx0doabaDyRLUQJUAK"

        def _get_waba_account_id(*args, **kwargs):
            return "Cyih7GWA"

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        def _set_webhook_url(*args, **kwargs):
            return "https://kaironlocalchat.digite.com/api/bot/waba_partner/62bc24b493a0d6b7a46328f5/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY"

        def _mock_get_bot_settings(*args, **kwargs):
            return BotSettings(whatsapp="360dialog")

        monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
        monkeypatch.setattr(BSP360Dialog, 'generate_waba_key', _generate_waba_key)
        monkeypatch.setattr(BSP360Dialog, 'get_account', _get_waba_account_id)
        monkeypatch.setattr(BSP360Dialog, 'set_webhook_url', _set_webhook_url)
        monkeypatch.setattr(Authentication, 'generate_integration_token', _get_integration_token)
        monkeypatch.setitem(Utility.environment['model']['agent'], 'url', "http://kairon-api.digite.com")

        config = {
            "connector_type": ChannelTypes.WHATSAPP.value,
            "config": {
                "bsp_type": WhatsappBSPTypes.bsp_360dialog.value,
                "client_name": "kAIron",
                "client_id": "jno40M5NCL",
                "channel_id": "skds23Ga",
                "partner_id": "f167CmPA",
            }
        }
        url = ChatDataProcessor.save_channel_config(config, "62bc24b493a0d6b7a46328f5", "test@demo.in")
        assert url == 'http://kairon-api.digite.com/api/bot/whatsapp/62bc24b493a0d6b7a46328f5/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY'

        webhook_url = BSP360Dialog("62bc24b493a0d6b7a46328f5", "test@demo.in").post_process()
        assert webhook_url == 'http://kairon-api.digite.com/api/bot/whatsapp/62bc24b493a0d6b7a46328f5/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY'
        
    def test_post_process_bsp_disabled(self, monkeypatch):
        def _generate_waba_key(*args, **kwargs):
            return "kHCwksdsdsMVYVx0doabaDyRLUQJUAK"

        def _get_waba_account_id(*args, **kwargs):
            return "Cyih7GWA"

        def _get_integration_token(*args, **kwargs):
            return "eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY", ""

        def _set_webhook_url(*args, **kwargs):
            return "https://kaironlocalchat.digite.com/api/bot/waba_partner/62bc24b493a0d6b7a46328f5/eyJhbGciOiJIUzI1NiI.sInR5cCI6IkpXVCJ9.TXXmZ4-rMKQZMLwS104JsvsR0XPg4xBt2UcT4x4HgLY"

        monkeypatch.setattr(BSP360Dialog, 'generate_waba_key', _generate_waba_key)
        monkeypatch.setattr(BSP360Dialog, 'get_account', _get_waba_account_id)
        monkeypatch.setattr(BSP360Dialog, 'set_webhook_url', _set_webhook_url)
        monkeypatch.setattr(Authentication, 'generate_integration_token', _get_integration_token)
        monkeypatch.setitem(Utility.environment['model']['agent'], 'url', "http://kairon-api.digite.com")

        with pytest.raises(AppException, match="Feature disabled for this account. Please contact support!"):
            BSP360Dialog("62bc24b493a0d6b7a46328f5", "test@demo.in").post_process()

    @responses.activate
    def test_post_process_error(self):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        url = f"{base_url}/api/v2/token"
        responses.add("POST", json={}, url=url, status=500)
        with pytest.raises(AppException, match=r'Failed to get partner auth token: *'):
            BSP360Dialog("62bc24b493a0d6b7a46328f5", "test@demo.in").post_process()

    def test_post_process_client_config_deleted(self):
        with pytest.raises(AppException, match="Channel not found!"):
            BSP360Dialog("test_bot", "test@demo.in").post_process()

    def test_bsp_factory_error(self):
        with pytest.raises(AppException, match="bsp_type not yet implemented!"):
            BusinessServiceProviderFactory.get_instance("wati")

    def test_bsp_factory(self):
        assert isinstance(BusinessServiceProviderFactory.get_instance(WhatsappBSPTypes.bsp_360dialog.value)("test", "test"), BSP360Dialog)

    def test_parent_class_abstract_methods(self):
        with pytest.raises(Exception):
            WhatsappBusinessServiceProviderBase.get_template()

        with pytest.raises(Exception):
            WhatsappBusinessServiceProviderBase().get_account()

        with pytest.raises(Exception):
            WhatsappBusinessServiceProviderBase().save_channel_config()

        with pytest.raises(Exception):
            WhatsappBusinessServiceProviderBase().post_process()

        with pytest.raises(Exception):
            WhatsappBusinessServiceProviderBase.add_template()

        with pytest.raises(Exception):
            WhatsappBusinessServiceProviderBase.edit_template()

        with pytest.raises(Exception):
            WhatsappBusinessServiceProviderBase.delete_template()



    @pytest.mark.asyncio
    @responses.activate
    def test_get_user_media_data_with_no_data(self):
        bot = "682323a603ec3be7dcaa75bc"
        media_data = UserMedia.get_user_media_data(bot)
        assert len(media_data) == 0
        assert media_data == []
        print(media_data)
        UserMediaData.objects().delete()

    @pytest.mark.asyncio
    @responses.activate
    def test_get_user_media_data(self):
        UserMediaData(
            media_id="0196c9efbf547b81a66ba2af7b72d5ba",
            filename="whataspp_360_885215267637065.jpg",
            extension=".jpg",
            upload_status="Completed",
            upload_type="user",
            filesize=410484,
            additional_info={"description": "Issue description", "phone_number": "919876543210"},
            sender_id="mahesh.sattala@digite.com",
            bot="682323a603ec3be7dcaa75bc",
            timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
            media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
            output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        ).save()
        UserMediaData(
            media_id="0196c9efbf547b81a66ba2af7b72d5bb",
            filename="whataspp_360_885215267637065.jpg",
            extension=".jpg",
            upload_status="Completed",
            upload_type="user",
            filesize=410484,
            additional_info={"description": "Testing description", "phone_number": "919876543210"},
            sender_id="mahesh.sattala@digite.com",
            bot="682323a603ec3be7dcaa75bc",
            timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
            media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
            output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        ).save()
        UserMediaData(
            media_id="0196c9efbf547b81a66ba2af7b72d5ba",
            filename="whataspp_360_885215267637065.jpg",
            extension=".jpg",
            upload_status="Completed",
            upload_type="user",
            filesize=410484,
            additional_info={"description": "Issue description 2", "phone_number": "919876543210"},
            sender_id="mahesh.sattala@digite.com",
            bot="682323a603ec3be7dcaa75bc",
            timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
            media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
            output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        ).save()
        UserMediaData(
            media_id="0196c9efbf547b81a66ba2af7b72d5bb",
            filename="whataspp_360_885215267637065.jpg",
            extension=".jpg",
            upload_status="Failed",
            upload_type="user",
            filesize=410484,
            additional_info={"description": "Testing description 2", "phone_number": "919876543210"},
            sender_id="mahesh.sattala@digite.com",
            bot="682323a603ec3be7dcaa75bc",
            timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
            media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
            output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        ).save()
        UserMediaData(
            media_id="0196c9efbf547b81a66ba2af7b72d5ba",
            filename="whataspp_360_885215267637065.jpg",
            extension=".jpg",
            upload_status="Completed",
            upload_type="user",
            filesize=410484,
            additional_info={"description": "Issue description 3", "phone_number": "919876543210"},
            sender_id="mahesh.sattala@digite.com",
            bot="682323a603ec3be7dcaa75bc",
            timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
            media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
            output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        ).save()
        UserMediaData(
            media_id="0196c9efbf547b81a66ba2af7b72d5bb",
            filename="whataspp_360_885215267637065.jpg",
            extension=".jpg",
            upload_status="processing",
            upload_type="system",
            filesize=410484,
            additional_info={"description": "Testing description 4", "phone_number": "919876543210"},
            sender_id="mahesh.sattala@digite.com",
            bot="682323a603ec3be7dcaa75bc",
            timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
            media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
            output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        ).save()
        UserMediaData(
            media_id="0196c9efbf547b81a66ba2af7b72d5bb",
            filename="whataspp_360_885215267637065.jpg",
            extension=".jpg",
            upload_status="Completed",
            upload_type="system",
            filesize=410484,
            additional_info={"description": "Testing description 5", "phone_number": "919876543210"},
            sender_id="mahesh.sattala@digite.com",
            bot="682323a603ec3be7dcaa75bc",
            timestamp=datetime(2026, 2, 20, 5, 37, 17, 59000),
            media_url="https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
            output_filename="user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg",
        ).save()

        media_data = UserMedia.get_user_media_data("682323a603ec3be7dcaa75bc")
        assert len(media_data) == 4
        print(media_data)
        assert media_data == [
            {
                'sender_id': 'mahesh.sattala@digite.com',
                'timestamp': datetime(2026, 2, 20, 5, 37, 17, 59000),
                'media_url': 'https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg',
                'additional_info': {'description': 'Issue description', 'phone_number': '919876543210'},
            },
            {
                'sender_id': 'mahesh.sattala@digite.com',
                'timestamp': datetime(2026, 2, 20, 5, 37, 17, 59000),
                'media_url': 'https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg',
                'additional_info': {'description': 'Testing description', 'phone_number': '919876543210'},
            },
            {
                'sender_id': 'mahesh.sattala@digite.com',
                'timestamp': datetime(2026, 2, 20, 5, 37, 17, 59000),
                'media_url': 'https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg',
                'additional_info': {'description': 'Issue description 2', 'phone_number': '919876543210'},
            },
            {
                'sender_id': 'mahesh.sattala@digite.com',
                'timestamp': datetime(2026, 2, 20, 5, 37, 17, 59000),
                'media_url': 'https://uat-kairon-upload.s3.amazonaws.com/user_media/698431b7f85e2534c76f5034/919515991685_019c74a78760760fa2c08e4da2ce35c1_whataspp_360_885215267637065.jpeg',
                'additional_info': {'description': 'Issue description 3', 'phone_number': '919876543210'},
            }
        ]

        UserMediaData.objects().delete()

    @pytest.mark.asyncio
    @responses.activate
    @patch("kairon.shared.chat.user_media.UserMedia.get_media_content_buffer")
    async def test_upload_media_success(self, mock_get_buffer):
        media_id = "0196c9efbf547b81a66ba2af7b72d5ba"
        bsp_type = "360dialog"
        expected_external_media_id = "abc123"
        bot = "682323a603ec3be7dcaa75bc"

        UserMediaData(
            media_id=media_id,
            filename="Upload_Download Data.pdf",
            extension=".pdf",
            upload_status="Completed",
            upload_type="user",
            filesize=410484,
            sender_id="himanshu.gupta_@digite.com",
            bot=bot,
            timestamp=datetime.utcnow(),
            media_url="https://upload-doc-poc.s3.amazonaws.com/user_media/682323a603ec3be7dcaa75bc/himanshu.gt_digite.com_0196c9efbf547b81a66ba2af7b72d5ba_Upload_Download Data.pdf",
            output_filename="user_media/682323a603ec3be7dcaa75bc/himanshu.gupta_digite.com_0196c9efbf547b81a66ba2af7b72d5ba_Upload_Download Data.pdf",
        ).save()

        BotSettings(
            bot=bot,
            user="himanshu.gupta_@digite.com",
            whatsapp="360dialog",
            timestamp=datetime.utcnow()
        ).save()

        Channels(
            bot=bot,
            connector_type="whatsapp",
            config={
                "client_name": "dummy",
                "client_id": "dummy",
                "channel_id": "dummy",
                "api_key": "dummy_token",
                "partner_id": "dummy",
                "waba_account_id": "dummy",
                "bsp_type": "360dialog"
            },
            user="test@example.com",
            timestamp=datetime.utcnow()
        ).save()

        mock_get_buffer.return_value = (
            io.BytesIO(b"%PDF-1.4 mock content"),
            "Upload_Download Data.pdf",
            ".pdf",
        )

        responses.add(
            responses.POST,
            "https://waba-v2.360dialog.io/media",
            json={"id": expected_external_media_id},
            status=200,
            content_type="application/json"
        )

        external_media_id = await BSP360Dialog.upload_media(bot, bsp_type, media_id)

        assert external_media_id == expected_external_media_id

        updated_doc = UserMediaData.objects.get(media_id=media_id)
        assert updated_doc.external_upload_info == {
            "bsp": bsp_type,
            "external_media_id": expected_external_media_id,
            "error": ""
        }
        UserMediaData.objects().delete()
        BotSettings.objects().delete()
        Channels.objects().delete()

    @pytest.mark.asyncio
    async def test_upload_media_media_not_found(self):
        media_id = "non_existing_media_id"
        bsp_type = "360dialog"
        bot = "682323a603ec3be7dcaa75bc"

        with pytest.raises(AppException) as exc_info:
            await BSP360Dialog.upload_media(bot, bsp_type, media_id)

        assert str(exc_info.value) == f"UserMediaData not found for media_id: {media_id}"

    @pytest.mark.asyncio
    async def test_upload_media_channel_not_configured(self):
        media_id = "non_existing_media_id"
        bsp_type = "360dialog"
        bot = "682323a603ec3be7dcaa75bc"

        UserMediaData(
            media_id=media_id,
            filename="Upload_Download Data.pdf",
            extension=".pdf",
            upload_status="Completed",
            upload_type="user",
            filesize=410484,
            sender_id="himanshu.gupta_@digite.com",
            bot=bot,
            timestamp=datetime.utcnow(),
            media_url="https://upload-doc-poc.s3.amazonaws.com/user_media/682323a603ec3be7dcaa75bc/himanshu.gt_digite.com_0196c9efbf547b81a66ba2af7b72d5ba_Upload_Download Data.pdf",
            output_filename="user_media/682323a603ec3be7dcaa75bc/himanshu.gupta_digite.com_0196c9efbf547b81a66ba2af7b72d5ba_Upload_Download Data.pdf",
        ).save()

        with pytest.raises(AppException) as exc_info:
            await BSP360Dialog.upload_media(bot, bsp_type, media_id)

        assert str(
            exc_info.value) == f"Channel config not found for bot: {bot}, connector_type: whatsapp, bsp_type: {bsp_type}"
        UserMediaData.objects().delete()

    @pytest.mark.asyncio
    async def test_upload_media_access_token_not_found(self):
        media_id = "non_existing_media_id"
        bsp_type = "360dialog"
        bot = "682323a603ec3be7dcaa75bc"

        UserMediaData(
            media_id=media_id,
            filename="Upload_Download Data.pdf",
            extension=".pdf",
            upload_status="Completed",
            upload_type="user",
            filesize=410484,
            sender_id="himanshu.gupta_@digite.com",
            bot=bot,
            timestamp=datetime.utcnow(),
            media_url="https://upload-doc-poc.s3.amazonaws.com/user_media/682323a603ec3be7dcaa75bc/himanshu.gt_digite.com_0196c9efbf547b81a66ba2af7b72d5ba_Upload_Download Data.pdf",
            output_filename="user_media/682323a603ec3be7dcaa75bc/himanshu.gupta_digite.com_0196c9efbf547b81a66ba2af7b72d5ba_Upload_Download Data.pdf",
        ).save()

        BotSettings(
            bot=bot,
            user="himanshu.gupta_@digite.com",
            whatsapp="360dialog",
            timestamp=datetime.utcnow()
        ).save()

        Channels(
            bot=bot,
            connector_type="whatsapp",
            config={
                "client_name": "dummy",
                "client_id": "dummy",
                "channel_id": "dummy",
                "api_key": "",
                "partner_id": "dummy",
                "waba_account_id": "dummy",
                "bsp_type": "360dialog"
            },
            user="test@example.com",
            timestamp=datetime.utcnow()
        ).save()

        with pytest.raises(AppException) as exc_info:
            await BSP360Dialog.upload_media(bot, bsp_type, media_id)

        assert str(
            exc_info.value) == "API key (access token) not found in channel config"

        UserMediaData.objects().delete()
        BotSettings.objects().delete()
        Channels.objects().delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.chat.user_media.UserMedia.get_media_content_buffer")
    async def test_upload_media_file_stream_not_found(self, mock_get_buffer):
        media_id = "0196c9efbf547b81a66ba2af7b72d5ba"
        bsp_type = "360dialog"
        bot = "682323a603ec3be7dcaa75bc"

        UserMediaData(
            media_id=media_id,
            filename="Upload_Download Data.pdf",
            extension=".pdf",
            upload_status="Completed",
            upload_type="user",
            filesize=410484,
            sender_id="himanshu.gupta_@digite.com",
            bot=bot,
            timestamp=datetime.utcnow(),
            media_url="https://upload-doc-poc.s3.amazonaws.com/user_media/682323a603ec3be7dcaa75bc/himanshu.gt_digite.com_0196c9efbf547b81a66ba2af7b72d5ba_Upload_Download Data.pdf",
            output_filename="user_media/682323a603ec3be7dcaa75bc/himanshu.gupta_digite.com_0196c9efbf547b81a66ba2af7b72d5ba_Upload_Download Data.pdf",
        ).save()

        BotSettings(
            bot=bot,
            user="himanshu.gupta_@digite.com",
            whatsapp="360dialog",
            timestamp=datetime.utcnow()
        ).save()

        Channels(
            bot=bot,
            connector_type="whatsapp",
            config={
                "client_name": "dummy",
                "client_id": "dummy",
                "channel_id": "dummy",
                "api_key": "dummy_token",
                "partner_id": "dummy",
                "waba_account_id": "dummy",
                "bsp_type": "360dialog"
            },
            user="test@example.com",
            timestamp=datetime.utcnow()
        ).save()

        mock_get_buffer.return_value = (None, None, None)

        with pytest.raises(AppException) as exc_info:
            await BSP360Dialog.upload_media(bot, bsp_type, media_id)

        assert str(exc_info.value) == "File stream not found"

        UserMediaData.objects().delete()
        BotSettings.objects().delete()
        Channels.objects().delete()


    @pytest.mark.asyncio
    def test_get_media_ids_success(self):
        bot = "682323a603ec3be7dcaa75bc"
        Channels.objects(bot=bot).delete()
        UserMediaData.objects(bot=bot).delete()
        BotSettings.objects(bot=bot).delete()
        BotSettings(
            bot=bot,
            user="test@example.com",
            whatsapp="360dialog",
            timestamp=datetime.utcnow(),
        ).save()
        Channels(
            bot=bot,
            connector_type="whatsapp",
            config={
                "bsp_type": "360dialog",
                "client_name": "dummy",
                "client_id": "dummy",
            },
            user="test@example.com",
            timestamp=datetime.utcnow(),
        ).save()

        media_id = "0196c9efbf547b81a66ba2af7b72d5ba"
        UserMediaData(
            media_id=media_id,
            filename="sample.pdf",
            upload_status=UserMediaUploadStatus.completed.value,
            upload_type="broadcast",
            filesize=12345,
            sender_id="tester@example.com",
            bot=bot,
            extension= "image/png",
            timestamp=datetime.utcnow(),
            media_url="",
            output_filename="",
            external_upload_info={"bsp": "360dialog"},
        ).save()

        result = UserMedia.get_media_ids(bot)

        assert isinstance(result, list)
        assert result[0]["media_id"] == media_id
        assert result[0]["filename"] == "sample.pdf"
        assert result[0]["upload_status"] == UserMediaUploadStatus.completed.value
        assert result[0]["sender_id"] == "tester@example.com"
        assert abs(result[0]["timestamp"] - datetime.utcnow()) < timedelta(seconds=1)

        Channels.objects(bot=bot).delete()
        UserMediaData.objects(bot=bot).delete()

    @pytest.mark.asyncio
    def test_get_media_ids_filters_last_30_days(self):
        bot = "682323a603ec3be7dcaa75bc"

        Channels.objects(bot=bot).delete()
        UserMediaData.objects(bot=bot).delete()
        BotSettings.objects(bot=bot).delete()

        BotSettings(
            bot=bot,
            user="test@example.com",
            whatsapp="360dialog",
            timestamp=datetime.utcnow(),
        ).save()

        Channels(
            bot=bot,
            connector_type="whatsapp",
            config={
                "bsp_type": "360dialog",
                "client_name": "dummy",
                "client_id": "dummy",
            },
            user="test@example.com",
            timestamp=datetime.utcnow(),
        ).save()
        recent_timestamp = datetime.utcnow() - timedelta(days=5)
        recent_media_id = "valid123"
        UserMediaData(
            media_id=recent_media_id,
            filename="recent.pdf",
            upload_status=UserMediaUploadStatus.completed.value,
            upload_type="broadcast",
            filesize=1000,
            sender_id="tester@example.com",
            bot=bot,
            extension="image/png",
            timestamp=recent_timestamp,
            media_url="",
            output_filename="",
            external_upload_info={"bsp": "360dialog"},
        ).save()

        old_media_id = "old123"
        UserMediaData(
            media_id=old_media_id,
            filename="oldfile.pdf",
            upload_status=UserMediaUploadStatus.completed.value,
            upload_type="broadcast",
            filesize=999,
            sender_id="tester@example.com",
            bot=bot,
            extension="image/png",
            timestamp=datetime.utcnow() - timedelta(days=40),
            media_url="",
            output_filename="",
            external_upload_info={"bsp": "360dialog"},
        ).save()

        result = UserMedia.get_media_ids(bot)

        assert isinstance(result, list)
        assert len(result) == 1

        assert result[0]["media_id"] == recent_media_id
        assert result[0]["filename"] == "recent.pdf"
        assert result[0]["upload_status"] == UserMediaUploadStatus.completed.value
        assert result[0]["sender_id"] == "tester@example.com"

        assert result[0]["timestamp"] >= datetime.utcnow() - timedelta(days=30)
        Channels.objects(bot=bot).delete()
        UserMediaData.objects(bot=bot).delete()

    @pytest.mark.asyncio
    def test_get_media_ids_no_channel_config(self):
        bot = "682323a603ec3be7dcaa75bc"
        Channels.objects(bot=bot).delete()
        UserMediaData.objects(bot=bot).delete()

        result = UserMedia.get_media_ids(bot)
        assert result == []

    @pytest.mark.asyncio
    @responses.activate
    async def test_upload_media_file_success(self, tmp_path):
        bot = "682323a603ec3be7dcaa75bc"
        sender_id = "test_user"
        filename = "test.pdf"
        extension = "application/pdf"
        expected_media_id = "ext123"

        content_dir = tmp_path / "media_upload_records" / bot
        content_dir.mkdir(parents=True)
        file_path = content_dir / filename
        file_path.write_bytes(b"%PDF-1.4 dummy content")
        os.makedirs(f"media_upload_records/{bot}", exist_ok=True)
        os.replace(file_path, f"media_upload_records/{bot}/{filename}")

        Channels(
            bot=bot,
            connector_type="whatsapp",
            config={
                "client_name": "dummy",
                "client_id": "dummy",
                "channel_id": "dummy",
                "api_key": "dummy_token",
                "partner_id": "dummy",
                "waba_account_id": "dummy",
                "bsp_type": "360dialog"
            },
            user="test@example.com",
            timestamp=datetime.utcnow()
        ).save()
        responses.add(
            responses.POST,
            "https://waba-v2.360dialog.io/media",
            json={"id": expected_media_id},
            status=200,
            content_type="application/json"
        )

        channel_config = ChatDataProcessor.get_channel_config("whatsapp", bot)
        with patch("kairon.shared.chat.user_media.UserMedia.save_media_content") as mock_save, \
                patch.dict("kairon.shared.utils.Utility.environment",
                           {"storage": {"whatsapp_media": {"bucket": "dummy-bucket"}}}):
            external_id = await BSP360Dialog.upload_media_file(
                bot=bot,
                channel_config=channel_config,
                sender_id=sender_id,
                filename=filename,
                extension=extension,
                filesize=12345,
            )
            mock_save.assert_called_once()
            assert external_id == expected_media_id

    @pytest.mark.asyncio
    async def test_upload_media_file_missing_api_key(self, tmp_path):
        bot = "682323a603ec3be7dcaa75bc"
        filename = "test.pdf"
        extension = "application/pdf"
        Channels.objects(bot=bot).delete()
        Channels(
            bot=bot,
            connector_type="whatsapp",
            config={
                "client_name": "dummy",
                "client_id": "dummy",
                "channel_id": "dummy",
                "partner_id": "dummy",
                "waba_account_id": "dummy",
                "bsp_type": "360dialog"
            },
            user="test@example.com",
            timestamp=datetime.utcnow()
        ).save()

        content_dir = tmp_path / "media_upload_records" / bot
        content_dir.mkdir(parents=True)
        (content_dir / filename).write_bytes(b"%PDF dummy")
        channel = "whatsapp"
        channel_config = ChatDataProcessor.get_channel_config(channel, bot)
        with pytest.raises(AppException, match=r"API key \(access token\) not found in channel config"):
            await BSP360Dialog.upload_media_file(
                bot=bot,
                channel_config=channel_config,
                sender_id="test_user",
                filename=filename,
                extension=extension,
                filesize=123,
            )

        Channels.objects().delete()

    @pytest.mark.asyncio
    @responses.activate
    async def test_upload_media_file_non_200_response(self, tmp_path):
        from unittest.mock import patch, MagicMock
        bot = "682323a603ec3be7dcaa75bc"
        sender_id = "test_user"
        filename = "test.pdf"
        extension = "application/pdf"
        Channels.objects().delete()

        content_dir = tmp_path / "media_upload_records" / bot
        content_dir.mkdir(parents=True)
        file_path = content_dir / filename
        file_path.write_bytes(b"%PDF dummy")
        os.makedirs(f"media_upload_records/{bot}", exist_ok=True)
        os.replace(file_path, f"media_upload_records/{bot}/{filename}")

        Channels(
            bot=bot,
            connector_type="whatsapp",
            config={
                "client_name": "dummy",
                "client_id": "dummy",
                "channel_id": "dummy",
                "api_key": "dummy_token",
                "partner_id": "dummy",
                "waba_account_id": "dummy",
                "bsp_type": "360dialog"
            },
            user="test@example.com",
            timestamp=datetime.utcnow()
        ).save()

        # Mock API response with failure
        responses.add(
            responses.POST,
            "https://waba-v2.360dialog.io/media",
            json={"error": "bad request"},
            status=400,
            content_type="application/json"
        )

        channel_config = ChatDataProcessor.get_channel_config("whatsapp", bot)
        with patch("kairon.shared.chat.user_media.UserMedia.create_media_doc") as mock_create_doc, \
                patch("kairon.shared.chat.user_media.UserMedia.save_media_content") as mock_save:
            mock_doc = MagicMock()
            mock_create_doc.return_value = mock_doc
            with pytest.raises(AppException, match=r"bad request"):
                await BSP360Dialog.upload_media_file(
                    bot=bot,
                    channel_config=channel_config,
                    sender_id=sender_id,
                    filename=filename,
                    extension=extension,
                    filesize=123,
                )

            mock_doc.update.assert_any_call(
                set__upload_status=UserMediaUploadStatus.failed.value,
                set__additional_info={"message": "Upload failed"},
                set__external_upload_info__error='{"error": "bad request"}'
            )

            mock_save.assert_not_called()


def test_delete_media_success():
    from unittest.mock import patch, MagicMock
    bot = "test_bot"
    media_id = "12345"

    mock_obj = MagicMock()
    mock_obj.output_filename = "file.png"
    mock_manager = MagicMock()
    mock_manager.get.return_value = mock_obj

    with patch("kairon.shared.chat.user_media.UserMediaData.objects", mock_manager):
        with patch("kairon.shared.chat.user_media.Utility.environment", {"storage": {"whatsapp_media": {"bucket": "test-bucket"}}}):
            with patch("kairon.shared.chat.user_media.CloudUtility.delete_file") as mock_delete:
                result = UserMedia.delete_media(bot, media_id)

    mock_manager.get.assert_called_once_with(bot=bot, media_id=media_id)
    mock_delete.assert_called_once_with("test-bucket", "file.png")
    mock_obj.delete.assert_called_once()
    assert result == "Deleted successfully"


def test_delete_media_failure():
    from unittest.mock import patch, MagicMock
    bot = "test_bot"
    media_id = "12345"

    mock_manager = MagicMock()
    mock_manager.get.side_effect = Exception("DB delete failed")

    with patch("kairon.shared.chat.user_media.UserMediaData.objects", mock_manager):
        with pytest.raises(AppException) as exc_info:
            UserMedia.delete_media(bot, media_id)

    assert "Failed to delete:DB delete failed" in str(exc_info.value)

def test_delete_media_with_custom_bucket():
    from unittest.mock import patch, MagicMock

    bot = "test_bot"
    media_id = "media123"
    custom_bucket = "my-custom-bucket"
    mock_media = MagicMock()
    mock_media.output_filename = "test/path/file.jpg"
    mock_manager = MagicMock()
    mock_manager.get.return_value = mock_media

    with patch("kairon.shared.chat.user_media.UserMediaData.objects", mock_manager):
        with patch("kairon.shared.chat.user_media.Utility.environment", {"storage": {"whatsapp_media": {"bucket": "default-bucket"}}}):
            with patch("kairon.shared.chat.user_media.CloudUtility.delete_file") as mock_delete_file:
                result = UserMedia.delete_media(bot, media_id, bucket=custom_bucket)

    mock_manager.get.assert_called_once_with(bot=bot, media_id=media_id)
    mock_delete_file.assert_called_once_with(custom_bucket, "test/path/file.jpg")
    mock_media.delete.assert_called_once()
    assert result == "Deleted successfully"


def test_delete_media_file_success():
    media_id = "12345"
    channel_config = {"config": {"api_key": "dummy_api_key"}}

    with patch("kairon.shared.utils.Utility.execute_http_request") as mock_http:
        mock_http.return_value = None

        result = BSP360Dialog.delete_media_file(media_id, channel_config)

    mock_http.assert_called_once()
    assert result == "Media file deleted successfully"


def test_delete_media_file_not_exist_raises():
    media_id = "12345"
    channel_config = {"config": {"api_key": "dummy_api_key"}}

    with patch("kairon.shared.utils.Utility.execute_http_request") as mock_http:
        mock_http.side_effect = AppException("media file does not exist for this media id.")
        with pytest.raises(AppException, match="media file does not exist for this media id."):
            BSP360Dialog.delete_media_file(media_id, channel_config)

    mock_http.assert_called_once()


def test_bsp_360dialog_fetch_media_ids_success():
    bot = "bsp360_fetch_success_bot"
    UserMediaData.objects(bot=bot).delete()
    media_id = "bsp360_media_uuid_001"
    UserMediaData(
        bot=bot, media_id=media_id, filename="doc.pdf", extension=".pdf",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type=UserMediaUploadType.broadcast.value,
        sender_id="u@t.com", timestamp=datetime.utcnow(),
        external_upload_info={"bsp": "360dialog", "external_media_id": "ext_360_001"},
    ).save()
    UserMediaData(
        bot=bot, media_id="other_bsp_media", filename="img.jpg", extension=".jpg",
        upload_status=UserMediaUploadStatus.completed.value,
        upload_type=UserMediaUploadType.broadcast.value,
        sender_id="u@t.com", timestamp=datetime.utcnow(),
        external_upload_info={"bsp": "gupshup", "external_media_id": "gs_001"},
    ).save()
    result = BSP360Dialog.fetch_media_ids(bot)
    assert len(result) == 1
    assert result[0]["media_id"] == media_id
    assert result[0]["filename"] == "doc.pdf"
    UserMediaData.objects(bot=bot).delete()


def test_bsp_360dialog_fetch_media_ids_exception():
    bot = "bsp360_fetch_exc_bot"
    with patch(
        "kairon.shared.channels.whatsapp.bsp.dialog360.UserMediaData.objects",
        side_effect=Exception("db connection lost"),
    ):
        with pytest.raises(AppException) as exc_info:
            BSP360Dialog.fetch_media_ids(bot)
    assert f"Error while fetching media ids for bot '{bot}': db connection lost" in str(exc_info.value)


def test_bsp_360dialog_fetch_broadcast_media_ids_success():
    from unittest.mock import MagicMock
    bot = "bsp360_broadcast_media_bot"
    mock_doc = MagicMock()
    mock_doc.filename = "promo.pdf"
    mock_doc.media_id = "bcast_media_001"
    mock_doc.upload_status = UserMediaUploadStatus.completed.value
    mock_doc.sender_id = "sender@test.com"
    mock_doc.timestamp = datetime.utcnow()

    mock_qs = MagicMock()
    mock_qs.only.return_value = [mock_doc]

    with patch(
        "kairon.shared.channels.whatsapp.bsp.dialog360.UserMediaData.objects",
        return_value=mock_qs,
    ):
        result = BSP360Dialog.fetch_broadcast_media_ids(bot)
    assert isinstance(result, list)
    assert len(result) == 1
    assert result[0]["media_id"] == "bcast_media_001"
    assert result[0]["filename"] == "promo.pdf"
    assert result[0]["upload_status"] == UserMediaUploadStatus.completed.value


def test_bsp_360dialog_fetch_broadcast_media_ids_exception():
    bot = "bsp360_broadcast_exc_bot"
    with patch(
        "kairon.shared.channels.whatsapp.bsp.dialog360.UserMediaData.objects",
        side_effect=Exception("timeout"),
    ):
        with pytest.raises(AppException) as exc_info:
            BSP360Dialog.fetch_broadcast_media_ids(bot)
    assert f"Error while fetching media ids for bot '{bot}': timeout" in str(exc_info.value)


class TestBSPGupshup:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))

    GS_BOT = "gs_bsp_test_bot_001"
    GS_USER = "gs_bsp_test_user@test.com"

    @pytest.fixture
    def gupshup_channel(self):
        encrypted_name = Utility.encrypt_message("gs_app_name")
        Channels.objects(bot=self.GS_BOT).delete()
        BotSettings.objects(bot=self.GS_BOT).delete()
        BotSettings(
            bot=self.GS_BOT, user=self.GS_USER,
            whatsapp=WhatsappBSPTypes.bsp_gupshup.value
        ).save()
        Channels(
            bot=self.GS_BOT,
            connector_type=ChannelTypes.WHATSAPP.value,
            config={
                "client_name": encrypted_name,
                "app_id": "gs_app_001",
                "app_name": "gs_app_name",
                "partner_app_token": "gs_partner_token_xyz",
                "bsp_type": WhatsappBSPTypes.bsp_gupshup.value
            },
            user=self.GS_USER,
            timestamp=datetime.utcnow()
        ).save()
        yield
        Channels.objects(bot=self.GS_BOT).delete()
        BotSettings.objects(bot=self.GS_BOT).delete()

    # ─── validate ─────────────────────────────────────────────────────

    def test_validate_success(self, monkeypatch):
        def _get_bot_settings(*a, **kw):
            return BotSettings(whatsapp="gupshup", bot=self.GS_BOT, user=self.GS_USER)
        monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _get_bot_settings)
        BSPGupshup(self.GS_BOT, self.GS_USER).validate()

    def test_validate_bsp_disabled(self, monkeypatch):
        def _get_bot_settings(*a, **kw):
            return BotSettings(whatsapp="360dialog", bot=self.GS_BOT, user=self.GS_USER)
        monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _get_bot_settings)
        with pytest.raises(AppException, match="Feature disabled for this account"):
            BSPGupshup(self.GS_BOT, self.GS_USER).validate()

    # ─── get_account ──────────────────────────────────────────────────

    def test_get_account_returns_app_id(self):
        assert BSPGupshup(self.GS_BOT, self.GS_USER).get_account("my_app_001") == "my_app_001"

    # ─── save_channel_config ──────────────────────────────────────────

    def test_save_channel_config_success(self, monkeypatch):
        captured = {}

        def _save_channel_config(conf, bot, user):
            captured['conf'] = conf
            return "http://kairon-api.kairon.com/api/bot/whatsapp/gs_bsp_test_bot_001/token"

        monkeypatch.setattr(ChatDataProcessor, 'save_channel_config', _save_channel_config)
        BSPGupshup(self.GS_BOT, self.GS_USER).save_channel_config(
            app_id="app_001", app_name="MyApp", partner_app_token="tok_abc"
        )
        assert captured['conf']['config']['app_id'] == 'app_001'
        assert captured['conf']['config']['bsp_type'] == WhatsappBSPTypes.bsp_gupshup.value
        assert captured['conf']['config']['partner_app_token'] == 'tok_abc'
        assert captured['conf']['connector_type'] == ChannelTypes.WHATSAPP.value

    def test_save_channel_config_defaults_app_name_to_app_id(self, monkeypatch):
        captured = {}

        def _save_channel_config(conf, bot, user):
            captured['conf'] = conf
            return "url"

        monkeypatch.setattr(ChatDataProcessor, 'save_channel_config', _save_channel_config)
        BSPGupshup(self.GS_BOT, self.GS_USER).save_channel_config(
            app_id="app_002", partner_app_token="tok_xyz"
        )
        assert captured['conf']['config']['app_name'] == 'app_002'

    def test_save_channel_config_missing_app_id(self):
        with pytest.raises(AppException, match="app_id is required"):
            BSPGupshup(self.GS_BOT, self.GS_USER).save_channel_config(partner_app_token="tok")

    def test_save_channel_config_missing_partner_app_token(self):
        with pytest.raises(AppException, match="partner_app_token is required"):
            BSPGupshup(self.GS_BOT, self.GS_USER).save_channel_config(app_id="app_001")

    # ─── validate_template_request ────────────────────────────────────

    def test_validate_template_request_text_success(self):
        data = {
            "elementName": "tmpl1", "content": "Hello!", "category": "UTILITY",
            "vertical": "Tech", "templateType": "TEXT", "example": "Hello!"
        }
        BSPGupshup(self.GS_BOT, self.GS_USER).validate_template_request(data)

    def test_validate_template_request_text_header_with_variable_and_example_header(self):
        data = {
            "elementName": "t1", "content": "Hi", "category": "UTILITY",
            "vertical": "Tech", "templateType": "TEXT", "example": "Hi",
            "header": "Hello {{1}}", "exampleHeader": "Hello John"
        }
        BSPGupshup(self.GS_BOT, self.GS_USER).validate_template_request(data)

    def test_validate_template_request_image_with_example_media(self):
        data = {
            "elementName": "t2", "content": "See image", "category": "MARKETING",
            "vertical": "Retail", "templateType": "IMAGE", "example": "sample",
            "exampleMedia": "handle_123"
        }
        BSPGupshup(self.GS_BOT, self.GS_USER).validate_template_request(data)

    def test_validate_template_request_missing_keys(self):
        data = {"elementName": "t1", "category": "UTILITY"}
        with pytest.raises(AppException, match="Missing"):
            BSPGupshup(self.GS_BOT, self.GS_USER).validate_template_request(data)

    def test_validate_template_request_image_missing_example_media(self):
        data = {
            "elementName": "t2", "content": "See image", "category": "MARKETING",
            "vertical": "Retail", "templateType": "IMAGE", "example": "sample"
        }
        with pytest.raises(AppException, match="exampleMedia"):
            BSPGupshup(self.GS_BOT, self.GS_USER).validate_template_request(data)

    def test_validate_template_request_text_header_variable_missing_example_header(self):
        data = {
            "elementName": "t3", "content": "Hi", "category": "UTILITY",
            "vertical": "Tech", "templateType": "TEXT", "example": "Hi",
            "header": "Hello {{1}}"
        }
        with pytest.raises(AppException, match="exampleHeader is required"):
            BSPGupshup(self.GS_BOT, self.GS_USER).validate_template_request(data)

    def test_validate_template_request_text_header_no_variable_ok(self):
        data = {
            "elementName": "t4", "content": "Hi", "category": "UTILITY",
            "vertical": "Tech", "templateType": "TEXT", "example": "Hi",
            "header": "Hello World"
        }
        BSPGupshup(self.GS_BOT, self.GS_USER).validate_template_request(data)

    def test_validate_template_request_invalid_type(self):
        data = {
            "elementName": "t5", "content": "Hi", "category": "UTILITY",
            "vertical": "Tech", "templateType": "AUDIO", "example": "sample"
        }
        with pytest.raises(AppException, match="Invalid templateType"):
            BSPGupshup(self.GS_BOT, self.GS_USER).validate_template_request(data)

    # ─── add_template ─────────────────────────────────────────────────

    @responses.activate
    def test_add_template_success(self, gupshup_channel):
        data = {
            "elementName": "promo_tmpl", "content": "Hello {{1}}!", "category": "MARKETING",
            "vertical": "Retail", "templateType": "TEXT", "example": "Hello John!", "buttons": []
        }
        api_resp = {"id": "gs_tmpl_001", "status": "PENDING"}
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        responses.add("POST", url=f"{base_url}/partner/app/gs_app_001/templates", json=api_resp, status=201)
        result = BSPGupshup(self.GS_BOT, self.GS_USER).add_template(data, self.GS_BOT, self.GS_USER)
        assert result == api_resp

    @responses.activate
    def test_add_template_api_failure(self, gupshup_channel):
        data = {
            "elementName": "promo_tmpl", "content": "Hello!", "category": "MARKETING",
            "vertical": "Retail", "templateType": "TEXT", "example": "Hello!", "buttons": []
        }
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        responses.add("POST", url=f"{base_url}/partner/app/gs_app_001/templates",
                      json={"error": "bad request"}, status=400)
        with pytest.raises(AppException, match="Failed to add gupshup template"):
            BSPGupshup(self.GS_BOT, self.GS_USER).add_template(data, self.GS_BOT, self.GS_USER)

    def test_add_template_channel_not_found(self):
        data = {
            "elementName": "t1", "content": "Hi", "category": "UTILITY",
            "vertical": "Tech", "templateType": "TEXT", "example": "Hi", "buttons": []
        }
        with pytest.raises(AppException, match="Channel not found!"):
            BSPGupshup("no_such_bot_gs_xyz", self.GS_USER).add_template(data, "no_such_bot_gs_xyz", self.GS_USER)

    def test_add_template_missing_required_keys(self, gupshup_channel):
        data = {"elementName": "t1", "category": "UTILITY"}
        with pytest.raises(AppException, match="Missing"):
            BSPGupshup(self.GS_BOT, self.GS_USER).add_template(data, self.GS_BOT, self.GS_USER)

    # ─── edit_template ────────────────────────────────────────────────

    @responses.activate
    def test_edit_template_success(self, gupshup_channel):
        template_id = "gs_tmpl_edit_001"
        data = {"content": "Updated content {{1}}"}
        api_resp = {"id": template_id, "status": "APPROVED"}
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        responses.add("PUT", url=f"{base_url}/partner/app/gs_app_001/templates/{template_id}",
                      json=api_resp, status=200)
        result = BSPGupshup(self.GS_BOT, self.GS_USER).edit_template(data, template_id)
        assert result == api_resp

    @responses.activate
    def test_edit_template_api_failure(self, gupshup_channel):
        template_id = "gs_tmpl_edit_002"
        data = {"content": "Updated content"}
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        responses.add("PUT", url=f"{base_url}/partner/app/gs_app_001/templates/{template_id}",
                      json={"error": "not allowed"}, status=403)
        with pytest.raises(AppException, match="Failed to edit gupshup template"):
            BSPGupshup(self.GS_BOT, self.GS_USER).edit_template(data, template_id)

    def test_edit_template_channel_not_found(self):
        with pytest.raises(AppException, match="Channel not found!"):
            BSPGupshup("no_such_bot_gs_xyz", self.GS_USER).edit_template({"content": "x"}, "tmpl_id")

    # ─── delete_template ──────────────────────────────────────────────

    @responses.activate
    def test_delete_template_success(self, gupshup_channel):
        template_name = "promo_tmpl_del"
        api_resp = {"success": True}
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        responses.add("DELETE", url=f"{base_url}/partner/app/gs_app_001/template/{template_name}",
                      json=api_resp, status=200)
        result = BSPGupshup(self.GS_BOT, self.GS_USER).delete_template(template_name)
        assert result == api_resp

    @responses.activate
    def test_delete_template_api_failure(self, gupshup_channel):
        template_name = "bad_tmpl"
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        responses.add("DELETE", url=f"{base_url}/partner/app/gs_app_001/template/{template_name}",
                      json={"error": "not found"}, status=404)
        with pytest.raises(AppException, match="Failed to delete gupshup template"):
            BSPGupshup(self.GS_BOT, self.GS_USER).delete_template(template_name)

    def test_delete_template_channel_not_found(self):
        with pytest.raises(AppException, match="Channel not found!"):
            BSPGupshup("no_such_bot_gs_xyz", self.GS_USER).delete_template("some_tmpl")

    # ─── list_templates ───────────────────────────────────────────────

    @responses.activate
    def test_list_templates_returns_waba_templates(self, gupshup_channel):
        api_resp = {"waba_templates": [{"id": "t1", "elementName": "promo"}]}
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        responses.add("GET", url=f"{base_url}/partner/app/gs_app_001/templates",
                      json=api_resp, status=200)
        result = BSPGupshup(self.GS_BOT, self.GS_USER).list_templates()
        assert result == [{"id": "t1", "elementName": "promo"}]

    @responses.activate
    def test_list_templates_returns_templates_key_fallback(self, gupshup_channel):
        api_resp = {"templates": [{"id": "t2", "elementName": "info"}]}
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        responses.add("GET", url=f"{base_url}/partner/app/gs_app_001/templates",
                      json=api_resp, status=200)
        result = BSPGupshup(self.GS_BOT, self.GS_USER).list_templates()
        assert result == [{"id": "t2", "elementName": "info"}]

    @responses.activate
    def test_list_templates_empty_response(self, gupshup_channel):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        responses.add("GET", url=f"{base_url}/partner/app/gs_app_001/templates",
                      json={}, status=200)
        result = BSPGupshup(self.GS_BOT, self.GS_USER).list_templates()
        assert result == []

    def test_list_templates_channel_not_found(self):
        with pytest.raises(AppException, match="Channel not found!"):
            BSPGupshup("no_such_bot_gs_xyz", self.GS_USER).list_templates()

    # ─── get_template ─────────────────────────────────────────────────

    @responses.activate
    def test_get_template_delegates_to_list_templates(self, gupshup_channel):
        template_id = "tmpl_specific_001"
        api_resp = {"waba_templates": [{"id": template_id, "status": "APPROVED"}]}
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        responses.add("GET", url=f"{base_url}/partner/app/gs_app_001/templates",
                      json=api_resp, status=200)
        result = BSPGupshup(self.GS_BOT, self.GS_USER).get_template(template_id)
        assert {"id": template_id, "status": "APPROVED"} in result

    # ─── __get_partner_token ──────────────────────────────────────────

    @responses.activate
    def test_get_partner_token_success(self, monkeypatch):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        monkeypatch.setitem(Utility.system_metadata["channels"], "gupshup",
                            {"partner_email": "gs@test.io", "partner_password": "gs_pass"})
        responses.add("POST", url=f"{base_url}/partner/account/login",
                      json={"token": "partner_tok_abc"}, status=200)
        token = BSPGupshup._BSPGupshup__get_partner_token(base_url)
        assert token == "partner_tok_abc"

    @responses.activate
    def test_get_partner_token_login_non_200(self, monkeypatch):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        monkeypatch.setitem(Utility.system_metadata["channels"], "gupshup",
                            {"partner_email": "gs@test.io", "partner_password": "bad_pass"})
        responses.add("POST", url=f"{base_url}/partner/account/login",
                      json={"error": "invalid credentials"}, status=401)
        with pytest.raises(AppException, match="Gupshup partner login failed"):
            BSPGupshup._BSPGupshup__get_partner_token(base_url)

    @responses.activate
    def test_get_partner_token_no_token_in_response(self, monkeypatch):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        monkeypatch.setitem(Utility.system_metadata["channels"], "gupshup",
                            {"partner_email": "gs@test.io", "partner_password": "gs_pass"})
        responses.add("POST", url=f"{base_url}/partner/account/login",
                      json={"message": "ok"}, status=200)
        with pytest.raises(AppException, match="returned no token"):
            BSPGupshup._BSPGupshup__get_partner_token(base_url)

    def test_get_partner_token_missing_credentials(self, monkeypatch):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        monkeypatch.setitem(Utility.system_metadata["channels"], "gupshup",
                            {"partner_email": "", "partner_password": ""})
        with pytest.raises(AppException, match="partner_email / partner_password not configured"):
            BSPGupshup._BSPGupshup__get_partner_token(base_url)

    # ─── post_process ─────────────────────────────────────────────────

    @responses.activate
    def test_post_process_success(self, monkeypatch, gupshup_channel):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        monkeypatch.setitem(Utility.system_metadata["channels"], "gupshup",
                            {"partner_email": "gs@test.io", "partner_password": "gs_pass"})
        monkeypatch.setitem(Utility.environment['model']['agent'], 'url', "http://kairon-api.kairon.com/")
        responses.add("POST", url=f"{base_url}/partner/account/login",
                      json={"token": "partner_tok_xyz"}, status=200)
        webhook_url = f"http://kairon-api.kairon.com/api/bot/whatsapp/{self.GS_BOT}/token"
        with patch("kairon.shared.chat.processor.ChatDataProcessor.save_channel_config",
                   return_value=webhook_url) as mock_save, \
             patch("kairon.shared.utils.Utility.execute_http_request") as mock_http:
            mock_http.return_value = {"success": True}
            result = BSPGupshup(self.GS_BOT, self.GS_USER).post_process()
        assert result == webhook_url
        assert "whatsapp" in result

    def test_post_process_channel_not_found(self):
        with pytest.raises(AppException):
            BSPGupshup("no_such_bot_gs_xyz", self.GS_USER).post_process()

    # ─── get_template_for_broadcast ───────────────────────────────────

    @responses.activate
    def test_get_template_for_broadcast_found(self, gupshup_channel):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        api_resp = {"waba_templates": [{"id": "promo_tmpl", "language": "en", "status": "APPROVED"}]}
        responses.add("GET", url=f"{base_url}/partner/app/gs_app_001/templates",
                      json=api_resp, status=200)
        template, exc = BSPGupshup(self.GS_BOT, self.GS_USER).get_template_for_broadcast("promo_tmpl", "en")
        assert template == {"id": "promo_tmpl", "language": "en", "status": "APPROVED"}
        assert exc is None

    @responses.activate
    def test_get_template_for_broadcast_not_found(self, gupshup_channel):
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        api_resp = {"waba_templates": [{"id": "other_tmpl", "language": "en"}]}
        responses.add("GET", url=f"{base_url}/partner/app/gs_app_001/templates",
                      json=api_resp, status=200)
        template, exc = BSPGupshup(self.GS_BOT, self.GS_USER).get_template_for_broadcast("promo_tmpl", "en")
        assert template == {}
        assert exc is None

    def test_get_template_for_broadcast_list_error(self, gupshup_channel):
        with patch.object(BSPGupshup, 'list_templates', side_effect=Exception("API down")):
            template, exc = BSPGupshup(self.GS_BOT, self.GS_USER).get_template_for_broadcast("promo_tmpl", "en")
        assert template == {}
        assert exc is not None

    @responses.activate
    def test_get_template_for_broadcast_found_by_element_name(self, gupshup_channel):
        """elementName field is the primary match key; id may differ."""
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        api_resp = {"waba_templates": [
            {"id": "internal_uuid_xyz", "elementName": "promo_tmpl", "language": "en", "status": "APPROVED"}
        ]}
        responses.add("GET", url=f"{base_url}/partner/app/gs_app_001/templates",
                      json=api_resp, status=200)
        template, exc = BSPGupshup(self.GS_BOT, self.GS_USER).get_template_for_broadcast("promo_tmpl", "en")
        assert template["elementName"] == "promo_tmpl"
        assert template["id"] == "internal_uuid_xyz"
        assert exc is None

    @responses.activate
    def test_get_template_for_broadcast_element_name_miss_falls_back_to_id(self, gupshup_channel):
        """When elementName doesn't match, id is the fallback lookup key."""
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]
        api_resp = {"waba_templates": [
            {"id": "promo_tmpl", "elementName": "different_name", "language": "en", "status": "APPROVED"}
        ]}
        responses.add("GET", url=f"{base_url}/partner/app/gs_app_001/templates",
                      json=api_resp, status=200)
        template, exc = BSPGupshup(self.GS_BOT, self.GS_USER).get_template_for_broadcast("promo_tmpl", "en")
        assert template["id"] == "promo_tmpl"
        assert exc is None

    # ─── to_log_template ──────────────────────────────────────────────

    def test_to_log_template_text_with_header_body_footer(self):
        import json as _json
        raw = {
            "templateType": "TEXT",
            "containerMeta": _json.dumps({
                "header": "Hello Header", "data": "Body text {{1}}", "footer": "Footer text"
            })
        }
        result = BSPGupshup(self.GS_BOT, self.GS_USER).to_log_template(raw)
        types = [c["type"] for c in result]
        assert "HEADER" in types and "BODY" in types and "FOOTER" in types

    def test_to_log_template_image_header(self):
        import json as _json
        raw = {"templateType": "IMAGE", "containerMeta": _json.dumps({"data": "Caption"})}
        result = BSPGupshup(self.GS_BOT, self.GS_USER).to_log_template(raw)
        assert result[0] == {"type": "HEADER", "format": "IMAGE"}

    def test_to_log_template_video_header(self):
        import json as _json
        raw = {"templateType": "VIDEO", "containerMeta": _json.dumps({})}
        result = BSPGupshup(self.GS_BOT, self.GS_USER).to_log_template(raw)
        assert result[0] == {"type": "HEADER", "format": "VIDEO"}

    def test_to_log_template_document_header(self):
        import json as _json
        raw = {"templateType": "DOCUMENT", "containerMeta": _json.dumps({})}
        result = BSPGupshup(self.GS_BOT, self.GS_USER).to_log_template(raw)
        assert result[0] == {"type": "HEADER", "format": "DOCUMENT"}

    def test_to_log_template_with_buttons(self):
        import json as _json
        raw = {
            "templateType": "TEXT",
            "containerMeta": _json.dumps({
                "data": "Hello",
                "buttons": [{"type": "QUICK_REPLY", "text": "Yes"}, {"type": "QUICK_REPLY", "text": "No"}]
            })
        }
        result = BSPGupshup(self.GS_BOT, self.GS_USER).to_log_template(raw)
        assert any(c["type"] == "BUTTONS" for c in result)

    def test_to_log_template_not_a_dict(self):
        result = BSPGupshup(self.GS_BOT, self.GS_USER).to_log_template("not a dict")
        assert result == []

    def test_to_log_template_invalid_container_meta_json(self):
        raw = {"templateType": "TEXT", "containerMeta": "not-json"}
        result = BSPGupshup(self.GS_BOT, self.GS_USER).to_log_template(raw)
        assert isinstance(result, list)

    # ─── _resolve_runtime_params ──────────────────────────────────────

    def test_resolve_runtime_params_dict_data(self):
        import json as _json
        template_config = {"data": _json.dumps({"1": "John", "2": "Acme Corp"})}
        body_params, media_id = BSPGupshup._resolve_runtime_params(template_config, {})
        assert body_params == ["John", "Acme Corp"]
        assert media_id is None

    def test_resolve_runtime_params_components_list(self):
        import json as _json
        components = [
            {"type": "body", "parameters": [{"type": "text", "text": "Alice"}, {"type": "text", "text": "Corp"}]}
        ]
        template_config = {"data": _json.dumps([components])}
        body_params, media_id = BSPGupshup._resolve_runtime_params(template_config, {})
        assert "Alice" in body_params and "Corp" in body_params

    def test_resolve_runtime_params_falls_back_to_sample_text(self):
        template_config = {"data": "[]"}
        container_meta = {
            "data": "Hi {{1}}, welcome to {{2}}!",
            "sampleText": "Hi John, welcome to Acme!"
        }
        body_params, media_id = BSPGupshup._resolve_runtime_params(template_config, container_meta)
        assert len(body_params) == 2

    def test_resolve_runtime_params_falls_back_to_sample_media(self):
        template_config = {"data": "[]"}
        container_meta = {"sampleMedia": "handle_media_001"}
        body_params, media_id = BSPGupshup._resolve_runtime_params(template_config, container_meta)
        assert media_id == "handle_media_001"

    # ─── _extract_components_params ───────────────────────────────────

    def test_extract_components_params_body_text_and_image_header(self):
        components = [
            {"type": "body", "parameters": [{"type": "text", "text": "Alice"}]},
            {"type": "header", "parameters": [{"type": "image", "image": {"id": "img_handle_001"}}]}
        ]
        body_params, media_id = BSPGupshup._extract_components_params(components)
        assert body_params == ["Alice"]
        assert media_id == "img_handle_001"

    def test_extract_components_params_video_header(self):
        components = [
            {"type": "header", "parameters": [{"type": "video", "video": {"id": "vid_handle_001"}}]}
        ]
        body_params, media_id = BSPGupshup._extract_components_params(components)
        assert media_id == "vid_handle_001"

    def test_extract_components_params_empty(self):
        body_params, media_id = BSPGupshup._extract_components_params([])
        assert body_params == [] and media_id is None

    # ─── _extract_sample_text_params ──────────────────────────────────

    def test_extract_sample_text_params_two_placeholders(self):
        container_meta = {
            "data": "Hi {{1}}, your order {{2}} is confirmed.",
            "sampleText": "Hi John, your order ORD123 is confirmed."
        }
        result = BSPGupshup._extract_sample_text_params(container_meta)
        assert len(result) == 2

    def test_extract_sample_text_params_no_placeholders(self):
        container_meta = {"data": "Hello World!", "sampleText": "Hello World!"}
        result = BSPGupshup._extract_sample_text_params(container_meta)
        assert result == []

    def test_extract_sample_text_params_empty_sample_text(self):
        container_meta = {"data": "Hello {{1}}!", "sampleText": ""}
        result = BSPGupshup._extract_sample_text_params(container_meta)
        assert result == []

    # ─── _build_template_payload ──────────────────────────────────────

    def test_build_template_payload_text_substitutes_params(self):
        components = BSPGupshup._build_template_payload(
            "tmpl_001", ["John", "Acme"], None, "TEXT", {"data": "Hi {{1}} from {{2}}!"}
        )
        body = next(c for c in components if c["type"] == "body")
        texts = [p["text"] for p in body["parameters"]]
        assert texts == ["John", "Acme"]

    def test_build_template_payload_image_with_media(self):
        components = BSPGupshup._build_template_payload(
            "tmpl_002", [], "img_handle_001", "IMAGE", {}
        )
        header = next(c for c in components if c["type"] == "header")
        assert header["parameters"][0]["type"] == "image"
        assert header["parameters"][0]["image"]["id"] == "img_handle_001"

    def test_build_template_payload_video_with_media(self):
        components = BSPGupshup._build_template_payload(
            "tmpl_003", [], "vid_handle_001", "VIDEO", {}
        )
        header = next(c for c in components if c["type"] == "header")
        assert header["parameters"][0]["type"] == "video"
        assert header["parameters"][0]["video"]["id"] == "vid_handle_001"

    def test_build_template_payload_document_with_media(self):
        components = BSPGupshup._build_template_payload(
            "tmpl_004", [], "doc_handle_001", "DOCUMENT", {}
        )
        header = next(c for c in components if c["type"] == "header")
        assert header["parameters"][0]["type"] == "document"
        assert header["parameters"][0]["document"]["id"] == "doc_handle_001"

    def test_build_template_payload_text_no_params(self):
        components = BSPGupshup._build_template_payload(
            "tmpl_005", [], None, "TEXT", {"data": "Hello World!"}
        )
        assert components == []

    # ─── get_broadcast_template_params ────────────────────────────────

    def test_get_broadcast_template_params_text_with_sample_text(self):
        import json as _json
        raw_template = {
            "id": "bc_tmpl_001", "templateType": "TEXT",
            "containerMeta": _json.dumps({
                "data": "Hi {{1}}, your code is {{2}}.",
                "sampleText": "Hi John, your code is ABC123."
            })
        }
        template_config = {"template_id": "bc_tmpl_001", "data": "[]"}
        components = BSPGupshup(self.GS_BOT, self.GS_USER).get_broadcast_template_params(
            raw_template, template_config)
        body = next((c for c in components if c["type"] == "body"), None)
        assert body is not None
        assert all(p["type"] == "text" for p in body["parameters"])

    def test_get_broadcast_template_params_image_uses_sample_media(self):
        import json as _json
        raw_template = {
            "id": "bc_tmpl_002", "templateType": "IMAGE",
            "containerMeta": _json.dumps({"data": "Check image", "sampleMedia": "img_handle_bc"})
        }
        template_config = {"template_id": "bc_tmpl_002", "data": "[]"}
        components = BSPGupshup(self.GS_BOT, self.GS_USER).get_broadcast_template_params(
            raw_template, template_config)
        header = next(c for c in components if c["type"] == "header")
        assert header["parameters"][0]["type"] == "image"
        assert header["parameters"][0]["image"]["id"] == "img_handle_bc"

    def test_get_broadcast_template_params_non_dict_raw_template(self):
        template_config = {"template_id": "bc_tmpl_003", "data": "[]"}
        components = BSPGupshup(self.GS_BOT, self.GS_USER).get_broadcast_template_params(
            None, template_config)
        assert isinstance(components, list)

    def test_get_broadcast_template_params_list_of_list_passthrough_includes_button(self):
        """data = [[body, button]] is returned as-is; button component must survive."""
        import json as _json
        body = {"type": "body", "parameters": [{"type": "text", "text": "John"}]}
        button = {"type": "button", "sub_type": "url", "index": "0",
                  "parameters": [{"type": "text", "text": "ORD123"}]}
        template_config = {"template_id": "bt_001", "data": _json.dumps([[body, button]])}
        raw_template = {"id": "bt_001", "templateType": "TEXT", "containerMeta": "{}"}
        components = BSPGupshup(self.GS_BOT, self.GS_USER).get_broadcast_template_params(
            raw_template, template_config)
        assert components == [body, button]
        types = [c["type"] for c in components]
        assert "button" in types
        assert "body" in types

    def test_get_broadcast_template_params_flat_list_falls_back_to_runtime(self):
        """data is a flat list (not list-of-list); parsed_data[0] is a dict, falls through to runtime params."""
        import json as _json
        raw_template = {
            "id": "bt_002", "templateType": "TEXT",
            "containerMeta": _json.dumps({"data": "Hi {{1}}", "sampleText": "Hi Alice"})
        }
        template_config = {"template_id": "bt_002", "data": _json.dumps([{"type": "body"}])}
        components = BSPGupshup(self.GS_BOT, self.GS_USER).get_broadcast_template_params(
            raw_template, template_config)
        assert isinstance(components, list)
        body = next((c for c in components if c["type"] == "body"), None)
        assert body is not None

    # ─── get_template_params_for_broadcast ────────────────────────────

    def test_get_template_params_for_broadcast_returns_one_per_recipient(self):
        """Each recipient gets an identical copy of the computed components list."""
        import json as _json
        body = {"type": "body", "parameters": [{"type": "text", "text": "val"}]}
        button = {"type": "button", "sub_type": "url", "index": "0",
                  "parameters": [{"type": "text", "text": "X"}]}
        template_config = {"template_id": "tp_001", "data": _json.dumps([[body, button]])}
        raw_template = {"id": "tp_001", "templateType": "TEXT", "containerMeta": "{}"}
        recipients = ["9190000001", "9190000002", "9190000003"]
        result = BSPGupshup(self.GS_BOT, self.GS_USER).get_template_params_for_broadcast(
            raw_template, template_config, recipients, default_params=None)
        assert len(result) == 3
        assert all(r == [body, button] for r in result)

    # ─── fetch_media_ids ──────────────────────────────────────────────

    def test_fetch_media_ids_returns_completed_broadcast_media(self):
        bot = "gs_fetch_media_ids_bot"
        UserMediaData.objects(bot=bot).delete()
        UserMediaData(
            bot=bot, media_id="handle_001", filename="promo.pdf", extension="application/pdf",
            sender_id="user_a", upload_status=UserMediaUploadStatus.completed.value,
            upload_type=UserMediaUploadType.broadcast.value,
            external_upload_info={"bsp": "gupshup", "handle_id": "ext_handle_abc"},
            timestamp=datetime.utcnow()
        ).save()
        result = BSPGupshup.fetch_media_ids(bot)
        assert len(result) == 1
        assert result[0]["handle_id"] == "ext_handle_abc"
        assert result[0]["filename"] == "promo.pdf"
        UserMediaData.objects(bot=bot).delete()

    def test_fetch_media_ids_excludes_failed_uploads(self):
        bot = "gs_fetch_media_ids_excl_bot"
        UserMediaData.objects(bot=bot).delete()
        UserMediaData(
            bot=bot, media_id="failed_001", filename="fail.pdf", extension="application/pdf",
            sender_id="user_b", upload_status=UserMediaUploadStatus.failed.value,
            upload_type=UserMediaUploadType.broadcast.value,
            timestamp=datetime.utcnow()
        ).save()
        result = BSPGupshup.fetch_media_ids(bot)
        assert result == []
        UserMediaData.objects(bot=bot).delete()

    def test_fetch_media_ids_empty_returns_empty_list(self):
        result = BSPGupshup.fetch_media_ids("bot_with_zero_media_gs_xyz")
        assert result == []

    def test_fetch_media_ids_returns_external_media_id_in_id_field(self):
        bot = "gs_fetch_media_ids_ext_bot"
        UserMediaData.objects(bot=bot).delete()
        UserMediaData(
            bot=bot, media_id="internal_uuid", filename="promo.jpg", extension="image/jpeg",
            sender_id="user_c", upload_status=UserMediaUploadStatus.completed.value,
            upload_type=UserMediaUploadType.broadcast.value,
            external_upload_info={"bsp": "gupshup", "handle_id": "ext_handle_001", "external_media_id": "gs_media_456"},
            timestamp=datetime.utcnow()
        ).save()
        result = BSPGupshup.fetch_media_ids(bot)
        assert len(result) == 1
        assert result[0]["id"] == "gs_media_456"
        assert result[0]["handle_id"] == "ext_handle_001"
        assert result[0]["filename"] == "promo.jpg"
        UserMediaData.objects(bot=bot).delete()

    def test_fetch_media_ids_id_none_when_external_media_id_absent(self):
        bot = "gs_fetch_media_ids_no_ext_bot"
        UserMediaData.objects(bot=bot).delete()
        UserMediaData(
            bot=bot, media_id="internal_uuid2", filename="doc.pdf", extension="application/pdf",
            sender_id="user_d", upload_status=UserMediaUploadStatus.completed.value,
            upload_type=UserMediaUploadType.broadcast.value,
            external_upload_info={"bsp": "gupshup", "handle_id": "ext_handle_002"},
            timestamp=datetime.utcnow()
        ).save()
        result = BSPGupshup.fetch_media_ids(bot)
        assert len(result) == 1
        assert result[0]["id"] is None
        assert result[0]["handle_id"] == "ext_handle_002"
        UserMediaData.objects(bot=bot).delete()

    # ─── fetch_broadcast_media_ids ────────────────────────────────────

    def test_fetch_broadcast_media_ids_success(self):
        bot = "gs_fetch_bc_media_ids_bot"
        UserMediaData.objects(bot=bot).delete()
        UserMediaData(
            bot=bot, media_id="ext_media_001", filename="video.mp4", extension="video/mp4",
            sender_id="user_c", upload_status=UserMediaUploadStatus.completed.value,
            upload_type=UserMediaUploadType.broadcast.value,
            timestamp=datetime.utcnow()
        ).save()
        result = BSPGupshup.fetch_broadcast_media_ids(bot)
        assert len(result) == 1
        assert result[0]["media_id"] == "ext_media_001"
        UserMediaData.objects(bot=bot).delete()

    def test_fetch_broadcast_media_ids_excludes_empty_media_id(self):
        bot = "gs_fetch_bc_media_excl_bot"
        UserMediaData.objects(bot=bot).delete()
        UserMediaData(
            bot=bot, media_id="", filename="img.png", extension="image/png",
            sender_id="user_d", upload_status=UserMediaUploadStatus.completed.value,
            upload_type=UserMediaUploadType.broadcast.value,
            timestamp=datetime.utcnow()
        ).save()
        result = BSPGupshup.fetch_broadcast_media_ids(bot)
        assert result == []
        UserMediaData.objects(bot=bot).delete()

    # ─── delete_media_file ────────────────────────────────────────────

    def test_delete_media_file_gupshup_success(self):
        channel_config = {"config": {"app_id": "gs_app_001", "partner_app_token": "gs_tok"}}
        with patch("kairon.shared.utils.Utility.execute_http_request") as mock_http:
            mock_http.return_value = None
            result = BSPGupshup.delete_media_file("gs_media_001", channel_config)
        assert result == "Media file deleted successfully"
        mock_http.assert_called_once()

    def test_delete_media_file_gupshup_raises_on_failure(self):
        channel_config = {"config": {"app_id": "gs_app_001", "partner_app_token": "gs_tok"}}
        with patch("kairon.shared.utils.Utility.execute_http_request") as mock_http:
            mock_http.side_effect = AppException("media file does not exist for this media id.")
            with pytest.raises(AppException, match="media file does not exist"):
                BSPGupshup.delete_media_file("bad_media_id", channel_config)

    # ─── upload_media_file ────────────────────────────────────────────

    @pytest.mark.asyncio
    async def test_upload_media_file_missing_partner_token(self):
        channel_config = {"config": {"app_id": "gs_app_001"}}
        with pytest.raises(AppException, match="partner app token not found"):
            await BSPGupshup.upload_media_file(
                bot="gs_upload_bot", channel_config=channel_config, sender_id="user",
                filename="test.pdf", extension="application/pdf"
            )

    @pytest.mark.asyncio
    @responses.activate
    async def test_upload_media_file_upload_request_fails(self):
        from unittest.mock import MagicMock
        bot = "gs_upload_fail_bot_002"
        filename = "fail.pdf"
        extension = "application/pdf"
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]

        os.makedirs(f"media_upload_records/{bot}", exist_ok=True)
        with open(f"media_upload_records/{bot}/{filename}", "wb") as f:
            f.write(b"%PDF dummy")

        channel_config = {"config": {"app_id": "gs_app_001", "partner_app_token": "gs_partner_tok"}}
        responses.add("POST", url=f"{base_url}/partner/app/gs_app_001/upload/media",
                      json={"error": "upload failed"}, status=400)

        with patch("kairon.shared.channels.whatsapp.bsp.gupshup.UserMedia.create_media_doc") as mock_doc:
            mock_doc_inst = MagicMock()
            mock_doc.return_value = mock_doc_inst
            with pytest.raises(AppException):
                await BSPGupshup.upload_media_file(
                    bot=bot, channel_config=channel_config, sender_id="user",
                    filename=filename, extension=extension, filesize=50
                )
            mock_doc_inst.update.assert_called()

    @pytest.mark.asyncio
    @responses.activate
    async def test_upload_media_file_success(self):
        from unittest.mock import MagicMock
        bot = "gs_upload_success_bot_003"
        filename = "promo.pdf"
        extension = "application/pdf"
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]

        os.makedirs(f"media_upload_records/{bot}", exist_ok=True)
        with open(f"media_upload_records/{bot}/{filename}", "wb") as f:
            f.write(b"%PDF-1.4 dummy content")

        channel_config = {"config": {"app_id": "gs_app_001", "partner_app_token": "gs_partner_tok"}}
        responses.add("POST", url=f"{base_url}/partner/app/gs_app_001/upload/media",
                      json={"handleId": "handle_upload_001"}, status=200)
        responses.add("POST", url=f"{base_url}/partner/app/gs_app_001/media",
                      json={"mediaId": "ext_media_upload_001"}, status=200)

        storage_env = {"storage": {"whatsapp_media": {"bucket": "test-bucket"}}}
        with patch("kairon.shared.channels.whatsapp.bsp.gupshup.UserMedia.create_media_doc") as mock_doc, \
             patch("kairon.shared.channels.whatsapp.bsp.gupshup.UserMedia.save_media_content") as mock_save, \
             mock.patch.dict(Utility.environment, storage_env):
            mock_doc_inst = MagicMock()
            mock_doc.return_value = mock_doc_inst
            mock_save.return_value = "https://s3.aws/test/promo.pdf"
            result = await BSPGupshup.upload_media_file(
                bot=bot, channel_config=channel_config, sender_id="user",
                filename=filename, extension=extension, filesize=100
            )
        assert result == "ext_media_upload_001"

    # ─── upload_media ────────────────────────────────────────────

    @pytest.mark.asyncio
    @patch("kairon.shared.channels.whatsapp.bsp.gupshup.UserMedia.get_media_content_buffer")
    @responses.activate
    async def test_gupshup_upload_media_success(self, mock_get_buffer):
        import io as _io
        bot = "gs_upload_media_success_001"
        bsp_type = "gupshup"
        media_id = "gs_media_uuid_001"
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]

        UserMediaData(
            bot=bot, media_id=media_id, filename="test.pdf", extension=".pdf",
            upload_status="Completed", upload_type="user", filesize=1000,
            sender_id="user@test.com", timestamp=datetime.utcnow()
        ).save()
        Channels(
            bot=bot, connector_type="whatsapp",
            config={"app_id": "gs_app_test_001", "partner_app_token": "gs_tok_secret", "bsp_type": bsp_type},
            user="user@test.com", timestamp=datetime.utcnow()
        ).save(validate=False)

        mock_get_buffer.return_value = (_io.BytesIO(b"%PDF mock"), "test.pdf", ".pdf")
        responses.add(responses.POST, f"{base_url}/partner/app/gs_app_test_001/media",
                      json={"mediaId": "gs_ext_001"}, status=200)

        result = await BSPGupshup.upload_media(bot, bsp_type, media_id)

        assert result == "gs_ext_001"
        doc = UserMediaData.objects.get(media_id=media_id)
        assert doc.external_upload_info["external_media_id"] == "gs_ext_001"
        assert doc.external_upload_info["error"] == ""
        assert "application/pdf" in responses.calls[0].request.body.decode("latin-1")

        UserMediaData.objects(bot=bot).delete()
        Channels.objects(bot=bot).delete()

    @pytest.mark.asyncio
    async def test_gupshup_upload_media_doc_not_found(self):
        with pytest.raises(AppException, match="UserMediaData not found"):
            await BSPGupshup.upload_media("no_bot", "bsp_gupshup", "nonexistent_media_id_xyz")

    @pytest.mark.asyncio
    async def test_gupshup_upload_media_channel_not_configured(self):
        bot = "gs_upload_media_no_ch_001"
        media_id = "gs_media_no_ch_001"
        UserMediaData(
            bot=bot, media_id=media_id, filename="doc.pdf", extension=".pdf",
            upload_status="Completed", upload_type="user", filesize=500,
            sender_id="u@t.com", timestamp=datetime.utcnow()
        ).save()

        with pytest.raises(AppException, match="Channel config not found"):
            await BSPGupshup.upload_media(bot, "gupshup", media_id)

        UserMediaData.objects(bot=bot).delete()

    @pytest.mark.asyncio
    async def test_gupshup_upload_media_missing_partner_token(self):
        bot = "gs_upload_media_no_tok_001"
        bsp_type = "gupshup"
        media_id = "gs_media_no_tok_001"
        UserMediaData(
            bot=bot, media_id=media_id, filename="doc.pdf", extension=".pdf",
            upload_status="Completed", upload_type="user", filesize=500,
            sender_id="u@t.com", timestamp=datetime.utcnow()
        ).save()
        Channels(
            bot=bot, connector_type="whatsapp",
            config={"app_id": "gs_app_no_tok", "bsp_type": bsp_type},
            user="u@t.com", timestamp=datetime.utcnow()
        ).save(validate=False)

        with pytest.raises(AppException, match="partner_app_token not found"):
            await BSPGupshup.upload_media(bot, bsp_type, media_id)

        UserMediaData.objects(bot=bot).delete()
        Channels.objects(bot=bot).delete()

    @pytest.mark.asyncio
    @patch("kairon.shared.channels.whatsapp.bsp.gupshup.UserMedia.get_media_content_buffer")
    @responses.activate
    async def test_gupshup_upload_media_api_failure(self, mock_get_buffer):
        import io as _io
        bot = "gs_upload_media_fail_001"
        bsp_type = "gupshup"
        media_id = "gs_media_fail_001"
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["gupshup"]["partner_base_url"]

        UserMediaData(
            bot=bot, media_id=media_id, filename="doc.pdf", extension=".pdf",
            upload_status="Completed", upload_type="user", filesize=500,
            sender_id="u@t.com", timestamp=datetime.utcnow()
        ).save()
        Channels(
            bot=bot, connector_type="whatsapp",
            config={"app_id": "gs_app_fail", "partner_app_token": "gs_tok_fail", "bsp_type": bsp_type},
            user="u@t.com", timestamp=datetime.utcnow()
        ).save(validate=False)

        mock_get_buffer.return_value = (_io.BytesIO(b"%PDF mock"), "doc.pdf", ".pdf")
        responses.add(responses.POST, f"{base_url}/partner/app/gs_app_fail/media",
                      json={"error": "upload rejected"}, status=400)

        with pytest.raises(AppException):
            await BSPGupshup.upload_media(bot, bsp_type, media_id)

        doc = UserMediaData.objects.get(media_id=media_id)
        assert doc.external_upload_info.get("error")

        UserMediaData.objects(bot=bot).delete()
        Channels.objects(bot=bot).delete()


class TestDataRouterMediaEndpoints:
    BOT = "data_router_test_bot_001"
    USER = "data_router_test_user_001"

    def _make_user(self):
        from unittest.mock import MagicMock
        user = MagicMock()
        user.get_bot.return_value = self.BOT
        user.get_user.return_value = self.USER
        return user

    @pytest.mark.asyncio
    async def test_get_media_ids_exception_case(self):
        from kairon.api.app.routers.bot.data import get_media_ids
        user = self._make_user()
        with patch(
            "kairon.api.app.routers.bot.data.MessageBroadcastProcessor.fetch_media_ids",
            side_effect=Exception("channel not found"),
        ):
            with pytest.raises(AppException) as exc_info:
                await get_media_ids(current_user=user)
        assert "Error while fetching media ids: channel not found" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_get_whatsapp_media_ids_success(self):
        from kairon.api.app.routers.bot.data import get_whatsapp_media_ids
        user = self._make_user()
        with patch(
            "kairon.api.app.routers.bot.data.MessageBroadcastProcessor.fetch_broadcast_media_ids",
            return_value=["media_001", "media_002"],
        ):
            result = await get_whatsapp_media_ids(current_user=user)
        assert result.data == ["media_001", "media_002"]
        assert result.message == "List of media ids"

    @pytest.mark.asyncio
    async def test_get_whatsapp_media_ids_exception_case(self):
        from kairon.api.app.routers.bot.data import get_whatsapp_media_ids
        user = self._make_user()
        with patch(
            "kairon.api.app.routers.bot.data.MessageBroadcastProcessor.fetch_broadcast_media_ids",
            side_effect=Exception("bsp config missing"),
        ):
            with pytest.raises(AppException) as exc_info:
                await get_whatsapp_media_ids(current_user=user)
        assert "Error while fetching media ids: bsp config missing" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_fetch_media_handle_id_success(self):
        from kairon.api.app.routers.bot.data import fetch_media_handle_id
        user = self._make_user()
        with patch(
            "kairon.api.app.routers.bot.data.UserMedia.get_media_handle_id",
            return_value="handle_xyz_001",
        ):
            result = await fetch_media_handle_id(media_id="media_doc_id_001", current_user=user)
        assert result.data == {"handle_id": "handle_xyz_001"}
        assert result.message == "Successfully fetched media details"

    @pytest.mark.asyncio
    async def test_fetch_media_handle_id_not_found(self):
        from kairon.api.app.routers.bot.data import fetch_media_handle_id
        user = self._make_user()
        with patch(
            "kairon.api.app.routers.bot.data.UserMedia.get_media_handle_id",
            side_effect=AppException("Media not found"),
        ):
            with pytest.raises(AppException) as exc_info:
                await fetch_media_handle_id(media_id="nonexistent_id", current_user=user)
        assert "Media not found" in str(exc_info.value)
