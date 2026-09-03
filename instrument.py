"""The transport server, wrapped.

Everything instrument-specific lives here; the notebook only calls the three
functions at the bottom. This mirrors examples/Lockin_sweep.py exactly:

    with CESession() as exp:
        exp.Transport.LockinSweep(exp_folder, exp_comments, sweep_config,
                                  run_continuous=False)

``flex`` is imported lazily, so the notebook still opens (and rehearsal mode
still works) on a machine that cannot reach the instrument.
"""

from __future__ import annotations

import time
from pathlib import Path

_import_error: str = ""

try:
    from flex.exp.CESession import CESession
except Exception as exc:  # noqa: BLE001 - absence is a normal state here
    CESession = None
    _import_error = f"{type(exc).__name__}: {exc}"


def is_available() -> bool:
    """True when a real sweep can be run from this machine."""
    return CESession is not None


def describe() -> str:
    """One line for the notebook's status bar."""
    if is_available():
        return "Transport server reachable — CESession imported"
    return f"No instrument on this machine ({_import_error}) — rehearsal mode only"


def build_sweep_config(
    *,
    start: float,
    end: float,
    sweep_time: float = 30.0,
    initial_wait: float = 1.0,
    return_to_start: bool = False,
    channel: int = 1,
    pattern: str = "Ramp /\\",
    table: list | None = None,
) -> dict:
    """Assemble the dict LockinSweep expects, for one sweep channel."""
    return {
        "sweepTime": float(sweep_time),
        "initialWaitTime": float(initial_wait),
        "returnToStart": bool(return_to_start),
        "sweepChannels": [
            {
                "Enable?": True,
                "Channel": int(channel),
                "Start": float(start),
                "End": float(end),
                "Pattern": pattern,
                "Table": table if table is not None else [1],
            }
        ],
    }


def wait_for_new_tdms(
    folder: Path, before: set[str], *, timeout: float = 60.0, poll: float = 0.5
) -> Path | None:
    """Wait for a .tdms that was not in ``before`` to appear and stop growing."""
    folder = Path(folder)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        fresh = [p for p in folder.glob("*.tdms") if p.name not in before]
        if fresh:
            newest = max(fresh, key=lambda p: p.stat().st_mtime)
            size = newest.stat().st_size
            time.sleep(poll)
            if newest.stat().st_size == size:   # finished writing
                return newest
        time.sleep(poll)
    return None


def run_sweep(
    *,
    exp_folder: str,
    comments: str,
    config: dict,
    watch_dir: Path | None = None,
    timeout: float = 60.0,
) -> Path | None:
    """Run one lock-in sweep. Returns the TDMS file it produced, if we spot it.

    ``watch_dir`` is where the notebook expects the file to land - normally
    ``<session root>/<exp_folder>``. If it is not given, or nothing new shows up
    before ``timeout``, the sweep has still run; the file just gets picked up on
    the next reload.
    """
    if not is_available():
        raise RuntimeError(f"CESession unavailable — {_import_error}")

    before: set[str] = set()
    if watch_dir is not None:
        watch_dir = Path(watch_dir)
        if watch_dir.is_dir():
            before = {p.name for p in watch_dir.glob("*.tdms")}

    with CESession() as exp:
        exp.Transport.LockinSweep(exp_folder, comments, config, run_continuous=False)

    if watch_dir is None or not watch_dir.is_dir():
        return None
    return wait_for_new_tdms(watch_dir, before, timeout=timeout)
