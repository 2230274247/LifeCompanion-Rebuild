from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
import math
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
    except (ValueError, TypeError, UnicodeError) as exc:
        raise AuthError("INVALID_TOKEN") from exc
    if not isinstance(header, dict) or not isinstance(payload, dict):
        raise AuthError("INVALID_TOKEN")
    if header.get("alg") != "HS256":
        raise AuthError("UNSUPPORTED_TOKEN_ALGORITHM")
    expected = hmac.new(
        secret.encode(),
        f"{header_part}.{payload_part}".encode(),
        hashlib.sha256,
    ).digest()
    try:
        signature = _b64decode(signature_part)
    except ValueError as exc:
        raise AuthError("INVALID_TOKEN_SIGNATURE") from exc
    if not hmac.compare_digest(expected, signature):
        raise AuthError("INVALID_TOKEN_SIGNATURE")
    if not isinstance(payload.get("id"), str):
        raise AuthError("TOKEN_MISSING_USER_ID")
    expires = payload.get("exp")
    if isinstance(expires, bool) or not isinstance(expires, (int, float)) or not math.isfinite(expires):
        raise AuthError("TOKEN_MISSING_EXPIRY")
    if expires <= time.time():
        raise AuthError("TOKEN_EXPIRED")
    return payload


def bearer_token(request: Request) -> str | None:
    value = request.headers.get("authorization", "")
    if value.lower().startswith("bearer "):
        return value[7:].strip()
    return None


def verified_claims_from_request(request: Request) -> dict[str, Any]:
    token = bearer_token(request)
    if not token:
        raise HTTPException(status_code=401, detail={"code": "AUTH_REQUIRED"})
    settings = request.app.state.settings
    try:
        payload = verify_hs256(token, settings.jwt_secret)
    except AuthError as exc:
        raise HTTPException(
            status_code=401, detail={"code": "INVALID_AUTH_TOKEN", "reason": str(exc)}
        ) from exc
    return payload


def identity_from_request(request: Request) -> tuple[str, str]:
    payload = verified_claims_from_request(request)
    return payload["id"], "bearer"

