#!/usr/bin/env python3
"""
orchestrate.py — run the persisted multi-agent deliberation loop.

This is the repeatable version of the manual process used for session 1:
one persona proposes on a taskpods worktree, five persona instances vote,
the orchestrator tallies, merges approved turns to main, and archives
rejected turns on a ``rejected/`` branch. All decisions are committed.

The script is deliberately dependency-free (Python 3.9+ standard library).
It uses ``taskpods`` when available and falls back to plain ``git worktree``.

Agent contract
--------------
The agent command is run inside the pod with these environment variables:

    DELIBERATE_PROMPT       full prompt text
    DELIBERATE_PROMPT_FILE  path to the same prompt
    DELIBERATE_PHASE        "propose" or "vote"
    DELIBERATE_TURN         turn number
    DELIBERATE_PERSONA      persona name
    DELIBERATE_POD          pod path
    DELIBERATE_TURN_FILE    expected turn file path (relative to pod)
    DELIBERATE_VOTE_PATH    expected vote path (relative to pod, vote phase only)

The default command is::

    dsh headless "$(cat "$DELIBERATE_PROMPT_FILE")"

Override it with ``--agent-cmd`` if your agent CLI differs, for example::

    --agent-cmd 'claude -p "$(cat "$DELIBERATE_PROMPT_FILE")"'
    --agent-cmd 'codex exec "$(cat "$DELIBERATE_PROMPT_FILE")"'
    --agent-cmd 'python3 deliberation/tests/mock_agent.py'

The prompt is passed through a file, not through shell interpolation, so
backticks and dollar signs in a prompt are safe.

Usage
-----
    python deliberation/orchestrate.py status
    python deliberation/orchestrate.py check
    python deliberation/orchestrate.py new-session
    python deliberation/orchestrate.py run --max-turns 1
    python deliberation/orchestrate.py run --max-turns 0   # until convergence/ceiling
    python deliberation/orchestrate.py run --dry-run

``run`` runs one turn by default. Use ``--max-turns N`` for more, or
``--max-turns 0`` to run until the session converges or hits the ceiling.

Approved turns are merged locally with ``--no-ff``; ``taskpods done`` is not
used because it pushes to ``origin``. Nothing is pushed by this script.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover - Python < 3.9 fallback
    ZoneInfo = None  # type: ignore


# ---------------------------------------------------------------------------
# Constants and small helpers
# ---------------------------------------------------------------------------

MONTHS = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

DEFAULT_PERSONAS = [
    "electoral-administrator",
    "disinformation-researcher",
    "civil-libertarian",
    "constitutional-lawyer",
    "small-party-organiser",
]

PERSONA_RE = re.compile(r"^##\s+\d+\.\s+`([a-z0-9-]+)`\s*$", re.M)
VERSION_RE = re.compile(r"\*\*Version\s+([0-9]+(?:\.[0-9]+){1,2})\s+—\s+(.+?)\*\*")
CLAUSE_RE = re.compile(r"^##\s+(\d+)\.\s")
HUNK_RE = re.compile(r"^@@\s+-(\d+)(?:,(\d+))?\s+\+(\d+)(?:,(\d+))?\s+@@", re.M)


class OrchestrationError(RuntimeError):
    """A recoverable orchestration error with a human-readable message."""


def now_nz() -> datetime.datetime:
    if ZoneInfo is not None:
        try:
            return datetime.datetime.now(ZoneInfo("Pacific/Auckland"))
        except Exception:
            pass
    return datetime.datetime.now().astimezone()


def today_nz() -> str:
    d = now_nz()
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def iso_now() -> str:
    return now_nz().isoformat(timespec="seconds")


def log(msg: str) -> None:
    print(msg, flush=True)


def run(
    cmd: Sequence[str],
    cwd: Optional[Path] = None,
    check: bool = True,
    capture: bool = True,
    timeout: Optional[float] = None,
) -> subprocess.CompletedProcess:
    try:
        proc = subprocess.run(
            list(cmd),
            cwd=str(cwd) if cwd else None,
            check=False,
            text=True,
            capture_output=capture,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise OrchestrationError(f"command not found: {cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise OrchestrationError(
            f"command timed out after {timeout}s: {' '.join(cmd)}"
        ) from exc
    if check and proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        if len(detail) > 2000:
            detail = detail[-2000:]
        raise OrchestrationError(
            f"command failed ({proc.returncode}): "
            f"{' '.join(shlex.quote(c) for c in cmd)}"
            + (f"\n{detail}" if detail else "")
        )
    return proc


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    return run(["git", *args], cwd=repo, check=check)


def git_out(repo: Path, *args: str) -> str:
    return git(repo, *args).stdout.strip()


def git_ok(repo: Path, *args: str) -> bool:
    return git(repo, *args, check=False).returncode == 0


def read_json(path: Path) -> Dict[str, Any]:
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError as exc:
        raise OrchestrationError(f"missing file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise OrchestrationError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise OrchestrationError(f"expected a JSON object in {path}")
    return data


def write_json(path: Path, data: Dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)
        f.write("\n")


def bump_version(version: str, kind: str) -> str:
    if kind == "none":
        return version
    parts = [int(p) for p in version.split(".")]
    while len(parts) < 3:
        parts.append(0)
    if kind == "patch":
        parts[2] += 1
    elif kind == "minor":
        parts[1] += 1
        parts[2] = 0
    elif kind == "major":
        parts[0] += 1
        parts[1] = 0
        parts[2] = 0
    else:
        raise OrchestrationError(f"unknown version bump: {kind}")
    return ".".join(str(p) for p in parts)


def parse_personas(repo: Path) -> List[str]:
    path = repo / "deliberation" / "personas.md"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return list(DEFAULT_PERSONAS)
    found = PERSONA_RE.findall(text)
    return found or list(DEFAULT_PERSONAS)


def persona_section(repo: Path, persona: str) -> str:
    path = repo / "deliberation" / "personas.md"
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return ""
    pattern = re.compile(rf"^##\s+\d+\.\s+`{re.escape(persona)}`\s*$", re.M)
    match = pattern.search(text)
    if not match:
        return ""
    rest = text[match.end():]
    end = re.search(r"^---\s*$|^##\s+\d+\.", rest, re.M)
    return rest[: end.start()].strip() if end else rest.strip()


def default_state(personas: Sequence[str]) -> Dict[str, Any]:
    return {
        "protocol_version": 1,
        "status": "ready",
        "active_persona": personas[0],
        "pending_vote": None,
        "last_merged_turn": 0,
        "last_turn": 0,
        "next_turn": 1,
        "turn_ceiling": 10,
        "convergence": {
            "consecutive_unanimous_minor": 0,
            "required": 2,
            "minor_max_changed_lines": 40,
        },
        "rotation": list(personas),
        "history": [],
        "session": 1,
        "session_first_merge_pending": True,
        "updated_at": iso_now(),
    }


def normalize_state(state: Dict[str, Any], personas: Sequence[str]) -> Dict[str, Any]:
    base = default_state(personas)
    for key, value in base.items():
        state.setdefault(key, value)
    if not isinstance(state.get("convergence"), dict):
        state["convergence"] = dict(base["convergence"])
    for key, value in base["convergence"].items():
        state["convergence"].setdefault(key, value)
    if not isinstance(state.get("history"), list):
        state["history"] = []
    if not state.get("rotation"):
        state["rotation"] = list(personas)
    return state


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------


class Orchestrator:
    def __init__(
        self,
        repo: Path,
        agent_cmd: str,
        voters: int,
        timeout: float,
        use_taskpods: bool,
        verbose: bool = False,
    ) -> None:
        self.repo = repo.resolve()
        self.state_path = self.repo / "deliberation" / "state.json"
        self.agent_cmd = agent_cmd
        self.voters = voters
        self.timeout = timeout
        self.use_taskpods = use_taskpods
        self.verbose = verbose
        self.personas = parse_personas(self.repo)
        if self.voters > len(self.personas):
            raise OrchestrationError(
                f"--voters {self.voters} exceeds the {len(self.personas)} "
                "personas in personas.md"
            )
        self.state = self.load_state()

    # -- state ------------------------------------------------------------

    def load_state(self, path: Optional[Path] = None) -> Dict[str, Any]:
        target = path or self.state_path
        if not target.exists():
            raise OrchestrationError(f"state file not found: {target}")
        state = normalize_state(read_json(target), self.personas)
        if path is None:
            self.state = state
        return state

    def save_state(
        self,
        state: Optional[Dict[str, Any]] = None,
        path: Optional[Path] = None,
    ) -> None:
        state = state or self.state
        state["updated_at"] = iso_now()
        write_json(path or self.state_path, state)

    # -- git and pods -----------------------------------------------------

    def require_clean_main(self) -> None:
        status = git_out(self.repo, "status", "--porcelain")
        if status:
            raise OrchestrationError(
                "the main worktree is not clean:\n" + status +
                "\nCommit or stash these changes before starting a turn."
            )

    def branch_exists(self, branch: str) -> bool:
        return git_ok(
            self.repo, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}"
        )

    def pod_path(self, turn: int) -> Path:
        return self.repo / ".taskpods" / f"turn-{turn:03d}"

    def pod_branch(self, turn: int) -> str:
        return f"pods/turn-{turn:03d}"

    def rejected_branch(self, turn: int) -> str:
        return f"rejected/turn-{turn:03d}"

    def _taskpods_exe(self) -> Optional[str]:
        if not self.use_taskpods:
            return None
        local = self.repo / ".venv" / "bin" / "taskpods"
        if local.exists():
            return str(local)
        return shutil.which("taskpods")

    def start_pod(self, turn: int) -> Path:
        name = f"turn-{turn:03d}"
        pod = self.pod_path(turn)
        branch = self.pod_branch(turn)
        if pod.exists():
            raise OrchestrationError(
                f"pod already exists: {pod}\n"
                "If a previous turn crashed, inspect it or remove it with "
                f"`git worktree remove --force {pod}`."
            )
        if self.branch_exists(branch):
            raise OrchestrationError(f"branch already exists: {branch}")
        self.require_clean_main()

        exe = self._taskpods_exe()
        if exe:
            log(f"[pod] taskpods start {name}")
            proc = run(
                [exe, "start", name, "--base", "main", "--agent", "true"],
                cwd=self.repo,
                check=False,
                timeout=self.timeout,
            )
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout or "").strip()
                raise OrchestrationError(
                    f"taskpods start failed ({proc.returncode}): {detail}\n"
                    "Retry with --no-taskpods to use plain git worktree."
                )
        else:
            log(f"[pod] git worktree add -b {branch} {pod} main")
            git(self.repo, "worktree", "add", "-b", branch, str(pod), "main")

        if not pod.exists():
            raise OrchestrationError(f"pod was not created: {pod}")
        return pod

    def remove_pod(self, turn: int, delete_branch: bool = False) -> None:
        pod = self.pod_path(turn)
        branch = self.pod_branch(turn)
        if pod.exists():
            log(f"[pod] removing {pod}")
            git(self.repo, "worktree", "remove", "--force", str(pod), check=False)
        if delete_branch and self.branch_exists(branch):
            git(self.repo, "branch", "-D", branch, check=False)

    def archive_rejected_branch(self, turn: int) -> None:
        pod = self.pod_path(turn)
        branch = self.pod_branch(turn)
        target = self.rejected_branch(turn)
        if pod.exists():
            git(self.repo, "worktree", "remove", "--force", str(pod), check=False)
        if self.branch_exists(target):
            if self.branch_exists(branch):
                git(self.repo, "branch", "-D", branch, check=False)
            return
        if self.branch_exists(branch):
            git(self.repo, "branch", "-m", branch, target)
        else:
            raise OrchestrationError(
                f"cannot archive: neither {branch} nor {target} exists"
            )

    # -- agent ------------------------------------------------------------

    def run_agent(
        self, prompt: str, pod: Path, phase: str, turn: int, persona: str
    ) -> str:
        env = os.environ.copy()
        turn_persona = persona
        if phase == "vote":
            turn_persona = (self.state.get("pending_vote") or {}).get(
                "persona", persona
            )
        env.update(
            {
                "DELIBERATE_PROMPT": prompt,
                "DELIBERATE_PHASE": phase,
                "DELIBERATE_TURN": str(turn),
                "DELIBERATE_PERSONA": persona,
                "DELIBERATE_POD": str(pod),
                "DELIBERATE_TURN_FILE": self.turn_file_rel(turn, turn_persona),
                "DELIBERATE_VOTE_PATH": self.vote_rel(turn, persona),
            }
        )
        fd, tmp_name = tempfile.mkstemp(prefix=f"deliberate-{phase}-", suffix=".txt")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(prompt)
            env["DELIBERATE_PROMPT_FILE"] = tmp_name
            cmd = self.agent_cmd
            if "{prompt_file}" in cmd:
                cmd = cmd.replace("{prompt_file}", shlex.quote(tmp_name))
            if "{pod}" in cmd:
                cmd = cmd.replace("{pod}", shlex.quote(str(pod)))
            if self.verbose:
                log(f"[agent] {phase} {persona} in {pod}")
                log(f"[agent] $ {cmd}")
            try:
                proc = subprocess.run(
                    cmd,
                    shell=True,
                    cwd=str(pod),
                    env=env,
                    text=True,
                    capture_output=True,
                    timeout=self.timeout,
                )
            except subprocess.TimeoutExpired as exc:
                raise OrchestrationError(
                    f"agent timed out after {self.timeout}s during {phase} "
                    f"for {persona}"
                ) from exc
        finally:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass

        if proc.returncode != 0:
            detail = (proc.stderr or proc.stdout or "").strip()
            if len(detail) > 3000:
                detail = detail[-3000:]
            raise OrchestrationError(
                f"agent failed ({proc.returncode}) during {phase} for {persona}:\n"
                f"{detail}\nPod left at {pod}"
            )
        if self.verbose and proc.stdout.strip():
            log(proc.stdout.strip()[-2000:])
        return proc.stdout

    # -- paths ------------------------------------------------------------

    def turn_file_rel(self, turn: int, persona: str) -> str:
        return f"deliberation/turn-{turn:03d}-persona-{persona}.md"

    def vote_rel(self, turn: int, persona: str) -> str:
        return f"deliberation/votes/turn-{turn:03d}-{persona}.json"

    def summary_rel(self, turn: int) -> str:
        return f"deliberation/turn-{turn:03d}-vote-summary.json"

    def summary_for(self, turn: int, pod: Path) -> Dict[str, Any]:
        """Load a turn summary from the pod, main, or the rejected branch."""
        candidates = [
            pod / self.summary_rel(turn),
            self.repo / self.summary_rel(turn),
        ]
        for path in candidates:
            if path.exists():
                return read_json(path)
        branch = self.rejected_branch(turn)
        if self.branch_exists(branch):
            raw = git_out(self.repo, "show", f"{branch}:{self.summary_rel(turn)}")
            try:
                data = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise OrchestrationError(
                    f"invalid summary on {branch}: {exc}"
                ) from exc
            if isinstance(data, dict):
                return data
        raise OrchestrationError(f"cannot find a vote summary for turn {turn}")

    # -- prompts ----------------------------------------------------------

    def proposer_prompt(self, turn: int, persona: str, pod: Path) -> str:
        turn_file = self.turn_file_rel(turn, persona)
        brief = persona_section(self.repo, persona)
        base = git_out(self.repo, "rev-parse", "--short", "main")
        return f"""You are the **{persona}** persona in a structured policy deliberation.

