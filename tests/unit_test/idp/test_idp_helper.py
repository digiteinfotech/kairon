import asyncio
import os

import pytest
import responses
from mongoengine import connect

from kairon.exceptions import AppException
from kairon.idp.constants import (
    IDPURLConstants,
    IDPClientNames,
)
from kairon.idp.data_objects import IdpConfig
from kairon.idp.factory import IDPFactory
from kairon.idp.helper import IDPHelper
from kairon.idp.processor import IDPProcessor
from kairon.shared.organization.processor import OrgProcessor
from kairon.shared.utils import Utility
from stress_test.data_objects import User


def get_user():
    return User(
        email="user@test.in",
        first_name="Test",
        last_name="User",
        account=2,
        status=True,
        is_integration_user=False,
    )


def get_idp_clients_list():
    data = [
        {
            "id": "d2da3349-4000-433a-99b2-6aa34fcf3c1f",
            "clientId": "account",
            "name": "${client_account}",
            "rootUrl": "${authBaseUrl}",
            "baseUrl": "/realms/realm_name_1/account/",
            "surrogateAuthRequired": False,
            "enabled": True,
            "alwaysDisplayInConsole": False,
            "clientAuthenticatorType": "client-secret",
            "redirectUris": ["/realms/realm_name_1/account/*"],
            "webOrigins": [],
            "notBefore": 0,
            "bearerOnly": False,
            "consentRequired": False,
            "serviceAccountsEnabled": False,
            "publicClient": True,
            "frontchannelLogout": False,
            "protocol": "openid-connect",
        },
        {
            "id": "1011d6e4-0a5b-4d16-9c20-2e05e3a648a4",
            "clientId": "admin-cli",
            "name": "${client_admin-cli}",
            "enabled": True,
            "bearerOnly": False,
            "directAccessGrantsEnabled": True,
            "serviceAccountsEnabled": True,
            "publicClient": False,
            "protocol": "openid-connect",
            "attributes": {},
            "fullScopeAllowed": True,
            "nodeReRegistrationTimeout": 0,
        },
        {
            "id": "daf58840-7426-4c32-a61d-457d85b71c33",
            "clientId": "realm-management",
            "name": "${client_realm-management}",
            "surrogateAuthRequired": False,
            "enabled": True,
            "bearerOnly": True,
            "directAccessGrantsEnabled": False,
            "serviceAccountsEnabled": False,
            "publicClient": False,
        },
        {
            "id": "e15a3e48-0e1e-403f-929a-4f0c08f36d69",
            "clientId": "IDPTEST",
            "name": "IDPTEST",
            "description": "Custom client",
            "enabled": True,
            "alwaysDisplayInConsole": False,
            "clientAuthenticatorType": "client-secret",
            "redirectUris": [
                "https://9722-2405-201-23-90ed-b834-5dbc-794f-adb.in.ngrok.io/login/idp/callback/realm_name_1"
            ],
            "bearerOnly": False,
            "directAccessGrantsEnabled": True,
            "serviceAccountsEnabled": True,
            "authorizationServicesEnabled": True,
            "fullScopeAllowed": True,
            "nodeReRegistrationTimeout": 0,
            "protocolMappers": [],
        },
    ]
    return data


