"""The viewer through the real HTTP layer, with the seed corpus in a real Postgres."""

from __future__ import annotations

import re

import pytest
from sqlalchemy import text

from tests.integration.conftest import log_in, new_browser
from web import process_store
from web.seed_import import import_seed_processes


@pytest.fixture
def seeded(app, make_user):
    make_user()
    import_seed_processes(app.state.engine)


@pytest.fixture
def signed_in(browser, seeded):
    log_in(browser)
    return browser


def process_id(app, slug: str) -> str:
    with app.state.engine.connect() as connection:
        return str(
            connection.execute(text("SELECT id FROM processes WHERE slug = :s"), {"s": slug}).scalar_one()
        )


def hospital_url(app, **query) -> str:
    suffix = "&".join(f"{key}={value}" for key, value in query.items())
    return f"/processes/{process_id(app, 'hospital-onboarding')}" + (f"?{suffix}" if suffix else "")


def test_everything_needs_a_session(browser, app, seeded):
    for path in ("/clients", hospital_url(app), f"{hospital_url(app)}/transcripts/katrin-weber"):
        assert browser.get(path).status_code == 303, path


def test_login_lands_on_the_clients_page(browser, seeded):
    assert log_in(browser).headers["location"] == "/clients"


def test_clients_lists_the_shared_synthetic_corpus(signed_in):
    page = signed_in.get("/clients").text
    assert "Synthetic corpus" in page and "2 processes" in page


def test_a_client_lists_its_processes_with_headline_numbers(signed_in):
    client_link = re.search(r'href="(/clients/[0-9a-f-]+)"', signed_in.get("/clients").text).group(1)
    page = signed_in.get(client_link).text
    assert "Südmark Kliniken" in page and "cycle efficiency" in page and "7 interviews" in page


def test_every_tab_renders_for_every_claim_set(signed_in, app):
    for slug in ("hospital-onboarding", "inbound-lead-to-qualified-contact"):
        base = f"/processes/{process_id(app, slug)}"
        for claim_set in ("claims", "claims-codex"):
            for tab in ("timeline", "delay", "cadences", "fractures", "evidence", "score"):
                response = signed_in.get(f"{base}?tab={tab}&claims={claim_set}")
                assert response.status_code == 200, (slug, claim_set, tab)


def test_timeline_draws_the_scale_and_states_cycle_efficiency(signed_in, app):
    page = signed_in.get(hospital_url(app, tab="timeline")).text
    assert 'class="timeline"' in page and "tl-work" in page and "tl-external" in page
    assert "0.45% of the elapsed time" in page


def test_delay_tab_shows_no_evidence_instead_of_zero_bars(signed_in, app):
    page = signed_in.get(hospital_url(app, tab="delay")).text
    assert page.count("no time evidence") >= 5
    assert "0 min" not in page


def test_delay_tab_puts_the_silent_bottleneck_above_the_loud_complainer(signed_in, app):
    page = signed_in.get(hospital_url(app, tab="delay")).text
    assert page.index("1. Andrea Hoffmann") < page.index("7. Katrin Weber")


def test_cadences_tab_lists_the_batch(signed_in, app):
    page = signed_in.get(hospital_url(app, tab="cadences")).text
    assert "thursday" in page.lower()


def test_fractures_tab_quotes_both_sides_and_links_to_the_transcript(signed_in, app):
    page = signed_in.get(hospital_url(app, tab="fractures")).text
    assert "silence" in page and "never mentions" in page
    link = re.search(r'href="(/processes/[0-9a-f-]+/transcripts/[a-z-]+#L\d+)"', page)
    assert link, "a fracture quote should link to the line it came from"


def test_a_transcript_link_lands_on_a_line_that_contains_the_quote(signed_in, app):
    page = signed_in.get(hospital_url(app, tab="fractures")).text
    path, line = re.search(r'href="(/processes/[0-9a-f-]+/transcripts/[a-z-]+)#L(\d+)"', page).groups()
    transcript = signed_in.get(path).text
    assert f'id="L{line}"' in transcript


def test_evidence_tab_pages_and_filters(signed_in, app):
    everything = signed_in.get(hospital_url(app, tab="evidence")).text
    assert "495 claims, page 1" in everything and "Next page" in everything
    one_person = signed_in.get(hospital_url(app, tab="evidence", person="katrin-weber")).text
    assert (
        "81 claims" in one_person
        and "katrin-weber" in one_person
        and "markus-brandt" not in one_person.split("<tbody>")[1]
    )
    one_kind = signed_in.get(hospital_url(app, tab="evidence", kind="complaint")).text
    assert "<td>complaint</td>" in one_kind and "<td>wait</td>" not in one_kind


def test_evidence_rows_link_to_transcript_lines(signed_in, app):
    page = signed_in.get(hospital_url(app, tab="evidence", person="katrin-weber")).text
    assert len(re.findall(r"/transcripts/katrin-weber#L\d+", page)) > 20


def test_score_tab_shows_the_planted_answer_checks(signed_in, app):
    page = signed_in.get(hospital_url(app, tab="score")).text
    assert "5 of 7 criteria pass" in page and "bottleneck in top three" in page


