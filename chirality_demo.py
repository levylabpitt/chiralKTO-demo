# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "marimo",
#     "numpy",
#     "pandas",
#     "altair",
#     "scipy",
#     "pyarrow",
#     "npTDMS",
#     "ipython",
# ]
# ///
"""Chirality in KTO: sweep one structure, sweep its mirror image, compare."""

import marimo

app = marimo.App(width="medium", app_title="Chirality in KTO")


@app.cell
def _():
    import sys
    from datetime import datetime
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import numpy as np
    import pandas as pd

    NOTEBOOK_DIR = Path(__file__).resolve().parent
    if str(NOTEBOOK_DIR) not in sys.path:
        sys.path.insert(0, str(NOTEBOOK_DIR))

    import instrument
    from chiral_kto import analysis, ivio, simulate
    from chiral_kto.ivio import DEFAULT_CHANNELS

    SLOTS = ("A", "B", "C")
    COLOURS = {"A": "#d1495b", "B": "#0f7bbf", "C": "#8d99ae"}
    SIGN = {"A": +1.0, "B": -1.0, "C": 0.0}
    return (
        DEFAULT_CHANNELS,
        NOTEBOOK_DIR,
        Path,
        SIGN,
        SLOTS,
        COLOURS,
        alt,
        analysis,
        datetime,
        instrument,
        ivio,
        mo,
        np,
        pd,
        simulate,
    )


@app.cell
def _(instrument, mo):
    mo.hstack(
        [
            mo.md("# Chirality in KTaO₃"),
            mo.md(f"`{instrument.describe()}`"),
        ],
        justify="space-between",
        align="center",
    )
    return


@app.cell
def _(NOTEBOOK_DIR, Path, mo):
    session_dir = mo.ui.text(
        value=str(NOTEBOOK_DIR / "data"), label="Session folder", full_width=True
    )

    def make_browser(start):
        """Directory picker, degrading gracefully if the widget is unavailable."""
        try:
            base = Path(start).expanduser()
            return mo.ui.file_browser(
                initial_path=base if base.is_dir() else Path.cwd(),
                selection_mode="directory",
                multiple=False,
                label="",
            )
        except Exception:
            return None

    return make_browser, session_dir


@app.cell
def _(make_browser, session_dir):
    browse = make_browser(session_dir.value)
    return (browse,)


@app.cell
def _(DEFAULT_CHANNELS, mo):
    a_folder = mo.ui.text("A_CW", label="A · chiral")
    b_folder = mo.ui.text("B_CCW", label="B · mirror image")
    c_folder = mo.ui.text("C_control", label="C · achiral control")
    c_on = mo.ui.switch(True, label="use control")

    signal_mode = mo.ui.radio(
        options=["4T", "2T"], value="4T", inline=True, label="Leads"
    )
    current_gain = mo.ui.number(
        1e-9, 1e9, value=1.0, label="Current gain (A/raw)"
    )

    ch_drive = mo.ui.text(DEFAULT_CHANNELS["drive"], label="drive (2T V)")
    ch_current = mo.ui.text(DEFAULT_CHANNELS["current"], label="current")
    ch_vplus = mo.ui.text(DEFAULT_CHANNELS["v_plus"], label="V+ (4T)")
    ch_vminus = mo.ui.text(DEFAULT_CHANNELS["v_minus"], label="V- (4T)")
    return (
        a_folder,
        b_folder,
        c_folder,
        c_on,
        ch_current,
        ch_drive,
        ch_vminus,
        ch_vplus,
        current_gain,
        signal_mode,
    )


