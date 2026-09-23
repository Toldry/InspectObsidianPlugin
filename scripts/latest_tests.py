#!/usr/bin/env python3
"""
latest_tests.py

Quickly inspect the unit test / scorer output (explanation) from the latest (or specified) evaluation log.

Usage:
    python scripts/latest_tests.py
    python scripts/latest_tests.py --log logs/<file>.eval
    python scripts/latest_tests.py --failures-only
"""

import argparse
import re
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

try:
    from inspect_ai.log import read_eval_log
except ImportError:
    print("Error: inspect_ai is not installed in the current environment.", file=sys.stderr)
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="View test execution output from latest eval log.")
    parser.add_argument("--log", "-l", type=str, default=None, help="Path to specific .eval file.")
    parser.add_argument("--logs-dir", type=str, default="./logs", help="Path to logs directory.")
    parser.add_argument(
        "--failures-only", "-f", action="store_true", help="Filter and display only failure/error lines."
    )
    args = parser.parse_args()

    if args.log:
        log_path = Path(args.log)
    else:
        logs_dir = Path(args.logs_dir)
        eval_files = list(logs_dir.glob("*.eval"))
        if not eval_files:
            print("No .eval files found in logs directory.", file=sys.stderr)
            sys.exit(1)
        log_path = max(eval_files, key=lambda p: p.stat().st_mtime)

    log = read_eval_log(str(log_path))
    print(f"Log: {log_path.name}")
    print("=" * 80)

    for i, sample in enumerate(getattr(log, "samples", []) or []):
        print(f"Sample [{i}] ({sample.id}):")
        if not sample.scores:
            print("  (No scores recorded)")
            continue

        for scorer_name, score in sample.scores.items():
            reason_str = f" (reason: {score.reason})" if getattr(score, "reason", None) else ""
            print(f"  Scorer: {scorer_name} | Result: {score.value}{reason_str}")
            print("-" * 80)
            explanation = score.explanation or "(No explanation)"
            # Clean ANSI escape sequences if any legacy ones are stored in the log
            cleaned = re.sub(r"\x1b\[[0-9;]*[a-zA-Z]", "", explanation)

            if args.failures_only:
                lines = cleaned.splitlines()
                matching_lines = [
                    l for l in lines
                    if any(kw in l for kw in ("FAIL", "failed", "Error", "AssertionError", "error:"))
                ]
                if matching_lines:
                    print("\n".join(matching_lines))
                else:
                    print("No failure keywords found in test output.")
            else:
                print(cleaned)
        print("=" * 80)


if __name__ == "__main__":
    main()
