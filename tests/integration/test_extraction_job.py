"""The worker running real jobs against real Postgres, with a fake provider on the wire."""

from __future__ import annotations

import json
import re

import httpx
import pytest
from sqlalchemy import text

from web import clock, job_store, process_store
from web.user_store import create_user
from worker.extraction_job import run_extraction_job
from worker.job_loop import CurrentJob, work_once

CAST = [
    {"person_id": "anna-schmidt", "name": "Anna Schmidt", "role": "Intake Coordinator at Brauhaus Mueller"},
    {"person_id": "boris-keller", "name": "Boris Keller", "role": "Approver"},
    {"person_id": "clara-wolf", "name": "Clara Wolf", "role": "Finance Clerk"},
]
REAL_NAMES = ("Anna", "Schmidt", "Boris", "Keller", "Clara", "Wolf", "Brauhaus", "Mueller", "anna-schmidt")
ENVIRONMENT = {
    "PROVIDERS_ENABLED": "openrouter,deepseek",
    "SENSITIVE_OK_PROVIDERS": "openrouter",
    "OPENROUTER_API_KEY": "sk-or-test-key",
    "DEEPSEEK_API_KEY": "sk-ds-test-key",
}


def transcript_for(member, other):
    return (
        "**Interviewer:** What are you waiting on?\n\n"
        f"**{member['name']}:** I am waiting for {other['name']} to approve the request. "
        "It takes about two days."
    )


class FakeProvider:
    """Answers like a model that quotes the first sentence of the interview it was shown."""

    def __init__(self, fail_for=(), tokens=(100, 50), on_call=None, status_for_failure=400):
        self.requests: list[httpx.Request] = []
        self.fail_for, self.tokens, self.on_call, self.status = (
            set(fail_for),
            tokens,
            on_call,
            status_for_failure,
        )

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        prompt = json.loads(request.content)["messages"][0]["content"]
        speaker = re.search(r"\*\*name:\*\* (PERSON_\d+)", prompt).group(1)
        if self.on_call:
            self.on_call(len(self.requests))
        if speaker in self.fail_for:
            return httpx.Response(self.status, text="nope")
        other = re.search(r"waiting for (PERSON_\d+) to approve", prompt).group(1)
        claim = {
            "id": "respondent-001",
            "respondent_id": "respondent",
            "session_id": "session",
            "captured_at": "2000-01-01T00:00:00Z",
            "kind": "wait",
            "hedging": "firm",
            "polarity": "asserted",
            "subject_scope": "self",
            "verbatim": f"I am waiting for {other} to approve the request.",
            "entity_refs": [{"text": other, "type": "actor", "role": "waiting_on"}],
            "payload": {"waiting_on": other, "owner": "internal", "current": True, "duration": None},
        }
        body = {
            "choices": [{"message": {"content": json.dumps([claim])}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": self.tokens[0], "completion_tokens": self.tokens[1]},
        }
        return httpx.Response(200, json=body)

    def client(self) -> httpx.Client:
        return httpx.Client(transport=httpx.MockTransport(self))

    @property
    def wire_text(self) -> str:
        return "\n".join(r.content.decode() for r in self.requests)


@pytest.fixture
def world(engine):
    """A user, a client, an uploaded process with three interviews, ready for a job."""

    def build(sensitivity="sensitive", provider="openrouter", max_tokens=1_000_000, private_terms=()):
        with engine.begin() as connection:
            user = create_user(connection, "owner@example.com", "hash")
            client = process_store.create_client(connection, "Brauhaus", user, False, sensitivity)
            process = process_store.create_process(
                connection,
                client_id=client,
                slug="p",
                name="Intake",
                domain="beer orders",
                organisation={"name": "Brauhaus Mueller"},
                cast=CAST,
                private_terms=list(private_terms),
                status="extracting",
            )
            others = CAST[1:] + CAST[:1]
            process_store.add_transcripts(
                connection,
                process,
                {m["person_id"]: transcript_for(m, o) for m, o in zip(CAST, others, strict=True)},
            )
            job = job_store.enqueue_job(
                connection, process, user, provider, "some-model", "run-1", max_tokens, "corr-123"
            )
        return process, job, user

    return build


def run(engine, job_id, provider=None, environment=None):
    provider = provider or FakeProvider()
    with engine.begin() as connection:
        row = connection.execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id}).one()
        connection.execute(
            text("UPDATE jobs SET status = 'running', heartbeat_at = now() WHERE id = :id"), {"id": job_id}
        )
    run_extraction_job(engine, row, environment or ENVIRONMENT, provider.client(), lambda seconds: None)
    return provider