@app.cell
def _(
    Path,
    a_folder,
    b_folder,
    browse,
    c_folder,
    c_on,
    ch_current,
    ch_drive,
    ch_vminus,
    ch_vplus,
    current_gain,
    mo,
    session_dir,
    signal_mode,
):
    def _picked():
        if browse is None or not browse.value:
            return ""
        raw = getattr(browse.value[0], "path", None) or getattr(browse.value[0], "id", "")
        return str(raw() if callable(raw) else raw)

    root_path = Path(_picked() or session_dir.value.strip().strip('"')).expanduser()
    slot_names = {"A": a_folder.value, "B": b_folder.value, "C": c_folder.value}
    slot_dirs = {s: root_path / slot_names[s] for s in ("A", "B", "C")}
    channel_map = {
        "drive": ch_drive.value,
        "current": ch_current.value,
        "v_plus": ch_vplus.value,
        "v_minus": ch_vminus.value,
    }

    def _count(s):
        d = slot_dirs[s]
        n = len(list(d.glob("*.tdms"))) if d.is_dir() else 0
        return f"`{slot_names[s]}` — {n}"

    mo.vstack(
        [
            mo.md("## Setup"),
            session_dir,
            mo.accordion({"Browse…": browse}) if browse is not None else mo.md(""),
            mo.hstack([a_folder, b_folder, c_folder, c_on], justify="start", gap=1, wrap=True),
            mo.md(" · ".join(_count(s) for s in ("A", "B", "C")) + " sweeps"),
            mo.hstack([signal_mode, current_gain], justify="start", gap=2),
            mo.hstack(
                [ch_drive, ch_current, ch_vplus, ch_vminus], justify="start", gap=1, wrap=True
            ),
        ]
    )
    return channel_map, root_path, slot_dirs, slot_names


@app.cell
def _(mo):
    active = mo.ui.dropdown(options=["A", "B", "C"], value="A", label="**Sweep which structure**")

    v_start = mo.ui.number(-10.0, 10.0, 0.001, value=-0.1, label="Start (V)")
    v_end = mo.ui.number(-10.0, 10.0, 0.001, value=0.1, label="End (V)")
    sweep_time = mo.ui.number(1.0, 600.0, 1.0, value=30.0, label="Sweep time (s)")
    initial_wait = mo.ui.number(0.0, 60.0, 0.5, value=1.0, label="Initial wait (s)")
    sweep_channel = mo.ui.number(1, 16, 1, value=1, label="Channel")
    sweep_pattern = mo.ui.text("Ramp /\\", label="Pattern")
    return_start = mo.ui.switch(False, label="return to start")
    repeats = mo.ui.number(1, 20, 1, value=3, label="Repeats")

    comments = mo.ui.text_area(
        value="T = 6K\nI+/- = 1/3\nV+/- = 4/5\nBG -1V",
        label="Comments (saved with the sweep)",
        rows=4,
        full_width=True,
    )

    rehearsal = mo.ui.switch(False, label="rehearsal (synthetic data)")
    run_btn = mo.ui.run_button(label="⚡  Run IV sweep", kind="success")
    reload_btn = mo.ui.run_button(label="🔄  Reload", kind="neutral")
    return (
        active,
        comments,
        initial_wait,
        rehearsal,
        reload_btn,
        repeats,
        return_start,
        run_btn,
        sweep_channel,
        sweep_pattern,
        sweep_time,
        v_end,
        v_start,
    )


@app.cell
def _(
    active,
    comments,
    initial_wait,
    mo,
    rehearsal,
    reload_btn,
    repeats,
    return_start,
    run_btn,
    slot_dirs,
    sweep_channel,
    sweep_pattern,
    sweep_time,
    v_end,
    v_start,
):
    mo.vstack(
        [
            mo.md("## Measure"),
            mo.hstack(
                [active, mo.md(f"→ saves into `{slot_dirs[active.value]}`")],
                justify="start",
                gap=1,
            ),
            mo.hstack(
                [v_start, v_end, sweep_time, initial_wait, sweep_channel, sweep_pattern],
                justify="start",
                gap=1,
                wrap=True,
            ),
            mo.hstack([return_start, repeats, rehearsal], justify="start", gap=2),
            comments,
            mo.hstack([run_btn, reload_btn], justify="start", gap=1),
        ]
    )
    return


