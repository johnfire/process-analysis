"""Login sessions. The browser holds a random token; the database holds only its hash."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection, Row

from web.database import sessions, users

SESSION_LIFETIME = timedelta(days=14)
PENDING_SECOND_FACTOR_LIFETIME = timedelta(minutes=10)


def create_session(
    connection: Connection,
    user_id: UUID,
    token_hash: str,
    now: datetime,
    is_mfa_verified: bool,
    ip_address: str,
) -> None:
    lifetime = SESSION_LIFETIME if is_mfa_verified else PENDING_SECOND_FACTOR_LIFETIME
    connection.execute(
        insert(sessions).values(
            user_id=user_id,
            token_hash=token_hash,
            is_mfa_verified=is_mfa_verified,
            created_at=now,
            expires_at=now + lifetime,
            ip_address=ip_address,
        )
    )


def find_live_session(connection: Connection, token_hash: str, now: datetime) -> Row | None:
    """The session joined with its user, or None when unknown or expired."""
    return connection.execute(
        select(
            sessions.c.id.label("session_id"),
            sessions.c.is_mfa_verified,
            users.c.id.label("user_id"),
            users.c.email,
            users.c.is_admin,
            users.c.is_totp_enabled,
            users.c.totp_secret,
            users.c.totp_last_step,
            users.c.password_hash,
            users.c.created_at,
        )
        .join_from(sessions, users, sessions.c.user_id == users.c.id)
        .where(sessions.c.token_hash == token_hash)
        .where(sessions.c.expires_at > now)
    ).first()


def promote_to_full_session(connection: Connection, session_id: UUID, now: datetime) -> None:
    connection.execute(
        update(sessions)
        .where(sessions.c.id == session_id)
        .values(is_mfa_verified=True, expires_at=now + SESSION_LIFETIME)
    )


def end_session(connection: Connection, token_hash: str) -> None:
    connection.execute(delete(sessions).where(sessions.c.token_hash == token_hash))


def end_all_sessions(connection: Connection, user_id: UUID, keep_session_id: UUID | None = None) -> None:
    statement = delete(sessions).where(sessions.c.user_id == user_id)
    if keep_session_id is not None:
        statement = statement.where(sessions.c.id != keep_session_id)
    connection.execute(statement)


def count_sessions(connection: Connection, user_id: UUID, now: datetime) -> int:
    rows = connection.execute(
        select(sessions.c.id).where(sessions.c.user_id == user_id).where(sessions.c.expires_at > now)
    ).all()
    return len(rows)
