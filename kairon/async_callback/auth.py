from blacksheep import Request, json
from jose import jwt, ExpiredSignatureError

from kairon import Utility
from kairon.shared.auth import Authentication
from kairon.shared.data.constant import TOKEN_TYPE


class CallbackAuthenticator:
    @staticmethod
    async def verify(request: Request):
        SECRET_KEY = Utility.environment["security"]["secret_key"]
        ALGORITHM  = Utility.environment["security"]["algorithm"]
        auth_header = request.headers.get(b"authorization") or ""
        if not auth_header:
            return json({"success": False, "error": "Missing Authorization header"}, status=401)

        token_str = auth_header[0].decode("utf-8", errors="ignore")
        if not token_str.startswith("Bearer "):
            return json({"success": False, "error": "Bad Authorization header"}, status=401)
        token = token_str.split(" ", 1)[1]

        try:
            decoded = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            claims = Authentication.decrypt_token_claims(decoded["sub"])
            if claims.get("type") != TOKEN_TYPE.DYNAMIC.value:
                return json({"success": False, "error": "Invalid token type"}, status=401)
        except ExpiredSignatureError:
            return json({"success": False, "error": "Token expired"}, status=401)
        except Exception as e:
            return json({"success": False, "error": f"Token error: {e}"}, status=401)

        return None