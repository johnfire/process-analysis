"""Reads and writes for clients, processes, transcripts, claims and results.

Visibility is decided here, in the query, not in the routes: a client is visible to a user when
they own it or when it has no owner (the shared synthetic corpus). A process of another user's
client simply does not exist as far as this module is concerned.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import and_, delete, func, insert, or_, select, update
from sqlalchemy.engine import Connection, Row

from web.database import claims, clients, processes, results, transcripts

PAGE_SIZE = 100
PRIMARY_CLAIM_SET = "claims"


def is_visible_to(user_id: UUID):
    return or_(clients.c.owner_user_id.is_(None), clients.c.owner_user_id == user_id)


def visible_clients(connection: Connection, user_id: UUID) -> list[Row]:
    return list(
        connection.execute(
            select(clients, func.count(processes.c.id).label("process_count"))
            .select_from(clients.outerjoin(processes, processes.c.client_id == clients.c.id))
            .where(is_visible_to(user_id))
            .group_by(clients.c.id)
            .order_by(clients.c.is_synthetic.desc(), clients.c.name)
        )
    )


def find_visible_client(connection: Connection, client_id: UUID, user_id: UUID) -> Row | None:
    return connection.execute(
        select(clients).where(clients.c.id == client_id).where(is_visible_to(user_id))
    ).first()


def list_processes(connection: Connection, client_id: UUID) -> list[Row]:
    return list(
        connection.execute(
            select(processes).where(processes.c.client_id == client_id).order_by(processes.c.name)
        )
    )


def find_visible_process(connection: Connection, process_id: UUID, user_id: UUID) -> Row | None:
    """The process joined with its client's name, or None when it is missing or not this user's."""
    return connection.execute(
        select(processes, clients.c.name.label("client_name"), clients.c.id.label("owning_client_id"))
        .join_from(processes, clients, processes.c.client_id == clients.c.id)
        .where(processes.c.id == process_id)
        .where(is_visible_to(user_id))
    ).first()


def claim_sets_of(connection: Connection, process_id: UUID) -> list[str]:
    """Claim sets, newest analysis first; sets that have no result yet follow alphabetically."""
    stored = connection.execute(
        select(claims.c.claim_set).where(claims.c.process_id == process_id).distinct()
    )
    newest = {
        row.claim_set: row.latest
        for row in connection.execute(
            select(results.c.claim_set, func.max(results.c.created_at).label("latest"))
            .where(results.c.process_id == process_id)
            .group_by(results.c.claim_set)
        )
    }
    return sorted(
        (row[0] for row in stored),
        key=lambda name: (name not in newest, -(newest[name].timestamp() if name in newest else 0), name),
    )


def latest_result(connection: Connection, process_id: UUID, claim_set: str) -> dict[str, Any] | None:
    row = connection.execute(
        select(results.c.document)
        .where(results.c.process_id == process_id)
        .where(results.c.claim_set == claim_set)
        .order_by(results.c.created_at.desc())
        .limit(1)
    ).first()
    return row.document if row else None


def latest_headlines(connection: Connection, process_ids: list[UUID]) -> dict[UUID, dict[str, Any]]:
    """The newest primary-claim-set result of each process, for the process list."""
    headlines: dict[UUID, dict[str, Any]] = {}
    rows = connection.execute(
        select(results.c.process_id, results.c.document)
        .where(results.c.process_id.in_(process_ids))
        .where(results.c.claim_set == PRIMARY_CLAIM_SET)
        .order_by(results.c.created_at)
    )
    for row in rows:
        headlines[row.process_id] = row.document  # oldest first, so the newest overwrites
    return headlines


def transcript_bodies(connection: Connection, process_id: UUID) -> dict[str, str]:
    rows = connection.execute(
        select(transcripts.c.person_key, transcripts.c.body).where(transcripts.c.process_id == process_id)
    )
    return {row.person_key: row.body for row in rows}


def claim_filter(process_id: UUID, claim_set: str, person_key: str | None, kind: str | None):
    condition = and_(claims.c.process_id == process_id, claims.c.claim_set == claim_set)
    if person_key:
        condition = and_(condition, claims.c.person_key == person_key)
    if kind:
        condition = and_(condition, claims.c.body["kind"].astext == kind)
    return condition


def list_claims(
    connection: Connection,
    process_id: UUID,
    claim_set: str,
    person_key: str | None = None,
    kind: str | None = None,
    page: int = 1,
) -> tuple[list[dict[str, Any]], int]:
    """One page of claims and the total matching, in interview order."""
    condition = claim_filter(process_id, claim_set, person_key, kind)
    total = connection.execute(select(func.count()).select_from(claims).where(condition)).scalar_one()
    rows = connection.execute(
        select(claims.c.person_key, claims.c.body)
        .where(condition)
        .order_by(claims.c.person_key, claims.c.position)
        .limit(PAGE_SIZE)
        .offset((max(page, 1) - 1) * PAGE_SIZE)
    )
    return [{"person_key": row.person_key, **row.body} for row in rows], total


def claim_kinds(connection: Connection, process_id: UUID, claim_set: str) -> list[str]:
    rows = connection.execute(
        select(claims.c.body["kind"].astext)
        .where(claims.c.process_id == process_id)
        .where(claims.c.claim_set == claim_set)
        .distinct()
    )
    return sorted(row[0] for row in rows if row[0])


def claims_by_person(
    connection: Connection, process_id: UUID, claim_set: str
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    rows = connection.execute(
        select(claims.c.person_key, claims.c.body)
        .where(claims.c.process_id == process_id)
        .where(claims.c.claim_set == claim_set)
        .order_by(claims.c.person_key, claims.c.position)
    )
    for row in rows:
        grouped.setdefault(row.person_key, []).append(row.body)
    return grouped


# ---- writes (used by the importer, and later by the workbench) --------------------------------


def find_synthetic_client(connection: Connection, name: str) -> UUID | None:
    return connection.execute(
        select(clients.c.id).where(clients.c.is_synthetic.is_(True)).where(clients.c.name == name)
    ).scalar()


def create_client(
    connection: Connection,
    name: str,
    owner_user_id: UUID | None,
    is_synthetic: bool,
    sensitivity: str = "sensitive",
) -> UUID:
    return connection.execute(
        insert(clients)
        .values(name=name, owner_user_id=owner_user_id, is_synthetic=is_synthetic, sensitivity=sensitivity)
        .returning(clients.c.id)
    ).scalar_one()


def find_owned_client(connection: Connection, client_id: UUID, user_id: UUID) -> Row | None:
    """A client this user owns. The shared synthetic corpus is nobody's to change."""
    return connection.execute(
        select(clients).where(clients.c.id == client_id).where(clients.c.owner_user_id == user_id)
    ).first()


