"""
Validate the task without Docker: rebuild the evaluation base exactly like the Dockerfile
(upstream commit + env.patch, deterministic SHA), then run the hidden tests (test.patch) on:

  1. the base commit            -> must FAIL (the tests detect the bug)
  2. base + gold.patch          -> must PASS (the reference fix satisfies the tests)
  3. base + a model patch       -> reported only (optional, via --log or --patch)

The test run mirrors npm_test_scorer: tests/ and vitest.config.ts are restored from the base
commit before test.patch is applied.

Requires git, Node.js and network access (git fetch + npm ci).

Usage:
    python scripts/validate_task.py
    python scripts/validate_task.py --log logs/<file>.eval      # also replay that run's model_patch
    python scripts/validate_task.py --patch some.diff --keep     # replay a diff, keep the work dir
"""

import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DOCKERFILE = ROOT / "Dockerfile"
ENV_PATCH = ROOT / "env.patch"
GOLD_PATCH = ROOT / "gold.patch"
TEST_PATCH = ROOT / "test.patch"

COMMIT_ENV = {
    "GIT_AUTHOR_NAME": "User",
    "GIT_AUTHOR_EMAIL": "user@example.com",
    "GIT_COMMITTER_NAME": "User",
    "GIT_COMMITTER_EMAIL": "user@example.com",
    "GIT_AUTHOR_DATE": "2026-08-22T16:31:34+02:00",
    "GIT_COMMITTER_DATE": "2026-08-22T16:31:34+02:00",
}
COMMIT_MESSAGE = "test: extend Obsidian API test mock"


def dockerfile_arg(name: str) -> str:
    match = re.search(rf"^ARG {name}=(\S+)", DOCKERFILE.read_text(encoding="utf-8"), re.M)
    if not match:
        sys.exit(f"Could not find ARG {name} in {DOCKERFILE}")
    return match.group(1)


