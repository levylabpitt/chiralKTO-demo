# Chirality in KTaO₃

Drive a wire left → right, drive it right → left, see whether the bias
asymmetry flips sign.

```bash
.\demo.ps1
```

First run downloads deps via `uv` (~30s). Do that before the demo.

---

## The flow

1. **Setup** — session folder, wire label, current left/right (AO channels),
   voltage left/right (AI channels). Folder = label. Moving to a new wire is
   just retyping the label.
2. **Measure** — pick a direction, hit **Run IV sweep**. One sweep per click.
3. **Sweeps** — table of what's on disk, pick which sweeps to plot, and
   which ramp segment (up / down / both — for a round-trip sweep).
4. **IV curves** — both directions, overlaid, one plot.

No analysis beyond that right now (asymmetry, mirror score, dI/dV) — it's
still in `chiral_kto/analysis.py` if we want it back later.

---

## Instrument

[`instrument.py`](instrument.py) wraps `CESession`/`LockinSweep`, same as
[`examples/Lockin_sweep.py`](examples/Lockin_sweep.py). `flex` is imported
lazily — the notebook still opens without it, status line up top says which
state you're in.

Whichever side isn't driving gets zeroed twice over: a 0V entry in
`sweepChannels`, plus a direct `Lockin().setAO_DC(channel, 0)` call right
before the sweep starts. Not left floating, and not left at whatever the
last sweep set it to.

## Data

FLEX creates `exp_folder` as a direct child of the session folder and writes
the `.tdms` inside it — so the notebook watches
`<session>/<label>_forward/` and `<session>/<label>_reverse/`, not a nested
`<label>/forward/`. Session folder must be the same folder FLEX itself is
pointed at.

No separate current-sense field — current is read from whichever side isn't
driving (right's AI channel going left→right, left's going right→left), same
numbers as Current left/right in Setup. Bias (V) is likewise referenced to
whichever side *is* driving, not a fixed left/right convention — driving from
the right makes the right electrode the high side, so without this an
ordinary resistance comes out with an inverted slope in that direction. Both
live in `chiral_kto/ivio.py::load_wire_folder`, covered by `selftest.py`.

Current gain and 2T/4T are global. Bad files show up under *Unreadable*,
nothing else stops.

---

## Trust, but verify

```bash
.\demo.ps1 test
```

20 checks against synthetic data with a known asymmetry — round-tripped
through TDMS, forward/reverse mirroring, an achiral wire near zero, a weak
partner scoring partial not perfect, and a hand-built ordinary resistor that
must slope the same way driven from either end. Tests `chiral_kto/analysis.py`
too, which the notebook doesn't currently use. Run after touching either.

---

## Layout

```
chirality_demo.py     notebook — UI only
instrument.py          CESession / LockinSweep wrapper
selftest.py             19 checks, no instrument needed
chiral_kto/
  ivio.py               read TDMS
  analysis.py           branches, asymmetry, dI/dV, mirror test — not wired in yet
  simulate.py           synthetic chiral sweeps as TDMS, for selftest.py
examples/               original script this was built from
demo.ps1               launcher: no arg = edit, `present`, `test`
```

## If something breaks mid-demo

- Cell goes red — everything below stops, rest is fine. Fix, it re-runs.
- Sweep throws — run from FLEX directly, hit **Reload**.
- Curves look off — check which current lead is left vs right.
