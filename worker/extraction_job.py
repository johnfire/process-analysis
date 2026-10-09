"""Run one extraction job: for each interview, ask the chosen model for claims, then analyse.

Failure is isolated per transcript: one that cannot be extracted is recorded as failed and the
rest carry on. The job stops cleanly, keeping finished work, when it is cancelled, when its token
cap is reached, or when its process has been deleted. The policy check is repeated here, not only
in the web form, so a job that should never have been queued cannot send data anywhere.
"""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

import httpx
from sqlalchemy import select
from sqlalchemy.engine import Connection, Engine, Row

from analyzer.analysis import ANALYZER_VERSION, analyse
from analyzer.private_extraction import PrivateExtraction, RespondentDetails, extract_privately
from analyzer.pseudonymise import PersonToHide
from analyzer.resolve import Person
from analyzer.result_document import build_result_document
from web import clock, job_store, process_store
from web.audit_trail import record_audit
from web.database import clients, processes
from web.model_providers import PROVIDERS, ProviderError, ProviderSpec, api_key_for, complete
from web.provider_policy import is_allowed, parse_provider_list
from web.structured_logging import correlation_id

log = logging.getLogger("worker.extraction")
ERROR_CHARACTERS = 300
WORKER_ADDRESS = "worker"


@dataclass
class TokenMeter:
    limit: int
    tokens_in: int = 0
    tokens_out: int = 0

    @property
    def total(self) -> int:
        return self.tokens_in + self.tokens_out

    @property
    def is_over_limit(self) -> bool:
        return self.total >= self.limit

    def add(self, tokens_in: int, tokens_out: int) -> None:
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out


@dataclass(frozen=True)
class JobContext:
    job: Row
    process: Row
    sensitivity: str
    transcripts: dict[str, str]


def load_context(connection: Connection, job: Row) -> JobContext | None:
    row = connection.execute(
        select(processes, clients.c.sensitivity)
        .join_from(processes, clients, processes.c.client_id == clients.c.id)
        .where(processes.c.id == job.process_id)
    ).first()
    if row is None:
        return None
    return JobContext(job, row, row.sensitivity, process_store.transcript_bodies(connection, job.process_id))


def refusal_reason(context: JobContext, environment: Mapping[str, str]) -> str | None:
    """Why this job may not run, or None. Provider, approval and key are all checked here."""
    provider = context.job.provider
    enabled = parse_provider_list(environment.get("PROVIDERS_ENABLED", ""))
    approved = parse_provider_list(environment.get("SENSITIVE_OK_PROVIDERS", ""))
    if provider not in PROVIDERS:
        return f"Unknown provider {provider!r}."
    if not is_allowed(provider, context.sensitivity, enabled, approved):
        return f"{PROVIDERS[provider].label} is not allowed for {context.sensitivity} clients on this server."
    if api_key_for(PROVIDERS[provider], environment) is None:
        return f"No API key for {PROVIDERS[provider].label} is configured on the worker."
    return None


def people_to_hide(cast: list[dict[str, Any]]) -> list[PersonToHide]:
    return [PersonToHide(position, member["name"]) for position, member in enumerate(cast, start=1)]


def extra_terms_for(process: Row) -> list[str]:
    organisation = (process.organisation or {}).get("name")
    return [term for term in [organisation, *process.private_terms] if term]


def update_progress(engine: Engine, job_id: UUID, progress: list[dict[str, Any]], meter: TokenMeter) -> None:
    with engine.begin() as connection:
        job_store.record_progress(
            connection, job_id, progress, meter.tokens_in, meter.tokens_out, clock.utcnow()
        )


def stop_reason(engine: Engine, job_id: UUID, meter: TokenMeter) -> str | None:
    """Why the job should stop before the next transcript: deleted, cancelled, or over its cap."""
    with engine.connect() as connection:
        exists, is_cancelled = job_store.job_state(connection, job_id)
    if not exists:
        return "deleted"
    if is_cancelled:
        return "cancelled"
    return "stopped_cost_cap" if meter.is_over_limit else None


def summarise(result: PrivateExtraction) -> dict[str, Any]:
    return {
        "state": "done",
        "claims": len(result.claims),
        "ungrounded": result.ungrounded_count,
        "invalid": len(result.invalid),
        "grounding_rate": round(result.grounding_rate, 3),
    }


