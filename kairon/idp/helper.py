import json

import requests
from fastapi_keycloak import FastAPIKeycloak
from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.idp.constants import IDPURLConstants, AUTH_ACCESS_TOKEN_PAYLOAD, ADD_REALM_PAYLOAD, \
    IDPPayload
from kairon.idp.data_objects import IdpConfig


class IDPHelper:

    def __int__(self):
        if not Utility.environment["idp"]["enable"]:
            raise AppException("IDP is not enabled")

    @staticmethod
    def get_admin_access_token():
        if not Utility.environment["idp"]["IDP_ENABLED"]:
            raise AppException("SSO is not enabled")

        url = Utility.environment["idp"]["server_url"] + IDPURLConstants.AUTH_TOKEN_URL.value.format(
            realm_name="master")
        headers = {"content-type": "application/x-www-form-urlencoded"}
        body = AUTH_ACCESS_TOKEN_PAYLOAD.format(username=Utility.environment["idp"]["admin_username"],
                                                password=Utility.environment["idp"]["admin_password"])

        try:
            result = requests.post(url=url, headers=headers, data=body)
            result = result.json()
            return result.get("access_token")
        except AppException:
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
    def allow_full_access_for_client(realm_name, client_name="account"):
        url = Utility.environment["idp"]["server_url"] + \
              IDPURLConstants.GET_CLIENTS_FOR_REALM_URL.value.format(realm_name=realm_name)
        headers = {
            "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
        }
        try:
            clients = Utility.execute_http_request("GET", http_url=url, headers=headers)
            for client in clients:
                if client["clientId"] is client_name:
                    body = client
                else:
                    raise AppException("Client not found")
                realm_client_id = body["id"]
                body["fullScopeAllowed"] = True

                url = Utility.environment["idp"]["server_url"] + IDPURLConstants.UPDATE_CLIENT_URL.value.format(
                    realm_client_id=realm_client_id)
                headers = {
                    "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
                }
                Utility.execute_http_request("PUT", http_url=url, request_body=body, headers=headers,
                                             return_json=False)
        except AppException:
            raise AppException("Could not update access in realm client")

    # @staticmethod
    # def attach_roles(realm_name, **kwargs):
    #     url = Utility.environment["idp"]["server_url"] +
    #     IDPURLConstants.ADD_IDP_TO_REALM_URL.value.format(realm_name=realm_name)
    #     headers = {
    #         "Authorization": "Bearer " + IDPHelper.get_admin_access_token(),
    #         "Content-Type": "application/json"
    #     }
    #     body = str(CREATE_IDP_PAYLOAD).format(tenant=kwargs.get("tenant"))
    #
    #     try:
    #         Utility.execute_http_request("POST", http_url=url, request_body=json.loads(body), headers=headers)
    #     except AppException:
    #         raise AppException("Could not create realm")
    #
    @staticmethod
    def get_fastapi_idp_object(realm_name):
        if not Utility.environment["idp"]["IDP_ENABLED"]:
            raise AppException("SSO is not enabled")
        try:
            config = IdpConfig.objects().get(realm_name=realm_name)
        except DoesNotExist:
            raise AppException("No sso configuration found for your account")

        if Utility.environment["idp"]["enable"]:
            raise AppException("SSO is not enabled")

        idp = FastAPIKeycloak(
            server_url=config.keycloak_server,
            client_id=config.client_id,
            client_secret=config.client_secret,
            admin_client_secret=Utility.environment["idp"]["admin_client_secret"],
            realm=realm_name,
            callback_uri=Utility.environment["app"]["server_url"]
        )
        return idp