def delete_client(connection: Connection, client_id: UUID) -> None:
    connection.execute(delete(clients).where(clients.c.id == client_id))


def delete_process(connection: Connection, process_id: UUID) -> None:
    connection.execute(delete(processes).where(processes.c.id == process_id))


def set_process_status(connection: Connection, process_id: UUID, status: str) -> None:
    connection.execute(update(processes).where(processes.c.id == process_id).values(status=status))


def replace_person_claims(
    connection: Connection,
    process_id: UUID,
    claim_set: str,
    person_key: str,
    person_claims: list[dict[str, Any]],
) -> None:
    """Store one respondent's claims for a claim set, replacing any earlier attempt for that respondent."""
    connection.execute(
        delete(claims)
        .where(claims.c.process_id == process_id)
        .where(claims.c.claim_set == claim_set)
        .where(claims.c.person_key == person_key)
    )
    add_claims(connection, process_id, claim_set, {person_key: person_claims})


def claim_set_taken(connection: Connection, process_id: UUID, claim_set: str) -> bool:
    return has_claim_set(connection, process_id, claim_set)


def find_process_by_slug(connection: Connection, client_id: UUID, slug: str) -> UUID | None:
    return connection.execute(
        select(processes.c.id).where(processes.c.client_id == client_id).where(processes.c.slug == slug)
    ).scalar()


def create_process(connection: Connection, **values: Any) -> UUID:
    return connection.execute(insert(processes).values(**values).returning(processes.c.id)).scalar_one()


def add_transcripts(connection: Connection, process_id: UUID, bodies: dict[str, str]) -> None:
    if bodies:
        connection.execute(
            insert(transcripts),
            [{"process_id": process_id, "person_key": key, "body": body} for key, body in bodies.items()],
        )


def has_claim_set(connection: Connection, process_id: UUID, claim_set: str) -> bool:
    return (
        connection.execute(
            select(claims.c.id)
            .where(claims.c.process_id == process_id)
            .where(claims.c.claim_set == claim_set)
            .limit(1)
        ).first()
        is not None
    )


def add_claims(
    connection: Connection,
    process_id: UUID,
    claim_set: str,
    claims_by_person: dict[str, list[dict[str, Any]]],
) -> None:
    rows = [
        {
            "process_id": process_id,
            "claim_set": claim_set,
            "person_key": person,
            "position": position,
            "body": body,
        }
        for person, person_claims in claims_by_person.items()
        for position, body in enumerate(person_claims)
    ]
    if rows:
        connection.execute(insert(claims), rows)


def has_result(connection: Connection, process_id: UUID, claim_set: str, analyzer_version: str) -> bool:
    return (
        connection.execute(
            select(results.c.id)
            .where(results.c.process_id == process_id)
            .where(results.c.claim_set == claim_set)
            .where(results.c.analyzer_version == analyzer_version)
        ).first()
        is not None
    )


def add_result(
    connection: Connection, process_id: UUID, claim_set: str, analyzer_version: str, document: dict[str, Any]
) -> None:
    connection.execute(
        insert(results).values(
            process_id=process_id, claim_set=claim_set, analyzer_version=analyzer_version, document=document
        )
    )
