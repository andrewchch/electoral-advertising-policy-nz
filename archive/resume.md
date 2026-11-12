# Resume Block — paste at the start of a new chat

**Project:** A Fair and Transparent Electoral Information Marketplace (NZ policy proposal)
**Current version:** 0.10.2, dated 13 November 2026
**Files held:** proposal.md · archive/changelog.md · archive/questions.md · archive/resume.md

**Structure (11 clauses):**
1 Principles · 2 Public Information Portal · 3 Multi-Party Oversight Board ·
4 Equitable Access · 5 Regulation of Independent Promotion · 6 Money in Politics ·
7 Protection of Electoral Deliberation · 8 Regulation of Electoral Advertising ·
9 Proportional Enforcement · 10 Legal Safeguards and Review · 11 Justification and Evidence

**Position in one line:** A tiered regime — self-certification for ordinary political
advertising, pre-clearance only for four enumerated manipulative techniques, correction as
the default remedy, distributed oversight, and money-in-politics reform (donation cap,
lower spending ceiling, vouchers).

**Constraints to observe:**
- Cite New Zealand authority only (NZBORA, Electoral Act 1993, Crimes Act 1961,
  Broadcasting Act 1989, *Electoral Commission v Watson*).
- No references to earlier drafts inside proposal.md.
- Keep clause numbering stable; if renumbering, log the mapping in changelog.md.

**Last decision made:** deliberation session 1 (turns 1–4) merged and converged at
v0.10.2. s 8.5 now has one pre-clearance decision period, a 24-hour correction and
resubmission rule, a single incompleteness notice, and deemed-code register/review/takedown
safeguards; s 9 names the High Court for disqualification. The proposed fifth technique
(deceptive numerical framing) was rejected 0–5: Q4 is answered for that instrument, and Q5
is now the more promising route.

**Next three open questions:**
1. Q5: is a narrow offence of knowingly false statements of fact about a rival's platform
   the right route to the "9 new taxes" problem, now that pre-clearance of numerical
   framing has been rejected?
2. Q3: what reach/spend threshold triggers paid digital pre-clearance?
3. Q1/Q2: commit to donation cap and vouchers as a package, and what is the spending
   ceiling figure?

**Working method:** iterate clause by clause ("rewrite s 8.5"), not document by document.

---

## Multi-agent deliberation

The repository also holds a persisted multi-agent deliberation loop. On resume:

> Read `deliberation/state.json` and the most recent turn files. Continue from the
> current state.

`deliberation/protocol.md` is the operating manual; `deliberation/personas.md` defines
the five voting personas. Every proposal, vote, and state transition is committed, so the
loop is safe to terminate at any point. Do not re-litigate a decided turn.

**Automated runner:** `python3 deliberation/orchestrate.py status` and
`python3 deliberation/orchestrate.py check` work as-is. The current state is `converged`,
so run `python3 deliberation/orchestrate.py new-session` before `run`. See
`deliberation/README.md` for the agent command, recovery, and tests.

**Session 1 status:** converged at turn 4 (ceiling 10). Three approved (turns 1, 3, 4),
one rejected (turn 2, archived on `rejected/turn-002`). The next persona, if the session is
resumed, is `small-party-organiser` at turn 5. Full report:
`deliberation/turn-004-final-report.md`.