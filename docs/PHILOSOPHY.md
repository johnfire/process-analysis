# AI-native process refactoring — working philosophy

Status: draft 1, 2026-09-06. Foundation doc, pre-app. Iterate freely.

---

## 0. The thesis

Classic process improvement asks: **which step is slow, and how do we speed it up?**
AI-era process improvement should ask: **which constraint shaped this process, and is that
constraint still real?**

Every step in every business process is a fossil. It exists because at some point something
was expensive — attention, knowledge, verification, structure, coordination. The process is
the shape the organisation took to route around those costs. When the cost of a constraint
collapses, the step that routed around it becomes dead weight, but nobody deletes it, because
nobody remembers it was a workaround. It just looks like "how we do things."

So the core move is not automation. It's **constraint archaeology**: dig up the constraint
behind each step, check whether it still binds, and delete the fossil if it doesn't.

This is what separates a 20% gain from a 10x one. Automating a step you should have deleted
is the RPA mistake, at a higher price.

---

## 1. The seven constraints that shaped every process you'll ever look at

For each step, ask which of these it was routing around, and whether that's still true.

| # | Constraint | Process shape it produced | What collapses |
|---|---|---|---|
| 1 | **Cost of attention** | Batching, queues, scheduled runs, "we process these Thursdays" | Batch size → 1; event-driven |
| 2 | **Cost of expertise** | Specialisation, handoffs, escalation tiers, translation loss | Roles recombine into one augmented owner |
| 3 | **Cost of verification** | Sampling QA + approval hierarchies as a *proxy* for checking | 100% checking; approval chains become deletable |
| 4 | **Cost of structuring input** | Forms, required fields, templates, "use this format please" | Accept input as it arrives; structure it machine-side |
| 5 | **Cost of handling variance** | Aggressive standardisation; exceptions forced through or black-holed | Per-case paths; serve variance instead of suppressing it |
| 6 | **Cost of memory & search** | Re-establishing context at every handoff; "where's that doc" | Context held continuously across the whole case |
| 7 | **Cost of coordination** | Status meetings, weekly reports, dashboards, chase-ups | State observable on demand; reporting layer collapses |
| 8 | **Cost of reconciling disagreeing systems** | Master data management, canonical models, ERP/CRM consolidation megaprojects | Tolerate the disagreement; resolve per case at the orchestration layer |

**#3, #5 and #8 are the big ones and the ones people miss.**

- #3: most approval chains are not information-processing, they're *risk rituals*. They exist
  because you couldn't check everything, so you made a human sign as insurance. If you can
  check 100% of cases cheaply, you can invert the whole thing: approve by default, verify
  universally, escalate only exceptions. This is the single largest structural change
  available — and the one that hits the most political resistance, because approvals are
  where power lives.
- #5: this contradicts lean. Lean says reduce variation, because variation is expensive.
  If handling variation becomes cheap, **standardisation is no longer a prerequisite for
  automation.** You can drop "standardise" from the lever ladder. That's a genuinely
  non-obvious inversion of 40 years of doctrine, and I'd want to stress-test it.
- #8: deterministic integrations shattered whenever two systems disagreed about what a vendor
  record was, so orgs built enormous consolidation programmes to make them agree. That is a
  documented way to lose two years and nine figures before delivering a euro of value (TSB:
  £318M migration, ~£200M incident costs, £48.65M FCA/PRA fine, 5.2M customers locked out;
  Zimmer Biomet: $172M claim against Deloitte after a botched consolidation). Judgment-capable
  middleware tolerates the disagreement, so the orchestration layer replaces the migration.
  **Caveat:** "tolerates" is load-bearing and hides where the risk went. You still have to decide
  which system wins when two disagree — you have merely moved that from a data migration into a
  policy layer. Cheaper and better, but not free, and an agent silently picking a side is worse
  than an explicit precedence rule.

---

## 2. The wrong unit of analysis is the step

"Eliminate steps" is the right instinct but the wrong granularity. A step is an artifact of
how the work was divided among people. Decompose instead into **decisions and the evidence
they consume.**

A process, stripped down, is: a sequence of decisions; each needs evidence; each has a
consequence if wrong.

For every decision, four questions:

1. **What evidence does it need?** (Most "steps" are pure evidence-gathering, and evidence
   gathering is the most compressible activity in any organisation.)
2. **Is there a written rule?** If a documented rule exists, it isn't judgment — it's an
   unautomated lookup wearing a judgment costume. This test alone reclassifies an enormous
   amount of supposedly-human work.
3. **What's the cost of being wrong, and is it reversible?**
4. **Who bears that consequence?**

Once the process is a decision graph rather than a task list, the steps that exist only to
move paper between decisions become visibly optional.

---

## 3. Human vs AI: five criteria, only one of which is about capability

The lazy version is "AI does routine, humans do judgment." That's wrong — it maps to nothing
real and it puts humans exactly where they add least. Better criteria for **must be human**:

