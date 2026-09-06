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

Pre-implementation. The thinking is settled enough to build against; the application is not
yet designed.

## Docs

- [`docs/PHILOSOPHY.md`](docs/PHILOSOPHY.md) — the working philosophy. Constraint archaeology,
  decisions-not-steps decomposition, human/AI allocation criteria, the five shapes AI takes in a
  process, the replacement lever ladder, failure modes (technical and political), and the one
  genuinely unsolved problem: honest capture of the real as-is.

## Open questions

1. Is dropping "standardise" from the lever ladder correct, or an over-rotation on cheap
   variance handling?
2. Does the accountability human survive contact with real organisations, or degrade into a
   rubber stamp?
3. Is process capture automatable at all — or is any tool built here necessarily a consultant's
   instrument rather than a self-serve product?

Question 3 is the fork that decides what gets built.