def job_row(engine, job_id):
    with engine.connect() as connection:
        return connection.execute(text("SELECT * FROM jobs WHERE id = :id"), {"id": job_id}).one()


def scalar(engine, sql, **params):
    with engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def test_a_full_run_extracts_analyses_and_records_everything(engine, world):
    process, job, _ = world()
    run(engine, job)
    row = job_row(engine, job)
    assert row.status == "done" and row.error is None
    assert [e["state"] for e in row.progress] == ["done", "done", "done"]
    assert (row.tokens_in, row.tokens_out) == (300, 150)
    assert scalar(engine, "SELECT status FROM processes WHERE id = :p", p=process) == "analysed"
    assert (
        scalar(engine, "SELECT count(*) FROM claims WHERE process_id = :p AND claim_set = 'run-1'", p=process)
        == 3
    )
    assert (
        scalar(
            engine, "SELECT count(*) FROM results WHERE process_id = :p AND claim_set = 'run-1'", p=process
        )
        == 1
    )


def test_stored_claims_use_real_names_and_the_original_wording(engine, world):
    process, job, _ = world()
    run(engine, job)
    with engine.connect() as connection:
        grouped = process_store.claims_by_person(connection, process, "run-1")
    [claim] = grouped["anna-schmidt"]
    assert claim["verbatim"] == "I am waiting for Boris Keller to approve the request."
    assert claim["entity_refs"][0]["text"] == "Boris Keller"
    assert claim["respondent_id"] == "anna-schmidt" and claim["id"] == "anna-schmidt-001"


def test_no_real_name_ever_goes_over_the_wire(engine, world):
    _, job, _ = world(private_terms=["Hopfenstrasse 12"])
    provider = run(engine, job)
    assert len(provider.requests) == 3
    for forbidden in REAL_NAMES:
        assert forbidden not in provider.wire_text, forbidden
    assert "PERSON_1" in provider.wire_text


def test_the_api_key_is_sent_as_a_header_and_never_in_the_body(engine, world):
    _, job, _ = world()
    provider = run(engine, job)
    assert all(r.headers["authorization"] == "Bearer sk-or-test-key" for r in provider.requests)
    assert "sk-or-test-key" not in provider.wire_text


def test_sensitive_data_is_refused_for_a_provider_the_operator_did_not_approve(engine, world):
    process, job, _ = world(sensitivity="sensitive", provider="deepseek")
    provider = run(engine, job)
    assert provider.requests == []
    row = job_row(engine, job)
    assert row.status == "failed" and "not allowed for sensitive" in row.error
    assert scalar(engine, "SELECT status FROM processes WHERE id = :p", p=process) == "failed"


def test_the_same_provider_is_fine_for_a_standard_client(engine, world):
    _, job, _ = world(sensitivity="standard", provider="deepseek")
    assert run(engine, job).requests and job_row(engine, job).status == "done"


def test_a_provider_that_is_switched_off_or_has_no_key_makes_no_calls(engine, world):
    _, job, _ = world(sensitivity="standard")
    provider = run(engine, job, environment={**ENVIRONMENT, "PROVIDERS_ENABLED": "deepseek"})
    assert provider.requests == [] and "not allowed" in job_row(engine, job).error
    _, second, _ = world_again(engine)
    provider = run(
        engine, second, environment={k: v for k, v in ENVIRONMENT.items() if k != "OPENROUTER_API_KEY"}
    )
    assert provider.requests == [] and "No API key" in job_row(engine, second).error


