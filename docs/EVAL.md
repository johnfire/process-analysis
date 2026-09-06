# Eval: testing the analyzer against synthetic processes

Status: draft 1, 2026-09-06. Companion to [PHILOSOPHY.md](PHILOSOPHY.md) and
[CAPTURE.md](CAPTURE.md).

---

## Why synthetic, and what it buys

We have no real multi-respondent process to test against. A solo operation cannot exercise the
two instruments the method actually turns on — the queue-gap calculation needs two accounts
either side of a handoff, and contradiction detection needs accounts that disagree. Waiting for a
willing organisation before writing any analysis code would stall the project indefinitely.

Synthetic processes solve this, and they buy something a real subject never could: **a known
answer key.** With a real company you can build a plausible map and never learn whether it was
right. With a generated process you know exactly where the bottleneck is, exactly which approval
is a ritual, and exactly which complaint is a red herring — so "did the analyzer find it" becomes
a measurement rather than an opinion.

---

## The central rule: two-stage generation

**Generate ground truth first. Generate testimony from it. Never generate testimony directly.**

**Stage 1 — the hidden process.** A generator builds the *actual* process as a structured object:
steps, real durations, real queues, real handoffs, ownership, systems of record, which approvals
are substantive and which are ritual, where volume leaves the happy path. This object is the
answer key and is never shown to the analyzer.

**Stage 2 — the testimony.** For each person in the cast, generate what that person would
actually say in an interview, derived from *their slice* of the ground truth and nothing more. A
warehouse supervisor does not know what finance does with the document after it leaves them, and
their account must reflect that ignorance.

If testimony is generated directly, there is no answer key, and every eval degrades into "does
the output look plausible" — which is exactly the failure mode this project exists to criticise
in other people's AI pilots.

---

## Ground truth schema (sketch)

Per process: a cast (role, seniority, tenure, disposition), and an ordered set of steps carrying
at minimum —

- `touch_time` and `elapsed_time`, separately
- `queue_before`, and crucially `queue_owner: internal | external`
- `handoff_from` / `handoff_to`
- `systems_touched`, and `precedence` when two disagree
- `exception_rate` and where exceptions go
- `decision`: the rule if one exists, `reversible`, `consequence_bearer`
- `true_classification`: deterministic / model / human — the label the analyzer must recover
- `constraint`: which of the eight fossils this step encodes, and whether it still binds

### Internal vs external queues

A modelling requirement that fell out of considering customer acquisition as a domain, and which
generalises: **not all waiting is ours to delete.** A prospect taking three weeks to reply is a
real queue that no redesign collapses. If the model does not distinguish `queue_owner: internal`
from `external`, the analyzer will correctly identify the largest wait in a sales process and then
have nothing to propose — or worse, propose something fatuous.

Every generated process must contain both kinds, and the analyzer is scored on separating them.
Getting the *total* elapsed time right while attributing an external wait to an internal cause is
a failure, not a partial credit.

---

## Testimony realism

The dominant failure mode of generated interview data is that model-written witnesses are far too
coherent. Real answers are vague, internally inconsistent, confidently wrong about numbers, and
evasive in specific directions. A dataset of articulate consistent witnesses tests nothing,
because the entire method is about extracting signal from degraded testimony.

The cast generator must be explicitly instructed to produce:

- **Wrong estimates** — people misjudge elapsed time badly, usually underestimating their own
  step's queue and overestimating everyone else's.
- **Vagueness and deferral** — "I don't really know, you'd have to ask Sabine."
- **Blame direction** — friction questions point outward by design; the cast should point outward.
- **Defensiveness on their own step**, in proportion to their perceived job risk.
- **Internal inconsistency** — the same person giving two different numbers ten minutes apart.
- **Silence about the normalised** — steps a person has fully internalised should simply not be
  mentioned unless directly probed.

---

## Planted decoys

Where the eval earns its keep. Each generated process carries deliberately planted structures,
each targeting a specific known weakness of the method:

| Planted structure | Tests |
|---|---|
| **Loud cheap step** — universally complained about, negligible cost | Complaint-bias correction. Do we correctly *ignore* it? |
| **Silent expensive wait** — days long, nobody mentions it, it's been normalised | Can we find what generates no pain signal? |
| **False blame claim** — A says "waiting on legal", legal never received it | Triangulation. Is the claim held as hypothesis until confirmed? |
| **Ritual approval** — an approver who has never once rejected anything | The probe with no pain signal (CAPTURE.md) |
| **Non-AI fix** — the largest single win is structural, not intelligence | Can we emit `NOT-AN-AI-PROBLEM`? |
| **External queue** — the biggest wait belongs to a customer or a bank | Do we separate their queue from ours? |
| **Genuine judgment step** — irreversible, high blast radius, no written rule | Do we correctly leave a human in place rather than automating? |

The last one matters as much as the rest. An analyzer that recommends automating everything
scores well on the first six and is still wrong.

---

## Scoring

Applying our own rule to ourselves: **deterministic code wherever a rule can be written; a model
only where genuine judgment is needed.** Most of these checks are arithmetic, not judgment, and
should never touch an LLM.

Deterministic:

- Rank correlation between estimated and true queue durations
- Was the true top bottleneck ranked first
- Planted contradictions detected / missed / invented (precision and recall)
- Ritual approval identified: yes/no
- Step classification vs `true_classification` — confusion matrix, with
  *automated-something-that-should-be-human* weighted far more heavily than the reverse
- Internal vs external queue attribution accuracy
- Decoy resistance: did the loud cheap step appear in the top findings

Model-judged, and only these:

- Quality and specificity of the proposed redesign
- Whether the stated reason for a finding matches its actual evidence

**Independence requirement.** The model that generates a process must not be the model that
scores it, and neither should share a family with the analyzer where avoidable. This is our own
correlated-verification-failure rule (PHILOSOPHY.md §6) applied to our own harness: a checker
that fails the same way as the doer is not a checker.

---

## Roles

The suite is multi-model and multi-role by construction, with strict information barriers:

| Role | Sees | Never sees |
|---|---|---|
| **Architect** — builds hidden ground truth | Domain brief, decoy spec | Our method; the analyzer |
| **Cast** — one instance per persona, writes testimony | Only that persona's slice | Full ground truth; other personas' accounts; our method |
| **Analyzer** — our pipeline | Testimony only | Ground truth |
| **Scorer** — mostly code, model only where noted | Ground truth + analyzer output | Testimony generation prompts |

**The generator must never be handed our method.** No constraint archaeology, no eight
constraints, no lever ladder. Give it the domain, the cast, and the decoy spec in neutral
language. Otherwise the dataset is shaped like our solution and we are marking our own homework.

Use more than one model family for generation, or every synthetic office inherits one model's
idea of what an office looks like.

---

## The honest limit

**Synthetic data validates the analyzer. It cannot validate the interviewer.**

A generated respondent answers our questions honestly by construction, because the model was told
to. It tells us nothing about whether a real person, whose job may be at stake, answers "has an
approver ever actually said no?" straight or with a flinch. It cannot test whether the framing
rule from CAPTURE.md actually lowers the threat level, because a synthetic witness was never
threatened.

So: **synthetic proves the reasoning; only a real subject proves the elicitation.** Worth holding
onto, because passing this suite will feel like the method works, and it will only mean half of
it does.

---

## CI

The suite runs from the first push, per house standards. A fixed seed corpus of generated
processes is committed; regeneration is a separate deliberate act, so that scores are comparable
across commits and a change in score means a change in the analyzer rather than a change in the
weather.
