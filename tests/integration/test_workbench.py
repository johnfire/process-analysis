"""Clients, uploads, extraction setup, jobs and deletion, through the real HTTP layer and Postgres."""

from __future__ import annotations

import re

import httpx
import pytest
from sqlalchemy import text

from tests.integration.conftest import DEFAULT_PASSWORD, SITE, log_in, new_browser
from tests.integration.test_extraction_job import ENVIRONMENT, FakeProvider
from web.seed_import import import_seed_processes
from worker.job_loop import CurrentJob, work_once

ANNA = "I am waiting for Boris to approve the request. It takes about two days."
BORIS = "I am waiting for Clara to approve the request. It takes about two days."


def interview(name, line):
    return f"**Interviewer:** What are you waiting on?\n\n**{name}:** {line}"


def process_form(**overrides):
    fields = {
        "name": "Order intake",
        "domain": "a beer order from request to delivery",
        "organisation": "Brauhaus Mueller",
        "terms": "Hopfenstrasse 12\nProjekt Adler",
        "name_0": "Anna Schmidt",
        "role_0": "Intake Coordinator",
        "text_0": interview("Anna Schmidt", ANNA),
        "name_1": "Boris Keller",
        "role_1": "Approver",
        "text_1": interview("Boris Keller", BORIS),
        "name_2": "Clara Wolf",
        "role_2": "Finance Clerk",
        "text_2": interview("Clara Wolf", ANNA.replace("Boris", "Anna")),
    }
    return {**fields, **overrides}


@pytest.fixture
def owner(browser, make_user):
    make_user()
    log_in(browser)
    return browser


def count(app, sql, **params):
    with app.state.engine.connect() as connection:
        return connection.execute(text(sql), params).scalar_one()


def make_client(owner, name="Brauhaus", sensitivity="sensitive"):
    response = owner.post("/clients", data={"name": name, "sensitivity": sensitivity})
    assert response.status_code == 303, response.text
    return response.headers["location"].rsplit("/", 1)[1]


def make_process(owner, client_id, **overrides):
    response = owner.post(f"/clients/{client_id}/processes", data=process_form(**overrides))
    assert response.status_code == 303, response.text
    return response.headers["location"].rsplit("/", 1)[1]


# ---- clients ------------------------------------------------------------------------------------


def test_a_new_client_defaults_to_sensitive_and_is_listed_with_its_label(owner, app):
    client_id = make_client(owner)
    assert count(app, "SELECT sensitivity FROM clients WHERE id = :i", i=client_id) == "sensitive"
    assert "Brauhaus" in owner.get("/clients").text and "sensitive" in owner.get("/clients").text


def test_bad_client_input_is_refused_and_creates_nothing(owner, app):
    assert owner.post("/clients", data={"name": "  ", "sensitivity": "sensitive"}).status_code == 400
    assert owner.post("/clients", data={"name": "X", "sensitivity": "public"}).status_code == 400
    assert count(app, "SELECT count(*) FROM clients") == 0


def test_creating_a_client_is_audited(owner, app):
    make_client(owner)
    assert count(app, "SELECT count(*) FROM audit_log WHERE action = 'client_create'") == 1


def test_a_client_page_offers_actions_only_to_its_owner(owner, app):
    own = make_client(owner)
    assert "New process" in owner.get(f"/clients/{own}").text
    import_seed_processes(app.state.engine)
    shared = count(app, "SELECT id FROM clients WHERE is_synthetic")
    page = owner.get(f"/clients/{shared}").text
    assert "New process" not in page and "Delete client" not in page


def test_the_shared_corpus_cannot_be_modified_by_anyone(owner, app):
    import_seed_processes(app.state.engine)
    shared = str(count(app, "SELECT id FROM clients WHERE is_synthetic"))
    assert owner.get(f"/clients/{shared}/processes/new", headers={"Accept": "text/html"}).status_code == 404
    assert owner.get(f"/clients/{shared}/delete", headers={"Accept": "text/html"}).status_code == 404
    assert (
        owner.post(
            f"/clients/{shared}/delete", data={"password": DEFAULT_PASSWORD, "confirmation": "DELETE"}
        ).status_code
        == 404
    )
    assert count(app, "SELECT count(*) FROM clients WHERE is_synthetic") == 1


