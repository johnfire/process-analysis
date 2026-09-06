# Architecture

Status: draft 1, 2026-09-06. Follows [PHILOSOPHY.md](PHILOSOPHY.md),
[CAPTURE.md](CAPTURE.md), [EVAL.md](EVAL.md).

---

## The central decision: an evidence graph, not a process diagram

The naïve build stores a process model and lets people edit it. That fails the moment two
respondents disagree — you either overwrite one account with the other or you average them, and
both destroy the most valuable observation in the dataset. Per CAPTURE.md, a contradiction is not
noise to be resolved; it is the located point where information is being lost.

So the system is three strictly separated layers:

```
CLAIMS  →  ENTITIES  →  GRAPH
 (written)  (resolved)   (derived)
```

**Claims are the only thing ever written.** Everything else is recomputed.

### Claims

One typed assertion by one person. *"There's a step where I check the budget code."* *"I hand it
to Sabine."* *"It usually sits about two days."* *"I'm waiting on legal right now."*

```
claim
  id
  respondent          who said it
  captured_at
  kind                step | handoff | duration | wait | system | rule |
                      approval | exception | artifact | complaint
  payload             kind-specific
  hedging             firm | approximate | guessed | deferred
  verbatim            the exact span it came from
  question_id         which probe elicited it
```

Two fields carry more weight than they look. **`hedging`** is signal, not metadata: "about two
days, I think" and "two days" are different observations, and flattening them throws away the
confidence model. **`verbatim`** is what makes the output defensible in a room — every number
must be traceable to a sentence somebody actually said.

### Entities

The hard part, and the piece that decides whether the system works at all.

A's "the intake form", B's "the request" and C's "that PDF thing" may be one artifact. Same
problem for steps, roles, and systems. This is record linkage across people who deliberately name
things differently, and it is the one place a language model is doing work nothing else can do —
a genuine placement rather than a decorative one.

Resolutions are stored separately from claims and are themselves revisable. Merging two entities
never edits the underlying claims.

### The graph is derived, never authored

The process model is a pure function of `claims + resolutions`. Consequences, all of which we
want:

- **Correction is cheap.** Fix a claim or a resolution, regenerate. Nothing is lost or overwritten.
- **Provenance is total.** Every node answers *who told us this, how firmly, and who disagrees.*
  This is the correlation-ID principle applied to an organisation instead of a request.
- **Contradictions are objects, not errors.** Two claims resolving to the same entity with
  incompatible payloads produce a `fracture` — a first-class node carrying both accounts, not an
  exception to be caught.
- **Confidence is computable.** A step asserted firmly by four respondents and a step mentioned
  once, hedged, are not the same fact, and the graph should never pretend otherwise.

Regeneration must be deterministic given the same inputs, or nothing downstream is reproducible.

---

## Pipeline

```
transcripts ─▶ claim extraction ─▶ entity resolution ─▶ graph build ─▶ metrics ─▶ findings
                   (model)              (model)            (code)      (code)    (v1)
```

### Model placements, and the ratio

Per PHILOSOPHY.md the preference order is **deterministic code → model → human**. Applied here:

| Stage | Who | Why |
|---|---|---|
| Claim extraction | model | unstructured speech → typed assertions |
| Entity resolution | model | vocabulary alignment across respondents |
| Graph build | code | pure function, must be reproducible |
| Queue-gap calculation | code | arithmetic over paired claims |
| Handoff count, cycle efficiency | code | arithmetic |
| Internal/external wait split | code + model | classification, rule-checked |
| Contradiction detection | code | structural: same entity, incompatible payloads |
| Constraint attribution (v1) | model | judgment, emitted as hypothesis |
| Step classification (v1) | model + rules | judgment, rule-checked |

Only two model calls in v0. That ratio is deliberate: it keeps the expensive, unauditable,
non-reproducible part small, bounded, and individually testable.

### Derived metrics (all code)

- **Queue gap** — the CAPTURE.md move. Pair the upstream claim *"how long after you send it does
  it get picked up"* with the downstream claim *"how long after it arrives do you start it"*. The
  difference is the queue, and no single respondent holds it.
- **Handoff count** per path — the primary build-sequencing signal.
- **Process cycle efficiency** — touch ÷ elapsed, per step and end to end.
- **Internal vs external wait split** — never conflated; see PHILOSOPHY.md §7.
- **Finding rank** — `volume × elapsed`, never complaint frequency or intensity.

---

## v0 is headless

**Build the analyzer first, against synthetic transcripts. The eval suite is the harness.**

There are no human respondents in v0 — the cast is generated per EVAL.md. So there is nothing to
interview and nothing to display that a file cannot carry. Building an interview UI before
reconstruction is proven is building the easy half first, which is how this kind of project dies
looking good.

```
v0:  transcripts in → claims → entities → graph → metrics → JSON + SVG out
                                                     ↑
                                       scored against hidden ground truth, in CI
```

Done-when: **the analyzer recovers a planted bottleneck from six biased accounts, resists the
planted loud-cheap-step decoy, and separates internal from external queues** — scored
deterministically, on a committed seed corpus, in CI. If that fails, nothing downstream matters
and we know in weeks.

### The SVG ships in v0

Python in, drawing out — no front end needed for the image that makes the argument.

**The primary view is drawn to time-scale.** Not a flowchart with equal boxes; a horizontal
timeline where waiting occupies the space it actually occupies. Touch time solid, queue time
grey, internal and external queues visually distinct. On a real process this produces a thin
bright sliver of work floating in a vast grey field, and that picture *is* the finding. Hammer's
insurance case drawn honestly is 0.05% work — you would zoom 2000× before seeing the boxes.

Secondary views, later: handoff graph (edge weight = delay), constraint tint per step
(binding / collapsed / unknown), allocation view after classification, and before/after on one
shared axis.

---

## Phases

- **v0 — reconstruction.** Headless analyzer, evidence graph, deterministic metrics, JSON + SVG,
  CI-scored against synthetic ground truth. *Proves the method is real.*
- **v1 — diagnosis.** Constraint attribution and step classification, both as hypotheses with
  evidence attached, never conclusions. Typed findings: `DELETE` · `COLLAPSE` · `REORDER` ·
  `AUTOMATE→code` · `AUTOMATE→model` · `HUMAN+evidence` · **`NOT-AN-AI-PROBLEM`**.
- **v2 — elicitation.** Adaptive multi-respondent interview surface, answerable from a phone. The
  first version a real organisation can use, and the first test of the thing synthetic data
  structurally cannot prove.
- **v3 — redesign and baseline.** To-be proposal, before/after on one time axis, and the baseline
  gate that refuses to show a redesign until a before-number is recorded.

Each phase is independently useful.

---

## Stack

Python core — matches fleet-orchestrator, and this is analysis-shaped work. SVG generated
server-side. No front end before v2; when it arrives it gets a gitignored `mise.local.toml`
pinning node + temurin-21, or Arch's Node 26 will eat it.

Tests from the first push per house standards: unit tests on the deterministic stages, the eval
suite as the integration tier, and a committed seed corpus so a score change means an analyzer
change rather than a change in the weather.

---

## Deliberately unresolved

- **Product or instrument.** Whether this becomes something other people run or stays ours does
  not change v0 by a single line, so it waits until the analyzer works.
- **Whether the fleet-orchestrator flow schema can express negative constraints** — "role X must
  not receive artifact Y", "role B's model family ≠ role C's". The eval's information barriers
  depend on it and the current bindings only express what each role *gets*. If it can't, this
  project is what forces the feature.
- **How many respondents before a reconstruction is trustworthy**, and how that confidence is
  surfaced rather than buried.
