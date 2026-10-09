from __future__ import annotations

from web.extraction_preview import build_preview, estimate_tokens

CAST = [
    {"person_id": "anna", "name": "Anna Schmidt", "role": "r"},
    {"person_id": "boris", "name": "Boris Keller", "role": "r"},
]
TRANSCRIPTS = {
    "anna": "**Anna Schmidt:** I wait for Boris. Brigitte at Hopfen GmbH calls me.",
    "boris": "**Boris Keller:** Anna is fine. Brigitte is the problem.",
}


def test_the_sample_is_what_the_provider_would_see():
    preview = build_preview(CAST, TRANSCRIPTS, ["Hopfen GmbH"])
    assert "PERSON_1" in preview.sample and "Anna" not in preview.sample and "Hopfen" not in preview.sample


def test_replacements_are_counted_across_all_transcripts():
    assert (
        build_preview(CAST, TRANSCRIPTS, ["Hopfen GmbH"]).replacement_count == 5
    )  # 3 in the first interview, 2 in the second


def test_an_unlisted_name_is_surfaced_for_review():
    preview = build_preview(CAST, TRANSCRIPTS, [])
    assert ("Brigitte", 2) in preview.leftovers


def test_listing_the_name_removes_it_from_the_review_list():
    preview = build_preview(CAST, TRANSCRIPTS, ["Brigitte"])
    assert all(word != "Brigitte" for word, _ in preview.leftovers)


def test_no_transcripts_means_no_preview():
    assert build_preview(CAST, {}, []) is None


def test_the_estimate_grows_with_the_transcripts_and_includes_the_fixed_prompt():
    small, large = estimate_tokens(["x" * 350]), estimate_tokens(["x" * 3500])
    assert large[0] > small[0] > 3000 and large[1] > small[1]