@app.cell
def _(
    SIGN,
    active,
    comments,
    initial_wait,
    instrument,
    mo,
    rehearsal,
    repeats,
    return_start,
    run_btn,
    simulate,
    slot_dirs,
    slot_names,
    sweep_channel,
    sweep_pattern,
    sweep_time,
    v_end,
    v_start,
):
    run_status = mo.md("")

    if run_btn.value:
        _slot = active.value
        _dir = slot_dirs[_slot]
        _dir.mkdir(parents=True, exist_ok=True)
        _done, _errors = [], []

        _config = instrument.build_sweep_config(
            start=float(v_start.value),
            end=float(v_end.value),
            sweep_time=float(sweep_time.value),
            initial_wait=float(initial_wait.value),
            return_to_start=bool(return_start.value),
            channel=int(sweep_channel.value),
            pattern=sweep_pattern.value,
        )

        for _rep in range(int(repeats.value)):
            _title = f"Sweeping {slot_names[_slot]} — {_rep + 1}/{int(repeats.value)}"
            try:
                with mo.status.spinner(title=_title):
                    if rehearsal.value:
                        _path = simulate.simulate_into(
                            _dir,
                            SIGN[_slot],
                            stem=slot_names[_slot],
                            v_max=max(abs(v_start.value), abs(v_end.value)),
                        )
                    else:
                        _path = instrument.run_sweep(
                            exp_folder=slot_names[_slot],
                            comments=comments.value,
                            config=_config,
                            watch_dir=_dir,
                            timeout=float(sweep_time.value) + 30.0,
                        )
                _done.append(_path.name if _path else "(ran; file not seen yet)")
            except Exception as exc:
                _errors.append(f"repeat {_rep + 1}: {exc}")
                break

        if _errors:
            run_status = mo.callout(
                mo.md("**Sweep failed.** " + "; ".join(_errors)),
                kind="danger",
            )
        else:
            run_status = mo.callout(
                mo.md(
                    f"**{len(_done)} sweep(s)** into `{_dir}`\n\n"
                    + "\n".join(f"- `{d}`" for d in _done)
                ),
                kind="success",
            )
    run_status
    return (run_status,)


@app.cell
def _(
    SLOTS,
    c_on,
    channel_map,
    current_gain,
    ivio,
    mo,
    reload_btn,
    run_status,
    signal_mode,
    slot_dirs,
    slot_names,
):
    reload_btn.value, run_status  # reload triggers

    sweeps = {}
    problems = []
    for _s in SLOTS:
        if _s == "C" and not c_on.value:
            sweeps[_s] = []
            continue
        _found, _bad = ivio.load_folder(
            slot_dirs[_s],
            mode=signal_mode.value,
            channels=channel_map,
            current_gain=float(current_gain.value),
        )
        sweeps[_s] = _found
        problems += [f"{slot_names[_s]} — {b}" for b in _bad]

    _rows = [
        {"structure": slot_names[_s], **_sw.summary()} for _s in SLOTS for _sw in sweeps[_s]
    ]
    _blocks = [
        mo.md("## Sweeps"),
        mo.ui.table(_rows, selection=None, page_size=6),
    ]
    if problems:
        _blocks.append(
            mo.callout(
                mo.md("**Unreadable**\n\n" + "\n".join(f"- {p}" for p in problems)),
                kind="warn",
            )
        )
    mo.vstack(_blocks)
    return (sweeps,)


@app.cell
def _(SLOTS, mo, sweeps):
    pick = {
        s: mo.ui.multiselect(
            options=[sw.name for sw in sweeps[s]],
            value=[sw.name for sw in sweeps[s]],
            label=f"{s}",
        )
        for s in SLOTS
    }
    mo.hstack([pick[s] for s in SLOTS if sweeps[s]], justify="start", gap=2, wrap=True)
    return (pick,)


@app.cell
def _(SLOTS, pick, sweeps):
    selected = {
        s: [sw for sw in sweeps[s] if sw.name in set(pick[s].value)] for s in SLOTS
    }
    return (selected,)


