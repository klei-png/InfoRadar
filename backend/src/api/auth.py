import hashlib
import os
import secrets
import time

import jwt
from dotenv import load_dotenv
from fastapi import Depends, HTTPException
from fastapi.security import HTTPBearer,HTTPAuthorizationCredentials

load_dotenv()

AUTH_SECRET = os.environ.get("AUTH_SECRET","")
AUTH_PASSWORD = os.environ.get("AUTH_PASSWORD","")   # 仅用于首次引导默认用户，之后密码以 users 表为准
TOKEN_TTL = 7*24*3600
_PBKDF2_ROUNDS = 200_000

_security = HTTPBearer(auto_error=False)

def auth_enabled() -> bool:
    return bool(AUTH_SECRET)

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                 salt.encode(), _PBKDF2_ROUNDS)
    return f"pbkdf2${salt}${digest.hex()}"

def verify_password(password: str, stored: str) -> bool:
    try:
        _, salt, expected = stored.split("$")
        digest = hashlib.pbkdf2_hmac("sha256", password.encode(),
                                     salt.encode(), _PBKDF2_ROUNDS)
        return secrets.compare_digest(digest.hex(), expected)
    except ValueError:
        return False

def create_token(username: str) -> str:
    return jwt.encode({"sub": username, "exp": int(time.time()) + TOKEN_TTL},
                      AUTH_SECRET, algorithm="HS256")

def require_auth(
        cred: HTTPAuthorizationCredentials | None = Depends(_security),
) -> None:
    if not auth_enabled():
        return
    if cred is None:
        raise HTTPException(401,"未登录")
    try:
        jwt.decode(cred.credentials,AUTH_SECRET,algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401,"登录已过期，请重新登录")
