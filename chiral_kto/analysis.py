"""Turn raw IV sweeps into the numbers that make the chirality claim.

The physics the demo is showing: a chiral structure written by cAFM lithography
transports charge asymmetrically in bias, and its enantiomer should show the
*mirrored* asymmetry. So the pipeline is

    sweep -> monotonic branches -> common symmetric bias grid
          -> per-bias asymmetry A(V) -> enantiomer mirror test

with an achiral control supplying the noise floor that says whether the
A-vs-B splitting is real.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

try:  # scipy is nice for smoothing but must not be load-bearing
    from scipy.signal import savgol_filter as _savgol
except Exception:  # pragma: no cover - fallback path
    _savgol = None


# ---------------------------------------------------------------- branches


def split_branches(
    v: np.ndarray, i: np.ndarray, min_points: int = 8
) -> list[tuple[np.ndarray, np.ndarray]]:
    """Split a sweep into monotonic ramps (forward / backward / repeats)."""
    v = np.asarray(v, float)
    i = np.asarray(i, float)
    if v.size < min_points:
        return [(v, i)] if v.size else []

    dv = np.diff(v)
    sign = np.sign(dv)
    # carry the last non-zero direction across flat spots
    last = 0.0
    filled = np.empty_like(sign)
    for k, s in enumerate(sign):
        if s != 0:
            last = s
        filled[k] = last
    if not np.any(filled):
        return [(v, i)]

    cuts = np.flatnonzero(np.diff(filled) != 0) + 1
    segments = []
    for a, b in zip([0, *cuts.tolist()], [*cuts.tolist(), v.size]):
        if b - a >= min_points:
            segments.append((v[a:b], i[a:b]))
    return segments or [(v, i)]


def _resample(v: np.ndarray, i: np.ndarray, grid: np.ndarray) -> np.ndarray:
    """Interpolate one monotonic branch onto ``grid``; NaN outside its range."""
    order = np.argsort(v)
    vs, ivals = v[order], i[order]
    # collapse duplicate voltages so np.interp stays well defined
    vs, idx = np.unique(vs, return_inverse=True)
    ivals = np.bincount(idx, weights=ivals) / np.bincount(idx)
    out = np.interp(grid, vs, ivals, left=np.nan, right=np.nan)
    out[(grid < vs[0]) | (grid > vs[-1])] = np.nan
    return out


def sweep_on_grid(
    v: np.ndarray,
    i: np.ndarray,
    grid: np.ndarray,
    *,
    branch: str = "both",
) -> np.ndarray:
    """One sweep -> one current trace on ``grid``.

    ``branch`` is "both" (average the ramps, cancelling hysteresis), "forward"
    (increasing bias only) or "backward".
    """
    segments = split_branches(v, i)
    if branch == "forward":
        segments = [s for s in segments if s[0][-1] > s[0][0]] or segments
    elif branch == "backward":
        segments = [s for s in segments if s[0][-1] < s[0][0]] or segments

    stack = np.vstack([_resample(sv, si, grid) for sv, si in segments])
    with np.errstate(invalid="ignore"):
        return np.nanmean(stack, axis=0)


def common_grid(
    sweeps, n_points: int = 401, v_limit: float | None = None
) -> np.ndarray:
    """Symmetric bias grid covering the range every sweep actually measured."""
    if not sweeps:
        return np.linspace(-1.0, 1.0, n_points)
    reach = min(
        min(abs(float(np.nanmin(s.v))), abs(float(np.nanmax(s.v)))) for s in sweeps
    )
    if v_limit is not None:
        reach = min(reach, abs(v_limit))
    reach = max(reach, 1e-9)
    return np.linspace(-reach, reach, n_points | 1)  # odd -> a point exactly at 0


# ---------------------------------------------------------------- metrics


def _interp_finite(x: np.ndarray, xp: np.ndarray, fp: np.ndarray) -> np.ndarray:
    """np.interp that ignores NaNs in ``fp`` instead of smearing them."""
    good = np.isfinite(fp)
    if good.sum() < 2:
        return np.full_like(np.asarray(x, float), np.nan)
    return np.interp(x, xp[good], fp[good], left=np.nan, right=np.nan)


def asymmetry(grid: np.ndarray, current: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Bias-resolved asymmetry A(|V|) = (|I(+V)| - |I(-V)|) / (|I(+V)| + |I(-V)|).

    Bounded in [-1, 1], sign-flips between enantiomers, and is zero for any
    curve that is odd in bias (i.e. for an achiral, symmetric junction).
    """
    u = grid[grid > 0]
    ip = np.abs(_interp_finite(u, grid, current))
    im = np.abs(_interp_finite(-u, grid, current))
    total = ip + im
    with np.errstate(invalid="ignore", divide="ignore"):
        a = np.where(total > 0, (ip - im) / total, np.nan)
    return u, a