@app.cell
def _(mo, np, selected):
    def _sig(x, digits=4):
        if not np.isfinite(x) or x == 0:
            return 0.0
        return float(round(x, -int(np.floor(np.log10(abs(x)))) + digits - 1))

    _all = [s for group in selected.values() for s in group]
    _reach = _sig(
        min(min(abs(float(np.nanmin(s.v))), abs(float(np.nanmax(s.v)))) for s in _all)
        if _all
        else 0.1
    )

    branch_mode = mo.ui.radio(
        options=["both", "forward", "backward"], value="both", inline=True, label="Branch"
    )
    smooth_win = mo.ui.slider(5, 81, 2, value=21, label="Smoothing", show_value=True)
    log_scale = mo.ui.switch(False, label="log |I|")
    eval_window = mo.ui.range_slider(
        start=0.0,
        stop=_reach,
        step=_reach / 100,
        value=[_sig(0.5 * _reach), _reach],
        label="Evaluation bias window (V)",
        show_value=True,
        full_width=True,
    )

    mo.vstack(
        [
            mo.md("## Analysis"),
            mo.hstack([branch_mode, smooth_win, log_scale], justify="start", gap=2),
            eval_window,
        ]
    )
    return branch_mode, eval_window, log_scale, smooth_win


@app.cell
def _(SLOTS, analysis, branch_mode, mo, selected, slot_names, smooth_win):
    mo.stop(
        len(selected["A"]) == 0 or len(selected["B"]) == 0,
        mo.callout(mo.md("Need at least one sweep selected for A and B."), kind="info"),
    )

    _pool = [s for group in selected.values() for s in group]
    shared_grid = analysis.common_grid(_pool, n_points=401)
    results = {
        _s: analysis.analyse_slot(
            slot_names[_s],
            selected[_s],
            grid=shared_grid,
            branch=branch_mode.value,
            smooth_window=int(smooth_win.value),
        )
        for _s in SLOTS
    }
    return (results,)


@app.cell
def _(analysis, eval_window, results):
    mirror = analysis.mirror_test(
        results["A"],
        results["B"],
        results["C"],
        v_window=(float(eval_window.value[0]), float(eval_window.value[1])),
    )
    return (mirror,)


@app.cell
def _(mirror, mo, results):
    def _pct(x):
        return "—" if x != x else f"{100 * x:+.2f}%"

    def _num(x, fmt="{:.2f}"):
        return "—" if x != x else fmt.format(x)

    _headline = [
        mo.stat(
            value=_pct(mirror.contrast),
            label="Chiral contrast  A(A) − A(B)",
            caption=f"±{100 * mirror.contrast_err:.2f}%   t = {_num(mirror.t_stat, '{:.1f}')}",
            bordered=True,
        ),
        mo.stat(
            value=_num(mirror.mirror_score),
            label="Mirror score",
            caption="1 = perfect enantiomer pair · 0 = no mirroring",
            bordered=True,
        ),
    ]
    _tiles = [
        mo.stat(
            value=_pct(mirror.a_values[results[s].label][0]),
            label=results[s].label,
            caption=f"±{100 * mirror.a_values[results[s].label][1]:.2f}% · "
            f"{results[s].n_sweeps} sweeps",
            bordered=True,
        )
        for s in ("A", "B", "C")
        if results.get(s) is not None and results[s].label in mirror.a_values
    ]

    mo.vstack(
        [
            mo.hstack(_headline, widths="equal", gap=1),
            mo.hstack(_tiles, widths="equal", gap=1),
            mo.callout(
                mo.md(
                    f"### {mirror.verdict()}\n\n"
                    f"Over **{mirror.v_window[0]:.4g} – {mirror.v_window[1]:.4g} V**. "
                    + (
                        f"The achiral control sits at {100 * mirror.noise_floor:.2f}%, "
                        "which is the floor this contrast has to clear."
                        if mirror.noise_floor == mirror.noise_floor
                        else "No control loaded — enable one for a noise floor."
                    )
                ),
                kind="success" if mirror.significant else "neutral",
            ),
        ]
    )
    return


