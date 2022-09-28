from enum import Enum

KEYCLOAK_SUPPORTED_PROVIDER = {
    "saml": "SAML v2.0",
    "oidc": "OpenID Connect v1.0",
    "azure-oidc": "OpenID Connect with Azure AD",
    "keycloak-oidc": "Keycloak OpenID Connect",
}


class IDPClientNames(str, Enum):
    ACCOUNT = "account"
    REALM_MANAGEMENT = "realm-management"
    ADMIN_CLI = "admin-cli"


class IDPURLConstants(str, Enum):
    KAIRON_IDP_CALLBACK_URL = "/login/idp/callback/{realm_name}"
    AUTH_TOKEN_URL = "/realms/{realm_name}/protocol/openid-connect/token"
    ADD_REALM_URL = "/admin/realms"
    ADD_IDP_TO_REALM_URL = ADD_REALM_URL + "/{realm_name}/identity-provider/instances"
    UPDATE_IDP_TO_REALM_URL = ADD_IDP_TO_REALM_URL + "/{alias_name}"
    GET_CLIENTS_FOR_REALM_URL = ADD_REALM_URL + "/{realm_name}/clients"
    UPDATE_CLIENT_URL = GET_CLIENTS_FOR_REALM_URL + "/{realm_client_id}"
    GET_SECRET_FOR_IDP_CLIENT_URL = GET_CLIENTS_FOR_REALM_URL + "/{realm_client_id}/client-secret"
    AZURE_OIDC = "https://login.microsoftonline.com/{tenant}/v2.0/.well-known/openid-configuration"
    KEYCLOAK_OIDC = "{idp_server_url}/realms/{tenant}/.well-known/openid-configuration"
    BROWSER_AUTH_FLOW_EXECUTION_URL = ADD_REALM_URL + "/{realm_name}/authentication/flows/browser/executions"
    BROWSER_AUTH_FLOW_EXECUTION_CONFIG_URL = ADD_REALM_URL + "/{realm_name}/authentication/executions/{flow_execution_id}/config"
    SERVICE_ACCOUNT_USER_URL = GET_CLIENTS_FOR_REALM_URL + "/{realm_client_id}/service-account-user"
    ADD_ROLES_TO_SERVICE_ACCOUNT = ADD_REALM_URL + "/{realm_name}/users/{service_user_id}/role-mappings/clients/{realm_client_id}"
    AVAILABLE_ROLE_FOR_CLIENT = ADD_ROLES_TO_SERVICE_ACCOUNT + "/available"
    BROAKER_REDIRECT_URI = "/realms/{realm_name}/broker/{realm_name}/endpoint"


class IDPConfigType(str, Enum):
    KEYCLOAK_OIDC = "keycloak_oidc"
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


ADD_BROWSER_AUTH_FLOW_CONFIG_PAYLOAD = {
    "config": {
        "defaultProvider": "REALM_NAME"
    },
    "alias": "REALM_NAME"
}

ADD_IPD_CLIENT_PAYLOAD = {
    "clientId": "REALM_NAME",
    "name": "REALM_NAME",
    "adminUrl": "",
    "alwaysDisplayInConsole": False,
    "access": {
        "view": True,
        "configure": True,
        "manage": True
    },
    "attributes": {},
    "authenticationFlowBindingOverrides": {},
    "authorizationServicesEnabled": True,
    "bearerOnly": False,
    "directAccessGrantsEnabled": True,
    "enabled": True,
    "protocol": "openid-connect",
    "description": "Custom client",

    "rootUrl": "${authBaseUrl}",
    "baseUrl": "/realms/REALM_NAME/account/",
    "surrogateAuthRequired": False,
    "clientAuthenticatorType": "client-secret",
    "defaultRoles": [
        "manage-account",
        "view-profile"
    ],
    "redirectUris": [
        "REDIRECT_URI"
    ],
    "webOrigins": [],
    "notBefore": 0,
    "consentRequired": False,
    "standardFlowEnabled": True,
    "implicitFlowEnabled": False,
    "serviceAccountsEnabled": True,
    "publicClient": False,
    "frontchannelLogout": False,
    "fullScopeAllowed": False,
    "nodeReRegistrationTimeout": 0,
    "defaultClientScopes": [
        "web-origins",
        "role_list",
        "profile",
        "roles",
        "email"
    ],
    "optionalClientScopes": [
        "address",
        "phone",
        "offline_access",
        "microprofile-jwt"
    ]
}