# ---- creating a process --------------------------------------------------------------------------


def test_a_process_is_created_from_pasted_transcripts(owner, app):
    process_id = make_process(owner, make_client(owner))
    assert count(app, "SELECT status FROM processes WHERE id = :i", i=process_id) == "draft"
    assert count(app, "SELECT count(*) FROM transcripts WHERE process_id = :i", i=process_id) == 3
    with app.state.engine.connect() as connection:
        row = connection.execute(
            text('SELECT "cast", private_terms, organisation FROM processes WHERE id = :i'), {"i": process_id}
        ).one()
    assert [m["person_id"] for m in row.cast] == ["anna-schmidt", "boris-keller", "clara-wolf"]
    assert row.private_terms == ["Hopfenstrasse 12", "Projekt Adler"] and row.organisation == {
        "name": "Brauhaus Mueller"
    }


def test_a_transcript_can_be_uploaded_as_a_file(owner, app):
    client_id = make_client(owner)
    files = {"file_0": ("anna.md", interview("Anna Schmidt", ANNA).encode(), "text/markdown")}
    data = process_form(text_0="")
    response = owner.post(f"/clients/{client_id}/processes", data=data, files=files)
    assert response.status_code == 303, response.text
    body = count(app, "SELECT body FROM transcripts WHERE person_key = 'anna-schmidt'")
    assert "waiting for Boris" in body


def test_mistakes_re_render_the_form_with_what_was_typed_and_save_nothing(owner, app):
    client_id = make_client(owner)
    response = owner.post(f"/clients/{client_id}/processes", data=process_form(role_1="", name="Keep me"))
    assert (
        response.status_code == 400
        and "Row 2: enter their role" in response.text
        and "Keep me" in response.text
    )
    assert count(app, "SELECT count(*) FROM processes") == 0


def test_a_process_needs_a_name_and_at_least_one_interview(owner):
    client_id = make_client(owner)
    assert owner.post(f"/clients/{client_id}/processes", data={"name": "", "domain": ""}).status_code == 400


def test_an_oversized_upload_is_refused_early(owner):
    client_id = make_client(owner)
    response = owner.post(
        f"/clients/{client_id}/processes",
        data=process_form(),
        headers={"Content-Length": str(50 * 1024 * 1024)},
    )
    assert response.status_code == 413


def test_nobody_can_add_a_process_to_someone_elses_client(browser, app, make_user):
    make_user()
    make_user("other@example.com")
    log_in(browser)
    client_id = make_client(browser)
    intruder = new_browser(app)
    log_in(intruder, email="other@example.com")
    assert (
        intruder.get(f"/clients/{client_id}/processes/new", headers={"Accept": "text/html"}).status_code
        == 404
    )
    assert intruder.post(f"/clients/{client_id}/processes", data=process_form()).status_code == 404
    assert count(app, "SELECT count(*) FROM processes") == 0


# ---- the extraction setup page -------------------------------------------------------------------


def test_the_setup_page_shows_what_the_provider_would_receive_with_no_real_names(owner):
    page = owner.get(f"/processes/{make_process(owner, make_client(owner))}/extract").text
    sample = re.search(r'<pre class="sample"[^>]*>(.*?)</pre>', page, re.S).group(1)
    assert "PERSON_1" in sample
    for name in ("Anna", "Boris", "Schmidt", "Brauhaus"):
        assert name not in sample


def test_sensitive_clients_are_offered_only_approved_providers(owner):
    page = owner.get(
        f"/processes/{make_process(owner, make_client(owner, sensitivity='sensitive'))}/extract"
    ).text
    assert re.search(r'value="openrouter"[^>]*>', page) and "disabled" not in re.search(
        r'<input[^>]*value="openrouter"[^>]*>', page
    ).group(0)
    assert "disabled" in re.search(r'<input[^>]*value="deepseek"[^>]*>', page).group(0)
    assert "not approved for sensitive clients" in page and "not switched on for this server" in page


def test_standard_clients_may_use_any_switched_on_provider(owner):
    page = owner.get(
        f"/processes/{make_process(owner, make_client(owner, sensitivity='standard'))}/extract"
    ).text
    assert "disabled" not in re.search(r'<input[^>]*value="deepseek"[^>]*>', page).group(0)
    assert "disabled" in re.search(r'<input[^>]*value="anthropic"[^>]*>', page).group(0)


