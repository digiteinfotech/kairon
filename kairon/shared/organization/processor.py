from mongoengine import DoesNotExist

from kairon import Utility
from kairon.exceptions import AppException
from kairon.idp.data_objects import IdpConfig
from kairon.idp.processor import IDPProcessor
from kairon.shared.account.data_objects import Organization
from kairon.shared.data.constant import FeatureMappings
from kairon.shared.data.data_objects import UserOrgMappings
from kairon.shared.data.constant import ORG_SETTINGS_MESSAGES


class OrgProcessor:

    @staticmethod
    def upsert_organization(user, org_data):
        try:
            org = Organization.objects(account__contains=user.account).get()
            org.name = org_data.get("name")
            org.create_user = org_data.get("create_user")
            org.sso_login = org_data.get("sso_login")
            org.account = org_data.get("account") if org_data.get("account") is not None else org.account
            org.save()
            try:
                idp_config = IdpConfig.objects(account__contains=user.account, organization=org_data.get("name")).get()
                idp_config.organization = org_data.get("name")
                result = idp_config.config("config")
                result["client_id"] = Utility.decrypt_message(result["client_id"])
                result["client_secret"] = Utility.decrypt_message(result["client_secret"])
                result["org"] = org_data.get("name")
                idp_config.config = result
                idp_config.save()
            except DoesNotExist:
                pass
            OrgProcessor.update_org_mapping(org_data.get("name"), FeatureMappings.SSO_LOGIN.value,
                                            str(org_data.get("sso_login")))
        except DoesNotExist:
            try:
                Organization.objects(name=org_data.get("name")).get()
                raise AppException("Name already exists")
            except DoesNotExist:
                pass
            account = [user.account] if org_data.get("account") is None else [user.account, org_data.get("account")]
            Organization(user=user.email,
                         account=account,
                         name=org_data.get("name"),
                         create_user=org_data.get("create_user"),
                         sso_login=org_data.get("sso_login")
                         ).save()

    @staticmethod
    def get_organization_for_account(account):
        try:
            org = Organization.objects(account__contains=account).get()
            data = org.to_mongo().to_dict()
            data.pop("_id")
            return data
        except DoesNotExist:
            return {}

    @staticmethod
    def get_organization(org_name):
        try:
            org = Organization.objects(name=org_name).get()
            data = org.to_mongo().to_dict()
            data.pop("_id")
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
                org_data = UserOrgMappings.objects(user=user,
                                                   feature_type=feature,
                                                   ).get()
            else:
                org_data = UserOrgMappings.objects(user=user,
                                                   organization=org,
                                                   feature_type=feature,
                                                   ).get()

            data = org_data.to_mongo().to_dict()
            return data.get("value")
        except DoesNotExist:
            return {}

    @staticmethod
    def update_org_mapping(org, feature, value):
        try:
            org_data = UserOrgMappings.objects(organization=org,
                                               feature_type=feature,
                                               ).all()
            for data in org_data:
                data.value = value
                data.save()
        except DoesNotExist:
            pass

    @staticmethod
    def delete_org(account, org_name):
        try:
            org = Organization.objects(name=org_name, account__contains=account).get()
            org.delete()
        except DoesNotExist:
            raise AppException("Organization not found")
        IDPProcessor.delete_idp(org_name)
