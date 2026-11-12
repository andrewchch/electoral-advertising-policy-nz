# Running the Deliberation Loop

`orchestrate.py` is the repeatable version of the manual process used for
[deliberation session 1](turn-004-final-report.md). It runs one persona at a time on a
taskpods worktree, collects one vote per persona, tallies, merges approved turns to
`main`, and archives rejected turns on a `rejected/` branch.

The script is a single Python file with no third-party dependencies. It uses `taskpods`
when available and falls back to plain `git worktree`.

---

## Quick start

```bash
python3 deliberation/orchestrate.py status
python3 deliberation/orchestrate.py check

# The current state is converged. Start session 2 first:
python3 deliberation/orchestrate.py new-session

# Run one turn:
python3 deliberation/orchestrate.py run --max-turns 1

# Run until convergence or the turn ceiling:
python3 deliberation/orchestrate.py run --max-turns 0
```

`run` runs **one turn** by default. Nothing is pushed to `origin`.

---

## Replaying the experiment from v0.9

The current `main` is v0.10.2 with session 1 history. Two ways to run again:

**Continue on the current proposal.** Use `new-session`, then `run`. This starts at turn 5
and keeps the v0.10.2 text.

**Replay from the original v0.9 baseline.** Do this in a throwaway clone, because the
runner always uses `main` as the base branch:

```bash
REAL=/path/to/electoral-advertising-policy-nz
git clone "$REAL" /tmp/electoral-replay
cd /tmp/electoral-replay

# Reset main to the bootstrap commit (v0.9 + deliberation scaffolding).
git checkout -B main 0c3de44

# Bring in the runner and docs from the current main.
git checkout origin/main -- deliberation/orchestrate.py deliberation/README.md deliberation/tests
git commit -m "Add the runner to the replay baseline"

# --no-taskpods keeps the runner on this clone's reset main; taskpods would
# fetch origin/main (v0.10.2) instead.
python3 deliberation/orchestrate.py --no-taskpods check
python3 deliberation/orchestrate.py --no-taskpods run --max-turns 0 \
  --agent-cmd 'your-agent-command'
```

The clone's `main` is the v0.9 baseline, so the first approved turn gets the first
version bump of the session. The original repo is untouched.

---

## The agent command

The script runs a shell command inside the pod. The default is:

```bash
dsh headless "$(cat "$DELIBERATE_PROMPT_FILE")"
```

`dsh headless` needs a configured headless profile. If `~/.dsh/profiles/headless` does not
exist, either create it or pass a different command:

```bash
# Claude Code
python3 deliberation/orchestrate.py run \
  --agent-cmd 'claude -p "$(cat "$DELIBERATE_PROMPT_FILE")"'

# Codex
python3 deliberation/orchestrate.py run \
  --agent-cmd 'codex exec "$(cat "$DELIBERATE_PROMPT_FILE")"'

# A local script (used by the tests)
python3 deliberation/orchestrate.py run \
  --agent-cmd 'python3 deliberation/tests/mock_agent.py'
```

The prompt is passed through a file, not shell interpolation. Backticks and dollar signs in
a prompt are safe. If your agent reads stdin instead of an argument, use:

```bash
--agent-cmd 'claude -p < "$DELIBERATE_PROMPT_FILE"'
```

### Environment contract

The agent command receives:

| Variable | Meaning |
|---|---|
| `DELIBERATE_PROMPT` | full prompt text |
| `DELIBERATE_PROMPT_FILE` | path to the same prompt |
| `DELIBERATE_PHASE` | `propose` or `vote` |
| `DELIBERATE_TURN` | turn number |
| `DELIBERATE_PERSONA` | persona name |
| `DELIBERATE_POD` | pod path |
| `DELIBERATE_TURN_FILE` | expected turn file, relative to the pod |
| `DELIBERATE_VOTE_PATH` | expected vote file, relative to the pod (vote phase) |

The prompt tells the agent exactly what to write. In automated mode the agent writes only:

- `proposal.md`
- `deliberation/turn-NNN-persona-<persona>.md` (propose phase), or
- `deliberation/votes/turn-NNN-<persona>.json` (vote phase)

The orchestrator writes `state.json`, commits, tallies, and merges. This is a deliberate
change from the manual session, where the agent also updated state: keeping state
transitions in one process makes the loop crash-safe.

---

## Commands

