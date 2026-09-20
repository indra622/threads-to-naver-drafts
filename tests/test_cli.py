import pytest

from threads_to_naver.cli import build_parser


def test_latest_and_date_are_mutually_exclusive() -> None:
    parser = build_parser()
    with pytest.raises(SystemExit):
        parser.parse_args(["run", "--latest", "--date", "2026-09-19"])


def test_latest_flag_is_available() -> None:
    args = build_parser().parse_args(["run", "--latest", "--dry-run"])
    assert args.latest is True
    assert args.dry_run is True


def test_backfill_limit_is_available() -> None:
    args = build_parser().parse_args(["backfill", "--limit", "25", "--dry-run"])
    assert args.command == "backfill"
    assert args.limit == 25
    assert args.dry_run is True


def test_append_footer_limit_is_available() -> None:
    args = build_parser().parse_args(
        ["append-footer", "--limit", "10", "--dry-run"]
    )
    assert args.command == "append-footer"
    assert args.limit == 10
    assert args.dry_run is True
