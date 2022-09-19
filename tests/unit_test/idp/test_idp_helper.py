from urllib.parse import urljoin

import pytest
import responses

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

    def test_get_admin_access_token_disabled(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['idp'], 'enable', False)
        monkeypatch.setitem(Utility.environment['idp'], 'server_url', 'http://localhost:8080')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_username', 'sample')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_password', 'sample')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_client_secret', '8e5b7371-be31-4a5c-8b58-a4f1baf519c9')
        monkeypatch.setitem(Utility.environment['idp'], 'type', True)

        with pytest.raises(AppException, match="SSO is not enabled"):
            IDPHelper.get_admin_access_token()

    def test_get_admin_access_token_worng_url(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['idp'], 'enable', True)
        monkeypatch.setitem(Utility.environment['idp'], 'server_url', 'http:localhost:8080')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_username', 'sample')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_password', 'sample')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_client_secret', '8e5b7371-be31-4a5c-8b58-a4f1baf519c9')
        monkeypatch.setitem(Utility.environment['idp'], 'type', True)

        token = IDPHelper.get_admin_access_token()
        assert token == None

    def test_get_admin_access_token_worng_username_or_password(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['idp'], 'enable', True)
        monkeypatch.setitem(Utility.environment['idp'], 'server_url', 'http://localhost:8080')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_username', 'sample')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_password', 'sample')
        monkeypatch.setitem(Utility.environment['idp'], 'admin_client_secret', '8e5b7371-be31-4a5c-8b58-a4f1baf519c9')
        monkeypatch.setitem(Utility.environment['idp'], 'type', True)

        token = IDPHelper.get_admin_access_token()
        assert token == None

    @responses.activate
    def test_get_admin_access_token(self):
        event_url = urljoin("http://localhost:8080", IDPURLConstants.AUTH_TOKEN_URL.value.format(realm_name="master"))
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
            "POST", event_url, json=response_data
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

    def test_save_keycloak_config_new(self, monkeypatch):
        monkeypatch.setitem(Utility.environment['idp'], 'enable', False)
        realm_name = "NewAzureAD"
        data = {
            "realm_name": realm_name,
            "client_id": "12354",
            "client_secret": "12345",
            "config_type": "azure_oidc",
            "config": {
                "tenant": "1234"
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
            "POST", get_clients_url, json=[
                {
                    "id": "c3abbb22-79c9-4a82-ab80-0d4ddefc632d",
                    "clientId": "account",
                    "name": "${client_account}",
                    "rootUrl": "${authBaseUrl}",
                    "baseUrl": "/realms/SingleTenant/account/",
                    "surrogateAuthRequired": False,
                    "enabled": True,
                    "alwaysDisplayInConsole": False,
                    "clientAuthenticatorType": "client-secret",
                    "redirectUris": [
                        "/realms/SingleTenant/account/*"
                    ],
                    "webOrigins": [],
                    "notBefore": 0,
                    "bearerOnly": False,
                    "consentRequired": False,
                    "standardFlowEnabled": True,
                    "implicitFlowEnabled": False,
                    "directAccessGrantsEnabled": False,
                    "serviceAccountsEnabled": False,
                    "publicClient": True,
                    "frontchannelLogout": False,
                    "protocol": "openid-connect",
                    "attributes": {
                        "id.token.as.detached.signature": "false",
                        "saml.assertion.signature": "false",
                        "saml.force.post.binding": "false",
                        "saml.multivalued.roles": "false",
                        "saml.encrypt": "false",
                        "oauth2.device.authorization.grant.enabled": "false",
                        "backchannel.logout.revoke.offline.tokens": "false",
                        "saml.server.signature": "false",
                        "saml.server.signature.keyinfo.ext": "false",
                        "use.refresh.tokens": "true",
                        "exclude.session.state.from.auth.response": "false",
                        "oidc.ciba.grant.enabled": "false",
                        "saml.artifact.binding": "false",
                        "backchannel.logout.session.required": "false",
                        "client_credentials.use_refresh_token": "false",
                        "saml_force_name_id_format": "false",
                        "require.pushed.authorization.requests": "false",
                        "saml.client.signature": "false",
                        "tls.client.certificate.bound.access.tokens": "false",
                        "saml.authnstatement": "false",
                        "display.on.consent.screen": "false",
                        "saml.onetimeuse.condition": "false"
                    },
                    "authenticationFlowBindingOverrides": {},
                    "fullScopeAllowed": True,
                    "nodeReRegistrationTimeout": 0,
                    "defaultClientScopes": [
                        "web-origins",
                        "profile",
                        "roles",
                        "email"
                    ],
                    "optionalClientScopes": [
                        "address",
                        "phone",
                        "offline_access",
                        "microprofile-jwt"
                    ],
                    "access": {
                        "view": True,
                        "configure": True,
                        "manage": True
                    }
                }]
        )

        update_access_url = Utility.environment["idp"]["server_url"] + IDPURLConstants.UPDATE_CLIENT_URL.value.format(
            realm_client_id="c3abbb22-79c9-4a82-ab80-0d4ddefc632d")
        responses.add(
            "PUT", update_access_url, status=200
        )

        IDPProcessor.save_idp_config(data=data, user=get_user())
        saved_data = IdpConfig.objects(account=get_user().account).get()
        saved_data = saved_data.to_mongo().to_dict()
        assert saved_data.realm_name == realm_name
