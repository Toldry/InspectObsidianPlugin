#!/usr/bin/env python3
"""
inspect_latest_log.py

Utility to quickly inspect, summarize, and debug the latest (or specified)
Inspect AI evaluation log (.eval file) without encoding issues or verbose noise.

Usage:
    python scripts/inspect_latest_log.py                  # Summary of latest log
    python scripts/inspect_latest_log.py --messages       # View agent trajectory & tool calls
    python scripts/inspect_latest_log.py --explanation    # View full test runner / scorer output
    python scripts/inspect_latest_log.py --patch          # View the model diff patch
    python scripts/inspect_latest_log.py --all            # Complete report
    python scripts/inspect_latest_log.py --log <path>     # Inspect a specific log file
    python scripts/inspect_latest_log.py --list           # List recent log files
"""

import argparse
from datetime import datetime
import sys
from pathlib import Path

# Ensure UTF-8 output even in Windows cmd/PowerShell to prevent charmap crashes
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

try:
    from inspect_ai.log import read_eval_log
except ImportError:
    print("Error: inspect_ai is not installed in the current environment.", file=sys.stderr)
    sys.exit(1)


def find_latest_log(logs_dir: Path) -> Path | None:
    """Find the most recently modified .eval file in the logs directory."""
    if not logs_dir.exists():
        return None
    eval_files = list(logs_dir.glob("*.eval"))
    if not eval_files:
        return None
    return max(eval_files, key=lambda p: p.stat().st_mtime)


