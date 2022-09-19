from enum import Enum

KEYCLOAK_SUPPORTED_PROVIDER = {
    "saml": "SAML v2.0",
    "oidc": "OpenID Connect v1.0",
    "azure-oidc": "OpenID Connect with Azure AD",
    "keycloak-oidc": "Keycloak OpenID Connect",
}


class IDPURLConstants(str, Enum):
    KAIRON_IDP_CALLBACK_URL = "/login/idp/callback/{realm_name}"
    AUTH_TOKEN_URL = "/auth/realms/{realm_name}/protocol/openid-connect/token"
    ADD_REALM_URL = "/auth/admin/realms"
    ADD_IDP_TO_REALM_URL = "/auth/admin/realms/{realm_name}/identity-provider/instances"
    UPDATE_IDP_TO_REALM_URL = "/auth/admin/realms/{realm_name}/identity-provider/instances/{alias_name}"
    GET_CLIENTS_FOR_REALM_URL = "/auth/admin/realms/{realm_name}/clients"
    UPDATE_CLIENT_URL = "/auth/admin/realms/SingleTenant/clients/{realm_client_id}"
    AZURE_OIDC = "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
    KEYCLOAK_OIDC = "{idp_server_url}/auth/realms/{tenant}/.well-known/openid-configuration"


class IDPConfigType(str, Enum):
    SAML = "saml"
    KEYCLOAK_OIDC = "keycloak_oidc"
    OIDC = "oidc"
    AZURE_OIDC = "azure_oidc"


AUTH_ACCESS_TOKEN_PAYLOAD = "grant_type=password&client_id=admin-cli&username={username}&password={password}"

ADD_REALM_PAYLOAD = {
    "id": "realm_name",
    "realm": "realm_name",
    "displayName": "realm_name",
    "enabled": True,
    "sslRequired": "external",
    "registrationAllowed": False,
    "loginWithEmailAllowed": True,
    "duplicateEmailsAllowed": False,
    "resetPasswordAllowed": False,
    "editUsernameAllowed": False,
    "bruteForceProtected": True
}


class IDPPayload:
    basic_config = {
        "alias": "REALM_NAME",
        "providerId": "PROVIDER_ID",
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

    idp_provider_config = {
        "azure_oidc": {
            "userInfoUrl": "https://graph.microsoft.com/oidc/userinfo",
            "validateSignature": "true",
            "clientId": "CLIENT_ID",
            "clientSecret": "CLIENT_SECRET",
            "tokenUrl": "https://login.microsoftonline.com/TENANT/oauth2/v2.0/token",
            "jwksUrl": "https://login.microsoftonline.com/TENANT/discovery/v2.0/keys",
            "issuer": "https://login.microsoftonline.com/TENANT/v2.0",
            "useJwksUrl": "true",
            "authorizationUrl": "https://login.microsoftonline.com/TENANT/oauth2/v2.0/authorize",
            "clientAuthMethod": "client_secret_basic",
            "logoutUrl": "https://login.microsoftonline.com/TENANT/oauth2/v2.0/logout",
            "syncMode": "IMPORT"
        }
    }

    @staticmethod
    def get_idp_config(idp_provider):
        basic_config = IDPPayload.basic_config
        basic_config["config"] = IDPPayload.idp_provider_config[idp_provider]
        return basic_config
