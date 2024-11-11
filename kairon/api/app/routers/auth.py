from fastapi import APIRouter, Security, Path
from fastapi import Depends
from starlette.background import BackgroundTasks
from starlette.requests import Request

from kairon.idp.processor import IDPProcessor
from kairon.shared.account.activity_log import UserActivityLogger
from kairon.shared.data.utils import DataUtility
from kairon.shared.organization.processor import OrgProcessor
from kairon.shared.utils import Utility, MailUtility
from kairon.shared.auth import Authentication
from kairon.api.models import Response, IntegrationRequest, RecaptchaVerifiedOAuth2PasswordRequestForm
from kairon.shared.authorization.processor import IntegrationProcessor
from kairon.shared.constants import ADMIN_ACCESS, TESTER_ACCESS, UserActivityType
from kairon.shared.data.constant import ACCESS_ROLES, TOKEN_TYPE
from kairon.shared.models import User

router = APIRouter()


@router.post("/login", response_model=Response)
async def login_for_access_token(
        background_tasks: BackgroundTasks, request: Request,
        form_data: RecaptchaVerifiedOAuth2PasswordRequestForm = Depends()
):
    """
    Authenticates the user and generates jwt token
    """
    OrgProcessor.validate_sso_only(form_data.username)

    Utility.validate_enable_sso_only()
    access_tkn, access_tkn_exp, refresh_tkn, refresh_tkn_exp = Authentication.authenticate(form_data.username, form_data.password)
    background_tasks.add_task(
        Authentication.validate_trusted_device, form_data.username, form_data.fingerprint, request
    )
    return {
        "data": {
            "access_token": access_tkn, "access_token_expiry": access_tkn_exp, "token_type": "bearer",
            "refresh_token": refresh_tkn, "refresh_token_expiry": refresh_tkn_exp
        }, "message": "User Authenticated",
    }


@router.get("/{bot}/token/refresh", response_model=Response)
async def refresh_token(
        token: str = Depends(DataUtility.oauth2_scheme),
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=TESTER_ACCESS)
):
    """
    Generates an access token from refresh token supplied.
    """
    access_token, new_refresh_token = Authentication.generate_token_from_refresh_token(token)
    return {
        "data": {"access_token": access_token, "token_type": "bearer", "refresh_token": new_refresh_token},
        "message":
            "This token will be shown only once. Please copy this somewhere safe."
            "It is your responsibility to keep the token secret. If leaked, others may have access to your system."
    }


@router.get("/token/refresh", response_model=Response)
async def refresh_login_token(
        token: str = Depends(DataUtility.oauth2_scheme),
        current_user: User = Security(Authentication.get_current_user)
):
    """
    Generates an access token from refresh token supplied.
    """
    access_tkn, access_tkn_exp, refresh_tkn, refresh_tkn_exp = Authentication.generate_login_token_from_refresh_token(token, current_user.dict())
    return {
        "data": {"access_token": access_tkn, "access_token_expiry": access_tkn_exp,
                 "token_type": "bearer", "refresh_token": refresh_tkn,
                 "refresh_token_expiry": refresh_tkn_exp},
        "message":
            "This token will be shown only once. Please copy this somewhere safe."
            "It is your responsibility to keep the token secret. If leaked, others may have access to your system."
    }


@router.get("/{bot}/integration/token/temp", response_model=Response)
async def generate_limited_access_temporary_token(
        expiry_minutes: int = 5, access_list: list = None,
        current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS),
):
    """
    Generates a limited access temporary token with Tester role.
    """
    access_list = access_list or ['/api/bot/.+/chat/client/config$']
    access_token, _ = Authentication.generate_integration_token(
        current_user.get_bot(), current_user.email, ACCESS_ROLES.TESTER.value, expiry=expiry_minutes,
        access_limit=access_list, token_type=TOKEN_TYPE.DYNAMIC.value
    )
    return {
        "data": {"access_token": access_token, "token_type": "bearer"},
        "message":
            "This token will be shown only once. Please copy this somewhere safe."
            "It is your responsibility to keep the token secret. If leaked, others may have access to your system."
    }


