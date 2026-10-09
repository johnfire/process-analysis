from __future__ import annotations

from web.upload_parsing import MAX_TRANSCRIPT_CHARACTERS, parse_respondents, parse_terms, slugify, unique_key


def form(**fields):
    return fields


def test_slugs_are_ascii_and_stable():
    assert slugify("Dr. Elena Vidal") == "dr-elena-vidal"
    assert slugify("Jürgen Müller-Lüdenscheidt") == "jurgen-muller-ludenscheidt"
    assert slugify("???") == "respondent"


def test_duplicate_names_get_distinct_keys():
    assert unique_key("anna", {"anna"}) == "anna-2"
    assert unique_key("anna", {"anna", "anna-2"}) == "anna-3"


def test_complete_rows_become_respondents_and_blank_rows_are_ignored():
    parsed = parse_respondents(
        form(name_0="Anna Schmidt", role_0="Clerk", text_0="  I wait.  ", name_1="", role_1="", text_1=""), {}
    )
    assert parsed.errors == []
    [one] = parsed.respondents
    assert (one.person_key, one.name, one.role, one.transcript) == (
        "anna-schmidt",
        "Anna Schmidt",
        "Clerk",
        "I wait.",
    )


def test_two_people_with_the_same_name_do_not_collide():
    parsed = parse_respondents(
        form(name_0="Anna", role_0="a", text_0="x", name_1="Anna", role_1="b", text_1="y"), {}
    )
    assert [r.person_key for r in parsed.respondents] == ["anna", "anna-2"]


def test_an_uploaded_file_wins_over_pasted_text():
    parsed = parse_respondents(form(name_0="A B", role_0="r", text_0="pasted"), {0: b"from the file"})
    assert parsed.respondents[0].transcript == "from the file"


def test_a_byte_order_mark_is_stripped():
    parsed = parse_respondents(form(name_0="A B", role_0="r"), {0: "﻿hello".encode()})
    assert parsed.respondents[0].transcript == "hello"


def test_a_file_that_is_not_text_is_reported():
    parsed = parse_respondents(form(name_0="A B", role_0="r"), {0: b"\xff\xfe\x00bad"})
    assert parsed.respondents == [] and "UTF-8" in parsed.errors[0]


def test_a_missing_name_role_or_transcript_is_reported_by_row_number():
    assert (
        "Row 1: enter the respondent's name" in parse_respondents(form(role_0="r", text_0="x"), {}).errors[0]
    )
    assert "enter their role" in parse_respondents(form(name_0="n", text_0="x"), {}).errors[0]
    assert "paste or upload" in parse_respondents(form(name_0="n", role_0="r"), {}).errors[0]


def test_an_oversized_transcript_is_refused():
    parsed = parse_respondents(form(name_0="n", role_0="r", text_0="x" * (MAX_TRANSCRIPT_CHARACTERS + 1)), {})
    assert parsed.respondents == [] and "longer than" in parsed.errors[0]


def test_nothing_at_all_is_an_error():
    assert parse_respondents(form(), {}).errors == ["Add at least one interview transcript."]


def test_terms_are_trimmed_deduplicated_and_bounded():
    terms, errors = parse_terms("  Hopfenstrasse 12 \n\nhopfenstrasse 12\nProjekt Adler\n")
    assert terms == ["Hopfenstrasse 12", "Projekt Adler"] and errors == []
    assert parse_terms("\n".join(f"term {n}" for n in range(60)))[1]
    assert parse_terms("x" * 200)[1]
