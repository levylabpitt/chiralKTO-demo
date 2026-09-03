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
3. **Sweeps / Analysis** — updates on its own.

Money shot is the asymmetry plot: dashed = −A driving right → left. A chiral
wire flips sign; an achiral one sits near zero either way.

---

## Instrument

[`instrument.py`](instrument.py) wraps `CESession`/`LockinSweep`, same as
[`examples/Lockin_sweep.py`](examples/Lockin_sweep.py). `flex` is imported
lazily — the notebook still opens without it, status line up top says which
state you're in.

Whichever side isn't driving gets pinned at 0V explicitly (a second entry in
`sweepChannels`), not left floating.

## Data

One sweep, one `.tdms`, in `<wire>/forward/` (left→right) or `<wire>/reverse/`
(right→left). No separate current-sense field — current is read from whichever
side isn't driving (right's AI channel going left→right, left's going
right→left), same numbers as Current left/right in Setup. Current gain and
2T/4T are global. Bad files show up under *Unreadable*, nothing else stops.

---

## What it computes

1. **Branches** — round-trip ramp split into up/down, averaged by default.
2. **Common grid** — every sweep interpolated onto one bias axis.
3. **Asymmetry** `A(V) = (|I(+V)| − |I(−V)|) / (|I(+V)| + |I(−V)|)`.
4. **Contrast** `⟨A_fwd − A_rev⟩` over the eval window, with SEM and t-stat.
5. **Mirror score** `1 − ‖A_fwd + A_rev‖ / (‖A_fwd‖ + ‖A_rev‖)`. 1 = reverse
   is exactly −forward. Not a correlation — that reads as noise once A(V)
   saturates. Penalizes magnitude mismatch too.

Also: mean IV ±1 SD, log |I|, dI/dV. Export writes CSVs to
`<session>/exports/<wire>_<timestamp>/`.

---

## Trust, but verify

```bash
.\demo.ps1 test
```

19 checks against synthetic data with a known asymmetry — round-tripped
through TDMS, forward/reverse mirroring, an achiral wire near zero, a weak
partner scoring partial not perfect. Uses `chiral_kto/simulate.py`, which
isn't wired into the notebook itself. Run after touching `analysis.py`.

---

## Layout

```
chirality_demo.py     notebook — UI only
instrument.py          CESession / LockinSweep wrapper
selftest.py             19 checks, no instrument needed
chiral_kto/
  ivio.py               read TDMS
  analysis.py           branches, asymmetry, dI/dV, mirror test
  simulate.py           synthetic chiral sweeps as TDMS, for selftest.py
examples/               original script this was built from
demo.ps1               launcher: no arg = edit, `present`, `test`
```

## If something breaks mid-demo

- Cell goes red — everything below stops, rest is fine. Fix, it re-runs.
- Sweep throws — run from FLEX directly, hit **Reload**.
- Curves look off — check which current lead is left vs right.
