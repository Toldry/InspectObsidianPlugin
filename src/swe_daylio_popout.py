from pathlib import Path
import re
import sys

from inspect_ai import Task, task
from inspect_ai.agent import react
from inspect_ai.dataset import Sample
from inspect_ai.scorer import (
    CORRECT,
    INCORRECT,
    Score,
    Target,
    accuracy,
    scorer,
    stderr,
)
from inspect_ai.solver import TaskState
from inspect_ai.tool import bash, text_editor
from inspect_ai.util import ExecResult, sandbox

# Ensure local module imports work when invoked directly by inspect CLI
_current_dir = Path(__file__).resolve().parent
_root_dir = _current_dir.parent
for _p in (_current_dir, _root_dir):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

try:
    from quota_guard import safe_agent_solver
except ImportError:
    from src.quota_guard import safe_agent_solver

# Evaluation base: upstream 91887ba + env.patch, committed deterministically by the Dockerfile.
# Keep in sync with BASE_COMMIT in the Dockerfile.
BASE_COMMIT = "b15fd4c01336c8688029ad790c78ec16078f92bc"

# Issue description based on the upstream commit message, with the expected
# behaviour spelled out so that it matches what the hidden tests check.
ISSUE_DESCRIPTION = """
Bug: clicking event labels in the Daylio mood graph doesn't open notes when the graph is in a pop-out window

When I move the mood graph into its own window (a pop-out window), clicking an event label usually does
nothing: the click doesn't seem to register and the note isn't opened. Dragging the graph to pan still works.
When a note does open, it opens inside the pop-out window instead of the main Obsidian window.

Expected behaviour:
- If the graph's window contains only the Daylio graph (no notes), clicking a label opens the note in the
  main (original) Obsidian window and brings that window into focus. The graph stays open.
- If the graph's window also has notes open, or the graph is in the main window, clicking a label opens the
  note in that same window, like a normal Obsidian link click. The graph itself is never replaced.
- Modifier clicks from a graph-only pop-out window:
  - Ctrl/Cmd+Click opens the note in a new tab in the graph's own (pop-out) window.
  - Ctrl/Cmd+Alt+Click opens the note in a new split in the main window.
  - Ctrl/Cmd+Alt+Shift+Click opens the note in a new window.
"""

AGENT_PROMPT = """You are an expert software engineer. Your task is to resolve the reported issue in the repository located at /repo.
Investigate the codebase, implement the necessary fix, and verify your solution before completing the task.

Note: this repository indents with tabs, and the text_editor tool converts tabs to spaces in every file it edits.
Keep your diff minimal: make edits with bash (for example a short Python script), or restore tab indentation afterwards."""


@scorer(metrics=[accuracy(), stderr()])
def npm_test_scorer(patch_path: Path | str | None = None):
    """Scorer that isolates agent changes, applies SWE-bench evaluation test patch, and runs npm test."""
    async def score(state: TaskState, target: Target) -> Score:
        if state.metadata.get("is_spending_cap_error"):
            abort_reason = state.metadata.get("abort_reason", "Monthly spending cap or quota exceeded")
            return Score.unscored(
                reason="scoring_failed",
                explanation=f"Aborted automatically due to API quota / spending cap limit: {abort_reason}",
            )

        base_commit = state.metadata.get("base_commit", BASE_COMMIT)

        # Capture the agent's patch against the base commit for logging/auditability.
        # Stage everything first so new (untracked) files are included.
        await sandbox().exec(["git", "add", "-A"], cwd="/repo")
        diff_res: ExecResult = await sandbox().exec(
            ["git", "diff", "--cached", base_commit],
            cwd="/repo",
        )
        agent_patch = diff_res.stdout if diff_res.returncode == 0 else ""
        # Same diff ignoring whitespace, so indentation churn doesn't hide the real change
        diff_ws_res: ExecResult = await sandbox().exec(
            ["git", "diff", "--cached", "--ignore-all-space", base_commit],
            cwd="/repo",
        )
        agent_patch_ignore_ws = diff_ws_res.stdout if diff_ws_res.returncode == 0 else ""

        # Restore tests/ and the test config exactly as in the base commit, to prevent tampering and
        # ensure clean patch application. Deleting tests/ first also drops test files the agent added
        # (even ones it committed), which may depend on mock changes that are reverted here.
        await sandbox().exec(["rm", "-rf", "tests"], cwd="/repo")
        await sandbox().exec(
            ["git", "checkout", base_commit, "--", "tests/", "vitest.config.ts"],
            cwd="/repo",
        )

        # Resolve test patch path (checking src/ and repo root)
        if patch_path is None:
            resolved_path = Path(__file__).resolve().parent / "test.patch"
            if not resolved_path.exists():
                resolved_path = Path(__file__).resolve().parent.parent / "test.patch"
        else:
            resolved_path = Path(patch_path)

        # Read test patch with encoding detection and LF newline normalization
        raw_bytes = resolved_path.read_bytes()
        encoding = "utf-16" if raw_bytes.startswith((b"\xff\xfe", b"\xfe\xff")) else "utf-8"
        patch_content = raw_bytes.decode(encoding).replace("\r\n", "\n")

        # Write the normalized test patch into the sandbox
        patch_filename = "/tmp/eval_test.patch"
        await sandbox().write_file(patch_filename, patch_content)

        # Apply the evaluation test patch
        apply_res: ExecResult = await sandbox().exec(
            ["git", "apply", "--whitespace=nowarn", patch_filename],
            cwd="/repo",
        )
        if apply_res.returncode != 0:
            return Score.unscored(
                reason="scoring_failed",
                explanation=f"Error applying test patch: {apply_res.stdout}\n{apply_res.stderr}",
            )

        # Run vitest directly (not via the package.json script, which the agent can edit)
        result: ExecResult = await sandbox().exec(
            ["node_modules/.bin/vitest", "run", "--no-color"],
            cwd="/repo",
            env={"NO_COLOR": "1", "CI": "true"},
        )

        raw_output = result.stdout if result.returncode == 0 else f"{result.stdout}\n{result.stderr}"
        # Strip any remaining ANSI escape sequences to prevent garbled characters in Inspect UI
        clean_explanation = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw_output)

        return Score(
            value=CORRECT if result.returncode == 0 else INCORRECT,
            explanation=clean_explanation,
            metadata={"model_patch": agent_patch, "model_patch_ignore_whitespace": agent_patch_ignore_ws},
        )

    return score


@task
def swe_daylio_popout(message_limit: int = 200, attempts: int = 1) -> Task:
    dataset = [
        Sample(
            id="daylio-popout-window-note-open",
            input=ISSUE_DESCRIPTION,
            metadata={"base_commit": BASE_COMMIT},
        )
    ]

    return Task(
        dataset=dataset,
        solver=safe_agent_solver(
            react(
                prompt=AGENT_PROMPT,
                tools=[bash(), text_editor()],
                attempts=attempts,
            )
        ),
        scorer=npm_test_scorer(),
        sandbox="docker",
        message_limit=message_limit,
        score_on_error=True,
        fail_on_error=True,
    )
