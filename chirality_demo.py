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
"""Chirality in KTO: drive a wire left-right or right-left, compare."""

import marimo

app = marimo.App(width="medium", app_title="Chirality in KTO")


@app.cell
def _():
    import sys
    from datetime import datetime
    from pathlib import Path

    import altair as alt
    import marimo as mo
    import pandas as pd

    NOTEBOOK_DIR = Path(__file__).resolve().parent
    if str(NOTEBOOK_DIR) not in sys.path:
        sys.path.insert(0, str(NOTEBOOK_DIR))

    import instrument
    from chiral_kto import ivio

    DIRECTIONS = ("forward", "reverse")
    DIR_LABELS = {"forward": "left → right", "reverse": "right → left"}
    DIR_COLOURS = {"forward": "#d1495b", "reverse": "#0f7bbf"}

    def exp_folder_name(label: str, direction: str) -> str:
        """The exp_folder string LockinSweep gets - FLEX creates this as a
        direct child of the session folder and puts the .tdms inside it."""
        return f"{label}_{direction}"

    return (
        DIRECTIONS,
        DIR_COLOURS,
        DIR_LABELS,
        NOTEBOOK_DIR,
        Path,
        alt,
        datetime,
        exp_folder_name,
        instrument,
        ivio,
        mo,
        pd,
    )


