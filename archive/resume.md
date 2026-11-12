# Resume Block — paste at the start of a new chat

**Project:** A Fair and Transparent Electoral Information Marketplace (NZ policy proposal)
**Current version:** 0.9, dated 12 November 2026
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

**Last decision made:** v0.9 consolidation and renumbering; pre-clearance narrowed to
prescribed techniques only.

**Next three open questions:**
1. Donation cap and vouchers — commit to both, or prioritise one?
2. Should the prescribed techniques list be extended to numerical/visual framing (would
   capture the "9 new taxes" billboard, but widens s 5 exposure)?
3. What reach/spend threshold triggers digital pre-clearance?

**Working method:** iterate clause by clause ("rewrite s 8.5"), not document by document.

---

## Multi-agent deliberation

The repository also holds a persisted multi-agent deliberation loop. On resume:

> Read `deliberation/state.json` and the most recent turn files. Continue from the
> current state.

`deliberation/protocol.md` is the operating manual; `deliberation/personas.md` defines
the five voting personas. Every proposal, vote, and state transition is committed, so the
loop is safe to terminate at any point. Do not re-litigate a decided turn.