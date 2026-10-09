"""Starting an extraction run and following it: the setup page, the job page, cancel."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from sqlalchemy.engine import Connection, Row

from web import job_store, process_store
from web.audit_trail import record_audit
from web.current_user import SignedInUser, client_address, require_user
from web.extraction_preview import build_preview
from web.model_providers import PROVIDERS
from web.page_rendering import render_page
from web.provider_policy import allowed_providers
from web.structured_logging import correlation_id
from web.viewer_routes import parse_id
from web.workbench_routes import not_found, redirect

router = APIRouter()

MODEL_NAME = re.compile(r"^[\w./:@+-]{1,120}$")
MIN_TOKEN_CAP, MAX_TOKEN_CAP = 1_000, 5_000_000
CAP_HEADROOM = 3  # the default cap is this many times the estimate, because the estimate is rough


def provider_choices(request: Request, sensitivity: str) -> list[dict[str, Any]]:
    """Every provider with whether it can be used here, and if not, why."""
    settings = request.app.state.settings
    allowed = allowed_providers(sensitivity, settings.enabled_providers, settings.sensitive_ok_providers)
    choices = []
    for name, spec in PROVIDERS.items():
        if name in allowed:
            reason = None
        elif name not in settings.enabled_providers:
            reason = "not switched on for this server"
        else:
            reason = "not approved for sensitive clients on this server"
        choices.append({"name": name, "label": spec.label, "model": spec.suggested_model, "reason": reason})
    return choices


def owned_process(request: Request, connection: Connection, process_id: str, user: SignedInUser) -> Row:
    process = process_store.find_owned_process(connection, parse_id(process_id), user.user_id)
    if process is None:
        raise not_found()
    return process


def setup_context(request: Request, connection: Connection, process: Row) -> dict[str, Any]:
    transcripts = process_store.transcript_bodies(connection, process.id)
    terms = [t for t in [(process.organisation or {}).get("name"), *process.private_terms] if t]
    preview = build_preview(process.cast, transcripts, terms)
    default_cap = (
        max(100_000, (preview.estimated_total * CAP_HEADROOM) // 10_000 * 10_000) if preview else 100_000
    )
    return {
        "process": process,
        "providers": provider_choices(request, process.sensitivity),
        "preview": preview,
        "default_cap": min(default_cap, MAX_TOKEN_CAP),
        "has_active_job": job_store.has_active_job(connection, process.id),
        "terms": terms,
    }


@router.get("/processes/{process_id}/extract", response_class=HTMLResponse)
def extract_page(request: Request, process_id: str, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.connect() as connection:
        process = owned_process(request, connection, process_id, user)
        context = setup_context(request, connection, process)
    return render_page(request, "extract.html", user=user, **context)


def unique_claim_set(connection: Connection, process_id: UUID, provider: str, model: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", f"{provider}-{model}".lower()).strip("-")[:48]
    candidate, number = base, 2
    while process_store.claim_set_taken(connection, process_id, candidate) or job_store.claim_set_in_use(
        connection, process_id, candidate
    ):
        candidate = f"{base}-{number}"
        number += 1
    return candidate


def request_problem(request: Request, process: Row, provider: str, model: str, max_tokens: int) -> str | None:
    allowed = [c["name"] for c in provider_choices(request, process.sensitivity) if c["reason"] is None]
    if provider not in allowed:
        return "That provider cannot be used for this client."
    if not MODEL_NAME.fullmatch(model):
        return "Enter the model name exactly as the provider spells it."
    if not MIN_TOKEN_CAP <= max_tokens <= MAX_TOKEN_CAP:
        return f"The token cap must be between {MIN_TOKEN_CAP:,} and {MAX_TOKEN_CAP:,}."
    return None


@router.post("/processes/{process_id}/extract", response_class=HTMLResponse)
def start_extraction(
    request: Request,
    process_id: str,
    provider: str = Form(""),
    model: str = Form(""),
    max_tokens: int = Form(0),
    user: SignedInUser = Depends(require_user),
):
    model = model.strip()
    with request.app.state.engine.begin() as connection:
        process = owned_process(request, connection, process_id, user)
        problem = request_problem(request, process, provider, model, max_tokens)
        if problem is None and job_store.has_active_job(connection, process.id):
            problem = "A run is already queued or in progress for this process."
        if problem:
            context = setup_context(request, connection, process)
            return render_page(request, "extract.html", user=user, status_code=400, error=problem, **context)
        claim_set = unique_claim_set(connection, process.id, provider, model)
        job_id = job_store.enqueue_job(
            connection, process.id, user.user_id, provider, model, claim_set, max_tokens, correlation_id.get()
        )
        process_store.set_process_status(connection, process.id, "extracting")
        record_audit(
            connection,
            user.user_id,
            user.email,
            "extraction_queued",
            "success",
            client_address(request),
            f"{process.id} via {provider}/{model}",
        )
    return RedirectResponse(f"/jobs/{job_id}", status_code=303)


def visible_job(request: Request, connection: Connection, job_id: str, user: SignedInUser) -> Row:
    job = job_store.find_visible_job(connection, parse_id(job_id), user.user_id)
    if job is None:
        raise not_found()
    return job


def status_document(job: Row) -> dict[str, Any]:
    return {
        "status": job.status,
        "is_finished": job.status in job_store.FINISHED_STATES,
        "progress": job.progress,
        "tokens_in": job.tokens_in,
        "tokens_out": job.tokens_out,
        "max_tokens": job.max_tokens,
        "error": job.error,
        "is_cancel_requested": job.is_cancel_requested,
    }


@router.get("/jobs/{job_id}", response_class=HTMLResponse)
def job_page(request: Request, job_id: str, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.connect() as connection:
        job = visible_job(request, connection, job_id, user)
    return render_page(
        request,
        "job.html",
        user=user,
        job=job,
        state=status_document(job),
        is_owner=job.client_owner == user.user_id,
    )


@router.get("/jobs/{job_id}/status")
def job_status(request: Request, job_id: str, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.connect() as connection:
        job = visible_job(request, connection, job_id, user)
    return JSONResponse(status_document(job), headers={"Cache-Control": "no-store"})


@router.post("/jobs/{job_id}/cancel")
def cancel_job(request: Request, job_id: str, user: SignedInUser = Depends(require_user)):
    with request.app.state.engine.begin() as connection:
        job = visible_job(request, connection, job_id, user)
        if job.client_owner != user.user_id:
            raise HTTPException(status_code=403, detail="Only the owner can cancel a run")
        job_store.request_cancel(connection, job.id)
        record_audit(
            connection,
            user.user_id,
            user.email,
            "extraction_cancel_requested",
            "success",
            client_address(request),
            str(job.id),
        )
    return redirect(f"/jobs/{job.id}")
