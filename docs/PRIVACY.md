# What leaves the server, and what does not

Written for the operator. Describes what the code does today, including where it falls short.

## The rule

When a model reads an interview, the text is sent to a third-party provider over the internet.
Everything below exists to reduce what is disclosed in that moment, and to make the operator the one
who decides which providers may receive which data.

## What is hidden before sending

Before any transcript is sent, `analyzer/pseudonymise.py` replaces:

1. **People in the cast** — every way their name is likely written: full name, first name, last name,
   without a title ("Dr. Elena Vidal", "Elena", "Vidal", "Dr. Vidal"). Each person becomes `PERSON_n`.
2. **Email addresses, telephone numbers (8 or more digits) and web addresses** — `EMAIL_n`, `PHONE_n`, `URL_n`.
3. **Terms the operator lists** per process (and the organisation's name) — `TERM_n`.
4. **The respondent's role line**, which often names the employer.

The model is told the respondent is `PERSON_k`. Claim ids, respondent ids and session ids are never
taken from the model's reply.

## What is not hidden

- **A name nobody listed.** Someone mentioned in passing but not interviewed and not added to the
  terms list is sent as written. The setup page therefore shows the text as the provider will receive
  it, and lists capitalised words that are still present, so the operator can add them first. That
  list is a heuristic: it over-reports (German nouns) and cannot find a name that is also an
  ordinary word.
- **Identification without a name.** "The only night-shift pharmacist in the Augsburg site" identifies
  someone. No program can find that. Read the preview.
- **The content itself.** What people say about how the work happens is exactly what the provider
  reads. That is the product.
- **Metadata the provider sees anyway:** the request's time, size, model, and the server's address.

## Which providers receive what

Every client has a label:

- **sensitive** (the default): only providers listed in `SENSITIVE_OK_PROVIDERS` may be used. With
  nothing listed, a sensitive client cannot use any provider.
- **standard**: any provider listed in `PROVIDERS_ENABLED`.

The label is checked twice: when the run is requested, and again in the worker immediately before any
data is sent. API keys exist only in the worker's environment; the web container never holds them.

**The code cannot know a provider's data-handling terms.** Listing a provider under
`SENSITIVE_OK_PROVIDERS` is a statement by the operator that they have read that provider's current
terms (retention, training on API data, subprocessors, region) and accept them. That statement is
not verified by software and it can go stale; terms change.

## What is recorded

- Every model call writes an audit entry attributed to the model (`model:provider/name`), with the
  process and respondent it concerned, and whether it succeeded. No transcript text is logged.
- Starting and cancelling a run, creating and deleting clients and processes, and every refused
  deletion are audited with the acting user.
- The worker's log carries a correlation id from the request that queued the job.

## Deleting

Deleting a process or client removes its transcripts, claims, results and jobs from this database.
It cannot recall what a provider has already received; that is governed by the provider's terms.
Daily database backups keep seven daily, four weekly and three monthly copies, so deleted data
persists in backups until they age out.

## Before real client data

- Read the terms of every provider you will list as approved, and write down the date.
- Agree what may be sent with the client, in writing; a processing agreement is needed if you act as
  their processor under the GDPR.
- Run the `gdpr-audit` skill against the live app.
- Remember the 2FA secret is stored unencrypted in the database (a known gap).
