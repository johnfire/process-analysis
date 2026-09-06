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
- A `rule` is a decision *this person makes*: given a condition, they take an action. An
  explanation of why something goes wrong ("these things happen when the data is old") is not a
  rule. If you cannot phrase it as "when X, I do Y", it is not a `rule`.

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

One narrow exception, which is about *existence* rather than volume: if the respondent says a
thing does not exist at all, do not record that thing as existing. "I don't need sign-off for my
part" means there is no approval here — record no `approval` claim, rather than an approval whose
approver is "nobody". `denied` is for denying a property of something real, not for denying that
the thing is there. This rule is narrow: it applies only to non-existence, and it is never a
reason to drop a claim about something that does exist.

**`subject_scope`** — `self` their own work · `direct_observation` something they have personally
seen elsewhere · `hearsay` what they believe about somebody else's work without having seen it.

**This is a labelling rule, never a filtering one. Never drop a claim because it is hearsay** —
what one person believes about another's work is among the most valuable material in the
transcript, because comparing it against that person's own account is how the analysis finds where
information is being lost. Record it, and mark it `hearsay`.

Expect a lot of it. These questions invite people to talk about what obstructs them, so most
respondents describe other people's work at length and with total confidence. Confidence is not
evidence. If the claim is about what somebody *else* does, how long *they* take, or why *their*
part is slow, and the respondent has not personally watched it happen, mark it `hearsay` —
including when they are plainly right, and including when they name the person. Only what passes
through this respondent's own hands is `self`.

**`question_id`** — the number of the interview question that prompted this answer, as a string
("q7"). Null if volunteered mid-answer.

## Extract generously and honestly

Coverage matters more than tidiness. A 900-word transcript should normally yield **40 to 70
claims**; if you have produced far fewer, you are summarising rather than extracting, and
structural claims (`step`, `handoff`, `exception`) are the first things lost when that happens.
Every distinct thing the respondent says about how the work happens is a claim.

- One answer usually contains several claims. Split them.
- Every activity the respondent describes doing is a `step` claim, even a small one, and even if
  they mention it only in passing.
- Record contradictions as they come. If the respondent says a task takes ten minutes and later
  describes it taking an hour, that is two `duration` claims, both recorded, neither reconciled.
  Reconciling is not your job.
- Record what they say about other people, marked `hearsay`. Do not discard it and do not treat it
  as fact.
- Durations are ranges. "A couple of days" is `{"low": 2, "high": 3, "unit": "day"}`. Any hedged
  number is a range: "probably ten minutes" is `{"low": 8, "high": 15, "unit": "minute"}`, not ten
  exactly. Use `low == high` only when the respondent states a precise figure without hedging.
  A point value recorded from a hedged answer manufactures precision the respondent did not have,
  and it propagates into every downstream metric looking authoritative.
- Do not infer. If they did not say it, there is no claim. An empty field is better than a guess.

## Schema

```json
{{SCHEMA}}
```

## Transcript

{{TRANSCRIPT}}

Output the JSON array only.
