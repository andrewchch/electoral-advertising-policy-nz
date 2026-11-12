# Turn 000 — Bootstrap

- **Date:** 2026-11-13
- **Status:** complete (setup only; not a proposal)

## What was set up

The proposal is at v0.9 (12 November 2026). This commit places the proposal, the archive,
and the deliberation scaffolding under version control so that the first taskpods branch
starts from a clean, complete baseline.

Decisions taken before turn 1:

- **Panel:** five personas (`personas.md`). The first proposer is
  `electoral-administrator`, following the rotation in `state.json`.
- **Voting:** all five personas vote on every proposal; quorum 4; simple majority of
  votes cast; abstentions excluded; ties fail. The proposer has no casting vote.
- **Persistence:** one turn file per proposal, one vote JSON per persona, one vote
  summary per turn, all committed on the pod branch. `state.json` is the cursor and is
  committed at every transition.
- **Merge:** approved turns merge locally to `main` with `--no-ff`. `taskpods done` is
  not used because it pushes to `origin` and the local repository has no push
  credentials; publishing unreviewed policy changes is outside this proof of concept.
- **Stopping:** hard ceiling of 10 turns; early stop after two consecutive unanimous
  approvals of minor edits (one clause, fewer than 40 changed lines). `state.json` holds
  both values.
- **Hygiene:** `.venv/`, `.dsh/`, and `.taskpods/` are ignored. The private drafting
  transcript is not present and must not be added.

## Open questions at the start

Q1–Q8 in `archive/questions.md`. Q4 and Q5 (whether to extend the prescribed techniques
list to numerical or visual framing) are the central unresolved design questions. Q3 (the
reach threshold for paid digital pre-clearance) is also expected to surface early.

## First turn

`electoral-administrator` opens turn 1 on branch `pods/turn-001`.
