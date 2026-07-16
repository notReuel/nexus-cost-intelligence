"""
Authentication & authorization — the C-1 fix.

No endpoint mutates shared data without an authenticated principal, a tenant
scope, and a sufficient role. Password hashing uses stdlib scrypt (no fragile
native deps); sessions are stateless signed JWTs.
"""
import os
import hmac
import hashlib
import base64
import secrets
from datetime import datetime, timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session, select

from .db import get_session
from .models import User, Tenant, Role

# In production set JWT_SECRET via env. Falling back to a random per-boot
# secret is only safe for a single-process demo: with more than one worker
# process (e.g. `uvicorn --workers 4`, or any horizontally-scaled deploy),
# each process would mint its OWN random secret, so a token issued by one
# worker is silently rejected as invalid by the others — this manifests as
# intermittent, hard-to-diagnose 401s that correlate with load-balancer
# routing, not with anything the user did. Warn loudly so this can't be missed.
import logging
_log = logging.getLogger("nexus.auth")
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    _log.warning(
        "JWT_SECRET not set — using a random per-process secret. This BREAKS "
        "authentication the moment more than one worker process is running "
        "(uvicorn --workers >1, multiple dynos/instances, or any restart). "
        "Set JWT_SECRET explicitly before running with more than one process."
    )
JWT_ALG = "HS256"
TOKEN_TTL_HOURS = int(os.getenv("TOKEN_TTL_HOURS", "12"))

oauth2 = OAuth2PasswordBearer(tokenUrl="/api/auth/login", auto_error=False)


# ─── Password hashing (scrypt) ───────────────────────────────────────────
def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("Password must be at least 8 characters")
    salt = secrets.token_bytes(16)
    dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return f"{base64.b64encode(salt).decode()}${base64.b64encode(dk).decode()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt_b64, hash_b64 = stored.split("$", 1)
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(hash_b64)
        dk = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk, expected)   # constant-time
    except Exception:
        return False


# ─── Tokens ──────────────────────────────────────────────────────────────
def issue_token(user: User) -> str:
    now = datetime.utcnow()
    payload = {
        "sub": str(user.id), "tid": user.tenant_id, "role": user.role.value,
        "iat": now, "exp": now + timedelta(hours=TOKEN_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


def _decode(token: str) -> dict:
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


# ─── Dependencies ────────────────────────────────────────────────────────
def current_user(token: Optional[str] = Depends(oauth2),
                 session: Session = Depends(get_session)) -> User:
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required",
                            headers={"WWW-Authenticate": "Bearer"})
    data = _decode(token)
    user = session.get(User, int(data["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


_ORDER = {Role.VIEWER: 0, Role.ESTIMATOR: 1, Role.APPROVER: 2, Role.ADMIN: 3}

def require_role(minimum: Role):
    """Guard factory: reject principals below `minimum`."""
    def _guard(user: User = Depends(current_user)) -> User:
        if _ORDER[user.role] < _ORDER[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                f"Requires {minimum.value} role or higher")
        return user
    return _guard


def tenant_scope(user: User = Depends(current_user)) -> int:
    """The only tenant a request may read/write. Cross-tenant access is
    impossible because every query filters on this — the IDOR / cross-tenant
    fix from the audit."""
    return user.tenant_id


def optional_current_user(token: Optional[str] = Depends(oauth2),
                          session: Session = Depends(get_session)) -> Optional[User]:
    """For the estimating endpoints (Project Model, Budget, Ranking), which
    are public by design but must show a richer, tenant-blended view to a
    logged-in user. Unlike current_user, a missing or invalid token is NOT
    an error here — it just means 'anonymous, reference-library-only'. A
    present-but-invalid token IS still rejected, so a stale/tampered token
    can't silently degrade to a different tenant's view."""
    if not token:
        return None
    data = _decode(token)  # raises 401 if the token is malformed/expired
    user = session.get(User, int(data["sub"]))
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user
