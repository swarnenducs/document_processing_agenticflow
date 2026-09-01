"""Issue and verify admin access tokens with PyJWT (HS256)."""

from __future__ import annotations

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt

from ip_api.core.settings import Settings

ALGORITHM = "HS256"
ISSUER = "ipp_agentic_api"
AUDIENCE = "ipp-admin"
TOKEN_TYP = "admin_access"

_fallback_secret: str | None = None


def reset_jwt_fallback_secret() -> None:
    """Drop the process-local signing secret (tests / reload_settings)."""
    global _fallback_secret
    _fallback_secret = None


def signing_secret(cfg: Settings) -> str:
    """Prefer ADMIN_JWT_SECRET, then ADMIN_API_KEY, then a process-local secret."""
    for raw in (cfg.admin_jwt_secret, cfg.admin_api_key):
        secret = (raw or "").strip()
        if secret:
            return secret
    global _fallback_secret
    if _fallback_secret is None:
        _fallback_secret = secrets.token_urlsafe(48)
    return _fallback_secret


def issue_admin_jwt(
    cfg: Settings,
    *,
    ttl_seconds: int | None = None,
) -> tuple[str, int, str]:
    """Return (token, expires_in, expires_at ISO-8601 UTC)."""
    ttl = cfg.admin_token_ttl_seconds if ttl_seconds is None else int(ttl_seconds)
    ttl = max(60, min(ttl, 7 * 24 * 3600))
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl)
    payload: dict[str, Any] = {
        "iss": ISSUER,
        "aud": AUDIENCE,
        "sub": "admin",
        "typ": TOKEN_TYP,
        "iat": int(now.timestamp()),
        "nbf": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "jti": secrets.token_urlsafe(16),
    }
    token = jwt.encode(payload, signing_secret(cfg), algorithm=ALGORITHM)
    if isinstance(token, bytes):
        token = token.decode("ascii")
    return token, ttl, expires_at.replace(microsecond=0).isoformat().replace("+00:00", "Z")


def jwt_is_valid(token: str, cfg: Settings) -> bool:
    raw = (token or "").strip()
    if raw.count(".") != 2:
        return False
    try:
        claims = jwt.decode(
            raw,
            signing_secret(cfg),
            algorithms=[ALGORITHM],
            audience=AUDIENCE,
            issuer=ISSUER,
        )
    except jwt.PyJWTError:
        return False
    return claims.get("typ") == TOKEN_TYP and claims.get("sub") == "admin"
