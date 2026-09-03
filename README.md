# Chirality in KTaO₃

Sweep a chiral structure, sweep its mirror image, and see whether the bias
asymmetry flips sign. Lithography happens on the writing PC; this notebook runs
the IV sweeps and the analysis.

```bash
.\demo.ps1
```

First run downloads dependencies via `uv` (~30 s). **Do that before the demo.**

---

## The flow

1. **§1 Setup** — point at the session folder. Each structure is a subfolder,
   named exactly like the `exp_folder` you pass to `LockinSweep`. Pick 4T or 2T.
2. **§2 Measure** — choose a structure, set the sweep, hit **Run IV sweep**.
   It calls `Transport.LockinSweep` and waits for the TDMS to land.
3. **§3–4** — the analysis picks the file up and updates itself.
4. Switch to the other structure, sweep again. The verdict fills in.

Sweeps run from FLEX directly work too — hit **Reload**.

The money shot is the asymmetry plot: the dashed blue trace is −A for structure
B. If the two really are enantiomers, it lands on the red curve — a claim the
audience checks with their own eyes.

---

## Instrument

Everything instrument-specific is in [`instrument.py`](instrument.py), which
mirrors [`examples/Lockin_sweep.py`](examples/Lockin_sweep.py):

```python
with CESession() as exp:
    exp.Transport.LockinSweep(exp_folder, comments, sweep_config, run_continuous=False)
```

`flex` is imported lazily, so the notebook opens on a machine that cannot reach
the instrument — the status line at the top says which state you are in. Flip
**rehearsal** in §2 to write synthetic chiral sweeps instead, for practising or
for when the hardware is down.

## Data

One sweep, one `.tdms`. Channels default to the wiring in the example script:

| role | channel | |
|---|---|---|
| drive | `AO1` | 2T bias |
| current | `AI4` | |
| V+ / V− | `AI3` / `AI5` | 4T bias = AI3 − AI5 |

Change them in `DEFAULT_CHANNELS` in [`chiral_kto/ivio.py`](chiral_kto/ivio.py)
if the wiring moves — nothing else hard-codes them. If `AI4` is not already in
amps, set **Current gain** in §1 to the preamp sensitivity. A file that will not
read is listed under *Unreadable files* rather than taking the notebook down.

---

## What it computes

Each folder is a structure; every file in it is a repeat sweep.

1. **Branch splitting** — a round-trip ramp is cut into up and down branches.
   Average them (default) to cancel hysteresis, or look at one.
2. **Common grid** — all sweeps interpolated onto one symmetric bias grid
   spanning the range they all actually measured.
3. **Asymmetry** `A(V) = (|I(+V)| − |I(−V)|) / (|I(+V)| + |I(−V)|)` — bounded in
   ±1, zero for any junction odd in bias, flips sign between enantiomers.
   Repeats give the ±1 SD band and the error bar.
4. **Chiral contrast** `⟨A_A − A_B⟩` over the evaluation window, with a standard
   error from the repeats and a *t*-statistic.
5. **Mirror score** `1 − ‖A_A + A_B‖ / (‖A_A‖ + ‖A_B‖)`, in [0, 1]. 1 = B is
   exactly −A; 0 = identical structures, or one with no response. Deliberately
   *not* a correlation: where A(V) has saturated both curves are near-constant
   and a centred correlation sees only noise. This form also penalises a
   magnitude mismatch — a partner with a quarter of the asymmetry scores ≈0.3.
6. **Noise floor** — the achiral control's asymmetry. The contrast must clear
   3× this *and* reach t > 3 before the verdict calls it significant.

Also plotted: mean IV with ±1 SD, log |I|, and dI/dV. **Export** writes four
CSVs into `<session folder>/exports/<timestamp>/`.

---

## Trust, but verify

```bash
.\demo.ps1 test
```

18 checks: a synthetic enantiomer pair with a known `β·tanh(V/Vs)` asymmetry,
round-tripped through real TDMS, plus 2T/4T and gain checks and two null
controls (identical structures must score 0; a weak partner must not pass as a
clean enantiomer). Run it if you touch `chiral_kto/analysis.py`.

---

## Layout

```
chirality_demo.py     the notebook — UI only
instrument.py         CESession / LockinSweep wrapper
selftest.py           18 checks, no instrument needed
chiral_kto/
  ivio.py             read the TDMS files
  analysis.py         branches, asymmetry, dI/dV, mirror test
  simulate.py         synthetic chiral sweeps, written as TDMS
examples/             the original script this was built from
demo.ps1              launcher — no arg = edit, `present` = app mode, `test` = checks
```

## If something breaks mid-demo

- **A cell goes red** — everything below stops, nothing above is lost. Fix it
  and it re-runs on its own.
- **The sweep call throws** — run it from FLEX and hit *Reload*. The analysis
  only ever needs files on disk.
- **Instrument unreachable** — switch on **rehearsal** and keep talking. The
  analysis on screen is the real analysis.
- **Curves look upside down** — swap which folder is A and which is B, or check
  the sign on the current channel.
