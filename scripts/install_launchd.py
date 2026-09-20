from __future__ import annotations

import argparse
import plistlib
from pathlib import Path

LABEL = "local.threads-to-naver-drafts"


def main() -> int:
    parser = argparse.ArgumentParser(description="Install the daily launchd job.")
    parser.add_argument("--hour", type=int, default=11)
    parser.add_argument("--minute", type=int, default=0)
    args = parser.parse_args()
    if not 0 <= args.hour <= 23 or not 0 <= args.minute <= 59:
        parser.error("hour/minute out of range")

    project = Path(__file__).resolve().parents[1]
    executable = project / ".venv" / "bin" / "threads-to-naver"
    if not executable.exists():
        raise SystemExit("Install the project first: uv sync --extra dev")

    log_dir = Path.home() / "Library" / "Logs" / "threads-to-naver"
    log_dir.mkdir(parents=True, exist_ok=True)
    plist_path = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"
    payload = {
        "Label": LABEL,
        "ProgramArguments": [str(executable), "run"],
        "WorkingDirectory": str(project),
        "StartCalendarInterval": {"Hour": args.hour, "Minute": args.minute},
        "StandardOutPath": str(log_dir / "stdout.log"),
        "StandardErrorPath": str(log_dir / "stderr.log"),
        "ProcessType": "Background",
    }
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    with plist_path.open("wb") as file:
        plistlib.dump(payload, file)
    print(f"Wrote {plist_path}")
    print(f"Enable with: launchctl bootstrap gui/$(id -u) {plist_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