Repository pod: {pod}
Turn: {turn}

Your mandate:
{brief}

Read these files before acting:
- deliberation/personas.md
- deliberation/protocol.md
- deliberation/state.json
- proposal.md
- archive/questions.md

Your task is to identify ONE concrete issue in the proposal from your persona's
perspective and make the smallest adequate change to proposal.md.

Rules:
- Cite New Zealand authority only: NZBORA 1990, Electoral Act 1993, Crimes Act 1961,
  Broadcasting Act 1989, and Electoral Commission v Watson.
- proposal.md must not refer to earlier drafts.
- Do not renumber clauses. If renumbering is unavoidable, stop and explain in the turn file.
- Change one clause or sub-clause; prefer fewer than 40 changed lines.
- Do not edit deliberation/state.json, the votes directory, or any file other than
  proposal.md and the turn file below.
- Do not commit. The orchestrator commits.

Write exactly one turn file: {turn_file}

Use this structure (fill every section):

# Turn {turn:03d} — {persona}

- **Date:** {today_nz()}
- **Branch:** {self.pod_branch(turn)}
- **Base:** {base}

## Issue identified

One paragraph: what is wrong, where, and why it matters from your persona's perspective.

## Proposed change

The exact replacement text, or a precise description of the edit.

## Reasoning