@app.cell
def _(instrument, mo):
    mo.hstack(
        [mo.md("# Chirality in KTaO₃"), mo.md(f"`{instrument.describe()}`")],
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
def _(mo):
    wire_label = mo.ui.text("wire1", label="Wire label")
    cur_left = mo.ui.number(1, 32, 1, value=1, label="Current left")
    cur_right = mo.ui.number(1, 32, 1, value=2, label="Current right")
    volt_left = mo.ui.text("AI3", label="Voltage left")
    volt_right = mo.ui.text("AI5", label="Voltage right")
    signal_mode = mo.ui.radio(options=["4T", "2T"], value="4T", inline=True, label="Leads")
    current_gain = mo.ui.number(1e-9, 1e9, value=1.0, label="Current gain (A/raw)")
    return (
        cur_left,
        cur_right,
        current_gain,
        signal_mode,
        volt_left,
        volt_right,
        wire_label,
    )


@app.cell
def _(
    Path,
    browse,
    cur_left,
    cur_right,
    current_gain,
    exp_folder_name,
    mo,
    session_dir,
    signal_mode,
    volt_left,
    volt_right,
    wire_label,
):
    def _picked():
        if browse is None or not browse.value:
            return ""
        raw = getattr(browse.value[0], "path", None) or getattr(browse.value[0], "id", "")
        return str(raw() if callable(raw) else raw)

    root_path = Path(_picked() or session_dir.value.strip().strip('"')).expanduser()
    _label = wire_label.value.strip()
    fwd_dir = root_path / exp_folder_name(_label, "forward")
    rev_dir = root_path / exp_folder_name(_label, "reverse")
    n_f = len(list(fwd_dir.glob("*.tdms"))) if fwd_dir.is_dir() else 0
    n_r = len(list(rev_dir.glob("*.tdms"))) if rev_dir.is_dir() else 0

    mo.vstack(
        [
            mo.md("## Setup"),
            session_dir,
            mo.accordion({"Browse…": browse}) if browse is not None else mo.md(""),
            wire_label,
            mo.hstack([cur_left, cur_right, volt_left, volt_right], justify="start", gap=1, wrap=True),
            mo.hstack([signal_mode, current_gain], justify="start", gap=2),
            mo.md(
                f"current is sensed on whichever side isn't driving — right's "
                f"channel when going left → right, left's when going right → left"
            ),
            mo.md(
                f"`{fwd_dir.name}`: {n_f} · `{rev_dir.name}`: {n_r} "
                f"— both directly under `{root_path}`"
            ),
        ]
    )
    return fwd_dir, rev_dir, root_path


@app.cell
def _(DIR_LABELS, mo):
    direction = mo.ui.radio(
        options=list(DIR_LABELS.values()), value=DIR_LABELS["forward"], inline=True, label="Direction"
    )

    v_start = mo.ui.number(-10.0, 10.0, 0.001, value=-0.1, label="Start (V)")
    v_end = mo.ui.number(-10.0, 10.0, 0.001, value=0.1, label="End (V)")
    sweep_time = mo.ui.number(1.0, 600.0, 1.0, value=30.0, label="Sweep time (s)")
    initial_wait = mo.ui.number(0.0, 60.0, 0.5, value=1.0, label="Initial wait (s)")
    sweep_pattern = mo.ui.text("Ramp /\\", label="Pattern")
    return_start = mo.ui.switch(False, label="return to start")

    comments = mo.ui.text_area(
        value="T = 6K\nI+/- = 1/3\nV+/- = 4/5\nBG -1V",
        label="Comments (saved with the sweep)",
        rows=4,
        full_width=True,
    )

    run_btn = mo.ui.run_button(label="⚡  Run IV sweep", kind="success")
    reload_btn = mo.ui.run_button(label="🔄  Reload", kind="neutral")
    return (
        comments,
        direction,
        initial_wait,
        reload_btn,
        return_start,
        run_btn,
        sweep_pattern,
        sweep_time,
        v_end,
        v_start,
    )


@app.cell
def _(
    DIR_LABELS,
    comments,
    cur_left,
    cur_right,
    direction,
    fwd_dir,
    initial_wait,
    mo,
    return_start,
    rev_dir,
    run_btn,
    reload_btn,
    sweep_pattern,
    sweep_time,
    v_end,
    v_start,
    wire_label,
):
    _dir = "forward" if direction.value == DIR_LABELS["forward"] else "reverse"
    _drive, _hold = (cur_left.value, cur_right.value) if _dir == "forward" else (cur_right.value, cur_left.value)
    _save_dir = fwd_dir if _dir == "forward" else rev_dir

    mo.vstack(
        [
            mo.md("## Measure"),
            direction,
            mo.md(
                f"AO{_drive} drives, AO{_hold} held at 0V → saves into `{_save_dir}` "
                f"({wire_label.value})"
            ),
            mo.hstack(
                [v_start, v_end, sweep_time, initial_wait, sweep_pattern],
                justify="start", gap=1, wrap=True,
            ),
            comments,
            mo.hstack([return_start, run_btn, reload_btn], justify="start", gap=1),
        ]
    )
    return


@app.cell
def _(
    DIR_LABELS,
    comments,
    cur_left,
    cur_right,
    direction,
    exp_folder_name,
    fwd_dir,
    initial_wait,
    instrument,
    mo,
    return_start,
    rev_dir,
    run_btn,
    sweep_pattern,
    sweep_time,
    v_end,
    v_start,
    wire_label,
):
    run_status = mo.md("")

    if run_btn.value:
        _dir = "forward" if direction.value == DIR_LABELS["forward"] else "reverse"
        _drive, _hold = (cur_left.value, cur_right.value) if _dir == "forward" else (cur_right.value, cur_left.value)
        _save_dir = fwd_dir if _dir == "forward" else rev_dir

        _config = instrument.build_sweep_config(
            start=float(v_start.value),
            end=float(v_end.value),
            drive_channel=_drive,
            hold_channel=_hold,
            sweep_time=float(sweep_time.value),
            initial_wait=float(initial_wait.value),
            return_to_start=bool(return_start.value),
            pattern=sweep_pattern.value,
        )

        try:
            with mo.status.spinner(title=f"IV {direction.value} — {wire_label.value}"):
                _path = instrument.run_sweep(
                    exp_folder=exp_folder_name(wire_label.value.strip(), _dir),
                    comments=comments.value,
                    config=_config,
                    hold_channel=_hold,
                    watch_dir=_save_dir,
                )
            run_status = mo.callout(
                mo.md(f"**{direction.value}** — `{_path.name if _path else '(ran; file not seen yet)'}`"),
                kind="success",
            )
        except Exception as exc:
            run_status = mo.callout(mo.md(f"**Sweep failed.** {exc}"), kind="danger")
    run_status
    return (run_status,)


@app.cell
def _(
    DIRECTIONS,
    cur_left,
    cur_right,
    current_gain,
    fwd_dir,
    ivio,
    mo,
    reload_btn,
    rev_dir,
    run_status,
    signal_mode,
    volt_left,
    volt_right,
):
    reload_btn.value, run_status  # reload triggers

    _dirs = {"forward": fwd_dir, "reverse": rev_dir}
    # whichever side isn't driving is where the return current is sensed
    _drives = {"forward": cur_left.value, "reverse": cur_right.value}
    _senses = {"forward": cur_right.value, "reverse": cur_left.value}
    sweeps = {}
    problems = []
    for _d in DIRECTIONS:
        _found, _bad = ivio.load_folder(
            _dirs[_d],
            mode=signal_mode.value,
            channels={
                "drive": f"AO{_drives[_d]}",
                "current": f"AI{_senses[_d]}",
                "v_plus": volt_left.value,
                "v_minus": volt_right.value,
            },
            current_gain=float(current_gain.value),
        )
        sweeps[_d] = _found
        problems += [f"{_d} — {b}" for b in _bad]

    _rows = [
        {"direction": _d, **_sw.summary()} for _d in DIRECTIONS for _sw in sweeps[_d]
    ]
    _blocks = [mo.md("## Sweeps"), mo.ui.table(_rows, selection=None, page_size=8)]
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
def _(DIRECTIONS, mo, sweeps):
    pick = {
        d: mo.ui.multiselect(
            options=[sw.name for sw in sweeps[d]],
            value=[sw.name for sw in sweeps[d]],
            label=d,
        )
        for d in DIRECTIONS
    }
    mo.hstack([pick[d] for d in DIRECTIONS if sweeps[d]], justify="start", gap=2, wrap=True)
    return (pick,)


@app.cell
def _(DIRECTIONS, pick, sweeps):
    selected = {d: [sw for sw in sweeps[d] if sw.name in set(pick[d].value)] for d in DIRECTIONS}
    return (selected,)


@app.cell
def _(DIRECTIONS, DIR_LABELS, pd, selected):
    def iv_frame():
        frames = [
            pd.DataFrame(
                {
                    "V": sw.v,
                    "I_nA": sw.i / 1e-9,
                    "direction": DIR_LABELS[d],
                    "file": sw.name,
                }
            )
            for d in DIRECTIONS
            for sw in selected[d]
        ]
        if not frames:
            return pd.DataFrame(columns=["V", "I_nA", "direction", "file"])
        return pd.concat(frames, ignore_index=True)

    return (iv_frame,)


@app.cell
def _(DIR_COLOURS, DIR_LABELS, alt, iv_frame, mo, pd, signal_mode):
    mo.stop(
        iv_frame().empty,
        mo.callout(mo.md("No sweeps selected — pick some above, or run one."), kind="info"),
    )

    _df = iv_frame()
    _colour = alt.Color(
        "direction:N",
        scale=alt.Scale(
            domain=list(DIR_LABELS.values()),
            range=[DIR_COLOURS["forward"], DIR_COLOURS["reverse"]],
        ),
        legend=alt.Legend(title=None, orient="top"),
    )
    _zero = (
        alt.Chart(pd.DataFrame({"x": [0.0]}))
        .mark_rule(strokeDash=[4, 4], opacity=0.4)
        .encode(x="x:Q")
    )
    _lines = (
        alt.Chart(_df)
        .mark_line(strokeWidth=1.5, opacity=0.85)
        .encode(
            x=alt.X("V:Q", title=f"{signal_mode.value} bias (V)"),
            y=alt.Y("I_nA:Q", title="I (nA)"),
            color=_colour,
            detail="file:N",
            tooltip=["direction:N", "file:N", alt.Tooltip("V:Q", format=".4g"),
                     alt.Tooltip("I_nA:Q", format=".4g")],
        )
    )

    mo.vstack(
        [
            mo.md("## IV curves"),
            mo.ui.altair_chart((_lines + _zero).properties(height=380)),
        ]
    )
    return


@app.cell
def _(mo):
    export_btn = mo.ui.run_button(label="💾  Export", kind="neutral")
    mo.vstack([mo.md("## Export"), export_btn])
    return (export_btn,)


@app.cell
def _(datetime, export_btn, iv_frame, mo, root_path, wire_label):
    mo.stop(not export_btn.value)

    _out = root_path / "exports" / f"{wire_label.value}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    _out.mkdir(parents=True, exist_ok=True)
    iv_frame().to_csv(_out / "iv_curves.csv", index=False)

    mo.callout(mo.md(f"**Exported** → `{_out}`"), kind="success")
    return


if __name__ == "__main__":
    app.run()
