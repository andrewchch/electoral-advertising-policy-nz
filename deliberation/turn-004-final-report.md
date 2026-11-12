# Deliberation Session 1 — Final Report

- **Dates:** 13 November 2026
- **Starting point:** v0.9 (12 November 2026), commit `0c3de44`
- **Ending point:** v0.10.2 (13 November 2026), commit `e7131a3` plus this record
- **Outcome:** converged at turn 4 (ceiling 10). Three proposals approved, one rejected.
- **Protocol:** `deliberation/protocol.md`
- **State:** `deliberation/state.json`

---

## 1. Summary

Four turns were run. Turn 1 (4–1) closed a completeness gap in the pre-clearance
procedure. Turn 2 (0–5) proposed adding deceptive numerical framing as a fifth
prescribed technique and was rejected unanimously, including by its own proposer. Turn 3
(5–0) replaced the two 48-hour clocks that turn 1 had left behind with one decision
period, added a resubmission rule, and made deemed codes reviewable and subject to
takedown. Turn 4 (5–0) aligned s 9's disqualification forum with ss 7.6 and 8.10.

Turns 3 and 4 were both unanimous approvals of minor edits (18 and 2 changed lines in
`proposal.md`, one clause each), which met the convergence condition (two consecutive
unanimous minor approvals). The session stopped at turn 4, well below the hard ceiling of
10.

The net change to `proposal.md` from v0.9 is 18 insertions and 5 deletions, confined to
s 8.5 and s 9. No clause was renumbered.

---

## 2. Turn record

| Turn | Persona | Issue | Outcome | Tally | Change |
|---|---|---|---|---|---|
| 1 | `electoral-administrator` | s 8.5 keyed the 48-hour clock to a "complete application" but required no completeness decision, so Commission silence could suspend the clock | approved | 4–1 | s 8.5: 24-hour completeness notice, deemed-complete default, fixed start point (9 lines) |
| 2 | `disinformation-researcher` | The four techniques do not reach transparently sourced but materially misleading numerical framing (the "9 new taxes" billboard) | rejected | 0–5 | s 8.3/8.9: proposed fifth technique and carve-back (8 lines) |
| 3 | `civil-libertarian` | Turn 1 left two 48-hour clocks, no resubmission rule, and a deemed code immune from takedown | approved | 5–0 | s 8.5: one applicable period, 24-hour correction, one incompleteness notice, deemed-code register/review/takedown (18 lines) |
| 4 | `constitutional-lawyer` | s 9 said "an independent court" while ss 7.6 and 8.10 said the High Court | approved | 5–0 | s 9: "the High Court" (2 lines) |

Per-turn files: `deliberation/turn-00N-persona-*.md`. Votes: `deliberation/votes/`.
Tallies: `deliberation/turn-00N-vote-summary.json`.

---

## 3. What changed

**v0.10 (turn 1).** s 8.5 gains a 24-hour duty to tell an applicant whether an application
is complete, a default that an application not rejected as incomplete is complete, and a
fixed start point for the 48-hour decision. The purpose is to stop silence defeating the
deemed-approval safeguard.

**v0.10.1 (turn 3).** s 8.5 is rewritten to have one applicable 48-hour period: 48 hours
from receipt, or, where an incompleteness notice has been given, 48 hours from the
corrected application. An applicant has 24 hours to correct; the correction keeps the
original date for the five-working-day lead time; the Commission may reject as incomplete
only once and only on the s 8.5(2) matters. New s 8.5(8) makes a deemed code a registered
and reviewed code, and applies s 8.8(2) takedown as if the advertising had not been
pre-cleared.

**v0.10.2 (turn 4).** s 9 names the High Court as the forum for disqualification, matching
ss 7.6 and 8.10.

---

## 4. What was rejected

Turn 2 proposed a fifth prescribed technique, "deceptive numerical framing", and a
conforming carve-out from the s 8.9 "primarily informational" exclusion. It was rejected
0–5. The panel accepted the harm but not the instrument:

- applying it requires the Commission to decide whether measures count as "new taxes",
  which baseline is fair, and what context a viewer "needs" — contested policy
  characterisation, contrary to s 2;
- "calculated to create" is an objective-tendency formula, not intent, and "materially
  false impression" is undefined; s 6 NZBORA would push a court to read the technique
  down;
- the technique does not fit the genus of the list (source/nature) or the s 8.12
  justification (techniques that bypass conscious evaluation);
- the s 8.9 carve-out removes the "selective or one-sided" protection and is circular in
  operation;
- it is inconsistent with s 7.5's protection for contested factual claims about a vote;
- it imposes pre-clearance and self-classification risk on the cheapest speech a small
  party has.

The preferred alternative, recorded in `deliberation/turn-002-rejection.md` on the
rejected branch, is an objective basis-disclosure duty (figures, source, base period,
inclusions) self-certified through the promoter statement and verified by post-publication
correction, or a narrow Q5 offence of knowingly false statements of fact about a rival's
platform. The rejected branch is preserved as `rejected/turn-002`.

---

## 5. Open items

The session converged on drafting, not on the whole proposal. The following are recorded,
not resolved.

**From turn 1 and turn 3 (s 8.5).**