@app.cell
def _(COLOURS, SLOTS, alt, np, pd, results):
    def colour():
        keep = [s for s in SLOTS if results.get(s) is not None]
        return alt.Color(
            "structure:N",
            scale=alt.Scale(
                domain=[results[s].label for s in keep], range=[COLOURS[s] for s in keep]
            ),
            legend=alt.Legend(title=None, orient="top"),
        )

    def iv_frame():
        return pd.concat(
            [
                pd.DataFrame(
                    {
                        "V": r.grid,
                        "I_nA": r.i_mean / 1e-9,
                        "lo": (r.i_mean - r.i_sd) / 1e-9,
                        "hi": (r.i_mean + r.i_sd) / 1e-9,
                        "absI_nA": np.abs(r.i_mean) / 1e-9,
                        "dIdV_nS": r.didv / 1e-9,
                        "structure": r.label,
                    }
                )
                for r in (results.get(s) for s in SLOTS)
                if r is not None
            ],
            ignore_index=True,
        ).dropna(subset=["I_nA"])

    def asym_frame():
        return pd.concat(
            [
                pd.DataFrame(
                    {
                        "V": r.u,
                        "A": 100 * r.a_mean,
                        "lo": 100 * (r.a_mean - r.a_sd),
                        "hi": 100 * (r.a_mean + r.a_sd),
                        "structure": r.label,
                    }
                )
                for r in (results.get(s) for s in SLOTS)
                if r is not None
            ],
            ignore_index=True,
        ).dropna(subset=["A"])

    return asym_frame, colour, iv_frame


@app.cell
def _(alt, colour, iv_frame, log_scale, mo, pd, signal_mode):
    _df = iv_frame()
    _base = alt.Chart(_df)
    _x = alt.X("V:Q", title=f"{signal_mode.value} bias (V)")

    if log_scale.value:
        _iv = _base.mark_line(strokeWidth=2.5).encode(
            x=_x,
            y=alt.Y("absI_nA:Q", title="|I| (nA)", scale=alt.Scale(type="log")),
            color=colour(),
            tooltip=["structure:N", alt.Tooltip("V:Q", format=".4g"),
                     alt.Tooltip("absI_nA:Q", format=".4g")],
        )
    else:
        _iv = _base.mark_area(opacity=0.18).encode(
            x=_x, y="lo:Q", y2="hi:Q", color=colour()
        ) + _base.mark_line(strokeWidth=2.5).encode(
            x=_x,
            y=alt.Y("I_nA:Q", title="I (nA)"),
            color=colour(),
            tooltip=["structure:N", alt.Tooltip("V:Q", format=".4g"),
                     alt.Tooltip("I_nA:Q", format=".4g")],
        )

    _zero = (
        alt.Chart(pd.DataFrame({"x": [0.0]}))
        .mark_rule(strokeDash=[4, 4], opacity=0.4)
        .encode(x="x:Q")
    )
    mo.vstack(
        [
            mo.md("### IV curves — mean of repeats, shaded ±1 SD"),
            mo.ui.altair_chart((_iv + _zero).properties(height=320)),
        ]
    )
    return