def world_again(engine):
    with engine.begin() as connection:
        user = create_user(connection, "second@example.com", "hash")
        client = process_store.create_client(connection, "Second", user, False, "standard")
        process = process_store.create_process(
            connection,
            client_id=client,
            slug="q",
            name="Q",
            domain="d",
            organisation={"name": "X"},
            cast=CAST,
            status="extracting",
        )
        process_store.add_transcripts(
            connection, process, {m["person_id"]: transcript_for(m, CAST[0]) for m in CAST}
        )
        job = job_store.enqueue_job(connection, process, user, "openrouter", "m", "run-1", 10**6, "c")
    return process, job, user


def test_one_failing_transcript_does_not_stop_the_others(engine, world):
    process, job, _ = world()
    run(engine, job, FakeProvider(fail_for={"PERSON_2"}))
    row = job_row(engine, job)
    assert row.status == "partial"
    assert [e["state"] for e in row.progress] == ["done", "failed", "done"]
    assert "HTTP 400" in row.progress[1]["error"]
    assert scalar(engine, "SELECT count(*) FROM claims WHERE process_id = :p", p=process) == 2
    assert scalar(engine, "SELECT status FROM processes WHERE id = :p", p=process) == "analysed"


def test_when_every_transcript_fails_the_job_and_process_fail_and_nothing_is_analysed(engine, world):
    process, job, _ = world()
    run(engine, job, FakeProvider(fail_for={"PERSON_1", "PERSON_2", "PERSON_3"}))
    assert job_row(engine, job).status == "failed"
    assert scalar(engine, "SELECT status FROM processes WHERE id = :p", p=process) == "failed"
    assert scalar(engine, "SELECT count(*) FROM results WHERE process_id = :p", p=process) == 0


def test_a_cancelled_job_stops_cleanly_and_keeps_finished_work(engine, world):
    process, job, _ = world()

    def cancel_after_first(call_number):
        if call_number == 1:
            with engine.begin() as connection:
                job_store.request_cancel(connection, job)

    run(engine, job, FakeProvider(on_call=cancel_after_first))
    row = job_row(engine, job)
    assert row.status == "cancelled"
    assert [e["state"] for e in row.progress] == ["done", "pending", "pending"]
    assert scalar(engine, "SELECT count(*) FROM claims WHERE process_id = :p", p=process) == 1
    assert scalar(engine, "SELECT count(*) FROM results WHERE process_id = :p", p=process) == 1


def test_a_job_cancelled_before_it_starts_makes_no_calls(engine, world):
    _, job, _ = world()
    with engine.begin() as connection:
        job_store.request_cancel(connection, job)
    assert run(engine, job).requests == [] and job_row(engine, job).status == "cancelled"


def test_the_token_cap_stops_the_job_after_the_transcript_that_reached_it(engine, world):
    process, job, _ = world(max_tokens=200)
    run(engine, job, FakeProvider(tokens=(150, 60)))
    row = job_row(engine, job)
    assert row.status == "stopped_cost_cap"
    assert [e["state"] for e in row.progress] == ["done", "pending", "pending"]
    assert scalar(engine, "SELECT count(*) FROM claims WHERE process_id = :p", p=process) == 1


def test_a_process_deleted_mid_job_ends_the_job_without_a_crash(engine, world):
    process, job, _ = world()

    def delete_process(call_number):
        if call_number == 1:
            with engine.begin() as connection:
                process_store.delete_process(connection, process)

    run(engine, job, FakeProvider(on_call=delete_process))
    assert scalar(engine, "SELECT count(*) FROM jobs") == 0
    assert scalar(engine, "SELECT count(*) FROM claims") == 0


