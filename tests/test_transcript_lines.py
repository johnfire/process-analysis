from __future__ import annotations

from web.transcript_lines import bold_markup_to_html, locate_quote, transcript_lines

BODY = (
    "**Interviewer:** What are you waiting on?\n"
    "\n"
    "**Anna:** I’m waiting on Petra’s sign-off, and it can take “a couple of days” at best.\n"
    "\n"
    "**Anna:** Then the batch runs on Thursday.\n"
)


def test_non_empty_lines_keep_their_file_line_numbers():
    assert [line.number for line in transcript_lines(BODY)] == [1, 3, 5]


def test_a_quote_is_found_on_its_line():
    assert locate_quote(BODY, "the batch runs on Thursday") == 5


def test_typographic_quotes_and_dashes_do_not_prevent_a_match():
    assert locate_quote(BODY, "I'm waiting on Petra's sign-off") == 3
    assert locate_quote(BODY, 'a couple of days" at best') == 3


def test_case_and_spacing_are_ignored():
    assert locate_quote(BODY, "THE  BATCH   RUNS on thursday") == 5


def test_a_quote_that_is_not_there_gives_none():
    assert locate_quote(BODY, "something never said in this interview at all") is None
    assert locate_quote(BODY, "") is None


def test_a_long_quote_that_drifts_late_still_matches_on_its_opening():
    drifted = (
        "I'm waiting on Petra's sign-off, and it can take a couple of days at best, I paraphrase the end"
    )
    assert locate_quote(BODY, drifted) == 3


def test_bold_markers_become_strong_tags():
    assert bold_markup_to_html("**Anna:** hello") == "<strong>Anna:</strong> hello"
