# Task

Invent a realistic business process at a specific company and describe how it *actually* works —
not how a policy document would claim it works. Output a single JSON object conforming to the
schema supplied below. Output nothing but the JSON: no commentary, no markdown fence.

You are inventing the truth. Somebody else will later interview the people in this company, and
each of them will only know their own corner of it. So the truth must be complete, specific, and
quantified, even in the places no single employee could see.

## Brief

- **Domain:** {{DOMAIN}}
- **Organisation:** roughly {{HEADCOUNT}} people, {{SECTOR}}
- **Cast:** between 4 and 7 named people who touch this process
- **Steps:** between 8 and 16, in order

## What makes this realistic

Real processes are lopsided. Almost all of the calendar time is spent waiting, and almost none of
it doing. A step that takes eleven minutes of actual work can easily sit for four days before
anyone starts it. Write the numbers that way: `touch_minutes` should usually be small, and
`queue_before_minutes` should frequently be enormous by comparison. A process where work time and
elapsed time are similar is not a process anybody would ask about.

Waiting has causes, and they are mundane: somebody batches things up and does them all on a
Friday, somebody is part-time, a request sits in an inbox behind more urgent things, an outside
party has its own timetable. Fill in `queue_cause` honestly.

Give people real names, real tenure, and real attitudes. Someone who has been doing this for
eleven years feels differently about it than someone who arrived in March.

## Features this process must contain

Build these in naturally, as things that would genuinely occur in a company like this. Do not
label them in the prose; just make them true, and record where they are in the `planted` block.

1. **A step everybody finds irritating that costs almost nothing.** A login that times out, a
   form field that resets, a system that logs you out. High irritation, trivial time cost.
   Everyone will mention it.
2. **A long wait that nobody notices any more.** Days of dead time, present for years, so
   normalised that the people involved have stopped experiencing it as a delay. Mark the step
   `normalised: true`. Nobody will raise this unless asked a very direct question.
3. **Somebody who sincerely believes another team is blocking them, and is wrong.** They are
   waiting on a request that the other team never received — it failed silently, went to the wrong
   address, sat in a shared inbox nobody reads. Both parties are honest; both accounts are
   incompatible. Record the truth in `planted.false_blame`, and set its `step_id` to the real
   step this is about — a step the blamed person actually performs. The misapprehension must be
   about work that appears in both people's daily experience, or neither of them will mention it.
4. **An approval that has never once been refused.** Somebody's sign-off is required, and in the
   entire history of this process that person has never sent anything back. Nobody has noticed.
   Set `has_ever_rejected: false`.
5. **A step whose biggest available improvement involves no software and no intelligence
   whatsoever.** Something purely arrangemental — a document being sent automatically instead of
   requested, a standing slot instead of a chase, an address changed. Record it in
   `planted.non_technological_fix`. It must save several days, though it need not be the single
   largest saving in the process.
6. **A long wait caused entirely by an outside party**, which this company has no power to change:
   a bank's settlement window, a regulator's response time, a customer who takes as long as they
   take. Set `queue_owner: external`.
7. **A decision that genuinely has to be made by a person**, because it cannot be reduced to a
   rule, being wrong is expensive, and the mistake cannot be undone. Set `decision.statable_rule`
   to null and `true_classification: human`.

Everywhere else, be honest about `true_classification`:
- `deterministic` — there is a statable rule; a competent person could be told it in one sentence
- `model` — judgment, but low stakes, reversible, and there is a long history of similar calls
- `human` — genuine judgment where a mistake is expensive and irreversible

Most steps in a real process are `deterministic`. Very few are `human`.

## Schema

Your output must validate against this exactly. Every required field must be present.

```json
{{SCHEMA}}
```

Output the JSON object only.
