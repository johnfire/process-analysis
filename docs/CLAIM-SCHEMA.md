# Claim schema

Status: draft 1, 2026-09-06. Normative artifact: [`schema/claim.schema.json`](../schema/claim.schema.json).
Fixtures: [`schema/examples.json`](../schema/examples.json). See [ARCHITECTURE.md](ARCHITECTURE.md)
for where claims sit.

A claim is one typed assertion, by one respondent, about a process. Claims are the only thing the
system ever writes; entities and the process graph are derived. This document explains the
decisions the schema encodes — the schema itself carries the field-level detail.

JSON Schema (draft 2020-12) is the normative form deliberately, rather than Python types: the
synthetic cast models in [EVAL.md](EVAL.md) must emit claim-shaped data too, and a portable
contract can be handed to a model of any family and used to validate what comes back.

---

## Decisions worth defending

### 1. Claims never store resolved entity IDs

Only raw mention strings — `"the intake form"`, `"that PDF thing"`. Resolution lives in a
separate, revisable layer. If a claim held an entity ID, then fixing a bad merge would mean
rewriting claims, and "claims are append-only" would be a lie. This is what makes correction
cheap: re-resolve and regenerate, and no evidence is touched.

### 2. Append-only, with `supersedes`

A correction is a new claim that supersedes an old one, never an edit. The audit trail is the
point: when someone in the room says *"that's not how it works"*, the answer must be a named
person and a verbatim sentence, and that must remain true after three rounds of revision.

### 3. `subject_scope` implements the triangulation rule

`self` · `direct_observation` · `hearsay`.

CAPTURE.md's rule — *any claim about someone else is a hypothesis, promoted only when that side's
own account confirms it* — needs a field to hang on, or it stays a good intention. Friction
questions point outward by design, so hearsay will be abundant, and a system that scores it as
fact produces the exact failure mode we identified: a map where every department is a victim and
none is a cause.

Hearsay is never scored as fact. Where a hearsay claim and the subject's own `self` claim
conflict, that is a **fracture**, and the fracture is the finding.

### 4. `polarity` — denials are first-class

*"No, he's never sent one back."*

That is the single most valuable answer the ritual-approval probe can produce, and it is a
denial. A schema that only models assertions cannot represent it, and the one reliable probe for
constraint #3 would have nowhere to land.

### 5. `hedging` is signal, not metadata

`firm` · `approximate` · `guessed` · `deferred` · `refused`.

"About two days, I think" and "two days" are different observations, and flattening them discards
the confidence model. Two of these do specific work:

- **`deferred`** — *"you'd have to ask Sabine"* — discovers cast members we haven't interviewed,
  and drives who to talk to next.
- **`refused`** — declining to answer is data. Someone who won't say how long their step takes
  has told us something about the step.

### 6. Durations are ranges, not points

People say *"a couple of days"*. Recording that as `2` fabricates precision the respondent never
had, and the fabricated precision then propagates into every derived metric wearing a false air
of authority. `{low, high, unit}` throughout.

### 7. `measure` separates touch, elapsed and queue — and `basis` separates typical from anecdote

Conflating touch time with elapsed time is the single most common error in process data, and the
entire method turns on the gap between them. They are different enum values, not a convention.

`basis` distinguishes *"usually two days"* from *"the last one took three weeks"*. Worst-case
anecdotes are not noise to be averaged out — they are usually exception-path evidence, and
sometimes the most useful thing in the transcript.

### 8. `question_id` makes the question bank empirical

Every claim records which probe elicited it. Over a few processes that yields the yield: which
questions actually produce structural claims, and which produce only complaints. CAPTURE.md's
question bank was designed by argument; this is how it stops being designed by argument.

### 9. Complaints are captured precisely so we can prove we ignore them

Findings rank by `volume × elapsed`, never by intensity or frequency of mention, and EVAL.md
plants a loud-cheap-step decoy specifically to test that. But we cannot *demonstrate* the decoy
was resisted unless the decoy was recorded in the first place. Complaints are also the answers
that build the only rapport this method needs, so they arrive whether we model them or not.

