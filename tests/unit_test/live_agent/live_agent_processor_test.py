import os

import pytest
import responses
from mongoengine import connect, ValidationError

from kairon.shared.utils import Utility
from kairon.exceptions import AppException
from kairon.shared.account.data_objects import Bot
from kairon.shared.live_agent.data_objects import LiveAgents
from kairon.shared.live_agent.processor import LiveAgentsProcessor
from kairon.live_agent.live_agent import LiveAgent
import ujson as json
from kairon.live_agent.factory import LiveAgentFactory
from datetime import datetime, timezone


class TestLiveAgentProcessor:

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())
        pytest.bot = Bot(name="test", account=1, user="test_user").save()

    @responses.activate
    def test_add_live_agent(self):
        config = {"agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}

        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
            json={"payload": []}
        )
        responses.add(
            "POST",
            f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
            json={
                "id": 14036,
                "avatar_url": "",
                "channel_id": 2317,
                "name": "kairon-bot",
                "channel_type": "Channel::Api",
                "greeting_enabled": False,
                "greeting_message": None,
                "working_hours_enabled": False,
                "enable_email_collect": True,
                "csat_survey_enabled": False,
                "enable_auto_assignment": True,
                "out_of_office_message": None,
                "working_hours": [
                    {
                        "day_of_week": 0,
                        "closed_all_day": True,
                        "open_hour": None,
                        "open_minutes": None,
                        "close_hour": None,
                        "close_minutes": None,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 1,
                        "closed_all_day": False,
                        "open_hour": 9,
                        "open_minutes": 0,
                        "close_hour": 17,
                        "close_minutes": 0,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 2,
                        "closed_all_day": False,
                        "open_hour": 9,
                        "open_minutes": 0,
                        "close_hour": 17,
                        "close_minutes": 0,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 3,
                        "closed_all_day": False,
                        "open_hour": 9,
                        "open_minutes": 0,
                        "close_hour": 17,
                        "close_minutes": 0,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 4,
                        "closed_all_day": False,
                        "open_hour": 9,
                        "open_minutes": 0,
                        "close_hour": 17,
                        "close_minutes": 0,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 5,
                        "closed_all_day": False,
                        "open_hour": 9,
                        "open_minutes": 0,
                        "close_hour": 17,
                        "close_minutes": 0,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 6,
                        "closed_all_day": True,
                        "open_hour": None,
                        "open_minutes": None,
                        "close_hour": None,
                        "close_minutes": None,
                        "open_all_day": False
                    }
                ],
                "timezone": "UTC",
                "callback_webhook_url": None,
                "allow_messages_after_resolved": True,
                "widget_color": None,
                "website_url": None,
                "hmac_mandatory": False,
                "welcome_title": None,
                "welcome_tagline": None,
                "web_widget_script": None,
                "website_token": None,
                "selected_feature_flags": None,
                "reply_time": None,
                "phone_number": None,
                "webhook_url": None,
                "inbox_identifier": "tSaxZWrxyFowmFHzWwhMwi5y"}
        )
        LiveAgentsProcessor.save_config(config, pytest.bot.id, pytest.bot.user)
        assert LiveAgents.objects(bot=pytest.bot.id).get()

    def test_get_live_agent(self):
        expected_config = {
            "agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67",
                                                 "inbox_identifier": "tSaxZWrxyFowmFHzWwhMwi5y"},
            "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
            "trigger_on_actions": ["action_default_fallback", "action_enquiry"]
        }

        agent = LiveAgentsProcessor.get_config(pytest.bot.id, False)
        assert agent["config"] == expected_config["config"]
        assert agent["agent_type"] == expected_config["agent_type"]
        assert agent["override_bot"] == expected_config["override_bot"]
        assert agent["trigger_on_intents"] == expected_config["trigger_on_intents"]
        assert agent["trigger_on_actions"] == expected_config["trigger_on_actions"]

    @responses.activate
    def test_add_live_agent_with_inbox_identifier(self):
        config = {"agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67",
                                                       "inbox_identifier": "tSaxZWrxyFowmFHzWwhkjnfc"},
                  "override_bot": False, "trigger_on_actions": ["action_default_fallback"]}

        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
            json={
                "payload": [
                    {
                        "id": 14035,
                        "avatar_url": "",
                        "channel_id": 2316,
                        "name": "test",
                        "channel_type": "Channel::Api",
                        "greeting_enabled": False,
                        "greeting_message": None,
                        "working_hours_enabled": False,
                        "enable_email_collect": True,
                        "csat_survey_enabled": False,
                        "enable_auto_assignment": True,
                        "out_of_office_message": None,
                        "working_hours": [
                            {
                                "day_of_week": 0,
                                "closed_all_day": True,
                                "open_hour": None,
                                "open_minutes": None,
                                "close_hour": None,
                                "close_minutes": None,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 1,
                                "closed_all_day": False,
                                "open_hour": 9,
                                "open_minutes": 0,
                                "close_hour": 17,
                                "close_minutes": 0,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 2,
                                "closed_all_day": False,
                                "open_hour": 9,
                                "open_minutes": 0,
                                "close_hour": 17,
                                "close_minutes": 0,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 3,
                                "closed_all_day": False,
                                "open_hour": 9,
                                "open_minutes": 0,
                                "close_hour": 17,
                                "close_minutes": 0,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 4,
                                "closed_all_day": False,
                                "open_hour": 9,
                                "open_minutes": 0,
                                "close_hour": 17,
                                "close_minutes": 0,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 5,
                                "closed_all_day": False,
                                "open_hour": 9,
                                "open_minutes": 0,
                                "close_hour": 17,
                                "close_minutes": 0,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 6,
                                "closed_all_day": True,
                                "open_hour": None,
                                "open_minutes": None,
                                "close_hour": None,
                                "close_minutes": None,
                                "open_all_day": False
                            }
                        ],
                        "timezone": "UTC",
                        "callback_webhook_url": None,
                        "allow_messages_after_resolved": True,
                        "widget_color": None,
                        "website_url": None,
                        "hmac_mandatory": False,
                        "welcome_title": None,
                        "welcome_tagline": None,
                        "web_widget_script": None,
                        "website_token": None,
                        "selected_feature_flags": None,
                        "reply_time": None,
                        "phone_number": None,
                        "webhook_url": "",
                        "inbox_identifier": "G9aiymXKjzvKXx9YHg2ojyrK"
                    },
                    {
                        "id": 14036,
                        "avatar_url": "",
                        "channel_id": 2317,
                        "name": "kairon-bot",
                        "channel_type": "Channel::Api",
                        "greeting_enabled": False,
                        "greeting_message": None,
                        "working_hours_enabled": False,
                        "enable_email_collect": True,
                        "csat_survey_enabled": False,
                        "enable_auto_assignment": True,
                        "out_of_office_message": None,
                        "working_hours": [
                            {
                                "day_of_week": 0,
                                "closed_all_day": True,
                                "open_hour": None,
                                "open_minutes": None,
                                "close_hour": None,
                                "close_minutes": None,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 1,
                                "closed_all_day": False,
                                "open_hour": 9,
                                "open_minutes": 0,
                                "close_hour": 17,
                                "close_minutes": 0,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 2,
                                "closed_all_day": False,
                                "open_hour": 9,
                                "open_minutes": 0,
                                "close_hour": 17,
                                "close_minutes": 0,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 3,
                                "closed_all_day": False,
                                "open_hour": 9,
                                "open_minutes": 0,
                                "close_hour": 17,
                                "close_minutes": 0,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 4,
                                "closed_all_day": False,
                                "open_hour": 9,
                                "open_minutes": 0,
                                "close_hour": 17,
                                "close_minutes": 0,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 5,
                                "closed_all_day": False,
                                "open_hour": 9,
                                "open_minutes": 0,
                                "close_hour": 17,
                                "close_minutes": 0,
                                "open_all_day": False
                            },
                            {
                                "day_of_week": 6,
                                "closed_all_day": True,
                                "open_hour": None,
                                "open_minutes": None,
                                "close_hour": None,
                                "close_minutes": None,
                                "open_all_day": False
                            }
                        ],
                        "timezone": "UTC",
                        "callback_webhook_url": None,
                        "allow_messages_after_resolved": True,
                        "widget_color": None,
                        "website_url": None,
                        "hmac_mandatory": False,
                        "welcome_title": None,
                        "welcome_tagline": None,
                        "web_widget_script": None,
                        "website_token": None,
                        "selected_feature_flags": None,
                        "reply_time": None,
                        "phone_number": None,
                        "webhook_url": None,
                        "inbox_identifier": "tSaxZWrxyFowmFHzWwhkjnfc"
                    }
                ]
            }
        )
        LiveAgentsProcessor.save_config(config, pytest.bot.id, pytest.bot.user)
        assert LiveAgents.objects(bot=pytest.bot.id).get()

    @responses.activate
    def test_add_live_agent_failure(self):
        config = {"agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}
        responses.add(
            "GET",
            f"https://app.chatwoot.com/public/api/v1/accounts/{config['config']['account_id']}/inboxes",
            status=404,
            body="Not Found"
        )
        with pytest.raises(AppException, match="Unable to connect. Please verify credentials."):
            LiveAgentsProcessor.save_config(config, pytest.bot.id, pytest.bot.user)

    @responses.activate
    def test_add_live_agent_invalid_type(self):
        config = {"agent_type": "livechat", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}

        with pytest.raises(ValidationError, match=f'Agent system not supported'):
            LiveAgentsProcessor.save_config(config, pytest.bot.id, pytest.bot.user)

    def test_get_live_agent_2(self):
        expected_config = {
            "agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67",
                                                 "inbox_identifier": "tSaxZWrxyFowmFHzWwhkjnfc"},
            "override_bot": False, "trigger_on_actions": ["action_default_fallback"]
        }

        agent = LiveAgentsProcessor.get_config(pytest.bot.id, False)
        assert agent["config"] == expected_config["config"]
        assert agent["agent_type"] == expected_config["agent_type"]
        assert agent["override_bot"] == expected_config["override_bot"]
        assert agent["trigger_on_intents"] == []
        assert agent["trigger_on_actions"] == expected_config["trigger_on_actions"]

    @responses.activate
    def test_update_live_agent(self):
        config = {"agent_type": "chatwoot", "config": {"account_id": "13", "api_access_token": "hgj657890"},
                  "override_bot": True}

        responses.add(
            "GET",
            f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
            json={"payload": []}
        )
        responses.add(
            "POST",
            f"https://app.chatwoot.com/api/v1/accounts/{config['config']['account_id']}/inboxes",
            json={
                "id": 14036,
                "avatar_url": "",
                "channel_id": 2317,
                "name": "kairon-bot",
                "channel_type": "Channel::Api",
                "greeting_enabled": False,
                "greeting_message": None,
                "working_hours_enabled": False,
                "enable_email_collect": True,
                "csat_survey_enabled": False,
                "enable_auto_assignment": True,
                "out_of_office_message": None,
                "working_hours": [
                    {
                        "day_of_week": 0,
                        "closed_all_day": True,
                        "open_hour": None,
                        "open_minutes": None,
                        "close_hour": None,
                        "close_minutes": None,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 1,
                        "closed_all_day": False,
                        "open_hour": 9,
                        "open_minutes": 0,
                        "close_hour": 17,
                        "close_minutes": 0,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 2,
                        "closed_all_day": False,
                        "open_hour": 9,
                        "open_minutes": 0,
                        "close_hour": 17,
                        "close_minutes": 0,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 3,
                        "closed_all_day": False,
                        "open_hour": 9,
                        "open_minutes": 0,
                        "close_hour": 17,
                        "close_minutes": 0,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 4,
                        "closed_all_day": False,
                        "open_hour": 9,
                        "open_minutes": 0,
                        "close_hour": 17,
                        "close_minutes": 0,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 5,
                        "closed_all_day": False,
                        "open_hour": 9,
                        "open_minutes": 0,
                        "close_hour": 17,
                        "close_minutes": 0,
                        "open_all_day": False
                    },
                    {
                        "day_of_week": 6,
                        "closed_all_day": True,
                        "open_hour": None,
                        "open_minutes": None,
                        "close_hour": None,
                        "close_minutes": None,
                        "open_all_day": False
                    }
                ],
                "timezone": "UTC",
                "callback_webhook_url": None,
                "allow_messages_after_resolved": True,
                "widget_color": None,
                "website_url": None,
                "hmac_mandatory": False,
                "welcome_title": None,
                "welcome_tagline": None,
                "web_widget_script": None,
                "website_token": None,
                "selected_feature_flags": None,
                "reply_time": None,
                "phone_number": None,
                "webhook_url": None,
                "inbox_identifier": "tSaxZWrxyFowmFHzWwhMwadsday"}
        )
        LiveAgentsProcessor.save_config(config, pytest.bot.id, pytest.bot.user)
        assert LiveAgents.objects(bot=pytest.bot.id).get()

    def test_update_live_agent_invalid_type(self):
        config = {"agent_type": "livechat", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}

        with pytest.raises(ValidationError, match=f'Agent system not supported'):
            LiveAgentsProcessor.save_config(config, pytest.bot.id, pytest.bot.user)

    def test_get_live_agent_after_update(self):
        expected_config = {
            "agent_type": "chatwoot", "config": {"account_id": "13", "api_access_token": "hgj657890",
                                                 "inbox_identifier": "tSaxZWrxyFowmFHzWwhMwadsday"},
            "override_bot": True
        }

        agent = LiveAgentsProcessor.get_config(pytest.bot.id, False)
        assert agent["config"] == expected_config["config"]
        assert agent["agent_type"] == expected_config["agent_type"]
        assert agent["override_bot"] == expected_config["override_bot"]
        assert agent["trigger_on_intents"] == []
        assert agent["trigger_on_actions"] == []

    def test_get_live_agent_with_masked_required_fields(self):
        expected_config = {
            "agent_type": "chatwoot", "config": {"account_id": "***", "api_access_token": "hgj657***",
                                                 "inbox_identifier": "tSaxZWrxyFowmFHzWwhMwadsday"},
            "override_bot": True
        }

        agent = LiveAgentsProcessor.get_config(pytest.bot.id)
        assert agent["config"] == expected_config["config"]
        assert agent["agent_type"] == expected_config["agent_type"]
        assert agent["override_bot"] == expected_config["override_bot"]
        assert agent["trigger_on_intents"] == []
        assert agent["trigger_on_actions"] == []

    def test_delete_agent_config(self):
        LiveAgentsProcessor.delete_config(pytest.bot.id, "test_user")

    def test_get_agent_config_none(self):
        assert not LiveAgentsProcessor.get_config(pytest.bot.id, raise_error=False)

    def test_get_agent_config_raise_error(self):
        with pytest.raises(AppException, match="Live agent config not found!"):
            LiveAgentsProcessor.get_config(pytest.bot.id)

    def test_get_contact_not_exists(self):
        metadata = LiveAgentsProcessor.get_contact(str(pytest.bot.id), "udit", "chatwoot")
        assert metadata is None

    def test_add_contact(self):
        assert not LiveAgentsProcessor.save_contact(
            str(pytest.bot.id), "udit", "chatwoot", {"source_id": 'fdfghjkl56789', "inbox_identifier": "dsfghjk567890"}
        )

    def test_get_contact(self):
        metadata = LiveAgentsProcessor.get_contact(str(pytest.bot.id), "udit", "chatwoot")
        assert metadata["metadata"] == {"source_id": 'fdfghjkl56789', "inbox_identifier": "dsfghjk567890"}
        assert metadata["agent_type"] == "chatwoot"
        assert metadata["sender_id"] == "udit"

    def test_update_contact(self):
        assert not LiveAgentsProcessor.save_contact(
            str(pytest.bot.id), "udit", "chatwoot", {"source_id": 'fdfghjkl56987', "inbox_identifier": "dsfghjk567089"}
        )

    def test_get_contact_after_update(self):
        metadata = LiveAgentsProcessor.get_contact(str(pytest.bot.id), "udit", "chatwoot")
        assert metadata["metadata"] == {"source_id": 'fdfghjkl56987', "inbox_identifier": "dsfghjk567089"}
        assert metadata["agent_type"] == "chatwoot"
        assert metadata["sender_id"] == "udit"

    def test_get_live_agent_exception(self):
        with pytest.raises(AppException, match="Live agent config not found!"):
            LiveAgent.from_bot("Chatbot")

    @responses.activate
    def test_chatwoot_getBusinesshours(selfs):
        config = {"agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}
        business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
        output_json = business_workingdata.get("working_enabled_true")
        responses.add(responses.GET, 'https://app.chatwoot.com/api/v1/accounts/12/inboxes/25226',
        json=output_json, status=200)
        live_agent = LiveAgentFactory.get_agent(config["agent_type"], config["config"])
        businessdata = live_agent.getBusinesshours(config, "25226")
        assert output_json == businessdata

    @responses.activate
    def test_chatwoot_getBusinesshours_working_enabled(selfs):
        config = {"agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}
        business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
        output_json = business_workingdata.get("working_enabled_true")
        responses.add(responses.GET, 'https://app.chatwoot.com/api/v1/accounts/12/inboxes/25227',
                      json=output_json, status=200)
        live_agent = LiveAgentFactory.get_agent(config["agent_type"], config["config"])
        businessdata = live_agent.getBusinesshours(config, "25227")
        assert output_json == businessdata
        assert businessdata["working_hours_enabled"] == True

    @responses.activate
    def test_chatwoot_getBusinesshours_working_disabled(selfs):
        import ujson as json
        from kairon.live_agent.factory import LiveAgentFactory
        config = {"agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}
        business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
        output_json = business_workingdata.get("working_enabled_false")
        responses.add(responses.GET, 'https://app.chatwoot.com/api/v1/accounts/12/inboxes/25226',
                      json=output_json, status=200)
        live_agent = LiveAgentFactory.get_agent(config["agent_type"], config["config"])
        businessdata = live_agent.getBusinesshours(config, "25226")
        assert output_json == businessdata
        assert businessdata["working_hours_enabled"] == False

    @responses.activate
    def test_chatwoot_getBusinesshours_underworkinghours_false(selfs):
        config = {"agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}
        business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
        output_json = business_workingdata.get("working_enabled_true")
        responses.add(responses.GET, 'https://app.chatwoot.com/api/v1/accounts/12/inboxes/25226',
                      json=output_json, status=200)
        live_agent = LiveAgentFactory.get_agent(config["agent_type"], config["config"])
        businessdata = live_agent.getBusinesshours(config, "25226")
        current_utcnow = datetime(2023, 2, 13, 3, 15, 00, tzinfo=timezone.utc)
        workingstatus = live_agent.validate_businessworkinghours(businessdata, current_utcnow)
        assert workingstatus == False

    @responses.activate
    def test_chatwoot_getBusinesshours_underworkinghours_true(selfs):
        config = {"agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}
        business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
        output_json = business_workingdata.get("working_enabled_true")
        responses.add(responses.GET, 'https://app.chatwoot.com/api/v1/accounts/12/inboxes/25226',
                      json=output_json, status=200)
        live_agent = LiveAgentFactory.get_agent(config["agent_type"], config["config"])
        businessdata = live_agent.getBusinesshours(config, "25226")
        current_utcnow = datetime(2023, 2, 13, 5, 15, 00, tzinfo=timezone.utc)
        workingstatus = live_agent.validate_businessworkinghours(businessdata, current_utcnow)
        assert workingstatus == True

    @responses.activate
    def test_chatwoot_getBusinesshours_alldayworking(selfs):
        config = {"agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}
        business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
        output_json = business_workingdata.get("working_enabled_all_day_working")
        responses.add(responses.GET, 'https://app.chatwoot.com/api/v1/accounts/12/inboxes/25226',
                      json=output_json, status=200)
        live_agent = LiveAgentFactory.get_agent(config["agent_type"], config["config"])
        businessdata = live_agent.getBusinesshours(config, "25226")
        current_utcnow = datetime(2023, 2, 13, 5, 15, 00, tzinfo=timezone.utc)
        workingstatus = live_agent.validate_businessworkinghours(businessdata, current_utcnow)
        assert workingstatus == True

    @responses.activate
    def test_chatwoot_getBusinesshours_alldayworking_false(selfs):
        config = {"agent_type": "chatwoot", "config": {"account_id": "12", "api_access_token": "asdfghjklty67"},
                  "override_bot": False, "trigger_on_intents": ["greet", "enquiry"],
                  "trigger_on_actions": ["action_default_fallback", "action_enquiry"]}
        business_workingdata = json.load(open("tests/testing_data/live_agent/business_working_data.json"))
        output_json = business_workingdata.get("working_enabled_all_day_working")
        responses.add(responses.GET, 'https://app.chatwoot.com/api/v1/accounts/12/inboxes/25226',
                      json=output_json, status=200)
        live_agent = LiveAgentFactory.get_agent(config["agent_type"], config["config"])
        businessdata = live_agent.getBusinesshours(config, "25226")
        current_utcnow = datetime(2023, 2, 14, 5, 15, 00, tzinfo=timezone.utc)
        workingstatus = live_agent.validate_businessworkinghours(businessdata, current_utcnow)
        assert workingstatus == False