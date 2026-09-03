# Chirality in KTaO₃

Drive a wire forward, drive it reverse, see whether the bias asymmetry flips
sign. One wire, two directions. Multiple wires supported.

```bash
.\demo.ps1
```

First run downloads deps via `uv` (~30s). Do that before the demo.

---

## The flow

1. **Setup** — session folder, number of wires. Each wire: name, folder,
   electrode A, electrode B (the two AO channels at its ends).
2. **Measure** — pick a wire and a direction. Forward drives electrode A,
   holds B at 0V; reverse is the opposite. Hit **Run IV sweep**.
3. **Sweeps / Analysis** — updates on its own. Switch direction, sweep again.
4. **All wires** — one row per wire, so you can compare across them.

Money shot is the asymmetry plot: dashed = −A driving reverse. A chiral wire
flips sign; an achiral one sits near zero either way.

---

## Instrument

[`instrument.py`](instrument.py) wraps `CESession`/`LockinSweep`, same as
[`examples/Lockin_sweep.py`](examples/Lockin_sweep.py). `flex` is imported
lazily — the notebook still opens without it, status line up top says which
state you're in. **Rehearsal** in Measure writes synthetic data instead.

Each direction pins the *other* electrode at 0V explicitly (a second entry in
`sweepChannels`), not left floating.

## Data

One sweep, one `.tdms`, one file per repeat, in `<wire>/forward/` or
`<wire>/reverse/`. Current/V+/V- channel names are set once in Setup, shared
across wires — change them if the wiring moves. Current gain scales into amps
if the current channel isn't already in amps. Bad files show up under
*Unreadable*, nothing else stops.

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
partner scoring partial not perfect. Run after touching `analysis.py`.

---

## Layout

```
chirality_demo.py     notebook — UI only
instrument.py          CESession / LockinSweep wrapper
selftest.py             19 checks, no instrument needed
chiral_kto/
  ivio.py               read TDMS
  analysis.py           branches, asymmetry, dI/dV, mirror test
  simulate.py           synthetic chiral sweeps as TDMS
examples/               original script this was built from
demo.ps1               launcher: no arg = edit, `present`, `test`
```

## If something breaks mid-demo

- Cell goes red — everything below stops, rest is fine. Fix, it re-runs.
- Sweep throws — run from FLEX directly, hit **Reload**.
- Instrument unreachable — flip **rehearsal**, keep talking.
- Curves look off — check which electrode is A vs B for that wire.
