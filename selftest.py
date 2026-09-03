# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pandas", "scipy", "npTDMS"]
# ///
"""Prove the analysis pipeline before the demo, without touching the instrument.

Generates a synthetic enantiomer pair with a known asymmetry, writes it out as
real TDMS files, reads them back through the same loader the notebook uses, and
checks that the recovered numbers match the model.

    .\\demo.ps1 test
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

from chiral_kto import analysis, ivio, simulate  # noqa: E402

BETA = 0.22
V_S = 0.045
V_MAX = 0.1
CONTACT_DROP = 0.35
#: 4T sees the sample voltage: the drive minus what the contacts eat
V_SAMPLE_MAX = V_MAX * (1 - CONTACT_DROP)
PASS, FAIL = "  ok  ", " FAIL "
failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    print(f"[{PASS if condition else FAIL}] {name}" + (f"  — {detail}" if detail else ""))
    if not condition:
        failures.append(name)


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        folders = simulate.write_demo_dataset(
            root,
            n_repeats=4,
            beta=BETA,
            v_s=V_S,
            v_max=V_MAX,
            contact_drop=CONTACT_DROP,
        )

        # --- round trip through TDMS --------------------------------------
        sweeps = {}
        for key, folder in folders.items():
            loaded, problems = ivio.load_folder(folder, mode="4T")
            check(f"load {key}", len(loaded) == 4 and not problems, f"{len(loaded)} files")
            sweeps[key] = loaded

        one = sweeps["A_CW"][0]
        check(
            "4T reads AI3 − AI5 across the sample",
            np.isclose(one.v.max(), V_SAMPLE_MAX, rtol=0.02),
            f"Vmax={one.v.max():.4f} V, expected {V_SAMPLE_MAX:.4f} V",
        )

        two_t, _ = ivio.load_folder(folders["A_CW"], mode="2T")
        check(
            "2T reads the AO1 drive, so it spans more bias",
            np.isclose(two_t[0].v.max(), V_MAX, rtol=0.02),
            f"Vmax={two_t[0].v.max():.4f} V, expected {V_MAX:.4f} V",
        )

        gained, _ = ivio.load_folder(folders["A_CW"], mode="4T", current_gain=1e-3)
        check(
            "current gain scales the current channel",
            np.isclose(np.abs(gained[0].i).max(), 1e-3 * np.abs(one.i).max(), rtol=1e-6),
            f"{np.abs(gained[0].i).max():.3e} A",
        )

        # --- branch splitting --------------------------------------------
        branches = analysis.split_branches(one.v, one.i)
        check("round-trip sweep splits into 2 ramps", len(branches) == 2, f"{len(branches)}")

        # --- per-slot reduction -------------------------------------------
        pool = [s for group in sweeps.values() for s in group]
        grid = analysis.common_grid(pool, n_points=401)
        res = {
            k: analysis.analyse_slot(k, sweeps[k], grid=grid)
            for k in folders
        }

        window = (0.5 * V_SAMPLE_MAX, V_SAMPLE_MAX)
        expected = BETA * float(np.mean(np.tanh(np.linspace(*window, 400) / V_S)))

        a_mean = res["A_CW"].a_at(*window)[0]
        b_mean = res["B_CCW"].a_at(*window)[0]
        c_mean = res["C_control"].a_at(*window)[0]

        check(
            "CW asymmetry recovers +beta*tanh(V/Vs)",
            abs(a_mean - expected) < 0.03,
            f"got {a_mean:+.3f}, expected ~{expected:+.3f}",
        )
        check(
            "CCW asymmetry is the mirror image",
            abs(b_mean + expected) < 0.03,
            f"got {b_mean:+.3f}, expected ~{-expected:+.3f}",
        )
        check(
            "achiral control sits near zero",
            abs(c_mean) < 0.03,
            f"got {c_mean:+.3f}",
        )

        # --- the verdict ---------------------------------------------------
        mt = analysis.mirror_test(
            res["A_CW"], res["B_CCW"], res["C_control"], v_window=window
        )
        check("mirror score near 1", mt.mirror_score > 0.85, f"{mt.mirror_score:.3f}")
        check(
            "contrast is ~2x the single-structure asymmetry",
            abs(mt.contrast - 2 * expected) < 0.06,
            f"{mt.contrast:+.3f}",
        )
        check("result is flagged significant", mt.significant, f"t = {mt.t_stat:.1f}")
        check(
            "verdict names an enantiomer pair",
            "enantiomer" in mt.verdict(),
            mt.verdict(),
        )

        # --- null control: two copies of the same handedness ---------------
        null = analysis.mirror_test(res["A_CW"], res["A_CW"], res["C_control"], v_window=window)
        check(
            "identical structures show no contrast",
            not null.significant,
            f"contrast {null.contrast:+.4f}",
        )
        check(
            "identical structures score ~0 on the mirror test",
            null.mirror_score < 0.15,
            f"{null.mirror_score:.3f}",
        )

        # --- a weak partner must not pass as a clean enantiomer ------------
        half = simulate.write_demo_dataset(
            root / "half",
            n_repeats=4,
            beta=BETA / 4,
            v_s=V_S,
            v_max=V_MAX,
            contact_drop=CONTACT_DROP,
            seed=99,
        )
        weak = analysis.analyse_slot(
            "weak", ivio.load_folder(half["B_CCW"], mode="4T")[0], grid=grid
        )
        partial = analysis.mirror_test(res["A_CW"], weak, res["C_control"], v_window=window)
        check(
            "a partner with 1/4 the asymmetry scores as partial, not textbook",
            0.2 < partial.mirror_score < 0.7,
            f"{partial.mirror_score:.3f}",
        )

        # --- conductance sanity --------------------------------------------
        g0 = res["A_CW"].g0
        check("zero-bias conductance is positive and finite", np.isfinite(g0) and g0 > 0,
              f"{g0 / 1e-9:.3f} nS")

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: " + ", ".join(failures))
        return 1
    print("all checks passed — the notebook's analysis is trustworthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
