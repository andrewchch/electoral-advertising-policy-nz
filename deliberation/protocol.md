# Deliberation Protocol

A proof-of-concept for improving the proposal through structured multi-agent
deliberation. One persona proposes at a time on an isolated branch; every persona
votes; approved changes merge to `main`; rejected changes are preserved and archived.

This file is the operating manual. `state.json` is the live cursor. Anything a future
session needs is committed here, not held in chat.

---

## 1. Panel

Five fixed personas are defined in `personas.md`:

1. `electoral-administrator`
2. `disinformation-researcher`
3. `civil-libertarian`
4. `constitutional-lawyer`
5. `small-party-organiser`

The rotation is fixed in `state.json`. Each turn has exactly one proposer. All five
personas vote on every proposal, including the proposer.

Personas are lenses, not factions. They share the proposal's stated objectives but
weigh rights, administrability, and effectiveness differently. A vote must be reasoned
from the persona's stated mandate, not from a general preference for change or stability.

---

## 2. State machine

```
ready ──► proposing ──► voting ──► approved ──► merged ──► ready
                            │
                            └────────► rejected ──► archived ──► ready
```

`state.json` fields:

| Field | Meaning |
|---|---|
| `status` | `ready`, `proposing`, `voting`, `approved`, `rejected`, `merged`, `converged`, `stopped` |
| `active_persona` | persona for the next proposal |
| `pending_vote` | `null`, or `{turn, proposal, branch, base}` while a vote is open |
| `last_merged_turn` | highest turn merged to `main` |
| `last_turn` | highest turn opened, merged or rejected |
| `next_turn` | next turn number to open |
| `turn_ceiling` | hard stop (10) |
| `convergence` | consecutive unanimous minor approvals and threshold |
| `history` | one compact record per turn |

Only the orchestrator writes `state.json`. Voters never edit it.

---

## 3. Turn procedure

For turn `N`:

1. Read `state.json` and the most recent turn file. Confirm `status` is `ready` and the
   proposer is `active_persona`.
2. `taskpods start turn-NNN --base main` from the repo root. Work only inside
   `.taskpods/turn-NNN`.
3. Adopt the persona in `personas.md`. Read `proposal.md` and the open questions in
   `archive/questions.md`. Identify **one** issue, stated as a concrete drafting problem,
   not a general theme.
4. Make the smallest change that fixes the issue. Prefer a single clause or sub-clause.
   Do not renumber clauses. If renumbering is unavoidable, add the mapping to
   `archive/changelog.md` in the same commit.
5. Write `deliberation/turn-NNN-persona-<persona>.md` using the template below.
6. Set `state.json` to `proposing` with `pending_vote` populated, then commit on the
   pod branch:
   `git add -A && git commit -m "turn NNN: <persona> — <short issue>"`
7. Set `status` to `voting` and commit that state change (a separate, tiny commit makes
   the transition visible in history).

### Turn file template

```markdown
# Turn NNN — <persona>

- **Date:** YYYY-MM-DD
- **Branch:** pods/turn-NNN
- **Base:** <main sha at branch point>

## Issue identified

One paragraph. What is wrong, where, and why it matters from this persona's perspective.
Quote the current text if useful.

## Proposed change

The exact replacement text, or a precise description of the edit. State the clause and
sub-clause.

## Reasoning

Why this change fixes the issue; why it is the smallest adequate change; what it does
not change. Note any NZ authority engaged (NZBORA 1990, Electoral Act 1993, Crimes Act
1961, Broadcasting Act 1989, *Electoral Commission v Watson*).

## Risks and counter-arguments

The strongest objection from another persona, and the response.

## Open questions touched

Q-numbers from `archive/questions.md`, if any.
```

---

## 4. Voting

Voting is by separate agent instances, one per persona. Each voter:

1. Reads `deliberation/personas.md` for its mandate.
2. Reads the turn file and `git diff main -- proposal.md`.
3. Checks the change against the proposal's constraints: NZ authority only, no earlier
   drafts referenced, clause numbering stable, and the clause's own safeguards.
4. Writes exactly one file, `deliberation/votes/turn-NNN-<persona>.json`, and changes
   nothing else.

Vote schema:

```json
{
  "turn": 1,
  "persona": "civil-libertarian",
  "vote": "approve",
  "confidence": "high",
  "minor": true,
  "reason": "Two to four sentences, reasoned from the persona's mandate.",
  "conditions": []
}
```

`vote` is `approve`, `reject`, or `abstain`. `minor` is the voter's own assessment of
whether the change is a minor edit (one clause, small line count). `conditions` is a
short list of changes that would move an abstain or reject to approve; it is advisory.

---

## 5. Tally and decision

- Quorum: at least 4 of 5 votes cast.
- Simple majority of votes cast, abstentions excluded: 3 of 5, or 3 of 4, approves.
- A tie fails. A proposal that fails is rejected.
- The orchestrator writes `deliberation/turn-NNN-vote-summary.json` with every vote,
  the tally, the changed-line count from `git diff --numstat main -- proposal.md`, the
  outcome, and the commit shas.
