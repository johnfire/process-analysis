"""Invite links and password-reset links: single use, time limited, stored only as hashes."""

from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection, Row

from web.database import invites, password_resets

INVITE_LIFETIME = timedelta(days=7)
RESET_LIFETIME = timedelta(minutes=30)


def create_invite(
    connection: Connection, email: str, token_hash: str, invited_by: UUID | None, now: datetime
) -> None:
    connection.execute(
        insert(invites).values(
            email=email.strip().lower(),
            token_hash=token_hash,
            invited_by=invited_by,
            created_at=now,
            expires_at=now + INVITE_LIFETIME,
        )
    )


def find_open_invite(connection: Connection, token_hash: str, now: datetime) -> Row | None:
    return connection.execute(
        select(invites)
        .where(invites.c.token_hash == token_hash)
        .where(invites.c.accepted_at.is_(None))
        .where(invites.c.expires_at > now)
    ).first()


def claim_invite(connection: Connection, invite_id: UUID, now: datetime) -> bool:
    """Mark an invite used; False when a concurrent request got there first."""
    claimed = connection.execute(
        update(invites)
        .where(invites.c.id == invite_id)
        .where(invites.c.accepted_at.is_(None))
        .values(accepted_at=now)
    )
    return claimed.rowcount == 1


def list_invites(connection: Connection) -> list[Row]:
    return list(connection.execute(select(invites).order_by(invites.c.created_at.desc()).limit(100)))


def create_reset(connection: Connection, user_id: UUID, token_hash: str, now: datetime) -> None:
    connection.execute(
        insert(password_resets).values(
            user_id=user_id, token_hash=token_hash, created_at=now, expires_at=now + RESET_LIFETIME
        )
    )


def find_open_reset(connection: Connection, token_hash: str, now: datetime) -> Row | None:
    return connection.execute(
        select(password_resets)
        .where(password_resets.c.token_hash == token_hash)
        .where(password_resets.c.used_at.is_(None))
        .where(password_resets.c.expires_at > now)
    ).first()


def claim_reset(connection: Connection, reset_id: UUID, now: datetime) -> bool:
    claimed = connection.execute(
        update(password_resets)
        .where(password_resets.c.id == reset_id)
        .where(password_resets.c.used_at.is_(None))
        .values(used_at=now)
    )
    return claimed.rowcount == 1


def void_open_resets(connection: Connection, user_id: UUID, now: datetime) -> None:
    """A newer request replaces older ones, so only the latest emailed link works."""
    connection.execute(
        update(password_resets)
        .where(password_resets.c.user_id == user_id)
        .where(password_resets.c.used_at.is_(None))
        .values(used_at=now)
    )


def has_recent_reset(connection: Connection, user_id: UUID, now: datetime, within_seconds: int) -> bool:
    """True when a reset was already issued moments ago, so repeated requests cannot flood an inbox."""
    since = now - timedelta(seconds=within_seconds)
    return (
        connection.execute(
            select(password_resets.c.id)
            .where(password_resets.c.user_id == user_id)
            .where(password_resets.c.created_at >= since)
        ).first()
        is not None
    )