@app.cell
def _(alt, asym_frame, colour, eval_window, mirror, mo, pd, results):
    _df = asym_frame()
    _b = results["B"]
    _x = alt.X("V:Q", title="|Bias| (V)")

    _layers = (
        alt.Chart(
            pd.DataFrame(
                {"x": [float(eval_window.value[0])], "x2": [float(eval_window.value[1])]}
            )
        )
        .mark_rect(opacity=0.09, color="#333")
        .encode(x="x:Q", x2="x2:Q")
        + alt.Chart(_df).mark_area(opacity=0.18).encode(x=_x, y="lo:Q", y2="hi:Q", color=colour())
        + alt.Chart(_df)
        .mark_line(strokeWidth=2.5)
        .encode(
            x=_x,
            y=alt.Y("A:Q", title="Asymmetry A (%)"),
            color=colour(),
            tooltip=["structure:N", alt.Tooltip("V:Q", format=".4g"),
                     alt.Tooltip("A:Q", format=".2f")],
        )
        + alt.Chart(pd.DataFrame({"V": _b.u, "A": -100 * _b.a_mean}).dropna())
        .mark_line(strokeWidth=2, strokeDash=[6, 4], color="#0f7bbf", opacity=0.9)
        .encode(x="V:Q", y="A:Q")
        + alt.Chart(pd.DataFrame({"y": [0.0]}))
        .mark_rule(strokeDash=[4, 4], opacity=0.5)
        .encode(y="y:Q")
    )

    mo.vstack(
        [
            mo.md(
                f"### Asymmetry\n\n"
                f"Dashed = −A for {_b.label}. Enantiomers land on top of A. "
                f"Mirror score {mirror.mirror_score:.2f}."
            ),
            mo.ui.altair_chart(_layers.properties(height=320)),
        ]
    )
    return


@app.cell
def _(alt, colour, iv_frame, mo, signal_mode):
    mo.vstack(
        [
            mo.md("### Differential conductance"),
            mo.ui.altair_chart(
                alt.Chart(iv_frame())
                .mark_line(strokeWidth=2)
                .encode(
                    x=alt.X("V:Q", title=f"{signal_mode.value} bias (V)"),
                    y=alt.Y("dIdV_nS:Q", title="dI/dV (nS)"),
                    color=colour(),
                    tooltip=["structure:N", alt.Tooltip("V:Q", format=".4g"),
                             alt.Tooltip("dIdV_nS:Q", format=".4g")],
                )
                .properties(height=280)
            ),
        ]
    )
    return


@app.cell
def _(mo):
    export_btn = mo.ui.run_button(label="💾  Export", kind="neutral")
    mo.vstack([mo.md("## Export"), export_btn])
    return (export_btn,)


@app.cell
def _(
    SLOTS,
    asym_frame,
    datetime,
    eval_window,
    export_btn,
    iv_frame,
    mirror,
    mo,
    pd,
    results,
    root_path,
    signal_mode,
):
    mo.stop(not export_btn.value)

    _out = root_path / "exports" / datetime.now().strftime("%Y%m%d_%H%M%S")
    _out.mkdir(parents=True, exist_ok=True)
    _lo, _hi = float(eval_window.value[0]), float(eval_window.value[1])

    iv_frame().to_csv(_out / "iv_curves.csv", index=False)
    asym_frame().to_csv(_out / "asymmetry.csv", index=False)

    pd.DataFrame(
        [
            {
                "structure": r.label,
                "mode": signal_mode.value,
                "n_sweeps": r.n_sweeps,
                "A_mean_pct": 100 * r.a_at(_lo, _hi)[0],
                "A_sem_pct": 100 * r.a_at(_lo, _hi)[1],
                "rectification_ratio": r.rr_at(_lo, _hi),
                "G0_nS": r.g0 / 1e-9,
                "files": "; ".join(r.files),
            }
            for r in (results.get(s) for s in SLOTS)
            if r is not None
        ]
    ).to_csv(_out / "summary.csv", index=False)

    pd.DataFrame(
        [
            {
                "v_window_lo": mirror.v_window[0],
                "v_window_hi": mirror.v_window[1],
                "chiral_contrast_pct": 100 * mirror.contrast,
                "contrast_sem_pct": 100 * mirror.contrast_err,
                "t_stat": mirror.t_stat,
                "mirror_score": mirror.mirror_score,
                "noise_floor_pct": 100 * mirror.noise_floor,
                "verdict": mirror.verdict(),
            }
        ]
    ).to_csv(_out / "mirror_test.csv", index=False)

    mo.callout(mo.md(f"**Exported** → `{_out}`"), kind="success")
    return


if __name__ == "__main__":
    app.run()
