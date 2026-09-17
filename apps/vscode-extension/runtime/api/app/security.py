from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Header, HTTPException, Request, status
from sqlalchemy import select

from .config import get_settings
from .database import SessionLocal
from .models import AuthSession, User


SESSION_COOKIE = "cph_session"
PBKDF2_ITERATIONS = 600_000


@dataclass(frozen=True)
class Principal:
    user_id: str
    role: str
    display_name: str


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    actual_salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), actual_salt, PBKDF2_ITERATIONS)
    return "pbkdf2_sha256${}${}${}".format(
        PBKDF2_ITERATIONS,
        base64.urlsafe_b64encode(actual_salt).decode(),
        base64.urlsafe_b64encode(digest).decode(),
    )


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        algorithm, iterations, salt_text, digest_text = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = base64.urlsafe_b64decode(salt_text)
        expected = base64.urlsafe_b64decode(digest_text)
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def create_login_session(user: User) -> tuple[AuthSession, str]:
    raw_token = secrets.token_urlsafe(48)
    auth_session = AuthSession(
        user_id=user.id,
        token_hash=token_hash(raw_token),
        expires_at=datetime.now(UTC) + timedelta(hours=8),
    )
    return auth_session, raw_token


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def get_principal(
    request: Request,
    x_cph_user: str | None = Header(default=None),
) -> Principal:
    settings = get_settings()
    with SessionLocal() as session:
        user: User | None = None
        raw_token = request.cookies.get(SESSION_COOKIE)
        if raw_token:
            auth_session = session.scalar(
                select(AuthSession).where(
                    AuthSession.token_hash == token_hash(raw_token),
                    AuthSession.revoked_at.is_(None),
                )
            )
            if auth_session and _as_utc(auth_session.expires_at) > datetime.now(UTC):
                user = session.get(User, auth_session.user_id)
                auth_session.last_seen_at = datetime.now(UTC)
                session.commit()
        if user is None and settings.demo_mode and x_cph_user:
            user = session.scalar(select(User).where(User.id == x_cph_user, User.active.is_(True)))
        if user is None and settings.demo_mode:
            user = session.scalar(
                select(User).where(User.active.is_(True)).order_by(User.created_at)
            )
        if user is None or not user.active:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        return Principal(user_id=user.id, role=user.role, display_name=user.display_name)


def ensure_role(principal: Principal, *roles: str) -> None:
    if principal.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")
