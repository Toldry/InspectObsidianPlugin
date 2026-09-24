# AGENTS.md

Welcome to the **InspectObsidianPlugin** repository. This document serves as the guide and instruction manual for AI agents operating in this workspace.

---

## 1. Project Overview

**InspectObsidianPlugin** is an evaluation suite built on the [Inspect AI](https://inspect.aisi.org.uk/) framework by the UK AI Security Institute (UK AISI). It focuses on benchmarking and evaluating LLM coding agents on real-world **Obsidian plugin development, maintenance, and bug fixing** (SWE-bench style).

### Core Goals
- Evaluate autonomous coding agents' capability to resolve complex, real-world issues in Obsidian plugins (TypeScript / Node.js).
- Provide safe, reproducible, and deterministic execution environments using Docker sandboxes with isolated network access.
- Grade agent solutions using hidden reference unit tests without exposing test suites or gold commit history to the model during evaluation.

---

## 2. Framework Knowledge Base (`llms.txt` & `llms-guide.txt`)

This repository includes official offline reference documentation for Inspect AI:

- **[`llms.txt`](llms.txt)**: The structural index and topic map of the Inspect AI documentation. Consult this file to quickly locate relevant APIs, solver definitions, agent interfaces, and command-line options.
- **[`llms-guide.txt`](llms-guide.txt)**: The comprehensive developer manual and complete reference guide for Inspect AI. Consult this file whenever you need in-depth implementation details on:
  - Task, Dataset, and Sample specifications
  - Solver and Agent configurations (e.g., `react`, `deepagent`, memory, limits)
  - Tool registration and sandboxing (`bash`, `text_editor`, Docker sandboxes)
  - Custom Scorers and metrics (`@scorer`, `Score`, sandbox execution)
  - Logging, log formats (`.eval`), and viewing tools (`inspect view`, `inspect log`)

> **Agent Instruction**: Whenever you are uncertain about Inspect AI syntax, parameters, or APIs, search and consult [`llms-guide.txt`](llms-guide.txt) and [`llms.txt`](llms.txt) before proposing changes.

---

## 3. Repository Architecture

```
InspectObsidianPlugin/
├── .devcontainer/          # Dev container for AI agents (no Docker access; see Section 6)
│   ├── devcontainer.json
│   ├── Dockerfile            # All setup: apt Python/Node/gh, inspect_ai venv (sudo is disabled at runtime)
│   └── managed-settings.json # Claude Code starts in auto mode inside the container only
├── src/
│   ├── swe_daylio_popout.py  # Main Inspect task definition & custom test scorer
│   └── quota_guard.py        # Automatic abort & retry suppression for spending caps
├── env.patch               # Environment-only changes (test mock stubs) committed on top of upstream as the eval base
├── test.patch              # Hidden reference unit tests applied post-agent run
├── gold.patch              # Reference fix (never copied into the image); used by scripts/validate_task.py
├── Dockerfile              # Sandbox container definition (shallow-fetched upstream commit + env.patch, npm deps)
├── .dockerignore           # Build context is only Dockerfile + env.patch (keeps hidden tests / gold out)
├── compose.yaml            # Docker Compose config (network_mode: none for isolation)
├── scripts/                # Log inspection & debugging utilities (Python)
│   ├── inspect_latest_log.py # Summarize, inspect trajectory, scores, and tokens
│   ├── latest_diff.py        # Dump model-generated git diff (model_patch; -w hides whitespace churn)
│   ├── latest_tests.py       # View clean test scorer output & failure messages
│   └── validate_task.py      # Docker-free check: hidden tests fail on base, pass with gold.patch
├── logs/                   # Evaluation results stored as .eval logs
├── .env                    # Environment credentials (e.g., model API keys)
├── .venv/                  # Python virtual environment (contains inspect_ai)
├── llms.txt                # Inspect AI topic index
├── llms-guide.txt          # Inspect AI comprehensive guide
└── README.md               # User-facing project overview
```

### Component Details

1. **Task Definition ([`src/swe_daylio_popout.py`](src/swe_daylio_popout.py)) & Quota Guard ([`src/quota_guard.py`](src/quota_guard.py))**:
   - Defines the task using `@task`.
   - Supplies the agent with the issue prompt and base commit metadata.
   - Equips the agent with execution tools (`bash()`, `text_editor()`).
   - Guards against endless retry loops on spending caps / quota exhaustion by catching terminal errors and marking the evaluation as failed (`status="error"`) with `Score.unscored(reason="scoring_failed")`.
   - Captures model diff against `base_commit` and hooks into the `npm_test_scorer()` to validate changes.

2. **Sandbox Environment ([`Dockerfile`](Dockerfile) & [`compose.yaml`](compose.yaml))**:
   - Runs a containerized Node.js environment (`node:20`).
   - Shallow-fetches (`git fetch --depth 1`) **only** the upstream commit SHA (`91887ba8fae8068ff3f02e37c62d565221a8ee48`) to eliminate future commit/tag leakage while preserving exact git blob SHAs.
   - Applies [`env.patch`](env.patch) and commits it with a fixed identity and date, so the evaluation base commit has a deterministic SHA (`BASE_COMMIT`). The build fails if the SHA drifts. If you change `env.patch`, update `BASE_COMMIT` in both the Dockerfile and `src/swe_daylio_popout.py` (run `scripts/validate_task.py` to get the new SHA).
   - Pre-installs all npm dependencies so tests can run offline with `network_mode: none`.

3. **Evaluation Test Suite ([`test.patch`](test.patch))**:
   - Contains unit tests that specifically assert the expected behavior for the issue.
   - Prior to scoring, `tests/` is deleted and restored from `base_commit` (together with `vitest.config.ts`) to prevent tampering, and `test.patch` is applied cleanly using `git apply --whitespace=nowarn`. Vitest is then run directly (`node_modules/.bin/vitest run`), not via the `package.json` script.
   - Tests check *behavior* (where the note ends up, via a window-aware fake workspace), not which Obsidian API the fix calls, so any correct fix can pass.
   - After changing `test.patch`, `env.patch` or `gold.patch`, run `python scripts/validate_task.py`: the hidden tests must fail on the base and pass with `gold.patch`. Add `--log logs/<file>.eval` to replay a model's patch. This runs locally with Node.js (no Docker).
   - Never exposed directly to the model during solver execution.

---

## 4. Key Workflows & CLI Commands

### Running Evaluations

> **Agent Instruction**: Agents must **never** run `inspect eval`, `inspect score`, or `docker compose build` themselves. The user runs these on the host machine. The dev container has no Docker access (see [Section 6](#6-dev-container-devcontainer)), so these commands would fail there anyway. When you need an evaluation run, **ask the user to run it**: give the exact command, and say what you'll check in the resulting log. Once the user confirms it finished, read the new log with the tools under [Viewing and Analyzing Logs](#viewing-and-analyzing-logs).

To run an evaluation task (user, on the host):
```bash
# Run a single sample test
inspect eval src/swe_daylio_popout.py --model google/gemini-3.6-flash --limit 1

# Run with custom limits or log directory
inspect eval src/swe_daylio_popout.py --model <model-name> --limit 1 --log-dir ./logs
```

### Viewing and Analyzing Logs

Inspect provides visual tools, CLI commands, and dedicated workspace scripts in `scripts/` to examine evaluation runs and debug failures:

1. **Dedicated Workspace Inspection Scripts (`scripts/`) [Recommended]**:
   Cross-platform utilities with built-in UTF-8 safety (preventing Windows charmap encoding errors) to inspect `.eval` files:
   ```bash
   # Quick summary of the latest log (status, duration, message count, token usage, score preview):
   python scripts/inspect_latest_log.py

   # View message trajectory and tool call history:
   python scripts/inspect_latest_log.py --messages
   # (Add --full-content to avoid truncating message bodies)

   # View clean test scorer / Vitest explanation:
   python scripts/inspect_latest_log.py --explanation

   # View only the failing unit tests from the test run:
   python scripts/latest_tests.py --failures-only

   # View the git diff (model_patch) produced by the agent:
   python scripts/latest_diff.py
   # (Add --ignore-whitespace / -w to hide tab-to-space churn from the text_editor tool)

   # List recent evaluation logs:
   python scripts/inspect_latest_log.py --list

   # Inspect any specific older log file:
   python scripts/inspect_latest_log.py --log logs/<file>.eval --all
   ```

2. **Web Log Viewer (`inspect view`)**:
   Launch the interactive browser UI to inspect agent transcripts, model prompts/completions, tool call traces, and scorer outputs:
   ```bash
   inspect view
   # Or target a specific log directory:
   inspect view --log-dir ./logs
   ```

3. **Listing Evaluation Logs (`inspect log list`)**:
   List logs with status filtering:
   ```bash
   # List all logs
   inspect log list

   # Filter by evaluation status (started, success, cancelled, error)
   inspect log list --status error
   inspect log list --status success

   # Output list as JSON or with absolute paths
   inspect log list --json
   inspect log list --absolute
   ```

4. **CLI Log Dumping (`inspect log dump`)**:
   Read `.eval` binary log files uniformly as JSON:
   ```bash
   # Quick inspection: header only (metadata, scores, metrics, without huge message transcripts)
   inspect log dump --header-only logs/<log-file>.eval

   # Full dump (includes all samples, messages, and tool calls)
   inspect log dump logs/<log-file>.eval
   ```

5. **Extracting Specific Information via PowerShell or Python**:
   - **PowerShell (quick score and error extraction)**:
     ```powershell
     # Extract sample scores and explanations:
     (inspect log dump logs/<log-file>.eval | ConvertFrom-Json).samples[0].scores

     # View the last message / tool call in the trajectory:
     (inspect log dump logs/<log-file>.eval | ConvertFrom-Json).samples[0].messages[-1]
     ```

   - **Python API (`inspect_ai.log.read_eval_log`)**:
     ```python
     from inspect_ai.log import read_eval_log

     log = read_eval_log("logs/<log-file>.eval")
     print("Eval status:", log.status)
     print("Scores:", log.samples[0].scores)
     print("Explanation:", log.samples[0].scores["npm_test_scorer"].explanation)
     ```

6. **Re-Scoring Existing Logs (`inspect score`)** — *host only, ask the user*:
   Re-run a scorer over an existing eval log without re-executing the model (the scorer runs tests in a Docker sandbox, so this needs Docker):
   ```bash
   inspect score logs/<log-file>.eval --scorer src/swe_daylio_popout.py@npm_test_scorer
   ```

7. **Recovering Incomplete/Crashed Logs (`inspect log recover`)**:
   Recover samples buffered in SQLite if an evaluation crashed:
   ```bash
   inspect log recover logs/<crashed-log>.eval
   ```

---

## 5. Development Guidelines for Agents

- **Preserve Test Secrecy**: Never expose the contents of `test.patch` to the agent prompt or task input. The task input must only contain the user-reported issue description.
- **Prevent Git History Leakage**: Ensure sandbox environments never contain commits, tags, or branches created after `base_commit`. Use shallow commit fetches (`git fetch --depth 1 origin <base_commit>`).
- **Deterministic Sandboxes**: Keep sandbox images self-contained. All dependencies must be baked in during image build (`Dockerfile`) since network access is disabled during eval runs.
- **Inspect Framework Idioms**: Always adhere to Inspect AI conventions outlined in [`llms-guide.txt`](llms-guide.txt) when introducing new tasks, scorers, or solver configurations.
- **Evaluations Are Run by the User**: Never run `inspect eval`, `inspect score`, or any Docker command. Ask the user to run it on the host, giving the exact command (see [Running Evaluations](#running-evaluations)).

---

## 6. Dev Container (`.devcontainer/`)

The dev container exists so AI agents can work in this repo **without putting the host machine at risk**. Every decision below serves that goal. Don't weaken any of them without the user's explicit approval.

### Key Decisions

- **No Docker inside the dev container.** Neither way of giving a container Docker access keeps it isolated:
  - *Docker-outside-of-Docker* shares the host's Docker socket. Anything that can reach the socket can start a privileged container that mounts the host filesystem, which is root on the host.
  - *Docker-in-Docker* runs a separate daemon inside the container. That needs `--privileged`, and escaping a privileged container is a well-known technique. On Docker Desktop for Windows, the host VM also mounts the Windows drives, so an escape reaches Windows files.
  - **Consequence:** evaluations and Docker builds run on the host, by the user only (see [Running Evaluations](#running-evaluations)).
  - If agents ever need Docker, the options that stay isolated are Docker Sandboxes (microVM-based) or Docker-in-Docker with Docker Desktop's Enhanced Container Isolation. Plain DinD and DooD don't qualify.
- **`--security-opt=no-new-privileges:true` is set, so `sudo` does not work** in the running container (it fails with `effective uid is not 0`). Put root-level setup (`apt` packages, directory ownership) in [`.devcontainer/Dockerfile`](.devcontainer/Dockerfile). Runtime installs must not need root. Python tooling lives in `/opt/venv` (owned by `vscode`, first on `PATH`), so `pip install` works without root.
- **No dev container features and no `postCreateCommand`.** Python, Node, `gh` and `inspect_ai` are installed in the Dockerfile, ordered from least to most frequently changed, so each is a cached Docker layer. Features always run after the Dockerfile and re-run together whenever the feature list changes; the `python` feature alone took ~3 minutes. Add new tools as Dockerfile steps, not features.
- **The base image is pinned to `ubuntu-24.04`.** The floating `ubuntu` tag moved to 26.04 ("resolute") and broke the build without any repo change. Pinning keeps builds reproducible. Bump the pin on purpose, never by switching back to a floating tag.
- **Claude Code history and login persist across rebuilds.** The config lives in the named volume `claude-code-config-${devcontainerId}`, mounted at `/home/vscode/.claude`. `CLAUDE_CONFIG_DIR` points to the same path, so `.claude.json` also lands in the volume. This follows [Anthropic's dev container guidance](https://code.claude.com/docs/en/devcontainer). The volume is kept separate from the host's `~/.claude` on purpose, so host credentials and other projects' history stay out of the sandbox.
- **Claude Code starts in auto mode inside the container and in Manual mode on the host.**
  - Inside the container, the Dockerfile copies [`.devcontainer/managed-settings.json`](.devcontainer/managed-settings.json) (`permissions.defaultMode: "auto"`) to `/etc/claude-code/managed-settings.json`, where only the container sees it.
  - On the host, the user's own `~/.claude/settings.json` sets `defaultMode: "default"`.
  - Don't put `defaultMode` in the project's `.claude/settings.json`: the workspace is shared by both environments, and Claude Code ignores `auto` there anyway.
- **The Claude Code VS Code extension** (`anthropic.claude-code`) is installed automatically through `customizations.vscode.extensions`. It includes its own copy of Claude Code, so installing the Claude Code CLI separately isn't needed.

### What Survives a Rebuild

| Survives | Lost |
|---|---|
| The workspace (bind-mounted from the host) | Packages installed by hand (`apt`, `pip`, `npm -g`) |
| The `.gitconfig` bind mount and the `--env-file` secrets | Changes under `/home/vscode`, except `~/.claude` |
| The Claude Code config volume (`~/.claude`) | Files outside the workspace (`/tmp`, `/opt`, …) |

Anything the environment needs permanently belongs in `.devcontainer/Dockerfile`, never in manual installs.