def rectification_ratio(grid: np.ndarray, current: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """RR(|V|) = |I(+V)| / |I(-V)|."""
    u = grid[grid > 0]
    ip = np.abs(_interp_finite(u, grid, current))
    im = np.abs(_interp_finite(-u, grid, current))
    with np.errstate(invalid="ignore", divide="ignore"):
        return u, np.where(im > 0, ip / im, np.nan)


def smooth(y: np.ndarray, window: int = 21, poly: int = 3) -> np.ndarray:
    """Savitzky-Golay if scipy is around, boxcar otherwise. NaN safe."""
    y = np.asarray(y, float)
    finite = np.isfinite(y)
    n = int(finite.sum())
    if n < 5:
        return y
    window = int(window) | 1                 # savgol needs an odd window
    window = min(window, n if n % 2 else n - 1)
    window = max(window, 5)
    filled = np.interp(np.arange(y.size), np.flatnonzero(finite), y[finite])
    if _savgol is not None and window > poly:
        out = _savgol(filled, window, poly)
    else:
        out = np.convolve(filled, np.ones(window) / window, mode="same")
    return np.where(finite, out, np.nan)


def differential_conductance(
    grid: np.ndarray, current: np.ndarray, window: int = 21
) -> np.ndarray:
    """dI/dV in siemens, from the smoothed trace."""
    return np.gradient(smooth(current, window), grid)


def zero_bias_conductance(grid: np.ndarray, current: np.ndarray, span: float = 0.05) -> float:
    """Slope of a straight-line fit through the low-bias region, in siemens."""
    m = np.isfinite(current) & (np.abs(grid) <= abs(span) * np.nanmax(np.abs(grid)))
    if m.sum() < 3:
        return float("nan")
    return float(np.polyfit(grid[m], current[m], 1)[0])


# ---------------------------------------------------------------- per-slot


@dataclass
class SlotResult:
    """Everything computed for one written structure (a folder of repeats)."""

    label: str
    grid: np.ndarray
    curves: np.ndarray          # (n_sweeps, n_grid) current in A
    i_mean: np.ndarray
    i_sd: np.ndarray
    u: np.ndarray               # positive bias axis
    asym: np.ndarray            # (n_sweeps, n_u)
    a_mean: np.ndarray
    a_sd: np.ndarray
    didv: np.ndarray
    g0: float
    n_sweeps: int
    files: list[str]

    def a_at(self, v_lo: float, v_hi: float) -> tuple[float, float, int]:
        """Mean asymmetry over a bias window: (mean, standard error, n)."""
        m = (self.u >= v_lo) & (self.u <= v_hi)
        vals = self.asym[:, m] if self.asym.size else np.empty((0, 0))
        vals = vals[np.isfinite(vals)]
        if vals.size == 0:
            return float("nan"), float("nan"), 0
        # n is the number of independent sweeps, not the number of grid points
        n = max(self.n_sweeps, 1)
        return float(vals.mean()), float(vals.std(ddof=0) / np.sqrt(n)), n

    def rr_at(self, v_lo: float, v_hi: float) -> float:
        u, rr = rectification_ratio(self.grid, self.i_mean)
        m = (u >= v_lo) & (u <= v_hi) & np.isfinite(rr)
        return float(np.nanmean(rr[m])) if m.any() else float("nan")


def analyse_slot(
    label: str,
    sweeps,
    *,
    grid: np.ndarray | None = None,
    branch: str = "both",
    smooth_window: int = 21,
) -> SlotResult | None:
    """Reduce a folder of repeat sweeps to one SlotResult."""
    if not sweeps:
        return None
    grid = common_grid(sweeps) if grid is None else grid

    curves = np.vstack([sweep_on_grid(s.v, s.i, grid, branch=branch) for s in sweeps])
    with np.errstate(invalid="ignore"):
        i_mean = np.nanmean(curves, axis=0)
        i_sd = np.nanstd(curves, axis=0, ddof=0) if len(sweeps) > 1 else np.zeros_like(i_mean)

    asym_rows = [asymmetry(grid, row)[1] for row in curves]
    u = asymmetry(grid, i_mean)[0]
    asym = np.vstack(asym_rows) if asym_rows else np.empty((0, u.size))
    with np.errstate(invalid="ignore"):
        a_mean = np.nanmean(asym, axis=0)
        a_sd = np.nanstd(asym, axis=0, ddof=0) if len(sweeps) > 1 else np.zeros_like(a_mean)

    return SlotResult(
        label=label,
        grid=grid,
        curves=curves,
        i_mean=i_mean,
        i_sd=i_sd,
        u=u,
        asym=asym,
        a_mean=a_mean,
        a_sd=a_sd,
        didv=differential_conductance(grid, i_mean, smooth_window),
        g0=zero_bias_conductance(grid, i_mean),
        n_sweeps=len(sweeps),
        files=[s.name for s in sweeps],
    )


# ---------------------------------------------------------------- the verdict


@dataclass
class MirrorTest:
    """Does driving reverse flip the asymmetry seen driving forward?"""

    mirror_score: float      # 1 - ||A_A + A_B|| / (||A_A|| + ||A_B||), in [0, 1]
    contrast: float          # <A_A - A_B> over the evaluation window
    contrast_err: float
    t_stat: float
    noise_floor: float       # |<A>| of a control slot, if one was given
    a_values: dict[str, tuple[float, float, int]]
    v_window: tuple[float, float]

    @property
    def significant(self) -> bool:
        clears_noise = (
            not np.isfinite(self.noise_floor)
            or abs(self.contrast) > 3 * max(self.noise_floor, 0.0)
        )
        return bool(np.isfinite(self.t_stat) and abs(self.t_stat) > 3 and clears_noise)

    def verdict(self) -> str:
        if not np.isfinite(self.contrast):
            return "not enough data"
        if not self.significant:
            return "no significant chiral contrast yet"
        if self.mirror_score > 0.7:
            return "reverse mirrors forward - consistent with a chiral wire"
        if self.mirror_score > 0.4:
            return "partial mirroring - contrast is real, symmetry is imperfect"
        return "contrast is real, but reverse doesn't mirror forward"


def _mirror_score(a: np.ndarray, b: np.ndarray) -> float:
    """How close is ``b`` to being ``-a``? 1 = perfect mirror, 0 = no mirroring.

    Uses the normalised residual ||a + b|| / (||a|| + ||b||) rather than a
    correlation: over a bias window where A(V) has saturated, both curves are
    near-constant and a *centred* correlation sees only noise. The residual form
    keeps working there, and it also penalises a magnitude mismatch - a partner
    with half the asymmetry does not score as a clean enantiomer.
    """
    good = np.isfinite(a) & np.isfinite(b)
    if good.sum() < 3:
        return float("nan")
    a, b = a[good], b[good]
    norm_a = float(np.sqrt(np.mean(a**2)))
    norm_b = float(np.sqrt(np.mean(b**2)))
    if norm_a + norm_b <= 0:
        return float("nan")
    residual = float(np.sqrt(np.mean((a + b) ** 2)))
    return 1.0 - residual / (norm_a + norm_b)


def mirror_test(
    slot_a: SlotResult,
    slot_b: SlotResult,
    control: SlotResult | None = None,
    *,
    v_window: tuple[float, float] | None = None,
) -> MirrorTest:
    """Compare the two enantiomeric structures over a high-bias window."""
    u = slot_a.u
    if v_window is None:
        v_window = (0.5 * float(u.max()), float(u.max()))
    lo, hi = v_window

    a_mean, a_err, a_n = slot_a.a_at(lo, hi)
    b_mean, b_err, b_n = slot_b.a_at(lo, hi)

    # do the two asymmetry curves sit on top of each other once B is flipped?
    shared = np.linspace(lo, hi, 200)
    ca = _interp_finite(shared, slot_a.u, slot_a.a_mean)
    cb = _interp_finite(shared, slot_b.u, slot_b.a_mean)
    score = _mirror_score(ca, cb)

    contrast = a_mean - b_mean
    err = float(np.hypot(a_err, b_err))
    t = contrast / err if err > 0 else float("nan")

    values = {slot_a.label: (a_mean, a_err, a_n), slot_b.label: (b_mean, b_err, b_n)}
    floor = float("nan")
    if control is not None:
        c_mean, c_err, c_n = control.a_at(lo, hi)
        values[control.label] = (c_mean, c_err, c_n)
        floor = abs(c_mean) + (c_err if np.isfinite(c_err) else 0.0)

    return MirrorTest(
        mirror_score=score,
        contrast=contrast,
        contrast_err=err,
        t_stat=t,
        noise_floor=floor,
        a_values=values,
        v_window=(lo, hi),
    )