| Command | What it does |
|---|---|
| `status` | State, history, active persona, pods, rejected branches |
| `check` | Validate state, history, vote summaries, and archived branches |
| `new-session` | Clear convergence/stopped status and start another session; keeps turn numbering |
| `run --max-turns N` | Run N turns (default 1); `0` means until convergence or ceiling |
| `run --dry-run` | Print the next proposer prompt without running an agent |
| `run --parallel-votes` | Run the persona voters concurrently |
| `run --version-bump auto` | Minor bump on the first merge of a session, then patch (default) |
| `run --version-bump none` | No version/changelog change (useful for tests) |
| `run --force` | Run another turn despite a converged/stopped status |

Common options: `--repo PATH`, `--voters N` (default 5, capped by `personas.md`),
`--timeout SECONDS` (default 1800 per agent), `--no-taskpods`, `--verbose`.

### `new-session`

The current repository is at `status: converged`, so `run` refuses to start. `new-session`:

- resets the convergence counter and clears `stopped_reason`;
- increments `session`;
- keeps `last_turn` and continues at `next_turn` (turn 5, persona `small-party-organiser`);
- sets `session_first_merge_pending`, so the first approved turn gets a minor version bump.

It does **not** reset turn numbering or delete turn files.

---

## Turn lifecycle

For turn `N`:

1. `begin_turn` writes `status: proposing` on `main` and commits it. This makes a crash
   resumable.
2. `taskpods start turn-NNN --base main` (or `git worktree add`) creates the pod.
3. The proposer agent edits `proposal.md` and writes the turn file.
4. The orchestrator checks that only those two files changed, commits with
   `turn NNN: <persona> — <issue>`, and opens the vote.
5. Five persona agents read the turn file and `git diff main -- proposal.md` and write one
   vote JSON each. A missing or invalid vote is retried once.
6. The orchestrator tallies (quorum 4, simple majority, ties fail), computes changed lines
   and clauses, decides whether the edit is minor, and writes
   `deliberation/turn-NNN-vote-summary.json`.
7. **Approved:** merge `--no-ff` to `main`, bump the proposal version, append the
   changelog, record `state.json`, remove the pod and branch.
   **Rejected:** write `deliberation/turn-NNN-rejection.md`, commit, remove the worktree,
   rename the branch to `rejected/turn-NNN`, and record the rejection on `main`.
8. If the convergence rule or the ceiling is met, set `converged` or `stopped` and write
   `deliberation/turn-NNN-final-report.md`; otherwise set `ready` for the next turn.

The stopping rule is in `state.json`: two consecutive unanimous minor approvals, or the
turn ceiling (10).

---

## Crash recovery

The orchestrator is designed to be resumed with `run`:

| State | What `run` does |
|---|---|
| `ready` | Opens the next turn |
| `proposing` | Checks the pod for a proposal diff, opens the vote |
| `voting` | Reuses existing valid votes, then tallies |
| `approved` | Merges if needed, records, removes the pod |
| `rejected` | Writes the rejection record if needed, archives |
| `converged` / `stopped` | Writes the final report if missing, then refuses unless `--force` or `new-session` |

If an agent fails, the pod is left in place and the error names it. Inspect it, then either
fix the files and run `run` again, or remove it manually:

```bash
git worktree remove --force .taskpods/turn-NNN
git branch -D pods/turn-NNN
```

`check` will report inconsistent state and missing archived branches.

---

## Tests

The tests create throwaway git repositories, copy the proposal and deliberation files, and
drive the orchestrator with `deliberation/tests/mock_agent.py`. They make no network or
model calls.

```bash
python3 -m unittest discover -s deliberation/tests -v
```

Covered: approved merge, rejected archive, convergence stop, final report, new session,
parallel votes, automatic version bump, dry-run safety, and state consistency.

---

## Safety notes

- **No push.** The script only merges locally. `taskpods done` is not used because it
  unconditionally pushes to `origin`.
- **Agent trust.** The agent command is arbitrary shell; run only agents you trust. The
  orchestrator validates the changed paths, the turn file, and the vote schema, but it
  cannot inspect the agent's reasoning.
- **One branch at a time.** Proposer pods are sequential. Voters are read-only and may run
  in parallel (`--parallel-votes`); they never touch the proposal.
- **The private drafting transcript** is not part of this repository and must not be added.
