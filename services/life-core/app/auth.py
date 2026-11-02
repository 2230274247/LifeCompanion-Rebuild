from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from typing import Any

from fastapi import HTTPException, Request


class AuthError(ValueError):
    pass


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def verify_hs256(token: str, secret: str) -> dict[str, Any]:
    if not secret:
        raise AuthError("AUTH_SECRET_NOT_CONFIGURED")
    try:
        header_part, payload_part, signature_part = token.split(".")
        header = json.loads(_b64decode(header_part))
        payload = json.loads(_b64decode(payload_part))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("INVALID_TOKEN") from exc
    if header.get("alg") != "HS256":
        raise AuthError("UNSUPPORTED_TOKEN_ALGORITHM")
    expected = hmac.new(
        secret.encode(),
        f"{header_part}.{payload_part}".encode(),
        hashlib.sha256,
    ).digest()
    if not hmac.compare_digest(expected, _b64decode(signature_part)):
        raise AuthError("INVALID_TOKEN_SIGNATURE")
    if not isinstance(payload.get("id"), str):
        raise AuthError("TOKEN_MISSING_USER_ID")
    if isinstance(payload.get("exp"), (int, float)) and payload["exp"] <= time.time():
        raise AuthError("TOKEN_EXPIRED")
    return payload


def bearer_token(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return request.cookies.get("refreshToken")


def identity_from_request(request: Request) -> tuple[str, str]:
    token = bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})
    settings = request.app.state.settings
    is_bearer = request.headers.get("authorization", "").lower().startswith("bearer ")
    secret = settings.jwt_secret if is_bearer else settings.jwt_refresh_secret
    try:
        payload = verify_hs256(token, secret)
    except AuthError as exc:
        raise HTTPException(
            status_code=401, detail={"code": "INVALID_AUTH_TOKEN", "reason": str(exc)}
        ) from exc
    return payload["id"], "bearer" if is_bearer else "refresh_cookie"

