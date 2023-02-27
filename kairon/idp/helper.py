import json

from fastapi_keycloak import FastAPIKeycloak
from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.idp.constants import (
    IDPURLConstants,
    AUTH_ACCESS_TOKEN_PAYLOAD,
    ADD_REALM_PAYLOAD,
    IDPPayload,
    ADD_BROWSER_AUTH_FLOW_CONFIG_PAYLOAD,
    ADD_IPD_CLIENT_PAYLOAD, IDPClientNames
)
from kairon.idp.data_objects import IdpConfig
import requests


class IDPHelper:

    def __int__(self):
        if not Utility.environment["idp"]["enable"]:
            raise AppException("IDP is not enabled")

    @staticmethod
    def get_admin_access_token():
        if not Utility.environment["idp"]["enable"]:
            raise AppException("SSO is not enabled")

        url = Utility.environment["idp"]["server_url"] + IDPURLConstants.AUTH_TOKEN_URL.value.format(
            realm_name="master")
        headers = {"content-type": "application/x-www-form-urlencoded"}
        body = AUTH_ACCESS_TOKEN_PAYLOAD.format(username=Utility.environment["idp"]["admin_username"],
                                                password=Utility.environment["idp"]["admin_password"])

        try:
            result = requests.post(url=url, headers=headers, data=body)
            if result.status_code == 200:
                return result.json().get("access_token")
            else:
                raise AppException("Could not get token")
        except Exception:
            return None

    @staticmethod
    def create_realm(realm_name):
        url = Utility.environment["idp"]["server_url"] + IDPURLConstants.ADD_REALM_URL.value
        headers = {
            "Authorization": "Bearer " + IDPHelper.get_admin_access_token()
        }
        body = ADD_REALM_PAYLOAD
        body["id"] = realm_name
        body["realm"] = realm_name
        body["displayName"] = realm_name

        try:
            return Utility.execute_http_request("POST", http_url=url, request_body=body, headers=headers,
                                                return_json=False)
        except AppException:
            raise AppException("Could not create realm")

    @staticmethod
    def upsert_identity_provider(realm_name, operation, **kwargs):
        method = "POST"
        url = Utility.environment["idp"]["server_url"] + IDPURLConstants.ADD_IDP_TO_REALM_URL.value.format(
            realm_name=realm_name)
        if operation == "update":
            method = "PUT"
            url = Utility.environment["idp"]["server_url"] + IDPURLConstants.UPDATE_IDP_TO_REALM_URL.value.format(
                realm_name=realm_name, alias_name=realm_name)
        headers = {
            "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
            "Content-Type": "application/json"
        }
        body = json.dumps(IDPPayload.get_idp_config(idp_provider=kwargs.get("config_type")))

        body = body.replace("TENANT", kwargs.get("tenant"))
        body = body.replace("REALM_NAME", realm_name)
        body = body.replace("CLIENT_ID", kwargs.get("client_id"))
        body = body.replace("CLIENT_SECRET", kwargs.get("client_secret"))
        body = body.replace("PROVIDER_ID", kwargs.get("config_type").split("_")[1])

        try:
            Utility.execute_http_request(method, http_url=url, request_body=json.loads(body), headers=headers,
                                         return_json=False)
        except AppException:
            raise AppException("Could not create realm")

    @staticmethod
    def allow_full_access_for_client(realm_name, client_name, get_service_user=False):
        try:
            clients = IDPHelper.get_realm_clients(realm_name)
            for client in clients:
                if client["clientId"] == client_name:
                    body = client
                    realm_client_id = body["id"]
                    body["fullScopeAllowed"] = True
                    body["publicClient"] = False
                    body["bearerOnly"] = False
                    body["directAccessGrantsEnabled"] = True
                    body["serviceAccountsEnabled"] = True

                    url = Utility.environment["idp"]["server_url"] + IDPURLConstants.UPDATE_CLIENT_URL.value.format(
                        realm_client_id=realm_client_id, realm_name=realm_name)
                    headers = {
                        "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
                    }
                    Utility.execute_http_request("PUT", http_url=url, request_body=body, headers=headers,
                                                 return_json=False)
                    idp_client_secret = IDPHelper.get_secret_for_client(realm_name=realm_name,
                                                                        client_id=realm_client_id)
                    if get_service_user:
                        service_account_id = IDPHelper.get_service_account_user_for_client(realm_name, realm_client_id)
                        return idp_client_secret, service_account_id
                    return idp_client_secret
        except AppException:
            raise AppException(f"Could not update access in realm client {client_name}")

    @staticmethod
    def get_fastapi_idp_object(realm_name):
        if not Utility.environment["idp"]["enable"]:
            raise AppException("SSO is not enabled")
        try:
            config = IdpConfig.objects().get(realm_name=realm_name)
            if not config.status:
                raise AppException("SSO is disable for your organization")
        except DoesNotExist:
            raise AppException("No sso configuration found for your account")

        try:
            return FastAPIKeycloak(
                server_url=Utility.environment["idp"]["server_url"],
                client_id=config.idp_client_id,
                client_secret=config.idp_client_secret,
                admin_client_secret=config.idp_admin_client_secret,
                realm=realm_name,
                callback_uri=Utility.environment["idp"]["callback_frontend_url"] + f"/login/idp/callback/{realm_name}"
            )

        except Exception as ex:
            raise AppException(f"Error occures {ex}")

    @staticmethod
    def create_autherization_flow(realm_name):
        url = Utility.environment["idp"]["server_url"] + \
              IDPURLConstants.BROWSER_AUTH_FLOW_EXECUTION_URL.value.format(realm_name=realm_name)
        headers = {
            "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
        }
        try:
            browser_auth_flows = Utility.execute_http_request("GET", http_url=url, headers=headers)
            for auth_flow in browser_auth_flows:
                if auth_flow["providerId"] == "identity-provider-redirector":
                    body = auth_flow
                    browser_auth_flow_id = auth_flow["id"]
                    body["requirement"] = "REQUIRED"
                    Utility.execute_http_request("PUT", http_url=url, request_body=body, headers=headers,
                                                 return_json=False)

                    url = Utility.environment["idp"][
                              "server_url"] + IDPURLConstants.BROWSER_AUTH_FLOW_EXECUTION_CONFIG_URL.value.format(
                        flow_execution_id=browser_auth_flow_id, realm_name=realm_name)
                    body = json.dumps(ADD_BROWSER_AUTH_FLOW_CONFIG_PAYLOAD)
                    body = body.replace("REALM_NAME", realm_name)
                    Utility.execute_http_request("POST", http_url=url, request_body=json.loads(body), headers=headers,
                                                 return_json=False)
                    break
        except AppException as ex:

            raise AppException(f"Could not create auth flow {ex}")

    @staticmethod
    def create_ipd_client(realm_name):
        url = Utility.environment["idp"]["server_url"] + \
              IDPURLConstants.GET_CLIENTS_FOR_REALM_URL.value.format(realm_name=realm_name)
        headers = {
            "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
        }
        try:
            body = json.dumps(ADD_IPD_CLIENT_PAYLOAD)
            body = body.replace("REALM_NAME", realm_name)
            body = body.replace("REDIRECT_URI",
                                Utility.environment["idp"][
                                    "callback_frontend_url"] + f"/login/idp/callback/{realm_name}")

            Utility.execute_http_request("POST", http_url=url, request_body=json.loads(body), headers=headers,
                                         return_json=False)
        except Exception:
            raise AppException("Could not create client")

    @staticmethod
    def get_secret_for_client(realm_name, client_id):
        url = Utility.environment["idp"]["server_url"] + \
              IDPURLConstants.GET_SECRET_FOR_IDP_CLIENT_URL.value.format(realm_name=realm_name,
                                                                         realm_client_id=client_id)
        headers = {
            "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
        }
        try:
            resp = Utility.execute_http_request("GET", http_url=url, headers=headers)
            return resp.get("value")
        except AppException:
            raise AppException("Could not create clients")

    @staticmethod
    def get_service_account_user_for_client(realm_name, client_id):
        url = Utility.environment["idp"]["server_url"] + \
              IDPURLConstants.SERVICE_ACCOUNT_USER_URL.value.format(realm_name=realm_name,
                                                                    realm_client_id=client_id)
        headers = {
            "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
        }
        try:
            resp = Utility.execute_http_request("GET", http_url=url, headers=headers)
            return resp.get("id")
        except AppException:
            raise AppException("User not found, client access type might be public")

    @staticmethod
    def get_available_role_for_service_account_in_client(realm_name, client_id, user_id):
        url = Utility.environment["idp"]["server_url"] + \
              IDPURLConstants.AVAILABLE_ROLE_FOR_CLIENT.value.format(realm_name=realm_name,
                                                                     realm_client_id=client_id,
                                                                     service_user_id=user_id)
        headers = {
            "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
        }
        try:
            return Utility.execute_http_request("GET", http_url=url, headers=headers, return_json=False)
        except AppException:
            raise AppException("No role available")

    @staticmethod
    def add_role_to_service_account_in_client(realm_name, user_id):

        try:
            clients = IDPHelper.get_realm_clients(realm_name)
            for client in clients:
                if client["clientId"] in (IDPClientNames.ACCOUNT.value, IDPClientNames.REALM_MANAGEMENT.value):
                    resp = IDPHelper.get_available_role_for_service_account_in_client(realm_name, client["id"], user_id)
                    headers = {"Authorization": "Bearer " + IDPHelper.get_admin_access_token()}
                    url = Utility.environment["idp"]["server_url"] + \
                          IDPURLConstants.ADD_ROLES_TO_SERVICE_ACCOUNT.value.format(
                              realm_name=realm_name,
                              realm_client_id=client["id"],
                              service_user_id=user_id)
                    Utility.execute_http_request("POST", http_url=url, request_body=resp.json(), headers=headers,
                                                 return_json=False)
        except AppException:
            raise AppException("No role available")

    @staticmethod
    def get_realm_clients(realm_name):
        url = Utility.environment["idp"]["server_url"] + \
              IDPURLConstants.GET_CLIENTS_FOR_REALM_URL.value.format(realm_name=realm_name)
        headers = {
            "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
        }
        try:
            return Utility.execute_http_request("GET", http_url=url, headers=headers)
        except AppException:
            raise AppException("Could not get clients")

    @staticmethod
    def delete_realm(realm_name):
        url = Utility.environment["idp"]["server_url"] + IDPURLConstants.ADD_REALM_URL.value + f"/{realm_name}"
        headers = {
            "Authorization": "Bearer " + IDPHelper.get_admin_access_token()
        }
        try:
            return Utility.execute_http_request("DELETE", http_url=url,  headers=headers, return_json=False)
        except AppException:
            raise AppException("Exception occure while deleting realm")
