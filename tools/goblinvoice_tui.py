from __future__ import annotations

import argparse
import os
import signal
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from goblinvoice.config import load_settings


@dataclass(slots=True)
class ManagedProcess:
    name: str
    command: list[str]
    pid_path: Path
    log_path: Path


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _read_pid(pid_path: Path) -> int | None:
    if not pid_path.exists():
        return None
    content = pid_path.read_text(encoding="utf-8").strip()
    if not content:
        return None
    try:
        return int(content)
    except ValueError:
        return None


def _start_process(proc: ManagedProcess) -> str:
    pid = _read_pid(proc.pid_path)
    if pid is not None and _is_running(pid):
        return f"{proc.name}: already running (pid {pid})"

    proc.pid_path.parent.mkdir(parents=True, exist_ok=True)
    proc.log_path.parent.mkdir(parents=True, exist_ok=True)

    with proc.log_path.open("a", encoding="utf-8") as log_file:
        handle = subprocess.Popen(  # noqa: S603
            proc.command,
            stdout=log_file,
            stderr=log_file,
            start_new_session=True,
        )

    proc.pid_path.write_text(f"{handle.pid}\n", encoding="utf-8")
    return f"{proc.name}: started (pid {handle.pid})"


def _stop_process(proc: ManagedProcess) -> str:
    pid = _read_pid(proc.pid_path)
    if pid is None:
        return f"{proc.name}: not running"

    if not _is_running(pid):
        proc.pid_path.unlink(missing_ok=True)
        return f"{proc.name}: stale pid file removed"

    os.kill(pid, signal.SIGTERM)
    proc.pid_path.unlink(missing_ok=True)
    return f"{proc.name}: stopped (pid {pid})"


def _status_process(proc: ManagedProcess) -> str:
    pid = _read_pid(proc.pid_path)
    if pid is None:
        return f"{proc.name}: stopped"
    if _is_running(pid):
        return f"{proc.name}: running (pid {pid})"
    return f"{proc.name}: stale pid file"


def main() -> None:
    parser = argparse.ArgumentParser(description="GoblinVoice process manager")
    parser.add_argument("--up", action="store_true", help="start API and bot")
    parser.add_argument("--down", action="store_true", help="stop API and bot")
    parser.add_argument("--status", action="store_true", help="show service status")
    args = parser.parse_args()

    settings = load_settings()
    services = [
        ManagedProcess(
            name="goblinvoice-api",
            command=[sys.executable, "-m", "goblinvoice.api.app"],
            pid_path=settings.pids_path / "goblinvoice-api.pid",
            log_path=settings.logs_path / "api.log",
        ),
        ManagedProcess(
            name="goblinvoice-bot",
            command=[sys.executable, "-m", "goblinvoice.bot.client"],
            pid_path=settings.pids_path / "goblinvoice-bot.pid",
            log_path=settings.logs_path / "bot.log",
        ),
    ]

    if args.up:
        for service in services:
            print(_start_process(service))
        return

    if args.down:
        for service in services:
            print(_stop_process(service))
        return

    if args.status:
        for service in services:
            print(_status_process(service))
        return

    parser.print_help()


if __name__ == "__main__":
    main()
