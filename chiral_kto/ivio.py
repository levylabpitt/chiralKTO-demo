"""Read the TDMS files the transport server writes.

One lock-in sweep -> one .tdms file, laid out the way examples/Lockin_sweep.py
reads it: a single group whose channels are the raw AO/AI traces.

    AO1  drive output          AI4  measured current
    AI3  V+                    AI5  V-

which gives two views of the same sweep:

    2T   x = AO1,        y = AI4      includes the contacts
    4T   x = AI3 - AI5,  y = AI4      the sample alone
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import numpy as np
from nptdms import TdmsFile

#: channel roles -> TDMS channel names. Override in the notebook if the wiring
#: changes; nothing else in the codebase hard-codes these.
DEFAULT_CHANNELS: dict[str, str] = {
    "drive": "AO1",
    "current": "AI4",
    "v_plus": "AI3",
    "v_minus": "AI5",
}


@dataclass
class IVSweep:
    """One sweep, reduced to volts and amps under a chosen 2T/4T view."""

    v: np.ndarray
    i: np.ndarray
    path: Path
    mode: str = "4T"
    group: str = ""
    mtime: float = 0.0

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def timestamp(self) -> datetime:
        return datetime.fromtimestamp(self.mtime)

    def summary(self) -> dict[str, object]:
        return {
            "file": self.name,
            "mode": self.mode,
            "points": int(self.v.size),
            "V min": float(np.nanmin(self.v)),
            "V max": float(np.nanmax(self.v)),
            "|I| max (nA)": float(np.nanmax(np.abs(self.i))) / 1e-9,
            "acquired": self.timestamp.strftime("%H:%M:%S"),
        }


def load_tdms(
    path: str | Path,
    *,
    mode: str = "4T",
    channels: dict[str, str] | None = None,
    current_gain: float = 1.0,
    group: str | None = None,
) -> IVSweep:
    """Load one TDMS sweep.

    ``current_gain`` scales the current channel into amps (A per raw unit) -
    set it to the preamp sensitivity if the channel is not already in amps.
    """
    path = Path(path)
    names = {**DEFAULT_CHANNELS, **(channels or {})}

    tdms = TdmsFile.read(path)
    groups = tdms.groups()
    if not groups:
        raise ValueError(f"{path.name}: file has no groups")
    grp = tdms[group] if group else groups[0]
    available = [c.name for c in grp.channels()]

    def pull(role: str) -> np.ndarray:
        want = names[role]
        if want not in available:
            raise ValueError(
                f"{path.name}: no channel {want!r} for {role} "
                f"(group {grp.name!r} has {available})"
            )
        return np.asarray(grp[want].data, dtype=float)

    current = pull("current") * float(current_gain)
    voltage = pull("drive") if mode == "2T" else pull("v_plus") - pull("v_minus")

    n = min(voltage.size, current.size)
    voltage, current = voltage[:n], current[:n]
    good = np.isfinite(voltage) & np.isfinite(current)

    return IVSweep(
        v=voltage[good],
        i=current[good],
        path=path,
        mode=mode,
        group=grp.name,
        mtime=path.stat().st_mtime,
    )


def scan_folder(folder: str | Path, *, newest_first: bool = False) -> list[Path]:
    """Every .tdms in a folder, oldest first by default."""
    folder = Path(folder).expanduser()
    if not folder.is_dir():
        return []
    files = [p for p in folder.glob("*.tdms") if p.is_file()]
    files.sort(key=lambda p: p.stat().st_mtime, reverse=newest_first)
    return files


def load_folder(
    folder: str | Path,
    *,
    mode: str = "4T",
    channels: dict[str, str] | None = None,
    current_gain: float = 1.0,
    limit: int | None = None,
) -> tuple[list[IVSweep], list[str]]:
    """Load a folder of sweeps. Returns (sweeps, problems).

    A file that will not read comes back as a message rather than an exception,
    so one bad acquisition cannot take the notebook down mid-demo.
    """
    sweeps: list[IVSweep] = []
    problems: list[str] = []
    paths = scan_folder(folder)
    if limit:
        paths = paths[-limit:]
    for p in paths:
        try:
            sweeps.append(
                load_tdms(p, mode=mode, channels=channels, current_gain=current_gain)
            )
        except Exception as exc:  # noqa: BLE001 - surfaced in the UI
            problems.append(f"{p.name}: {exc}")
    return sweeps, problems


def wire_channels(
    direction: str, *, cur_left: int, cur_right: int, volt_left: str, volt_right: str
) -> dict[str, str]:
    """Channel map for one drive direction of a two-electrode wire.

    Current is sensed on whichever side isn't driving. Bias is referenced to
    whichever side *is* driving (v_plus = the driving side) rather than a
    fixed left/right convention - otherwise an ordinary, non-chiral resistance
    comes out with opposite-sign slope in the two directions, since driving
    from the right makes the right electrode the high side, not the left.
    """
    if direction == "forward":
        drive, sense, v_plus, v_minus = cur_left, cur_right, volt_left, volt_right
    else:
        drive, sense, v_plus, v_minus = cur_right, cur_left, volt_right, volt_left
    return {"drive": f"AO{drive}", "current": f"AI{sense}", "v_plus": v_plus, "v_minus": v_minus}


def load_wire_folder(
    folder: str | Path,
    direction: str,
    *,
    cur_left: int,
    cur_right: int,
    volt_left: str,
    volt_right: str,
    mode: str = "4T",
    current_gain: float = 1.0,
) -> tuple[list[IVSweep], list[str]]:
    """load_folder(), with the direction-dependent channel wiring worked out."""
    return load_folder(
        folder,
        mode=mode,
        channels=wire_channels(
            direction, cur_left=cur_left, cur_right=cur_right, volt_left=volt_left, volt_right=volt_right
        ),
        current_gain=current_gain,
    )
