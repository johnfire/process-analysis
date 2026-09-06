# Capture: reconstructing a process from friction

Status: draft 1, 2026-09-06. Companion to [PHILOSOPHY.md](PHILOSOPHY.md) §8.

---

## Why this route

Capture is step 1 of the method and 60–80% of the real work. Everything downstream —
constraint archaeology, allocation, redesign — is comparatively mechanical once the map is
honest. So whatever produces the map defines the product.

Three routes were on the table:

- **A — capture is human work.** The reality lives in 10–20 people's heads; extracting it is a
  relationship problem. Implies a consultant's power tool: the practitioner brings the map.
- **B — capture is observable.** Don't ask, watch: mail headers, ticket transitions, calendar
  density, file mtimes, document lineage. Immune to the incentive problem, because behaviour
  leaves traces even when testimony won't. Collides head-on with BetrVG §87(1)(6) works council
  co-determination, plus GDPR Art. 6/88 and a DPIA.
- **C — capture is elicitable, if you change the question.** Reconstruct the process from
  friction and complaint rather than from description.

**We're building C.**

The strongest objection to automated capture is that AI-run interviews fail because half the job
is the relationship with the operator. That objection is correct *for description questions* —
asking someone to explain their own job precisely enough to automate it requires trust, because
the request is threatening on its face. It is much weaker for friction questions. **C is chosen
precisely because it minimises the relationship requirement**, not in spite of the objection.

---

## The framing rule

> **Point the question away from the respondent's value and toward the system acting on them.
> They are a witness, not a suspect.**

Every question in the bank derives from this. "Walk me through your day" is an audit and gets
audited answers: inflated complexity, emphasised judgment, hidden routine. "What are you waiting
on right now?" is sympathy, and gets the truth — because the respondent believes they are
reporting someone *else's* failure.

Corollaries:

1. **Never ask about the respondent's speed, competence, or necessity.** Not once, not obliquely.
2. **Prefer present tense and concrete instances** over averages and percentages. Nobody knows
   what share of their volume leaves the happy path. Everybody remembers the last one that went
   wrong.
3. **Recall ease is the frequency estimate.** If they produce three exception stories without
   pausing, exceptions are common. That's better data than a number they'd have guessed.
4. **Ask about artifacts, not activities.** The private spreadsheet, the reformatted file, the
   chase email. Artifacts are concrete, un-threatening, and each one is a documented failure of
   the official system.

---

## The question bank, by extraction target

| Target | Don't ask | Ask |
|---|---|---|
| Elapsed vs touch time | "How long does this take you?" | "From it landing on you to you being done — how much of that is you actually working on it?" |
| Queue location | "Where are the delays?" | "What are you waiting on **right now**?" |
| Handoffs | "Who do you hand off to?" | "Who do you have to chase? Who chases you?" |
| Exception rate | "What share leaves the happy path?" | "Tell me about the last one that went weird. And the one before that." |
| Rework loops | "How often is it wrong?" | "What comes back to you?" |
| **Determinism test** | "Is this a judgment call?" | **"If you were training your replacement for one week, what rule would you give them?"** |
| Systems + precedence | "Which systems do you use?" | "What do you copy from where?" (re-keying is the tell) |
| Cost of error | "What's the risk here?" | "What's the worst thing that happened when this went wrong?" |
| Coordination waste | — | "What status update do you write that you suspect nobody reads?" |
| Structuring cost | — | "What do you have to reformat before you can use it?" |
| Memory cost | — | "What do you look up or re-explain every single time?" |
| Batching constraint | — | "What deadline are you always up against, and what makes it tight?" |
| Tribal knowledge | — | "What do you always have to explain to the new person that isn't written down?" |

### The four that justify the exercise

- **"Has an approver ever actually said no? When?"**
  *Never* or *I can't remember* identifies a pure risk ritual and a deletable step. This is the
  only reliable probe for constraint #3, which generates no pain signal of its own. Nobody asks
  it.
- **"What do you keep in your own spreadsheet because the system won't hold it?"**
  Every shadow spreadsheet is a documented failure of a system of record, and people volunteer
  them proudly rather than defensively.
- **"If you vanished for two weeks with no laptop, what would be broken when you got back?"**
  Finds the true critical path and every single point of failure — without asking anyone to
  concede they are replaceable.
- **"What do you do that you're fairly sure is pointless?"**
  The highest-yield sentence in process discovery. People enjoy answering it. It costs nothing.

### Ordering

**Pain first, structure second.** Open with venting: it is ego-safe, the respondent enjoys it,
and it builds the only rapport this method requires. Move to structural questions only once they
are talking freely. Never open with "walk me through the process" — it sets the audit frame for
everything that follows, and the frame does not recover.

---

## What only software can do

This is the line between a questionnaire and a product.

### The queue-gap calculation

Ask the upstream person: *"How long after you send it does it get picked up?"*
Ask the downstream person: *"How long after it arrives do you start it?"*

**The gap between those two answers is the queue.** Neither party can see it alone; typically
nobody in the organisation holds that number at all. It is computed from two individually safe,
individually unremarkable questions asked of two different people, and it is exactly the quantity
the whole method turns on.

Generalise: the most valuable numbers in a process are *differences between accounts*, not
values in any single account.

### Contradiction as signal, not noise

A says "I'm waiting on finance." Finance says "we never received the request."

That is not conflicting data to be averaged, cleaned, or resolved in favour of the more senior
respondent. **It is the precise location where information is being lost.** Contradictions
between respondents are the highest-value observations in the dataset, and the system should hunt
them deliberately and surface them as findings.

Operating rule: **any claim about someone else is a hypothesis.** It is promoted to a finding
only when the other side's account confirms it, and promoted to a *fracture* when it doesn't.

---

## Where pain-based capture fails

Known plateau at roughly 70% of the picture. Three specific gaps, each needing a different
instrument:

1. **Complaint bias.** People complain about what is *annoying*, not what is *expensive*. A
   four-day wait everybody has stopped noticing produces zero complaints and enormous cost.
   Correction: rank findings by `volume × elapsed time`, never by complaint intensity or
   frequency of mention.
2. **Blame points outward.** Every department names the one next door. Aggregate naively and the
   map shows every department as a victim and no department as a cause. The triangulation rule
   above is the only fix, and it has to be structural rather than a review step.
3. **Internalised constraints are invisible.** Nobody resents the approval chain — they have
   absorbed it as the nature of reality. Constraint #3 emits almost no pain signal. This needs a
   probe class aimed at the *unexamined* rather than the painful; the approver question is the
   prototype.

Knowing the plateau up front is what stops us shipping something that quietly stops at 70% and
calls it done.

---

## Open design questions

- AI-conducted, human-conducted, or both from one bank? Current lean: one question bank, two
  delivery modes — an adaptive branching interviewer, degrading gracefully to a printable guide
  for a human to run. The branch logic (what to ask next, given what was just said) is where the
  model earns its place; the questions themselves are largely fixed.
- How many respondents per process before the reconstruction is trustworthy, and how is that
  confidence surfaced rather than hidden?
- How to keep the instrument from becoming a grievance collector — the output must be a process
  model, not a complaints register.