### 10. Fifteen kinds, and why not fewer

`step` `handoff` `artifact` `system` `actor` · `duration` `wait` `schedule` · `rule` `approval`
`exception` `consequence` · `complaint` `rework` `workaround`

Each maps to a specific extraction target in CAPTURE.md and a specific scored quantity in
EVAL.md. The pairs that look mergeable are not:

- **`system` vs `artifact`** — a system is a place, an artifact is a thing that moves. Systems
  answer the precedence question; artifacts trace the flow.
- **`schedule` vs `duration`** — a schedule is a *cause* of queue (constraint #1); a duration is a
  *measure* of it. Merging them loses the causal link that makes the queue deletable.
- **`rework` vs `exception`** — rework travels backward to an earlier step; an exception travels
  forward on a different path. Topologically different, and they imply different fixes.
- **`workaround` vs `complaint`** — a complaint is affect; a workaround is evidence of a missing
  capability. The shadow spreadsheet is a fact about the system, not a feeling about it.

Extraction reliability is the cost of fifteen kinds. Mitigation is a two-stage classify — family
first, then kind within family — which is materially more reliable than a flat fifteen-way choice.

---

## What the schema deliberately does not do

**No ordering. No sequence. No graph.** A claim asserts what one person said; it never asserts
where a step sits in the process. Order is *derived* at the graph layer from handoff claims, and
it must stay derived — the moment a claim carries a step index, one respondent's mental model has
been silently promoted to the truth, and the whole evidence-graph design collapses back into an
authored diagram.

**No confidence score on the claim.** Confidence is a property of a *node in the graph* —
computed from how many respondents assert it, how firmly, and at what `subject_scope`. A single
claim has `hedging`, which is an observation. It does not have a probability, which would be a
conclusion.

---

## Amendment: `subject_scope` is a hint, not the triangulation mechanism

Found while extracting the false-blame holder's transcript from the first corpus. Rainer
sincerely believes Petra is blocking him. Extraction captured that belief correctly — `wait`
with `waiting_on: "Petra"`, `handoff` "Petra gets chased", `rework` "Petra's information kept
changing" — and scoped every one of them `self`.

That scoping is defensible, which is the problem. "I'm waiting on Petra" asserts two things with
different epistemic status: *I am waiting*, which he knows directly, and *Petra is the cause*,
which he is inferring. `subject_scope` is a single label over a whole claim and cannot express
the split, so an extractor choosing `self` is not making an error — it is answering an ambiguous
question, and a different model would answer it differently on a different day.

Triangulation therefore does **not** depend on `subject_scope`. It derives from whether the
payload names a party other than the respondent — a rule, evaluated in code, in
`analyzer/triangulation.py`. `subject_scope` remains a useful signal about the respondent's own
stance; it is simply not what the fracture detector keys off.

This is the deterministic-first principle catching a design error rather than an implementation
one: we had made the most important structural decision in the pipeline contingent on a model's
judgment about a genuinely ambiguous question, when a rule was available. Had we shipped it, the
fracture detector would have failed silently and intermittently, which is the worst possible
failure mode for a measurement instrument.

Note the returned counterparties are *candidates*, not resolved actors — `waiting_on` names a
thing ("an answer", "availability information") as readily as a person, and separating them is
entity resolution's job. Guessing at that boundary here would bury an unreviewable judgment
inside a function whose entire value is being a rule.

## Open

- **Do we score claim extraction independently, or only end to end?** Ground truth in EVAL.md is a
  process, not a claim set, so extraction is currently only measurable through its effect on
  reconstruction. Current lean: end-to-end as the primary score, plus a small hand-labelled claim
  set as a regression tier so an extraction regression is attributable rather than mysterious.
- **`entity_refs` vs payload strings.** Several payloads carry mention text directly
  (`handoff.from`, `wait.waiting_on`) *and* the claim carries `entity_refs`. That redundancy is
  currently deliberate — payloads stay readable, `entity_refs` stays uniformly walkable for the
  resolver — but it is a normalisation smell and should be revisited once the resolver exists.