Why this fixes the issue, why it is the smallest adequate change, and what it does not
change. Note any NZ authority engaged.

## Risks and counter-arguments

The strongest objection from another persona, and the response.

## Open questions touched

Q-numbers from archive/questions.md, if any.

When finished, reply with a two-line summary: the issue and the change.
"""

    def voter_prompt(self, turn: int, persona: str, pod: Path) -> str:
        pending = self.state.get("pending_vote") or {}
        proposal_persona = pending.get("persona") or ""
        turn_file = self.turn_file_rel(turn, proposal_persona or persona)
        vote_file = self.vote_rel(turn, persona)
        brief = persona_section(self.repo, persona)
        return f"""You are the **{persona}** persona voting in a structured policy deliberation.

Repository pod: {pod}
Turn: {turn}

Your mandate:
{brief}

Read:
- deliberation/personas.md
- {turn_file}
- proposal.md
- Run `git diff main -- proposal.md` in the pod.

Decide approve, reject, or abstain. Judge from your persona's mandate, not from a general
preference for change or stability. Check the constraints: NZ authority only; no earlier
drafts referenced; clause numbering stable; the change is within the proposal's own logic.

Write exactly one file: {vote_file}

JSON schema (valid JSON, nothing else in the file):
{{"turn": {turn}, "persona": "{persona}", "vote": "approve|reject|abstain",
 "confidence": "high|medium|low", "minor": true|false,
 "reason": "at most 90 words, reasoned from the mandate", "conditions": []}}

