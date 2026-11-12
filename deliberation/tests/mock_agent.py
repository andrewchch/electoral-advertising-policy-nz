#!/usr/bin/env python3
"""A deterministic stand-in for an agent, used by the orchestration tests.

It honours the documented environment contract:

* propose: append a marker to proposal.md and write the turn file.
* vote: write a vote JSON, approve unless MOCK_VOTE=reject.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def main() -> int:
    phase = os.environ["DELIBERATE_PHASE"]
    pod = Path(os.environ["DELIBERATE_POD"])
    turn = int(os.environ["DELIBERATE_TURN"])
    persona = os.environ["DELIBERATE_PERSONA"]

    if phase == "propose":
        proposal = pod / "proposal.md"
        text = proposal.read_text(encoding="utf-8")
        marker = f"<!-- mock turn {turn:03d} -->"
        if marker not in text:
            proposal.write_text(text.rstrip() + "\n\n" + marker + "\n", encoding="utf-8")
        turn_file = pod / os.environ["DELIBERATE_TURN_FILE"]
        turn_file.parent.mkdir(parents=True, exist_ok=True)
        turn_file.write_text(
            f"""# Turn {turn:03d} — {persona}

- **Date:** 2026-11-13
- **Branch:** pods/turn-{turn:03d}
- **Base:** main

## Issue identified

Mock issue for orchestration testing.

## Proposed change

Append a mock marker to proposal.md.

## Reasoning

This is a test fixture; the marker exercises the commit, diff, and tally paths.

## Risks and counter-arguments

None: the mock changes no real clause.

## Open questions touched

None.
""",
            encoding="utf-8",
        )
        return 0

    if phase == "vote":
        vote = os.environ.get("MOCK_VOTE", "approve")
        if vote not in {"approve", "reject", "abstain"}:
            vote = "approve"
        vote_file = pod / os.environ["DELIBERATE_VOTE_PATH"]
        vote_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "turn": turn,
            "persona": persona,
            "vote": vote,
            "confidence": "high",
            "minor": True,
            "reason": f"Mock {vote} from {persona} for turn {turn}.",
            "conditions": [],
        }
        vote_file.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 0

    raise SystemExit(f"unknown phase: {phase}")


if __name__ == "__main__":
    raise SystemExit(main())