class TestIDP:

    @pytest.fixture
    def set_idp_props(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["idp"], "enable", True)
        monkeypatch.setitem(
            Utility.environment["idp"], "server_url", "http://localhost:8080/auth"
        )
        monkeypatch.setitem(Utility.environment["idp"], "admin_username", "sample")
        monkeypatch.setitem(Utility.environment["idp"], "admin_password", "sample")
        monkeypatch.setitem(
            Utility.environment["idp"],
            "admin_client_secret",
            "8e5b7371-be31-4a5c-8b58-a4f1baf519c9",
        )
        monkeypatch.setitem(Utility.environment["idp"], "type", "idp")
        monkeypatch.setitem(
            Utility.environment["idp"],
            "callback_frontend_url",
            "https://localhost:3000",
        )

    @pytest.fixture(autouse=True, scope="class")
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())

    def test_get_admin_access_token_disabled(self, monkeypatch, set_idp_props):
        monkeypatch.setitem(Utility.environment["idp"], "enable", False)

        with pytest.raises(AppException, match="SSO is not enabled"):
            IDPHelper.get_admin_access_token()

    def test_get_admin_access_token_wrong_url(self, monkeypatch, set_idp_props):
        monkeypatch.setitem(
            Utility.environment["idp"], "server_url", "http:localhost:8080/auth"
        )

        token = IDPHelper.get_admin_access_token()
        assert not token

    @responses.activate
    def test_get_admin_access_token_wrong_username_or_password(
        self, monkeypatch, set_idp_props
    ):
        monkeypatch.setitem(
            Utility.environment["idp"], "admin_username", "wrongusername"
        )
        monkeypatch.setitem(
            Utility.environment["idp"], "admin_password", "worngpassword"
        )

        auth_url = Utility.environment["idp"][
            "server_url"
        ] + IDPURLConstants.AUTH_TOKEN_URL.value.format(realm_name="master")
        responses.add(
            "POST",
            auth_url,
            json={
                "error": "invalid_grant",
                "error_description": "Invalid user credentials",
            },
            status=401,
        )

        token = IDPHelper.get_admin_access_token()
        assert token is None

    @responses.activate
    def test_get_admin_access_token(self, set_idp_props):
        event_url = (
            "http://localhost:8080/auth"
            + IDPURLConstants.AUTH_TOKEN_URL.value.format(realm_name="master")
        )
        response_data = {
            "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJjMmdiOEdnUDJQdE1VYWZzb1Z3aGt0bEwxMnpwYzhHNDN2NE93UHNOS3R3In0.eyJleHAiOjE2NjM1MjUzMDMsImlhdCI6MTY2MzUyNTI0MywianRpIjoiZjUzMDdiOGUtMGZmZi00OGU4LWI0N2MtY2E5NTQ2NGE4NjdjIiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2F1dGgvcmVhbG1zL21hc3RlciIsInN1YiI6ImVhOGQyZDAxLWM2NTYtNDE2Zi1hMmZhLTBkYjExNDU5NzUyOSIsInR5cCI6IkJlYXJlciIsImF6cCI6ImFkbWluLWNsaSIsInNlc3Npb25fc3RhdGUiOiI5MGJiMjA1Mi01OTdlLTRiNjctODI4NC1hZTdmODYxZWRkMjciLCJhY3IiOiIxIiwic2NvcGUiOiJlbWFpbCBwcm9maWxlIiwic2lkIjoiOTBiYjIwNTItNTk3ZS00YjY3LTgyODQtYWU3Zjg2MWVkZDI3IiwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJwcmVmZXJyZWRfdXNlcm5hbWUiOiJrYWlyb25rZXljbG9hayJ9.HavJzfu1igpt4IuvZCuQxInWTHz1Dt4L5Oy4q5Fw03QuudztXvUQGGthAWkjNzxGwcwhyBmlzsiLmqsj40K3epiCReEM_bL7zKhiXcXXzAzgxWvXZ4x75WYk00fMxW5eETSfIcLPyqPtGdKyyyEKS1fjtw-O_4VXhp3kO8FrSX7TC1A9Tj0R6I19RaQwSo8pxYeStHtgFri6Vuei4N7bto6pDNMn6hlkfxVelgGocs4lkdI8LRv8LgXenNDK6dd5PcaR5UGoCwU_sBa2AUZjJNqaOIjVJjhTBXAlqqQBOkMzhk41zPCK2zBv8uktQVreLixcoQKAxxD8e81e-YdU8w",
            "expires_in": 60,
            "refresh_expires_in": 1800,
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICIxZTQ5MThlOS1jMjIxLTQwNzEtYWZjNC05MzkxZmJmMGFhYTkifQ.eyJleHAiOjE2NjM1MjcwNDMsImlhdCI6MTY2MzUyNTI0MywianRpIjoiNDczY2M4MWMtNWM1ZC00NTkxLWE3OTAtYzQ2Yjc3NWQzNmE3IiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2F1dGgvcmVhbG1zL21hc3RlciIsImF1ZCI6Imh0dHA6Ly9sb2NhbGhvc3Q6ODA4MC9hdXRoL3JlYWxtcy9tYXN0ZXIiLCJzdWIiOiJlYThkMmQwMS1jNjU2LTQxNmYtYTJmYS0wZGIxMTQ1OTc1MjkiLCJ0eXAiOiJSZWZyZXNoIiwiYXpwIjoiYWRtaW4tY2xpIiwic2Vzc2lvbl9zdGF0ZSI6IjkwYmIyMDUyLTU5N2UtNGI2Ny04Mjg0LWFlN2Y4NjFlZGQyNyIsInNjb3BlIjoiZW1haWwgcHJvZmlsZSIsInNpZCI6IjkwYmIyMDUyLTU5N2UtNGI2Ny04Mjg0LWFlN2Y4NjFlZGQyNyJ9.jrd7_VYHBXIpm0QZK72he8RRsGJIXVzehUXIVhg-Qds",
            "token_type": "Bearer",
            "not-before-policy": 0,
            "session_state": "90bb2052-597e-4b67-8284-ae7f861edd27",
            "scope": "email profile",
        }
        responses.post(event_url,
                       match=[responses.matchers.header_matcher({"content-type": "application/x-www-form-urlencoded"}),
                              responses.matchers.urlencoded_params_matcher({"grant_type": "password",
                                                                            "client_id": "admin-cli",
                                                                            "username": Utility.environment["idp"]["admin_username"],
                                                                            "password": Utility.environment["idp"]["admin_password"]})
                              ],
                       json=response_data,
                       status=200)
        response_token = IDPHelper.get_admin_access_token()
        assert response_token == response_data["access_token"]

    def test_save_keycloak_config_sso_disabled(self, monkeypatch):
        monkeypatch.setitem(Utility.environment["idp"], "enable", False)
        data = {
            "realm_name": "NewAzureAD",
            "client_id": "12354",
            "client_secret": "12345",
            "config_type": "azure_oidc",
            "config": {"tenant": "1234"},
        }
        with pytest.raises(AppException, match="SSO is not enabled"):
            IDPProcessor.save_idp_config(data=data, user=get_user())

    @responses.activate
    def test_save_keycloak_config_new(self, monkeypatch, set_idp_props):
        def _get_admin_token(*args, **kwargs):
            return (
                "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJjMmdiOEdnUDJQdE1VY"
            )

        def _add_role_to_service_account_in_client(*args, **kwargs):
            return None

        def _create_autherization_flow(*args, **kwargs):
            return None

        def _get_realm_clients(*args, **kwargs):
            return get_idp_clients_list()

        def _allow_full_access_for_client(*args, **kwargs):
            if kwargs.get("get_service_user"):
                return "eyJhbGciOiJSUzI1NiIsInR5c", "12345"
            return "eyJhbGciOiJSUzI1NiIsInR5c"

        monkeypatch.setattr(IDPHelper, "get_admin_access_token", _get_admin_token)
        monkeypatch.setattr(IDPHelper, "get_realm_clients", _get_realm_clients)
        monkeypatch.setattr(
            IDPHelper, "allow_full_access_for_client", _allow_full_access_for_client
        )
        monkeypatch.setattr(
            IDPHelper,
            "add_role_to_service_account_in_client",
            _add_role_to_service_account_in_client,
        )
        monkeypatch.setattr(
            IDPHelper, "create_autherization_flow", _create_autherization_flow
        )
        realm_name = "IDPTEST"
        data = {
            "organization": "Test",
            "config": {
                "realm_name": realm_name,
                "config_type": "oidc",
                "config_sub_type": "azure_oidc",
                "client_id": "95280cec-93ca-4a94-a852-c23aa1039beb",
                "client_secret": "F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075eheP8cLk",
                "tenant": "fa1b21ce-4ca5-4009",
            },
        }
        add_realm_url = (
            Utility.environment["idp"]["server_url"]
            + IDPURLConstants.ADD_REALM_URL.value
        )

        responses.add("POST", add_realm_url, status=201)

        add_idp_url = Utility.environment["idp"][
            "server_url"
        ] + IDPURLConstants.ADD_IDP_TO_REALM_URL.value.format(realm_name=realm_name)

        responses.add("POST", add_idp_url, status=200)

        get_clients_url = Utility.environment["idp"][
            "server_url"
        ] + IDPURLConstants.GET_CLIENTS_FOR_REALM_URL.value.format(
            realm_name=realm_name
        )

        responses.add("POST", get_clients_url, json={})

        add_ipp_payload = {
            "alias": realm_name,
            "providerId": "keycloak-oidc1",
            "enabled": True,
            "updateProfileFirstLoginMode": "on",
            "trustEmail": False,
            "storeToken": False,
            "addReadTokenRoleOnCreate": False,
            "authenticateByDefault": False,
            "linkOnly": False,
            "firstBrokerLoginFlowAlias": "first broker login",
            "config": {},
        }
        add_idp_realm_url = Utility.environment["idp"][
            "server_url"
        ] + IDPURLConstants.ADD_IDP_TO_REALM_URL.value.format(realm_name=realm_name)
        responses.add("POST", add_idp_realm_url, status=200, json=add_ipp_payload)

        update_client_access_url = Utility.environment["idp"][
            "server_url"
        ] + IDPURLConstants.UPDATE_CLIENT_URL.value.format(
            realm_client_id="12345", realm_name=realm_name
        )

        responses.add("POST", update_client_access_url, status=200, json={})

        redirect_url = IDPProcessor.save_idp_config(data=data, user=get_user())
        saved_data = IdpConfig.objects(account=get_user().account).get()
        assert saved_data.realm_name == realm_name
        assert (
            redirect_url
            == f"http://localhost:8080/auth/realms/{realm_name}/broker/{realm_name}/endpoint"
        )

    def test_get_idp_config(self, set_idp_props):
        user = get_user()
        idp_config = IDPProcessor.get_idp_config(account=user.account)
        realm_name = "IDPTEST"
        assert idp_config is not None
        assert idp_config["client_id"] == "95280cec-93ca-4a94-a852-c23aa10*****"
        assert idp_config["client_secret"] == "F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075ehe*****"
        assert idp_config["organization"] == "Test"
        assert idp_config["tenant"] == "fa1b21ce-4ca5-4009"
        assert (
            idp_config["idp_redirect_uri"]
            == f"http://localhost:8080/auth/realms/{realm_name}/broker/{realm_name}/endpoint"
        )

    def test_get_idp_config_not_exists(self):
        account = "5"
        idp_config = IDPProcessor.get_idp_config(account=account)
        assert idp_config is not None
        assert idp_config == {}

    def test_update_idp_config_tenant(self, monkeypatch, set_idp_props):
        def _get_admin_token(*args, **kwargs):
            return (
                "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJjMmdiOEdnUDJQdE1VY"
            )

        def _upsert_identity_provider(*args, **kwargs):
            return None

        monkeypatch.setattr(
            IDPHelper, "upsert_identity_provider", _upsert_identity_provider
        )
        monkeypatch.setattr(IDPHelper, "get_admin_access_token", _get_admin_token)

        realm_name = "IDPTEST"
        user = get_user()
        data = {
            "organization": "Test",
            "config": {
                "realm_name": realm_name,
                "config_type": "oidc",
                "config_sub_type": "azure_oidc",
                "client_id": "95280cec-93ca-4a94-a852-c23aa1039beb",
                "client_secret": "F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075eheP8cLk",
                "tenant": "fa1b21ce-4ca5-4009_new",
            },
        }

        IDPProcessor.save_idp_config(data=data, user=get_user())

        updated_idp_config = IDPProcessor.get_idp_config(account=user.account)
        assert updated_idp_config is not None
        assert updated_idp_config["client_id"] == "95280cec-93ca-4a94-a852-c23aa10*****"
        assert (
            updated_idp_config["client_secret"]
            == "F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075ehe*****"
        )
        assert updated_idp_config["organization"] == "Test"
        assert updated_idp_config["tenant"] != "fa1b21ce-4ca5-4009"
        assert updated_idp_config["tenant"] == "fa1b21ce-4ca5-4009_new"

    def test_update_idp_config_client_id(self, monkeypatch, set_idp_props):
        def _get_admin_token(*args, **kwargs):
            return (
                "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJjMmdiOEdnUDJQdE1VY"
            )

        def _upsert_identity_provider(*args, **kwargs):
            return None

        monkeypatch.setattr(
            IDPHelper, "upsert_identity_provider", _upsert_identity_provider
        )

        monkeypatch.setattr(IDPHelper, "get_admin_access_token", _get_admin_token)

        realm_name = "IDPTEST"
        user = get_user()
        data = {
            "organization": "Test",
            "config": {
                "realm_name": realm_name,
                "config_type": "oidc",
                "config_sub_type": "azure_oidc",
                "client_id": "new_95280cec-93ca-4a94-a852-c23aa1039beb",
                "client_secret": "F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075eheP8cLk",
                "tenant": "fa1b21ce-4ca5-4009_new",
            },
        }

        IDPProcessor.save_idp_config(data=data, user=get_user())

        updated_idp_config = IDPProcessor.get_idp_config(account=user.account)
        assert updated_idp_config is not None
        assert (
            updated_idp_config["client_id"]
            == "new_95280cec-93ca-4a94-a852-c23aa10*****"
        )
        assert updated_idp_config["client_id"] != "95280cec-93ca-4a94-a852-c23aa10*****"
        assert (
            updated_idp_config["client_secret"]
            == "F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075ehe*****"
        )
        assert updated_idp_config["organization"] == "Test"
        assert updated_idp_config["tenant"] == "fa1b21ce-4ca5-4009_new"

    def test_update_idp_config_client_secret(self, monkeypatch, set_idp_props):
        def _get_admin_token(*args, **kwargs):
            return (
                "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJjMmdiOEdnUDJQdE1VY"
            )

        def _upsert_identity_provider(*args, **kwargs):
            return None

        monkeypatch.setattr(
            IDPHelper, "upsert_identity_provider", _upsert_identity_provider
        )

        monkeypatch.setattr(IDPHelper, "get_admin_access_token", _get_admin_token)

        realm_name = "IDPTEST"
        user = get_user()
        data = {
            "organization": "Test",
            "config": {
                "realm_name": realm_name,
                "config_type": "oidc",
                "config_sub_type": "azure_oidc",
                "client_id": "new_95280cec-93ca-4a94-a852-c23aa1039beb",
                "client_secret": "new_F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075eheP8cLk",
                "tenant": "fa1b21ce-4ca5-4009_new",
            },
        }

        IDPProcessor.save_idp_config(data=data, user=get_user())

        updated_idp_config = IDPProcessor.get_idp_config(account=user.account)
        assert updated_idp_config is not None
        assert (
            updated_idp_config["client_id"]
            == "new_95280cec-93ca-4a94-a852-c23aa10*****"
        )
        assert updated_idp_config["client_id"] != "95280cec-93ca-4a94-a852-c23aa10*****"
        assert (
            updated_idp_config["client_secret"]
            != "F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075ehe*****"
        )
        assert (
            updated_idp_config["client_secret"]
            == "new_F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075ehe*****"
        )
        assert updated_idp_config["organization"] == "Test"
        assert updated_idp_config["tenant"] == "fa1b21ce-4ca5-4009_new"

    def test_delete_idp_config(self, monkeypatch, set_idp_props):
        def _delete_realm(*args, **kwargs):
            return None

        monkeypatch.setattr(IDPHelper, "delete_realm", _delete_realm)
        user = get_user()
        realm_name = "IDPTEST"
        fetched_idp_config = IDPProcessor.get_idp_config(account=user.account)

        assert (
            fetched_idp_config["client_id"]
            == "new_95280cec-93ca-4a94-a852-c23aa10*****"
        )
        assert fetched_idp_config["client_id"] != "95280cec-93ca-4a94-a852-c23aa10*****"
        assert (
            fetched_idp_config["client_secret"]
            != "F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075ehe*****"
        )
        assert (
            fetched_idp_config["client_secret"]
            == "new_F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075ehe*****"
        )
        assert fetched_idp_config["organization"] == "Test"
        assert fetched_idp_config["tenant"] == "fa1b21ce-4ca5-4009_new"

        IDPProcessor.delete_idp(realm_name=realm_name, user=user.email)
        fetched_idp_config = IDPProcessor.get_idp_config(account=user.account)
        assert fetched_idp_config == {}

    def test_get_idp_config_after_delete(self, monkeypatch, set_idp_props):
        def _delete_realm(*args, **kwargs):
            return None

        monkeypatch.setattr(IDPHelper, "delete_realm", _delete_realm)
        realm_name = "IDPTEST"
        with pytest.raises(AppException, match="IDP config not found"):
            IDPProcessor.delete_idp(realm_name=realm_name)

    @responses.activate
    def test_get_realm_clients(self, monkeypatch, set_idp_props):
        def _get_admin_token(*args, **kwargs):
            return (
                "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJjMmdiOEdnUDJQdE1VY"
            )

        monkeypatch.setattr(IDPHelper, "get_admin_access_token", _get_admin_token)

        realm_name = "IDPTEST"

        url = Utility.environment["idp"][
            "server_url"
        ] + IDPURLConstants.GET_CLIENTS_FOR_REALM_URL.value.format(
            realm_name=realm_name
        )

        responses.add("GET", url, status=200, json=get_idp_clients_list())

        result = IDPHelper.get_realm_clients(realm_name)
        assert result is not None
        assert result[0]["clientId"] == IDPClientNames.ACCOUNT.value

    def test_get_realm_clients_error(self, monkeypatch, set_idp_props):
        def _get_admin_token(*args, **kwargs):
            return (
                "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJjMmdiOEdnUDJQdE1VY"
            )

        monkeypatch.setitem(
            Utility.environment["idp"], "server_url", "http:localhost:8080/auth"
        )
        monkeypatch.setattr(IDPHelper, "get_admin_access_token", _get_admin_token)
        realm_name = "IDPTEST"
        with pytest.raises(AppException, match="Could not get clients"):
            IDPHelper.get_realm_clients(realm_name)

    def test_idp_helper(self):
        idp_helper = IDPFactory.get_supported_idp("idp")
        assert idp_helper.__name__ == "IDPHelper"

    def test_identify_user_and_create_access_token_new_user(
        self, monkeypatch, set_idp_props
    ):
        def _get_idp_token(*args, **kwargs):
            return {
                "email": "test_sso_user@demo.in",
                "given_name": "test",
                "family_name": "user",
            }

        def _validate_org_settings(*args, **kwargs):
            return

        monkeypatch.setattr(IDPProcessor, "get_idp_token", _get_idp_token)
        monkeypatch.setattr(
            OrgProcessor, "validate_org_settings", _validate_org_settings
        )

        realm_name = "IDPTEST"
        loop = asyncio.new_event_loop()
        existing_user, user_details, access_token = loop.run_until_complete(
            IDPProcessor.identify_user_and_create_access_token(
                realm_name, "session_state", "code"
            )
        )
        assert user_details["email"] == "test_sso_user@demo.in"
        assert existing_user == False
        assert access_token is not None

    def test_identify_user_and_create_access_token_existing_user(
        self, monkeypatch, set_idp_props
    ):
        def _get_idp_token(*args, **kwargs):
            return {
                "email": "test_sso_user@demo.in",
                "given_name": "test",
                "family_name": "user",
            }

        def _validate_org_settings(*args, **kwargs):
            return

        monkeypatch.setattr(IDPProcessor, "get_idp_token", _get_idp_token)
        monkeypatch.setattr(
            OrgProcessor, "validate_org_settings", _validate_org_settings
        )

        realm_name = "IDPTEST"
        loop = asyncio.new_event_loop()
        existing_user, user_details, access_token = loop.run_until_complete(
            IDPProcessor.identify_user_and_create_access_token(
                realm_name, "session_state", "code"
            )
        )
        assert user_details["email"] == "test_sso_user@demo.in"
        assert existing_user == True
        assert access_token is not None

    def test_get_supported_provider_list(self):
        provider_list = IDPProcessor.get_supported_provider_list()
        assert provider_list == {
            "saml": "SAML v2.0",
            "oidc": "OpenID Connect v1.0",
            "azure-oidc": "OpenID Connect with Azure AD",
            "keycloak-oidc": "Keycloak OpenID Connect",
        }
