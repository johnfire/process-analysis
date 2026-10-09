"""Reads and writes on the users table."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, insert, select, update
from sqlalchemy.engine import Connection, Row
from sqlalchemy.exc import IntegrityError

from web.database import users


def find_user_by_email(connection: Connection, email: str) -> Row | None:
    return connection.execute(select(users).where(users.c.email == email.strip().lower())).first()


def find_user(connection: Connection, user_id: UUID) -> Row | None:
    return connection.execute(select(users).where(users.c.id == user_id)).first()


def create_user(
    connection: Connection, email: str, password_hash: str, is_admin: bool = False
) -> UUID | None:
    """The new user's id, or None when that email already has an account."""
    try:
        with connection.begin_nested():
            return connection.execute(
                insert(users)
                .values(email=email.strip().lower(), password_hash=password_hash, is_admin=is_admin)
                .returning(users.c.id)
            ).scalar_one()
    except IntegrityError:
        return None


def change_password(connection: Connection, user_id: UUID, password_hash: str, now: datetime) -> None:
    connection.execute(
        update(users)
        .where(users.c.id == user_id)
        .values(password_hash=password_hash, password_changed_at=now)
    )


def replace_password_hash(connection: Connection, user_id: UUID, password_hash: str) -> None:
    """Upgrade a hash to current parameters without counting as a password change."""
    connection.execute(update(users).where(users.c.id == user_id).values(password_hash=password_hash))


def store_pending_totp_secret(connection: Connection, user_id: UUID, secret: str) -> None:
    connection.execute(
        update(users)
        .where(users.c.id == user_id)
        .values(totp_secret=secret, is_totp_enabled=False, totp_last_step=None)
    )


def enable_totp(connection: Connection, user_id: UUID, accepted_step: int) -> None:
    connection.execute(
        update(users).where(users.c.id == user_id).values(is_totp_enabled=True, totp_last_step=accepted_step)
    )


def disable_totp(connection: Connection, user_id: UUID) -> None:
    connection.execute(
        update(users)
        .where(users.c.id == user_id)
        .values(totp_secret=None, is_totp_enabled=False, totp_last_step=None)
    )


def claim_totp_step(connection: Connection, user_id: UUID, step: int) -> bool:
    """Record a used time step; False when another request already used this step or a later one."""
    claimed = connection.execute(
        update(users)
        .where(users.c.id == user_id)
        .where((users.c.totp_last_step.is_(None)) | (users.c.totp_last_step < step))
        .values(totp_last_step=step)
    )
    return claimed.rowcount == 1


def delete_user(connection: Connection, user_id: UUID) -> None:
    connection.execute(delete(users).where(users.c.id == user_id))


def export_profile(user: Row) -> dict[str, Any]:
    """The user's own record without secrets, for the data export."""
    return {
        "id": str(user.id),
        "email": user.email,
        "is_admin": user.is_admin,
        "two_factor_enabled": user.is_totp_enabled,
        "created_at": user.created_at.isoformat(),
        "password_changed_at": user.password_changed_at.isoformat(),
    }
