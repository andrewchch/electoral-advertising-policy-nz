#!/usr/bin/env python3
"""Tests for deliberation/orchestrate.py.

Run with:

    python3 -m unittest discover -s deliberation/tests -v

The end-to-end tests create a throwaway git repository, copy the real
proposal and deliberation files into it, and drive the orchestrator with
deliberation/tests/mock_agent.py. No network or model calls are made.
"""

from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ORCH = ROOT / "deliberation" / "orchestrate.py"
MOCK = Path(__file__).resolve().parent / "mock_agent.py"

sys.path.insert(0, str(ROOT / "deliberation"))
import orchestrate  # noqa: E402


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=repo, text=True).strip()


class OrchestratorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.mkdtemp(prefix="deliberate-test-")
        self.repo = Path(self._tmp) / "repo"
        self.repo.mkdir(parents=True)
        self._make_repo()

    def tearDown(self) -> None:
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _make_repo(self, required: int = 2) -> None:
        shutil.copy2(ROOT / "proposal.md", self.repo / "proposal.md")
        shutil.copy2(ROOT / "LICENSE", self.repo / "LICENSE")
        shutil.copy2(ROOT / "README.md", self.repo / "README.md")
        shutil.copy2(ROOT / ".gitignore", self.repo / ".gitignore")
        shutil.copytree(ROOT / "archive", self.repo / "archive")
        (self.repo / "deliberation" / "votes").mkdir(parents=True)
        for name in ("personas.md", "protocol.md"):
            shutil.copy2(
                ROOT / "deliberation" / name,
                self.repo / "deliberation" / name,
            )
        (self.repo / "deliberation" / "votes" / ".gitkeep").touch()
        state = {
            "protocol_version": 1,
            "status": "ready",
            "active_persona": "electoral-administrator",
            "pending_vote": None,
            "last_merged_turn": 0,
            "last_turn": 0,
            "next_turn": 1,
            "turn_ceiling": 10,
            "convergence": {
                "consecutive_unanimous_minor": 0,
                "required": required,
                "minor_max_changed_lines": 40,
            },
            "rotation": [
                "electoral-administrator",
                "disinformation-researcher",
                "civil-libertarian",
                "constitutional-lawyer",
                "small-party-organiser",
            ],
            "history": [],
            "session": 1,
            "session_first_merge_pending": True,
            "updated_at": "2026-11-13T12:00:00+13:00",
        }
        (self.repo / "deliberation" / "state.json").write_text(
            json.dumps(state, indent=2) + "\n", encoding="utf-8"
        )
        subprocess.run(
            ["git", "init", "-q", "-b", "main"], cwd=self.repo, check=True
        )
        git(self.repo, "config", "user.email", "test@example.invalid")
        git(self.repo, "config", "user.name", "Deliberation Test")
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-q", "-m", "fixture")

    def _run(self, *args: str, mock_vote: str = "approve") -> subprocess.CompletedProcess:
        agent_cmd = f"{shlex.quote(sys.executable)} {shlex.quote(str(MOCK))}"
        env = os.environ.copy()
        env["MOCK_VOTE"] = mock_vote
        return subprocess.run(
            [
                sys.executable,
                str(ORCH),
                "--repo",
                str(self.repo),
                "--no-taskpods",
                "--agent-cmd",
                agent_cmd,
                *args,
            ],
            cwd=self.repo,
            env=env,
            text=True,
            capture_output=True,
        )

    def _state(self) -> dict:
        return json.loads((self.repo / "deliberation" / "state.json").read_text())

    def _summary(self, turn: int) -> dict:
        path = self.repo / f"deliberation/turn-{turn:03d}-vote-summary.json"
        return json.loads(path.read_text())

    def _assert_ok(self, proc: subprocess.CompletedProcess) -> None:
        if proc.returncode != 0:
            self.fail(
                f"command failed with {proc.returncode}\n"
                f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"
            )

    # -- unit ------------------------------------------------------------

    def test_bump_version(self) -> None:
        self.assertEqual(orchestrate.bump_version("0.10.2", "patch"), "0.10.3")
        self.assertEqual(orchestrate.bump_version("0.10.2", "minor"), "0.11.0")
        self.assertEqual(orchestrate.bump_version("0.10.2", "major"), "1.0.0")
        self.assertEqual(orchestrate.bump_version("0.10", "patch"), "0.10.1")
        self.assertEqual(orchestrate.bump_version("0.10.2", "none"), "0.10.2")

    def test_parse_personas(self) -> None:
        personas = orchestrate.parse_personas(ROOT)
        self.assertEqual(len(personas), 5)
        self.assertEqual(personas[0], "electoral-administrator")
        self.assertIn("constitutional-lawyer", personas)

    # -- end to end ------------------------------------------------------

    def test_approved_turn_merges_and_cleans_up(self) -> None:
        proc = self._run(
            "run", "--max-turns", "1", "--version-bump", "none", mock_vote="approve"
        )
        self._assert_ok(proc)
        state = self._state()
        self.assertEqual(state["last_merged_turn"], 1)
        self.assertEqual(state["last_turn"], 1)
        self.assertEqual(state["next_turn"], 2)
        self.assertEqual(state["status"], "ready")
        self.assertIn(
            "<!-- mock turn 001 -->",
            (self.repo / "proposal.md").read_text(),
        )
        summary = self._summary(1)
        self.assertEqual(summary["outcome"], "approved")
        self.assertEqual(summary["tally"], {"approve": 5, "reject": 0, "abstain": 0})
        self.assertTrue(summary["minor"])
        self.assertGreaterEqual(summary["changed_lines"]["total"], 1)
        self.assertLess(summary["changed_lines"]["total"], 40)
        self.assertEqual(len(summary["votes"]), 5)
        self.assertNotIn("pods/turn-001", git(self.repo, "branch", "--list", "pods/*"))
        self.assertFalse((self.repo / ".taskpods" / "turn-001").exists())

    def test_rejected_turn_is_archived_not_merged(self) -> None:
        proc = self._run(
            "run", "--max-turns", "1", "--version-bump", "none", mock_vote="reject"
        )
        self._assert_ok(proc)
        state = self._state()
        self.assertEqual(state["last_merged_turn"], 0)
        self.assertEqual(state["last_turn"], 1)
        self.assertEqual(state["status"], "ready")
        self.assertNotIn(
            "<!-- mock turn 001 -->",
            (self.repo / "proposal.md").read_text(),
        )
        branches = git(self.repo, "branch", "--list", "rejected/*")
        self.assertIn("rejected/turn-001", branches)
        summary = json.loads(
            git(
                self.repo,
                "show",
                "rejected/turn-001:deliberation/turn-001-vote-summary.json",
            )
        )
        self.assertEqual(summary["outcome"], "rejected")
        self.assertEqual(summary["tally"]["reject"], 5)
        note = git(
            self.repo,
            "show",
            "rejected/turn-001:deliberation/turn-001-rejection.md",
        )
        self.assertIn("Turn 001 — Rejection", note)
        self.assertIn("Mock reject", note)

    def test_convergence_stops_the_session(self) -> None:
        # Rebuild with a required convergence of one turn.
        shutil.rmtree(self.repo)
        self.repo.mkdir(parents=True)
        self._make_repo(required=1)
        proc = self._run(
            "run", "--max-turns", "1", "--version-bump", "none", mock_vote="approve"
        )
        self._assert_ok(proc)
        state = self._state()
        self.assertEqual(state["status"], "converged")
        self.assertEqual(state["last_merged_turn"], 1)
        self.assertIn("Convergence", state["stopped_reason"])
        report = self.repo / "deliberation" / "turn-001-final-report.md"
        self.assertTrue(report.exists())
        self.assertIn("Deliberation Session 1 — Final Report", report.read_text())
        self.assertEqual(
            state.get("final_report"), "deliberation/turn-001-final-report.md"
        )

    def test_new_session_advances_persona_and_turn(self) -> None:
        # One approved turn, then a new session.
        proc = self._run(
            "run", "--max-turns", "1", "--version-bump", "none", mock_vote="approve"
        )
        self._assert_ok(proc)
        proc = self._run("new-session")
        self._assert_ok(proc)
        state = self._state()
        self.assertEqual(state["status"], "ready")
        self.assertEqual(state["session"], 2)
        self.assertEqual(state["next_turn"], 2)
        self.assertEqual(state["active_persona"], "disinformation-researcher")
        self.assertEqual(state["last_merged_turn"], 1)
        self.assertEqual(state["session_start_turn"], 2)

    def test_check_reports_consistent_state(self) -> None:
        proc = self._run(
            "run", "--max-turns", "1", "--version-bump", "none", mock_vote="approve"
        )
        self._assert_ok(proc)
        proc = self._run("check")
        self._assert_ok(proc)
        self.assertIn("OK", proc.stdout)

    def test_parallel_votes(self) -> None:
        proc = self._run(
            "run",
            "--max-turns",
            "1",
            "--version-bump",
            "none",
            "--parallel-votes",
            mock_vote="approve",
        )
        self._assert_ok(proc)
        summary = self._summary(1)
        self.assertEqual(summary["tally"]["approve"], 5)
        self.assertEqual(self._state()["last_merged_turn"], 1)

    def test_auto_version_bump(self) -> None:
        proc = self._run("run", "--max-turns", "1", "--version-bump", "auto")
        self._assert_ok(proc)
        header = (self.repo / "proposal.md").read_text().splitlines()[2]
        self.assertIn("0.11.0", header)
        changelog = (self.repo / "archive" / "changelog.md").read_text()
        self.assertIn("v0.11.0", changelog)
        self.assertIn("deliberation turn 1", changelog)

    def test_dry_run_does_not_mutate(self) -> None:
        before = (self.repo / "deliberation" / "state.json").read_text()
        proc = self._run("run", "--dry-run")
        self._assert_ok(proc)
        self.assertIn("You are the **electoral-administrator** persona", proc.stdout)
        after = (self.repo / "deliberation" / "state.json").read_text()
        self.assertEqual(before, after)
        self.assertFalse((self.repo / ".taskpods" / "turn-001").exists())
        self.assertNotIn(
            "pods/turn-001", git(self.repo, "branch", "--list", "pods/*")
        )


if __name__ == "__main__":
    unittest.main()