- The proposer does not get a casting vote.

`turn-NNN-vote-summary.json` is committed on the pod branch in both outcomes.

---

## 6. Merge or archive

**Approved.** Merge the pod branch to `main` with `--no-ff`, then record the merge in
`state.json` on `main` (`status: merged`, `last_merged_turn: N`, advance the rotation).
Delete the pod worktree and branch. Update `archive/changelog.md` with the change.
Bump the proposal version only for the first merged turn of a session (v0.9 → v0.10),
then use point releases (v0.10.1, v0.10.2).

**Rejected.** Do not merge. On the pod branch, add a short
`deliberation/turn-NNN-rejection.md` recording the deciding reasons and any conditions
that would allow a future proposal. Rename the branch `rejected/turn-NNN`, remove the
worktree, and keep the branch. Record the rejection in `state.json` on `main`. If the
rejection settles an open question, update `archive/questions.md` on `main` and link to
the archived branch.

Approved changes are merged locally. `taskpods done` is not used while the repository
has no push credentials: it unconditionally pushes to `origin`, and this proof of concept
must not publish unreviewed policy changes. The local merge plus `taskpods abort` (after
merge) gives the same code outcome without the remote side effect. When push access is
available, `taskpods done --no-pr` may replace the local merge for approved turns.

---

## 7. Persistence and resume

Everything needed to resume is committed:

```
deliberation/
  protocol.md
  personas.md
  state.json
  turn-000-bootstrap.md
  turn-001-persona-electoral-administrator.md
  turn-001-vote-summary.json
  votes/
    turn-001-electoral-administrator.json
    ...
  turn-002-...
```

Every commit on a pod branch is durable even if the worktree is removed. No proposal,
vote, or state transition exists only in chat.

**Resume instruction.** The first instruction to any new agent session is:

> Read `deliberation/state.json` and the most recent turn files. Continue from the
> current state.

Do not re-litigate a decided turn. If `pending_vote` is non-null, finish the vote before
opening a new turn. If a branch exists for an incomplete turn, inspect it before
starting a new one.

---

## 8. Stopping condition

Two-part, both recorded in `state.json`:

1. **Hard ceiling:** stop when `last_turn` reaches `turn_ceiling` (10).
2. **Convergence:** stop early when the last two consecutive proposals were approved
   unanimously (5–0, no abstentions) and each was minor (diff touches one clause and
   changes fewer than 40 lines in `proposal.md`).

On stopping, set `status` to `converged` or `stopped`, write
`deliberation/turn-NNN-final-report.md` summarising the session, and do not open another
turn without a human instruction.

The ceiling and the convergence rule are tunable after the first run. Change them in
`state.json` and record the reason in the changelog, not by editing this file silently.

---

## 9. Constraints (inherited from the proposal)

- Cite New Zealand authority only: NZBORA 1990, Electoral Act 1993, Crimes Act 1961,
  Broadcasting Act 1989, and *Electoral Commission v Watson*.
- `proposal.md` must not refer to earlier drafts.
- Clause numbers are stable. If renumbering is unavoidable, log the mapping in
  `archive/changelog.md`.
- Iterate clause by clause ("rewrite s 8.5"), not document by document.
- The private drafting transcript is not part of this repository and must not be added.

---

## 10. What this is not

This is not a consensus simulator. A rejection is a successful outcome: it records a
reasoned boundary and prevents a bad edit from merging. The point of the proof of concept
is to show that a sequential, branch-based, fully persisted deliberation loop can produce
reviewable decisions, not that every proposal should pass.

---

## 11. Automated mode

`deliberation/orchestrate.py` implements this protocol end to end. Its operating guide is
`deliberation/README.md`. The manual procedure above remains valid; the automated mode
changes the division of labour to make the loop crash-safe:

- The agent writes only `proposal.md` and the turn file (propose phase), or one vote JSON
  (vote phase). It does not edit `state.json` and does not commit.
- The orchestrator owns `state.json`, commits, the tally, the merge or archive, the
  version bump, and the changelog. It records `status: proposing` on `main` before the
  pod is created, so a crashed turn can be resumed by running `run` again.
- A missing or invalid vote is retried once. A vote is accepted only if its `turn` and
  `persona` match, its `vote` and `confidence` are in range, it has a non-empty `reason`,
  a boolean `minor`, and a list of `conditions`.
- `new-session` clears convergence and continues turn numbering; it does not delete turn
  files or reset `last_turn`.
- On stopping, the runner writes `deliberation/turn-NNN-final-report.md` automatically. The
  report is generated from committed state; the turn files and vote summaries remain the
  authoritative record.

The agent command is configurable (`--agent-cmd`) and receives the prompt through
`DELIBERATE_PROMPT_FILE`, so prompts are not re-parsed by the shell. The default is
`dsh headless "$(cat "$DELIBERATE_PROMPT_FILE")"`; a headless DSH profile must exist.