def extract_one(
    engine: Engine,
    context: JobContext,
    member: dict[str, Any],
    position: int,
    spec: ProviderSpec,
    api_key: str,
    meter: TokenMeter,
    client: httpx.Client | None,
    pause: Callable[[float], None],
) -> dict[str, Any]:
    """Extract one respondent. Never raises: a failure becomes a 'failed' progress entry."""
    job, person_key = context.job, member["person_id"]

    def ask(prompt: str) -> str:
        completion = complete(spec, job.model, prompt, api_key, client, pause)
        meter.add(completion.input_tokens, completion.output_tokens)
        return completion.text

    respondent = RespondentDetails(person_key, member["name"], member["role"], position)
    try:
        result = extract_privately(
            ask,
            context.transcripts[person_key],
            respondent,
            people_to_hide(context.process.cast),
            extra_terms_for(context.process),
        )
        with engine.begin() as connection:
            process_store.replace_person_claims(
                connection, job.process_id, job.claim_set, person_key, result.claims
            )
        outcome, entry = "ok", summarise(result)
    except (ProviderError, ValueError, json.JSONDecodeError) as error:
        outcome, entry = "error", {"state": "failed", "error": str(error)[:ERROR_CHARACTERS]}
    except Exception:
        log.exception("unexpected failure extracting %s", person_key)
        outcome, entry = (
            "error",
            {"state": "failed", "error": "An internal error occurred; see the server log."},
        )
    audit_model_call(engine, context, person_key, outcome)
    return entry


def audit_model_call(engine: Engine, context: JobContext, person_key: str, outcome: str) -> None:
    """Every model call is recorded, attributed to the model that made it rather than to 'system'."""
    job = context.job
    try:
        with engine.begin() as connection:
            record_audit(
                connection,
                None,
                f"model:{job.provider}/{job.model}",
                "model_call",
                outcome,
                WORKER_ADDRESS,
                f"{job.process_id}/{person_key}",
            )
    except Exception:
        log.exception("could not write the audit entry for a model call")


def analyse_stored_claims(engine: Engine, context: JobContext) -> bool:
    """Analyse whatever claims exist for this job's claim set and store the result. False if none."""
    job, process = context.job, context.process
    with engine.begin() as connection:
        grouped = process_store.claims_by_person(connection, job.process_id, job.claim_set)
        if not grouped:
            return False
        cast = [Person(m["person_id"], m["name"], m["role"]) for m in process.cast]
        document = build_result_document(
            analyse(cast, grouped), job.claim_set, process.organisation, process.domain
        )
        process_store.add_result(connection, job.process_id, job.claim_set, ANALYZER_VERSION, document)
    return True


def final_status(stopped: str | None, progress: list[dict[str, Any]]) -> str:
    if stopped in ("cancelled", "stopped_cost_cap"):
        return stopped
    succeeded = sum(entry["state"] == "done" for entry in progress)
    if succeeded == len(progress) and progress:
        return "done"
    return "partial" if succeeded else "failed"


def finish(engine: Engine, context: JobContext, status: str, error: str | None, has_claims: bool) -> None:
    with engine.begin() as connection:
        job_store.finish_job(connection, context.job.id, status, error, clock.utcnow())
        process_store.set_process_status(
            connection, context.job.process_id, "analysed" if has_claims else "failed"
        )
        record_audit(
            connection,
            context.job.created_by,
            "job",
            "extraction_job",
            status,
            WORKER_ADDRESS,
            str(context.job.process_id),
        )


def run_extraction_job(
    engine: Engine,
    job: Row,
    environment: Mapping[str, str],
    client: httpx.Client | None = None,
    pause: Callable[[float], None] = time.sleep,
) -> None:
    """Run a claimed job to its end. Any failure is recorded on the job; nothing propagates."""
    token = correlation_id.set(job.correlation_id or "-")
    try:
        with engine.connect() as connection:
            context = load_context(connection, job)
        if context is None:
            return
        problem = refusal_reason(context, environment)
        if problem:
            finish(engine, context, "failed", problem, has_claims=False)
            return
        carry_out(engine, context, environment, client, pause)
    except Exception:
        log.exception("job %s failed unexpectedly", job.id)
        try:
            with engine.begin() as connection:
                message = "An internal error occurred; see the server log."
                job_store.finish_job(connection, job.id, "failed", message, clock.utcnow())
                process_store.set_process_status(connection, job.process_id, "failed")
        except Exception:
            log.exception("could not even record the failure of job %s", job.id)
    finally:
        correlation_id.reset(token)


def carry_out(
    engine: Engine,
    context: JobContext,
    environment: Mapping[str, str],
    client: httpx.Client | None,
    pause: Callable[[float], None],
) -> None:
    job = context.job
    spec = PROVIDERS[job.provider]
    api_key = api_key_for(spec, environment) or ""
    meter = TokenMeter(job.max_tokens)
    respondents = [m for m in context.process.cast if m["person_id"] in context.transcripts]
    progress: list[dict[str, Any]] = [
        {"person_key": m["person_id"], "name": m["name"], "state": "pending"} for m in respondents
    ]
    stopped = None
    for position, member in enumerate(context.process.cast, start=1):
        if member["person_id"] not in context.transcripts:
            continue
        stopped = stop_reason(engine, job.id, meter)
        if stopped:
            break
        entry = next(e for e in progress if e["person_key"] == member["person_id"])
        entry["state"] = "running"
        update_progress(engine, job.id, progress, meter)
        entry.update(extract_one(engine, context, member, position, spec, api_key, meter, client, pause))
        update_progress(engine, job.id, progress, meter)
    if stopped == "deleted":
        return
    has_claims = analyse_stored_claims(engine, context)
    finish(engine, context, final_status(stopped, progress), None, has_claims)
