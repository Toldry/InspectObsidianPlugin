from pathlib import Path
import re

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

# Issue description based on the commit message
ISSUE_DESCRIPTION = """
Bug: When clicking a daylio event label while the mood graph is in a new/separate window, it does not open the corresponding note. 

Also, if an entire window has only the daylio graph, and i click a label, then it opens the note in the same window.
it's supposed to work like this instead: if the daylio graph is in its own window without any notes open, then when a user clicks on a label, it will open the note in the other (original/first) window.


Additionaly, a modifier key click (Ctrl/Cmd + Click) from an isolated popout window should opens in a new tab, Ctrl/Cmd + Alt + Click for a split in the target window.
"""

AGENT_PROMPT = """You are an expert software engineer. Your task is to resolve the reported issue in the repository located at /repo.
Investigate the codebase, implement the necessary fix, and verify your solution before completing the task."""


@scorer(metrics=[accuracy(), stderr()])
def npm_test_scorer(patch_path: Path | str = Path(__file__).parent / "test.patch"):
    """Scorer that isolates agent changes, applies SWE-bench evaluation test patch, and runs npm test."""
    async def score(state: TaskState, target: Target) -> Score:
        base_commit = state.metadata.get("base_commit", "91887ba8fae8068ff3f02e37c62d565221a8ee48")

        # Capture the agent's patch against the base commit for logging/auditability
        diff_res: ExecResult = await sandbox().exec(
            ["git", "diff", base_commit],
            cwd="/repo",
        )
        agent_patch = diff_res.stdout if diff_res.returncode == 0 else ""

        # Revert any agent modifications to tests/ to prevent tampering and ensure clean patch application
        await sandbox().exec(
            ["git", "checkout", base_commit, "--", "tests/"],
            cwd="/repo",
        )

        # Read test patch with encoding detection and LF newline normalization
        path = Path(patch_path)
        raw_bytes = path.read_bytes()
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

        # Run test suite in the sandbox without color escape codes
        result: ExecResult = await sandbox().exec(
            ["npm", "run", "test", "--", "--no-color"],
            cwd="/repo",
            env={"NO_COLOR": "1", "CI": "true"},
        )

        raw_output = result.stdout if result.returncode == 0 else f"{result.stdout}\n{result.stderr}"
        # Strip any remaining ANSI escape sequences to prevent garbled characters in Inspect UI
        clean_explanation = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", raw_output)

        return Score(
            value=CORRECT if result.returncode == 0 else INCORRECT,
            explanation=clean_explanation,
            metadata={"model_patch": agent_patch},
        )

    return score


@task
def swe_daylio_popout(message_limit: int = 5, attempts: int = 1) -> Task:
    dataset = [
        Sample(
            id="daylio-popout-window-note-open",
            input=ISSUE_DESCRIPTION,
            metadata={"base_commit": "91887ba8fae8068ff3f02e37c62d565221a8ee48"},
        )
    ]

    return Task(
        dataset=dataset,
        solver=react(
            prompt=AGENT_PROMPT,
            tools=[bash(), text_editor()],
            attempts=attempts,
        ),
        scorer=npm_test_scorer(),
        sandbox="docker",
        message_limit=message_limit,
    )
