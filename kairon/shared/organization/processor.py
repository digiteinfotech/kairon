import logging
from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.idp.data_objects import IdpConfig
from kairon.idp.processor import IDPProcessor
from kairon.shared.account.data_objects import Organization
from kairon.shared.data.constant import FeatureMappings
from kairon.shared.data.data_objects import UserOrgMappings
from kairon.shared.data.constant import ORG_SETTINGS_MESSAGES

logger = logging.getLogger(__name__)

class OrgProcessor:

    @staticmethod
    def upsert_organization(user, org_data):
        try:
            org = Organization.objects(account__contains=user.account).get()
            old_org = org.name
            org.name = org_data.get("name")
            org.create_user = org_data.get("create_user")
            org.only_sso_login = org_data.get("only_sso_login")
            org.account = org_data.get("account") if org_data.get("account") is not None else org.account
            org.save()
            try:
                idp_config = IdpConfig.objects(account__contains=user.account, organization=old_org).get()
                idp_config.organization = org_data.get("name")
                result = idp_config.config("config")
                result["client_id"] = Utility.decrypt_message(result["client_id"])
                result["client_secret"] = Utility.decrypt_message(result["client_secret"])
                result["org"] = org_data.get("name")
                idp_config.config = result
                idp_config.save()
            except DoesNotExist:
                pass
            OrgProcessor.update_org_mapping(org_data.get("name"), FeatureMappings.ONLY_SSO_LOGIN.value,
                                            org_data.get("only_sso_login"))
        except DoesNotExist:
            try:
                Organization.objects(name=org_data.get("name")).get()
                raise AppException("Name already exists")
            except DoesNotExist:
                pass
            account = [user.account] if org_data.get("account") is None else [user.account, org_data.get("account")]
            org = Organization(user=user.email,
                         account=account,
                         name=org_data.get("name"),
                         create_user=org_data.get("create_user"),
                         only_sso_login=org_data.get("only_sso_login")
                         ).save()
        org = org.to_mongo().to_dict()
        return org['_id'].__str__()

    @staticmethod
    def get_organization_for_account(account):
        try:
            org = Organization.objects(account__contains=account).get()
            data = org.to_mongo().to_dict()
            data["id"] = data.pop("_id").__str__()
            return data
        except DoesNotExist:
            logger.error("Organization not found")
            return {}

    @staticmethod
    def get_organization(org_name):
        try:
            org = Organization.objects(name=org_name).get()
            data = org.to_mongo().to_dict()
            data["id"] = data.pop("_id")
            return data
        except DoesNotExist:
            return {}

    @staticmethod
    def validate_org_settings(organization, settings):
        org = Organization.objects(name=organization).get()
        data = org.to_mongo().to_dict()
        if not data.get(settings):
            raise AppException(ORG_SETTINGS_MESSAGES.get(settings))

    @staticmethod
    def upsert_user_org_mapping(user, org, feature, value):
        try:
            org_data = UserOrgMappings.objects(user=user,
                                               organization=org,
                                               feature_type=feature,
                                               ).get()
            org_data.value = value
            org_data.save()
        except DoesNotExist:
            UserOrgMappings(
                user=user,
                organization=org,
                feature_type=feature,
                value=value
            ).save()

    @staticmethod
    def get_user_org_mapping(user, feature, org=None):
        try:
            if org is None:
                org_data = UserOrgMappings.objects(user=user, feature_type=feature).get()
            else:
                org_data = UserOrgMappings.objects(user=user, organization=org, feature_type=feature).get()

            data = org_data.to_mongo().to_dict()
            return data.get("value")
        except DoesNotExist:
            return {}

    @staticmethod
    def update_org_mapping(org, feature, value):
        try:
            org_data = UserOrgMappings.objects(organization=org, feature_type=feature).all()
            for data in org_data:
                data.value = value
                data.save()
        except DoesNotExist:
            pass

    @staticmethod
    def delete_org_mapping(org):
        try:
            count = UserOrgMappings.objects(organization=org).delete()
            logger.debug(f"{count} user org mappings deleted for orgnization")
            return count
        except Exception as ex:
            logger.error(str(ex))

    @staticmethod
    def delete_org(account, org_id, user:str = None):
        try:
            org = Organization.objects(id=org_id, account__contains=account).get()
            org_name = org.name
            Utility.delete_documents(org, user)
        except DoesNotExist:
            raise AppException("Organization not found")
        IDPProcessor.delete_idp(org_name, user=user)
        OrgProcessor.delete_org_mapping(org_id)

    @staticmethod
    def validate_sso_only(user):
        feature = FeatureMappings.ONLY_SSO_LOGIN.value
        if OrgProcessor.get_user_org_mapping(user=user, feature=feature):
            raise AppException(ORG_SETTINGS_MESSAGES.get(feature))

    @staticmethod
    def update_sso_mappings(existing_user, user, org):
        only_sso_login = OrgProcessor.get_organization(org).get(FeatureMappings.ONLY_SSO_LOGIN.value)
        if not existing_user:
            OrgProcessor.upsert_user_org_mapping(user, org, FeatureMappings.ONLY_SSO_LOGIN.value, only_sso_login)
        else:
            if OrgProcessor.get_user_org_mapping(user, FeatureMappings.ONLY_SSO_LOGIN.value, org) is None:
                OrgProcessor.upsert_user_org_mapping(user, org, FeatureMappings.ONLY_SSO_LOGIN.value, only_sso_login)
