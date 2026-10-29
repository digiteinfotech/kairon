"""
Authentication for the CRM routes: a normal Kairon login (bot membership, as before) **or** a Kairon Metering staff token.

Metering staff sign in to the Admin console, which already holds that token. Accepting it here lets Admin manage CRM for any
bot without asking staff for each bot owner's Kairon login. It is deliberately narrow:
- only the `/crm/...` routes use this dependency; every other Kairon route still requires a Kairon login;
- verification is off unless `crm.staff_auth.jwt_secret` (env CRM_STAFF_JWT_SECRET, the same value as Metering's
  METERING_JWT_SECRET) is set, and then the staff email **must** be listed in `crm.staff_allowlist` (CRM_STAFF_ALLOWLIST).
  An empty allowlist rejects every staff token (fail closed);
- the algorithm is pinned, `exp`, `iat`, `aud` and `sub` are required, and the token type must be Metering's staff type;
- every staff action is logged with the staff identity and bot, never the token.
"""
from typing import Optional, Text

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import SecurityScopes
from loguru import logger

from kairon.shared.account.processor import AccountProcessor
from kairon.shared.auth import Authentication
from kairon.shared.data.utils import DataUtility
from kairon.shared.models import User
from kairon.shared.utils import Utility

STAFF_TOKEN_TYPE = "metering-staff"  # nosec B105 - JWT "typ" claim value, not a credential
STAFF_AUDIENCE = "kairon-metering"


def _staff_config() -> dict:
    return (Utility.environment.get("crm") or {}).get("staff_auth") or {}


def staff_allowlist() -> list:
    raw = (Utility.environment.get("crm") or {}).get("staff_allowlist")
    return [e.strip().lower() for e in str(raw or "").split(",") if e.strip()]


def is_listed(email: Text) -> bool:
    email = (email or "").strip().lower()
    return any((entry.startswith("@") and email.endswith(entry)) or email == entry for entry in staff_allowlist())


def verify_staff_token(token: Optional[Text]) -> Optional[Text]:
    """Returns the staff email for a valid Metering staff token, None when `token` is not one (so the normal path runs)."""
    secret = _staff_config().get("jwt_secret")
    if not secret or not token:
        return None
    try:
        claims = jwt.decode(token, secret, algorithms=["HS256"], audience=STAFF_AUDIENCE,
                            options={"require": ["exp", "iat", "aud", "sub"]})
    except jwt.PyJWTError:
        return None
    if claims.get("type") != STAFF_TOKEN_TYPE or not claims.get("sub"):
        return None
    return str(claims["sub"]).strip().lower()


async def get_crm_user_and_bot(security_scopes: SecurityScopes, request: Request,
                               token: str = Depends(DataUtility.oauth2_scheme)) -> User:
    staff_email = verify_staff_token(token)
    if staff_email is None:
        return await Authentication.get_current_user_and_bot(security_scopes, request, token)
    if not is_listed(staff_email):
        logger.warning("[CRMStaff] rejected staff token: identity is not in CRM_STAFF_ALLOWLIST")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED,
                            detail="Staff access to CRM is not enabled for this account.")
    bot_id = request.path_params.get("bot")
    if Utility.check_empty_string(bot_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Bot is required")
    bot_info = AccountProcessor.get_bot_and_validate_status(bot_id)
    logger.info(f"[CRMStaff] staff={staff_email} bot={bot_id} {request.method} {request.url.path}")
    return User(email=staff_email, first_name="Kairon", last_name="Staff", active_bot=bot_id,
                bot_account=bot_info["account"], account=bot_info["account"], status=True, role="admin")
