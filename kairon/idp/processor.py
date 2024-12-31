from urllib.parse import urlencode

from mongoengine.errors import DoesNotExist
from pydantic import SecretStr

from kairon import Utility
from kairon.exceptions import AppException
from kairon.idp.constants import IDPURLConstants
from kairon.idp.constants import KEYCLOAK_SUPPORTED_PROVIDER, IDPClientNames
from kairon.idp.data_objects import IdpConfig
from kairon.idp.factory import IDPFactory
from kairon.shared.account.processor import AccountProcessor
from kairon.shared.auth import Authentication
from kairon.shared.data.constant import FeatureMappings


class IDPProcessor:
    @staticmethod
    def save_idp_config(user, data):
        helper = IDPFactory.get_supported_idp(Utility.environment["idp"]["type"])
        if not Utility.environment["idp"]["enable"]:
            raise AppException("SSO is not enabled")
        config_data = data["config"]
        try:
            idp_config = IdpConfig.objects(account__contains=user.account).get()

            helper.upsert_identity_provider(realm_name=config_data.get("realm_name"),
                                            operation="update",
                                            client_id=config_data.get("client_id"),
                                            client_secret=config_data.get("client_secret"),
                                            config_type=config_data.get("config_sub_type"),
                                            tenant=config_data.get("tenant")
                                            )

            idp_config.config = config_data

            idp_config.save()
        except DoesNotExist:
            if not Utility.environment["idp"]["enable"]:
                raise AppException("SSO is not enabled")

            resp = helper.create_realm(realm_name=config_data.get("realm_name"))
            if resp.status_code == 409:
                raise AppException("Realm already present")
            elif resp.status_code != 201:
                raise AppException("Could not create realm")
            helper.upsert_identity_provider(realm_name=config_data.get("realm_name"),
                                            operation="create",
                                            client_id=config_data.get("client_id"),
                                            client_secret=config_data.get("client_secret"),
                                            config_type=config_data.get("config_sub_type"),
                                            tenant=config_data.get("tenant")
                                            )
            helper.create_ipd_client(realm_name=config_data.get("realm_name"))
            idp_client_secret = helper.allow_full_access_for_client(realm_name=config_data.get("realm_name"),
                                                                    client_name=config_data.get("realm_name"))
            idp_admin_client_secret, service_account_id = helper.allow_full_access_for_client(
                realm_name=config_data.get("realm_name"),
                client_name=IDPClientNames.ADMIN_CLI.value,
                get_service_user=True)
            helper.add_role_to_service_account_in_client(realm_name=config_data.get("realm_name"),
                                                         user_id=service_account_id)
            helper.create_autherization_flow(realm_name=config_data.get("realm_name"))

            idp_config = IdpConfig(
                user=user.email,
                account=[user.account],
                realm_name=config_data.get("realm_name"),
                organization=data.get("organization"),
                idp_client_id=config_data.get("realm_name"),
                idp_client_secret=idp_client_secret,
                idp_admin_client_secret=idp_admin_client_secret,
                config_type=config_data.get("config_type"),
                config_sub_type=config_data.get("config_sub_type"),
                config=config_data
            )
            idp_config.save()
        return Utility.environment["idp"]["server_url"] + \
               IDPURLConstants.BROAKER_REDIRECT_URI.value.format(realm_name=config_data.get("realm_name"))

    @staticmethod
    def get_idp_config(account):
        try:
            idp_config_data = IdpConfig.objects(account__contains=account, status=True).get()
            idp_config = idp_config_data.to_mongo().to_dict()
            result = idp_config.pop("config")
            result["client_id"] = Utility.decrypt_message(result["client_id"])[:-5] + "*****"
            result["client_secret"] = Utility.decrypt_message(result["client_secret"])[:-5] + "*****"
            result["organization"] = idp_config_data.organization
            result["idp_redirect_uri"] = Utility.environment["idp"][
                                             "server_url"] + IDPURLConstants.BROAKER_REDIRECT_URI.value.format(
                realm_name=idp_config_data.realm_name)
        except DoesNotExist:
            result = {}
        return result

    @staticmethod
    def create_realm(realm_name, account):
        helper = IDPFactory.get_supported_idp(Utility.environment["idp"]["type"])
        helper.create_realm(realm_name)

    @staticmethod
    def get_redirect_uri(realm_name):
        helper = IDPFactory.get_supported_idp(Utility.environment["idp"]["type"])
        try:
            idp = helper.get_fastapi_idp_object(realm_name)
        except AppException:
            return Utility.environment["idp"]["callback_frontend_url"] + "/login"
        query_param = {
            "response_type": "code",
            "client_id": idp.client_id,
        }

        return f"{idp.authorization_uri}?{urlencode(query_param)}"

    @staticmethod
    async def identify_user_and_create_access_token(realm_name, session_state, code):
        idp_token = IDPProcessor.get_idp_token(realm_name, session_state, code)

        try:
            AccountProcessor.get_user(idp_token['email'])
            existing_user = True
        except DoesNotExist:
            existing_user = False
            idp_token['password'] = SecretStr(Utility.generate_password())
            idp_token['account'] = idp_token['email']
            idp_token['first_name'] = idp_token['given_name']
            idp_token['last_name'] = idp_token['family_name']
            idp_token['accepted_privacy_policy'] = True
            idp_token['accepted_terms'] = True
        if existing_user:
            AccountProcessor.get_user_details(idp_token['email'])
        else:
            from kairon.shared.organization.processor import OrgProcessor
            OrgProcessor.validate_org_settings(realm_name, FeatureMappings.CREATE_USER.value)
            await AccountProcessor.account_setup(idp_token)
            tmp_token = Utility.generate_token(idp_token['email'])
            await AccountProcessor.confirm_email(tmp_token)

        access_token = Authentication.create_access_token(data={"sub": idp_token["email"]})
        return existing_user, idp_token, access_token

    @staticmethod
    def get_idp_token(realm_name, session_state, code):
        helper = IDPFactory.get_supported_idp(Utility.environment["idp"]["type"])
        idp = helper.get_fastapi_idp_object(realm_name)
        idp_token = idp._decode_token(
            idp.exchange_authorization_code(session_state=session_state, code=code).access_token)
        return idp_token

    @staticmethod
    def get_supported_provider_list():
        return KEYCLOAK_SUPPORTED_PROVIDER

    @staticmethod
    def delete_idp(realm_name, user: str = None):
        try:
            helper = IDPFactory.get_supported_idp(Utility.environment["idp"]["type"])
            helper.delete_realm(realm_name)
            idp_config_data = IdpConfig.objects(realm_name=realm_name, status=True).get()
            Utility.delete_documents(idp_config_data, user)

        except DoesNotExist:
            raise AppException("IDP config not found")