@router.post("/{bot}/integration/token", response_model=Response)
async def generate_integration_token(
    request: IntegrationRequest,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS),
):
    """
    Generates an access token for api integration.
    """
    access_token, _ = Authentication.generate_integration_token(
        current_user.get_bot(), current_user.get_user(), expiry=request.expiry_minutes, name=request.name,
        access_limit=request.access_list, role=request.role
    )
    return {
        "data": {"access_token": access_token, "token_type": "bearer"},
        "message":
            """This token will be shown only once. Please copy this somewhere safe. 
            It is your responsibility to keep the token secret. If leaked, others may have access to your system."""
    }


@router.put("/{bot}/integration/token", response_model=Response)
async def update_integration_token(
    request: IntegrationRequest,
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS),
):
    """
    Enable/disable/delete an integration.
    """
    Authentication.update_integration_token(
        request.name, current_user.get_bot(), current_user.get_user(), int_status=request.status
    )
    return {"message": "Integration status updated!"}


@router.get("/{bot}/integration/token/list", response_model=Response)
async def get_integrations(
    current_user: User = Security(Authentication.get_current_user_and_bot, scopes=ADMIN_ACCESS),
):
    """
    List available integrations.
    """
    return Response(data=list(IntegrationProcessor.get_integrations(current_user.get_bot())))


@router.get('/login/sso/{sso_type}')
async def sso_login(sso_type: str = Path(description="social media type", examples=["google"])):
    """
    Generate redirect url based on social media type.
    """
    return await Authentication.get_redirect_url(sso_type)


@router.get("/login/sso/callback/{sso_type}", response_model=Response)
async def sso_callback(
        request: Request,
        background_tasks: BackgroundTasks,
        sso_type: str = Path(description="social media type", examples=["google"])
):
    """
    Generate login token after successful social media login.
    """
    existing_user, user_details, access_token = await Authentication.verify_and_process(request, sso_type)
    if not existing_user and Utility.email_conf["email"]["enable"]:
        background_tasks.add_task(
            MailUtility.format_and_send_mail, mail_type='password_generated', email=user_details['email'],
            first_name=user_details['first_name'], password=user_details['password'].get_secret_value()
        )
    UserActivityLogger.add_log(a_type=UserActivityType.sso_login.value, email=user_details['email'],
                               data={"username": user_details['email'], "sso_type": sso_type})
    return {
        "data": {"access_token": access_token, "token_type": "bearer"},
        "message": """It is your responsibility to keep the token secret.
        If leaked then other may have access to your system.""",
    }


@router.post("/logout", response_model=Response)
async def logout(
        current_user: User = Depends(Authentication.get_current_user)
):
    """
    Invalidate user session and revoke authentication token upon successful logout.
    """
    UserActivityLogger.add_log(a_type=UserActivityType.logout.value, account=current_user.account,
                               email=current_user.email, data={"username": current_user.email})
    return Response(message="User Logged out!")


@router.get('/login/idp/{realm_name}')
async def idp_login(
        realm_name: str = Path(description="Domain name for your company", examples=["KAIRON"])):
    """
    Fetch redirect url for idp realm.
    """
    return IDPProcessor.get_redirect_uri(realm_name)


@router.get('/login/idp/callback/{realm_name}', response_model=Response)
async def idp_callback(session_state: str, code: str,
                       realm_name: str = Path(description="Realm name",
                                              examples=["KAIRON"]),
                       ):
    """
    Identify user and create access token for user
    """
    existing_user, user_details, access_token = await IDPProcessor.identify_user_and_create_access_token(realm_name,
                                                                                                         session_state,
                                                                                                         code)
    OrgProcessor.update_sso_mappings(existing_user,user_details.get("email"), realm_name)
    return Response(data={"access_token": access_token, "token_type": "bearer"}, message="User Authenticated")
