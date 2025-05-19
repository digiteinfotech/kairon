from blacksheep import Request
from jose import jwt, ExpiredSignatureError

from kairon import Utility
from kairon.shared.auth import Authentication
from kairon.shared.data.constant import TOKEN_TYPE



class AuthError(Exception):
    """Raised when callback auth fails (will map to HTTP 422)."""

class CallbackAuthenticator:
    @staticmethod
    async def verify(request: Request):
        SECRET_KEY = Utility.environment["security"]["secret_key"]
        ALGORITHM  = Utility.environment["security"]["algorithm"]

        vals = request.headers.get(b"authorization") or ()
        if not vals:
            raise AuthError("Missing Authorization header")

        header = vals[0].decode("utf-8", errors="ignore")
        if not header.startswith("Bearer "):
            raise AuthError("Bad Authorization header")

        token = header.split(" ", 1)[1]
        try:
            decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            claims  = Authentication.decrypt_token_claims(decoded["sub"])
            if claims.get("type") != TOKEN_TYPE.DYNAMIC.value:
                raise AuthError("Invalid token type")

        except ExpiredSignatureError:
            raise AuthError("Token expired")
        except Exception as e:
            raise AuthError(f"Token error: {e}")