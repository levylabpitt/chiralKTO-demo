"""Synthetic chiral sweeps, written as real TDMS files.

Same format the transport server produces, so the loader and the analysis take
exactly the same path whether the data came from the instrument or from here.
Two uses: rehearse before the demo, and keep going if the hardware is down.

The model is a tunnelling backbone times a handedness-dependent bias asymmetry,
so the analysis has a known right answer:

    I(V) = I0 * sinh(V/Vt) * (1 + h*beta*tanh(V/Vs))  ->  A(V) = h*beta*tanh(V/Vs)

h = +1 / -1 for the two enantiomers, 0 for an achiral control.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from nptdms import ChannelObject, TdmsWriter

from .ivio import DEFAULT_CHANNELS

HANDEDNESS = {"CW": +1.0, "CCW": -1.0, "control": 0.0}


def simulate_sweep(
    handedness: float | str = +1.0,
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
    h = (
        HANDEDNESS.get(handedness, 0.0)
        if isinstance(handedness, str)
        else float(handedness)
    )
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


def write_tdms(path: str | Path, raw: dict[str, np.ndarray], group: str | None = None) -> Path:
    """Write simulated channels out under the real TDMS channel names."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    group = group or f"Data.{path.stem.split('.')[-1]}"
    with TdmsWriter(path) as writer:
        writer.write_segment(
            [
                ChannelObject(group, DEFAULT_CHANNELS[role], np.asarray(data, float))
                for role, data in raw.items()
            ]
        )
    return path


def simulate_into(
    folder: str | Path,
    handedness: float | str,
    *,
    index: int | None = None,
    stem: str = "SIM",
    **kwargs,
) -> Path:
    """Write one simulated sweep into ``folder``, numbered like the real thing."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    if index is None:
        index = len(list(folder.glob("*.tdms")))
    return write_tdms(folder / f"{stem}.{index:06d}.tdms", simulate_sweep(handedness, **kwargs))


def write_demo_dataset(
    root: str | Path,
    *,
    n_repeats: int = 4,
    labels: tuple[str, str, str] = ("A_CW", "B_CCW", "C_control"),
    seed: int = 7,
    **kwargs,
) -> dict[str, Path]:
    """Populate one folder per structure with repeat sweeps."""
    root = Path(root)
    out: dict[str, Path] = {}
    for slot, (label, h) in enumerate(zip(labels, (+1.0, -1.0, 0.0))):
        folder = root / label
        for k in range(n_repeats):
            simulate_into(folder, h, index=k, stem=label, seed=seed + 100 * slot + k, **kwargs)
        out[label] = folder
    return out
