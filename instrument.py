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

try:
    from flex.inst.levylab.Lockin import Lockin
except Exception:  # noqa: BLE001 - absence is a normal state here
    Lockin = None


def is_available() -> bool:
    """True when a real sweep can be run from this machine."""
    return CESession is not None


def zero_channel(channel: int) -> None:
    """Force one AO channel to 0V directly, ahead of a sweep."""
    if Lockin is None:
        raise RuntimeError("Lockin driver unavailable")
    Lockin().setAO_DC(channel=int(channel), value=0)


def describe() -> str:
    """One line for the notebook's status bar."""
    if is_available():
        return "Transport server reachable — CESession imported"
    return f"No instrument on this machine ({_import_error}) — rehearsal mode only"


def build_sweep_config(
    *,
    start: float,
    end: float,
    drive_channel: int,
    hold_channel: int | None = None,
    sweep_time: float = 30.0,
    initial_wait: float = 1.0,
    return_to_start: bool = False,
    pattern: str = "Ramp /\\",
    table: list | None = None,
) -> dict:
    """Sweep config for one channel; optionally pin a second one at 0V.

    ``hold_channel`` is the electrode on the other end of the wire - explicitly
    driven to 0 rather than left floating, so swapping which end sources current
    (forward vs reverse) is a real electrode swap, not just a sign flip.
    """
    table = table if table is not None else [1]
    channels = [
        {
            "Enable?": True,
            "Channel": int(drive_channel),
            "Start": float(start),
            "End": float(end),
            "Pattern": pattern,
            "Table": table,
        }
    ]
    if hold_channel is not None:
        channels.append(
            {
                "Enable?": True,
                "Channel": int(hold_channel),
                "Start": 0.0,
                "End": 0.0,
                "Pattern": pattern,
                "Table": table,
            }
        )
    return {
        "sweepTime": float(sweep_time),
        "initialWaitTime": float(initial_wait),
        "returnToStart": bool(return_to_start),
        "sweepChannels": channels,
    }


def wait_for_new_tdms(
    folder: Path, before: set[str], *, timeout: float = 8.0, poll: float = 0.5
) -> Path | None:
    """Wait for a .tdms that was not in ``before`` to appear and stop growing.

    LockinSweep already blocks until the sweep is done, so this is only for the
    file to finish flushing to disk - a few seconds, not the sweep time.
    """
    folder = Path(folder)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        fresh = [p for p in folder.rglob("*.tdms") if p.name not in before]
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
    hold_channel: int | None = None,
    watch_dir: Path | None = None,
    timeout: float = 8.0,
) -> Path | None:
    """Run one lock-in sweep. Returns the TDMS file it produced, if we spot it.

    ``hold_channel`` is zeroed directly through the Lockin driver before the
    sweep starts - belt and suspenders on top of the 0V entry already in
    ``config``, so the passive electrode never carries a leftover voltage from
    a previous sweep.

    The sweep has already happened by the time this returns, regardless of
    whether the file gets found - a miss here just means hit Reload.
    """
    if not is_available():
        raise RuntimeError(f"CESession unavailable — {_import_error}")

    if hold_channel is not None:
        zero_channel(hold_channel)

    before: set[str] = set()
    if watch_dir is not None:
        watch_dir = Path(watch_dir)
        if watch_dir.is_dir():
            before = {p.name for p in watch_dir.rglob("*.tdms")}

    with CESession() as exp:
        exp.Transport.LockinSweep(exp_folder, comments, config, run_continuous=False)

    if watch_dir is None or not watch_dir.is_dir():
        return None
    return wait_for_new_tdms(watch_dir, before, timeout=timeout)
