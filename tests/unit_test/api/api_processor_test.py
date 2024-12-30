import asyncio
import datetime
import json
import os
import time
import uuid
from unittest import mock
from unittest.mock import patch
from urllib.parse import urljoin
from kairon.shared.utils import Utility, MailUtility
Utility.load_system_metadata()

import jwt
import pytest
import responses
from fastapi import HTTPException
from fastapi_sso.sso.base import OpenID
from mongoengine import connect
from mongoengine.errors import ValidationError, DoesNotExist
from mongomock.object_id import ObjectId
from pydantic import SecretStr
from pytest_httpx import HTTPXMock
from starlette.datastructures import Headers, URL
from starlette.requests import Request
from starlette.responses import RedirectResponse

from kairon.api.models import RegisterAccount, EventConfig, IDPConfig, StoryRequest, HttpActionParameters, Password
from kairon.exceptions import AppException
from kairon.idp.data_objects import IdpConfig
from kairon.idp.processor import IDPProcessor
from kairon.shared.account.data_objects import Feedback, BotAccess, User, Bot, Account, Organization, TrustedDevice
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.admin.data_objects import BotSecrets
from kairon.shared.auth import Authentication, LoginSSOFactory
from kairon.shared.authorization.processor import IntegrationProcessor
from kairon.shared.constants import UserActivityType
from kairon.shared.data.audit.data_objects import AuditLogData
from kairon.shared.data.audit.processor import AuditDataProcessor
from kairon.shared.data.constant import ACTIVITY_STATUS, ACCESS_ROLES, TOKEN_TYPE, INTEGRATION_STATUS, \
    ORG_SETTINGS_MESSAGES, FeatureMappings
from kairon.shared.data.data_objects import Configs, Rules, Responses, BotSettings
from kairon.shared.data.processor import MongoProcessor
from kairon.shared.organization.processor import OrgProcessor
from kairon.shared.sso.clients.facebook import FacebookSSO
from kairon.shared.sso.clients.google import GoogleSSO

os.environ["system_file"] = "./tests/testing_data/system.yaml"


def pytest_configure():
    return {'bot': None, 'account': None}