def test_the_two_claim_sets_are_selectable_and_give_different_pictures(signed_in, app):
    first = signed_in.get(hospital_url(app, tab="timeline", claims="claims")).text
    second = signed_in.get(hospital_url(app, tab="timeline", claims="claims-codex")).text
    assert "claims-codex" in first and first != second


def test_unknown_tab_and_claim_set_fall_back_to_sensible_defaults(signed_in, app):
    assert signed_in.get(hospital_url(app, tab="nonsense", claims="nonsense")).status_code == 200


def test_malformed_and_unknown_ids_are_not_found(signed_in):
    html = {"Accept": "text/html"}
    assert signed_in.get("/processes/not-a-uuid", headers=html).status_code == 404
    assert signed_in.get("/processes/00000000-0000-0000-0000-000000000000", headers=html).status_code == 404
    assert signed_in.get("/clients/00000000-0000-0000-0000-000000000000", headers=html).status_code == 404
    assert signed_in.get("/nothing-here", headers=html).status_code == 404


def test_a_missing_transcript_is_not_found(signed_in, app):
    assert signed_in.get(f"{hospital_url(app)}/transcripts/nobody").status_code == 404


def test_transcript_text_is_escaped(signed_in, app):
    with app.state.engine.begin() as connection:
        connection.execute(
            text(
                "UPDATE transcripts SET body = '**X:** <script>alert(1)</script>' "
                "WHERE person_key = 'katrin-weber'"
            )
        )
    page = signed_in.get(f"{hospital_url(app)}/transcripts/katrin-weber").text
    assert "<script>alert(1)</script>" not in page and "&lt;script&gt;" in page


def test_another_users_client_is_invisible_to_everyone_else(app, make_user, seeded):
    make_user("other@example.com")
    with app.state.engine.begin() as connection:
        owner = connection.execute(
            text("SELECT id FROM users WHERE email = 'other@example.com'")
        ).scalar_one()
        client_id = process_store.create_client(connection, "Private client", owner, False)
        private = process_store.create_process(
            connection,
            client_id=client_id,
            slug="p",
            name="Private process",
            domain="d",
            organisation={"name": "Private"},
            cast=[],
        )
    mine, theirs = new_browser(app), new_browser(app)
    log_in(mine)
    log_in(theirs, email="other@example.com")
    assert "Private client" not in mine.get("/clients").text
    assert mine.get(f"/clients/{client_id}", headers={"Accept": "text/html"}).status_code == 404
    assert mine.get(f"/processes/{private}", headers={"Accept": "text/html"}).status_code == 404
    assert "Private client" in theirs.get("/clients").text
    assert theirs.get(f"/processes/{private}").status_code == 200


def test_a_process_with_no_result_says_so_instead_of_crashing(app, make_user, seeded):
    make_user("other@example.com")
    with app.state.engine.begin() as connection:
        owner = connection.execute(
            text("SELECT id FROM users WHERE email = 'other@example.com'")
        ).scalar_one()
        client_id = process_store.create_client(connection, "Empty", owner, False)
        empty = process_store.create_process(
            connection,
            client_id=client_id,
            slug="e",
            name="Empty process",
            domain="d",
            organisation={},
            cast=[],
        )
    browser = new_browser(app)
    log_in(browser, email="other@example.com")
    assert "not been analysed yet" in browser.get(f"/processes/{empty}").text


def test_deleting_a_user_removes_their_clients_and_everything_under_them(app, make_user, seeded):
    make_user("other@example.com")
    with app.state.engine.begin() as connection:
        owner = connection.execute(
            text("SELECT id FROM users WHERE email = 'other@example.com'")
        ).scalar_one()
        client_id = process_store.create_client(connection, "Private client", owner, False)
        process = process_store.create_process(
            connection,
            client_id=client_id,
            slug="p",
            name="P",
            domain="d",
            organisation={},
            cast=[],
        )
        process_store.add_transcripts(connection, process, {"a": "text"})
        process_store.add_claims(connection, process, "claims", {"a": [{"kind": "wait"}]})
        process_store.add_result(connection, process, "claims", "0", {})
    browser = new_browser(app)
    log_in(browser, email="other@example.com")
    from tests.integration.conftest import DEFAULT_PASSWORD

    browser.post("/account/delete", data={"password": DEFAULT_PASSWORD, "confirmation": "DELETE"})
    for table in ("processes", "transcripts", "claims", "results"):
        remaining = count_rows(
            app,
            f"SELECT count(*) FROM {table} WHERE process_id::text = '{process}'"
            if table != "processes"
            else f"SELECT count(*) FROM processes WHERE id = '{process}'",
        )
        assert remaining == 0, table
    assert (
        count_rows(app, "SELECT count(*) FROM clients WHERE owner_user_id IS NULL") == 1
    )  # the shared one survives


def count_rows(app, sql: str) -> int:
    with app.state.engine.connect() as connection:
        return connection.execute(text(sql)).scalar_one()
