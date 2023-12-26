import os
from unittest import mock

import pytest
import responses
from mongoengine import connect, ValidationError

from kairon.exceptions import AppException
from kairon.shared.auth import Authentication
from kairon.shared.channels.whatsapp.bsp.base import WhatsappBusinessServiceProviderBase
from kairon.shared.channels.whatsapp.bsp.dialog360 import BSP360Dialog
from kairon.shared.channels.whatsapp.bsp.factory import BusinessServiceProviderFactory
from kairon.shared.chat.processor import ChatDataProcessor
from kairon.shared.constants import WhatsappBSPTypes, ChannelTypes
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.data_objects import BotSettings
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.utils import Utility


class TestBusinessServiceProvider:

    @pytest.fixture(autouse=True, scope='class')
    def setup(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        Utility.load_system_metadata()
        db_url = Utility.environment['database']["url"]
        pytest.db_url = db_url
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        responses.reset()

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
        url = f"{base_url}/api/v2/partners/{partner_id}/channels?filters={{'id':'{channel_id}'}}"
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
        url = f"{base_url}/api/v2/partners/{partner_id}/channels?filters={{'id':'{channel_id}'}}"
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
        responses.add("POST", json={}, url=url, status=500)

        with pytest.raises(AppException, match=r"Failed to generate api_keys for business account: *"):
            BSP360Dialog.generate_waba_key("skds23Ga")

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

    @responses.activate
    def test_add_template(self, monkeypatch):
        with mock.patch.dict(Utility.environment, {'channels': {"360dialog": {"partner_id": "new_partner_id"}}}):
            responses.reset()
            bot = "62bc24b493a0d6b7a46328ff"
            partner_id = "new_partner_id"
            waba_account_id = "Cyih7GWA"
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

            def _get_partners_auth_token(*args, **kwargs):
                return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

            monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)

            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
            url = f"{base_url}/v1/partners/{partner_id}/waba_accounts/{waba_account_id}/waba_templates"
            responses.add("POST", json=api_resp, url=url)
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
            partner_id = "new_partner_id"
            waba_account_id = "Cyih7GWA"
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
            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
            url = f"{base_url}/v1/partners/{partner_id}/waba_accounts/{waba_account_id}/waba_templates"
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
            template_id = "test_id"
            partner_id = "new_partner_id"
            waba_account_id = "Cyih7GWA"
            api_resp = {
                "meta": {
                    "developer_message": "template name=Introduction template was deleted",
                    "http_code": 200,
                    "success": True
                }
            }

            def _get_partners_auth_token(*args, **kwargs):
                return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

            monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)

            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
            url = f"{base_url}/v1/partners/{partner_id}/waba_accounts/{waba_account_id}/waba_templates/{template_id}"
            responses.add("DELETE", json=api_resp, url=url)
            template = BSP360Dialog(bot, "test").delete_template(template_id)
            assert template == {'meta': {'developer_message': 'template name=Introduction template was deleted', 'http_code': 200, 'success': True}}

    @responses.activate
    def test_delete_template_failure(self, monkeypatch):
        with mock.patch.dict(Utility.environment, {'channels': {"360dialog": {"partner_id": "new_partner_id"}}}):
            bot = "62bc24b493a0d6b7a46328ff"
            template_id = "test_id"
            partner_id = "new_partner_id"
            waba_account_id = "Cyih7GWA"

            def _get_partners_auth_token(*args, **kwargs):
                return "Bearer eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCIs.ImtpZCI6Ik1EZEZOVFk1UVVVMU9FSXhPRGN3UVVZME9EUTFRVFJDT1.RSRU9VUTVNVGhDTURWRk9UUTNPQSJ9"

            monkeypatch.setattr(BSP360Dialog, 'get_partner_auth_token', _get_partners_auth_token)
            base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
            url = f"{base_url}/v1/partners/{partner_id}/waba_accounts/{waba_account_id}/waba_templates/{template_id}"
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

        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        url = f"{base_url}/api/v2/partners/new_partner_id/waba_accounts/Cyih7GWA/waba_templates?filters=%7B%22id%22:%20%22test_id%22%7D&sort=business_templates.name"
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
        base_url = Utility.system_metadata["channels"]["whatsapp"]["business_providers"]["360dialog"]["hub_base_url"]
        url = f"{base_url}/api/v2/partners/new_partner_id/waba_accounts/Cyih7GWA/waba_templates?filters=%7B%22id%22:%20%22test_id%22%7D&sort=business_templates.name"
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
