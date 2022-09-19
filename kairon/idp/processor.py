from mongoengine.errors import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.idp.constants import IDPConfigType, KEYCLOAK_SUPPORTED_PROVIDER
from kairon.idp.data_objects import IdpConfig
from kairon.idp.factory import IDPFactory
from kairon.shared.auth import Authentication


class IDPProcessor:
    @staticmethod
    def save_idp_config(user, data):
        helper = IDPFactory.get_supported_idp(Utility.environment["idp"]["type"])
        try:
            helper.upsert_identity_provider(realm_name=data.get("realm_name"),
                                            operation="update",
                                            client_id=data.get("client_id"),
                                            client_secret=data.get("client_secret"),
                                            config_type=data.get("config_type"),
                                            tenant=data["config"].get("tenant")
                                            )

            idp_config = IdpConfig.objects(account=user.account).get()
            idp_config.keycloak_server = data.get("keycloak_server")
            idp_config.realm_name = data.get("realm_name")
            idp_config.client_id = data.get("client_id")
            idp_config.client_secret = data.get("client_secret")
            idp_config.config_type = data.get("config_type")
            idp_config.save()
        except DoesNotExist:
            if not Utility.environment["idp"]["enable"]:
                raise AppException("SSO is not enabled")

            resp = helper.create_realm(realm_name=data.get("realm_name"))
            if resp.status_code == 409:
                raise AppException("Realm already present")
            elif resp.status_code != 201:
                raise AppException("Could not create realm")
            helper.upsert_identity_provider(realm_name=data.get("realm_name"),
                                            operation="create",
                                            client_id=data.get("client_id"),
                                            client_secret=data.get("client_secret"),
                                            config_type=data.get("config_type"),
                                            tenant=data["config"].get("tenant")
                                            )
            helper.allow_full_access_for_client(realm_name=data.get("realm_name"))
            idp_config = IdpConfig(
                user=user.email,
                account=user.account,
                idp_server=data.get("keycloak_server"),
                realm_name=data.get("realm_name"),
                client_id=data.get("client_id"),
                client_secret=data.get("client_secret"),
                config_type=data.get("config_type")
            )
            idp_config.save()

    @staticmethod
    def get_idp_config(account):
        try:
            idp_config_data = IdpConfig.objects(account=account).get()
            keycloak_config = idp_config_data.to_mongo().to_dict()
            keycloak_config.pop("_id")
            keycloak_config["client_id"] = Utility.decrypt_message(keycloak_config["client_id"])
            keycloak_config["client_secret"] = Utility.decrypt_message(keycloak_config["client_secret"])
        except DoesNotExist:
            keycloak_config = {}
        return keycloak_config

    @staticmethod
    def create_realm(realm_name, account):
        helper = IDPFactory.get_supported_idp(Utility.environment["idp"]["IDP_TYPE"])
        helper.create_realm(realm_name)

    @staticmethod
    def get_redirect_uri(realm_name):
        helper = IDPFactory.get_supported_idp(Utility.environment["idp"]["IDP_TYPE"])
        idp = helper.get_fastapi_keycloak(realm_name)
        return idp.realm_uri

    @staticmethod
    def identify_user_and_create_access_token(realm_name, session_state, code):
        helper = IDPFactory.get_supported_idp(Utility.environment["idp"]["IDP_TYPE"])
        idp = helper.get_fastapi_idp_object(realm_name)
        idp_token = idp._decode_token(
            idp.exchange_authorization_code(session_state=session_state, code=code).access_token)
        access_token = Authentication.create_access_token(data={"sub": idp_token["email"]})
        return access_token

    @staticmethod
    def get_supported_provider_list():
        return KEYCLOAK_SUPPORTED_PROVIDER
