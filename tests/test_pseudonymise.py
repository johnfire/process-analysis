"""What leaves the server must not name anyone, and what comes back must be exact."""

from __future__ import annotations

import pytest

from analyzer.pseudonymise import (
    PersonToHide,
    aliases_of,
    original_quote,
    pseudonymise,
    restore_tokens,
)

PEOPLE = [PersonToHide(1, "Katrin Weber"), PersonToHide(2, "Dr. Elena Vidal"), PersonToHide(3, "Petra Lang")]
TRANSCRIPT = (
    "**Interviewer:** Who do you wait for?\n\n"
    "**Katrin Weber:** I wait for Petra to sign. Petra Lang is slow on Fridays, and Dr. Vidal even more so. "
    "Write to katrin.weber@suedmark.example or ring +49 8234 123456. "
    "Elena will say it is Suedmark Kliniken's fault, "
    "see https://suedmark.example/intranet."
)


def hidden(text=TRANSCRIPT, extra=None):
    return pseudonymise(text, PEOPLE, extra or ["Suedmark Kliniken"])


def test_no_listed_name_survives():
    shown = hidden().text
    for forbidden in ("Katrin", "Weber", "Petra", "Lang", "Vidal", "Elena", "Suedmark", "katrin.weber"):
        assert forbidden not in shown, forbidden


def test_every_form_of_a_name_maps_to_the_same_person():
    shown = hidden().text
    assert shown.count("PERSON_3") == 2  # "Petra" and "Petra Lang"
    assert shown.count("PERSON_2") == 2  # "Dr. Vidal" and "Elena"
    assert "**PERSON_1:**" in shown


def test_emails_phone_numbers_and_web_addresses_become_numbered_tokens():
    shown = hidden().text
    assert "EMAIL_1" in shown and "PHONE_1" in shown and "URL_1" in shown
    assert "+49" not in shown and "https://" not in shown


def test_the_same_email_gets_the_same_token_and_a_different_one_a_new_token():
    shown = pseudonymise("a@x.de then a@x.de then b@x.de", []).text
    assert shown == "EMAIL_1 then EMAIL_1 then EMAIL_2"


def test_matching_is_case_insensitive_and_whole_word_only():
    shown = pseudonymise("KATRIN spoke. Katrinas hat is not hers.", PEOPLE).text
    assert shown.startswith("PERSON_1 spoke.") and "Katrinas" in shown


def test_short_fragments_are_not_treated_as_aliases():
    assert all(len(alias) >= 3 for alias in aliases_of("Jo Li"))
    assert pseudonymise("Jo said hi", [PersonToHide(1, "Jo Li")]).text == "Jo said hi"


def test_a_title_is_not_an_alias_on_its_own():
    assert "Dr." not in aliases_of("Dr. Elena Vidal") and "Dr. Vidal" in aliases_of("Dr. Elena Vidal")


def test_text_with_nothing_to_hide_is_unchanged():
    assert pseudonymise("We wait on the batch.", PEOPLE).text == "We wait on the batch."


def test_tokens_restore_to_canonical_values():
    result = hidden()
    restored = restore_tokens(result.text, result.token_values)
    assert (
        "Katrin Weber" in restored
        and "Suedmark Kliniken" in restored
        and "katrin.weber@suedmark.example" in restored
    )


def test_a_token_the_model_invented_is_left_alone():
    assert restore_tokens("PERSON_99 said", hidden().token_values) == "PERSON_99 said"


def test_a_quote_comes_back_in_the_original_words_whatever_name_form_was_spoken():
    result = hidden()
    assert original_quote(TRANSCRIPT, result, "I wait for PERSON_3 to sign.") == "I wait for Petra to sign."
    assert (
        original_quote(TRANSCRIPT, result, "PERSON_3 is slow on Fridays") == "Petra Lang is slow on Fridays"
    )
    assert original_quote(TRANSCRIPT, result, "and PERSON_2 even more so") == "and Dr. Vidal even more so"


def test_a_quote_that_starts_or_ends_inside_a_token_snaps_to_the_whole_name():
    result = hidden()
    assert original_quote(TRANSCRIPT, result, "ERSON_3 to sign") == "Petra to sign"


def test_typographic_quotes_and_case_are_tolerated_but_invented_words_are_not():
    text = "Tom’s queue is long."
    result = pseudonymise(text, [])
    assert original_quote(text, result, "tom's queue is long") == text.rstrip(".")
    assert original_quote(text, result, "Tom's queue is short") is None


def test_an_empty_or_missing_quote_is_refused():
    assert original_quote(TRANSCRIPT, hidden(), "") is None
    assert original_quote(TRANSCRIPT, hidden(), "never said this at all") is None


def test_offsets_after_many_replacements_still_line_up():
    text = " ".join(["Petra Lang waits."] * 50) + " The final sentence is plain."
    result = pseudonymise(text, PEOPLE)
    assert original_quote(text, result, "The final sentence is plain.") == "The final sentence is plain."


def test_leftover_capitalised_words_are_reported_for_a_human_to_review():
    result = pseudonymise("We asked Brigitte and then Brigitte again. Monday was quiet.", [])
    assert ("Brigitte", 2) in result.leftovers and all(word != "Monday" for word, _ in result.leftovers)


@pytest.mark.parametrize("text", ["", "   ", "no names here"])
def test_degenerate_input_does_not_crash(text):
    assert pseudonymise(text, PEOPLE).text == text


def test_numeric_ranges_and_dates_that_are_not_phone_numbers_survive():
    text = "It takes 100 - 200 minutes, sometimes 2.5 days, and the 3 / 4 cases."
    assert pseudonymise(text, []).text == text


def test_a_real_phone_number_is_still_hidden():
    assert pseudonymise("ring 08234 / 123 456 please", []).text == "ring PHONE_1 please"


def test_line_breaks_and_extra_spaces_in_a_quote_do_not_prevent_a_match():
    text = "She said that\nthe batch  runs\n\non Thursday only."
    result = pseudonymise(text, [])
    assert original_quote(text, result, "the batch runs on Thursday") == "the batch  runs\n\non Thursday"
