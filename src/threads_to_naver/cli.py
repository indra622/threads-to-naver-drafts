from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from .config import Config
from .naver import NaverDraftWriter
from .secrets import setup_threads_token
from .service import backfill, run


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="threads-to-naver",
        description="Copy Threads posts verbatim into private Naver Blog drafts.",
    )
    parser.add_argument("--config", type=Path, help="Path to config.toml")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("setup-token", help="Save a Threads token in macOS Keychain")
    subparsers.add_parser("login", help="Open the persistent browser for Naver login")

    run_parser = subparsers.add_parser("run", help="Create drafts for one day")
    date_group = run_parser.add_mutually_exclusive_group()
    date_group.add_argument(
        "--date",
        help="Source date in YYYY-MM-DD; defaults to yesterday",
    )
    date_group.add_argument(
        "--latest",
        action="store_true",
        help="Use only the newest post from the last 30 days",
    )
    run_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and render JSON without opening Naver",
    )

    backfill_parser = subparsers.add_parser(
        "backfill",
        help="Create drafts for every historical original post",
    )
    backfill_parser.add_argument(
        "--limit",
        type=int,
        help="Maximum drafts to create in this resumable batch",
    )
    backfill_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Fetch and render JSON without opening Naver",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "setup-token":
            setup_threads_token()
            return 0

        config = Config.load(args.config)
        config.ensure_directories()
        if args.command == "login":
            with NaverDraftWriter(config) as writer:
                writer.login()
            return 0

        if args.command == "backfill":
            if args.limit is not None and args.limit < 1:
                raise ValueError("--limit must be at least 1")
            count = backfill(config, dry_run=args.dry_run, limit=args.limit)
            print(f"Completed: {count} item(s).")
            return 0

        target_date = (
            date.fromisoformat(args.date)
            if args.date
            else datetime_today(config) - timedelta(days=1)
        )
        count = run(
            config,
            target_date,
            dry_run=args.dry_run,
            latest_only=args.latest,
        )
        print(f"Completed: {count} item(s).")
        return 0
    except (FileNotFoundError, RuntimeError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1


def datetime_today(config: Config) -> date:
    from datetime import datetime

    return datetime.now(config.timezone).date()


if __name__ == "__main__":
    raise SystemExit(main())
