"""
main.py
CLI entry point for the financial research agent.

Usage:
    python main.py                                         # auto-discover theme
    python main.py --topic "AI chip demand"                # specific topic
    python main.py --topic "AI chip demand" --quality high # use Opus
    python main.py --topic "AI chip demand" --commit       # auto-commit report
"""

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Autonomous financial research agent"
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Theme to analyze (e.g. 'AI chip demand'). If omitted, auto-discovers from news.",
    )
    parser.add_argument(
        "--quality",
        choices=["standard", "high"],
        default="standard",
        help="'standard' uses claude-sonnet-4-6 (default). 'high' uses claude-opus-4-6.",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Auto-commit the generated report folder to git after completion.",
    )
    return parser.parse_args()


def git_commit_report(report_dir: Path, theme: str):
    from datetime import datetime
    date_str = datetime.utcnow().strftime("%Y-%m-%d")
    msg = f"Research report: {theme} ({date_str})"
    try:
        subprocess.run(["git", "add", str(report_dir)], check=True)
        subprocess.run(["git", "commit", "-m", msg], check=True)
        print(f"\nCommitted: {msg}")
    except subprocess.CalledProcessError as e:
        print(f"\nGit commit failed: {e}", file=sys.stderr)


def status(msg: str):
    print(f"  → {msg}")


def main():
    args = parse_args()

    print("\n╔══════════════════════════════════════════╗")
    print("║   Financial Research Agent               ║")
    print("╚══════════════════════════════════════════╝\n")

    if args.topic:
        print(f"Topic:   {args.topic}")
    else:
        print("Topic:   auto-discover from market signals")
    print(f"Quality: {args.quality} ({'claude-opus-4-6' if args.quality == 'high' else 'claude-sonnet-4-6'})")
    print()

    from pipeline import run_pipeline

    report_dir = run_pipeline(
        topic=args.topic,
        quality=args.quality,
        on_status=status,
    )

    print(f"\n✓ Report ready: {report_dir}/report.md\n")

    if args.commit:
        theme_name = report_dir.name.split("_", 1)[1].replace("-", " ")
        git_commit_report(report_dir, theme_name)


if __name__ == "__main__":
    main()
