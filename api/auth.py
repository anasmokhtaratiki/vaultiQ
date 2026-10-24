"""Stateless RS256 JWT issuance and validation (RFC 7519)."""
import time
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from . import config

_bearer = HTTPBearer(auto_error=False)


@lru_cache
def _key(name):
    return (config.CERTS / name).read_text()


def issue_token(claims, minutes):
    now = int(time.time())
    payload = {**claims, "iat": now, "exp": now + minutes * 60}
    return jwt.encode(payload, _key("jwt_private.pem"), algorithm="RS256")


def current_claims(creds: HTTPAuthorizationCredentials = Depends(_bearer)):
    if creds is None:
        raise HTTPException(401, "Missing bearer token")
    try:
        return jwt.decode(
            creds.credentials, _key("jwt_public.pem"), algorithms=["RS256"],
            options={"require": ["exp", "iat", "sub"]},
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(401, "Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(401, "Invalid token")


def require_borrower(claims=Depends(current_claims)):
    if claims.get("role") != "borrower" or claims.get("kyc_status") != "verified":
        raise HTTPException(403, "KYC verification required")
    return claims


def require_admin(claims=Depends(current_claims)):
    if claims.get("role") != "admin":
        raise HTTPException(403, "Admin only")
    return claims
