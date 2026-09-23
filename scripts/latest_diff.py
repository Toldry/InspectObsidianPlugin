#!/usr/bin/env python3
"""
latest_diff.py

Quickly inspect the model's git diff (model_patch) from the latest (or specified) evaluation log.

Usage:
    python scripts/latest_diff.py
    python scripts/latest_diff.py --log logs/<file>.eval
    python scripts/latest_diff.py --ignore-whitespace   # hide indentation churn (newer logs only)
"""

import argparse
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
    parser = argparse.ArgumentParser(description="View model git diff from latest eval log.")
    parser.add_argument("--log", "-l", type=str, default=None, help="Path to specific .eval file.")
    parser.add_argument("--logs-dir", type=str, default="./logs", help="Path to logs directory.")
    parser.add_argument(
        "--ignore-whitespace",
        "-w",
        action="store_true",
        help="Show the whitespace-insensitive diff (model_patch_ignore_whitespace), if the log has one.",
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
        found = False
        if sample.scores:
            for scorer_name, score in sample.scores.items():
                key = "model_patch"
                if args.ignore_whitespace:
                    if score.metadata and "model_patch_ignore_whitespace" in score.metadata:
                        key = "model_patch_ignore_whitespace"
                    else:
                        print("  (No whitespace-insensitive diff in this log; showing the full diff)")
                if score.metadata and key in score.metadata:
                    patch = score.metadata[key]
                    if patch.strip():
                        print(patch)
                    else:
                        print("  (Empty diff - agent made no git changes)")
                    found = True
        if not found:
            print("  (No model_patch recorded in score metadata)")
        print("=" * 80)


if __name__ == "__main__":
    main()
