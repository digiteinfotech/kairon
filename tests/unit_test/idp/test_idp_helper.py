import os

import pytest
import responses
from mongoengine import connect

from kairon.exceptions import AppException
from kairon.idp.constants import IDPURLConstants
from kairon.idp.data_objects import IdpConfig
from kairon.idp.helper import IDPHelper
from kairon.idp.processor import IDPProcessor
from kairon.shared.utils import Utility
from stress_test.data_objects import User


def get_user():
    return User(
        email='test',
        first_name='test',
        last_name='test',
        account=2,
        status=True,
        is_integration_user=False)


class TestIDP:

    @pytest.fixture()
    def set_idp_props(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['idp'], 'enable', True)
        monkeypatch.setitem(Utility.environment['idp'], 'server_url', 'http://localhost:8080/auth')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_username', 'sample')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_password', 'sample')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_client_secret', '8e5b7371-be31-4a5c-8b58-a4f1baf519c9')
        monkeypatch.setitem(Utility.environment['idp'], 'type', "idp")
        monkeypatch.setitem(Utility.environment['idp'], 'callback_uri',
                            'https://9722-2405-201-23-90ed-b834-5dbc-794f-adb.in.ngrok.io/login/idp/callback/REALM_NAME')

    @pytest.fixture(autouse=True, scope='class')
    def init_connection(self):
        os.environ["system_file"] = "./tests/testing_data/system.yaml"
        Utility.load_environment()
        connect(**Utility.mongoengine_connection())
        Utility.environment['elasticsearch']['enable'] = False
        yield None
        Utility.environment['notifications']['enable'] = False

    def test_get_admin_access_token_disabled(self, monkeypatch, set_idp_props):
        monkeypatch.setitem(Utility.environment['idp'], 'enable', False)

        with pytest.raises(AppException, match="SSO is not enabled"):
            IDPHelper.get_admin_access_token()

    def test_get_admin_access_token_wrong_url(self, monkeypatch, set_idp_props):
        monkeypatch.setitem(Utility.environment['idp'], 'server_url', 'http:localhost:8080/auth')

        token = IDPHelper.get_admin_access_token()
        assert token == None

    def test_get_admin_access_token_wrong_username_or_password(self, monkeypatch, set_idp_props):
        monkeypatch.setitem(Utility.environment['idp'], 'admin_username', 'wrongusername')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_password', 'worngpassword')

        auth_url = Utility.environment["idp"]["server_url"] + IDPURLConstants.AUTH_TOKEN_URL.value.format(
            realm_name="master")
        responses.add(
            "POST", auth_url, json={
                "error": "invalid_grant",
                "error_description": "Invalid user credentials"
            },
            status=401
        )

        token = IDPHelper.get_admin_access_token()
        assert token is None

    @responses.activate
    def test_get_admin_access_token(self, monkeypatch, set_idp_props):
        event_url = "http://localhost:8080/auth" + IDPURLConstants.AUTH_TOKEN_URL.value.format(realm_name="master")
        responses.reset()
        response_data = {
            "access_token": "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJjMmdiOEdnUDJQdE1VYWZzb1Z3aGt0bEwxMnpwYzhHNDN2NE93UHNOS3R3In0.eyJleHAiOjE2NjM1MjUzMDMsImlhdCI6MTY2MzUyNTI0MywianRpIjoiZjUzMDdiOGUtMGZmZi00OGU4LWI0N2MtY2E5NTQ2NGE4NjdjIiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2F1dGgvcmVhbG1zL21hc3RlciIsInN1YiI6ImVhOGQyZDAxLWM2NTYtNDE2Zi1hMmZhLTBkYjExNDU5NzUyOSIsInR5cCI6IkJlYXJlciIsImF6cCI6ImFkbWluLWNsaSIsInNlc3Npb25fc3RhdGUiOiI5MGJiMjA1Mi01OTdlLTRiNjctODI4NC1hZTdmODYxZWRkMjciLCJhY3IiOiIxIiwic2NvcGUiOiJlbWFpbCBwcm9maWxlIiwic2lkIjoiOTBiYjIwNTItNTk3ZS00YjY3LTgyODQtYWU3Zjg2MWVkZDI3IiwiZW1haWxfdmVyaWZpZWQiOmZhbHNlLCJwcmVmZXJyZWRfdXNlcm5hbWUiOiJrYWlyb25rZXljbG9hayJ9.HavJzfu1igpt4IuvZCuQxInWTHz1Dt4L5Oy4q5Fw03QuudztXvUQGGthAWkjNzxGwcwhyBmlzsiLmqsj40K3epiCReEM_bL7zKhiXcXXzAzgxWvXZ4x75WYk00fMxW5eETSfIcLPyqPtGdKyyyEKS1fjtw-O_4VXhp3kO8FrSX7TC1A9Tj0R6I19RaQwSo8pxYeStHtgFri6Vuei4N7bto6pDNMn6hlkfxVelgGocs4lkdI8LRv8LgXenNDK6dd5PcaR5UGoCwU_sBa2AUZjJNqaOIjVJjhTBXAlqqQBOkMzhk41zPCK2zBv8uktQVreLixcoQKAxxD8e81e-YdU8w",
            "expires_in": 60,
            "refresh_expires_in": 1800,
            "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICIxZTQ5MThlOS1jMjIxLTQwNzEtYWZjNC05MzkxZmJmMGFhYTkifQ.eyJleHAiOjE2NjM1MjcwNDMsImlhdCI6MTY2MzUyNTI0MywianRpIjoiNDczY2M4MWMtNWM1ZC00NTkxLWE3OTAtYzQ2Yjc3NWQzNmE3IiwiaXNzIjoiaHR0cDovL2xvY2FsaG9zdDo4MDgwL2F1dGgvcmVhbG1zL21hc3RlciIsImF1ZCI6Imh0dHA6Ly9sb2NhbGhvc3Q6ODA4MC9hdXRoL3JlYWxtcy9tYXN0ZXIiLCJzdWIiOiJlYThkMmQwMS1jNjU2LTQxNmYtYTJmYS0wZGIxMTQ1OTc1MjkiLCJ0eXAiOiJSZWZyZXNoIiwiYXpwIjoiYWRtaW4tY2xpIiwic2Vzc2lvbl9zdGF0ZSI6IjkwYmIyMDUyLTU5N2UtNGI2Ny04Mjg0LWFlN2Y4NjFlZGQyNyIsInNjb3BlIjoiZW1haWwgcHJvZmlsZSIsInNpZCI6IjkwYmIyMDUyLTU5N2UtNGI2Ny04Mjg0LWFlN2Y4NjFlZGQyNyJ9.jrd7_VYHBXIpm0QZK72he8RRsGJIXVzehUXIVhg-Qds",
            "token_type": "Bearer",
            "not-before-policy": 0,
            "session_state": "90bb2052-597e-4b67-8284-ae7f861edd27",
            "scope": "email profile"
        }
        responses.add(
            "POST", event_url, json=response_data, status=200
        )

        response_token = IDPHelper.get_admin_access_token()
        assert response_token == response_data["access_token"]

    def test_save_keycloak_config_sso_disabled(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['idp'], 'enable', False)
        data = {
            "realm_name": "NewAzureAD",
            "client_id": "12354",
            "client_secret": "12345",
            "config_type": "azure_oidc",
            "config": {
                "tenant": "1234"
            }
        }
        with pytest.raises(AppException, match="SSO is not enabled"):
            IDPProcessor.save_idp_config(data=data, user=get_user())

    @responses.activate
    def test_save_keycloak_config_new(self, monkeypatch, set_idp_props):
        def _get_admin_token(*args, **kwargs):
            return "eyJhbGciOiJSUzI1NiIsInR5cCIgOiAiSldUIiwia2lkIiA6ICJjMmdiOEdnUDJQdE1VY"

        def _add_role_to_service_account_in_client(*args, **kwargs):
            return None

        def _create_autherization_flow(*args, **kwargs):
            return None

        def _get_realm_clients(*args, **kwargs):
            return [{
                "id": "d2da3349-4000-433a-99b2-6aa34fcf3c1f",
                "clientId": "account",
                "name": "${client_account}",
                "rootUrl": "${authBaseUrl}",
                "baseUrl": "/realms/realm_name_1/account/",
                "surrogateAuthRequired": False,
                "enabled": True,
                "alwaysDisplayInConsole": False,
                "clientAuthenticatorType": "client-secret",
                "redirectUris": [
                    "/realms/realm_name_1/account/*"
                ],
                "webOrigins": [],
                "notBefore": 0,
                "bearerOnly": False,
                "consentRequired": False,
                "serviceAccountsEnabled": False,
                "publicClient": True,
                "frontchannelLogout": False,
                "protocol": "openid-connect"
            },
                {
                    "id": "0300bb2f-7e3e-49fb-88f0-bec2d444e50e",
                    "clientId": "account-console",
                    "name": "${client_account-console}",
                    "enabled": True,
                    "alwaysDisplayInConsole": False,
                    "clientAuthenticatorType": "client-secret",
                    "bearerOnly": False,
                    "directAccessGrantsEnabled": False,
                    "serviceAccountsEnabled": False,
                    "publicClient": True,
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
                    "frontchannelLogout": False,
                    "protocol": "openid-connect",
                    "attributes": {},
                    "authenticationFlowBindingOverrides": {},
                    "fullScopeAllowed": True,
                    "nodeReRegistrationTimeout": 0,
                },
                {
                    "id": "8f38dc39-8328-406e-8d1a-8ae115194bc1",
                    "clientId": "broker",
                    "name": "${client_broker}",
                    "bearerOnly": True,
                    "directAccessGrantsEnabled": False,
                    "serviceAccountsEnabled": False,
                    "publicClient": False,
                    "fullScopeAllowed": False,
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
                    "clientId": "realm_name_1",
                    "name": "realm_name_1",
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
                }
            ]

        def _allow_full_access_for_client(*args, **kwargs):
            return "eyJhbGciOiJSUzI1NiIsInR5c", "12345"

        monkeypatch.setattr(IDPHelper, 'get_admin_access_token', _get_admin_token)
        monkeypatch.setattr(IDPHelper, 'get_realm_clients', _get_realm_clients)
        monkeypatch.setattr(IDPHelper, 'allow_full_access_for_client', _allow_full_access_for_client)
        monkeypatch.setattr(IDPHelper, 'add_role_to_service_account_in_client', _add_role_to_service_account_in_client)
        monkeypatch.setattr(IDPHelper, 'create_autherization_flow', _create_autherization_flow)
        realm_name = "IDPTEST"
        data = {
            "organization": "Test",
            "config": {
                "realm_name": realm_name,
                "config_type": "oidc",
                "config_sub_type": "azure_oidc",
                "client_id": "95280cec-93ca-4a94-a852-c23aa1039beb",
                "client_secret": "F1X8Q~JCqf3bNjoGUVcqPgRCAJQYL075eheP8cLk",
                "tenant": "fa1b21ce-4ca5-4009-bdf5-09f040b36c64"
            }
        }
        add_realm_url = Utility.environment["idp"]["server_url"] + IDPURLConstants.ADD_REALM_URL.value

        responses.add(
            "POST", add_realm_url, status=201
        )

        add_idp_url = Utility.environment["idp"]["server_url"] + IDPURLConstants.ADD_IDP_TO_REALM_URL.value.format(
            realm_name=realm_name)

        responses.add(
            "POST", add_idp_url, status=200
        )

        get_clients_url = Utility.environment["idp"][
                              "server_url"] + IDPURLConstants.GET_CLIENTS_FOR_REALM_URL.value.format(
            realm_name=realm_name)

        responses.add(
            "POST", get_clients_url, json={}
        )

        add_ipp_payload = {
            "alias": "NEWTEST",
            "providerId": "keycloak-oidc1",
            "enabled": True,
            "updateProfileFirstLoginMode": "on",
            "trustEmail": False,
            "storeToken": False,
            "addReadTokenRoleOnCreate": False,
            "authenticateByDefault": False,
            "linkOnly": False,
            "firstBrokerLoginFlowAlias": "first broker login",
            "config": {}
        }
        add_idp_realm_url = Utility.environment["idp"][
                                "server_url"] + IDPURLConstants.ADD_IDP_TO_REALM_URL.value.format(
            realm_name=realm_name)
        responses.add(
            "POST", add_idp_realm_url, status=200, json=add_ipp_payload
        )

        update_client_access_url = Utility.environment["idp"][
                                       "server_url"] + IDPURLConstants.UPDATE_CLIENT_URL.value.format(
            realm_client_id="12345", realm_name=realm_name)

        responses.add(
            "POST", update_client_access_url, status=200, json={}
        )

        IDPProcessor.save_idp_config(data=data, user=get_user())
        saved_data = IdpConfig.objects(account=get_user().account).get()
        saved_data = saved_data.to_mongo().to_dict()
        assert saved_data.realm_name == realm_name
