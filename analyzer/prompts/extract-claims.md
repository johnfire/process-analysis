# Task

Read the interview transcript below and extract every typed claim the respondent makes about how
their work actually happens. Output a JSON array of claim objects conforming to the schema.
Output nothing but the JSON array — no commentary, no markdown fence.

## Who is speaking

- **respondent_id:** `{{RESPONDENT_ID}}`
- **name:** {{RESPONDENT_NAME}}
- **role:** {{RESPONDENT_ROLE}}
- **session_id:** `{{SESSION_ID}}`

Use `{{CAPTURED_AT}}` for every `captured_at`. Use `{{RESPONDENT_ID}}` for every `respondent_id`.
Generate `id` values as `{{RESPONDENT_ID}}-001`, `-002`, and so on, in the order the claims appear.

## Classify in two passes

First decide the family, then the kind within it. This is more reliable than choosing from fifteen
at once.

- **structural** — `step` `handoff` `artifact` `system` `actor`
- **temporal** — `duration` `wait` `schedule`
- **decision** — `rule` `approval` `exception` `consequence`
- **friction** — `complaint` `rework` `workaround`

Distinctions that are easy to get wrong:

- `system` is a place work is stored or done; `artifact` is a thing that moves between people.
- `schedule` is a *cause* of waiting (a weekly batch, a part-time pattern); `duration` is a
  *measure* of time. "I do them on Fridays" is a schedule, not a duration.
- `rework` travels backward to an earlier step; `exception` travels forward on a different path.
- `complaint` is how somebody feels; `workaround` is a thing they built because a system fails
  them. A private spreadsheet is a workaround, not a complaint.

## Fields that carry the most weight

**`verbatim` must be an exact substring of the transcript.** Copy it character for character from
the respondent's speech. Do not paraphrase, tidy, join two sentences, or fix the grammar. This is
checked mechanically and a claim that fails is discarded.

**`hedging`** — how firmly it was said, not how true it is.
`firm` stated plainly · `approximate` "about", "roughly", "a couple of" · `guessed` "I suppose",
"no idea really" · `deferred` pointed at somebody else ("you'd have to ask Sabine") ·
`refused` declined to answer.

**`polarity`** — `denied` when the respondent asserts something does *not* happen. "He's never sent
one back" is a denial and must be recorded as one.

**`subject_scope`** — `self` their own work · `direct_observation` something they have personally
seen elsewhere · `hearsay` what they believe about somebody else's work without having seen it.
Statements about another team's delays are almost always `hearsay`, however confidently delivered.

**`question_id`** — the number of the interview question that prompted this answer, as a string
("q7"). Null if volunteered mid-answer.

## Extract generously and honestly

- One answer usually contains several claims. Split them.
- Record contradictions as they come. If the respondent says a task takes ten minutes and later
  describes it taking an hour, that is two `duration` claims, both recorded, neither reconciled.
  Reconciling is not your job.
- Record what they say about other people, marked `hearsay`. Do not discard it and do not treat it
  as fact.
- Durations are ranges. "A couple of days" is `{"low": 2, "high": 3, "unit": "day"}`. Never invent
  a point value.
- Do not infer. If they did not say it, there is no claim. An empty field is better than a guess.

## Schema

```json
{{SCHEMA}}
```

## Transcript

{{TRANSCRIPT}}

Output the JSON array only.
