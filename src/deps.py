from __future__ import annotations

import base64
import hashlib
import hmac
import json
import uuid
from dataclasses import dataclass

from fastapi import Header
from fastapi.responses import JSONResponse

from src.config import settings


@dataclass(frozen=True)
class CartIdentity:
    user_id: uuid.UUID | None = None
    session_id: str | None = None

    @property
    def is_authenticated(self) -> bool:
        return self.user_id is not None


def _unauthorized(msg: str = "Authorization required") -> JSONResponse:
    return JSONResponse(status_code=401, content={"code": "UNAUTHORIZED", "message": msg})


def _b64decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode(f"{value}{padding}".encode("ascii"))


def _decode_jwt(token: str) -> dict | None:
    try:
        header_raw, payload_raw, signature_raw = token.split(".")
        header = json.loads(_b64decode(header_raw))
        if header.get("alg") != settings.jwt_algorithm:
            return None
        sig_input = f"{header_raw}.{payload_raw}".encode("ascii")
        expected = hmac.new(
            settings.jwt_secret_key.encode("utf-8"),
            sig_input,
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(expected, _b64decode(signature_raw)):
            return None
        return json.loads(_b64decode(payload_raw))
    except Exception:
        return None


def get_cart_identity(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_session_id: str | None = Header(default=None, alias="X-Session-Id"),
) -> CartIdentity:
    if authorization and authorization.startswith("Bearer "):
        token = authorization.removeprefix("Bearer ").strip()
        payload = _decode_jwt(token)
        sub = payload.get("sub") if payload else None
        if sub:
            try:
                return CartIdentity(user_id=uuid.UUID(sub))
            except ValueError:
                pass
    if x_session_id:
        return CartIdentity(session_id=x_session_id)
    return CartIdentity()


def get_jwt_user_id(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> uuid.UUID | JSONResponse:
    if not authorization or not authorization.startswith("Bearer "):
        return _unauthorized()
    token = authorization.removeprefix("Bearer ").strip()
    payload = _decode_jwt(token)
    sub = payload.get("sub") if payload else None
    if not sub:
        return _unauthorized()
    try:
        return uuid.UUID(sub)
    except ValueError:
        return _unauthorized()
