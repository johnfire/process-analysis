"""The audit log: who did what to what, and how it went.

Every state-changing action writes a row. Rows are inserted and never edited, with one exception:
when an account is deleted its identifying labels are blanked so the trail keeps the event but not
the person.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.engine import Connection

from web.database import audit_log
from web.structured_logging import correlation_id

ERASED_LABEL = "deleted-account"


def record_audit(
    connection: Connection,
    actor_user_id: UUID | None,
    actor_label: str,
    action: str,
    outcome: str,
    ip_address: str,
    target: str | None = None,
) -> None:
    connection.execute(
        insert(audit_log).values(
            actor_user_id=actor_user_id,
            actor_label=actor_label,
            action=action,
            target=target,
            outcome=outcome,
            correlation_id=correlation_id.get(),
            ip_address=ip_address,
        )
    )


def erase_identity(connection: Connection, user_id: UUID) -> None:
    connection.execute(
        update(audit_log)
        .where(audit_log.c.actor_user_id == user_id)
        .values(actor_label=ERASED_LABEL, ip_address=None)
    )
    connection.execute(update(audit_log).where(audit_log.c.target == str(user_id)).values(ip_address=None))


def export_audit_entries(connection: Connection, user_id: UUID) -> list[dict[str, Any]]:
    rows = connection.execute(
        select(audit_log).where(audit_log.c.actor_user_id == user_id).order_by(audit_log.c.id)
    )
    return [
        {
            "at": row.at.isoformat(),
            "action": row.action,
            "target": row.target,
            "outcome": row.outcome,
            "ip_address": row.ip_address,
        }
        for row in rows
    ]