def test_the_setup_page_warns_about_names_nobody_listed(owner):
    text_with_stranger = interview("Anna Schmidt", ANNA + " Brigitte keeps chasing me.")
    page = owner.get(
        f"/processes/{make_process(owner, make_client(owner), text_0=text_with_stranger)}/extract"
    ).text
    assert "Brigitte" in page and "Look before you send" in page


# ---- starting a run -------------------------------------------------------------------------------


def start(owner, process_id, **overrides):
    data = {"provider": "openrouter", "model": "some-model", "max_tokens": "200000", **overrides}
    return owner.post(f"/processes/{process_id}/extract", data=data)


def test_starting_a_run_queues_a_job_and_marks_the_process(owner, app):
    process_id = make_process(owner, make_client(owner))
    response = start(owner, process_id)
    assert response.status_code == 303 and response.headers["location"].startswith("/jobs/")
    assert count(app, "SELECT status FROM jobs") == "queued"
    assert count(app, "SELECT claim_set FROM jobs") == "openrouter-some-model"
    assert count(app, "SELECT status FROM processes WHERE id = :i", i=process_id) == "extracting"
    assert count(app, "SELECT count(*) FROM audit_log WHERE action = 'extraction_queued'") == 1


@pytest.mark.parametrize(
    "overrides",
    [
        {"provider": "deepseek"},
        {"provider": "anthropic"},
        {"provider": "nonsense"},
        {"model": ""},
        {"model": "bad model!"},
        {"max_tokens": "5"},
        {"max_tokens": "99999999"},
    ],
)
def test_a_run_that_breaks_the_rules_is_refused_and_nothing_is_queued(owner, app, overrides):
    process_id = make_process(owner, make_client(owner, sensitivity="sensitive"))
    assert start(owner, process_id, **overrides).status_code == 400
    assert count(app, "SELECT count(*) FROM jobs") == 0


def test_only_one_run_at_a_time_per_process(owner, app):
    process_id = make_process(owner, make_client(owner))
    start(owner, process_id)
    assert start(owner, process_id).status_code == 400 and count(app, "SELECT count(*) FROM jobs") == 1


def test_a_second_run_with_the_same_model_gets_its_own_claim_set(owner, app):
    process_id = make_process(owner, make_client(owner))
    start(owner, process_id)
    with app.state.engine.begin() as connection:
        connection.execute(text("UPDATE jobs SET status = 'done'"))
    start(owner, process_id)
    with app.state.engine.connect() as connection:
        names = sorted(r[0] for r in connection.execute(text("SELECT claim_set FROM jobs")))
    assert names == ["openrouter-some-model", "openrouter-some-model-2"]


def test_nobody_else_can_start_a_run_on_my_process(browser, app, make_user):
    make_user()
    make_user("other@example.com")
    log_in(browser)
    process_id = make_process(browser, make_client(browser))
    intruder = new_browser(app)
    log_in(intruder, email="other@example.com")
    assert start(intruder, process_id).status_code == 404 and count(app, "SELECT count(*) FROM jobs") == 0


# ---- the job page ---------------------------------------------------------------------------------


def test_the_job_page_and_its_status_feed(owner):
    process_id = make_process(owner, make_client(owner))
    job_url = start(owner, process_id).headers["location"]
    page = owner.get(job_url)
    assert page.status_code == 200 and "queued" in page.text and "Cancel run" in page.text
    feed = owner.get(f"{job_url}/status").json()
    assert feed["status"] == "queued" and feed["is_finished"] is False and feed["max_tokens"] == 200000
    assert owner.get(f"{job_url}/status").headers["cache-control"] == "no-store"


def test_cancelling_sets_the_flag_and_is_audited(owner, app):
    job_url = start(owner, make_process(owner, make_client(owner))).headers["location"]
    assert owner.post(f"{job_url}/cancel").status_code == 303
    assert count(app, "SELECT is_cancel_requested FROM jobs") is True
    assert count(app, "SELECT count(*) FROM audit_log WHERE action = 'extraction_cancel_requested'") == 1


