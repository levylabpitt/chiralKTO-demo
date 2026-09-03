"""Synthetic chiral sweeps, written as real TDMS files.

Same format the transport server produces, so the loader and the analysis take
exactly the same path whether the data came from the instrument or from here.
Two uses: rehearse before the demo, and keep going if the hardware is down.

One wire, driven from each end in turn (forward / reverse), is the whole
experiment now. The model is a tunnelling backbone times a direction-dependent
bias asymmetry, so the analysis has a known right answer:

    I(V) = I0 * sinh(V/Vt) * (1 + h*beta*tanh(V/Vs))  ->  A(V) = h*beta*tanh(V/Vs)

h = +chirality driving forward, -chirality driving reverse. chirality = 0 makes
an achiral wire - no contrast either way.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from nptdms import ChannelObject, TdmsWriter

from .ivio import DEFAULT_CHANNELS


def simulate_sweep(
    handedness: float = +1.0,
    *,
    v_max: float = 0.1,
    n_points: int = 201,
    i0: float = 2e-8,
    v_t: float = 0.055,
    beta: float = 0.22,
    v_s: float = 0.045,
    contact_asym: float = 0.015,
    contact_drop: float = 0.35,
    noise: float = 0.02,
    round_trip: bool = True,
    seed: int | None = None,
) -> dict[str, np.ndarray]:
    """One sweep as raw channels: drive, current, v_plus, v_minus.

    ``contact_drop`` is the fraction of the drive that falls across the contacts,
    so the 2T and 4T views differ the way they do on a real sample.
    """
    h = float(handedness)
    rng = np.random.default_rng(seed)

    ramp = np.linspace(-v_max, v_max, n_points)
    drive = np.concatenate([ramp, ramp[::-1][1:]]) if round_trip else ramp

    v_sample = drive * (1.0 - contact_drop)
    current = (
        i0
        * np.sinh(v_sample / v_t)
        * (1.0 + h * beta * np.tanh(v_sample / v_s))
        * (1.0 + contact_asym * np.tanh(v_sample / v_s))
    )
    current = current + rng.normal(0.0, noise * np.abs(current) + 0.02 * i0)

    v_noise = rng.normal(0.0, 1e-4 * v_max, size=v_sample.size)
    return {
        "drive": drive,
        "current": current,
        "v_plus": 0.5 * v_sample + v_noise,
        "v_minus": -0.5 * v_sample + v_noise,
    }


def write_tdms(
    path: str | Path,
    raw: dict[str, np.ndarray],
    *,
    channel_names: dict[str, str] | None = None,
    group: str | None = None,
) -> Path:
    """Write simulated channels out under real TDMS channel names."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    names = {**DEFAULT_CHANNELS, **(channel_names or {})}
    group = group or f"Data.{path.stem.split('.')[-1]}"
    with TdmsWriter(path) as writer:
        writer.write_segment(
            [
                ChannelObject(group, names[role], np.asarray(data, float))
                for role, data in raw.items()
            ]
        )
    return path


def simulate_into(
    folder: str | Path,
    handedness: float,
    *,
    channel_names: dict[str, str] | None = None,
    index: int | None = None,
    stem: str = "SIM",
    **kwargs,
) -> Path:
    """Write one simulated sweep into ``folder``, numbered like the real thing."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if index is None:
        index = len(list(folder.glob("*.tdms")))
    raw = simulate_sweep(handedness, **kwargs)
    return write_tdms(
        folder / f"{stem}.{index:06d}.tdms", raw, channel_names=channel_names
    )


def simulate_wire_sweep(
    folder: str | Path,
    direction: str,
    chirality: float = 1.0,
    **kwargs,
) -> Path:
    """One sweep for one wire, driven ``forward`` or ``reverse``.

    Forward and reverse get opposite sign - a genuinely chiral wire (chirality
    != 0) shows mirrored asymmetry between the two; chirality=0 is a wire with
    no chiral response either way.
    """
    sign = 1.0 if direction == "forward" else -1.0
    return simulate_into(folder, sign * chirality, **kwargs)


def write_demo_dataset(
    root: str | Path,
    *,
    n_wires: int = 2,
    n_repeats: int = 4,
    chirality: tuple[float, ...] | None = None,
    seed: int = 7,
    channel_names: dict[str, str] | None = None,
    **kwargs,
) -> dict[str, dict[str, Path]]:
    """Populate <root>/wireN/forward and /reverse with repeat sweeps."""
    root = Path(root)
    chir = chirality or tuple(1.0 if i == 0 else -1.0 for i in range(n_wires))
    out: dict[str, dict[str, Path]] = {}
    for wi in range(n_wires):
        label = f"wire{wi + 1}"
        wire_out = {}
        for direction in ("forward", "reverse"):
            folder = root / label / direction
            for k in range(n_repeats):
                simulate_wire_sweep(
                    folder,
                    direction,
                    chir[wi],
                    index=k,
                    stem=f"{label}_{direction}",
                    seed=seed + 1000 * wi + (500 if direction == "reverse" else 0) + k,
                    channel_names=channel_names,
                    **kwargs,
                )
            wire_out[direction] = folder
        out[label] = wire_out
    return out
