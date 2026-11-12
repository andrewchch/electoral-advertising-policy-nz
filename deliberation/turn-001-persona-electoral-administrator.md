# Turn 001 — electoral-administrator

- **Date:** 2026-11-13
- **Branch:** pods/turn-001
- **Base:** 0c3de44 (bootstrap commit on `main`)

## Issue identified

Section 8.5 is built around a "complete application" but never says who decides that an
application is complete, or when. Sub-clause 3 requires a decision "within 48 hours of a
complete application" and sub-clause 5 deems the application granted if no decision is
made within 48 hours. If the Commission says nothing, the applicant cannot tell whether
the clock has started, whether the application is being sat on as incomplete, or whether
the deemed-approval rule will ever operate. Silence becomes a way to defeat the very
safeguard that s 8.12 says converts delay from suppression into permission. A
pre-clearance applicant who has complied with the five-working-day lead time can be left
unable to publish, with no decision and no reviewable event.

This is an administrative gap, not a policy disagreement: the scheme's own logic requires
a completeness gate with a deadline and a default.

## Proposed change

Replace s 8.5(3) and amend s 8.5(5):

> 3. The Commission must, within 24 hours of receiving an application, notify the applicant
>    whether it is complete and, if not, what is missing. An application not rejected as
>    incomplete within that period is deemed complete. The Commission must decide a complete
>    application within 48 hours of receiving it.
>
> 5. If no decision is made within 48 hours of a complete application, the application is
>    deemed granted and a code issued immediately.

No other provision changes; sub-clause numbering is unchanged.

## Reasoning

The amendment supplies the missing trigger for the existing clock. Three elements do the
work:

- a 24-hour duty to notify completeness, with reasons for any deficiency;
- a default that silence makes the application complete, so the Commission cannot suspend
  the 48-hour period by failing to engage; and
- an express start time ("of receiving it") for the 48-hour decision period.

The substantive test for granting, conditioning, or refusing is untouched. The Commission
retains the power to refuse an application that is complete but deficient on the merits
under sub-clause 4. The 5-working-day lead time in sub-clause 1 remains, so a 24-hour
completeness check does not shorten the promoter's preparation period; it only protects
the promoter from administrative silence.

The change strengthens rather than limits expression. Section 14 NZBORA is engaged by any
pre-publication requirement; a clear, enforceable decision clock is part of what makes the
prior restraint proportionate under s 5. It is also consistent with the s 8.12
explanatory note's account of the deemed-approval rule.

## Risks and counter-arguments

*The Commission may not staff a 24-hour completeness desk, especially over a weekend, and
a weekend application could be deemed complete and then deemed granted without effective
review.* The 48-hour decision clock already has that consequence; the answer is staffing
and automation, not an open-ended completeness discretion. The 24-hour notice can be
largely automated (a checklist receipt), and the Commission can still refuse on the merits
within the 48 hours. If the select committee prefers, "24 hours" could become "1 working
day", but that would weaken the safeguard and should be a deliberate choice, not an
accident of drafting.

## Open questions touched

None directly. Q3 (the reach threshold for paid digital pre-clearance) is adjacent but not
resolved here.