1. **Accountability.** Someone must be answerable — legally, contractually, morally. Signing,
   firing, diagnosing, financial sign-off. The human's function here is *to bear consequence*,
   which is a real function and not a capability gap. Don't design it away; design it
   explicitly.
2. **Irreversibility × blast radius.** The dominant variable. A reversible decision wrong 5%
   of the time is cheap. An irreversible one wrong 0.1% of the time can end the company.
   Human presence should scale with this product, not with task difficulty.
3. **Relationship.** The other party needs a human because the *attention itself* is the
   value — condolence, negotiation, a furious customer, hiring. Efficiency is not the goal in
   these steps. Optimising them is value destruction.
4. **Novelty / out-of-distribution.** The case is genuinely unlike the record. Note this is a
   **routing** criterion, not a static assignment: the human is on exception duty, not in the
   flow.
5. **Taste / standard-setting.** Where the output defines what "good" means for everything
   downstream. Someone holds the bar.

**Before any of the five, run the determinism test.** If a rule can be written down, write it as
*code*, not as a prompt. Plain software is cheap, fast, auditable, and never hallucinates. Routing
a documented rule to a model is the second-most-common waste in this field after paving the
cowpath — you take a deterministic decision and make it probabilistic, more expensive, and harder
to audit, in exchange for nothing. Three destinations, in strict order of preference:
**deterministic code → model → human.** Only what fails the first test reaches the second.

And the inverse — work commonly assumed to need a human that mostly doesn't: reading,
summarising, classifying, extracting, drafting, reconciling, checking-against-rules, first-pass
triage, and most of what organisations call "review."

**Rule of thumb:** humans should be *rarer and higher-stakes* in the redesigned process, not
merely faster. If your redesign has humans in the same places doing the same things but
quicker, you haven't refactored — you've optimised.

**The verification-cost law.** The value of automating a step is:

    net value = work removed − verification cost added

If the output is five pages a human must read in full to trust it, you removed the writing and
added the reading, and netted approximately zero. Corollary, and the sharpest heuristic in this
whole document: **judge the difficulty of the action, not the difficulty of the thinking.** Hard
thinking with a cheap-to-verify output (a route, a match, a flag, a yes/no, a code) is the best
possible automation target. Easy thinking with an expensive-to-verify output is the worst, and it
is exactly what most AI pilots choose, because it demos well.

---

## 4. AI shows up in five distinct shapes, not one

Same model, wildly different leverage and risk depending on placement:

- **Doer** — performs the step end to end. Obvious, most-attempted, middling leverage,
  highest risk.
- **Router / triage** — decides where a case goes. *Highest leverage, lowest risk, most
  underrated.* Wrong routing is cheap to correct; correct routing eliminates whole downstream
  paths.
- **Checker** — verifies output (human's or another AI's). Converts sampling-QA into
  universal QA. This is what makes the #3 constraint collapse.
- **Memory** — carries case context across the whole process so it never needs re-establishing.
  This is what actually kills handoff loss.
- **Sensor** — continuously observes the running process and reports on it. Process mining,
  but live, and not restricted to systems with clean event logs.

Design question is never "should AI do this step" — it's "which of these five shapes belongs
where."

---

## 5. The new lever ladder

Classic lean: Eliminate → Simplify → **Standardise** → Automate → Outsource.

Proposed AI-era replacement, applied strictly in order:

1. **Eliminate** — the constraint is gone; the step is a fossil. Delete it.
2. **Collapse** — merge steps that were split only by a handoff. Recombine specialist roles
   into one augmented owner. (This is the 1990s BPR "case manager" dream, which failed then
   because no human could actually hold all the required knowledge. That's now a solvable
   problem.)
3. **Reorder / parallelise** — most serial dependencies in processes are *false* dependencies:
   cost optimisations, not real data dependencies. When work is cheap you can speculate —
   execute several branches before the decision that selects between them, and discard the
   losers. (Branch prediction, applied to paperwork.)
4. **Automate** — only what survives 1–3.
5. **Instrument** — the redesigned process must observe itself, or it decays back.

Note the deliberate omission of "standardise," per §1/#5, and the demotion of "automate" to
fourth. If a project reaches for step 4 first, that's the diagnostic that it will underdeliver.

---

## 6. Where this goes wrong — the honest section

Six failure modes, each of which needs a designed defence, not a warning label:

1. **Correlated verification failure.** If the doer is AI and the checker is AI, and they share
   a model, a prompt lineage, or a blind spot, you have one failure domain wearing two hats.
   The checker must fail *differently* from the doer — different model, different framing,
   or a deterministic rule check. Non-negotiable.
2. **Cheap work causes overproduction.** Overproduction is waste #2 in the lean taxonomy for a
   reason. Making drafting free reliably produces forty documents nobody reads. AI does not
   automatically reduce waste; it makes *producing* waste nearly free.
3. **Human deskilling / loss of calibration.** If humans only ever see exceptions, they lose
   their sense of the normal case and become *worse* at judging exceptions. This is documented
   in aviation automation. Defence: deliberately route a sample of normal cases back to humans
   to keep them calibrated. It looks like waste. It isn't.