def test_another_user_cannot_see_or_cancel_my_job(browser, app, make_user):
    make_user()
    make_user("other@example.com")
    log_in(browser)
    job_url = start(browser, make_process(browser, make_client(browser))).headers["location"]
    intruder = new_browser(app)
    log_in(intruder, email="other@example.com")
    assert intruder.get(job_url, headers={"Accept": "text/html"}).status_code == 404
    assert intruder.get(f"{job_url}/status").status_code == 404
    assert intruder.post(f"{job_url}/cancel").status_code == 404
    assert count(app, "SELECT is_cancel_requested FROM jobs") is False


# ---- deleting ------------------------------------------------------------------------------------


def test_deleting_a_process_needs_the_password_and_the_word_and_removes_everything(owner, app):
    process_id = make_process(owner, make_client(owner))
    start(owner, process_id)
    assert (
        owner.get(f"/processes/{process_id}/delete").status_code == 200
        and count(app, "SELECT count(*) FROM processes") == 1
    )
    for password, word in (("wrong password here", "DELETE"), (DEFAULT_PASSWORD, "delete")):
        assert (
            owner.post(
                f"/processes/{process_id}/delete", data={"password": password, "confirmation": word}
            ).status_code
            == 400
        )
    assert count(app, "SELECT count(*) FROM processes") == 1
    assert (
        owner.post(
            f"/processes/{process_id}/delete", data={"password": DEFAULT_PASSWORD, "confirmation": "DELETE"}
        ).status_code
        == 303
    )
    for table in ("processes", "transcripts", "jobs"):
        assert count(app, f"SELECT count(*) FROM {table}") == 0, table


def test_deleting_a_client_removes_all_its_processes(owner, app):
    client_id = make_client(owner)
    make_process(owner, client_id)
    done = owner.post(
        f"/clients/{client_id}/delete", data={"password": DEFAULT_PASSWORD, "confirmation": "DELETE"}
    )
    assert done.status_code == 303
    assert (
        count(app, "SELECT count(*) FROM clients") == 0
        and count(app, "SELECT count(*) FROM transcripts") == 0
    )


def test_deletions_are_audited_including_the_refused_ones(owner, app):
    client_id = make_client(owner)
    owner.post(
        f"/clients/{client_id}/delete", data={"password": "nope nope nope nope", "confirmation": "DELETE"}
    )
    owner.post(f"/clients/{client_id}/delete", data={"password": DEFAULT_PASSWORD, "confirmation": "DELETE"})
    with app.state.engine.connect() as connection:
        outcomes = [
            r[0]
            for r in connection.execute(
                text("SELECT outcome FROM audit_log WHERE action = 'client_delete' ORDER BY id")
            )
        ]
    assert outcomes == ["rejected", "success"]


def test_every_workbench_page_needs_a_session(browser):
    for path in ("/clients/new", "/jobs/00000000-0000-0000-0000-000000000000"):
        assert browser.get(path).status_code == 303, path
    assert browser.post("/clients", data={"name": "x"}).status_code == 303


# ---- the whole journey ----------------------------------------------------------------------------


def test_upload_run_and_view_end_to_end(owner, app, monkeypatch):
    provider = FakeProvider()
    original = httpx.Client
    monkeypatch.setattr(
        "httpx.Client", lambda *args, **kwargs: original(transport=httpx.MockTransport(provider))
    )
    process_id = make_process(owner, make_client(owner))
    job_url = start(owner, process_id).headers["location"]

    assert work_once(app.state.engine, ENVIRONMENT, CurrentJob()) is True

    state = owner.get(f"{job_url}/status").json()
    assert state["status"] == "done" and state["is_finished"] and state["tokens_in"] == 300
    page = owner.get(f"/processes/{process_id}").text
    assert "analysed" in page and "openrouter-some-model" in page and "Interviews" in page
    for tab in ("timeline", "delay", "fractures", "evidence"):
        assert owner.get(f"/processes/{process_id}?tab={tab}").status_code == 200, tab
    evidence = owner.get(f"/processes/{process_id}?tab=evidence").text
    assert "Boris" in evidence and "waiting for Boris" in evidence
    for name in ("Anna", "Boris", "Clara", "Brauhaus", "Hopfenstrasse"):
        assert name not in provider.wire_text, name
    assert SITE