class TestAccountProcessor:
    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        Utility.load_environment()
        connect(**Utility.mongoengine_connection(Utility.environment['database']["url"]))
        AccountProcessor.load_system_properties()

    def test_add_account(self):
        account_response = AccountProcessor.add_account("paypal", "testAdmin")
        account = AccountProcessor.get_account(account_response["_id"])
        assert account_response
        pytest.account = account_response["_id"]
        assert account_response["_id"] == account["_id"]
        assert account_response["name"] == account["name"]
        account_response = AccountProcessor.add_account("ebay", "testAdmin")
        account = AccountProcessor.get_account(account_response["_id"])
        assert account_response
        assert account_response["_id"] == account["_id"]
        assert account_response["name"] == account["name"]

    def test_add_duplicate_account(self):
        with pytest.raises(Exception):
            AccountProcessor.add_account("paypal", "testAdmin")

    def test_add_duplicate_account_case_insentive(self):
        with pytest.raises(Exception):
            AccountProcessor.add_account("PayPal", "testAdmin")

    def test_add_blank_account(self):
        with pytest.raises(AppException):
            AccountProcessor.add_account("", "testAdmin")

    def test_add_empty_account(self):
        with pytest.raises(AppException):
            AccountProcessor.add_account(" ", "testAdmin")

    def test_add_none_account(self):
        with pytest.raises(AppException):
            AccountProcessor.add_account(None, "testAdmin")

    def test_list_bots_none(self):
        assert not list(AccountProcessor.list_bots(1000))

    def test_add_bot_with_character_limit_exceeded(self):
        name = "supercalifragilisticexpialidociousalwaysworksmorethan60characters"
        with pytest.raises(AppException, match='Bot Name cannot be more than 60 characters.'):
            AccountProcessor.add_bot(name=name, account=pytest.account,
                                     user="fshaikh@digite.com", is_new_account=True)

    def test_add_bot(self):
        bot_response = AccountProcessor.add_bot("test", pytest.account, "fshaikh@digite.com", True)
        bot = Bot.objects(name="test").get().to_mongo().to_dict()
        assert bot['_id'].__str__() == bot_response['_id'].__str__()
        pytest.bot = bot_response["_id"].__str__()
        config = Configs.objects(bot=bot['_id'].__str__()).get().to_mongo().to_dict()
        expected_config = Utility.read_yaml(Utility.environment["model"]["train"]["default_model_training_config_path"])
        assert config['language'] == expected_config['language']
        assert config['pipeline'] == expected_config['pipeline']
        assert config['policies'] == expected_config['policies']
        rules = Rules.objects.filter(bot=bot['_id'].__str__())
        assert len(rules) == 3
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot['_id'].__str__(), status=True).get()
        assert Responses.objects(name='utter_default', bot=bot['_id'].__str__(), status=True).get()

    def test_update_bot_with_character_limit_exceeded(self):
        name = "supercalifragilisticexpialidociousalwaysworksmorethan60characters"
        with pytest.raises(AppException, match='Bot Name cannot be more than 60 characters.'):
            AccountProcessor.update_bot(name=name, bot=pytest.bot)

    def test_list_bots(self):
        bot = list(AccountProcessor.list_bots(pytest.account))
        assert bot[0]['name'] == 'test'
        assert bot[0]['_id']

    def test_get_bot(self):
        bot_response = AccountProcessor.get_bot(pytest.bot)
        assert bot_response
        assert bot_response["account"] == pytest.account

    def test_add_duplicate_bot(self):
        with pytest.raises(Exception):
            AccountProcessor.add_bot("test", pytest.account, "testAdmin")

    def test_add_duplicate_bot_case_insensitive(self):
        with pytest.raises(Exception):
            AccountProcessor.add_bot("TEST", pytest.account, "testAdmin")

    def test_add_blank_bot(self):
        with pytest.raises(AppException):
            AccountProcessor.add_bot(" ", pytest.account, "testAdmin")

    def test_add_empty_bot(self):
        with pytest.raises(AppException):
            AccountProcessor.add_bot("", pytest.account, "testAdmin")

    def test_add_none_bot(self):
        with pytest.raises(AppException):
            AccountProcessor.add_bot(None, pytest.account, "testAdmin")

    def test_add_none_user(self):
        with pytest.raises(AppException):
            AccountProcessor.add_bot('test', pytest.account, None)

    def test_add_user(self):
        user = AccountProcessor.add_user(
            email="fshaikh@digite.com",
            first_name="Fahad Ali",
            last_name="Shaikh",
            password="Welcome@1",
            account=pytest.account,
            user="testAdmin",
        )
        assert user
        assert user["password"] != "12345"
        assert user["status"]

    def test_add_bot_for_existing_user(self):
        bot_response = AccountProcessor.add_bot("test_version_2", pytest.account, "fshaikh@digite.com", False)
        bot = Bot.objects(name="test_version_2").get().to_mongo().to_dict()
        assert bot['_id'].__str__() == bot_response['_id'].__str__()
        assert len(
            AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned']) == 2
        config = Configs.objects(bot=bot['_id'].__str__()).get().to_mongo().to_dict()
        expected_config = Utility.read_yaml(Utility.environment["model"]["train"]["default_model_training_config_path"])
        assert config['language'] == expected_config['language']
        assert config['pipeline'] == expected_config['pipeline']
        assert config['policies'] == expected_config['policies']
        assert config['policies'][2]['name'] == 'RulePolicy'
        assert config['policies'][2]['core_fallback_action_name'] == "action_default_fallback"
        assert config['policies'][2]['core_fallback_threshold'] == 0.5
        assert config["policies"][2]["max_history"] == 5
        rules = Rules.objects.filter(bot=bot['_id'].__str__())
        assert len(rules) == 3
        assert Responses.objects(name='utter_default', bot=bot['_id'].__str__(), status=True).get()

    def test_add_member_already_exists(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        with pytest.raises(AppException, match='User is already a collaborator'):
            AccountProcessor.allow_bot_and_generate_invite_url(bot_id, "fshaikh@digite.com", 'testAdmin',
                                                               pytest.account, ACCESS_ROLES.DESIGNER.value)

    def test_add_member_bot_not_exists(self):
        with pytest.raises(DoesNotExist, match='Bot does not exists!'):
            AccountProcessor.allow_bot_and_generate_invite_url('bot_not_exists', "fshaikh@digite.com", 'testAdmin',
                                                               pytest.account)

    def test_list_bot_accessors_1(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        accessors = list(AccountProcessor.list_bot_accessors(bot_id))
        assert len(accessors) == 1
        assert accessors[0]['accessor_email'] == 'fshaikh@digite.com'
        assert accessors[0]['role'] == 'owner'
        assert accessors[0]['bot']
        assert accessors[0]['bot_account'] == pytest.account
        assert accessors[0]['user'] == "fshaikh@digite.com"
        assert accessors[0]['timestamp']

    def test_update_bot_access_modify_bot_owner_access(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        with pytest.raises(AppException, match='Ownership modification denied'):
            AccountProcessor.update_bot_access(bot_id, "fshaikh@digite.com", 'testAdmin',
                                               ACCESS_ROLES.OWNER.value, ACTIVITY_STATUS.INACTIVE.value)
        with pytest.raises(AppException, match='Ownership modification denied'):
            AccountProcessor.update_bot_access(bot_id, "fshaikh@digite.com", 'testAdmin',
                                               ACCESS_ROLES.ADMIN.value, ACTIVITY_STATUS.ACTIVE.value)

    def test_update_bot_access_user_not_exists(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        BotAccess(bot=bot_id, accessor_email="udit.pandey@digite.com", user='test',
                  role='designer', status='invite_not_accepted', bot_account=pytest.account).save()
        with pytest.raises(DoesNotExist, match='User does not exist!'):
            AccountProcessor.update_bot_access(bot_id, "udit.pandey@digite.com",
                                               ACCESS_ROLES.ADMIN.value, ACTIVITY_STATUS.INACTIVE.value)

    def test_update_bot_access_invite_not_accepted(self, monkeypatch):
        monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        User(email='udit.pandey@digite.com', first_name='udit', last_name='pandey', password='124556779', account=10,
             user='udit.pandey@digite.com').save()
        with pytest.raises(AppException, match='User is yet to accept the invite'):
            AccountProcessor.update_bot_access(bot_id, "udit.pandey@digite.com",
                                               ACCESS_ROLES.ADMIN.value, ACTIVITY_STATUS.INACTIVE.value)
        assert BotAccess.objects(bot=bot_id, accessor_email="udit.pandey@digite.com", user='test',
                                 role='designer', status='invite_not_accepted', bot_account=pytest.account).get()

    def test_list_active_invites(self):
        invite = list(AccountProcessor.list_active_invites("udit.pandey@digite.com"))
        assert invite[0]['accessor_email'] == 'udit.pandey@digite.com'
        assert invite[0]['role'] == 'designer'
        assert invite[0]['bot_name'] == 'test_version_2'

    def test_accept_bot_access_invite_user_not_exists(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        token = Utility.generate_token("pandey.udit867@gmail.com")
        with pytest.raises(DoesNotExist, match='User does not exist!'):
            AccountProcessor.validate_request_and_accept_bot_access_invite(token, bot_id)

    def test_update_bot_access_user_not_allowed(self):
        AccountProcessor.add_account('pandey.udit867@gmail.com', 'pandey.udit867@gmail.com')
        User(email='pandey.udit867@gmail.com', first_name='udit', last_name='pandey', password='124556779', account=10,
             user='pandey.udit867@gmail.com').save()
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        with pytest.raises(AppException, match='User not yet invited to collaborate'):
            AccountProcessor.update_bot_access(bot_id, "pandey.udit867@gmail.com",
                                               ACCESS_ROLES.ADMIN.value, ACTIVITY_STATUS.INACTIVE.value)

    def test_accept_bot_access_invite(self, monkeypatch):
        def _mock_get_user(*args, **kwargs):
            return None

        monkeypatch.setattr(AccountProcessor, 'get_user_details', _mock_get_user)

        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        token = Utility.generate_token("udit.pandey@digite.com")
        AccountProcessor.validate_request_and_accept_bot_access_invite(token, bot_id)
        assert BotAccess.objects(bot=bot_id, accessor_email="udit.pandey@digite.com", user='test',
                                 role='designer', status='active', bot_account=pytest.account).get()

    def test_list_active_invites_none(self):
        invite = list(AccountProcessor.list_active_invites("udit.pandey@digite.com"))
        assert invite == []

    def test_update_bot_access(self):
        account_bot_info = \
            AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]
        assert account_bot_info['role'] == 'owner'
        bot_id = account_bot_info['_id']
        assert ('test_version_2', 'fshaikh@digite.com', 'Fahad Ali', 'udit') == AccountProcessor.update_bot_access(
            bot_id, "udit.pandey@digite.com", 'testAdmin', ACCESS_ROLES.ADMIN.value, ACTIVITY_STATUS.ACTIVE.value
        )
        bot_access = BotAccess.objects(bot=bot_id, accessor_email="udit.pandey@digite.com").get()
        assert bot_access.role == ACCESS_ROLES.ADMIN.value
        assert bot_access.status == ACTIVITY_STATUS.ACTIVE.value
        shared_bot_info = AccountProcessor.get_accessible_bot_details(4, "udit.pandey@digite.com")['shared'][0]
        assert shared_bot_info['role'] == 'admin'
        assert shared_bot_info['_id'] == bot_id

        with pytest.raises(AppException, match='Ownership modification denied'):
            AccountProcessor.update_bot_access(bot_id, "udit.pandey@digite.com", 'testAdmin',
                                               ACCESS_ROLES.OWNER.value, ACTIVITY_STATUS.ACTIVE.value)
        bot_access = BotAccess.objects(bot=bot_id, accessor_email="udit.pandey@digite.com").get()
        assert bot_access.role == ACCESS_ROLES.ADMIN.value
        assert bot_access.status == ACTIVITY_STATUS.ACTIVE.value

    def test_update_bot_access_invalid_role(self):
        account_bot_info = \
            AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]
        assert account_bot_info['role'] == 'owner'
        bot_id = account_bot_info['_id']

        with pytest.raises(ValidationError):
            AccountProcessor.update_bot_access(bot_id, "udit.pandey@digite.com", 'testAdmin', "test",
                                               ACTIVITY_STATUS.ACTIVE.value)

    def test_update_bot_access_to_same_role(self):
        account_bot_info = \
            AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]
        assert account_bot_info['role'] == 'owner'
        bot_id = account_bot_info['_id']

        with pytest.raises(AppException, match='User is already admin of the bot'):
            AccountProcessor.update_bot_access(bot_id, "udit.pandey@digite.com", 'testAdmin',
                                               ACCESS_ROLES.ADMIN.value, ACTIVITY_STATUS.ACTIVE.value)

    def test_accept_bot_access_invite_user_not_allowed(self, monkeypatch):
        def _mock_get_user(*args, **kwargs):
            return None

        monkeypatch.setattr(AccountProcessor, 'get_user_details', _mock_get_user)

        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        token = Utility.generate_token("pandey.udit867@gmail.com")
        with pytest.raises(AppException, match='No pending invite found for this bot and user'):
            AccountProcessor.validate_request_and_accept_bot_access_invite(token, bot_id)

    def test_accept_bot_access_invite_token_expired(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6InBhbmRleS51ZGl0ODY3QGdtYWlsLmNvbSIsImV4cCI6MTUxNjIzOTAyMn0.dP8a4rHXb9dBrPFKfKD3_tfKu4NdwfSz213F15qej18'
        with pytest.raises(AppException, match='Invalid token'):
            AccountProcessor.validate_request_and_accept_bot_access_invite(token, bot_id)

    def test_accept_bot_access_invite_invalid_bot(self):
        token = Utility.generate_token("fshaikh@digite.com")
        with pytest.raises(DoesNotExist, match='Bot does not exists!'):
            AccountProcessor.validate_request_and_accept_bot_access_invite(token, '61cb4e2f7c7ac78d2fa8fab7')

    def test_list_bot_accessors_2(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        accessors = list(AccountProcessor.list_bot_accessors(bot_id))
        assert accessors[0]['accessor_email'] == 'fshaikh@digite.com'
        assert accessors[0]['role'] == 'owner'
        assert accessors[0]['bot']
        assert accessors[0]['bot_account'] == pytest.account
        assert accessors[0]['user'] == "fshaikh@digite.com"
        assert accessors[0]['timestamp']
        assert accessors[1]['accessor_email'] == 'udit.pandey@digite.com'
        assert accessors[1]['role'] == 'admin'
        assert accessors[1]['bot']
        assert accessors[1]['bot_account'] == pytest.account
        assert accessors[1]['user'] == 'testAdmin'
        assert accessors[1]['accept_timestamp']
        assert accessors[1]['timestamp']

    def test_invite_user_as_owner(self):
        with pytest.raises(AppException, match='There can be only 1 owner per bot'):
            AccountProcessor.allow_bot_and_generate_invite_url('test', 'user@demo.ai', 'admin@demo.ai', 2,
                                                               ACCESS_ROLES.OWNER.value)

    def test_transfer_ownership(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        AccountProcessor.transfer_ownership(pytest.account, bot_id, "fshaikh@digite.com", 'udit.pandey@digite.com')
        accessors = list(AccountProcessor.list_bot_accessors(bot_id))
        assert accessors[0]['accessor_email'] == 'fshaikh@digite.com'
        assert accessors[0]['role'] == 'admin'
        assert accessors[0]['bot']
        assert accessors[0]['bot_account'] == 10
        assert accessors[0]['user'] == "fshaikh@digite.com"
        assert accessors[1]['accessor_email'] == 'udit.pandey@digite.com'
        assert accessors[1]['role'] == 'owner'
        assert accessors[1]['bot']
        assert accessors[1]['bot_account'] == 10
        assert accessors[1]['user'] == "fshaikh@digite.com"
        assert AccountProcessor.get_bot_and_validate_status(bot_id)['account'] == 10

        AccountProcessor.transfer_ownership(pytest.account, bot_id, 'udit.pandey@digite.com', "fshaikh@digite.com")
        accessors = list(AccountProcessor.list_bot_accessors(bot_id))
        assert accessors[0]['accessor_email'] == 'fshaikh@digite.com'
        assert accessors[0]['role'] == 'owner'
        assert accessors[0]['bot']
        assert accessors[0]['bot_account'] == pytest.account
        assert accessors[0]['user'] == 'udit.pandey@digite.com'
        assert accessors[1]['accessor_email'] == 'udit.pandey@digite.com'
        assert accessors[1]['role'] == 'admin'
        assert accessors[1]['bot']
        assert accessors[1]['bot_account'] == pytest.account
        assert accessors[1]['user'] == 'udit.pandey@digite.com'
        assert AccountProcessor.get_bot_and_validate_status(bot_id)['account'] == pytest.account

    def test_transfer_ownership_to_non_member(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        User(email='udit@demo.ai', first_name='udit', last_name='pandey', password='124556779', account=10,
             user='udit@demo.ai').save()
        with pytest.raises(AppException, match='User not yet invited to collaborate'):
            AccountProcessor.transfer_ownership(pytest.account, bot_id, "fshaikh@digite.com", 'udit@demo.ai')

    def test_remove_bot_access_not_a_member(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        with pytest.raises(AppException, match='User not a collaborator to this bot'):
            AccountProcessor.remove_bot_access(bot_id, accessor_email='pandey.udit867@gmail.com')

    def test_remove_bot_access(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1][
            '_id']
        assert not AccountProcessor.remove_bot_access(bot_id, accessor_email='udit.pandey@digite.com')
        assert len(list(AccountProcessor.list_bot_accessors(bot_id))) == 1

    def test_remove_bot_from_all_accessors(self):
        bot_id = str(ObjectId())
        BotAccess(bot=bot_id, accessor_email="udit.pandey@digite.com", user='test',
                  role='designer', status='active', bot_account=10).save()
        BotAccess(bot=bot_id, accessor_email="pandey.udit867@gmail.com", user='test',
                  role='designer', status='invite_not_accepted', bot_account=10).save()
        BotAccess(bot=bot_id, accessor_email="pandey.udit@gmail.com", user='test',
                  role='designer', status='inactive', bot_account=10).save()
        BotAccess(bot=bot_id, accessor_email="udit867@gmail.com", user='test',
                  role='designer', status='deleted', bot_account=10).save()
        assert len(list(AccountProcessor.list_bot_accessors(bot_id))) == 3
        AccountProcessor.remove_bot_access(bot_id)
        assert len(list(AccountProcessor.list_bot_accessors(bot_id))) == 0

    def test_list_bots_2(self):
        bot = list(AccountProcessor.list_bots(pytest.account))
        assert bot[0]['name'] == 'test'
        assert bot[0]['_id']
        assert bot[1]['name'] == 'test_version_2'
        assert bot[1]['_id']

    def test_update_bot_name(self):
        AccountProcessor.update_bot('test_bot', pytest.bot)
        bot = list(AccountProcessor.list_bots(pytest.account))
        assert bot[0]['name'] == 'test_bot'
        assert bot[0]['_id']

    def test_update_bot_not_exists(self):
        with pytest.raises(AppException):
            AccountProcessor.update_bot('test_bot', '5f256412f98b97335c168ef0')

    def test_update_bot_empty_name(self):
        with pytest.raises(AppException):
            AccountProcessor.update_bot(' ', '5f256412f98b97335c168ef0')

    def test_delete_bot(self):
        bot = list(AccountProcessor.list_bots(pytest.account))
        pytest.deleted_bot = bot[1]['_id']
        AccountProcessor.delete_bot(pytest.deleted_bot)
        with pytest.raises(DoesNotExist):
            Bot.objects(id=pytest.deleted_bot, status=True).get()
        bots = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")
        assert len(bots['account_owned']) == 1
        assert pytest.deleted_bot not in [bot['_id'] for bot in bots['account_owned']]
        assert pytest.deleted_bot not in [bot['_id'] for bot in bots['shared']]

    def test_delete_bot_not_exists(self):
        with pytest.raises(AppException):
            AccountProcessor.delete_bot(pytest.deleted_bot)

    def test_delete_account_for_account_bots(self):
        account = {
            "account": "Test_Delete_Account",
            "email": "ritika@digite.com",
            "first_name": "Test_Delete_First",
            "last_name": "Test_Delete_Last",
            "password": SecretStr("Welcome@1"),
            "accepted_privacy_policy": True,
            "accepted_terms": True
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

        pytest.deleted_account = user_detail['account'].__str__()
        AccountProcessor.add_bot("delete_account_bot_1", pytest.deleted_account, "ritika@digite.com", False)
        AccountProcessor.add_bot("delete_account_bot_2", pytest.deleted_account, "ritika@digite.com", False)
        account_bots_before_delete = list(AccountProcessor.list_bots(pytest.deleted_account))

        assert len(account_bots_before_delete) == 2
        AccountProcessor.delete_account(pytest.deleted_account)

        for bot in account_bots_before_delete:
            with pytest.raises(DoesNotExist):
                Bot.objects(id=bot['_id'], account=pytest.deleted_account, status=True).get()

    def test_delete_account_for_shared_bot(self):
        account = {
            "account": "Test_Delete_Account",
            "email": "ritika@digite.com",
            "first_name": "Test_Delete_First",
            "last_name": "Test_Delete_Last",
            "password": SecretStr("Welcome@1"),
            "accepted_privacy_policy": True,
            "accepted_terms": True
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(
            AccountProcessor.account_setup(account_setup=account))

        # Add shared bot
        bot_response = AccountProcessor.add_bot("delete_account_shared_bot", user_detail['account'], "udit.pandey@digite.com", False)
        bot_id = bot_response['_id'].__str__()
        BotAccess(bot=bot_id, accessor_email="ritika@digite.com", user='testAdmin',
                  role='designer', status='active', bot_account=user_detail['account']).save()
        pytest.deleted_account = user_detail['account'].__str__()
        accessors_before_delete = list(AccountProcessor.list_bot_accessors(bot_id))

        assert len(accessors_before_delete) == 2
        assert accessors_before_delete[0]['accessor_email'] == 'udit.pandey@digite.com'
        assert accessors_before_delete[1]['accessor_email'] == 'ritika@digite.com'
        AccountProcessor.delete_account(pytest.deleted_account)
        accessors_after_delete = list(AccountProcessor.list_bot_accessors(bot_id))
        assert len(accessors_after_delete) == 0
        assert len(list(Bot.objects(id=bot_id, account=user_detail['account'], status=True))) == 0

    def test_delete_account_for_account(self):
        account = {
            "account": "Test_Delete_Account",
            "email": "ritika@digite.com",
            "first_name": "Test_Delete_First",
            "last_name": "Test_Delete_Last",
            "password": SecretStr("Welcome@1"),
            "accepted_privacy_policy": True,
            "accepted_terms": True
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(
            AccountProcessor.account_setup(account_setup=account))
        pytest.deleted_account = user_detail['account'].__str__()

        AccountProcessor.delete_account(pytest.deleted_account)
        assert AccountProcessor.get_account(pytest.deleted_account)
        assert not AccountProcessor.get_account(pytest.deleted_account).get('status')

        with pytest.raises(AppException, match="Account does not exist!"):
            AccountProcessor.delete_account(pytest.deleted_account)

    def test_delete_account_for_user(self):
        account = {
            "account": "Test_Delete_Account",
            "email": "ritika@digite.com",
            "first_name": "Test_Delete_First",
            "last_name": "Test_Delete_Last",
            "password": SecretStr("Welcome@1"),
            "accepted_privacy_policy": True,
            "accepted_terms": True
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(
            AccountProcessor.account_setup(account_setup=account))
        pytest.deleted_account = user_detail['account'].__str__()

        # Add Multiple user to same account
        user = {
            "account": pytest.deleted_account,
            "email": "ritika.G@digite.com",
            "first_name": "Test_Delete_First1",
            "last_name": "Test_Delete_Last1",
            "password": "Welcome@2",
            "user": "testAdmin"
        }
        AccountProcessor.add_user(**user)

        assert User.objects(email__iexact="ritika@digite.com", status=True).get()
        assert User.objects(email__iexact="ritika.G@digite.com", status=True).get()

        AccountProcessor.delete_account(pytest.deleted_account)

        assert User.objects(email__iexact="ritika@digite.com", status=False)
        assert User.objects(email__iexact="ritika.G@digite.com", status=False)

    def test_delete_account_again_add(self):
        account = {
            "account": "Test_Delete_Account",
            "email": "ritika@digite.com",
            "first_name": "Test_Delete_First",
            "last_name": "Test_Delete_Last",
            "password": SecretStr("Welcome@1"),
            "accepted_privacy_policy": True,
            "accepted_terms": True
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(
            AccountProcessor.account_setup(account_setup=account))
        pytest.deleted_account = user_detail['account'].__str__()

        AccountProcessor.delete_account(pytest.deleted_account)

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(
            AccountProcessor.account_setup(account_setup=account))
        new_account_id = user_detail['account'].__str__()

        assert new_account_id
        assert AccountProcessor.get_account(new_account_id).get('status')
        assert len(list(AccountProcessor.list_bots(new_account_id))) == 0

    def test_add_user_duplicate(self):
        with pytest.raises(Exception):
            AccountProcessor.add_user(
                email="fshaikh@digite.com",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_duplicate_case_insensitive(self):
        with pytest.raises(Exception):
            AccountProcessor.add_user(
                email="FShaikh@digite.com",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_empty_email(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_blank_email(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email=" ",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_invalid_email(self):
        with pytest.raises(ValidationError):
            AccountProcessor.add_user(
                email="demo",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_none_email(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email=None,
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_empty_firstname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_blank_firstname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name=" ",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_none_firstname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="",
                last_name="Shaikh",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_empty_lastname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_none_lastname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name=None,
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_blank_lastname(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name=" ",
                password="Welcome@1",
                account=1,
                user="testAdmin",
            )

    def test_add_user_empty_password(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password="",
                account=1,
                user="testAdmin",
            )

    def test_add_user_blank_password(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password=" ",
                account=1,
                user="testAdmin",
            )

    def test_add_user_None_password(self):
        with pytest.raises(AppException):
            AccountProcessor.add_user(
                email="demo@demo.ai",
                first_name="Fahad Ali",
                last_name="Shaikh",
                password=None,
                account=1,
                user="testAdmin",
            )

    def test_get_user(self):
        user = AccountProcessor.get_user("fshaikh@digite.com")
        assert all(
            user[key] is False if key in {"is_integration_user", "is_onboarded"} else user[key]
            for key in user.keys()
        )

    def test_get_user_not_exists(self):
        with pytest.raises(DoesNotExist, match='User does not exist!'):
            AccountProcessor.get_user("udit.pandey_kairon@digite.com")

    def test_get_user_details(self):
        user = AccountProcessor.get_user_details("fshaikh@digite.com")
        assert all(
            user[key] is False if key in {"is_integration_user", "is_onboarded"} else user[key]
            for key in user.keys()
        )

    def test_get_user_details_inactive_user(self, monkeypatch):
        def _mock_get_user(*args, **kwargs):
            return User(
                email="nupur@gmail.com",
                password=Utility.get_password_hash("password"),
                first_name="nupur",
                last_name="khare",
                account=1001,
                user="nupur@gmail.com",
                status=False
            ).to_mongo().to_dict()

        monkeypatch.setattr(AccountProcessor, "get_user", _mock_get_user)
        with pytest.raises(ValidationError):
            AccountProcessor.get_user_details("nupur@gmail.com", True)
        value = list(AuditLogData.objects(attributes__key='account', attributes__value=1001).order_by("-timestamp"))
        assert value[0]["entity"] == "invalid_login"
        assert value[0]["action"] == 'activity'
        assert value[0]["user"] == "nupur@gmail.com"
        assert value[0]["timestamp"]
        assert value[0]["data"] == {'message': ['Inactive User please contact admin!'], 'username': 'nupur@gmail.com'}

    def test_get_user_details_inactive_account(self, monkeypatch):
        def _mock_get_user(*args, **kwargs):
            return User(
                email="nupur@gmail.com",
                password=Utility.get_password_hash("password"),
                first_name="nupur",
                last_name="khare",
                account=1001,
                user="nupur@gmail.com",
                status=True
            ).to_mongo().to_dict()

        def _mock_get_account(*args, **kwargs):
            return Account(
                id=1000,
                name="nupur",
                user="nupur@gmail.com",
                status=False
            ).to_mongo().to_dict()

        monkeypatch.setattr(AccountProcessor, "get_user", _mock_get_user)
        monkeypatch.setattr(AccountProcessor, "get_account", _mock_get_account)
        with pytest.raises(ValidationError):
            AccountProcessor.get_user_details("nupur@gmail.com", True)
        value = list(AuditLogData.objects(attributes__key='account', attributes__value=1001).order_by("-timestamp"))
        assert value[0]["entity"] == "invalid_login"
        assert value[0]["action"] == 'activity'
        assert value[0]["user"] == "nupur@gmail.com"
        assert value[0]["timestamp"]
        assert value[0]["data"] == {'message': ['Inactive Account Please contact system admin!'],
                                    'username': 'nupur@gmail.com'}

    @pytest.fixture
    def mock_user_inactive(self, monkeypatch):
        def user_response(*args, **kwargs):
            return {
                "email": "demo@demo.ai",
                "status": False,
                "bot": "support",
                "account": 2,
                "is_integration_user": False
            }

        def bot_response(*args, **kwargs):
            return {"name": "support", "status": True}

        def account_response(*args, **kwargs):
            return {"name": "paytm", "status": True}

        monkeypatch.setattr(AccountProcessor, "get_user", user_response)
        monkeypatch.setattr(AccountProcessor, "get_bot", bot_response)
        monkeypatch.setattr(AccountProcessor, "get_account", account_response)

    def test_get_user_details_user_inactive(self, mock_user_inactive):
        with pytest.raises(ValidationError):
            user_details = AccountProcessor.get_user_details("demo@demo.ai")
            assert all(
                user_details[key] is False
                if key == "is_integration_user"
                else user_details[key]
                for key in user_details.keys()
            )

    @pytest.fixture
    def mock_bot_inactive(self, monkeypatch):
        def user_response(*args, **kwargs):
            return {
                "email": "demo@demo.ai",
                "status": True,
                "bot": "support",
                "account": 2,
                "is_integration_user": False
            }

        def bot_response(*args, **kwargs):
            return {"name": "support", "status": False}

        def account_response(*args, **kwargs):
            return {"name": "paytm", "status": True}

        monkeypatch.setattr(AccountProcessor, "get_user", user_response)
        monkeypatch.setattr(AccountProcessor, "get_bot", bot_response)
        monkeypatch.setattr(AccountProcessor, "get_account", account_response)

    def test_get_user_details_bot_inactive(self, mock_bot_inactive, monkeypatch):
        monkeypatch.setitem(Utility.email_conf["email"], 'enable', True)
        with pytest.raises(AppException) as e:
            AccountProcessor.get_user_details("demo@demo.ai")
        assert str(e).__contains__('Please verify your mail')

    @pytest.fixture
    def mock_account_inactive(self, monkeypatch):
        def user_response(*args, **kwargs):
            return {
                "email": "demo@demo.ai",
                "status": True,
                "bot": "support",
                "account": 2,
                "is_integration_user": False
            }

        def bot_response(*args, **kwargs):
            return {"name": "support", "status": True}

        def account_response(*args, **kwargs):
            return {"name": "paytm", "status": False}

        monkeypatch.setattr(AccountProcessor, "get_user", user_response)
        monkeypatch.setattr(AccountProcessor, "get_bot", bot_response)
        monkeypatch.setattr(AccountProcessor, "get_account", account_response)

    def test_get_user_details_account_inactive(self, mock_account_inactive):
        with pytest.raises(ValidationError):
            user_details = AccountProcessor.get_user_details("demo@demo.ai")
            assert all(
                user_details[key] is False
                if key == "is_integration_user"
                else user_details[key]
                for key in AccountProcessor.get_user_details(
                    user_details["email"]
                ).keys()
            )

    def test_account_setup_empty_values(self):
        account = {"email": "demo@ac.in"}
        with pytest.raises(AppException):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

    def test_account_setup_missing_account(self):
        account = {
            "bot": "Test",
            "email": "demo@ac.in",
            "first_name": "Test_First",
            "last_name": "Test_Last",
            "password": "welcome@1",
        }
        with pytest.raises(AppException):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

    def test_account_setup_user_info(self, monkeypatch):
        def _publish_auditlog(*args, **kwargs):
            return

        monkeypatch.setattr(AuditDataProcessor, "save_and_publish_auditlog", _publish_auditlog)
        account = {
            "account": "Test_Account",
            "bot": "Test",
            "email": "test@demo.in",
            "first_name": "Test_First",
            "last_name": "Test_Last",
            "password": SecretStr("Welcome@1"),
            "accepted_terms": True
        }
        with pytest.raises(AppException):
            loop = asyncio.new_event_loop()
            loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

    def test_account_setup(self):
        account = {
            "account": "Test_Account",
            "email": "demo@ac.in",
            "first_name": "Test_First",
            "last_name": "Test_Last",
            "password": SecretStr("Welcome@1"),
            "accepted_privacy_policy": True,
            "accepted_terms": True
        }
        loop = asyncio.new_event_loop()
        actual, mail, link = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))
        assert actual["_id"]
        assert actual["account"]
        assert actual["first_name"]
        assert len(list(AccountProcessor.list_bots(actual['account']))) == 0

    def test_default_account_setup(self):
        loop = asyncio.new_event_loop()
        actual, mail, link = loop.run_until_complete(AccountProcessor.default_account_setup())
        assert actual

    async def mock_smtp(self, *args, **kwargs):
        return None

    def test_validate_and_send_mail(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(MailUtility.validate_and_send_mail('demo@ac.in', subject='test', body='test'))
        assert True

    def test_send_false_email_id(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(MailUtility.validate_and_send_mail('..', subject='test', body="test"))

    def test_send_empty_mail_subject(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(MailUtility.validate_and_send_mail('demo@ac.in', subject=' ', body='test'))

    def test_send_empty_mail_body(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(MailUtility.validate_and_send_mail('demo@ac.in', subject='test', body=' '))

    def test_format_and_send_mail_invalid_type(self):
        loop = asyncio.new_event_loop()
        assert not loop.run_until_complete(MailUtility.format_and_send_mail('training_failure', 'demo@ac.in', 'udit'))

    def test_valid_token(self):
        token = Utility.generate_token('integ1@gmail.com')
        mail = Utility.verify_token(token).get("mail_id")
        assert mail

    def test_invalid_token(self):
        with pytest.raises(Exception):
            Utility.verify_token('..')

    def test_new_user_confirm(self, monkeypatch):
        AccountProcessor.add_user(
            email="integ2@gmail.com",
            first_name="inteq",
            last_name="2",
            password='Welcome@1',
            account=1,
            user="testAdmin",
        )
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('integ2@gmail.com')
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.confirm_email(token))
        assert True

    def test_user_already_confirmed(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        token = Utility.generate_token('integ2@gmail.com')
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.confirm_email(token))

    def test_user_not_confirmed(self):
        with pytest.raises(Exception):
            AccountProcessor.is_user_confirmed('sd')

    def test_user_confirmed(self):
        AccountProcessor.is_user_confirmed('integ2@gmail.com')
        assert True

    def test_send_empty_token(self):
        with pytest.raises(Exception):
            Utility.verify_token(' ')

    def test_reset_link_with_mail(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(AccountProcessor.send_reset_link('integ2@gmail.com'))
        assert result[0] == 'integ2@gmail.com'
        assert result[1] == 'inteq'
        assert result[2].__contains__('kairon.digite.com/reset_password/')
        Utility.email_conf["email"]["enable"] = False

    def test_reset_link_with_mail_limit_exceeded(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setitem(Utility.environment['user'], 'reset_password_request_limit', 2)
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(AccountProcessor.send_reset_link('integ2@gmail.com'))
        assert result[0] == 'integ2@gmail.com'
        assert result[1] == 'inteq'
        assert result[2].__contains__('kairon.digite.com/reset_password/')

        with pytest.raises(AppException, match='Password reset limit exhausted for today.'):
            loop.run_until_complete(AccountProcessor.send_reset_link('integ2@gmail.com'))
        Utility.email_conf["email"]["enable"] = False

    def test_reset_link_with_empty_mail(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link(''))
        Utility.email_conf["email"]["enable"] = False

    def test_reset_link_with_unregistered_mail(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link('sasha.41195@gmail.com'))
        Utility.email_conf["email"]["enable"] = False

    def test_reset_link_with_unconfirmed_mail(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link('integration@demo.ai'))
        Utility.email_conf["email"]["enable"] = False

    def test_overwrite_password_with_invalid_token(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.overwrite_password('fgh', "asdfghj@1"))

    def test_overwrite_password_with_empty_password_string(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.overwrite_password(
                'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20',
                " "))

    def test_overwrite_password_with_valid_entries(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('integ2@gmail.com')
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@3"))
        assert True

    def test_overwrite_password_limit_exceeded(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('integ2@gmail.com')
        loop = asyncio.new_event_loop()
        with pytest.raises(AppException, match='Password reset limit exhausted. Please come back in *'):
            loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@3"))

    @mock.patch('kairon.shared.account.activity_log.UserActivityLogger.is_password_reset_within_cooldown_period',
                autospec=True)
    def test_overwrite_password_email_password_same(self, mock_password_reset, monkeypatch):
        def _password_reset(*args, **kwargs):
            return

        mock_password_reset.return_value = _password_reset
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('integ2@gmail.com')
        loop = asyncio.new_event_loop()
        with pytest.raises(AppException, match='Email cannot be used as password!'):
            loop.run_until_complete(AccountProcessor.overwrite_password(token, "integ2@gmail.com"))

    def test_reset_link_not_within_cooldown_period(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(AppException, match='Password reset limit exhausted. Please come back in *'):
            loop.run_until_complete(AccountProcessor.send_reset_link('integ2@gmail.com'))
        Utility.email_conf["email"]["enable"] = False

    def test_send_confirmation_link_with_valid_id(self, monkeypatch):
        AccountProcessor.add_user(
            email="integ3@gmail.com",
            first_name="inteq",
            last_name="3",
            password='Welcome@1',
            account=1,
            user="testAdmin",
        )
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.send_confirmation_link('integ3@gmail.com'))
        Utility.email_conf["email"]["enable"] = False
        assert True

    def test_send_confirmation_link_with_confirmed_id(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link('integ1@gmail.com'))
        Utility.email_conf["email"]["enable"] = False

    def test_send_confirmation_link_with_invalid_id(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link(''))
        Utility.email_conf["email"]["enable"] = False

    def test_send_confirmation_link_with_unregistered_id(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link('sasha.41195@gmail.com'))
        Utility.email_conf["email"]["enable"] = False

    def test_reset_link_with_mail_not_enabled(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link('integ1@gmail.com'))

    def test_send_confirmation_link_with_mail_not_enabled(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link('integration@demo.ai'))

    def test_create_authentication_token_with_expire_time(self, monkeypatch):
        start_date = datetime.datetime.now()
        token = Authentication.create_access_token(data={"sub": "test"}, token_expire=180)
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert round((datetime.datetime.fromtimestamp(payload.get('exp')) - start_date).total_seconds() / 60) == 180
        assert payload["version"] == "2.0"
        assert not Utility.check_empty_string(payload['sub'])
        claims = Utility.decrypt_message(payload['sub'])
        claims = json.loads(claims)
        assert claims["sub"] == 'test'

        start_date = datetime.datetime.now()
        token = Authentication.create_access_token(data={"sub": "test"})
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert round((datetime.datetime.fromtimestamp(payload.get('exp')) - start_date).total_seconds() / 60) == 10080

        monkeypatch.setitem(Utility.environment['security'], 'token_expire', None)
        start_date = datetime.datetime.now()
        token = Authentication.create_access_token(data={"sub": "test"})
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert round((datetime.datetime.fromtimestamp(payload.get('exp')) - start_date).total_seconds() / 60) == 15

        start_date = datetime.datetime.now()
        token = Authentication.create_access_token(data={"sub": "test"}, token_type='INVALID_TYPE')
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert round((datetime.datetime.fromtimestamp(payload.get('exp')) - start_date).total_seconds() / 60) == 15

    def test_authenticate_method(self):
        AccountProcessor.add_user(
            email="nupur.khare@digite.com",
            first_name="Nupur",
            last_name="Khare",
            password="Welcome@15",
            account=pytest.account,
            user="testAdmin",
        )
        username = "nupur.khare@digite.com"
        password = "Welcome@15"
        access_token, access_token_expiry, new_refresh_token, refresh_token_expiry = Authentication.authenticate(
            username, password)
        refresh_token_expiry = datetime.datetime.fromtimestamp(refresh_token_expiry, tz=datetime.timezone.utc)

        payload = Utility.decode_limited_access_token(access_token)
        assert payload.get("sub") == username
        assert payload.get("type") == TOKEN_TYPE.LOGIN.value
        assert payload.get("iat")
        assert payload.get("exp")
        data = Utility.decode_limited_access_token(new_refresh_token)
        assert data.get("sub") == username
        assert data.get("exp")
        iat = datetime.datetime.fromtimestamp(data.get('iat'), tz=datetime.timezone.utc)
        assert data.get("ttl")
        assert data.get("type") == TOKEN_TYPE.REFRESH.value
        assert data.get("primary-token-type") == TOKEN_TYPE.LOGIN.value
        assert data.get("role") == ACCESS_ROLES.TESTER.value
        assert data.get("access-limit") == ['/api/auth/token/refresh']
        assert round((refresh_token_expiry - iat).total_seconds() / 60) == Utility.environment['security'][
            "refresh_token_expire"]

    def test_authenticate_incorrect_user(self):
        AccountProcessor.add_user(
            email="ABC@digite.com",
            first_name="Abc",
            last_name="efg",
            password="Welcome5463",
            account=pytest.account,
            user="testAdmin",
        )
        username = "A"
        password = "Welcome5463"
        with pytest.raises(DoesNotExist, match="User does not exist!"):
            Authentication.authenticate(username, password)

    def test_authenticate_user_does_not_exist(self):
        username = "abc@digite.com"
        password = "WSbchfk465"
        with pytest.raises(HTTPException):
            Authentication.authenticate(username, password)

    def test_generate_integration_token_login_token(self):
        bot = 'test'
        user = 'test_user'
        with pytest.raises(NotImplementedError):
            Authentication.generate_integration_token(bot, user, token_type=TOKEN_TYPE.LOGIN.value, role='chat')

    def test_generate_integration_token(self, monkeypatch):
        bot = 'test'
        user = 'test_user'
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]

        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        token, refresh_token = Authentication.generate_integration_token(bot, user, name='integration_token',
                                                                         role='chat')
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert payload["version"] == "2.0"
        assert not Utility.check_empty_string(payload['sub'])
        claims = Utility.decrypt_message(payload['sub'])
        payload = json.loads(claims)
        assert payload.get('bot') == bot
        assert payload.get('sub') == user
        assert payload.get('iat')
        assert payload.get('account') == 1000
        assert payload.get('type') == TOKEN_TYPE.INTEGRATION.value
        assert payload.get('role') == 'chat'
        assert not payload.get('exp')
        assert not refresh_token

    def test_generate_integration_token_different_bot(self, monkeypatch):
        bot = 'test_1'
        user = 'test_user'
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]

        def __mock_get_bot(*args, **kwargs):
            return {"account": 1001}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        token, _ = Authentication.generate_integration_token(bot, user, name='integration_token', role='tester')
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert payload["version"] == "2.0"
        assert not Utility.check_empty_string(payload['sub'])
        claims = Utility.decrypt_message(payload['sub'])
        payload = json.loads(claims)
        assert payload.get('bot') == bot
        assert payload.get('sub') == user
        assert payload.get('iat')
        assert payload.get('account') == 1001
        assert payload.get('type') == TOKEN_TYPE.INTEGRATION.value
        assert not payload.get('exp')
        assert payload.get('role') == 'tester'

    def test_generate_integration_token_with_expiry(self, monkeypatch):
        bot = 'test'
        user = 'test_user'
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]

        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        token, refresh_token = Authentication.generate_integration_token(
            bot, user, expiry=15, name='integration_token_with_expiry', role='designer'
        )
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert payload["version"] == "2.0"
        assert not Utility.check_empty_string(payload['sub'])
        claims = Utility.decrypt_message(payload['sub'])
        payload = json.loads(claims)
        assert payload.get('bot') == bot
        assert payload.get('sub') == user
        assert payload.get('iat')
        assert payload.get('type') == TOKEN_TYPE.INTEGRATION.value
        assert payload.get('role') == 'designer'
        iat = datetime.datetime.fromtimestamp(payload.get('iat'), tz=datetime.timezone.utc)
        exp = datetime.datetime.fromtimestamp(payload.get('exp'), tz=datetime.timezone.utc)
        assert round((exp - iat).total_seconds() / 60) == 15

        assert refresh_token
        claims = Utility.decode_limited_access_token(refresh_token)
        assert claims['iat'] == payload.get('iat')
        refresh_token_expiry = datetime.datetime.fromtimestamp(claims['exp'], tz=datetime.timezone.utc)
        assert round((refresh_token_expiry - iat).total_seconds() / 60) == 60
        del claims['iat']
        del claims['exp']
        assert claims == {'ttl': 15, 'bot': 'test', 'sub': 'test_user', 'type': 'refresh', 'role': 'tester',
                          'account': 1000, 'name': 'integration_token_with_expiry', 'primary-token-type': 'integration',
                          'primary-token-role': 'designer', 'primary-token-access-limit': None,
                          'access-limit': ['/api/auth/.+/token/refresh']}

    def test_generate_integration_token_with_access_limit(self, monkeypatch):
        bot = 'test1'
        user = 'test_user'
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]
        start_date = datetime.datetime.now(tz=datetime.timezone.utc)
        access_limit = ['/api/bot/endpoint']

        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        token, refresh_token = Authentication.generate_integration_token(bot, user, expiry=15,
                                                                         access_limit=access_limit,
                                                                         name='integration_token_with_access_limit',
                                                                         role='admin')
        pytest.refresh_token = refresh_token
        pytest.dynamic_token = token
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert payload["version"] == "2.0"
        assert not Utility.check_empty_string(payload['sub'])
        claims = Utility.decrypt_message(payload['sub'])
        payload = json.loads(claims)
        assert payload.get('bot') == bot
        assert payload.get('sub') == user
        assert payload.get('iat')
        pytest.integration_iat = payload.get('iat')
        assert payload.get('access-limit') == access_limit
        assert payload.get('type') == TOKEN_TYPE.INTEGRATION.value
        assert payload.get('role') == 'admin'
        iat = datetime.datetime.fromtimestamp(payload.get('iat'), tz=datetime.timezone.utc)
        exp = datetime.datetime.fromtimestamp(payload.get('exp'), tz=datetime.timezone.utc)
        assert round((exp - iat).total_seconds() / 60) == 15

        assert refresh_token
        claims = Utility.decode_limited_access_token(refresh_token)
        assert claims['iat'] == payload.get('iat')
        refresh_token_expiry = datetime.datetime.fromtimestamp(claims['exp'], tz=datetime.timezone.utc)
        assert round((refresh_token_expiry - iat).total_seconds() / 60) == 60
        del claims['iat']
        del claims['exp']
        assert claims == {'ttl': 15, 'bot': bot, 'sub': user, 'type': 'refresh', 'role': 'tester', 'account': 1000,
                          'name': 'integration_token_with_access_limit',
                          'primary-token-type': TOKEN_TYPE.INTEGRATION.value,
                          'primary-token-role': 'admin', 'primary-token-access-limit': access_limit,
                          'access-limit': ['/api/auth/.+/token/refresh']}

    def test_generate_non_dynamic_token_from_refresh_token(self):
        assert pytest.refresh_token
        with pytest.raises(HTTPException):
            Authentication.generate_token_from_refresh_token(pytest.refresh_token)

    def test_use_dynamic_token_to_refresh_token(self):
        assert pytest.dynamic_token
        with pytest.raises(HTTPException):
            Authentication.generate_token_from_refresh_token(pytest.dynamic_token)

    def test_generate_token_from_refresh_token(self, monkeypatch):
        bot = 'test1'
        user = 'test_user'
        access_limit = ['/api/bot/endpoint']

        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        token, refresh_token = Authentication.generate_integration_token(
            bot, user, expiry=15, access_limit=access_limit, token_type=TOKEN_TYPE.DYNAMIC.value,
            name='integration_token_with_access_limit', role='admin'
        )

        primary_token_claims = Utility.decode_limited_access_token(refresh_token)
        iat = datetime.datetime.fromtimestamp(primary_token_claims.get('iat'), tz=datetime.timezone.utc)
        assert refresh_token
        claims = Utility.decode_limited_access_token(refresh_token)
        assert claims['iat'] == primary_token_claims.get('iat')
        refresh_token_expiry = datetime.datetime.fromtimestamp(claims['exp'], tz=datetime.timezone.utc)
        assert round((refresh_token_expiry - iat).total_seconds() / 60) == 60
        del claims['iat']
        del claims['exp']
        assert claims == {'ttl': 15, 'bot': bot, 'sub': user, 'type': TOKEN_TYPE.REFRESH.value, 'role': 'tester',
                          'account': 1000,
                          'name': 'integration_token_with_access_limit',
                          'primary-token-type': TOKEN_TYPE.DYNAMIC.value,
                          'primary-token-role': 'admin', 'primary-token-access-limit': access_limit,
                          'access-limit': ['/api/auth/.+/token/refresh']}

        new_token, new_refresh_token = Authentication.generate_token_from_refresh_token(refresh_token)
        new_token_claims = Utility.decode_limited_access_token(new_token)
        assert new_token_claims['iat']
        new_token_iat = datetime.datetime.fromtimestamp(new_token_claims['iat'], tz=datetime.timezone.utc)
        new_token_expiry = datetime.datetime.fromtimestamp(new_token_claims['exp'], tz=datetime.timezone.utc)
        assert round((new_token_expiry - new_token_iat).total_seconds() / 60) == 15
        new_token_iat = new_token_claims.pop('iat')
        del new_token_claims['exp']
        assert new_token_claims == {'bot': bot, 'sub': user, 'type': 'dynamic', 'role': 'admin', 'account': 1000,
                                    'name': 'from refresh token', 'access-limit': access_limit}
        assert new_refresh_token
        claims = Utility.decode_limited_access_token(new_refresh_token)
        assert claims['iat'] == new_token_iat
        new_refresh_token_expiry = datetime.datetime.fromtimestamp(claims['exp'], tz=datetime.timezone.utc)
        assert round((new_refresh_token_expiry - iat).total_seconds() / 60) == 60
        del claims['iat']
        del claims['exp']
        assert claims == {'ttl': 15, 'bot': bot, 'sub': user, 'type': TOKEN_TYPE.REFRESH.value, 'role': 'tester',
                          'account': 1000,
                          'name': 'from refresh token',
                          'primary-token-type': TOKEN_TYPE.DYNAMIC.value,
                          'primary-token-role': 'admin', 'primary-token-access-limit': access_limit,
                          'access-limit': ['/api/auth/.+/token/refresh']}

    def test_generate_token_from_refresh_token_for_login_ex(self):
        user = AccountProcessor.get_user("nupur.khare@digite.com")
        assert pytest.refresh_token
        with pytest.raises(HTTPException):
            Authentication.generate_login_token_from_refresh_token(pytest.refresh_token, user)

    def test_token_from_dynamic_token_for_login(self):
        user = AccountProcessor.get_user("nupur.khare@digite.com")
        assert pytest.dynamic_token
        with pytest.raises(HTTPException):
            Authentication.generate_login_token_from_refresh_token(pytest.dynamic_token, user)

    def test_generate_login_token_from_refresh_token_test(self):
        AccountProcessor.add_user(
            email="nupurrkhare@digite.com",
            first_name="Nup",
            last_name="Urkhare",
            password="Welcome@1526",
            account=pytest.account,
            user="testAdmin",
        )
        username = "nupurrkhare@digite.com"
        user = AccountProcessor.get_user(username)
        access_token, access_token_exp, refresh_token, refresh_token_exp = Authentication.generate_login_tokens(
            user, True)
        payload = Utility.decode_limited_access_token(refresh_token)
        assert payload.get("sub") == user["email"]
        assert payload.get("type") == TOKEN_TYPE.REFRESH.value
        assert payload.get("primary-token-type") == TOKEN_TYPE.LOGIN.value
        assert payload.get("iat")
        assert payload.get("exp")
        assert payload.get("access-limit") == ['/api/auth/token/refresh']
        assert payload.get("role") == ACCESS_ROLES.TESTER.value
        assert payload.get("ttl")
        access, access_exp, refresh, refresh_exp = Authentication.generate_login_token_from_refresh_token(refresh_token,
                                                                                                          user)
        data_stack = Utility.decode_limited_access_token(refresh)
        value = list(AuditLogData.objects(attributes__key='account', attributes__value=pytest.account,
                                          entity="login_refresh_token").order_by("-timestamp"))
        assert value[0]['entity'] == "login_refresh_token"
        assert value[0]['user'] == "nupurrkhare@digite.com"
        assert value[0]['timestamp']

    def test_generate_token_from_refresh_token_for_login(self):
        user = AccountProcessor.get_user("nupur.khare@digite.com")
        access_token, access_token_exp, refresh_token, refresh_token_exp = Authentication.generate_login_tokens(
            user, True)
        payload = Utility.decode_limited_access_token(refresh_token)
        assert payload.get("sub") == user["email"]
        assert payload.get("type") == TOKEN_TYPE.REFRESH.value
        assert payload.get("primary-token-type") == TOKEN_TYPE.LOGIN.value
        assert payload.get("iat")
        assert payload.get("exp")
        assert payload.get("access-limit") == ['/api/auth/token/refresh']
        assert payload.get("role") == ACCESS_ROLES.TESTER.value
        assert payload.get("ttl")
        data = Utility.decode_limited_access_token(access_token)
        assert data.get("sub") == user["email"]
        assert data.get("exp")
        assert data.get("iat")
        assert data.get("type") == TOKEN_TYPE.LOGIN.value
        refresh_token_expiry = datetime.datetime.fromtimestamp(refresh_token_exp, tz=datetime.timezone.utc)
        iat = datetime.datetime.fromtimestamp(payload.get('iat'), tz=datetime.timezone.utc)
        assert round((refresh_token_expiry - iat).total_seconds() / 60) == Utility.environment['security'][
            "refresh_token_expire"]
        metering = list(
            AuditLogData.objects(attributes__key='account', attributes__value=user['account'], entity="login").order_by(
                "-timestamp"))
        assert metering[0]["entity"] == "login"
        assert metering[0]["user"] == "nupur.khare@digite.com"
        assert metering[0]["timestamp"]

        access, access_exp, refresh, refresh_exp = Authentication.generate_login_token_from_refresh_token(refresh_token,
                                                                                                          user)
        data_stack = Utility.decode_limited_access_token(refresh)
        value = list(AuditLogData.objects(attributes__key='account', attributes__value=user['account'],
                                          entity="login_refresh_token").order_by("-timestamp"))
        assert value[0]["entity"] == "login_refresh_token"
        assert value[0]["user"] == "nupur.khare@digite.com"
        assert value[0]["timestamp"]

    def test_authenticate_method_login_within_cooldown_period(self):
        username = "nupur.khare@digite.com"
        password = "HelloWorld"
        with pytest.raises(HTTPException):
            Authentication.authenticate(username, password)
        with pytest.raises(HTTPException):
            Authentication.authenticate(username, password)
        with pytest.raises(HTTPException):
            Authentication.authenticate(username, password)
        with pytest.raises(AppException, match='Account frozen due to too many unsuccessful login attempts. '
                                               f'Please come back in *'):
            Authentication.authenticate(username, password)

    def test_generate_integration_token_name_exists(self, monkeypatch):
        bot = 'test'
        user = 'test_user'

        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        with pytest.raises(AppException, match='Integration token with this name has already been initiated'):
            Authentication.generate_integration_token(bot, user, name='integration_token', role='chat')

    def test_generate_integration_token_limit_exceeded(self, monkeypatch):
        bot = 'test'
        user = 'test_user'

        def _mock_get_bot_settings(*args, **kwargs):
            return BotSettings(bot=bot, user=user, integrations_per_user_limit=2)

        monkeypatch.setattr(MongoProcessor, 'get_bot_settings', _mock_get_bot_settings)
        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        with pytest.raises(AppException, match='Integrations limit reached!'):
            Authentication.generate_integration_token(bot, user, name='integration_token1', role='chat')

    def test_generate_integration_token_dynamic(self, monkeypatch):
        bot = 'test'
        user = 'test_user'
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]
        start_date = datetime.datetime.now(tz=datetime.timezone.utc)
        access_limit = ['/api/bot/endpoint']

        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        token, _ = Authentication.generate_integration_token(bot, user, expiry=15, access_limit=access_limit,
                                                             token_type=TOKEN_TYPE.DYNAMIC.value)
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert payload["version"] == "2.0"
        assert not Utility.check_empty_string(payload['sub'])
        claims = Utility.decrypt_message(payload['sub'])
        payload = json.loads(claims)
        assert payload.get('bot') == bot
        assert payload.get('sub') == user
        assert payload.get('iat')
        assert payload.get('type') == TOKEN_TYPE.DYNAMIC.value
        assert payload.get('role') == 'chat'
        assert payload.get('access-limit') == access_limit
        iat = datetime.datetime.fromtimestamp(payload.get('iat'), tz=datetime.timezone.utc)
        exp = datetime.datetime.fromtimestamp(payload.get('exp'), tz=datetime.timezone.utc)
        assert round((exp - iat).total_seconds() / 60) == 15

    def test_generate_integration_token_without_name(self, monkeypatch):
        bot = 'test'
        user = 'test_user'


        def __mock_get_bot(*args, **kwargs):
            return {"account": 1000}

        monkeypatch.setattr(AccountProcessor, "get_bot", __mock_get_bot)
        with pytest.raises(ValidationError, match='name is required to add integration'):
            Authentication.generate_integration_token(bot, user, expiry=15)

    def test_list_integrations(self):
        bot = 'test'
        integrations = list(IntegrationProcessor.get_integrations(bot))
        assert integrations[0]['name'] == 'integration_token'
        assert integrations[0]['user'] == 'test_user'
        assert integrations[0]['iat']
        assert integrations[0]['status'] == 'active'
        assert integrations[0]['role'] == 'chat'
        assert integrations[1]['name'] == 'integration_token_with_expiry'
        assert integrations[1]['user'] == 'test_user'
        assert integrations[1]['iat']
        assert integrations[1]['expiry']
        assert integrations[1]['status'] == 'active'
        assert integrations[0]['role'] == 'chat'

        bot = 'test1'
        integrations = list(IntegrationProcessor.get_integrations(bot))
        assert integrations[0]['name'] == 'integration_token_with_access_limit'
        assert integrations[0]['user'] == 'test_user'
        assert integrations[0]['iat']
        assert integrations[0]['expiry']
        assert integrations[0]['access_list'] == ['/api/bot/endpoint']
        assert integrations[0]['status'] == 'active'
        assert integrations[0]['role'] == 'admin'

    def test_update_integration_token_without_name(self):
        bot = 'test'
        user = 'test_user'
        with pytest.raises(AppException, match="Integration does not exists"):
            Authentication.update_integration_token(None, bot, user)

    def test_update_integration_token_not_exists(self):
        bot = 'test'
        user = 'test_user'
        with pytest.raises(AppException, match="Integration does not exists"):
            Authentication.update_integration_token('integration_not_exists', bot, user)

    def test_validate_integration_token(self):
        bot = 'test1'
        user = 'test_user'
        name = 'integration_token_with_access_limit'
        payload = {'name': name, 'bot': bot, 'sub': user, 'iat': pytest.integration_iat,
                   'access_limit': ['/api/bot/endpoint'], 'role': 'admin'}
        assert not Authentication.validate_integration_token(payload)

    def test_validate_integration_token_not_exists(self):
        bot = 'test1'
        user = 'test_user'
        name = 'integration_not_exists'
        payload = {'name': name, 'bot': bot, 'sub': user, 'iat': pytest.integration_iat}
        with pytest.raises(HTTPException):
            Authentication.validate_integration_token(payload)

    def test_validate_integration_token_accessing_different_bot(self):
        bot = 'test1'
        bot_2 = 'test2'
        user = 'test_user'
        name = 'integration_not_exists'
        payload = {'name': name, 'bot': bot, 'sub': user, 'iat': pytest.integration_iat}
        with pytest.raises(HTTPException):
            Authentication.validate_bot_request(bot, bot_2)

    def test_list_integrations_after_update(self):
        bot = 'test'
        integrations = list(IntegrationProcessor.get_integrations(bot))
        assert integrations[0]['name'] == 'integration_token'
        assert integrations[0]['user'] == 'test_user'
        assert integrations[0]['iat']
        assert integrations[0]['status'] == 'active'
        assert integrations[0]['role'] == 'chat'
        assert integrations[1]['name'] == 'integration_token_with_expiry'
        assert integrations[1]['user'] == 'test_user'
        assert integrations[1]['iat']
        assert integrations[1]['expiry']
        assert integrations[1]['status'] == 'active'
        assert integrations[1]['role'] == 'designer'

        bot = 'test1'
        integrations = list(IntegrationProcessor.get_integrations(bot))
        assert integrations[0]['name'] == 'integration_token_with_access_limit'
        assert integrations[0]['user'] == 'test_user'
        assert integrations[0]['iat']
        assert integrations[0]['expiry']
        assert integrations[0]['access_list'] == ['/api/bot/endpoint']
        assert integrations[0]['status'] == 'active'
        assert integrations[0]['role'] == 'admin'

    def test_update_integration_delete_integration_token_different_bot(self):
        bot = 'test_1'
        user = 'test_user'
        token = Authentication.update_integration_token('integration_token', bot, user,
                                                        int_status=INTEGRATION_STATUS.DELETED.value)
        assert not token

    def test_update_integration_disable_integration_token(self):
        bot = 'test1'
        user = 'test_user'
        token = Authentication.update_integration_token('integration_token_with_access_limit', bot, user,
                                                        int_status=INTEGRATION_STATUS.INACTIVE.value)
        assert not token

    def test_list_integrations_after_disable(self):
        bot = 'test'
        integrations = list(IntegrationProcessor.get_integrations(bot))
        assert integrations[0]['name'] == 'integration_token'
        assert integrations[0]['user'] == 'test_user'
        assert integrations[0]['iat']
        assert integrations[0]['status'] == 'active'
        assert integrations[0]['role'] == 'chat'
        assert integrations[1]['name'] == 'integration_token_with_expiry'
        assert integrations[1]['user'] == 'test_user'
        assert integrations[1]['iat']
        assert integrations[1]['expiry']
        assert integrations[1]['status'] == 'active'
        assert integrations[1]['role'] == 'designer'

        bot = 'test1'
        integrations = list(IntegrationProcessor.get_integrations(bot))
        assert integrations[0]['name'] == 'integration_token_with_access_limit'
        assert integrations[0]['user'] == 'test_user'
        assert integrations[0]['iat']
        assert integrations[0]['expiry']
        assert integrations[0]['access_list'] == ['/api/bot/endpoint']
        assert integrations[0]['status'] == 'inactive'

    def test_validate_disabled_integration_token(self):
        bot = 'test1'
        user = 'test_user'
        name = 'integration_token_with_access_limit'
        payload = {'name': name, 'bot': bot, 'sub': user, 'iat': pytest.integration_iat,
                   'access_limit': ['/api/bot/endpoint/new']}
        with pytest.raises(HTTPException):
            Authentication.validate_integration_token(payload)

    def test_update_integration_delete_integration_token(self):
        bot = 'test1'
        user = 'test_user'
        token = Authentication.update_integration_token('integration_token_with_access_limit', bot, user,
                                                        int_status=INTEGRATION_STATUS.DELETED.value)
        assert not token

    def test_list_integrations_after_deletion(self):
        bot = 'test'
        integrations = list(IntegrationProcessor.get_integrations(bot))
        assert integrations[0]['name'] == 'integration_token'
        assert integrations[0]['user'] == 'test_user'
        assert integrations[0]['iat']
        assert integrations[0]['status'] == 'active'
        assert integrations[0]['role'] == 'chat'
        assert integrations[1]['name'] == 'integration_token_with_expiry'
        assert integrations[1]['user'] == 'test_user'
        assert integrations[1]['iat']
        assert integrations[1]['expiry']
        assert integrations[1]['status'] == 'active'
        assert integrations[1]['role'] == 'designer'

        bot = 'test1'
        integrations = list(IntegrationProcessor.get_integrations(bot))
        assert integrations == []

    def test_validate_deleted_integration_token(self):
        bot = 'test1'
        user = 'test_user'
        name = 'integration_token_with_access_limit'
        payload = {'name': name, 'bot': bot, 'sub': user, 'iat': pytest.integration_iat,
                   'access_limit': ['/api/bot/endpoint/new']}
        with pytest.raises(HTTPException):
            Authentication.validate_integration_token(payload)

    def test_add_feedback(self):
        AccountProcessor.add_feedback(4.5, 'test', feedback='product is good')
        feedback = Feedback.objects(user='test').get()
        assert feedback['rating'] == 4.5
        assert feedback['scale'] == 5.0
        assert feedback['feedback'] == 'product is good'
        assert feedback['timestamp']

    def test_add_feedback_2(self):
        AccountProcessor.add_feedback(5.0, 'test_user', scale=10, feedback='i love kairon')
        feedback = Feedback.objects(user='test_user').get()
        assert feedback['rating'] == 5.0
        assert feedback['scale'] == 10
        assert feedback['feedback'] == 'i love kairon'
        assert feedback['timestamp']

    def test_add_feedback_3(self):
        AccountProcessor.add_feedback(5.0, 'test')
        feedback = list(Feedback.objects(user='test'))
        assert feedback[1]['rating'] == 5.0
        assert feedback[1]['scale'] == 5.0
        assert not feedback[1]['feedback']
        assert feedback[1]['timestamp']

    def test_get_ui_config_none(self):
        assert AccountProcessor.get_ui_config('test') == {}

    def test_add_ui_config(self):
        config = {'has_stepper': True, 'has_tour': False}
        assert not AccountProcessor.update_ui_config(config, 'test')
        config = {'has_stepper': True, 'has_tour': False, 'theme': 'black'}
        assert not AccountProcessor.update_ui_config(config, 'test_user')

    def test_add_ui_config_duplicate(self):
        config = {'has_stepper': True, 'has_tour': False, 'theme': 'white'}
        assert not AccountProcessor.update_ui_config(config, 'test')

    def test_get_saved_ui_config(self):
        config = {'has_stepper': True, 'has_tour': False, 'theme': 'white'}
        assert AccountProcessor.get_ui_config('test') == config
        config = {'has_stepper': True, 'has_tour': False, 'theme': 'black'}
        assert AccountProcessor.get_ui_config('test_user') == config

    @pytest.mark.asyncio
    async def test_sso_login_google_not_enabled(self):
        with pytest.raises(AppException, match='google login is not enabled'):
            await Authentication.get_redirect_url("google")

        request = Request({'type': 'http',
                           'headers': Headers({}).raw,
                           'query_string': 'code=AQDKEbWXmRjtjiPdGUxXSTuye8ggMZvN9A_cXf1Bw9j_FLSe_Tuwsf_EP-LmmHVAQqTIhqL1Yj7mnsnBbsQdSPLC_4QmJ1GJqM--mbDR0l7UAKVxWdtqy8YAK60Ws02EhjydiIKJ7duyccCa7vXZN01XPAanHak2vvp1URPMvmIMgjEcMyI-IJR0k9PR5NHCEKUmdqeeFBkyFbTtjizGvjYee7kFt7T6_-6DT3q9_1fPvC9VRVPa7ppkJOD0n6NW4smjtpLrEckjO5UF3ekOCNfISYrRdIU8LSMv0RU3i0ALgK2CDyp7rSzOwrkpw6780Ix-QtgFOF4T7scDYR7ZqG6HY5vljBt_lUE-ZWjv-zT_QHhv08Dm-9AoeC_yGNx1Wb8&state=f7ad9a88-be24-4d88-a3bd-3f02b4b12a18&scope=email profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile openid&authuser=0&hd=digite.com&prompt=none'})
        with pytest.raises(AppException, match='google login is not enabled'):
            await Authentication.verify_and_process(request, "google")

    @pytest.mark.asyncio
    async def test_sso_login_facebook_not_enabled(self):
        with pytest.raises(AppException, match='facebook login is not enabled'):
            await Authentication.get_redirect_url("facebook")

        request = Request({'type': 'http',
                           'headers': Headers({}).raw,
                           'query_string': 'code=AQDKEbWXmRjtjiPdGUxXSTuye8ggMZvN9A_cXf1Bw9j_FLSe_Tuwsf_EP-LmmHVAQqTIhqL1Yj7mnsnBbsQdSPLC_4QmJ1GJqM--mbDR0l7UAKVxWdtqy8YAK60Ws02EhjydiIKJ7duyccCa7vXZN01XPAanHak2vvp1URPMvmIMgjEcMyI-IJR0k9PR5NHCEKUmdqeeFBkyFbTtjizGvjYee7kFt7T6_-6DT3q9_1fPvC9VRVPa7ppkJOD0n6NW4smjtpLrEckjO5UF3ekOCNfISYrRdIU8LSMv0RU3i0ALgK2CDyp7rSzOwrkpw6780Ix-QtgFOF4T7scDYR7ZqG6HY5vljBt_lUE-ZWjv-zT_QHhv08Dm-9AoeC_yGNx1Wb8&state=f7ad9a88-be24-4d88-a3bd-3f02b4b12a18&scope=email profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile openid&authuser=0&hd=digite.com&prompt=none'})
        with pytest.raises(AppException, match='facebook login is not enabled'):
            await Authentication.verify_and_process(request, "facebook")

    @pytest.mark.asyncio
    async def test_sso_login_linkedin_not_enabled(self):
        with pytest.raises(AppException, match='linkedin login is not enabled'):
            await Authentication.get_redirect_url("linkedin")

        request = Request({'type': 'http',
                           'headers': Headers({}).raw,
                           'query_string': 'code=AQDKEbWXmRjtjiPdGUxXSTuye8ggMZvN9A_cXf1Bw9j_FLSe_Tuwsf_EP-LmmHVAQqTIhqL1Yj7mnsnBbsQdSPLC_4QmJ1GJqM--mbDR0l7UAKVxWdtqy8YAK60Ws02EhjydiIKJ7duyccCa7vXZN01XPAanHak2vvp1URPMvmIMgjEcMyI-IJR0k9PR5NHCEKUmdqeeFBkyFbTtjizGvjYee7kFt7T6_-6DT3q9_1fPvC9VRVPa7ppkJOD0n6NW4smjtpLrEckjO5UF3ekOCNfISYrRdIU8LSMv0RU3i0ALgK2CDyp7rSzOwrkpw6780Ix-QtgFOF4T7scDYR7ZqG6HY5vljBt_lUE-ZWjv-zT_QHhv08Dm-9AoeC_yGNx1Wb8&state=f7ad9a88-be24-4d88-a3bd-3f02b4b12a18&scope=email profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile openid&authuser=0&hd=digite.com&prompt=none'})
        with pytest.raises(AppException, match='linkedin login is not enabled'):
            await Authentication.verify_and_process(request, "linkedin")

    @pytest.mark.asyncio
    async def test_verify_and_process_google(self, monkeypatch):
        Utility.environment['sso']['google']['enable'] = True

        async def _mock_google_response(*args, **kwargs):
            return OpenID(
                id='116918187277293076263',
                email='monisha.ks@digite.com',
                first_name='Monisha',
                last_name='KS',
                display_name='Monisha KS',
                picture='https://lh3.googleusercontent.com/a/AATXAJxqb5pnbXi5Yryt_9TPdPiB8mQe8Lk613-4ytus=s96-c',
                provider='google')

        def _mock_user_details(*args, **kwargs):
            return {"email": "monisha.ks@digite.com"}

        monkeypatch.setattr(AccountProcessor, "get_user", _mock_user_details)
        monkeypatch.setattr(AccountProcessor, "get_user_details", _mock_user_details)
        monkeypatch.setattr(GoogleSSO, "verify_and_process", _mock_google_response)
        request = Request({'type': 'http',
                           'headers': Headers({}).raw,
                           'query_string': 'code=AQDKEbWXmRjtjiPdGUxXSTuye8ggMZvN9A_cXf1Bw9j_FLSe_Tuwsf_EP-LmmHVAQqTIhqL1Yj7mnsnBbsQdSPLC_4QmJ1GJqM--mbDR0l7UAKVxWdtqy8YAK60Ws02EhjydiIKJ7duyccCa7vXZN01XPAanHak2vvp1URPMvmIMgjEcMyI-IJR0k9PR5NHCEKUmdqeeFBkyFbTtjizGvjYee7kFt7T6_-6DT3q9_1fPvC9VRVPa7ppkJOD0n6NW4smjtpLrEckjO5UF3ekOCNfISYrRdIU8LSMv0RU3i0ALgK2CDyp7rSzOwrkpw6780Ix-QtgFOF4T7scDYR7ZqG6HY5vljBt_lUE-ZWjv-zT_QHhv08Dm-9AoeC_yGNx1Wb8&state=f7ad9a88-be24-4d88-a3bd-3f02b4b12a18&scope=email profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile openid&authuser=0&hd=digite.com&prompt=none'})
        existing_user, user, token = await Authentication.verify_and_process(request, "google")
        assert Utility.decode_limited_access_token(token)["sub"] == "monisha.ks@digite.com"
        assert user['email'] == 'monisha.ks@digite.com'
        assert user['first_name'] == 'Monisha'
        assert user['last_name'] == 'KS'
        assert Utility.check_empty_string(user.get('password'))
        assert existing_user

    @pytest.mark.asyncio
    async def test_verify_and_process_user_doesnt_exist_google(self, monkeypatch):
        async def _mock_google_response(*args, **kwargs):
            return OpenID(
                id='116918187277293076263',
                email='monisha.ks@digite.com',
                first_name='Monisha',
                last_name='KS',
                display_name='Monisha KS',
                picture='https://lh3.googleusercontent.com/a/AATXAJxqb5pnbXi5Yryt_9TPdPiB8mQe8Lk613-4ytus=s96-c',
                provider='google')

        monkeypatch.setattr(GoogleSSO, "verify_and_process", _mock_google_response)
        request = Request({'type': 'http',
                           'headers': Headers({}).raw,
                           'query_string': 'code=AQDKEbWXmRjtjiPdGUxXSTuye8ggMZvN9A_cXf1Bw9j_FLSe_Tuwsf_EP-LmmHVAQqTIhqL1Yj7mnsnBbsQdSPLC_4QmJ1GJqM--mbDR0l7UAKVxWdtqy8YAK60Ws02EhjydiIKJ7duyccCa7vXZN01XPAanHak2vvp1URPMvmIMgjEcMyI-IJR0k9PR5NHCEKUmdqeeFBkyFbTtjizGvjYee7kFt7T6_-6DT3q9_1fPvC9VRVPa7ppkJOD0n6NW4smjtpLrEckjO5UF3ekOCNfISYrRdIU8LSMv0RU3i0ALgK2CDyp7rSzOwrkpw6780Ix-QtgFOF4T7scDYR7ZqG6HY5vljBt_lUE-ZWjv-zT_QHhv08Dm-9AoeC_yGNx1Wb8&state=f7ad9a88-be24-4d88-a3bd-3f02b4b12a18&scope=email profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile openid&authuser=0&hd=digite.com&prompt=none'})
        existing_user, user, token = await Authentication.verify_and_process(request, "google")
        assert user['email'] == 'monisha.ks@digite.com'
        assert user['first_name'] == 'Monisha'
        assert user['last_name'] == 'KS'
        assert not Utility.check_empty_string(user.get('password').get_secret_value())
        assert user.get('account') == user.get('email')
        assert not existing_user
        user = AccountProcessor.get_user_details('monisha.ks@digite.com')
        print(user)
        assert all(
            user[key] is False if key in {"is_integration_user", "is_onboarded"} else user[key]
            for key in user.keys()
        )
        print(list(AccountProcessor.list_bots(user['account'])))
        assert len(list(AccountProcessor.list_bots(user['account']))) == 0
        assert not AccountProcessor.is_user_confirmed(user['email'])

    @pytest.mark.asyncio
    async def test_ssostate_google(*args, **kwargs):
        request = Request({'type': 'http',
                           'headers': Headers({}).raw,
                           'query_string': 'code=AQDKEbWXmRjtjiPdGUxXSTuye8ggMZvN9A_cXf1Bw9j_FLSe_Tuwsf_EP-LmmHVAQqTIhqL1Yj7mnsnBbsQdSPLC_4QmJ1GJqM--mbDR0l7UAKVxWdtqy8YAK60Ws02EhjydiIKJ7duyccCa7vXZN01XPAanHak2vvp1URPMvmIMgjEcMyI-IJR0k9PR5NHCEKUmdqeeFBkyFbTtjizGvjYee7kFt7T6_-6DT3q9_1fPvC9VRVPa7ppkJOD0n6NW4smjtpLrEckjO5UF3ekOCNfISYrRdIU8LSMv0RU3i0ALgK2CDyp7rSzOwrkpw6780Ix-QtgFOF4T7scDYR7ZqG6HY5vljBt_lUE-ZWjv-zT_QHhv08Dm-9AoeC_yGNx1Wb8&state=f7ad9a88-be24-4d88-a3bd-3f02b4b12a18&scope=email profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile openid&authuser=0&hd=digite.com&prompt=none'})
        with pytest.raises(AppException) as e:
            await Authentication.verify_and_process(request, "google")
        assert str(e).__contains__('Failed to verify with google')

    @pytest.mark.asyncio
    async def test_get_redirect_url_google(self, monkeypatch):
        discovery_url = 'https://discovery.url.localhost/o/oauth2/v2/auth?response_type=code&client_id'

        async def _mock_get_discovery_doc(*args, **kwargs):
            return {'authorization_endpoint': discovery_url}

        monkeypatch.setattr(GoogleSSO, 'get_discovery_document', _mock_get_discovery_doc)
        assert isinstance(await Authentication.get_redirect_url("google"), RedirectResponse)

    @pytest.mark.asyncio
    async def test_verify_and_process_facebook(self, monkeypatch):
        Utility.environment['sso']['facebook']['enable'] = True

        async def _mock_facebook_response(*args, **kwargs):
            return OpenID(
                id='107921368422696',
                email='monisha.ks@digite.com',
                first_name='Moni',
                last_name='Shareddy',
                display_name='Monisha Shareddy',
                picture='https://scontent-bom1-2.xx.fbcdn.net/v/t1.30497-1/cp0/c15.0.50.50a/p50x50/84628273_176159830277856_972693363922829312_n.jpg?_nc_cat=1&ccb=1-5&_nc_sid=12b3be&_nc_ohc=reTAAmyXfF0AX9vbxxH&_nc_ht=scontent-bom1-2.xx&edm=AP4hL3IEAAAA&oh=00_AT_6IOixo-clV4B1Gthr_UabmxEzz50ri6yAhhXJzlbFeQ&oe=61F21F38',
                provider='facebook')

        def _mock_user_details(*args, **kwargs):
            return {"email": "monisha.ks@digite.com"}

        monkeypatch.setattr(AccountProcessor, "get_user", _mock_user_details)
        monkeypatch.setattr(AccountProcessor, "get_user_details", _mock_user_details)
        monkeypatch.setattr(FacebookSSO, "verify_and_process", _mock_facebook_response)

        request = Request({'type': 'http',
                           'headers': Headers({}).raw,
                           'query_string': 'code=AQDEkezmJoa3hfyVOafJkHbXG5OJNV3dZQ4gElP3WS71LJbErkK6ljLq31C0B3xRw2dv2G4Fh9mA2twjBVrQZfv_j0MYBS8xq0DEAg08YTZ2Kd1mPJ2HVDF5GnrhZcl2V1qpcO0pGzVQAFMLVRKVWxmirya0uqm150ZLHL_xN9NZjCvk1DRnOXKYXXZtaaU-HgO22Rxxzo90hTtW4mLBl7Vg55SRmic6p1r3KAkyfnAVTLSNPhaX2I9KUgeUjQ6EwGz3NtwjxKLPnsC1yPZqQMGBS6u2lHt-BOjj80iJmukbLH_35Xzn6Mv6xVSjqGwTjNEnn6N5dyT-3_X_vmYTlcGpr8LOn6tTf7kz_ysauexbGxn883m_thFV3Ozb9oP9u78)]'})
        existing_user, user, token = await Authentication.verify_and_process(request, "facebook")
        assert Utility.decode_limited_access_token(token)["sub"] == "monisha.ks@digite.com"
        assert user['email'] == 'monisha.ks@digite.com'
        assert user['first_name'] == 'Moni'
        assert user['last_name'] == 'Shareddy'
        assert Utility.check_empty_string(user.get('password'))
        assert existing_user

    @pytest.mark.asyncio
    async def test_verify_and_process_user_doesnt_exist_facebook(self, monkeypatch):
        async def _mock_facebook_response(*args, **kwargs):
            return OpenID(
                id='107921368422696',
                email='monishaks@digite.com',
                first_name='Moni',
                last_name='Shareddy',
                display_name='Monisha Shareddy',
                picture='https://scontent-bom1-2.xx.fbcdn.net/v/t1.30497-1/cp0/c15.0.50.50a/p50x50/84628273_176159830277856_972693363922829312_n.jpg?_nc_cat=1&ccb=1-5&_nc_sid=12b3be&_nc_ohc=reTAAmyXfF0AX9vbxxH&_nc_ht=scontent-bom1-2.xx&edm=AP4hL3IEAAAA&oh=00_AT_6IOixo-clV4B1Gthr_UabmxEzz50ri6yAhhXJzlbFeQ&oe=61F21F38',
                provider='facebook')

        monkeypatch.setattr(FacebookSSO, "verify_and_process", _mock_facebook_response)
        request = Request({'type': 'http',
                           'headers': Headers({'cookie': "ssostate=a257c5b8-4293-49db-a773-2c6fd78df016"}).raw,
                           'query_string': 'code=AQB4u0qDPLiqREyHXEmGydCw-JBg-vU1VL9yfR1PLuGijlyGsZs7CoYe98XhQ-jkQu_jYj-DMefRL_AcAvhenbBEuQ5Bhd18B9gOfDwe0JvB-Y5TAm21MrhVZtDxSm9VTSZVaPrwsWeN0dQYr2OgG9I0qPoM-OBEsOdJRYpCn-nKBKFGAbXb6AR7KTHhQtRDHHrylLe0QcSz2p1FjlLVWOrBh-A3o5xmvsaXaRtwYfYdJuxOBz2W7DlVw9m6qP9fx4gAzkp-j1sNKmiZjuHBsHJvKQsBG7xCw7etZh5Uie49R-WtP87-yic_CMYulju5bYRWTMd-549QWwjMW8lIQkPXStGwbU0JaOy9BHKmB6iUSrp0jIyo1RYdBo6Ji81Jyms&state=a257c5b8-4293-49db-a773-2c6fd78df016'})
        existing_user, user, token = await Authentication.verify_and_process(request, "facebook")
        assert user['email'] == 'monishaks@digite.com'
        assert user['first_name'] == 'Moni'
        assert user['last_name'] == 'Shareddy'
        assert not Utility.check_empty_string(user.get('password').get_secret_value())
        assert user.get('account') == user.get('email')
        assert not existing_user
        user = AccountProcessor.get_user_details('monishaks@digite.com')
        assert all(
            user[key] is False if key in {"is_integration_user", "is_onboarded"} else user[key]
            for key in user.keys()
        )
        print(list(AccountProcessor.list_bots(user['account'])))
        assert len(list(AccountProcessor.list_bots(user['account']))) == 0
        assert not AccountProcessor.is_user_confirmed(user['email'])

    @pytest.mark.asyncio
    async def test_get_redirect_url_facebook(self):
        assert isinstance(await Authentication.get_redirect_url("facebook"), RedirectResponse)

    @pytest.mark.asyncio
    async def test_invalid_ssostate_facebook(*args, **kwargs):
        request = Request({'type': 'http',
                           'headers': Headers({'cookie': "ssostate=a257c5b8-4293-49db-a773-2c6fd78df016"}).raw,
                           'query_string': 'code=AQB4u0qDPLiqREyHXEmGydCw-JBg-vU1VL9yfR1PLuGijlyGsZs7CoYe98XhQ-jkQu_jYj-DMefRL_AcAvhenbBEuQ5Bhd18B9gOfDwe0JvB-Y5TAm21MrhVZtDxSm9VTSZVaPrwsWeN0dQYr2OgG9I0qPoM-OBEsOdJRYpCn-nKBKFGAbXb6AR7KTHhQtRDHHrylLe0QcSz2p1FjlLVWOrBh-A3o5xmvsaXaRtwYfYdJuxOBz2W7DlVw9m6qP9fx4gAzkp-j1sNKmiZjuHBsHJvKQsBG7xCw7etZh5Uie49R-WtP87-yic_CMYulju5bYRWTMd-549QWwjMW8lIQkPXStGwbU0JaOy9BHKmB6iUSrp0jIyo1RYdBo6Ji81Jyms&state=a257c5b8-4293-49db-a773-2c6fd78df016'})
        with pytest.raises(AppException) as e:
            await Authentication.verify_and_process(request, "facebook")
        assert str(e).__contains__('Failed to verify with facebook')

    @pytest.mark.asyncio
    async def test_get_redirect_url_linkedin(self):
        Utility.environment['sso']['linkedin']['enable'] = True

        response = await Authentication.get_redirect_url("linkedin")
        assert isinstance(response, RedirectResponse)

    @pytest.mark.asyncio
    async def test_sso_linkedin_login_error(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            method=responses.POST,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.token_endpoint,
            json={'access_token': '1234567890'},
            match_content=b"grant_type=authorization_code&client_id=asdfghjklzxcvb&code=4%2F0AX4XfWh-AOKSPocewBBm0KAE_5j1qGNNWJAdbRcZ8OYKUU1KlwGqx_kOz6yzlZN-jUBi0Q&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fcallback%2Flinkedin&client_secret=qwertyuiopasdf",
        )
        httpx_mock.add_response(
            method=responses.GET,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.userinfo_endpoint,
            json={'given_name': 'udit', 'family_name': 'pandey', 'name': 'udit pandey'},
        )
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "http",
            "path": "/",
            'query_string': b'code=4/0AX4XfWh-AOKSPocewBBm0KAE_5j1qGNNWJAdbRcZ8OYKUU1KlwGqx_kOz6yzlZN-jUBi0Q&state={LoginSSOFactory.linkedin_sso.state}&scope=email profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile openid&authuser=0&hd=digite.com&prompt=none',
            "headers": Headers({
                'cookie': f"ssostate={LoginSSOFactory.get_client('linkedin').sso_client.state}",
                'host': 'www.example.org',
                'accept': 'application/json',

            }).raw,
            "client": ("134.56.78.4", 1453),
            "server": ("www.example.org", 443),
        }

        request = Request(scope=scope)
        request._url = URL(scope=scope)
        with pytest.raises(AppException, match='User was not verified with linkedin'):
            await Authentication.verify_and_process(request, "linkedin")

    @pytest.mark.asyncio
    async def test_sso_linkedin_login_success(self, httpx_mock: HTTPXMock, monkeypatch):
        httpx_mock.add_response(
            method=responses.POST,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.token_endpoint,
            json={'access_token': '1234567890'},
            match_content=b"grant_type=authorization_code&client_id=asdfghjklzxcvb&code=4%2F0AX4XfWh-AOKSPocewBBm0KAE_5j1qGNNWJAdbRcZ8OYKUU1KlwGqx_kOz6yzlZN-jUBi0Q&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fcallback%2Flinkedin&client_secret=qwertyuiopasdf",
        )
        httpx_mock.add_response(
            method=responses.GET,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.userinfo_endpoint,
            json={'given_name': 'monisha', 'family_name': 'reddy', 'name': 'monisha reddy',
                  'email': 'monisha.ks@digite.com'},
        )
        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            'query_string': b'code=4/0AX4XfWh-AOKSPocewBBm0KAE_5j1qGNNWJAdbRcZ8OYKUU1KlwGqx_kOz6yzlZN-jUBi0Q&state={LoginSSOFactory.linkedin_sso.state}&scope=email profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile openid&authuser=0&hd=digite.com&prompt=none',
            "headers": Headers({
                'cookie': f"ssostate={LoginSSOFactory.get_client('linkedin').sso_client.state}",
                'host': 'www.example.org',
                'accept': 'application/json',

            }).raw,
            "client": ("134.56.78.4", 1453),
            "server": ("www.example.org", 443),
        }

        def _mock_user_details(*args, **kwargs):
            return {"email": "monisha.ks@digite.com"}

        monkeypatch.setattr(AccountProcessor, "get_user", _mock_user_details)
        monkeypatch.setattr(AccountProcessor, "get_user_details", _mock_user_details)
        request = Request(scope=scope)
        request._url = URL(scope=scope)
        existing_user, user, token = await Authentication.verify_and_process(request, "linkedin")
        assert Utility.decode_limited_access_token(token)["sub"] == "monisha.ks@digite.com"
        assert user['email'] == 'monisha.ks@digite.com'
        assert user['first_name'] == 'monisha'
        assert user['last_name'] == 'reddy'
        assert Utility.check_empty_string(user.get('password'))
        assert existing_user

    @pytest.mark.asyncio
    async def test_sso_linkedin_login_new_user(self, httpx_mock: HTTPXMock, monkeypatch):
        httpx_mock.add_response(
            method=responses.POST,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.token_endpoint,
            json={'access_token': '1234567890'},
            match_content=b"grant_type=authorization_code&client_id=asdfghjklzxcvb&code=4%2F0AX4XfWh-AOKSPocewBBm0KAE_5j1qGNNWJAdbRcZ8OYKUU1KlwGqx_kOz6yzlZN-jUBi0Q&redirect_uri=http%3A%2F%2Flocalhost%3A8080%2Fcallback%2Flinkedin&client_secret=qwertyuiopasdf",
        )
        httpx_mock.add_response(
            method=responses.GET,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.userinfo_endpoint,
            json={'given_name': 'monisha', 'family_name': 'reddy', 'name': 'monisha reddy',
                  'email': 'monisha.ks.ks@digite.com'},
        )

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": "/",
            'query_string': b'code=4/0AX4XfWh-AOKSPocewBBm0KAE_5j1qGNNWJAdbRcZ8OYKUU1KlwGqx_kOz6yzlZN-jUBi0Q&state={LoginSSOFactory.linkedin_sso.state}&scope=email profile https://www.googleapis.com/auth/userinfo.email https://www.googleapis.com/auth/userinfo.profile openid&authuser=0&hd=digite.com&prompt=none',
            "headers": Headers({
                'cookie': f"ssostate={LoginSSOFactory.get_client('linkedin').sso_client.state}",
                'host': 'www.example.org',
                'accept': 'application/json',

            }).raw,
            "client": ("134.56.78.4", 1453),
            "server": ("www.example.org", 443),
        }

        request = Request(scope=scope)
        request._url = URL(scope=scope)
        existing_user, user, token = await Authentication.verify_and_process(request, "linkedin")
        assert Utility.decode_limited_access_token(token)["sub"] == "monisha.ks.ks@digite.com"
        assert user['email'] == 'monisha.ks.ks@digite.com'
        assert user['first_name'] == 'monisha'
        assert user['last_name'] == 'reddy'
        assert not Utility.check_empty_string(user.get('password').get_secret_value())
        assert not existing_user
        user = AccountProcessor.get_user_details('monisha.ks@digite.com')
        assert all(
            user[key] is False if key in {"is_integration_user", "is_onboarded"} else user[key]
            for key in user.keys()
        )
        user = AccountProcessor.get_user_details('monishaks@digite.com')
        assert all(
            user[key] is False if key in {"is_integration_user", "is_onboarded"} else user[key]
            for key in user.keys()
        )
        print(list(AccountProcessor.list_bots(user['account'])))
        assert len(list(AccountProcessor.list_bots(user['account']))) == 0
        assert not AccountProcessor.is_user_confirmed(user['email'])

    def test_sso_login_client_linkedin(self):
        assert LoginSSOFactory.get_client('linkedin').sso_client.client_secret == \
               Utility.environment['sso']['linkedin']['client_secret']
        assert LoginSSOFactory.get_client('linkedin').sso_client.client_id == Utility.environment['sso']['linkedin'][
            'client_id']
        assert LoginSSOFactory.get_client('linkedin').sso_client.redirect_uri == urljoin(
            Utility.environment['sso']['redirect_url'], 'linkedin')

    def test_sso_login_client_gmail(self):
        assert LoginSSOFactory.get_client('google').sso_client.client_secret == Utility.environment['sso']['google'][
            'client_secret']
        assert LoginSSOFactory.get_client('google').sso_client.client_id == Utility.environment['sso']['google'][
            'client_id']
        assert LoginSSOFactory.get_client('google').sso_client.redirect_uri == urljoin(
            Utility.environment['sso']['redirect_url'], 'google')

    def test_sso_login_client_facebook(self):
        assert LoginSSOFactory.get_client('facebook').sso_client.client_secret == \
               Utility.environment['sso']['facebook']['client_secret']
        assert LoginSSOFactory.get_client('facebook').sso_client.client_id == Utility.environment['sso']['facebook'][
            'client_id']
        assert LoginSSOFactory.get_client('facebook').sso_client.redirect_uri == urljoin(
            Utility.environment['sso']['redirect_url'], 'facebook')

    def test_overwrite_password_with_same_password(self, monkeypatch):
        AccountProcessor.add_user(
            email="samepasswrd@gmail.com",
            first_name="user1",
            last_name="passwrd",
            password='Welcome@1',
            account=1,
            user="testAdmin",
        )
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('samepasswrd@gmail.com')
        loop = asyncio.new_event_loop()
        with pytest.raises(AppException, match='You have already used this password, try another!'):
            loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@1"))

    def test_overwrite_password_with_same_password_again(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('samepasswrd@gmail.com')
        loop = asyncio.new_event_loop()
        Utility.environment['user']['reset_password_cooldown_period'] = 0
        loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@12"))
        time.sleep(2)
        with pytest.raises(AppException, match='You have already used this password, try another!'):
            loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@12"))

    def test_overwrite_password_with_original_passwrd(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('samepasswrd@gmail.com')
        loop = asyncio.new_event_loop()
        Utility.environment['user']['reset_password_cooldown_period'] = 0
        time.sleep(2)
        with pytest.raises(AppException, match='You have already used this password, try another!'):
            loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@1"))

    def test_overwrite_password_with_successful_update(self, monkeypatch):
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('samepasswrd@gmail.com')
        loop = asyncio.new_event_loop()
        Utility.environment['user']['reset_password_cooldown_period'] = 0
        time.sleep(2)
        loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@3"))
        assert True

    def test_reset_password_reuselink(self, monkeypatch):
        AccountProcessor.add_user(
            email="resuselink@gmail.com",
            first_name="user1",
            last_name="passwrd",
            password='Welcome@1',
            account=1,
            user="reuselink_acc",
        )
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        usertoken = Utility.generate_token('resuselink@gmail.com')
        loop.run_until_complete(AccountProcessor.confirm_email(usertoken))
        result = loop.run_until_complete(AccountProcessor.send_reset_link('resuselink@gmail.com'))
        token = str(result[2]).split("/")[2]
        Utility.email_conf["email"]["enable"] = False
        loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@3"))
        with pytest.raises(AppException, match='Link has already been used once and has thus expired!'):
            loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@4"))

    def test_valid_token_with_payload(self):
        uuid_value = str(uuid.uuid1())
        token = Utility.generate_token_payload(payload={"mail_id": "account_reuse_link@gmail.com",
                                                        "uuid": uuid_value})
        decoded_jwt = Utility.verify_token(token)
        assert uuid_value == decoded_jwt.get("uuid")
        assert "account_reuse_link@gmail.com" == decoded_jwt.get("mail_id")

    def test_valid_token_with_payload_only_email(self):
        token = Utility.generate_token_payload(payload={"mail_id": "account_reuse_link@gmail.com"})
        decoded_jwt = Utility.verify_token(token)
        assert not decoded_jwt.get("uuid")
        assert "account_reuse_link@gmail.com" == decoded_jwt.get("mail_id")

    def test_reset_password_reuselink_check_uuid(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(AccountProcessor.send_reset_link('resuselink@gmail.com'))
        token = str(result[2]).split("/")[2]
        decoded_jwt = Utility.verify_token(token)
        Utility.email_conf["email"]["enable"] = False
        assert decoded_jwt.get("uuid")

    def test_remove_trusted_device(self):
        AccountProcessor.remove_trusted_device("udit.pandey@digite.com", "1234567890fghj")

    def test_add_trusted_device(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['user'], "validate_trusted_device", True)
        request = Request({'type': 'http', 'headers': Headers({}).raw})
        AccountProcessor.get_location_and_add_trusted_device("udit.pandey@digite.com", "1234567890fghj", request)
        AccountProcessor.get_location_and_add_trusted_device("udit.pandey@digite.com", "kjhdsaqewrrtyuio879", request)

    def test_add_trusted_device_email_enabled(self, monkeypatch):
        monkeypatch.setitem(Utility.email_conf["email"], 'enable', True)
        monkeypatch.setitem(Utility.environment['user'], "validate_trusted_device", True)
        request = Request({'type': 'http', 'headers': Headers({"X-Forwarded-For": "34.75.89.98"}).raw})
        url, geo_location = AccountProcessor.get_location_and_add_trusted_device("trust@digite.com", "1234567890fghj",
                                                                                 request)
        assert not Utility.check_empty_string(url)

    def test_list_all_trusted_device(self):
        devices = list(AccountProcessor.list_trusted_devices("udit.pandey@digite.com"))
        assert devices[0]['_id']
        assert devices[0]['confirmation_timestamp']
        assert devices[0]['timestamp']
        assert devices[0]['status']
        assert devices[0]['is_confirmed']
        assert devices[0]['user']
        assert len(devices) == 2
        assert list(AccountProcessor.list_trusted_devices("trust@digite.com")) == []
        device = TrustedDevice.objects(user="trust@digite.com").get()
        assert device.fingerprint == "1234567890fghj"
        assert not device.confirmation_timestamp
        assert not device.is_confirmed

    def test_confirm_add_trusted_device(self):
        AccountProcessor.confirm_add_trusted_device("trust@digite.com", "1234567890fghj")
        devices = list(AccountProcessor.list_trusted_devices("trust@digite.com"))
        assert devices[0]['_id']
        assert devices[0]['confirmation_timestamp']
        assert devices[0]['timestamp']
        assert devices[0]['status']
        assert devices[0]['is_confirmed']
        assert devices[0]['user']

    def test_confirm_add_trusted_device_not_found(self):
        with pytest.raises(AppException, match="Device not found!"):
            AccountProcessor.confirm_add_trusted_device("trust@digite.com", "1234567890fghj")

    @pytest.mark.asyncio
    @responses.activate
    async def test_validate_trusted_device_add_device(self, monkeypatch):
        token = "abcgd563"
        enable = True

        def _mock_get_user_details(*args, **kwargs):
            return {"account": 10}

        monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
        monkeypatch.setitem(Utility.email_conf["email"], "enable", enable)
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
        monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", enable)
        monkeypatch.setattr(AccountProcessor, "get_user_details", _mock_get_user_details)

        url = f"https://ipinfo.io/10.11.12.13?token={token}"
        expected = {
            "ip": "10.11.12.13",
            "city": "Mumbai",
            "region": "Maharashtra",
            "country": "IN",
            "loc": "19.0728,72.8826",
            "org": "AS13150 CATO NETWORKS LTD",
            "postal": "400070",
            "timezone": "Asia/Kolkata"
        }
        responses.add("GET", url, json=expected)
        request = Request({'type': 'http', 'headers': Headers({"X-Forwarded-For": "34.75.89.98"}).raw})
        with patch("kairon.shared.utils.SMTP", autospec=True):
            await Authentication.validate_trusted_device("pandey.udit867@gmail.com", "kjhdsaqewrrtyuio879", request)

    def test_list_trusted_device(self):
        assert AccountProcessor.list_trusted_device_fingerprints("udit.pandey@digite.com") == [
            "1234567890fghj", "kjhdsaqewrrtyuio879"]

    @pytest.mark.asyncio
    async def test_validate_trusted_device(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", True)
        request = Request({'type': 'http', 'headers': Headers({"X-Forwarded-For": "34.75.89.98"}).raw})
        await Authentication.validate_trusted_device("udit.pandey@digite.com", "kjhdsaqewrrtyuio879", request)

    @pytest.mark.asyncio
    @responses.activate
    async def test_validate_trusted_device_invalid(self, monkeypatch):
        token = "abcgd563"
        enable = True
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "token", token)
        monkeypatch.setitem(Utility.email_conf["email"], "enable", enable)
        monkeypatch.setitem(Utility.environment["plugins"]["location"], "enable", enable)
        monkeypatch.setitem(Utility.environment["user"], "validate_trusted_device", enable)
        url = f"https://ipinfo.io/10.11.12.13?token={token}"
        expected = {
            "ip": "10.11.12.13",
            "city": "Mumbai",
            "region": "Maharashtra",
            "country": "IN",
            "loc": "19.0728,72.8826",
            "org": "AS13150 CATO NETWORKS LTD",
            "postal": "400070",
            "timezone": "Asia/Kolkata"
        }
        responses.add("GET", url, json=expected)
        request = Request({'type': 'http', 'headers': Headers({"X-Forwarded-For": "34.75.89.98"}).raw})
        with patch("kairon.shared.utils.SMTP", autospec=True):
            await Authentication.validate_trusted_device("udit.pandey@digite.com", "kjhdsaqewrrtyuio87", request)

    @pytest.mark.asyncio
    async def test_remove_trusted_device_not_exists_2(self):
        request = Request({'type': 'http', 'headers': Headers({"X-Forwarded-For": "34.75.89.98"}).raw})
        await Authentication.validate_trusted_device("pandey.udit867@gmail.com", "kjhdsaqewrrtyuio879", request)

    def test_list_fingerprint_not_exists(self):
        assert AccountProcessor.list_trusted_device_fingerprints("pandey.udit867@gmail.com") == []

    def test_upsert_organization_add(self):
        org_data = {"name": "test"}
        mail = "test@demo.in"
        account = "1234"
        user = User(account=account, email=mail)
        OrgProcessor.upsert_organization(user=user, org_data=org_data)

        result = Organization.objects().get(account__contains=user.account)
        assert result.name == org_data.get("name")

    def test_upsert_organization_update(self):
        org_data = {"name": "new_test", "create_user": True, "only_sso_login": False}
        mail = "test@demo.in"
        account = "1234"
        user = User(account=account, email=mail)
        OrgProcessor.upsert_organization(user=user, org_data=org_data)

        result = Organization.objects().get(account__contains=user.account)
        assert result.name == org_data.get("name")

        with pytest.raises(DoesNotExist):
            Organization.objects().get(name="test")

    def test_upsert_organization_add_same_name_diff_account(self):
        org_data = {"name": "new_test"}
        mail = "test@demo.in"
        account = "55555"
        user = User(account=account, email=mail)

        with pytest.raises(AppException, match="Name already exists"):
            OrgProcessor.upsert_organization(user=user, org_data=org_data)

    def test_upsert_organization_update_name(self):
        org_data = {"name": "new_test", "create_user": True, "only_sso_login": False}
        mail = "test@demo.in"
        account = "1234"
        user = User(account=account, email=mail)
        OrgProcessor.upsert_organization(user=user, org_data=org_data)

        result = Organization.objects().get(account__contains=user.account)
        assert result.name == org_data.get("name")

        with pytest.raises(DoesNotExist):
            Organization.objects().get(name="test")

    def test_upsert_organization_update_create_user(self):
        org_data = {"name": "new_test", "create_user": False, "only_sso_login": False}
        mail = "test@demo.in"
        account = "1234"
        user = User(account=account, email=mail)
        OrgProcessor.upsert_organization(user=user, org_data=org_data)

        result = Organization.objects().get(account__contains=user.account)
        assert result.name == org_data.get("name")
        assert result.create_user == org_data.get("create_user")
        assert result.only_sso_login == org_data.get("only_sso_login")
        with pytest.raises(DoesNotExist):
            Organization.objects().get(name="test")

    def test_validate_org_settings(self):
        with pytest.raises(AppException, match=ORG_SETTINGS_MESSAGES.get("create_user")):
            OrgProcessor.validate_org_settings(organization="new_test", settings=FeatureMappings.CREATE_USER.value)

    def test_upsert_organization_update_sso_login(self):
        org_data = {"name": "new_test", "create_user": False, "only_sso_login": True}
        mail = "test@demo.in"
        account = "1234"
        user = User(account=account, email=mail)
        OrgProcessor.upsert_organization(user=user, org_data=org_data)

        result = Organization.objects().get(account__contains=user.account)
        assert result.name == org_data.get("name")
        assert result.create_user == org_data.get("create_user")
        assert result.only_sso_login == org_data.get("only_sso_login")
        with pytest.raises(DoesNotExist):
            Organization.objects().get(name="test")

    def test_validate_org_settings_negative(self):
        OrgProcessor.validate_org_settings(organization="new_test", settings=FeatureMappings.ONLY_SSO_LOGIN.value)
        assert not None

    def test_get_organization_exists(self):
        account = 1234
        result = OrgProcessor.get_organization_for_account(account=account)
        assert result.get("name") == "new_test"

    def test_get_organization_not_exists(self, caplog):
        account = 12345
        result = OrgProcessor.get_organization_for_account(account=account)
        assert {} == result
        assert "Organization not found" in caplog.text
        assert any(
            record.levelname == "ERROR" and record.message == "Organization not found"
            for record in caplog.records
        )

    def test_invalid_account_number(self):
        with pytest.raises(DoesNotExist, match="Account does not exists"):
            AccountProcessor.get_account(0)

    @pytest.mark.asyncio
    async def test_reset_link_with_unverified_mail(self, monkeypatch):
        AccountProcessor.add_user(
            email="integration@2.com",
            first_name="user1",
            last_name="passwrd",
            password='Welcome@1',
            account=1,
            user="reuse-link_acc",
        )
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(MailUtility, 'trigger_smtp', self.mock_smtp)
        with pytest.raises(AppException, match="Error! The following user's mail is not verified"):
            await(AccountProcessor.send_reset_link('integration@2.com'))
        Utility.email_conf["email"]["enable"] = False

    def test_upsert_organization(self):
        org_data = {"name": "DEL"}
        mail = "testing@demo.in"
        account = "123456"
        user = User(account=account, email=mail)
        config = {
            "client_id": "90",
            "client_secret": "9099",
        }
        idp_config = IdpConfig(user="${user}", account=[user.account], organization="DEL", config=config).save()
        OrgProcessor.upsert_organization(user=user, org_data=org_data)
        result = IDPProcessor.get_idp_config("123456")
        assert result is not None

    @pytest.mark.asyncio
    async def test_account_setup_delete_bot_except_block(self, monkeypatch):
        def add_user_mock(*args, **kwargs):
            return None

        account = {
            "account": "1234",
            "email": "vdivya4690@gmail.com",
            "first_name": "delete_First",
            "last_name": "delete_Last",
            "password": SecretStr("Qwerty@4"),
            "accepted_privacy_policy": True,
            "accepted_terms": True
        }
        monkeypatch.setattr(AccountProcessor, "add_user", add_user_mock)
        bots_before_delete = list(AccountProcessor.list_bots(account["account"]))
        result = await(AccountProcessor.account_setup(account))
        bots_after_delete = list(AccountProcessor.list_bots(account["account"]))
        assert bots_after_delete == bots_before_delete
        assert result == (None, None, None)

    @pytest.mark.asyncio
    async def test_default_account_setup_error_msg(self):
        result = await AccountProcessor.default_account_setup()
        assert result is None

    def test_validate_confirm_password(cls):
        with pytest.raises(ValueError, match="Password and Confirm Password does not match"):
            RegisterAccount.validate_confirm_password(SecretStr("Owners@4"), {"password": SecretStr("Winte@20")})

    def test_validate_password(cls):
        with pytest.raises(ValueError, match="Password length must be 10\n"
                                             "Missing 1 number\nMissing 1 special letter"):
            Password.validate_password(SecretStr("Owners"), {})

    def test_validate_password_empty(cls):
        with pytest.raises(ValueError, match="Password length must be 10\n"
                                             "Missing 1 uppercase letter\n"
                                             "Missing 1 number\n"
                                             "Missing 1 special letter"):
            Password.validate_password(SecretStr(""), {})

    def test_validate_password_None(cls):
        with pytest.raises(ValueError, match="Password length must be 10\n"
                                             "Missing 1 number\nMissing 1 special letter"):
            Password.validate_password(SecretStr(None), {})

    def test_check(cls):
        with pytest.raises(ValueError, match="Provide key from key vault as value"):
            HttpActionParameters.check({"parameter_type": "key_vault", "key": "key"})

    def test_validate_organization_empty(self):
        with pytest.raises(ValueError, match="Organization can not be empty"):
            IDPConfig.validate_organization("", {})

    def test_validate_organization(self):
        result = IDPConfig.validate_organization("NXT", {})
        assert result == "NXT"

    def test_validate_organization_None(self):
        with pytest.raises(ValueError, match="Organization can not be empty"):
            IDPConfig.validate_organization(None, {})

    def test_validate_ws_url_empty(cls):
        with pytest.raises(ValueError, match="url can not be empty"):
            EventConfig.validate_ws_url("", {})

    def test_validate_ws_url_none_value(cls):
        config = EventConfig(ws_url="ws_url", headers={"headers": "Headers"}, method="method")
        with pytest.raises(ValueError, match="url can not be empty"):
            result = config.validate_ws_url(None, {})
            assert result is None

    def test_validate_ws_url(cls):
        config = EventConfig(ws_url="ws_url", headers={"headers": "Headers"}, method="method")
        result = config.validate_ws_url("https://www.google.com", {})
        assert result == "https://www.google.com"

    def test_validate_headers_empty(cls):
        result = EventConfig.validate_headers("", {})
        assert result == {}

    def test_validate_headers(cls):
        result = EventConfig.validate_headers({"headers": "Headers"}, {})
        assert result == {"headers": "Headers"}

    def test_validate_headers_None(cls):
        result = EventConfig.validate_headers(None, {})
        assert result == {}

    def test_validate_config_empty(cls):
        result = IDPConfig.validate_config("", {})
        assert result == {}

    def test_validate_config(cls):
        result = IDPConfig.validate_config({}, {})
        assert result == {}

    def test_validate_config_None(cls):
        result = IDPConfig.validate_config(None, {})
        assert result == {}

    def test_get_steps(cls):
        temp = [
            {"name": "greet", "type": "INTENT"},
            {"name": "utter_greet", "type": "FORM_ACTION"},
            {"name": "know_user", "type": "FORM_START"},
            {"type": "FORM_END"},
            {"name": "utter_submit", "type": "BOT"},
        ]

        request = StoryRequest(name="registration", type="STORY", steps=temp)
        result = request.get_steps()
        [r.pop("value", None) for r in result]
        temp[3] = {'name': None, 'type': 'FORM_END'}
        assert result == temp
        assert all([i for i in temp if type(i) is dict])

    def test_add_get_user_org_mapping(self):
        user = "test@demo.in"
        organization = "new_test"
        feature_type = FeatureMappings.ONLY_SSO_LOGIN.value
        value = True
        OrgProcessor.upsert_user_org_mapping(user=user, org=organization, feature=feature_type, value=value)

        result = OrgProcessor.get_user_org_mapping(user=user, org=organization, feature=feature_type)

        assert result == value

    def test_add_get_user_org_mapping_another(self):
        user = "test_another@demo.in"
        organization = "new_test"
        feature_type = FeatureMappings.ONLY_SSO_LOGIN.value
        value = True
        OrgProcessor.upsert_user_org_mapping(user=user, org=organization, feature=feature_type, value=value)
        assert not None

    def test_validate_sso_only(self):
        user = "test@demo.in"
        with pytest.raises(AppException, match="Login with your org SSO url, Login with username/password not allowed"):
            OrgProcessor.validate_sso_only(user=user)

    def test_update_user_specific_user_org_mapping(self):
        user = "test@demo.in"
        organization = "new_test"
        feature_type = FeatureMappings.ONLY_SSO_LOGIN.value
        value = False

        result = OrgProcessor.get_user_org_mapping(user=user, org=organization, feature=feature_type)

        assert result != value

        OrgProcessor.upsert_user_org_mapping(user=user, org=organization, feature=feature_type, value=value)

        result = OrgProcessor.get_user_org_mapping(user=user, org=organization, feature=feature_type)

        assert result == value

    def test_update_user_org_mapping_org_specific(self):
        organization = "new_test"
        feature_type = FeatureMappings.ONLY_SSO_LOGIN.value
        value = False
        OrgProcessor.update_org_mapping(org=organization, feature=feature_type, value=value)

        result = OrgProcessor.get_user_org_mapping(user="test@demo.in", org=organization, feature=feature_type)

        assert result == value

        new_val = False
        OrgProcessor.update_org_mapping(org=organization, feature=feature_type, value=new_val)

        assert result == new_val

    def test_delete_org_mapping(self):
        organization = "new_test"
        result = OrgProcessor.delete_org_mapping(organization)
        assert result >= 2

    def test_delete_org_mapping_not_exists(self):
        organization = "not_exists"
        result = OrgProcessor.delete_org_mapping(organization)
        assert result == 0

    def test_delete_org(self, monkeypatch):
        def _delete_idp(*args, **kwargs):
            return None

        monkeypatch.setattr(IDPProcessor, 'delete_idp', _delete_idp)

        account = 1234
        name = "new_test"
        OrgProcessor.delete_org(account=account, org_id=name, user="test")
        org = OrgProcessor.get_organization(org_name=name)
        assert org == {}

    @pytest.mark.asyncio
    async def test_add_bot_with_template(self, monkeypatch):
        bot = "bot_from_hi_hello_template"
        account = 2000
        user = "bot_user"
        template_name = "Hi-Hello-GPT"

        monkeypatch.setitem(Utility.environment['llm'], 'key', 'secret_value')

        bot_id = await AccountProcessor.add_bot_with_template(bot, account, user, template_name)
        assert not Utility.check_empty_string(bot_id)

        settings = MongoProcessor.get_bot_settings(bot_id, user)
        assert settings["llm_settings"]["enable_faq"] is True

        assert AccountProcessor.get_bot(bot_id)["metadata"] == {'from_template': 'Hi-Hello-GPT', 'language': 'en'}

        assert Utility.is_model_file_exists(bot_id) is True
        Utility.delete_directory(f"./models/{bot_id}")

        bot_secret = BotSecrets.objects(bot=bot_id, secret_type="gpt_key").get().to_mongo().to_dict()
        assert Utility.decrypt_message(bot_secret['value']) == 'secret_value'

    @pytest.mark.asyncio
    async def test_add_bot_with_template_llm_key_not_exists(self):
        bot = "bot_from_hi_hello_template_2"
        account = 2000
        user = "bot_user"
        template_name = "Hi-Hello-GPT"

        bot_id = await AccountProcessor.add_bot_with_template(bot, account, user, template_name)
        assert not Utility.check_empty_string(bot_id)

        settings = MongoProcessor.get_bot_settings(bot_id, user)
        assert settings["llm_settings"]["enable_faq"] is True

        assert AccountProcessor.get_bot(bot_id)["metadata"] == {'from_template': 'Hi-Hello-GPT', 'language': 'en'}

        assert Utility.is_model_file_exists(bot_id) is True
        Utility.delete_directory(f"./models/{bot_id}")

        with pytest.raises(DoesNotExist):
            BotSecrets.objects(bot=bot_id, secret_type="gpt_key").get().to_mongo().to_dict()

    @mock.patch('kairon.shared.data.audit.processor.AuditDataProcessor.publish_auditlog', autospec=True)
    def test_save_auditlog_document(self, mock_publish):
        from kairon.shared.account.processor import AccountProcessor
        def _publish(*args, **kwargs):
            return

        mock_publish.return_value = _publish
        bot = 'test_bot'
        user_name = "testsampleUser"
        account = AccountProcessor.add_account("Nupur", "testsampleUser")
        AccountProcessor.add_user(
            email="nk@digite.com",
            first_name="Nupur",
            last_name="Khare",
            password="Welcome@109",
            account=account['_id'],
            user=user_name,
        )
        entity = UserActivityType.reset_password.value
        data = {'status': 'pending'}
        kwargs = {'message': ['Reset password'], 'action': 'activity'}
        AuditDataProcessor.log(entity, account['_id'], bot, None, data, **kwargs)
        count = AuditLogData.objects(
            attributes=[{'key': 'account', 'value': account['_id']}, {'key': 'bot', 'value': bot}], user=user_name,
            action='activity').count()
        assert count == 1

    def test_get_attributes(self):
        document = {'bot': None, 'acccount': None, 'email': 'nk15@digite.com'}
        attributes = AuditDataProcessor.get_attributes(document)
        assert attributes[0]['key'] == 'email'
        assert attributes[0]['value'] == 'nk15@digite.com'

    def test_update_user_details_with_invalid_onboarding_status(self):
        with pytest.raises(ValidationError, match="Invalid is not a valid status"):
            AccountProcessor.update_user_details("fshaikh@digite.com", "Invalid")

        with pytest.raises(ValidationError, match="INITIATED is not a valid status"):
            AccountProcessor.update_user_details("fshaikh@digite.com", "INITIATED")

        with pytest.raises(ValidationError, match="IN PROGRESS is not a valid status"):
            AccountProcessor.update_user_details("fshaikh@digite.com", "IN PROGRESS")

        with pytest.raises(ValidationError, match="Done is not a valid status"):
            AccountProcessor.update_user_details("fshaikh@digite.com", "Done")

    def test_update_user_details_with_onboarding_status(self):
        assert len(AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned']) == 1
        user_details = AccountProcessor.get_complete_user_details("fshaikh@digite.com")
        assert user_details["_id"]
        assert user_details["email"] == "fshaikh@digite.com"
        assert user_details["bots"]["account_owned"][0]["user"] == "fshaikh@digite.com"
        assert user_details["bots"]["account_owned"][0]["timestamp"]
        assert user_details["bots"]["account_owned"][0]["name"] == "test_bot"
        assert user_details["bots"]["account_owned"][0]["_id"]
        assert not user_details["bots"]["shared"]
        assert user_details["timestamp"]
        assert user_details["status"]
        assert user_details["account_name"] == "paypal"
        assert user_details["first_name"] == "Fahad Ali"
        assert user_details["last_name"] == "Shaikh"
        assert user_details["onboarding_status"] == "Not Completed"
        assert user_details["is_onboarded"] is False

        AccountProcessor.update_user_details("fshaikh@digite.com", "In Progress")

        user_details = AccountProcessor.get_complete_user_details("fshaikh@digite.com")
        assert user_details["_id"]
        assert user_details["email"] == "fshaikh@digite.com"
        assert user_details["bots"]["account_owned"][0]["user"] == "fshaikh@digite.com"
        assert user_details["bots"]["account_owned"][0]["timestamp"]
        assert user_details["bots"]["account_owned"][0]["name"] == "test_bot"
        assert user_details["bots"]["account_owned"][0]["_id"]
        assert not user_details["bots"]["shared"]
        assert user_details["timestamp"]
        assert user_details["status"]
        assert user_details["account_name"] == "paypal"
        assert user_details["first_name"] == "Fahad Ali"
        assert user_details["last_name"] == "Shaikh"
        assert user_details["onboarding_status"] == "In Progress"
        assert user_details["onboarding_timestamp"]
        assert user_details["is_onboarded"] is False

        AccountProcessor.update_user_details("fshaikh@digite.com", "Completed")

        user_details = AccountProcessor.get_complete_user_details("fshaikh@digite.com")
        assert user_details["_id"]
        assert user_details["email"] == "fshaikh@digite.com"
        assert user_details["bots"]["account_owned"][0]["user"] == "fshaikh@digite.com"
        assert user_details["bots"]["account_owned"][0]["timestamp"]
        assert user_details["bots"]["account_owned"][0]["name"] == "test_bot"
        assert user_details["bots"]["account_owned"][0]["_id"]
        assert not user_details["bots"]["shared"]
        assert user_details["timestamp"]
        assert user_details["status"]
        assert user_details["account_name"] == "paypal"
        assert user_details["first_name"] == "Fahad Ali"
        assert user_details["last_name"] == "Shaikh"
        assert user_details["onboarding_status"] == "Completed"
        assert user_details["onboarding_timestamp"]
        assert user_details["is_onboarded"] is True
