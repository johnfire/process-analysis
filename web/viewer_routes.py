"""The viewer: clients, their processes, and one process's findings across six tabs."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from markupsafe import Markup, escape
from sqlalchemy.engine import Connection, Row

from web import job_store, process_store
from web.current_user import SignedInUser, require_user
from web.page_rendering import render_page
from web.process_charts import contrast_svg, timeline_svg
from web.transcript_lines import bold_markup_to_html, locate_quote, transcript_lines

router = APIRouter()

TABS = (
    ("timeline", "Timeline"),
    ("delay", "Delay"),
    ("cadences", "Cadences"),
    ("fractures", "Fractures"),
    ("evidence", "Evidence"),
    ("score", "Score"),
)


@dataclass(frozen=True)
class ProcessView:
    process: Row
    claim_sets: list[str]
    claim_set: str
    result: dict[str, Any] | None
    tab: str


def parse_id(raw: str) -> UUID:
    try:
        return UUID(raw)
    except ValueError:
        raise HTTPException(status_code=404, detail="Not found") from None


def choose_claim_set(claim_sets: list[str], requested: str | None) -> str:
    if requested is not None and requested in claim_sets:
        return requested
    if process_store.PRIMARY_CLAIM_SET in claim_sets:
        return process_store.PRIMARY_CLAIM_SET
    return claim_sets[0] if claim_sets else process_store.PRIMARY_CLAIM_SET


def available_tabs(result: dict[str, Any] | None) -> list[tuple[str, str]]:
    has_score = bool(result and result.get("score") is not None)
    return [(key, label) for key, label in TABS if key != "score" or has_score]


def choose_tab(requested: str | None, result: dict[str, Any] | None) -> str:
    keys = [key for key, _ in available_tabs(result)]
    return requested if requested in keys else "timeline"


@router.get("/clients", response_class=HTMLResponse)
def clients_page(request: Request, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.connect() as connection:
        listing = process_store.visible_clients(connection, user.user_id)
    return render_page(request, "clients.html", user=user, clients=listing)


@router.get("/clients/{client_id}", response_class=HTMLResponse)
def client_page(request: Request, client_id: str, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.connect() as connection:
        client = process_store.find_visible_client(connection, parse_id(client_id), user.user_id)
        if client is None:
            raise HTTPException(status_code=404, detail="Not found")
        listing = process_store.list_processes(connection, client.id)
        headlines = process_store.latest_headlines(connection, [p.id for p in listing])
    return render_page(
        request,
        "client.html",
        user=user,
        client=client,
        processes=listing,
        headlines=headlines,
        is_owner=client.owner_user_id == user.user_id,
    )


def load_view(
    connection: Connection, process: Row, requested_set: str | None, requested_tab: str | None
) -> ProcessView:
    claim_sets = process_store.claim_sets_of(connection, process.id)
    claim_set = choose_claim_set(claim_sets, requested_set)
    result = process_store.latest_result(connection, process.id, claim_set)
    return ProcessView(process, claim_sets, claim_set, result, choose_tab(requested_tab, result))


def link_quotes(quotes: list[dict[str, Any]], transcripts: dict[str, str]) -> list[dict[str, Any]]:
    """Each quote with the line of its speaker's transcript it was said on, when that can be found."""
    linked = []
    for quote in quotes:
        body = transcripts.get(quote["respondent_id"] or "")
        line = locate_quote(body, quote["verbatim"]) if body else None
        linked.append({**quote, "line": line})
    return linked


def fractures_context(connection: Connection, view: ProcessView, result: dict[str, Any]) -> dict[str, Any]:
    transcripts = process_store.transcript_bodies(connection, view.process.id)
    fractures = [
        {
            **fracture,
            "claimant_claims": link_quotes(fracture["claimant_claims"], transcripts),
            "counterparty_claims": link_quotes(fracture["counterparty_claims"], transcripts),
        }
        for fracture in result["fractures"]
    ]
    return {"fractures": fractures}


def evidence_context(connection: Connection, view: ProcessView, request: Request) -> dict[str, Any]:
    query = request.query_params
    person, kind = query.get("person") or None, query.get("kind") or None
    page = int(query["page"]) if query.get("page", "").isdigit() else 1
    rows, total = process_store.list_claims(connection, view.process.id, view.claim_set, person, kind, page)
    transcripts = process_store.transcript_bodies(connection, view.process.id)
    for row in rows:
        body = transcripts.get(row["person_key"])
        row["line"] = locate_quote(body, row.get("verbatim", "")) if body else None
    return {
        "claims": rows,
        "claim_total": total,
        "page": page,
        "has_next_page": page * process_store.PAGE_SIZE < total,
        "people": sorted(transcripts),
        "kinds": process_store.claim_kinds(connection, view.process.id, view.claim_set),
        "filter_person": person,
        "filter_kind": kind,
    }


def tab_context(connection: Connection, view: ProcessView, request: Request) -> dict[str, Any]:
    if view.result is None:
        return {}
    if view.tab == "timeline":
        return {"chart": timeline_svg(view.result["time"])}
    if view.tab == "delay":
        return {"chart": contrast_svg(view.result["people"])}
    if view.tab == "fractures":
        return fractures_context(connection, view, view.result)
    if view.tab == "evidence":
        return evidence_context(connection, view, request)
    return {}


@router.get("/processes/{process_id}", response_class=HTMLResponse)
def process_page(request: Request, process_id: str, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.connect() as connection:
        process = process_store.find_visible_process(connection, parse_id(process_id), user.user_id)
        if process is None:
            raise HTTPException(status_code=404, detail="Not found")
        view = load_view(
            connection, process, request.query_params.get("claims"), request.query_params.get("tab")
        )
        context = tab_context(connection, view, request)
        jobs = job_store.list_jobs(connection, process.id)
        transcript_people = sorted(process_store.transcript_bodies(connection, process.id))
    return render_page(
        request,
        "process.html",
        user=user,
        view=view,
        tabs=available_tabs(view.result),
        is_owner=process.client_owner == user.user_id,
        jobs=jobs,
        transcript_people=transcript_people,
        **context,
    )


@router.get("/processes/{process_id}/transcripts/{person_key}", response_class=HTMLResponse)
def transcript_page(
    request: Request, process_id: str, person_key: str, user: SignedInUser = Depends(require_user)
):
    with request.app.state.engine.connect() as connection:
        process = process_store.find_visible_process(connection, parse_id(process_id), user.user_id)
        body = process_store.transcript_bodies(connection, process.id).get(person_key) if process else None
    if process is None or body is None:
        raise HTTPException(status_code=404, detail="Not found")
    lines = [
        (line.number, Markup(bold_markup_to_html(str(escape(line.text))))) for line in transcript_lines(body)
    ]
    speaker = next((m["name"] for m in process.cast if m["person_id"] == person_key), person_key)
    return render_page(request, "transcript.html", user=user, process=process, speaker=speaker, lines=lines)