def test_a_crash_in_the_analysis_fails_the_job_and_the_process_instead_of_hanging(engine, world, monkeypatch):
    process, job, _ = world()
    monkeypatch.setattr("worker.extraction_job.analyse", lambda *args, **kwargs: 1 / 0)
    run(engine, job)
    assert job_row(engine, job).status == "failed"
    assert scalar(engine, "SELECT status FROM processes WHERE id = :p", p=process) == "failed"


def test_model_calls_are_audited_under_the_model_not_system(engine, world):
    _, job, _ = world()
    run(engine, job, FakeProvider(fail_for={"PERSON_2"}))
    with engine.connect() as connection:
        rows = connection.execute(
            text("SELECT actor_label, outcome FROM audit_log WHERE action = 'model_call' ORDER BY id")
        ).all()
    label = "model:openrouter/some-model"
    assert [(r.actor_label, r.outcome) for r in rows] == [(label, "ok"), (label, "error"), (label, "ok")]


def test_a_second_run_with_another_claim_set_keeps_the_first_result(engine, world):
    process, job, user = world()
    run(engine, job)
    with engine.begin() as connection:
        second = job_store.enqueue_job(
            connection, process, user, "openrouter", "other-model", "run-2", 10**6, "c2"
        )
    run(engine, second)
    assert (
        scalar(engine, "SELECT count(DISTINCT claim_set) FROM results WHERE process_id = :p", p=process) == 2
    )


# ---- the queue itself ---------------------------------------------------------------------------


def test_a_job_can_be_claimed_only_once(engine, world):
    _, job, _ = world()
    with engine.begin() as connection:
        first = job_store.claim_next_job(connection, clock.utcnow())
    with engine.begin() as connection:
        second = job_store.claim_next_job(connection, clock.utcnow())
    assert first.id == job and second is None


def test_a_running_job_whose_worker_went_silent_is_failed(engine, world):
    process, job, _ = world()
    with engine.begin() as connection:
        job_store.claim_next_job(connection, clock.utcnow())
        connection.execute(text("UPDATE jobs SET heartbeat_at = now() - interval '10 minutes'"))
        assert job_store.fail_stale_jobs(connection, clock.utcnow()) == 1
    assert job_row(engine, job).status == "failed" and "worker stopped" in job_row(engine, job).error
    assert scalar(engine, "SELECT status FROM processes WHERE id = :p", p=process) == "failed"


def test_a_recently_beating_job_is_left_alone(engine, world):
    world()
    with engine.begin() as connection:
        job_store.claim_next_job(connection, clock.utcnow())
        assert job_store.fail_stale_jobs(connection, clock.utcnow()) == 0


def test_only_one_active_job_per_process(engine, world):
    process, job, _ = world()
    with engine.connect() as connection:
        assert job_store.has_active_job(connection, process)
    run(engine, job)
    with engine.connect() as connection:
        assert not job_store.has_active_job(connection, process)


def test_the_loop_claims_runs_and_then_reports_idle(engine, world, monkeypatch):
    _, job, _ = world()
    provider = FakeProvider()
    original = httpx.Client
    monkeypatch.setattr(
        "httpx.Client", lambda *args, **kwargs: original(transport=httpx.MockTransport(provider))
    )
    current = CurrentJob()
    assert work_once(engine, ENVIRONMENT, current) is True
    assert job_row(engine, job).status == "done" and current.get() is None
    assert work_once(engine, ENVIRONMENT, current) is False


def test_an_unexpected_error_inside_one_transcript_shows_a_generic_message_not_internals(engine, world):
    class Exploding(FakeProvider):
        def __call__(self, request):
            if "PERSON_2" in json.loads(request.content)["messages"][0]["content"].split("**name:**")[1][:12]:
                raise RuntimeError("secret internal detail /srv/app/path")
            return super().__call__(request)

    _, job, _ = world()
    run(engine, job, Exploding())
    row = job_row(engine, job)
    assert row.status == "partial" and row.progress[1]["state"] == "failed"
    assert (
        "secret internal detail" not in json.dumps(row.progress) and "server log" in row.progress[1]["error"]
    )
    assert [e["state"] for e in row.progress] == ["done", "failed", "done"]
