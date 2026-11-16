import os
import time

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials

load_dotenv()

AUTH_SECRET = os.environ.get("AUTH_SECRET","")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD","")
TOKEN_TTL = 7*24*3600

_security = HTTPBearer(auto_error=False)

def auth_enabled() -> bool:
    return bool(AUTH_SECRET and AUTH_PASSWORD)

def create_token() -> bool:
    return jwt.encode({"exp":int(time.time()) + TOKEN_TTL},
                      AUTH_SECRET,algorithm="HS256")

def require_auth(
        cred: HTTPAuthorizationCredentials | None = Depends(_security),
) -> None:
    if not auth_enabled():
        return
    if cred is None:
        raise HTTPException(401,"未登录")
    try:
        jwt.decode(cred.credentials,AUTH_SECRET,algorithms=["HS256"])
    except jwt.PyJWKError:
        raise HTTPException(401,"登录已过期，请重新登录")
    