def run(cmd: list[str], cwd: Path, env: dict | None = None, check: bool = True) -> subprocess.CompletedProcess:
    exe = shutil.which(cmd[0]) or cmd[0]  # resolves npm.cmd on Windows
    result = subprocess.run(
        [exe, *cmd[1:]],
        cwd=cwd,
        env={**os.environ, **(env or {})},
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if check and result.returncode != 0:
        sys.exit(f"Command failed: {' '.join(cmd)}\n{result.stdout}\n{result.stderr}")
    return result


def lf_patch(path: Path, dest: Path) -> Path:
    """Write a copy of an LF-only patch with CRLF normalized (like the Dockerfile and scorer do)."""
    dest.write_bytes(path.read_bytes().replace(b"\r\n", b"\n"))
    return dest


def build_base(repo: Path, upstream: str, upstream_commit: str, base_commit: str) -> None:
    print(f"Building base: {upstream}@{upstream_commit[:10]} + env.patch")
    run(["git", "init", "-q"], repo)
    run(["git", "config", "core.autocrlf", "false"], repo)
    run(["git", "remote", "add", "origin", upstream], repo)
    run(["git", "fetch", "-q", "--depth", "1", "origin", upstream_commit], repo)
    run(["git", "checkout", "-q", "-b", "main", "FETCH_HEAD"], repo)
    run(["git", "remote", "remove", "origin"], repo)
    run(["git", "apply", str(lf_patch(ENV_PATCH, repo.parent / "env.patch"))], repo)
    run(["git", "add", "-A"], repo)
    run(["git", "commit", "-q", "-m", COMMIT_MESSAGE], repo, env=COMMIT_ENV)
    sha = run(["git", "rev-parse", "HEAD"], repo).stdout.strip()
    if sha != base_commit:
        sys.exit(f"Base SHA mismatch: built {sha}, Dockerfile expects {base_commit}")
    print(f"  base commit {sha} matches the Dockerfile")
    print("Installing npm dependencies (npm ci)...")
    run(["npm", "ci", "--no-audit", "--no-fund"], repo)
    run(["git", "reset", "-q", "--hard"], repo)


def run_hidden_tests(repo: Path, base_commit: str, label: str, patch: Path | None) -> tuple[bool, str]:
    """Reset to base, apply an optional source patch, restore tests like the scorer, run vitest."""
    run(["git", "reset", "-q", "--hard", base_commit], repo)
    run(["git", "clean", "-fdq", "-e", "node_modules"], repo)
    if patch is not None:
        # tests/ and vitest.config.ts are restored from base below anyway, so skip them here
        applied = run(
            ["git", "apply", "--whitespace=nowarn", "--exclude=tests/*", "--exclude=vitest.config.ts", str(patch)],
            repo,
            check=False,
        )
        if applied.returncode != 0:
            return False, f"{label}: patch did not apply\n{applied.stderr}"
    shutil.rmtree(repo / "tests")
    run(["git", "checkout", base_commit, "--", "tests/", "vitest.config.ts"], repo)
    run(["git", "apply", "--whitespace=nowarn", str(lf_patch(TEST_PATCH, repo.parent / "test.patch"))], repo)

    result = run(["node", "node_modules/vitest/vitest.mjs", "run", "--no-color"], repo, env={"NO_COLOR": "1", "CI": "true"}, check=False)
    output = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", result.stdout + result.stderr)
    totals = re.findall(r"^\s*Tests\s+(.*)$", output, re.M)
    failed = sorted({line.strip() for line in re.findall(r"^\s*FAIL\s+(.*)$", output, re.M)})
    summary = [f"{label}: {'PASS' if result.returncode == 0 else 'FAIL'} ({totals[-1] if totals else 'no test summary'})"]
    summary += [f"    x {name}" for name in failed]
    return result.returncode == 0, "\n".join(summary)


def model_patch_from_log(log_path: Path, dest: Path) -> Path:
    from inspect_ai.log import read_eval_log

    log = read_eval_log(str(log_path))
    for sample in log.samples or []:
        for score in (sample.scores or {}).values():
            patch = (score.metadata or {}).get("model_patch")
            if patch:
                dest.write_text(patch, encoding="utf-8", newline="")
                return dest
    sys.exit(f"No model_patch found in {log_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--upstream", default=dockerfile_arg("UPSTREAM_REPO"), help="Upstream git URL or local path")
    parser.add_argument("--log", type=Path, help="Eval log whose model_patch should be replayed")
    parser.add_argument("--patch", type=Path, help="Diff (against the base commit) to replay")
    parser.add_argument("--keep", action="store_true", help="Keep the temporary work directory")
    args = parser.parse_args()

    upstream_commit = dockerfile_arg("UPSTREAM_COMMIT")
    base_commit = dockerfile_arg("BASE_COMMIT")
    task_src = (ROOT / "src" / "swe_daylio_popout.py").read_text(encoding="utf-8")
    if f'BASE_COMMIT = "{base_commit}"' not in task_src:
        sys.exit("BASE_COMMIT in src/swe_daylio_popout.py does not match the Dockerfile")

    work = Path(tempfile.mkdtemp(prefix="daylio-validate-"))
    repo = work / "repo"
    repo.mkdir()
    ok = True
    try:
        build_base(repo, args.upstream, upstream_commit, base_commit)

        base_ok, base_report = run_hidden_tests(repo, base_commit, "base (expect FAIL)", None)
        print(base_report)
        if base_ok:
            ok = False
            print("  !! hidden tests pass without any fix: they don't detect the bug")

        gold_ok, gold_report = run_hidden_tests(repo, base_commit, "base + gold.patch (expect PASS)", GOLD_PATCH)
        print(gold_report)
        ok = ok and gold_ok

        replay = args.patch.resolve() if args.patch else None
        if args.log:
            replay = model_patch_from_log(args.log, work / "model.patch")
        if replay:
            _, replay_report = run_hidden_tests(repo, base_commit, f"base + {args.log or args.patch}", replay)
            print(replay_report)
    finally:
        if args.keep:
            print(f"Work directory kept at {work}")
        else:
            shutil.rmtree(work, ignore_errors=True)

    print("\nVALIDATION", "OK" if ok else "FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