Do not edit proposal.md, state.json, or any other file. Do not commit.
Return exactly one line: WROTE {vote_file} <vote>
"""

    # -- proposal phase ---------------------------------------------------

    def begin_turn(self, turn: int, persona: str) -> None:
        """Record 'proposing' on main before the pod is created.

        This is what makes a crashed turn resumable: the main state names the
        turn, persona, and branch even if the agent process dies.
        """
        state = self.load_state()
        state["status"] = "proposing"
        state["pending_vote"] = {
            "turn": turn,
            "persona": persona,
            "proposal": "",
            "branch": self.pod_branch(turn),
            "base": git_out(self.repo, "rev-parse", "--short", "main"),
        }
        self.save_state(state)
        git(self.repo, "add", "--", "deliberation/state.json")
        git(self.repo, "commit", "-m", f"turn {turn:03d}: start — {persona}")

    def run_proposal(
        self, turn: int, persona: str, pod: Path, dry_run: bool = False
    ) -> None:
        prompt = self.proposer_prompt(turn, persona, pod)
        if dry_run:
            log(f"[dry-run] proposer prompt for {persona} ({len(prompt)} chars) in {pod}")
            print(prompt)
            return
        log(f"[turn {turn}] proposer: {persona}")
        self.run_agent(prompt, pod, "propose", turn, persona)

        turn_rel = self.turn_file_rel(turn, persona)
        turn_path = pod / turn_rel
        if not turn_path.exists():
            raise OrchestrationError(
                f"proposer did not write {turn_rel}\nPod left at {pod}"
            )

        status = git_out(pod, "status", "--porcelain")
        allowed = {"proposal.md", turn_rel}
        unexpected = []
        for line in status.splitlines():
            # git_out() strips the whole output, so the first line may have
            # lost its leading status space. The path starts after the two
            # status characters.
            path = line[2:].strip() if len(line) > 2 else ""
            if not path or path.endswith(".taskpod.json"):
                continue
            if path not in allowed:
                unexpected.append(path)
        if unexpected:
            raise OrchestrationError(
                "proposer modified unexpected files:\n  " + "\n  ".join(unexpected) +
                f"\nOnly proposal.md and {turn_rel} are allowed.\nPod left at {pod}"
            )

        if git_ok(pod, "diff", "--quiet", "main", "--", "proposal.md"):
            raise OrchestrationError(
                f"proposal.md did not change on turn {turn}\nPod left at {pod}"
            )

        state = self.load_state(pod / "deliberation" / "state.json")
        state["status"] = "proposing"
        state["pending_vote"] = {
            "turn": turn,
            "persona": persona,
            "proposal": turn_rel,
            "branch": self.pod_branch(turn),
            "base": git_out(self.repo, "rev-parse", "--short", "main"),
        }
        self.save_state(state, path=pod / "deliberation" / "state.json")
        self.state = state

        git(pod, "add", "--", "proposal.md", turn_rel, "deliberation/state.json")
        issue = self.issue_summary(turn_path)
        message = f"turn {turn:03d}: {persona} — {issue}"
        git(pod, "commit", "-m", message)
        log(f"[turn {turn}] committed proposal: {message}")

    def issue_summary(self, turn_path: Path) -> str:
        text = turn_path.read_text(encoding="utf-8")
        match = re.search(
            r"^## Issue identified\s*\n+(.+?)(?:\n\n|\n## )", text, re.S | re.M
        )
        raw = match.group(1) if match else "proposal change"
        raw = re.sub(r"\s+", " ", raw).strip()
        raw = re.sub(r"[`*_#]", "", raw)
        return raw[:120].rstrip(".,;:") or "proposal change"

    # -- vote phase -------------------------------------------------------

    def open_vote(self, turn: int, pod: Path) -> Dict[str, Any]:
        state = self.load_state(pod / "deliberation" / "state.json")
        if state.get("status") != "voting":
            state["status"] = "voting"
            self.save_state(state, path=pod / "deliberation" / "state.json")
            git(pod, "add", "--", "deliberation/state.json")
            git(pod, "commit", "-m", f"turn {turn:03d}: open vote")
        self.state = state
        return state

    def run_votes(
        self,
        turn: int,
        pod: Path,
        parallel: bool = False,
        dry_run: bool = False,
    ) -> List[Dict[str, Any]]:
        voters = self.personas[: self.voters]
        votes: List[Dict[str, Any]] = []

        if dry_run:
            for persona in voters:
                prompt = self.voter_prompt(turn, persona, pod)
                log(f"[dry-run] voter prompt for {persona} ({len(prompt)} chars)")
            return votes

        def one(persona: str) -> Dict[str, Any]:
            vote_path = pod / self.vote_rel(turn, persona)
            if vote_path.exists():
                existing = self.validate_vote(vote_path, turn, persona)
                if existing:
                    log(f"[turn {turn}] vote: {persona} (existing)")
                    return existing
            prompt = self.voter_prompt(turn, persona, pod)
            last_error: Optional[Exception] = None
            for attempt in (1, 2):
                try:
                    self.run_agent(prompt, pod, "vote", turn, persona)
                    vote = self.validate_vote(vote_path, turn, persona)
                    if vote:
                        log(f"[turn {turn}] vote: {persona} -> {vote['vote']}")
                        return vote
                    raise OrchestrationError(
                        f"{persona} did not write a valid "
                        f"{self.vote_rel(turn, persona)}"
                    )
                except OrchestrationError as exc:
                    last_error = exc
                    if attempt == 1:
                        prompt += (
                            "\n\nYour previous attempt did not produce a valid vote "
                            "file. Write exactly the requested JSON file, then return "
                            "one line."
                        )
                        log(f"[turn {turn}] retrying vote for {persona}")
            raise OrchestrationError(str(last_error) + f"\nPod left at {pod}")

        if parallel:
            with concurrent.futures.ThreadPoolExecutor(
                max_workers=len(voters)
            ) as pool:
                futures = {pool.submit(one, p): p for p in voters}
                for future in concurrent.futures.as_completed(futures):
                    votes.append(future.result())
        else:
            for persona in voters:
                votes.append(one(persona))
        return votes

    def validate_vote(
        self, path: Path, turn: int, persona: str
    ) -> Optional[Dict[str, Any]]:
        if not path.exists():
            return None
        try:
            vote = read_json(path)
        except OrchestrationError:
            return None
        if vote.get("turn") != turn or vote.get("persona") != persona:
            return None
        if vote.get("vote") not in {"approve", "reject", "abstain"}:
            return None
        if vote.get("confidence") not in {"high", "medium", "low"}:
            vote["confidence"] = "medium"
        if not isinstance(vote.get("minor"), bool):
            return None
        if not isinstance(vote.get("reason"), str) or not vote["reason"].strip():
            return None
        if not isinstance(vote.get("conditions", []), list):
            vote["conditions"] = []
        return vote

    # -- tally and decision ----------------------------------------------

    def changed_stats(self, pod: Path) -> Tuple[int, int, List[int]]:
        numstat = git_out(pod, "diff", "--numstat", "main", "--", "proposal.md")
        added = removed = 0
        if numstat:
            parts = numstat.split("\t")
            if len(parts) >= 2:
                added, removed = int(parts[0]), int(parts[1])
        return added, removed, self.changed_clauses(pod)

    def changed_clauses(self, pod: Path) -> List[int]:
        diff = git_out(pod, "diff", "-U0", "main", "--", "proposal.md")
        proposal = (pod / "proposal.md").read_text(encoding="utf-8")
        headings: List[Tuple[int, int]] = []
        for idx, line in enumerate(proposal.splitlines(), start=1):
            m = CLAUSE_RE.match(line)
            if m:
                headings.append((idx, int(m.group(1))))
        changed_lines = set()
        for m in HUNK_RE.finditer(diff):
            old_start, old_count = int(m.group(1)), int(m.group(2) or 1)
            new_start, new_count = int(m.group(3)), int(m.group(4) or 1)
            changed_lines.update(
                range(max(1, old_start), old_start + max(1, old_count))
            )
            changed_lines.update(
                range(max(1, new_start), new_start + max(1, new_count))
            )
        clauses = set()
        for line_no in changed_lines:
            clause = None
            for heading_line, number in headings:
                if heading_line <= line_no:
                    clause = number
                else:
                    break
            if clause is not None:
                clauses.add(clause)
        return sorted(clauses)

    def tally(
        self, turn: int, pod: Path, votes: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        pending = self.state.get("pending_vote") or {}
        proposal_persona = pending.get("persona") or ""
        counts = {"approve": 0, "reject": 0, "abstain": 0}
        for vote in votes:
            counts[vote["vote"]] += 1
        quorum = max(1, (len(self.personas) + 1) // 2)
        if len(votes) < quorum:
            raise OrchestrationError(
                f"quorum not met: {len(votes)} votes, need {quorum}. "
                f"Pod left at {pod}"
            )
        approved = (
            counts["approve"] > counts["reject"]
            and counts["approve"] >= quorum
        )
        added, removed, clauses = self.changed_stats(pod)
        total = added + removed
        threshold = int(
            self.state["convergence"].get("minor_max_changed_lines", 40)
        )
        minor = total < threshold and len(clauses) <= 1
        proposal_commit = git_out(
            pod, "log", "--format=%h", "--grep", f"^turn {turn:03d}:", "-1"
        )
        return {
            "turn": turn,
            "proposal": self.turn_file_rel(turn, proposal_persona),
            "branch": self.pod_branch(turn),
            "base": pending.get("base", ""),
            "proposal_commit": proposal_commit,
            "changed_lines": {"added": added, "removed": removed, "total": total},
            "clauses_changed": clauses,
            "minor": minor,
            "quorum": len(votes),
            "votes": votes,
            "tally": counts,
            "outcome": "approved" if approved else "rejected",
            "dissent": [v["persona"] for v in votes if v["vote"] == "reject"],
            "unanimous": len(votes) == len(self.personas)
            and counts["approve"] == len(votes),
            "advisory_conditions": [
                {"persona": v["persona"], "condition": c}
                for v in votes
                for c in v.get("conditions", [])
            ],
            "decided_at": iso_now(),
        }

    def write_summary(self, turn: int, summary: Dict[str, Any], pod: Path) -> None:
        write_json(pod / self.summary_rel(turn), summary)

    def write_rejection_note(
        self, turn: int, pod: Path, summary: Dict[str, Any], persona: str
    ) -> str:
        lines = [
            f"# Turn {turn:03d} — Rejection",
            "",
            f"- **Date:** {today_nz()}",
            f"- **Outcome:** rejected {summary['tally']['approve']}–"
            f"{summary['tally']['reject']}"
            + (
                " (unanimous, including the proposer)"
                if summary["unanimous"]
                and summary["tally"]["reject"] == len(summary["votes"])
                else ""
            ),
            f"- **Branch:** preserved as `{self.rejected_branch(turn)}`",
            f"- **Proposal:** `{self.turn_file_rel(turn, persona)}`",
            "",
            "## Reasons",
            "",
        ]
        for vote in summary["votes"]:
            if vote["vote"] == "reject":
                lines.append(f"- **{vote['persona']}:** {vote['reason']}")
        conditions = [
            (v["persona"], c)
            for v in summary["votes"]
            for c in v.get("conditions", [])
        ]
        if conditions:
            lines += ["", "## Conditions for a future proposal", ""]
            for voter_persona, condition in conditions:
                lines.append(f"- **{voter_persona}:** {condition}")
        lines += [
            "",
            "This branch is kept as the record of the rejected proposal. "
            "Do not re-propose the same change without a materially different instrument.",
            "",
        ]
        rel = f"deliberation/turn-{turn:03d}-rejection.md"
        (pod / rel).write_text("\n".join(lines), encoding="utf-8")
        return rel

    # -- complete a vote --------------------------------------------------

    def complete_vote(
        self,
        turn: int,
        pod: Path,
        version_bump: str,
        parallel_votes: bool,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        self.state = self.load_state(pod / "deliberation" / "state.json")
        if self.state.get("status") != "voting":
            self.open_vote(turn, pod)
        persona = (self.state.get("pending_vote") or {}).get("persona", "")

        votes = self.run_votes(turn, pod, parallel=parallel_votes, dry_run=dry_run)
        if dry_run:
            return {}
        summary = self.tally(turn, pod, votes)
        self.write_summary(turn, summary, pod)

        self.state = self.load_state(pod / "deliberation" / "state.json")
        self.state["status"] = summary["outcome"]
        self.state["pending_vote"] = None
        self.update_convergence(self.state, summary)
        self.state["history"].append(
            {
                "turn": turn,
                "persona": persona,
                "outcome": summary["outcome"],
                "tally": summary["tally"],
                "minor": summary["minor"],
                "changed_lines": summary["changed_lines"]["total"],
                "proposal": self.turn_file_rel(turn, persona),
                "vote_summary": self.summary_rel(turn),
                "note": (
                    "Approved; merge pending."
                    if summary["outcome"] == "approved"
                    else "Rejected; archive pending."
                ),
            }
        )
        if summary["outcome"] == "approved":
            self.set_stopped(self.state)
        else:
            self.state["status"] = "rejected"
        self.save_state(self.state, path=pod / "deliberation" / "state.json")
        git(
            pod,
            "add",
            "--",
            "deliberation/votes",
            self.summary_rel(turn),
            "deliberation/state.json",
        )
        git(
            pod,
            "commit",
            "-m",
            f"turn {turn:03d}: tally {summary['tally']['approve']}-"
            f"{summary['tally']['reject']}; record",
        )
        log(
            f"[turn {turn}] {summary['outcome']} "
            f"({summary['tally']['approve']}-{summary['tally']['reject']}); "
            f"{summary['changed_lines']['total']} lines, minor={summary['minor']}"
        )
        if summary["outcome"] == "approved":
            self.finish_approved(
                turn, pod, summary, version_bump, persona
            )
        else:
            self.finish_rejected(turn, pod, summary, persona)
        return summary

    # -- finish approved --------------------------------------------------

    def merge_approved(
        self,
        turn: int,
        pod: Path,
        summary: Dict[str, Any],
        persona: str,
    ) -> None:
        turn_path = pod / self.turn_file_rel(turn, persona)
        issue = self.issue_summary(turn_path) if turn_path.exists() else "proposal change"
        message = (
            f"Merge turn {turn:03d}: {issue}\n\n"
            f"Approved {summary['tally']['approve']}-"
            f"{summary['tally']['reject']} ({persona} proposing). "
            f"{summary['changed_lines']['total']} changed lines, clause(s) "
            f"{summary['clauses_changed'] or 'n/a'}."
        )
        git(self.repo, "merge", "--no-ff", self.pod_branch(turn), "-m", message)
        log(f"[turn {turn}] merged {self.pod_branch(turn)} to main")

    def record_merge(
        self, turn: int, summary: Dict[str, Any], version_bump: str
    ) -> None:
        state = self.load_state()
        persona = ""
        for item in reversed(state.get("history", [])):
            if item.get("turn") == turn:
                persona = item.get("persona", "")
                break

        proposal_path = self.repo / "proposal.md"
        text = proposal_path.read_text(encoding="utf-8")
        match = VERSION_RE.search(text)
        old_version = match.group(1) if match else None
        kind = version_bump
        if kind == "auto":
            kind = (
                "minor"
                if state.get("session_first_merge_pending", False)
                else "patch"
            )
        if old_version and kind != "none":
            new_version = bump_version(old_version, kind)
            text = VERSION_RE.sub(
                f"**Version {new_version} — {today_nz()}**", text, count=1
            )
            proposal_path.write_text(text, encoding="utf-8")
            self.append_changelog(turn, new_version, persona, summary)
            log(f"[turn {turn}] version {old_version} -> {new_version}")
        else:
            new_version = old_version or "unchanged"

        state["last_merged_turn"] = turn
        state["last_turn"] = max(state.get("last_turn", 0), turn)
        state["next_turn"] = max(state.get("next_turn", turn + 1), turn + 1)
        state["session_first_merge_pending"] = False
        state["active_persona"] = self.next_persona(state, persona)
        if state.get("status") == "approved":
            self.set_stopped(state)
        self.save_state(state)

        git(
            self.repo,
            "add",
            "--",
            "proposal.md",
            "archive/changelog.md",
            "deliberation/state.json",
        )
        git(
            self.repo,
            "commit",
            "-m",
            f"Record turn {turn:03d} merged; v{new_version}",
        )
        log(f"[turn {turn}] recorded merge; v{new_version}")

    def append_changelog(
        self, turn: int, version: str, persona: str, summary: Dict[str, Any]
    ) -> None:
        path = self.repo / "archive" / "changelog.md"
        text = path.read_text(encoding="utf-8").rstrip() + "\n\n"
        turn_path = self.repo / self.turn_file_rel(turn, persona)
        issue = self.issue_summary(turn_path) if turn_path.exists() else ""
        entry = (
            f"## v{version} — {today_nz()} (deliberation turn {turn})\n"
            f"{issue}\n\n"
            f"Proposed by `{persona}`, approved "
            f"{summary['tally']['approve']}-{summary['tally']['reject']}; see "
            f"`{self.summary_rel(turn)}`.\n"
        )
        path.write_text(text + entry, encoding="utf-8")

    def finish_approved(
        self,
        turn: int,
        pod: Path,
        summary: Dict[str, Any],
        version_bump: str,
        persona: str,
    ) -> None:
        branch = self.pod_branch(turn)
        merged = True
        if self.branch_exists(branch):
            merged = git_ok(
                self.repo, "merge-base", "--is-ancestor", branch, "main"
            )
        if not merged:
            self.merge_approved(turn, pod, summary, persona)
        state = self.load_state()
        if state.get("last_merged_turn", 0) < turn:
            self.record_merge(turn, summary, version_bump)
        self.remove_pod(turn, delete_branch=True)
        state = self.load_state()
        if state.get("status") == "approved":
            self.set_stopped(state)
            self.save_state(state)
            git(self.repo, "add", "--", "deliberation/state.json")
            git(self.repo, "commit", "-m", f"Close turn {turn:03d}")

    # -- finish rejected --------------------------------------------------

    def finish_rejected(
        self,
        turn: int,
        pod: Path,
        summary: Dict[str, Any],
        persona: str,
    ) -> None:
        if pod.exists():
            self.state = self.load_state(pod / "deliberation" / "state.json")
            note_rel = self.write_rejection_note(turn, pod, summary, persona)
            git(
                pod,
                "add",
                "--",
                "deliberation/votes",
                self.summary_rel(turn),
                note_rel,
                "deliberation/state.json",
            )
            if git_out(pod, "status", "--porcelain"):
                git(
                    pod,
                    "commit",
                    "-m",
                    f"turn {turn:03d}: rejected; archive proposal and reasons",
                )
        else:
            note_rel = f"deliberation/turn-{turn:03d}-rejection.md"
        self.archive_rejected_branch(turn)

        state = self.load_state()
        new_last_turn = max(state.get("last_turn", 0), turn)
        state["pending_vote"] = None
        state["last_turn"] = new_last_turn
        state["next_turn"] = max(state.get("next_turn", turn + 1), turn + 1)
        state["active_persona"] = self.next_persona(state, persona)
        state["convergence"]["consecutive_unanimous_minor"] = 0
        if new_last_turn >= int(state.get("turn_ceiling", 10)):
            state["status"] = "stopped"
            state["stopped_reason"] = "Hard ceiling reached."
        else:
            state["status"] = "ready"
            state.pop("stopped_reason", None)
        state.setdefault("history", []).append(
            {
                "turn": turn,
                "persona": persona,
                "outcome": "rejected",
                "tally": summary["tally"],
                "minor": summary["minor"],
                "changed_lines": summary["changed_lines"]["total"],
                "vote_summary": self.summary_rel(turn),
                "rejection_note": note_rel,
                "archived_branch": self.rejected_branch(turn),
                "note": "Rejected by the panel; branch archived.",
            }
        )
        self.save_state(state)
        git(self.repo, "add", "--", "deliberation/state.json")
        git(
            self.repo,
            "commit",
            "-m",
            f"Record turn {turn:03d} rejected",
        )
        log(f"[turn {turn}] rejected; archived {self.rejected_branch(turn)}")

    # -- state and stopping ----------------------------------------------

    def next_persona(self, state: Dict[str, Any], current: str) -> str:
        rotation = state.get("rotation") or self.personas
        try:
            return rotation[(rotation.index(current) + 1) % len(rotation)]
        except ValueError:
            return rotation[0]

    def update_convergence(
        self, state: Dict[str, Any], summary: Dict[str, Any]
    ) -> None:
        approved = summary.get("outcome") == "approved"
        unanimous = summary.get("unanimous", False)
        minor = summary.get("minor", False)
        conv = state["convergence"]
        if approved and unanimous and minor:
            conv["consecutive_unanimous_minor"] = (
                int(conv.get("consecutive_unanimous_minor", 0)) + 1
            )
        else:
            conv["consecutive_unanimous_minor"] = 0

    def set_stopped(self, state: Dict[str, Any]) -> None:
        if int(state["last_turn"]) >= int(state["turn_ceiling"]):
            state["status"] = "stopped"
            state["stopped_reason"] = (
                f"Hard ceiling reached: last_turn {state['last_turn']} >= "
                f"turn_ceiling {state['turn_ceiling']}."
            )
        elif int(
            state["convergence"].get("consecutive_unanimous_minor", 0)
        ) >= int(state["convergence"].get("required", 2)):
            state["status"] = "converged"
            state["stopped_reason"] = (
                "Convergence: "
                f"{state['convergence']['consecutive_unanimous_minor']} consecutive "
                "unanimous minor approvals."
            )
        else:
            state["status"] = "ready"
            state.pop("stopped_reason", None)

    # -- one turn ---------------------------------------------------------

    def run_one_turn(
        self, dry_run: bool = False, version_bump: str = "auto"
    ) -> None:
        state = self.load_state()
        if state["status"] != "ready":
            raise OrchestrationError(
                f"cannot start a turn while status is {state['status']!r}; "
                "run `run` to resume or `new-session` to start a session"
            )
        turn = int(state["next_turn"])
        persona = state["active_persona"]
        if turn > int(state["turn_ceiling"]):
            self.set_stopped(state)
            self.save_state(state)
            log("Hard ceiling reached; no new turn opened.")
            return

        log(f"=== turn {turn:03d} — {persona} ===")
        if dry_run:
            prompt = self.proposer_prompt(turn, persona, self.pod_path(turn))
            log(f"[dry-run] proposer prompt for {persona} ({len(prompt)} chars)")
            print(prompt)
            return
        self.begin_turn(turn, persona)
        pod = self.start_pod(turn)
        try:
            self.run_proposal(turn, persona, pod)
            self.complete_vote(
                turn,
                pod,
                version_bump=version_bump,
                parallel_votes=False,
            )
        except Exception:
            log(f"[turn {turn}] stopped with the pod left at {pod}")
            raise


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------


def cmd_status(orch: Orchestrator) -> int:
    state = orch.state
    log(f"State: {state['status']}  (session {state.get('session', 1)})")
    log(
        f"Last merged turn: {state['last_merged_turn']}   "
        f"last turn: {state['last_turn']}   next: {state['next_turn']}"
    )
    log(f"Active persona: {state['active_persona']}")
    conv = state["convergence"]
    log(
        f"Convergence: {conv.get('consecutive_unanimous_minor', 0)}/"
        f"{conv.get('required', 2)}"
    )
    if state.get("stopped_reason"):
        log(f"Stopped: {state['stopped_reason']}")
    if state.get("pending_vote"):
        log(f"Pending vote: {json.dumps(state['pending_vote'], sort_keys=True)}")
    log("History:")
    for item in state.get("history", []):
        tally = item.get("tally", {})
        log(
            f"  turn {item.get('turn'):>3}  {item.get('persona', ''):<26} "
            f"{item.get('outcome', ''):<9} "
            f"{tally.get('approve', 0)}-{tally.get('reject', 0)}  "
            f"{item.get('changed_lines', 0):>4} lines  "
            f"minor={item.get('minor')}"
        )
    pods = git_out(orch.repo, "worktree", "list", "--porcelain")
    active = [
        line for line in pods.splitlines()
        if line.startswith("worktree ") and "/.taskpods/" in line
    ]
    log(
        "Pods: "
        + (", ".join(p.split(" ", 1)[1] for p in active) if active else "(none)")
    )
    branches = git_out(orch.repo, "branch", "--list", "rejected/*").splitlines()
    log(
        "Rejected branches: "
        + (", ".join(b.strip("* ") for b in branches) if branches else "(none)")
    )
    return 0


def cmd_check(orch: Orchestrator) -> int:
    errors: List[str] = []
    warnings: List[str] = []
    state = orch.state

    if state["status"] not in {
        "ready", "proposing", "voting", "approved", "rejected",
        "converged", "stopped",
    }:
        errors.append(f"unknown status: {state['status']}")
    if state["status"] == "voting" and not state.get("pending_vote"):
        errors.append("status is voting but pending_vote is null")
    if state["status"] in {"ready", "converged", "stopped"} and state.get(
        "pending_vote"
    ):
        errors.append("pending_vote is set but the status is not proposing/voting")
    if state["next_turn"] <= state["last_turn"]:
        errors.append("next_turn must be greater than last_turn")
    if state["last_merged_turn"] > state["last_turn"]:
        errors.append("last_merged_turn cannot exceed last_turn")

    for item in state.get("history", []):
        turn = item.get("turn")
        summary = orch.repo / item.get("vote_summary", "")
        if item.get("outcome") == "rejected":
            branch = item.get(
                "archived_branch", f"rejected/turn-{int(turn):03d}"
            )
            if not git_ok(
                orch.repo, "rev-parse", "--verify", f"refs/heads/{branch}"
            ):
                errors.append(f"turn {turn}: rejected branch {branch} is missing")
        elif not summary.exists():
            errors.append(f"turn {turn}: missing {summary}")

    if state["status"] == "ready":
        status = git_out(orch.repo, "status", "--porcelain")
        if status:
            errors.append("main worktree is not clean:\n" + status)

    pods = git_out(orch.repo, "worktree", "list", "--porcelain")
    pod_lines = [
        line.split(" ", 1)[1]
        for line in pods.splitlines()
        if line.startswith("worktree ") and "/.taskpods/" in line
    ]
    if state["status"] in {"ready", "converged", "stopped"} and pod_lines:
        warnings.append(
            "active pods exist while the state is not mid-turn: "
            + ", ".join(pod_lines)
        )

    for branch in git_out(orch.repo, "branch", "--list", "pods/*").splitlines():
        warnings.append("open pod branch: " + branch.strip("* "))

    if warnings:
        for warning in warnings:
            log(f"WARN: {warning}")
    if errors:
        for error in errors:
            log(f"ERROR: {error}")
        return 1
    log("OK: state, history, and branches are consistent.")
    return 0


def cmd_new_session(orch: Orchestrator, force: bool) -> int:
    state = orch.state
    if state["status"] in {"proposing", "voting", "approved", "rejected"} and not force:
        raise OrchestrationError(
            f"a turn is in progress (status {state['status']!r}); "
            "finish it first or use --force"
        )
    last_persona = state["active_persona"]
    if state.get("history"):
        last_persona = state["history"][-1].get("persona", last_persona)
    state["status"] = "ready"
    state["pending_vote"] = None
    state["convergence"]["consecutive_unanimous_minor"] = 0
    state.pop("stopped_reason", None)
    state["session"] = int(state.get("session", 1)) + 1
    state["session_first_merge_pending"] = True
    state["last_turn"] = max(
        state.get("last_turn", 0), state.get("last_merged_turn", 0)
    )
    state["next_turn"] = max(state.get("next_turn", 1), state["last_turn"] + 1)
    state["active_persona"] = orch.next_persona(state, last_persona)
    orch.save_state(state)
    git(orch.repo, "add", "--", "deliberation/state.json")
    git(
        orch.repo,
        "commit",
        "-m",
        f"Start deliberation session {state['session']}",
    )
    log(
        f"Session {state['session']} ready: next turn {state['next_turn']}, "
        f"persona {state['active_persona']}."
    )
    return 0


def cmd_run(
    orch: Orchestrator,
    max_turns: int,
    dry_run: bool,
    parallel_votes: bool,
    version_bump: str,
    force: bool,
) -> int:
    done = 0
    while True:
        state = orch.load_state()

        if state["status"] in {"converged", "stopped"}:
            # Crash between merge and recording: finish the merge record first.
            if (
                state.get("last_merged_turn", 0) < state.get("last_turn", 0)
                and state.get("history")
                and state["history"][-1].get("outcome") == "approved"
            ):
                turn = int(state["last_turn"])
                pod = orch.pod_path(turn)
                summary = orch.summary_for(turn, pod)
                persona = state["history"][-1].get("persona", "")
                log(f"[resume] recording approved turn {turn}")
                orch.finish_approved(
                    turn, pod, summary, version_bump, persona
                )
                done += 1
                continue
            if not force:
                log(
                    f"Session is {state['status']}: "
                    f"{state.get('stopped_reason', '')}"
                )
                log(
                    "Use `new-session` to start another session, or "
                    "`run --force` to override."
                )
                return 0
            state["status"] = "ready"
            state["convergence"]["consecutive_unanimous_minor"] = 0
            state.pop("stopped_reason", None)
            orch.save_state(state)
            git(orch.repo, "add", "--", "deliberation/state.json")
            git(orch.repo, "commit", "-m", "Override stop for another turn")
            log("[force] cleared convergence/stopped status")

        if state["status"] == "ready":
            if int(state["last_turn"]) >= int(state["turn_ceiling"]):
                state["status"] = "stopped"
                state["stopped_reason"] = "Hard ceiling reached."
                orch.save_state(state)
                log("Hard ceiling reached; no new turn opened.")
                return 0
            if max_turns and done >= max_turns:
                log(
                    f"Paused after {done} turn(s); state is ready for the "
                    "next run."
                )
                return 0
            if dry_run:
                turn = int(state["next_turn"])
                persona = state["active_persona"]
                log(f"[dry-run] next turn {turn} — {persona}")
                prompt = orch.proposer_prompt(turn, persona, orch.pod_path(turn))
                print(prompt)
                return 0
            orch.run_one_turn(version_bump=version_bump)
            done += 1

        elif state["status"] in {"proposing", "voting"}:
            pending = state.get("pending_vote") or {}
            turn = int(pending.get("turn", state["last_turn"]))
            pod = orch.pod_path(turn)
            if not pod.exists():
                raise OrchestrationError(
                    f"turn {turn} is {state['status']} but pod {pod} is missing"
                )
            if state["status"] == "proposing":
                if git_ok(pod, "diff", "--quiet", "main", "--", "proposal.md"):
                    raise OrchestrationError(
                        f"turn {turn} is marked proposing but proposal.md has "
                        f"no change.\nInspect {pod}."
                    )
                log(f"[resume] proposal for turn {turn} exists; opening vote")
                orch.open_vote(turn, pod)
            orch.complete_vote(
                turn,
                pod,
                version_bump=version_bump,
                parallel_votes=parallel_votes,
            )
            done += 1

        elif state["status"] == "approved":
            turn = int(state["last_turn"])
            pod = orch.pod_path(turn)
            summary = orch.summary_for(turn, pod)
            persona = ""
            for item in reversed(state.get("history", [])):
                if item.get("turn") == turn:
                    persona = item.get("persona", "")
                    break
            log(f"[resume] finishing approved turn {turn}")
            orch.finish_approved(turn, pod, summary, version_bump, persona)
            done += 1

        elif state["status"] == "rejected":
            turn = int(state["last_turn"])
            pod = orch.pod_path(turn)
            summary = orch.summary_for(turn, pod)
            log(f"[resume] finishing rejected turn {turn}")
            persona = ""
            for item in reversed(state.get("history", [])):
                if item.get("turn") == turn:
                    persona = item.get("persona", "")
                    break
            orch.finish_rejected(turn, pod, summary, persona)
            done += 1

        else:
            raise OrchestrationError(f"cannot resume status {state['status']!r}")

    return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the persisted multi-agent deliberation loop.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--repo",
        default=str(Path(__file__).resolve().parent.parent),
        help="repository root (default: parent of this script)",
    )
    parser.add_argument(
        "--agent-cmd",
        default=os.environ.get(
            "DELIBERATE_AGENT",
            'dsh headless "$(cat "$DELIBERATE_PROMPT_FILE")"',
        ),
        help="shell command run in the pod; may use {prompt_file} and {pod}",
    )
    parser.add_argument(
        "--voters",
        type=int,
        default=5,
        help="number of persona voters (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=1800.0,
        help="per-agent timeout in seconds (default: 1800)",
    )
    parser.add_argument(
        "--no-taskpods",
        action="store_true",
        help="use plain git worktree instead of the taskpods CLI",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="print agent commands and output",
    )

    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("status", help="show state, history, pods, rejected branches")
    sub.add_parser("check", help="validate state, history, and branches")

    p_new = sub.add_parser(
        "new-session", help="clear convergence and start another session"
    )
    p_new.add_argument(
        "--force", action="store_true", help="start even if a turn is in progress"
    )

    p_run = sub.add_parser("run", help="run one or more turns")
    p_run.add_argument(
        "--max-turns",
        type=int,
        default=1,
        help="maximum turns this invocation (0 = until convergence/ceiling; "
        "default: 1)",
    )
    p_run.add_argument(
        "--dry-run",
        action="store_true",
        help="print the next prompt without running an agent",
    )
    p_run.add_argument(
        "--parallel-votes",
        action="store_true",
        help="run the persona voters concurrently",
    )
    p_run.add_argument(
        "--version-bump",
        choices=["auto", "patch", "minor", "major", "none"],
        default="auto",
        help="version bump for approved turns (default: auto — minor on the "
        "first merge of a session, then patch)",
    )
    p_run.add_argument(
        "--force",
        action="store_true",
        help="run even if the session is converged/stopped",
    )
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    repo = Path(args.repo).resolve()
    if not (repo / ".git").exists():
        print(f"error: not a git repository: {repo}", file=sys.stderr)
        return 2
    try:
        orch = Orchestrator(
            repo=repo,
            agent_cmd=args.agent_cmd,
            voters=args.voters,
            timeout=args.timeout,
            use_taskpods=not args.no_taskpods,
            verbose=args.verbose,
        )
        if args.command == "status":
            return cmd_status(orch)
        if args.command == "check":
            return cmd_check(orch)
        if args.command == "new-session":
            return cmd_new_session(orch, args.force)
        if args.command == "run":
            return cmd_run(
                orch,
                max_turns=args.max_turns,
                dry_run=args.dry_run,
                parallel_votes=args.parallel_votes,
                version_bump=args.version_bump,
                force=args.force,
            )
        parser.error(f"unknown command: {args.command}")
        return 2
    except OrchestrationError as exc:
        print(f"\nerror: {exc}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(
            "\ninterrupted; state and pod are left in place for resume",
            file=sys.stderr,
        )
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