def list_recent_logs(logs_dir: Path, count: int = 10):
    """List recent log files sorted by modification time."""
    if not logs_dir.exists():
        print(f"Directory not found: {logs_dir}")
        return
    eval_files = sorted(logs_dir.glob("*.eval"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not eval_files:
        print(f"No .eval files found in {logs_dir}")
        return

    print(f"Recent evaluation logs in {logs_dir} (latest first):")
    print("-" * 80)
    for p in eval_files[:count]:
        mtime = datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")
        size_kb = p.stat().st_size / 1024
        print(f"  {mtime} | {size_kb:6.1f} KB | {p.name}")
    print("-" * 80)


def print_summary(log, log_path: Path):
    print("=" * 80)
    print(f"EVAL LOG SUMMARY: {log_path.name}")
    print("=" * 80)
    print(f"File Path   : {log_path.resolve()}")
    print(f"Status      : {log.status}")
    if hasattr(log, "eval"):
        eval_spec = log.eval
        print(f"Task        : {eval_spec.task}")
        print(f"Model       : {eval_spec.model}")
        print(f"Created     : {eval_spec.created}")
        if eval_spec.task_args:
            print(f"Task Args   : {eval_spec.task_args}")
        if eval_spec.config:
            limits = []
            for limit_attr in ("message_limit", "token_limit", "time_limit"):
                val = getattr(eval_spec.config, limit_attr, None)
                if val is not None:
                    limits.append(f"{limit_attr}={val}")
            if limits:
                print(f"Limits      : {', '.join(limits)}")

    if hasattr(log, "stats") and log.stats:
        started = getattr(log.stats, "started_at", None)
        completed = getattr(log.stats, "completed_at", None)
        if started and completed:
            try:
                dt_start = datetime.fromisoformat(started) if isinstance(started, str) else started
                dt_end = datetime.fromisoformat(completed) if isinstance(completed, str) else completed
                duration = (dt_end - dt_start).total_seconds()
                print(f"Duration    : {duration:.1f}s")
            except Exception:
                pass

        usage = getattr(log.stats, "model_usage", None)
        if usage:
            print("Token Usage :")
            for model_id, u in usage.items():
                in_tok = getattr(u, "input_tokens", 0)
                out_tok = getattr(u, "output_tokens", 0)
                tot_tok = getattr(u, "total_tokens", 0)
                print(f"  [{model_id}] Input: {in_tok:,} | Output: {out_tok:,} | Total: {tot_tok:,}")

    samples = getattr(log, "samples", []) or []
    print(f"Samples     : {len(samples)}")

    for i, sample in enumerate(samples):
        print(f"\n--- Sample [{i}] (id: {sample.id}) ---")
        if sample.limit:
            print(f"Limit Notice: {sample.limit}")

        total_msgs = len(sample.messages) if sample.messages else 0
        print(f"Messages    : {total_msgs}")

        if sample.scores:
            print("Scores      :")
            for scorer_name, score in sample.scores.items():
                print(f"  [{scorer_name}] = {score.value}")
                if score.metadata and "model_patch" in score.metadata:
                    patch = score.metadata["model_patch"]
                    patch_lines = len(patch.splitlines()) if patch else 0
                    print(f"    model_patch: {patch_lines} line(s) changed")
                if score.explanation:
                    first_lines = score.explanation.strip().splitlines()[:5]
                    preview = "\n      ".join(first_lines)
                    print(f"    explanation preview:\n      {preview}")
                    if len(score.explanation.strip().splitlines()) > 5:
                        print("      [... run with --explanation to see full output ...]")
        else:
            print("Scores      : None")
    print("=" * 80)


def print_messages(log, full: bool = False):
    samples = getattr(log, "samples", []) or []
    for s_idx, sample in enumerate(samples):
        print("\n" + "=" * 80)
        print(f"MESSAGES TRAJECTORY - Sample [{s_idx}] (id: {sample.id})")
        print("=" * 80)
        for m_idx, msg in enumerate(sample.messages or []):
            role = msg.role.upper()
            print(f"\n[{m_idx}] {role}:")

            # Print tool calls if present
            tool_calls = getattr(msg, "tool_calls", None)
            if tool_calls:
                for tc in tool_calls:
                    print(f"  -> Tool Call: {tc.function}({tc.arguments})")

            # Print tool error or source if present
            tool_call_id = getattr(msg, "tool_call_id", None)
            if tool_call_id:
                print(f"  (tool_call_id: {tool_call_id})")

            # Print text content
            content = msg.content
            if isinstance(content, list):
                text_parts = [p.text for p in content if hasattr(p, "text")]
                text = "\n".join(text_parts)
            else:
                text = str(content) if content else ""

            if text:
                if not full and len(text) > 400:
                    preview = text[:400].replace("\n", "\n  ")
                    print(f"  {preview}\n  [... truncated, use --full-content to see all ...]")
                else:
                    indented = text.replace("\n", "\n  ")
                    print(f"  {indented}")


def print_explanation(log):
    samples = getattr(log, "samples", []) or []
    for s_idx, sample in enumerate(samples):
        print("\n" + "=" * 80)
        print(f"SCORER EXPLANATION - Sample [{s_idx}] (id: {sample.id})")
        print("=" * 80)
        if not sample.scores:
            print("No scores recorded.")
            continue
        for scorer_name, score in sample.scores.items():
            print(f"\n--- Scorer: {scorer_name} | Value: {score.value} ---")
            if score.explanation:
                print(score.explanation)
            else:
                print("(No explanation provided)")


def print_patch(log):
    samples = getattr(log, "samples", []) or []
    for s_idx, sample in enumerate(samples):
        print("\n" + "=" * 80)
        print(f"MODEL PATCH - Sample [{s_idx}] (id: {sample.id})")
        print("=" * 80)
        has_patch = False
        if sample.scores:
            for scorer_name, score in sample.scores.items():
                if score.metadata and "model_patch" in score.metadata:
                    patch = score.metadata["model_patch"]
                    if patch.strip():
                        print(patch)
                        has_patch = True
                    else:
                        print(f"[{scorer_name}] model_patch is empty (no changes made by agent).")
                        has_patch = True
        if not has_patch:
            print("No model_patch found in scorer metadata.")


def main():
    parser = argparse.ArgumentParser(
        description="Inspect and summarize Inspect AI evaluation logs."
    )
    parser.add_argument(
        "--log", "-l",
        type=str,
        default=None,
        help="Path to specific .eval log file. Defaults to latest in ./logs",
    )
    parser.add_argument(
        "--messages", "-m",
        action="store_true",
        help="Display message conversation trajectory and tool calls.",
    )
    parser.add_argument(
        "--explanation", "-e",
        action="store_true",
        help="Display the full test scorer explanation / test runner stdout.",
    )
    parser.add_argument(
        "--patch", "-p",
        action="store_true",
        help="Display the git patch created by the model.",
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="Display summary, messages trajectory, explanation, and model patch.",
    )
    parser.add_argument(
        "--full-content",
        action="store_true",
        help="Do not truncate long message bodies when viewing messages.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List recent evaluation logs in the logs directory.",
    )
    parser.add_argument(
        "--logs-dir",
        type=str,
        default="./logs",
        help="Directory where .eval files are stored (default: ./logs)",
    )

    args = parser.parse_args()
    logs_dir = Path(args.logs_dir)

    if args.list:
        list_recent_logs(logs_dir)
        return

    if args.log:
        log_path = Path(args.log)
    else:
        log_path = find_latest_log(logs_dir)
        if not log_path:
            print(f"Error: No .eval files found in {logs_dir.resolve()}", file=sys.stderr)
            sys.exit(1)

    if not log_path.exists():
        print(f"Error: File not found: {log_path}", file=sys.stderr)
        sys.exit(1)

    try:
        log = read_eval_log(str(log_path))
    except Exception as e:
        print(f"Error reading eval log {log_path}: {e}", file=sys.stderr)
        sys.exit(1)

    # If no specific view flag was passed, default to summary
    default_view = not (args.messages or args.explanation or args.patch or args.all)

    if default_view or args.all:
        print_summary(log, log_path)

    if args.messages or args.all:
        print_messages(log, full=args.full_content)

    if args.explanation or args.all:
        print_explanation(log)

    if args.patch or args.all:
        print_patch(log)


if __name__ == "__main__":
    main()
