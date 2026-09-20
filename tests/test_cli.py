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
