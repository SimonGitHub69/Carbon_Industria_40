"""Evita più istanze del poller (es. servizio stoppato ma python ancora vivo)."""

from __future__ import annotations

import atexit
import logging
import os
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

_lock_path: Path | None = None
_lock_fh = None


def acquire_lock(lock_dir: Path) -> Path:
    global _lock_path, _lock_fh
    lock_dir.mkdir(parents=True, exist_ok=True)
    path = lock_dir / "modbus_poller.pid"
    if path.exists():
        try:
            old_pid = int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            old_pid = None
        if old_pid and _is_our_poller(old_pid):
            raise RuntimeError(
                f"Poller già in esecuzione (PID {old_pid}). "
                f"In PowerShell: Stop-Process -Id {old_pid} -Force "
                f"oppure elimina {path}"
            )
        logger.warning("Rimuovo lock stale: %s", path)
        path.unlink(missing_ok=True)

    fh = open(path, "w", encoding="utf-8")
    fh.write(str(os.getpid()))
    fh.flush()
    _lock_path = path
    _lock_fh = fh
    atexit.register(release_lock)
    logger.info("Instance lock: %s (PID %s)", path, os.getpid())
    return path


def release_lock() -> None:
    global _lock_path, _lock_fh
    if _lock_fh is not None:
        try:
            _lock_fh.close()
        except Exception:
            pass
        _lock_fh = None
    if _lock_path is not None and _lock_path.exists():
        try:
            _lock_path.unlink()
        except Exception:
            pass
        _lock_path = None


def _is_our_poller(pid: int) -> bool:
    """True solo se il PID è vivo E la command line contiene modbus_poller."""
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            out = subprocess.check_output(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    f"(Get-CimInstance Win32_Process -Filter \"ProcessId={pid}\").CommandLine",
                ],
                text=True,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).strip()
            return bool(out) and "modbus_poller" in out
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