- A lapse rule is missing where an applicant does not correct within 24 hours: no clock
  runs and no deemed grant occurs. The applicant should be able to resubmit without
  losing the s 8.5(1) lead time.
- The text should state expressly that a deemed code is pre-clearance for s 8.6, so
  s 8.6(1) cannot be read to prosecute a promoter who holds one.
- s 8.6(2) platform immunity still applies to a deemed code; the disinformation-researcher
  regards this as a residual gap (takedown is available, immunity is not removed).
- The s 8.12 s 5 analysis still says delay converts to permission; it should acknowledge
  that a deemed code can be taken down under s 8.8(2).
- "Receiving an application" and the notice channel are undefined.

**From turn 4 (s 9).**

- The serious-breach bullet still refers to "referral to an independent court"; reconcile
  it with the High Court formula.
- A disqualification order has no stated applicant, procedure, standard of proof, maximum
  term, or appeal route. ss 7.6 and 8.10 place it in a penalties list; s 9 now presupposes
  a civil full hearing. Clarify which it is.
- State the relationship with the Electoral Act 1993 disqualification provisions.

**Open questions (`archive/questions.md`).** Q4 is answered for the numerical-framing
instrument only; Q5 (a narrow offence) is now the more promising route and remains open.
Q3 (reach threshold for paid digital pre-clearance), Q1/Q2 (donation cap/vouchers and the
spending ceiling figure), Q6 (voucher cost), Q7 (board appointments), and Q8 (voting rules)
remain open.

---

## 6. Did the proof of concept work?

**What worked.**

- `taskpods start` created isolated worktrees and branches from `main`; `taskpods abort`
  closed them cleanly. The sequential, one-branch-at-a-time design was easy to hold.
- Every proposal, vote, interim state, rejection note, and tally is a committed file. The
  process can be killed at any point and resumed from `state.json` plus the turn files.
- Voting by five separate persona instances produced real disagreement. Turn 1's dissent
  identified a defect that turn 3 then fixed. Turn 2's rejection was unanimous and
  included the proposer voting against its own drafting, which is the behaviour the design
  wanted.
- The convergence rule stopped the session at 4 rather than 10, and the stop was
  justified: the last two proposals were small, unanimous, and consistency-improving.

**Deviations from the agreed design.**

- The proposer ran as the orchestrator adopting the persona inside the pod, rather than
  via `taskpods start turn-NNN --agent "dsh ..."`. `dsh headless` exists, but no headless
  profile was configured for this session. The lifecycle, branch, commit, and persistence
  requirements were met; the agent-launch mechanism can be swapped in without changing
  the protocol.
- Voters were separate DSH subagent instances, each with its own persona prompt and its
  own committed vote file. This is the substance of "separate DSH instances", but it is
  not literally five `dsh` CLI processes.
- `taskpods done` was not used. It unconditionally pushes to `origin`, and this repository
  has no push credentials; publishing unreviewed policy changes was out of scope. Approved
  turns were merged locally with `--no-ff`, then the pod was aborted. Rejected turns kept
  their branch under `rejected/`.

**Limitations.**

- All five personas are the same model family with different prompts. Correlation is
  likely; five votes are not five independent legal opinions.
- There was no human gate before merge. The session converged on drafting that had to be
  fixed two turns later (turn 1's 48/72-hour ambiguity), which is evidence of
  self-correction but also of the risk of merging plausible text.
- No external legal verification was performed. The proposal's citations and the
  interaction with the Electoral Act 1993, the Crimes Act 1961, and NZBORA would need
  Parliamentary Counsel and, ideally, expert review.
- The panel did not address the money-in-politics clauses, the portal, or the oversight
  board. The session is a proof of concept for the loop, not a full review of the
  proposal.

---

## 7. Recommendation for the next session

1. Do not re-propose numerical framing as a pre-clearance technique. If Q4 is revisited,
   use the basis-disclosure model or the Q5 offence, and record the turn 2 rejection as
   the boundary.
2. Fix the s 8.5 residual conditions in one turn (lapse rule, deemed-code status under
   s 8.6, notice channel, s 8.12 analysis), and the s 9 applicant/procedure gap in
   another.
3. Put a human sign-off gate before merging approved turns. The turn 1 → turn 3 sequence
   shows the loop can repair its own errors, but a human can catch them earlier.
4. If the literal `taskpods --agent "dsh ..."` flow is required, configure a headless
   profile and swap it in; otherwise document subagent voting as the implemented variant.
5. Keep the ceiling at 10 and the convergence rule at two consecutive unanimous minor
   approvals. They worked.

---

## 8. Commit map

| Commit | Meaning |
|---|---|
| `0c3de44` | Bootstrap v0.9 baseline and deliberation scaffolding |
| `ce78a11` | Merge turn 1 |
| `d5643fc` | Record turn 1; v0.10 |
| `404d08c` | Record turn 2 rejected; Q4/Q5 status |
| `60eda3f` | Merge turn 3 |
| `0aaedf9` | Record turn 3; v0.10.1 |
| `e7131a3` | Merge turn 4 |
| this commit | Record turn 4; v0.10.2; convergence; final report |

Rejected branch: `rejected/turn-002` (contains the proposal, votes, and rejection note).
