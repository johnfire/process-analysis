"""The privacy-preserving extraction pipeline, with a fake model standing in for the provider."""

from __future__ import annotations

import json

import pytest

from analyzer.private_extraction import RespondentDetails, extract_privately
from analyzer.pseudonymise import PersonToHide

PEOPLE = [PersonToHide(1, "Katrin Weber"), PersonToHide(2, "Petra Lang")]
RESPONDENT = RespondentDetails("katrin-weber", "Katrin Weber", "HR Coordinator at Suedmark Kliniken", 1)
TRANSCRIPT = (
    "**Interviewer:** What are you waiting on?\n\n"
    "**Katrin Weber:** I am waiting for Petra to tell me who is supervising the new starter. "
    "It usually takes about two days."
)


DURATION_PAYLOAD = {
    "measure": "queue",
    "value": {"low": 2, "high": 2, "unit": "day"},
    "subject": "the supervision answer",
    "basis": "typical",
}


def claim(**overrides):
    base = {
        "id": "respondent-001",
        "respondent_id": "respondent",
        "session_id": "session",
        "captured_at": "2000-01-01T00:00:00Z",
        "kind": "wait",
        "hedging": "firm",
        "polarity": "asserted",
        "subject_scope": "self",
        "verbatim": "I am waiting for PERSON_2 to tell me who is supervising the new starter.",
        "entity_refs": [{"text": "PERSON_2", "type": "actor", "role": "waiting_on"}],
        "payload": {
            "waiting_on": "PERSON_2 (supervision)",
            "owner": "internal",
            "current": True,
            "duration": None,
        },
    }
    return {**base, **overrides}


class RecordingModel:
    def __init__(self, reply):
        self.reply = reply
        self.prompts: list[str] = []

    def __call__(self, prompt: str) -> str:
        self.prompts.append(prompt)
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


def run(reply, **kwargs):
    model = RecordingModel(reply)
    result = extract_privately(model, TRANSCRIPT, RESPONDENT, PEOPLE, ["Suedmark Kliniken"], **kwargs)
    return model, result


def test_the_prompt_the_provider_receives_contains_no_listed_name():
    model, _ = run([claim()])
    sent = model.prompts[0]
    for forbidden in ("Katrin", "Weber", "Petra", "Lang", "Suedmark", "katrin-weber"):
        assert forbidden not in sent, forbidden
    assert "PERSON_1" in sent and "PERSON_2" in sent


def test_a_grounded_claim_comes_back_with_real_names_and_the_original_wording():
    _, result = run([claim()])
    [kept] = result.claims
    assert kept["verbatim"] == "I am waiting for Petra to tell me who is supervising the new starter."
    assert kept["entity_refs"][0]["text"] == "Petra Lang"
    assert kept["payload"]["waiting_on"] == "Petra Lang (supervision)"


def test_ids_respondent_and_session_are_ours_not_the_models():
    _, result = run(
        [
            claim(id="whatever", respondent_id="liar"),
            claim(
                id="x2",
                verbatim="It usually takes about two days.",
                kind="duration",
                payload=DURATION_PAYLOAD,
                entity_refs=[],
            ),
        ]
    )
    assert [c["id"] for c in result.claims] == ["katrin-weber-001", "katrin-weber-002"]
    assert {c["respondent_id"] for c in result.claims} == {"katrin-weber"}
    assert {c["session_id"] for c in result.claims} == {"s-katrin-weber"}


def test_a_claim_quoting_words_nobody_said_is_dropped_and_counted():
    _, result = run([claim(), claim(id="r2", verbatim="Petra is hopeless and always late.")])
    assert len(result.claims) == 1 and result.ungrounded_count == 1
    assert result.grounding_rate == pytest.approx(0.5)


def test_a_schema_invalid_claim_is_dropped_with_its_reason():
    _, result = run([claim(), claim(id="r2", kind="not-a-kind")])
    assert len(result.claims) == 1 and len(result.invalid) == 1


def test_supersedes_pointers_follow_the_renumbering():
    first = claim(id="a")
    second = claim(
        id="b",
        supersedes="a",
        verbatim="It usually takes about two days.",
        kind="duration",
        payload=DURATION_PAYLOAD,
        entity_refs=[],
    )
    _, result = run([first, second])
    assert result.claims[1]["supersedes"] == "katrin-weber-001"


def test_a_reply_with_no_json_raises_so_the_caller_can_record_the_failure():
    with pytest.raises(ValueError):
        run("I am sorry, I cannot help with that.")


def test_a_fenced_reply_is_understood():
    _, result = run("Here you go:\n```json\n" + json.dumps([claim()]) + "\n```")
    assert len(result.claims) == 1


def test_non_object_items_in_the_array_are_ignored():
    _, result = run(["nonsense", 3, claim()])
    assert len(result.claims) == 1
