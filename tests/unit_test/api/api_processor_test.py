import asyncio
import datetime
import os
from urllib.parse import urljoin

import jwt
import responses
from fastapi import HTTPException
from fastapi_sso.sso.base import OpenID
from mongoengine import connect
from mongoengine.errors import ValidationError, DoesNotExist
import pytest
from mongomock.object_id import ObjectId
from pydantic import SecretStr
from pytest_httpx import HTTPXMock
from starlette.datastructures import Headers, URL
from starlette.requests import Request
from starlette.responses import RedirectResponse

from kairon.shared.auth import Authentication, LoginSSOFactory
from kairon.shared.account.data_objects import Feedback, BotAccess, User
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.authorization.processor import IntegrationProcessor
from kairon.shared.data.constant import ACTIVITY_STATUS, ACCESS_ROLES, TOKEN_TYPE, INTEGRATION_STATUS
from kairon.shared.data.data_objects import Configs, Rules, Responses
from kairon.shared.sso.clients.facebook import FacebookSSO
from kairon.shared.sso.clients.google import GoogleSSO
from kairon.shared.utils import Utility
from kairon.exceptions import AppException
from stress_test.data_objects import Bot

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

    def test_add_bot(self):
        bot_response = AccountProcessor.add_bot("test", pytest.account, "fshaikh@digite.com", True)
        bot = Bot.objects(name="test").get().to_mongo().to_dict()
        assert bot['_id'].__str__() == bot_response['_id'].__str__()
        config = Configs.objects(bot=bot['_id'].__str__()).get().to_mongo().to_dict()
        assert config['language']
        assert config['pipeline'][5]['name'] == 'FallbackClassifier'
        assert config['pipeline'][5]['threshold'] == 0.7
        assert config['policies'][2]['name'] == 'RulePolicy'
        assert config['policies'][2]['core_fallback_action_name'] == "action_default_fallback"
        assert config['policies'][2]['core_fallback_threshold'] == 0.3
        assert Rules.objects(bot=bot['_id'].__str__()).get()
        assert Responses.objects(name__iexact='utter_please_rephrase', bot=bot['_id'].__str__(), status=True).get()
        assert Responses.objects(name='utter_default', bot=bot['_id'].__str__(), status=True).get()
        pytest.bot = bot_response['_id'].__str__()

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
        assert len(AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned']) == 2
        config = Configs.objects(bot=bot['_id'].__str__()).get().to_mongo().to_dict()
        assert config['language']
        assert config['pipeline'][5]['name'] == 'FallbackClassifier'
        assert config['pipeline'][5]['threshold'] == 0.7
        assert config['policies'][2]['name'] == 'RulePolicy'
        assert config['policies'][2]['core_fallback_action_name'] == "action_default_fallback"
        assert config['policies'][2]['core_fallback_threshold'] == 0.3
        assert Rules.objects(bot=bot['_id'].__str__()).get()
        assert Responses.objects(name='utter_default', bot=bot['_id'].__str__(), status=True).get()

    def test_add_member_already_exists(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        with pytest.raises(AppException, match='User is already a collaborator'):
            AccountProcessor.allow_bot_and_generate_invite_url(bot_id, "fshaikh@digite.com", 'testAdmin',
                                                               pytest.account, ACCESS_ROLES.DESIGNER.value)

    def test_add_member_bot_not_exists(self):
        with pytest.raises(DoesNotExist, match='Bot does not exists!'):
            AccountProcessor.allow_bot_and_generate_invite_url('bot_not_exists', "fshaikh@digite.com", 'testAdmin', pytest.account)

    def test_list_bot_accessors_1(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        accessors = list(AccountProcessor.list_bot_accessors(bot_id))
        assert len(accessors) == 1
        assert accessors[0]['accessor_email'] == 'fshaikh@digite.com'
        assert accessors[0]['role'] == 'owner'
        assert accessors[0]['bot']
        assert accessors[0]['bot_account'] == pytest.account
        assert accessors[0]['user'] == "fshaikh@digite.com"
        assert accessors[0]['timestamp']

    def test_update_bot_access_modify_bot_owner_access(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        with pytest.raises(AppException, match='Ownership modification denied'):
            AccountProcessor.update_bot_access(bot_id, "fshaikh@digite.com", 'testAdmin',
                                                      ACCESS_ROLES.OWNER.value, ACTIVITY_STATUS.INACTIVE.value)
        with pytest.raises(AppException, match='Ownership modification denied'):
            AccountProcessor.update_bot_access(bot_id, "fshaikh@digite.com", 'testAdmin',
                                                      ACCESS_ROLES.ADMIN.value, ACTIVITY_STATUS.ACTIVE.value)

    def test_update_bot_access_user_not_exists(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        BotAccess(bot=bot_id, accessor_email="udit.pandey@digite.com", user='test',
                  role='designer', status='invite_not_accepted', bot_account=pytest.account).save()
        with pytest.raises(DoesNotExist, match='User does not exist!'):
            AccountProcessor.update_bot_access(bot_id, "udit.pandey@digite.com",
                                               ACCESS_ROLES.ADMIN.value, ACTIVITY_STATUS.INACTIVE.value)

    def test_update_bot_access_invite_not_accepted(self, monkeypatch):
        monkeypatch.setitem(Utility.email_conf["email"], "enable", True)
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
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
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        token = Utility.generate_token("pandey.udit867@gmail.com")
        with pytest.raises(DoesNotExist, match='User does not exist!'):
            AccountProcessor.accept_bot_access_invite(token, bot_id)

    def test_update_bot_access_user_not_allowed(self):
        AccountProcessor.add_account('pandey.udit867@gmail.com', 'pandey.udit867@gmail.com')
        User(email='pandey.udit867@gmail.com', first_name='udit', last_name='pandey', password='124556779', account=10,
             user='pandey.udit867@gmail.com').save()
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        with pytest.raises(AppException, match='User not yet invited to collaborate'):
            AccountProcessor.update_bot_access(bot_id, "pandey.udit867@gmail.com",
                                               ACCESS_ROLES.ADMIN.value, ACTIVITY_STATUS.INACTIVE.value)

    def test_accept_bot_access_invite(self, monkeypatch):
        def _mock_get_user(*args, **kwargs):
            return None
        monkeypatch.setattr(AccountProcessor, 'get_user_details', _mock_get_user)

        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        token = Utility.generate_token("udit.pandey@digite.com")
        AccountProcessor.accept_bot_access_invite(token, bot_id)
        assert BotAccess.objects(bot=bot_id, accessor_email="udit.pandey@digite.com", user='test',
                                 role='designer', status='active', bot_account=pytest.account).get()

    def test_list_active_invites_none(self):
        invite = list(AccountProcessor.list_active_invites("udit.pandey@digite.com"))
        assert invite == []

    def test_update_bot_access(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        assert not AccountProcessor.update_bot_access(bot_id, "udit.pandey@digite.com", 'testAdmin',
                                                      ACCESS_ROLES.ADMIN.value, ACTIVITY_STATUS.ACTIVE.value)
        bot_access = BotAccess.objects(bot=bot_id, accessor_email="udit.pandey@digite.com").get()
        assert bot_access.role == ACCESS_ROLES.ADMIN.value
        assert bot_access.status == ACTIVITY_STATUS.ACTIVE.value

        with pytest.raises(AppException, match='Ownership modification denied'):
            AccountProcessor.update_bot_access(bot_id, "udit.pandey@digite.com", 'testAdmin',
                                               ACCESS_ROLES.OWNER.value, ACTIVITY_STATUS.ACTIVE.value)
        bot_access = BotAccess.objects(bot=bot_id, accessor_email="udit.pandey@digite.com").get()
        assert bot_access.role == ACCESS_ROLES.ADMIN.value
        assert bot_access.status == ACTIVITY_STATUS.ACTIVE.value

    def test_accept_bot_access_invite_user_not_allowed(self, monkeypatch):
        def _mock_get_user(*args, **kwargs):
            return None
        monkeypatch.setattr(AccountProcessor, 'get_user_details', _mock_get_user)

        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        token = Utility.generate_token("pandey.udit867@gmail.com")
        with pytest.raises(AppException, match='No pending invite found for this bot and user'):
            AccountProcessor.accept_bot_access_invite(token, bot_id)

    def test_accept_bot_access_invite_token_expired(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwibmFtZSI6InBhbmRleS51ZGl0ODY3QGdtYWlsLmNvbSIsImV4cCI6MTUxNjIzOTAyMn0.dP8a4rHXb9dBrPFKfKD3_tfKu4NdwfSz213F15qej18'
        with pytest.raises(AppException, match='Invalid token'):
            AccountProcessor.accept_bot_access_invite(token, bot_id)

    def test_accept_bot_access_invite_invalid_bot(self):
        token = Utility.generate_token("pandey.udit867@gmail.com")
        with pytest.raises(DoesNotExist, match='Bot does not exists!'):
            AccountProcessor.accept_bot_access_invite(token, '61cb4e2f7c7ac78d2fa8fab7')

    def test_list_bot_accessors_2(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
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
            AccountProcessor.allow_bot_and_generate_invite_url('test', 'user@demo.ai', 'admin@demo.ai', 2, ACCESS_ROLES.OWNER.value)

    def test_transfer_ownership(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
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
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        User(email='udit@demo.ai', first_name='udit', last_name='pandey', password='124556779', account=10,
             user='udit@demo.ai').save()
        with pytest.raises(AppException, match='User not yet invited to collaborate'):
            AccountProcessor.transfer_ownership(pytest.account, bot_id, "fshaikh@digite.com", 'udit@demo.ai')

    def test_remove_bot_access_not_a_member(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
        with pytest.raises(AppException, match='User not a collaborator to this bot'):
            AccountProcessor.remove_bot_access(bot_id, accessor_email='pandey.udit867@gmail.com')

    def test_remove_bot_access(self):
        bot_id = AccountProcessor.get_accessible_bot_details(pytest.account, "fshaikh@digite.com")['account_owned'][1]['_id']
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
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))

        pytest.deleted_account = user_detail['account'].__str__()
        bot_response_1 = AccountProcessor.add_bot("delete_account_bot_1", pytest.deleted_account, "ritika@digite.com", False)
        bot_response_2 = AccountProcessor.add_bot("delete_account_bot_2", pytest.deleted_account, "ritika@digite.com", False)
        account_bots_before_delete = list(AccountProcessor.list_bots(pytest.deleted_account))

        assert len(account_bots_before_delete) == 3
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
        }

        loop = asyncio.new_event_loop()
        user_detail, mail, link = loop.run_until_complete(
            AccountProcessor.account_setup(account_setup=account))

        #Add shared bot
        bot_response = AccountProcessor.add_bot("delete_account_shared_bot", 30, "udit.pandey@digite.com", False)
        bot_id = bot_response['_id'].__str__()
        BotAccess(bot=bot_id, accessor_email="ritika@digite.com", user='testAdmin',
                  role='designer', status='active', bot_account=30).save()
        pytest.deleted_account = user_detail['account'].__str__()
        accessors_before_delete = list(AccountProcessor.list_bot_accessors(bot_id))

        assert len(accessors_before_delete) == 2
        assert accessors_before_delete[0]['accessor_email'] == 'udit.pandey@digite.com'
        assert accessors_before_delete[1]['accessor_email'] == 'ritika@digite.com'
        AccountProcessor.delete_account(pytest.deleted_account)
        accessors_after_delete = list(AccountProcessor.list_bot_accessors(bot_id))
        assert len(accessors_after_delete) == 1
        assert accessors_after_delete[0]['accessor_email'] == 'udit.pandey@digite.com'
        assert accessors_after_delete[0]['bot_account'] == 30
        assert Bot.objects(id=bot_id, account=30, status=True).get()

    def test_delete_account_for_account(self):
        account = {
            "account": "Test_Delete_Account",
            "email": "ritika@digite.com",
            "first_name": "Test_Delete_First",
            "last_name": "Test_Delete_Last",
            "password": SecretStr("Welcome@1")
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
            "password": SecretStr("Welcome@1")
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
        assert len(list(AccountProcessor.list_bots(new_account_id))) == 1

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
            user[key] is False if key == "is_integration_user" else user[key]
            for key in user.keys()
        )

    def test_get_user_not_exists(self):
        with pytest.raises(DoesNotExist, match='User does not exist!'):
            AccountProcessor.get_user("udit.pandey_kairon@digite.com")

    def test_get_user_details(self):
        user = AccountProcessor.get_user_details("fshaikh@digite.com")
        assert all(
            user[key] is False if key == "is_integration_user" else user[key]
            for key in user.keys()
        )

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
        account = {}
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

    def test_account_setup_user_info(self):
        account = {
            "account": "Test_Account",
            "bot": "Test",
            "first_name": "Test_First",
            "last_name": "Test_Last",
            "password": SecretStr("Welcome@1"),
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
        }
        loop = asyncio.new_event_loop()
        actual, mail, link = loop.run_until_complete(AccountProcessor.account_setup(account_setup=account))
        assert actual["_id"]
        assert actual["account"]
        assert actual["first_name"]
        bot_id = Bot.objects(account=actual['account'], user="demo@ac.in").get()
        assert BotAccess.objects(bot_account=actual['account'], accessor_email=account['email'], bot=str(bot_id.id),
                                 status=ACTIVITY_STATUS.ACTIVE.value, role=ACCESS_ROLES.OWNER.value,
                                 user=account['email']).get()

    def test_default_account_setup(self):
        loop = asyncio.new_event_loop()
        actual, mail, link = loop.run_until_complete(AccountProcessor.default_account_setup())
        assert actual

    async def mock_smtp(self, *args, **kwargs):
        return None

    def test_validate_and_send_mail(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(Utility.validate_and_send_mail('demo@ac.in', subject='test', body='test'))
        assert True

    def test_send_false_email_id(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(Utility.validate_and_send_mail('..', subject='test', body="test"))

    def test_send_empty_mail_subject(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(Utility.validate_and_send_mail('demo@ac.in', subject=' ', body='test'))

    def test_send_empty_mail_body(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(Utility.validate_and_send_mail('demo@ac.in', subject='test', body=' '))

    def test_format_and_send_mail_invalid_type(self):
        loop = asyncio.new_event_loop()
        assert not loop.run_until_complete(Utility.format_and_send_mail('training_failure', 'demo@ac.in', 'udit'))

    def test_valid_token(self):
        token = Utility.generate_token('integ1@gmail.com')
        mail = Utility.verify_token(token)
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
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('integ2@gmail.com')
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.confirm_email(token))
        assert True

    def test_user_already_confirmed(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
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
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        result = loop.run_until_complete(AccountProcessor.send_reset_link('integ2@gmail.com'))
        assert result[0] == 'integ2@gmail.com'
        assert result[1] == 'inteq'
        assert result[2].__contains__('kairon.digite.com/reset_password/')
        Utility.email_conf["email"]["enable"] = False

    def test_reset_link_with_mail_limit_exceeded(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setitem(Utility.environment['user'], 'reset_password_request_limit', 2)
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
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
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link(''))
        Utility.email_conf["email"]["enable"] = False

    def test_reset_link_with_unregistered_mail(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link('sasha.41195@gmail.com'))
        Utility.email_conf["email"]["enable"] = False

    def test_reset_link_with_unconfirmed_mail(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link('integration@demo.ai'))
        Utility.email_conf["email"]["enable"] = False

    def test_overwrite_password_with_invalid_token(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.overwrite_password('fgh', "asdfghj@1"))

    def test_overwrite_password_with_empty_password_string(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.overwrite_password(
                'eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJtYWlsX2lkIjoiaW50ZWcxQGdtYWlsLmNvbSJ9.Ycs1ROb1w6MMsx2WTA4vFu3-jRO8LsXKCQEB3fkoU20',
                " "))

    def test_overwrite_password_with_valid_entries(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('integ2@gmail.com')
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@3"))
        assert True

    def test_overwrite_password_limit_exceeded(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        token = Utility.generate_token('integ2@gmail.com')
        loop = asyncio.new_event_loop()
        with pytest.raises(AppException, match='Password reset limit exhausted. Please come back in *'):
            loop.run_until_complete(AccountProcessor.overwrite_password(token, "Welcome@3"))

    def test_reset_link_not_within_cooldown_period(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
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
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        loop.run_until_complete(AccountProcessor.send_confirmation_link('integ3@gmail.com'))
        Utility.email_conf["email"]["enable"] = False
        assert True

    def test_send_confirmation_link_with_confirmed_id(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link('integ1@gmail.com'))
        Utility.email_conf["email"]["enable"] = False

    def test_send_confirmation_link_with_invalid_id(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link(''))
        Utility.email_conf["email"]["enable"] = False

    def test_send_confirmation_link_with_unregistered_id(self, monkeypatch):
        Utility.email_conf["email"]["enable"] = True
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_confirmation_link('sasha.41195@gmail.com'))
        Utility.email_conf["email"]["enable"] = False

    def test_reset_link_with_mail_not_enabled(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
        loop = asyncio.new_event_loop()
        with pytest.raises(Exception):
            loop.run_until_complete(AccountProcessor.send_reset_link('integ1@gmail.com'))

    def test_send_confirmation_link_with_mail_not_enabled(self, monkeypatch):
        monkeypatch.setattr(Utility, 'trigger_smtp', self.mock_smtp)
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
        assert payload.get('sub') == 'test'

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

    def test_generate_integration_token_login_token(self):
        bot = 'test'
        user = 'test_user'
        with pytest.raises(NotImplementedError):
            Authentication.generate_integration_token(bot, user, token_type=TOKEN_TYPE.LOGIN.value, role='chat')

    def test_generate_integration_token(self):
        bot = 'test'
        user = 'test_user'
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]
        token = Authentication.generate_integration_token(bot, user, name='integration_token', role='chat')
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert payload.get('bot') == bot
        assert payload.get('sub') == user
        assert payload.get('iat')
        assert payload.get('type') == TOKEN_TYPE.INTEGRATION.value
        assert payload.get('role') == 'chat'
        assert not payload.get('exp')

    def test_generate_integration_token_different_bot(self):
        bot = 'test_1'
        user = 'test_user'
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]
        token = Authentication.generate_integration_token(bot, user, name='integration_token', role='tester')
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert payload.get('bot') == bot
        assert payload.get('sub') == user
        assert payload.get('iat')
        assert payload.get('type') == TOKEN_TYPE.INTEGRATION.value
        assert not payload.get('exp')
        assert payload.get('role') == 'tester'

    def test_generate_integration_token_with_expiry(self):
        bot = 'test'
        user = 'test_user'
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]
        token = Authentication.generate_integration_token(bot, user, expiry=15, name='integration_token_with_expiry', role='designer')
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
        assert payload.get('bot') == bot
        assert payload.get('sub') == user
        assert payload.get('iat')
        assert payload.get('type') == TOKEN_TYPE.INTEGRATION.value
        assert payload.get('role') == 'designer'
        iat = datetime.datetime.fromtimestamp(payload.get('iat'), tz=datetime.timezone.utc)
        exp = datetime.datetime.fromtimestamp(payload.get('exp'), tz=datetime.timezone.utc)
        assert round((exp-iat).total_seconds() / 60) == 15

    def test_generate_integration_token_with_access_limit(self):
        bot = 'test1'
        user = 'test_user'
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]
        start_date = datetime.datetime.now(tz=datetime.timezone.utc)
        access_limit = ['/api/bot/endpoint']
        token = Authentication.generate_integration_token(bot, user, expiry=15, access_limit=access_limit, name='integration_token_with_access_limit', role='admin')
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
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

    def test_generate_integration_token_name_exists(self, monkeypatch):
        bot = 'test'
        user = 'test_user'
        monkeypatch.setitem(Utility.environment['security'], 'integrations_per_user', 3)
        with pytest.raises(AppException, match='Integration token with this name has already been initiated'):
            Authentication.generate_integration_token(bot, user, name='integration_token', role='chat')

    def test_generate_integration_token_limit_exceeded(self):
        bot = 'test'
        user = 'test_user'
        with pytest.raises(AppException, match='Integrations limit reached!'):
            Authentication.generate_integration_token(bot, user, name='integration_token1', role='chat')

    def test_generate_integration_token_dynamic(self):
        bot = 'test'
        user = 'test_user'
        secret_key = Utility.environment['security']["secret_key"]
        algorithm = Utility.environment['security']["algorithm"]
        start_date = datetime.datetime.now(tz=datetime.timezone.utc)
        access_limit = ['/api/bot/endpoint']
        token = Authentication.generate_integration_token(bot, user, expiry=15, access_limit=access_limit, token_type=TOKEN_TYPE.DYNAMIC.value)
        payload = jwt.decode(token, secret_key, algorithms=[algorithm])
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
        monkeypatch.setitem(Utility.environment['security'], 'integrations_per_user', 3)
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
        payload = {'name': name, 'bot': bot, 'sub': user, 'iat': pytest.integration_iat, 'access_limit': ['/api/bot/endpoint'], 'role': 'admin'}
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
        token = Authentication.update_integration_token('integration_token_with_access_limit', bot, user, int_status=INTEGRATION_STATUS.INACTIVE.value)
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
        payload = {'name': name, 'bot': bot, 'sub': user, 'iat': pytest.integration_iat, 'access_limit': ['/api/bot/endpoint/new']}
        with pytest.raises(HTTPException):
            Authentication.validate_integration_token(payload)

    def test_update_integration_delete_integration_token(self):
        bot = 'test1'
        user = 'test_user'
        token = Authentication.update_integration_token('integration_token_with_access_limit', bot, user, int_status=INTEGRATION_STATUS.DELETED.value)
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
        payload = {'name': name, 'bot': bot, 'sub': user, 'iat': pytest.integration_iat, 'access_limit': ['/api/bot/endpoint/new']}
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
        assert all(
            user[key] is False if key == "is_integration_user" else user[key]
            for key in user.keys()
        )
        assert len(list(AccountProcessor.list_bots(user['account']))) == 1
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
            user[key] is False if key == "is_integration_user" else user[key]
            for key in user.keys()
        )
        assert len(list(AccountProcessor.list_bots(user['account']))) == 1
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
        )
        httpx_mock.add_response(
            method=responses.GET,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.userinfo_endpoint,
            json={'first_name': 'udit', 'last_name': 'pandey', 'profile_url': '1234::mkfnwuefhbwi'},
        )
        httpx_mock.add_response(
            method=responses.GET,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.useremail_endpoint,
            json={'emailAddress': '1234567890'},
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
        )
        httpx_mock.add_response(
            method=responses.GET,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.userinfo_endpoint,
            json={'localizedFirstName': 'monisha', 'localizedLastName': 'reddy'},
        )
        httpx_mock.add_response(
            method=responses.GET,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.useremail_endpoint,
            json={'elements': [{'handle~': {'emailAddress': 'monisha.ks@digite.com'}}]}
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
        )
        httpx_mock.add_response(
            method=responses.GET,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.userinfo_endpoint,
            json={'localizedFirstName': 'monisha', 'localizedLastName': 'reddy'},
        )
        httpx_mock.add_response(
            method=responses.GET,
            url=await LoginSSOFactory.get_client('linkedin').sso_client.useremail_endpoint,
            json={'elements': [{'handle~': {'emailAddress': 'monisha.ks.ks@digite.com'}}]}
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
            user[key] is False if key == "is_integration_user" else user[key]
            for key in user.keys()
        )
        user = AccountProcessor.get_user_details('monishaks@digite.com')
        assert all(
            user[key] is False if key == "is_integration_user" else user[key]
            for key in user.keys()
        )
        assert len(list(AccountProcessor.list_bots(user['account']))) == 1
        assert not AccountProcessor.is_user_confirmed(user['email'])

    def test_sso_login_client_linkedin(self):
        assert LoginSSOFactory.get_client('linkedin').sso_client.client_secret == Utility.environment['sso']['linkedin']['client_secret']
        assert LoginSSOFactory.get_client('linkedin').sso_client.client_id == Utility.environment['sso']['linkedin']['client_id']
        assert LoginSSOFactory.get_client('linkedin').sso_client.redirect_uri == urljoin(Utility.environment['sso']['redirect_url'], 'linkedin')

    def test_sso_login_client_gmail(self):
        assert LoginSSOFactory.get_client('google').sso_client.client_secret == Utility.environment['sso']['google']['client_secret']
        assert LoginSSOFactory.get_client('google').sso_client.client_id == Utility.environment['sso']['google']['client_id']
        assert LoginSSOFactory.get_client('google').sso_client.redirect_uri == urljoin(Utility.environment['sso']['redirect_url'], 'google')

    def test_sso_login_client_facebook(self):
        assert LoginSSOFactory.get_client('facebook').sso_client.client_secret == Utility.environment['sso']['facebook']['client_secret']
        assert LoginSSOFactory.get_client('facebook').sso_client.client_id == Utility.environment['sso']['facebook']['client_id']
        assert LoginSSOFactory.get_client('facebook').sso_client.redirect_uri == urljoin(Utility.environment['sso']['redirect_url'], 'facebook')
