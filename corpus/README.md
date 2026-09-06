# Corpus

Synthetic processes for testing the analyzer, per [../docs/EVAL.md](../docs/EVAL.md).

Two stages, and the order is the whole point:

1. **Architect** invents the hidden truth — a complete, quantified process including timings no
   single employee could see. Validated against `spec/ground-truth.schema.json`.
2. **Cast** speaks as individual employees, each given only their own slice, answering the
   question bank from [../docs/CAPTURE.md](../docs/CAPTURE.md).

Testimony is never generated directly. Without an answer key, an eval degrades into "does the
output look plausible", which is the failure this project exists to criticise elsewhere.

```
corpus/
  spec/ground-truth.schema.json   what the architect must emit
  prompts/architect.md            invents the process
  prompts/cast.md                 speaks as one employee
  prompts/questions.md            the interview, from CAPTURE.md
  generate.py                     runner and barrier enforcement
  seed/<process-id>/
    ground_truth.json             the answer key - never shown to the analyzer
    transcripts/<person-id>.md    what the analyzer gets
```

## The barrier is code, not instruction

`build_slice()` constructs what each person can know and passes nothing else. A respondent gets
their own steps, the fact that work visibly arrives from and departs to somebody, their
colleagues' names and roles, and — if they are the one carrying the planted false-blame belief —
who they think is blocking them.

They do not get: anyone else's timings, the shape of the process end to end, the `planted` block,
or the `true_classification` labels. That exclusion is enforced by constructing the payload, never
by asking a model to disregard something it has already been shown. An instruction to forget is
not an information barrier.

## Model assignment

| Role | Model | Why |
|---|---|---|
| Architect | `hermes` → DeepSeek | Not Claude, not the analyzer |
| Cast | `codex` → GPT | A second family, so no single model's idea of an office propagates through both stages |
| Analyzer | Claude | The thing under test |
| Scorer | mostly deterministic code | Arithmetic is not a judgment call |

The generator is never shown our method — no constraint archaeology, no lever ladder, no
vocabulary from the philosophy. The architect prompt describes *features of a world* ("an approval
that has never once been refused") rather than *things we intend to detect*.

**An honest note on the limit of that barrier.** We cannot avoid telling the architect what to
plant, or there is no answer key. What we can and do avoid is telling it why those features
matter, what we call them, or what the analyzer looks for. The barrier is on method and
vocabulary, not on content — it prevents a dataset shaped like our solution, not a dataset
containing the structures we intend to find.

## Running

```
python corpus/generate.py --domain "inbound lead to first qualified contact" \
                          --headcount 180 --sector "industrial equipment distribution"
```

Requires `hermes` and `codex` on PATH, and `jsonschema` for ground-truth validation (generation
proceeds without it, unvalidated, with a warning).

Generated processes are committed. Regeneration is a separate deliberate act, so that a change in
analyzer score means a change in the analyzer rather than a change in the weather.

## Known gap in the first seed

`kessler-inbound-lead-qualification` was generated before the `false_blame.step_id` guard
existed. Its answer key describes the misapprehension as being about trade-show badge scans
uploaded to a CRM endpoint that silently fails — but no step in the process is "upload badge
scans", so that specific narrative reached neither person's slice.

A fracture did still emerge in the testimony, in different words: Anna describes capture as
automatic and reliable ("the whole point is that it creates itself"), Sabine describes it as
unreliable and invisible to her ("if the capture has done something odd then I'm the last to
know"). Two honest, incompatible accounts of the same handoff. So the corpus is usable, but a
scorer matching against the answer key's *wording* would mark a correct finding wrong.

The guard now prevents this: `false_blame` must name a real `step_id`, and that step must be
performed by the person being blamed. Regenerating this process under the fixed prompt is a
cheap follow-up and worth doing before the scorer is written.
