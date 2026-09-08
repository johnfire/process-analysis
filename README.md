# process-analysis

Tooling and thinking for **AI-native process refactoring** — not "applying AI" to existing
processes, but finding the steps that shouldn't exist at all.

## The premise

Every step in a business process is a fossil of a constraint: something that was once expensive
(attention, expertise, verification, structuring input, handling variance, memory, coordination,
reconciling disagreeing systems). The process is the shape the organisation took to route around
those costs. When a cost collapses, the workaround becomes dead weight — but nobody deletes it,
because nobody remembers it *was* a workaround.

So the question is never "which step can AI do faster?" It's **"which constraint shaped this
step, and does it still bind?"**

Hammer's number, from 1990 and still the sharpest statement of the problem: an insurance
application took 22 days to move through the business, containing 17 minutes of actual work.
Make every step twice as fast and you have saved eight and a half minutes.

## Status

Pre-implementation, designed. v0 is a headless analyzer scored against synthetic processes with
hidden ground truth — no UI, no real respondents, no interview surface. It is done when it
recovers a planted bottleneck from six biased accounts and resists the planted decoys.

## Try it

```bash
python -m venv .venv && .venv/bin/pip install -e ".[dev]"
.venv/bin/python -m analyzer list
.venv/bin/python -m analyzer report corpus/seed/hospital-onboarding
.venv/bin/python -m analyzer score  corpus/seed/hospital-onboarding
```

`report` runs the pipeline over an already-extracted process and prints what it found: the
time-scale picture, where the delay actually is, how that ordering differs from who complains
loudest, and any fractures between accounts. `score` grades the same analysis against the hidden
answer key.

Generating a new process, and extracting claims from it, both call external models and take
several minutes:

```bash
# invent a hidden process, then interview its cast   (needs `hermes` and `codex` on PATH)
.venv/bin/python corpus/generate.py --domain "invoice approval" \
                 --headcount 250 --sector "facilities management"

# transcripts -> claims                              (needs `hermes` on PATH)
.venv/bin/python analyzer/extract.py corpus/seed/<process-id>
```

`--ground-truth <path>` re-runs only the interviews against an existing answer key, which is what
you want after changing the question bank.

## Docs

- [`docs/PHILOSOPHY.md`](docs/PHILOSOPHY.md) — the working philosophy. Constraint archaeology,
  decisions-not-steps decomposition, human/AI allocation criteria, the five shapes AI takes in a
  process, the replacement lever ladder, failure modes (technical and political), and the one
  genuinely unsolved problem: honest capture of the real as-is.
- [`docs/CAPTURE.md`](docs/CAPTURE.md) — how we intend to solve that problem: reconstructing a
  process from friction rather than from description. The framing rule, the question bank, the
  two moves only software can make (queue-gap calculation, contradiction detection), and the
  known 70% plateau.
- [`docs/EVAL.md`](docs/EVAL.md) — how the analyzer gets tested before a real subject exists:
  two-stage synthetic generation (hidden ground truth, then biased testimony from it), planted
  decoys, deterministic scoring, and strict information barriers between generator, cast,
  analyzer and scorer.
- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — how it gets built: claims → entities → graph
  with the graph derived rather than authored, the deterministic/model split, a headless v0
  scored in CI, and the phase plan.
- [`docs/CLAIM-SCHEMA.md`](docs/CLAIM-SCHEMA.md) — the claim schema and the decisions it encodes.
  Normative form: [`schema/claim.schema.json`](schema/claim.schema.json).

## Open questions

1. Is dropping "standardise" from the lever ladder correct, or an over-rotation on cheap
   variance handling?
2. Does the accountability human survive contact with real organisations, or degrade into a
   rubber stamp?
3. ~~Is process capture automatable at all?~~ **Answered:** yes, via friction rather than
   description — see `docs/CAPTURE.md`. This decides the product: self-serve, no surveillance.
