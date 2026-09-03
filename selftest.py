# /// script
# requires-python = ">=3.11"
# dependencies = ["numpy", "pandas", "scipy", "npTDMS"]
# ///
"""Prove the analysis pipeline before the demo, without touching the instrument.

Generates a synthetic wire with a known asymmetry, driven forward and reverse,
writes it out as real TDMS files, reads them back through the same loader the
notebook uses, and checks the recovered numbers match the model.

    .\\demo.ps1 test
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import numpy as np
from nptdms import ChannelObject, TdmsWriter

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
        wires = simulate.write_demo_dataset(
            root, n_wires=2, n_repeats=4, beta=BETA, v_s=V_S, v_max=V_MAX,
            contact_drop=CONTACT_DROP,
        )

        # --- round trip through TDMS --------------------------------------
        sweeps = {}
        for wire, dirs in wires.items():
            for direction, folder in dirs.items():
                loaded, problems = ivio.load_folder(folder, mode="4T")
                check(
                    f"load {wire} {direction}",
                    len(loaded) == 4 and not problems,
                    f"{len(loaded)} files",
                )
                sweeps[(wire, direction)] = loaded

        one = sweeps[("wire1", "forward")][0]
        check(
            "4T reads AI3 − AI5 across the sample",
            np.isclose(one.v.max(), V_SAMPLE_MAX, rtol=0.02),
            f"Vmax={one.v.max():.4f} V, expected {V_SAMPLE_MAX:.4f} V",
        )

        two_t, _ = ivio.load_folder(wires["wire1"]["forward"], mode="2T")
        check(
            "2T reads the AO drive, so it spans more bias",
            np.isclose(two_t[0].v.max(), V_MAX, rtol=0.02),
            f"Vmax={two_t[0].v.max():.4f} V, expected {V_MAX:.4f} V",
        )

        gained, _ = ivio.load_folder(wires["wire1"]["forward"], mode="4T", current_gain=1e-3)
        check(
            "current gain scales the current channel",
            np.isclose(np.abs(gained[0].i).max(), 1e-3 * np.abs(one.i).max(), rtol=1e-6),
            f"{np.abs(gained[0].i).max():.3e} A",
        )

        # --- branch splitting --------------------------------------------
        branches = analysis.split_branches(one.v, one.i)
        check("round-trip sweep splits into 2 ramps", len(branches) == 2, f"{len(branches)}")

        # --- per-direction reduction ---------------------------------------
        pool = [s for group in sweeps.values() for s in group]
        grid = analysis.common_grid(pool, n_points=401)
        res = {key: analysis.analyse_slot(f"{key[0]} {key[1]}", sweeps[key], grid=grid) for key in sweeps}

        window = (0.5 * V_SAMPLE_MAX, V_SAMPLE_MAX)
        expected = BETA * float(np.mean(np.tanh(np.linspace(*window, 400) / V_S)))

        fwd_mean = res[("wire1", "forward")].a_at(*window)[0]
        rev_mean = res[("wire1", "reverse")].a_at(*window)[0]

        check(
            "forward asymmetry recovers +beta*tanh(V/Vs)",
            abs(fwd_mean - expected) < 0.03,
            f"got {fwd_mean:+.3f}, expected ~{expected:+.3f}",
        )
        check(
            "reverse asymmetry is the mirror image",
            abs(rev_mean + expected) < 0.03,
            f"got {rev_mean:+.3f}, expected ~{-expected:+.3f}",
        )

        # --- an achiral wire (chirality 0) sits near zero either way -------
        control = simulate.write_demo_dataset(
            root / "control", n_wires=1, n_repeats=4, chirality=(0.0,), v_s=V_S,
            v_max=V_MAX, contact_drop=CONTACT_DROP, seed=50,
        )
        ctrl_fwd = analysis.analyse_slot(
            "ctrl fwd", ivio.load_folder(control["wire1"]["forward"], mode="4T")[0], grid=grid
        )
        ctrl_mean = ctrl_fwd.a_at(*window)[0]
        check("achiral wire sits near zero", abs(ctrl_mean) < 0.03, f"got {ctrl_mean:+.3f}")

        # --- the verdict ---------------------------------------------------
        mt = analysis.mirror_test(res[("wire1", "forward")], res[("wire1", "reverse")], v_window=window)
        check("mirror score near 1", mt.mirror_score > 0.85, f"{mt.mirror_score:.3f}")
        check(
            "contrast is ~2x the single-direction asymmetry",
            abs(mt.contrast - 2 * expected) < 0.06,
            f"{mt.contrast:+.3f}",
        )
        check("result is flagged significant", mt.significant, f"t = {mt.t_stat:.1f}")
        check("verdict calls it chiral", "chiral wire" in mt.verdict(), mt.verdict())

        # --- null: driving the same direction twice ------------------------
        null = analysis.mirror_test(res[("wire1", "forward")], res[("wire1", "forward")], v_window=window)
        check("same direction shows no contrast", not null.significant, f"contrast {null.contrast:+.4f}")
        check("same direction scores ~0 on the mirror test", null.mirror_score < 0.15, f"{null.mirror_score:.3f}")

        # --- a weak partner must not pass as a clean mirror -----------------
        half = simulate.write_demo_dataset(
            root / "half", n_wires=1, n_repeats=4, chirality=(0.25,), v_s=V_S,
            v_max=V_MAX, contact_drop=CONTACT_DROP, seed=99,
        )
        weak = analysis.analyse_slot(
            "weak", ivio.load_folder(half["wire1"]["reverse"], mode="4T")[0], grid=grid
        )
        partial = analysis.mirror_test(res[("wire1", "forward")], weak, v_window=window)
        check(
            "a partner with 1/4 the asymmetry scores as partial, not textbook",
            0.2 < partial.mirror_score < 0.7,
            f"{partial.mirror_score:.3f}",
        )

        # --- conductance sanity --------------------------------------------
        g0 = res[("wire1", "forward")].g0
        check("zero-bias conductance is positive and finite", np.isfinite(g0) and g0 > 0,
              f"{g0 / 1e-9:.3f} nS")

        # --- an ordinary resistor must not look chiral just from which end
        # drives it. AI3/AI5 are FIXED physical probes (left/right), unaware
        # of software "directions" - only load_wire_folder should know to
        # reference bias to the driving side. Build the raw files by hand so
        # the idealised simulator (which has no left/right) can't hide the bug.
        R = 1e6
        ramp = np.linspace(-0.05, 0.05, 51)

        def write_raw(path, drive_ch, sense_ch, v_left_sign):
            path.parent.mkdir(parents=True, exist_ok=True)
            group = "Data.000000"
            with TdmsWriter(path) as w:
                w.write_segment(
                    [
                        ChannelObject(group, f"AO{drive_ch}", ramp),
                        ChannelObject(group, "AI3", v_left_sign * 0.5 * ramp),
                        ChannelObject(group, "AI5", -v_left_sign * 0.5 * ramp),
                        ChannelObject(group, f"AI{sense_ch}", ramp / R),
                    ]
                )

        raw_root = root / "raw_resistor"
        write_raw(raw_root / "r_forward" / "s.000000.tdms", 1, 2, v_left_sign=+1)
        write_raw(raw_root / "r_reverse" / "s.000000.tdms", 2, 1, v_left_sign=-1)

        r_fwd, _ = ivio.load_wire_folder(
            raw_root / "r_forward", "forward", cur_left=1, cur_right=2, volt_left="AI3", volt_right="AI5"
        )
        r_rev, _ = ivio.load_wire_folder(
            raw_root / "r_reverse", "reverse", cur_left=1, cur_right=2, volt_left="AI3", volt_right="AI5"
        )
        fwd_slope = float(np.polyfit(r_fwd[0].v, r_fwd[0].i, 1)[0])
        rev_slope = float(np.polyfit(r_rev[0].v, r_rev[0].i, 1)[0])
        check(
            "an ordinary resistor slopes the same way in both directions",
            fwd_slope > 0 and rev_slope > 0,
            f"forward {fwd_slope / 1e-9:.3f} nS, reverse {rev_slope / 1e-9:.3f} nS",
        )

    print()
    if failures:
        print(f"{len(failures)} check(s) failed: " + ", ".join(failures))
        return 1
    print("all checks passed — the notebook's analysis is trustworthy")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
