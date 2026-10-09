"""One-time recovery codes for users who lose their authenticator."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, func, insert, select, update
from sqlalchemy.engine import Connection

from web.database import recovery_codes


def replace_recovery_codes(connection: Connection, user_id: UUID, code_hashes: list[str]) -> None:
    connection.execute(delete(recovery_codes).where(recovery_codes.c.user_id == user_id))
    connection.execute(insert(recovery_codes), [{"user_id": user_id, "code_hash": h} for h in code_hashes])


def delete_recovery_codes(connection: Connection, user_id: UUID) -> None:
    connection.execute(delete(recovery_codes).where(recovery_codes.c.user_id == user_id))


def use_recovery_code(connection: Connection, user_id: UUID, code_hash: str, now: datetime) -> bool:
    """Spend a code; False when it is wrong or already spent (the UPDATE is the single-use guard)."""
    spent = connection.execute(
        update(recovery_codes)
        .where(recovery_codes.c.user_id == user_id)
        .where(recovery_codes.c.code_hash == code_hash)
        .where(recovery_codes.c.used_at.is_(None))
        .values(used_at=now)
    )
    return spent.rowcount == 1


def count_unused_codes(connection: Connection, user_id: UUID) -> int:
    return connection.execute(
        select(func.count())
        .select_from(recovery_codes)
        .where(recovery_codes.c.user_id == user_id)
        .where(recovery_codes.c.used_at.is_(None))
    ).scalar_one()