4. **The audit trail collapses with the steps.** Deleting a step often deletes the evidence
   that it happened. Keep the evidence even when you kill the ceremony.
5. **Chesterton's fence.** Some steps exist for undocumented reasons — a regulation, a
   contract clause, one catastrophe in 2014. Constraint archaeology is precisely the discipline
   that stops greenfield redesign from walking into these. If you can't name the constraint,
   you're not allowed to delete the step yet.
6. **Unfalsifiable baselines.** If you can't measure the before, you can't claim the after,
   and every organisation has an incentive to fudge. Baseline first, honestly, or the whole
   exercise is theatre.

Two symmetric traps to steer between: **paving the cowpath** (automate as-is, get 20%) and
**greenfield fantasy** (redesign from first principles, ignore why things are, blow up).
Constraint archaeology is the thing that sits between them — greenfield ambition disciplined
by evidence about why each fossil is there.

---

## 7. The method, as phases

0. **Baseline the outcome, not the process.** What is this process *for*? What would its
   customer actually want? Sometimes the answer is that it shouldn't exist. Ask before you map.
1. **Capture the real as-is** — including variants and exception paths, not the happy path
   people describe in interviews. (Hardest part. See §8.) Capture per step, at minimum:
   *what share of volume leaves the happy path and where it goes; who gets pulled in; touch time
   vs elapsed time and the gap; what's upstream and downstream; which systems of record are
   involved and which one wins when two disagree; how it differs by region/entity/acquisition;
   the cost of an error here.* Start at **department level**, not single-workflow level — an
   eight-week single-workflow perfection exercise gated by a sister process upstream nets zero.
2. **Recast as a decision graph** — decisions + evidence + consequence + reversibility, per §2.
3. **Constraint archaeology** — name the constraint behind every step, per §1. Mark each as
   *still binding* / *collapsed* / *unknown*. Separately mark every queue as **internal** or
   **external**: a prospect taking three weeks to reply, or a bank's settlement window, is a real
   wait that no redesign collapses. Conflating the two produces an analysis that correctly finds
   the largest delay in a process and then has nothing to propose about it.
4. **Allocate** — five criteria per decision, five AI shapes per placement, per §3 and §4.
5. **Redesign** — Eliminate → Collapse → Reorder → Automate → Instrument, per §5.
   Sequence the build by **handoff count, not volume**. The workflow with the most handoffs is
   the clearest win, and it is usually not the one with the most transactions.
6. **Design the failure domains** — for each new AI placement: how does it fail, who notices,
   what's the fallback, what's the blast radius. Per §6. This is Chris's anti-fragility rule
   applied to org design rather than code.
7. **Run it live** — the model is a running artifact, not a deck. If it's stale in three months
   we've rebuilt the thing we were complaining about.

---

## 8. The unsolved problem

Everything above is method. The thing that decides whether any of it becomes a product is
**§7 step 1: honest capture of the real as-is.**

- Interviews yield the idealised happy path. Real processes have dozens of variants.
- Process mining yields the truth, but only for work that leaves clean event logs with a stable
  case ID in a system of record — i.e. ERP order-to-cash and procure-to-pay, and nothing else.
- The mass of actual organisational waste lives in email, spreadsheets, chat, PDFs, meetings,
  and people's heads, where neither method reaches.

Whatever we build has to have an answer for that gap. Everything else in this document is
comparatively easy.

**And the gap is worse than "no data exists," because testimony is compromised at the source.**
The strongest counter-argument to automating capture: the reality of an organisation lives in the
heads of ten to twenty people who have done that exact job for years, and getting it out of them
is a relationship problem, not an extraction problem. AI-run interviews and engineer-run
interviews are both reported to fail — half the job is knowing which question to ask next and
being someone the operator will answer honestly. Note the person making this argument sells the
service it justifies, so discount accordingly; but the incentive problem underneath it is real
and independent of who's arguing. People do not accurately describe a process to a system they
suspect will replace them.

Two possible routes past it, both with teeth:

- **Don't ask — observe.** What people do leaves traces even when they won't talk: mail headers
  and timestamps, ticket transitions, calendar density, file modification times, chat volume,
  document lineage. This is process mining generalised beyond systems with clean case IDs, and
  it's the only version of capture that resists the incentive problem.
  **But:** in Germany this collides directly with BetrVG §87(1)(6) — any system capable of
  monitoring employee performance or conduct requires works council co-determination, and a
  Betriebsvereinbarung is not a formality. Plus GDPR Art. 6/88 and the usual DPIA. This is a
  fatal blocker or a genuine differentiator depending entirely on whether it's designed in from
  the start. Decide early; it constrains the architecture, not just the paperwork.
- **Change the interviewee's incentive.** Operators talk freely about what they *hate*, and about
  what makes their job stupid, far more freely than about what they do. "Where does your work
  wait on someone else" is a safe question. "Walk me through your day" is not. There may be a
  capture design that only ever asks the safe class of question and reconstructs the process from
  complaints rather than descriptions.
