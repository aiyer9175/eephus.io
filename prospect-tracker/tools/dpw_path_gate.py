# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The $/WAR path gate's one lab (docs/dpw-2026-09-25/DPW_PATH_GATE.md).

Modes:
  (default)            synthetic: the functions below, exercised by
                       test_dpw_path_lab.py on SYNTHETIC series only.
  --prelook            run ONCE by the pre-look amendment task (F-B): forecasts,
                       the I-3 and I-5 records, the stamps, g_I(N) on the truth
                       and on the served basis (forecast quantities, never
                       errors), the blindness check and, if it passes, the
                       origin-2026 ledger forecast rows; writes the
                       dpw_path_gate STUB block (verdict REGISTERED). Computes no
                       error of any arm and never calls the oracle search.
  --real               THE LOOK (F-C), once, on the registration's clock. Refuses
                       unless exactly one amendment commit exists and the block
                       at that commit reads REGISTERED; reads the pinned
                       dpw_path block and data/dpw_path_owner.json from that
                       commit, never the live files.
  --owner-after-look   copies an OD-7 zero_if_floor row from the live owner file
                       into the block's owner_after_look, only while the block's
                       INCUMBENT_BELOW_FLOOR is true (section 12).

Order inside the look (section 6, fixed): integrity gates; the size run at each
rho (truth and I only), which fixes c; the errors of I and F and
INCUMBENT_BELOW_FLOOR with that c; the detection run; MDE95; P2 attainability;
THEN the cells of A and the verdict; then the descriptive T and B, the term-mix
errors, BAND_COVERAGE and DeltaUSD.

The lab imports neither backtest nor surplus_backtest_real, never calls
fa_backtest.run_market_gate, computes nothing by consensus-FV cell, and writes
nothing but its block and ledger rows (I-6). It never writes
data/fa_dpw_series.json.
"""

from __future__ import annotations

import argparse
import hashlib
import itertools
import json
import math
import statistics
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import dpw_path as dp                                            # noqa: E402

# ---------------------------------------------------------------------------
# Registered constants (sections 1, 4, 5, 6, 7). Pinned by test_dpw_path_lab.py.
# ---------------------------------------------------------------------------
GATE_DOC_REL = "docs/dpw-2026-09-25/DPW_PATH_GATE.md"
EVAL_PATH = ROOT / "data" / "dpw_forecast_eval.json"
LEDGER_PATH = ROOT / "data" / "dpw_path_ledger.json"
OWNER_PATH = ROOT / "data" / "dpw_path_owner.json"
SERIES_PATH = ROOT / "data" / "fa_dpw_series.json"
EPOCH_DOC = ROOT / "docs" / "efv-2026-09-17" / "FWAR_LABEL_EPOCH_GATE.md"
BLOCK_KEY = "dpw_path_gate"
AMENDMENT_REGEX = "^## Amendment 1 [(]pre-look[)]$"
AMENDMENT_HEADING = "## Amendment 1 (pre-look)"

SEED = 20260925
B_BOOT = 2000                 # SE_boot on the real contrast
B_PLANT_BOOT = 500            # SE_boot inside a planted draw
N_DRAWS = 1000                # draws per size / detection evaluation
B_BAND = 500                  # tau bootstrap (the writer's)
ORIGINS = tuple(range(2018, 2026))
LAST_TARGET = 2026
H_MAX = 5
JACK_WINTERS = tuple(range(2015, 2027))
W_BASE = 1.113763
M = 0.025
C_DEFAULT = 1.894579
RHOS = (0.0, 0.8)
SIGMA_FLOOR = 0.01
MAX_HALVINGS = 6
BISECT_STEPS = 30
TOL_FRAC = 0.05
KAPPA_BRACKET = (0.0, 1.0)
KAPPA_BRACKET_NEG = (-3.0, 0.0)
GSTAR_LO, GSTAR_HI, GSTAR_STEP, GSTAR_TOL = -0.20, 0.30, 0.0005, 1e-10
REGIME_TARGETS = frozenset({2021, 2022})
S1 = frozenset(range(2018, 2021))
S2 = frozenset(range(2021, 2026))
FULL_HORIZON_ORIGINS = frozenset(range(2018, 2022))
DETECTION_BAR = 0.80
P_BAR = 0.05
MIN_UNTIED = 6
TIE = 1e-12
CLIP_HI = 0.12
SIZE_STATUSES = ("FULL", "PARTIAL", "UNAVAILABLE")
NO_PASSING_DRAW = "NO_PASSING_DRAW"
P2_UNATTAINABLE = "P2_UNATTAINABLE"
PASS_UNATTAINABLE = "PASS_UNATTAINABLE"
REGISTERED = "REGISTERED"
# The registered look dates of other gates (section 14) the look may never share.
OTHER_LOOK_DAYS = ("2026-10-02", "2026-10-09", "2026-10-23", "2026-11-06", "2026-11-13", "2027-02-15")

# Section 7, each criterion's text byte-identical to the document.
CRITERIA = {
    "P1": "- **P1, bound and sign-flip.** `Dbar(A, I) + c x SE* < 0`, AND the exact one-sided sign-flip\n"
          "  p <= 0.05.",
    "P2": "- **P2, practical size.** `Q(I) - Q(A) >= M/2` on the point estimate.",
    "P3": "- **P3, horizon one not worse.** `MSE_1(A) <= MSE_1(I)` on the point estimate.",
    "P4": "- **P4, time splits.** `D_o(A, I) < 0` at 6 or more of the 8 origins (a tied origin does not count).",
    "P5": "- **P5, both sub-periods.** `Dbar(A, I) < 0` on S1 and on S2.",
    "P6": "- **P6, without REGIME targets.** `Dbar(A, I) < 0` on the non-REGIME pairs. This drops REGIME\n"
          "  targets only; REGIME winters stay as inputs and anchors, and P7 covers that channel.",
    "P7": "- **P7, no single winter carries it.** `Dbar_(-y)(A, I) < 0` for every jackknife replicate of\n"
          "  section 5 that keeps at least 4 origins.",
    "P8": "- **P8, beats the floor and is no more biased.** `Dbar(A, F) < 0` on the point estimate, AND\n"
          "  `|bbar(A)| <= |bbar(I)| + M/2`.",
}
UNCONDITIONAL_SENTENCE = (
    "Every number here is a statement about the signings-implied $/WAR series on its growth-free "
    "sticker basis (deferred deals at their level-equivalent sticker), built from WAR projections "
    "fitted before each winter on the fWAR label with the 2020 playing-time correction; the "
    "projection settings and the label vintage are today's. The series is the price the winning "
    "bidder paid per projected win; it leaves out the tax a payroll above the threshold pays, "
    "minor-league deals and extensions. No surplus accuracy was measured, and seasons after 2031 "
    "are an assumption, not a forecast.")


class LabRefused(SystemExit):
    """The lab refuses to run (a precondition of the registration fails)."""


# ---------------------------------------------------------------------------
# The frame (sections 1.2, 4.1, 5): origins, horizons, weights, REGIME pairs
# ---------------------------------------------------------------------------

def weights_for(hs) -> np.ndarray:
    """w_h = 1.113763^-h renormalised over the horizons present; h keeps its value."""
    raw = np.array([W_BASE ** -h for h in hs], dtype=float)
    return raw / raw.sum()


def build_frame(series: dict, delete: int | None = None) -> dict:
    """The development frame on ``series`` with winter ``delete`` removed
    EVERYWHERE (inputs by the gap rule, origins and targets). An origin needs at
    least 4 winters at or before it and at least one target."""
    s = {int(w): float(v) for w, v in series.items()
         if v is not None and float(v) > 0 and int(w) != delete}
    origins = []
    for o in ORIGINS:
        if o not in s or len(dp.available(s, o)) < dp.MIN_WINTERS:
            continue
        H = min(H_MAX, LAST_TARGET - o)
        hs = [h for h in range(1, H + 1) if (o + h) in s]
        if not hs:
            continue
        a = s[o]
        r = np.array([s[o + h] / a for h in hs])
        nr = [i for i, h in enumerate(hs) if (o + h) not in REGIME_TARGETS]
        origins.append({
            "origin": o, "anchor": a, "hs": np.array(hs, dtype=float), "h_list": hs,
            "w": weights_for(hs), "r": r,
            "nr_idx": nr, "nr_w": weights_for([hs[i] for i in nr]) if nr else None,
            "g_I": dp.g_destale(s, o), "g_A": dp.g_robust(s, o),
        })
    return {"series": s, "delete": delete, "origins": origins}


def build_context(truth: dict) -> dict:
    """The full frame and the 12 delete-everywhere jackknife replicates."""
    return {"full": build_frame(truth),
            "reps": {y: build_frame(truth, delete=y) for y in JACK_WINTERS}}


def g_star(rec: dict) -> float:
    """The ORACLE growth g*_o: the constant growth minimising S_o from the anchor,
    over [-0.20, 0.30]: a grid scan at 0.0005, then golden section inside the two
    grid cells around the best grid point, to 1e-10. Used unclipped. Computed
    ONLY inside the look (G-0); --prelook never calls it."""
    def S(g):
        x = (1.0 + g) ** rec["hs"] - rec["r"]
        return float((rec["w"] * x * x).sum())
    n = int(round((GSTAR_HI - GSTAR_LO) / GSTAR_STEP))
    grid = [GSTAR_LO + i * GSTAR_STEP for i in range(n + 1)]
    vals = [S(g) for g in grid]
    b = min(range(len(grid)), key=vals.__getitem__)
    lo, hi = grid[max(0, b - 1)], grid[min(len(grid) - 1, b + 1)]
    phi = (math.sqrt(5.0) - 1.0) / 2.0
    c, d = hi - phi * (hi - lo), lo + phi * (hi - lo)
    fc, fd = S(c), S(d)
    while hi - lo > GSTAR_TOL:
        if fc < fd:
            hi, d, fd = d, c, fc
            c = hi - phi * (hi - lo)
            fc = S(c)
        else:
            lo, c, fc = c, d, fd
            d = lo + phi * (hi - lo)
            fd = S(d)
    return 0.5 * (lo + hi)


def attach_g_star(ctx: dict) -> None:
    for fr in [ctx["full"], *ctx["reps"].values()]:
        for rec in fr["origins"]:
            rec["g_star"] = g_star(rec)


# ---------------------------------------------------------------------------
# Losses of constant-growth arms, vectorised over draws (k x n)
# ---------------------------------------------------------------------------

def losses(frame: dict, G: np.ndarray) -> dict:
    """For growth matrix G (k draws x n origins of ``frame``): S_o, the bias
    b_o, the horizon-1 error u_1 (nan where h = 1 is absent) and the non-REGIME
    S_o (nan where no non-REGIME pair is left)."""
    G = np.atleast_2d(np.asarray(G, dtype=float))
    k, n = G.shape
    S = np.empty((k, n))
    bias = np.empty((k, n))
    u1 = np.full((k, n), np.nan)
    Snr = np.full((k, n), np.nan)
    for i, rec in enumerate(frame["origins"]):
        u = (1.0 + G[:, i:i + 1]) ** rec["hs"][None, :] - rec["r"][None, :]
        S[:, i] = (rec["w"][None, :] * u * u).sum(1)
        bias[:, i] = (rec["w"][None, :] * u).sum(1)
        if rec["h_list"][0] == 1:
            u1[:, i] = u[:, 0]
        if rec["nr_idx"]:
            un = u[:, rec["nr_idx"]]
            Snr[:, i] = (rec["nr_w"][None, :] * un * un).sum(1)
    return {"S": S, "bias": bias, "u1": u1, "Snr": Snr}


def growth_of(frame: dict, key: str) -> np.ndarray:
    """1 x n growth row for a registered constant-growth arm on ``frame``:
    g_I (incumbent), g_A (challenger), 0 (floor), g_star (oracle)."""
    if key == "F":
        return np.zeros((1, len(frame["origins"])))
    field = {"I": "g_I", "A": "g_A", "STAR": "g_star"}[key]
    return np.array([[rec[field] for rec in frame["origins"]]], dtype=float)


def _origin_years(frame):
    return [rec["origin"] for rec in frame["origins"]]


def sign_flip_p(D: np.ndarray, dbar: np.ndarray) -> np.ndarray:
    """Exact one-sided sign-flip p for each row of D (k x n): the share of the
    2^n sign patterns whose mean is at or below the observed mean; a tied
    origin contributes zero to every pattern."""
    n = D.shape[1]
    Dz = np.where(np.abs(D) < TIE, 0.0, D)
    signs = np.array(list(itertools.product((1.0, -1.0), repeat=n)))
    means = Dz @ signs.T / n
    return (means <= dbar[:, None] + 1e-15).mean(1)


def compare(ctx: dict, gx, gy, boot_idx: np.ndarray, c: float, *, gf=None,
            need_criteria: bool = True) -> dict:
    """The registered contrast of arm X against arm Y (section 5) for k draws at
    once. ``gx(frame)`` / ``gy(frame)`` return k x n growth matrices on any
    frame (the full frame and every jackknife replicate); ``boot_idx`` is
    k x B x n. With ``need_criteria`` P1 to P8 are evaluated (X as A, Y as I and
    ``gf`` the floor)."""
    full = ctx["full"]
    oy = _origin_years(full)
    LX, LY = losses(full, gx(full)), losses(full, gy(full))
    k = LX["S"].shape[0]
    LY_S = np.broadcast_to(LY["S"], LX["S"].shape)
    D = LX["S"] - LY_S
    dbar = D.mean(1)
    jack = np.empty((k, len(JACK_WINTERS)))
    jack_n = []
    for j, y in enumerate(JACK_WINTERS):
        fr = ctx["reps"][y]
        jack_n.append(len(fr["origins"]))
        if not fr["origins"]:
            jack[:, j] = np.nan
            continue
        jx, jy = losses(fr, gx(fr))["S"], losses(fr, gy(fr))["S"]
        jack[:, j] = (jx - np.broadcast_to(jy, jx.shape)).mean(1)
    nj = len(JACK_WINTERS)
    jm = np.nanmean(jack, 1)
    se_jack = np.sqrt((nj - 1) / nj * np.nansum((jack - jm[:, None]) ** 2, 1))
    bm = np.take_along_axis(D[:, None, :].repeat(boot_idx.shape[1], 1), boot_idx, 2).mean(2)
    se_boot = bm.std(1, ddof=1)
    se = np.maximum(se_jack, se_boot)
    p = sign_flip_p(D, dbar)
    QX = np.sqrt(LX["S"].mean(1))
    QY = np.sqrt(np.broadcast_to(LY["S"], LX["S"].shape).mean(1))
    out = {"origins": oy, "D": D, "Dbar": dbar, "SE_jack": se_jack, "SE_boot": se_boot, "SE": se,
           "jack": jack, "jack_n": jack_n, "p_sign": p, "Q_X": QX, "Q_Y": QY,
           "ties": (np.abs(D) < TIE).sum(1)}
    if not need_criteria:
        return out
    mse1_x = np.nanmean(LX["u1"] ** 2, 1)
    mse1_y = np.nanmean(np.broadcast_to(LY["u1"], LX["u1"].shape) ** 2, 1)
    s1 = [i for i, o in enumerate(oy) if o in S1]
    s2 = [i for i, o in enumerate(oy) if o in S2]
    dnr = LX["Snr"] - np.broadcast_to(LY["Snr"], LX["Snr"].shape)
    keep = [nn >= 4 for nn in jack_n]
    LF = losses(full, gf(full))
    dxf = (LX["S"] - np.broadcast_to(LF["S"], LX["S"].shape)).mean(1)
    bbar_x = LX["bias"].mean(1)
    bbar_y = np.broadcast_to(LY["bias"], LX["bias"].shape).mean(1)
    crit = {
        "P1": (dbar + c * se < 0) & (p <= P_BAR),
        "P2": (QY - QX) >= M / 2.0,
        "P3": mse1_x <= mse1_y,
        "P4": (D < -TIE).sum(1) >= MIN_UNTIED,
        "P5": (D[:, s1].mean(1) < 0) & (D[:, s2].mean(1) < 0),
        "P6": np.nanmean(dnr, 1) < 0,
        "P7": np.all(jack[:, [j for j, kp in enumerate(keep) if kp]] < 0, 1),
        "P8": (dxf < 0) & (np.abs(bbar_x) <= np.abs(bbar_y) + M / 2.0),
    }
    out.update({"criteria": crit, "pass": np.all(np.vstack(list(crit.values())), 0),
                "MSE_1_X": mse1_x, "MSE_1_Y": mse1_y, "Dbar_S1": D[:, s1].mean(1),
                "Dbar_S2": D[:, s2].mean(1), "Dbar_nonregime": np.nanmean(dnr, 1),
                "Dbar_XF": dxf, "bbar_X": bbar_x, "bbar_Y": bbar_y})
    return out


def const_arm(key: str):
    return lambda fr: growth_of(fr, key)


# ---------------------------------------------------------------------------
# The planted challenger (section 6 item 2), common random numbers by draw
# ---------------------------------------------------------------------------

def draw_streams(n_origins: int, n_draws: int = N_DRAWS, b_plant: int = B_PLANT_BOOT) -> dict:
    """Draw j uses seed 20260925 + j for every kappa, sigma and rho: e_o (one
    N(0, 1) per origin) and the plant bootstrap indices."""
    E = np.empty((n_draws, n_origins))
    idx = np.empty((n_draws, b_plant, n_origins), dtype=np.int64)
    for j in range(n_draws):
        rng = np.random.default_rng(SEED + j)
        E[j] = rng.standard_normal(n_origins)
        idx[j] = rng.integers(0, n_origins, size=(b_plant, n_origins))
    return {"E": E, "idx": idx}


def persistent_z(E: np.ndarray, rho: float) -> np.ndarray:
    """z_2018 = e_2018; z_o = rho z_(o-1) + sqrt(1 - rho^2) e_o."""
    z = np.empty_like(E)
    z[:, 0] = E[:, 0]
    a = math.sqrt(1.0 - rho * rho)
    for i in range(1, E.shape[1]):
        z[:, i] = rho * z[:, i - 1] + a * E[:, i]
    return z


def sigma_g(ctx: dict) -> float:
    gi = [math.log(1.0 + rec["g_I"]) for rec in ctx["full"]["origins"]]
    return max(statistics.stdev(gi), SIGMA_FLOOR)


def plant_arm(ctx: dict, z: np.ndarray, kappa: float, sigma: float):
    """g_C(o) = clip(g_I + kappa (g*_o - g_I) + sigma z_o, 0, 0.12) on any frame,
    z_o kept by origin year under a jackknife deletion."""
    col = {o: i for i, o in enumerate(_origin_years(ctx["full"]))}

    def gx(frame):
        gi = growth_of(frame, "I")
        gs = growth_of(frame, "STAR")
        zz = z[:, [col[o] for o in _origin_years(frame)]]
        return np.clip(gi + kappa * (gs - gi) + sigma * zz, 0.0, CLIP_HI)
    return gx


def evaluate_plant(ctx, streams, rho, kappa, sigma, c, need_criteria=True) -> dict:
    z = persistent_z(streams["E"], rho)
    return compare(ctx, plant_arm(ctx, z, kappa, sigma), const_arm("I"), streams["idx"], c,
                   gf=const_arm("F"), need_criteria=need_criteria)


def plant_search(f, sigma0: float) -> dict:
    """The size run's plant search (section 6 item 2(a)), on any f(kappa, sigma)
    -> (mean Dbar(C, I), tol). Records every evaluation."""
    steps = []

    def ev(kappa, sigma, note):
        m, tol = f(kappa, sigma)
        steps.append({"kappa": kappa, "sigma": sigma, "f": float(m), "tol": float(tol), "note": note})
        return float(m), float(tol)

    def found(kappa, sigma, halvings, how):
        return {"status": "FOUND", "kappa": kappa, "sigma": sigma, "halvings": halvings,
                "how": how, "steps": steps}

    def bisect(lo, hi, flo, sigma, halvings, how):
        for _ in range(BISECT_STEPS):
            mid = 0.5 * (lo + hi)
            fm, tm = ev(mid, sigma, f"bisect {how}")
            if abs(fm) <= tm:
                return found(mid, sigma, halvings, how)
            if (fm < 0) == (flo < 0):
                lo, flo = mid, fm
            else:
                hi = mid
        last = steps[-1]
        if abs(last["f"]) <= last["tol"]:
            return found(last["kappa"], sigma, halvings, how)
        return {"status": "UNAVAILABLE", "reason": "bisection ended with |f| > tol",
                "halvings": halvings, "steps": steps}

    sigma = float(sigma0)
    for halving in range(MAX_HALVINGS + 1):
        f0, t0 = ev(0.0, sigma, "step 1")
        if abs(f0) <= t0:
            return found(0.0, sigma, halving, "[0, 1]")
        f1, t1 = ev(1.0, sigma, "step 1")
        if abs(f1) <= t1:
            return found(1.0, sigma, halving, "[0, 1]")
        if (f0 < 0) != (f1 < 0):
            return bisect(0.0, 1.0, f0, sigma, halving, "[0, 1]")
        if f0 < 0:
            fm3, tm3 = ev(-3.0, sigma, "step 2")
            if abs(fm3) <= tm3:
                return found(-3.0, sigma, halving, "[-3, 0]")
            if fm3 >= 0:
                return bisect(-3.0, 0.0, fm3, sigma, halving, "[-3, 0]")
        if halving < MAX_HALVINGS:
            sigma = sigma / 2.0
    return {"status": "UNAVAILABLE", "reason": "no bracket after 6 halvings", "halvings": MAX_HALVINGS,
            "steps": steps}


def size_run(ctx, streams, sg, *, search=plant_search) -> dict:
    """Item 2(a) at each rho: the plant, size_full at c = 1.894579, and the c it
    leaves (raised to the larger available 95th percentile of -Dbar/SE* if any
    available size_full exceeds 0.05)."""
    runs = {}
    for rho in RHOS:
        def f(kappa, sigma, rho=rho):
            ev = evaluate_plant(ctx, streams, rho, kappa, sigma, C_DEFAULT, need_criteria=False)
            return float(ev["Dbar"].mean()), TOL_FRAC * float(np.median(ev["SE"]))
        res = search(f, sg)
        if res["status"] == "FOUND":
            ev = evaluate_plant(ctx, streams, rho, res["kappa"], res["sigma"], C_DEFAULT)
            res["size_full"] = float(ev["pass"].mean())
            res["q95_neg_dbar_over_se"] = float(np.percentile(-ev["Dbar"] / ev["SE"], 95))
        runs[str(rho)] = res
    avail = [r for r in runs.values() if r["status"] == "FOUND"]
    status = "FULL" if len(avail) == 2 else "PARTIAL" if len(avail) == 1 else "UNAVAILABLE"
    c = C_DEFAULT
    if avail and any(r["size_full"] > P_BAR for r in avail):
        c = max(C_DEFAULT, max(r["q95_neg_dbar_over_se"] for r in avail))
    return {"by_rho": runs, "size_status": status, "c": c,
            "unavailable_rho": [float(k) for k, r in runs.items() if r["status"] != "FOUND"]}


def detection_run(ctx, streams, sg, c) -> dict:
    """Item 2(b) at each rho: kappa bisected in [0, 1] at sigma_g so that the
    mean Q(I) - Q(C) equals M (kappa = 1 when M cannot be reached)."""
    out = {}
    for rho in RHOS:
        def gain(kappa, rho=rho):
            ev = evaluate_plant(ctx, streams, rho, kappa, sg, c, need_criteria=False)
            return float((ev["Q_Y"] - ev["Q_X"]).mean()) - M
        g1 = gain(1.0)
        note = None
        if g1 < 0:
            kappa, note = 1.0, "M_NOT_REACHED_AT_KAPPA_1"
        else:
            lo, hi = 0.0, 1.0
            g0 = gain(0.0)
            if g0 >= 0:
                kappa = 0.0
            else:
                for _ in range(BISECT_STEPS):
                    mid = 0.5 * (lo + hi)
                    if gain(mid) < 0:
                        lo = mid
                    else:
                        hi = mid
                kappa = 0.5 * (lo + hi)
        ev = evaluate_plant(ctx, streams, rho, kappa, sg, c)
        gainv = ev["Q_Y"] - ev["Q_X"]
        passed = ev["pass"]
        rec = {"kappa": kappa, "note": note, "detection_full": float(passed.mean()),
               "detection_p1": float(ev["criteria"]["P1"].mean()),
               "median_SE": float(np.median(ev["SE"]))}
        if passed.any():
            rec["type_m"] = float(gainv[passed].mean() / gainv.mean()) if gainv.mean() else None
            rec["detectable_gain_q"] = float(np.median(gainv[passed]))
            rec["null_reason"] = None
        else:
            rec["type_m"] = None
            rec["detectable_gain_q"] = None
            rec["null_reason"] = NO_PASSING_DRAW
        out[str(rho)] = rec
    return out


def real_boot_idx(n: int, b: int = B_BOOT) -> np.ndarray:
    rng = np.random.default_rng(SEED)
    return rng.integers(0, n, size=(1, b, n))


def power_block(ctx, *, n_draws: int = N_DRAWS, b_plant: int = B_PLANT_BOOT,
                search=plant_search, log=None) -> dict:
    """Section 6 in its registered order: the size run (fixes c), then the
    errors of I and F with INCUMBENT_BELOW_FLOOR at that c, then the detection
    run, MDE95 and P2 attainability. Uses the truth, I and F (and the oracle
    growth inside the plant) only; no error of A, T or B."""
    log = log if log is not None else []
    attach_g_star(ctx)
    n = len(ctx["full"]["origins"])
    streams = draw_streams(n, n_draws, b_plant)
    sg = sigma_g(ctx)
    log.append("size_run")
    size = size_run(ctx, streams, sg, search=search)
    c = size["c"]
    log.append("incumbent_vs_floor")
    idf = compare(ctx, const_arm("I"), const_arm("F"), real_boot_idx(n), c, need_criteria=False)
    below = bool(idf["Dbar"][0] - c * idf["SE"][0] > 0)
    log.append("detection_run")
    det = detection_run(ctx, streams, sg, c)
    mde95 = c * det["0.8"]["median_SE"]
    full = ctx["full"]
    QI = float(np.sqrt(losses(full, growth_of(full, "I"))["S"].mean()))
    Qs = float(np.sqrt(losses(full, growth_of(full, "STAR"))["S"].mean()))
    log.append("p2_attainability")
    return {"sigma_g": sg, "size_run": size, "c": c,
            "incumbent_vs_floor": {"Dbar": float(idf["Dbar"][0]), "SE_star": float(idf["SE"][0]),
                                   "SE_jack": float(idf["SE_jack"][0]),
                                   "SE_boot": float(idf["SE_boot"][0])},
            "INCUMBENT_BELOW_FLOOR": below, "detection": det, "MDE95": mde95,
            "detectable_gain_q_at_0.8": det["0.8"]["detectable_gain_q"],
            "Q_I": QI, "Q_g_star": Qs, "P2_UNATTAINABLE": bool(QI - Qs < M / 2.0),
            "n_draws": n_draws, "b_plant": b_plant, "seed": SEED}


# ---------------------------------------------------------------------------
# The cells of A and the verdict (sections 5 and 7)
# ---------------------------------------------------------------------------

def per_horizon(frame: dict, key: str) -> dict:
    """MSE_h (mean u^2) and BIAS_h (mean u) over the origins available at h."""
    G = growth_of(frame, key)[0]
    acc: dict[int, list] = {}
    for g, rec in zip(G, frame["origins"]):
        u = (1.0 + g) ** rec["hs"] - rec["r"]
        for h, x in zip(rec["h_list"], u):
            acc.setdefault(int(h), []).append(float(x))
    return {str(h): {"MSE": float(np.mean(np.square(v))), "BIAS": float(np.mean(v)), "n": len(v)}
            for h, v in sorted(acc.items())}


def cells(ctx: dict, c: float) -> dict:
    """The contrast of A against I with every registered statistic and P1-P8."""
    n = len(ctx["full"]["origins"])
    res = compare(ctx, const_arm("A"), const_arm("I"), real_boot_idx(n), c, gf=const_arm("F"))
    one = {k: (v[0].tolist() if isinstance(v, np.ndarray) and v.ndim == 2 else
               (float(v[0]) if isinstance(v, np.ndarray) else v))
           for k, v in res.items() if k not in ("criteria", "pass")}
    one["criteria"] = {k: {"pass": bool(v[0]), "text": CRITERIA[k]} for k, v in res["criteria"].items()}
    one["pass"] = bool(res["pass"][0])
    one["influence"] = {str(o): float(np.delete(res["D"][0], i).mean())
                        for i, o in enumerate(res["origins"])}
    one["MSE_h"] = {"A": per_horizon(ctx["full"], "A"), "I": per_horizon(ctx["full"], "I"),
                    "F": per_horizon(ctx["full"], "F")}
    one["c"] = c
    return one


def decide(cell: dict, power: dict) -> dict:
    """Section 7's closed vocabulary. Ties go to the incumbent."""
    c = power["c"]
    if cell["pass"]:
        return {"verdict": "PASS_DEV", "reason": None}
    if cell["Dbar"] - c * cell["SE"] > 0:
        return {"verdict": "WORSE", "reason": None}
    n = len(cell["origins"])
    k = int(cell["ties"])
    reasons = []
    if n - k < MIN_UNTIED:
        reasons.append("fewer than 6 untied origins")
    if 2.0 ** k / 2.0 ** n > P_BAR:
        reasons.append("smallest attainable sign-flip p above 0.05")
    if power.get("P2_UNATTAINABLE"):
        reasons.append(P2_UNATTAINABLE)
    if reasons:
        return {"verdict": "NULL_UNDERPOWERED", "reason": PASS_UNATTAINABLE, "detail": reasons}
    det = min(r["detection_full"] for r in power["detection"].values())
    if det < DETECTION_BAR:
        return {"verdict": "NULL_UNDERPOWERED", "reason": "detection_full below 0.80",
                "detection_full_min": det}
    return {"verdict": "NULL", "reason": None, "detection_full_min": det}


def sentence(verdict: dict, cell: dict, power: dict, first_blind_origin=None) -> str:
    """Section 17's sentence for the outcome."""
    v = verdict["verdict"]
    c = power["c"]
    dbar, se = cell["Dbar"], cell["SE"]
    size = power["size_run"]
    tail = ""
    if size["size_status"] == "UNAVAILABLE":
        tail = "; the size run was unavailable, so false passes were not size-controlled"
    elif size["size_status"] == "PARTIAL":
        tail = "; false passes were size-controlled only at rho = %g" % (
            [float(r) for r in RHOS if float(r) not in size["unavailable_rho"]][0])
    if v == "PASS_DEV":
        k = sum(1 for d in cell["D"] if d < -TIE)
        return ("On the eight forward-chained origins 2018 to 2025, a $/WAR growth rule based on the median "
                "of the series' own year-over-year changes forecast the level one to five winters ahead "
                f"better than the rule behind the served escalator (mean PV-weighted squared error contrast "
                f"{dbar:.6f}, bound {dbar + c * se:.6f}, {k} of 8 origins{tail}). Its designers chose it "
                "after reading every winter of the series, so this frame was not blind, and nothing "
                "switches until the blind condition.")
    if v == "NULL":
        return ("On the eight forward-chained origins 2018 to 2025, a median-based growth rule did not "
                f"forecast the $/WAR level better than the rule behind the served escalator ({dbar:.6f}, "
                f"bound {dbar + c * se:.6f}). Each season is priced at the one written $/WAR path, which "
                "grows at the escalator the owner set.")
    if v == "NULL_UNDERPOWERED":
        det = min(r["detection_full"] for r in power["detection"].values())
        why = (f"; a pass was unattainable because ({', '.join(verdict.get('detail') or [])})"
               if verdict.get("reason") == PASS_UNATTAINABLE else "")
        return ("Twelve winters cannot tell a median-based growth rule from the rule behind the served "
                f"escalator at a 2.5 percent margin (detection {det:.3f} against 0.80{why}). Each season is "
                "priced at the one written $/WAR path, which grows at the escalator the owner set. This is "
                "not evidence that constant growth is right. Blind forecasts accrue each winter from "
                f"{first_blind_origin if first_blind_origin is not None else 'the first blind origin'}.")
    if v == "WORSE":
        return ("The median-based growth rule forecast the $/WAR level worse than the rule behind the "
                f"served escalator at horizons one to five ({dbar:.6f}, lower bound {dbar - c * se:.6f}); "
                "recorded as a loss. The one written path keeps growing at the owner's escalator.")
    return f"The registered $/WAR path read was {v}. Nothing served changed."


def floor_sentence(power: dict) -> str | None:
    if not power.get("INCUMBENT_BELOW_FLOOR"):
        return None
    ivf = power["incumbent_vs_floor"]
    return ("The rule behind the served escalator forecast the $/WAR level worse than no growth at all on "
            f"the forward-chained origins ({ivf['Dbar']:.6f}, lower bound "
            f"{ivf['Dbar'] - power['c'] * ivf['SE_star']:.6f}). Nothing switches; the escalator goes back "
            "to the owner.")


def descriptive_arms(ctx: dict) -> dict:
    """T (trend_line) and B (damped), computed AFTER the verdict, DESCRIPTIVE;
    T's horizon-1 cells are SPENT."""
    out = {}
    for arm, method in (("T", "trend_line"), ("B", "damped")):
        rows = []
        for rec in ctx["full"]["origins"]:
            o = rec["origin"]
            s = ctx["full"]["series"]
            for h, r in zip(rec["h_list"], rec["r"]):
                p = dp.forecast(method, s, o, int(h)) / rec["anchor"]
                rows.append({"origin": o, "h": int(h), "u": float(p - r),
                             "label": "SPENT" if (arm == "T" and h == 1) else "DESCRIPTIVE"})
        out[arm] = rows
    return out


def band_coverage(ctx: dict) -> dict:
    """BAND_COVERAGE: the share of development pairs inside I's ex-ante P10/P90
    band (section 11's formula, built at each origin from winters <= it), per h."""
    cov: dict[int, list] = {}
    s = ctx["full"]["series"]
    for rec in ctx["full"]["origins"]:
        o = rec["origin"]
        sub = {w: v for w, v in s.items() if w <= o}
        path = {o + h: rec["anchor"] * (1.0 + rec["g_I"]) ** h for h in range(0, H_MAX + 1)}
        try:
            b = dp.band(path, o, sub, 0.0, "carry_destale")
        except dp.DpwPathError:
            continue
        for h in rec["h_list"]:
            t = o + int(h)
            cov.setdefault(int(h), []).append(b["p10"][t] <= s[t] <= b["p90"][t])
    return {str(h): {"share": float(np.mean(v)), "n": len(v), "target": 0.80} for h, v in sorted(cov.items())}


# ---------------------------------------------------------------------------
# DeltaUSD (section 8a): the dollar translation, priced from a COPY of the
# amendment commit's series file through the forced-on accessors
# ---------------------------------------------------------------------------

def exposure_by_horizon(data_dir: Path, series_copy: Path, horizons: int = 9) -> dict:
    """X(h), h = 1..9: the served value-leg dollars of season 2026 + h times
    season_discount(2026 + h) (PV at R to B), summed over prospects and veterans
    on /projections/ and free agents on /fa/ (a player on both counted once, on
    /projections/), carry_const, from the payload files on disk; by surface only.
    The accessors read ``series_copy`` (never the live file)."""
    import value_framework as vf
    dd = Path(data_dir)
    shas = {}
    tot = {"projections": [0.0] * (horizons + 1), "fa": [0.0] * (horizons + 1)}
    seen = set()
    with vf.dpw_path_forced(True, series_path=series_copy):
        if not vf.dpw_path_active():
            raise LabRefused("the series copy carries no dpw_path block")
        b = vf.pricing_base_season()
        mp_path = dd / "mlb_projections.json"
        if mp_path.exists():
            shas[mp_path.name] = _sha_file(mp_path)
            mp = json.loads(mp_path.read_text(encoding="utf-8"))
            first = int(mp.get("first_season") or b)
            for row in list(mp.get("vets") or []) + list(mp.get("prospects") or []):
                key = row.get("key")
                if not key or key in seen:
                    continue
                seen.add(key)
                war = list(row.get("war") or []) + list(row.get("warTail") or [])
                for t, w in enumerate(war):
                    s = first + t
                    h = s - (b - 1)
                    if 1 <= h <= horizons and w is not None:
                        tot["projections"][h] += vf.season_value_usd(float(w), s) * vf.season_discount(s)
        for fp in sorted(dd.glob("fa_class*.json")):
            shas[fp.name] = _sha_file(fp)
            fc = json.loads(fp.read_text(encoding="utf-8"))
            cy = int(fc.get("class_year") or b)
            for m in fc.get("members") or []:
                key = m.get("key")
                if not key or key in seen:
                    continue
                seen.add(key)
                for t, w in enumerate(m.get("warPath") or []):
                    s = cy + t
                    h = s - (b - 1)
                    if 1 <= h <= horizons and w is not None:
                        tot["fa"][h] += vf.season_value_usd(float(w), s) * vf.season_discount(s)
    X = [tot["projections"][h] + tot["fa"][h] for h in range(horizons + 1)]
    return {"X": {str(h): X[h] for h in range(1, horizons + 1)},
            "by_surface": {k: {str(h): v[h] for h in range(1, horizons + 1)} for k, v in tot.items()},
            "payload_sha256": shas, "series_copy_sha256": _sha_file(series_copy),
            "players_counted": len(seen)}


def taper_fold(X: dict) -> dict:
    """X*(h) = X(h) for h = 1..4; X*(5) = X(5) + sum_{k=1..4} (1 - k/5) X(5 + k)."""
    xs = {int(h): float(v) for h, v in X.items()}
    out = {h: xs.get(h, 0.0) for h in range(1, 5)}
    out[5] = xs.get(5, 0.0) + sum((1.0 - k / 5.0) * xs.get(5 + k, 0.0) for k in range(1, 5))
    return out


def delta_usd(ctx: dict, xstar: dict, type_m=None) -> dict:
    """E_o(P) = |sum_h X*(h) e_{o,h}(P)|, e = P/A - 1; DeltaUSD = the mean over
    origins 2018-2021 of E_o(A) - E_o(I) (all-origin mean secondary)."""
    rows = []
    for rec in ctx["full"]["origins"]:
        e = {}
        for key, g in (("A", rec["g_A"]), ("I", rec["g_I"])):
            tot = 0.0
            for h, r in zip(rec["h_list"], rec["r"]):
                tot += xstar.get(int(h), 0.0) * (((1.0 + g) ** h) / r - 1.0)
            e[key] = abs(tot)
        rows.append({"origin": rec["origin"], "E_A": e["A"], "E_I": e["I"], "diff": e["A"] - e["I"]})
    head = [r["diff"] for r in rows if r["origin"] in FULL_HORIZON_ORIGINS]
    out = {"per_origin": rows, "DeltaUSD": float(np.mean(head)) if head else None,
           "DeltaUSD_all_origins": float(np.mean([r["diff"] for r in rows])) if rows else None}
    if type_m:
        out["DeltaUSD_over_type_m"] = out["DeltaUSD"] / type_m if out["DeltaUSD"] is not None else None
    else:
        out["DeltaUSD_over_type_m"] = None
        out["DeltaUSD_over_type_m_reason"] = NO_PASSING_DRAW
    return out


# ---------------------------------------------------------------------------
# Integrity helpers (I-1 to I-8), git, the ledger and the owner record
# ---------------------------------------------------------------------------

def _sha_file(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def md5_file(p: Path) -> str | None:
    try:
        return hashlib.md5(Path(p).read_bytes()).hexdigest()
    except OSError:
        return None


def check_md5_unchanged(start: str | None, path: Path = SERIES_PATH) -> dict:
    """I-6: the series file is unchanged across the run; a change VOIDS the look."""
    end = md5_file(path)
    if start != end:
        raise LabRefused(f"I-6 failed: {path.name} changed during the run ({start} -> {end})")
    return {"md5_start": start, "md5_end": end, "unchanged": True}


def git(args: list[str], cwd: Path | None = None) -> str:
    return subprocess.run(["git", *args], cwd=str(cwd or ROOT), check=True, capture_output=True,
                          text=True, encoding="utf-8").stdout


def amendment_commits(cwd: Path | None = None, doc_rel: str = GATE_DOC_REL) -> list[str]:
    """The registered lookup: git log -G '^## Amendment 1 [(]pre-look[)]$'
    --format=%H -- <doc>. Line-anchored, so the registration commit, which
    mentions the heading mid-line only, never matches."""
    out = git(["log", "-G", AMENDMENT_REGEX, "--format=%H", "--", doc_rel], cwd=cwd)
    return [ln.strip() for ln in out.splitlines() if ln.strip()]


def show_at(commit: str, rel: str, cwd: Path | None = None) -> str:
    return git(["show", f"{commit}:{rel}"], cwd=cwd)


def repo_rel(path: Path) -> str:
    """A path relative to the git top level (the repo root is prospect-tracker's parent)."""
    top = Path(git(["rev-parse", "--show-toplevel"]).strip())
    return Path(path).resolve().relative_to(top.resolve()).as_posix()


def blob_shas(paths=None, cwd: Path | None = None) -> dict:
    """I-7: the git blob shas of tools/dpw_path_gate.py and dpw_path.py, of the
    working files and of HEAD's committed blobs; the run refuses if they differ."""
    paths = paths or [ROOT / "tools" / "dpw_path_gate.py", ROOT / "dpw_path.py"]
    out = {}
    for p in paths:
        work = git(["hash-object", str(p)], cwd=cwd).strip()
        rel = Path(p).resolve().relative_to(Path(git(["rev-parse", "--show-toplevel"], cwd=cwd)
                                                     .strip()).resolve()).as_posix()
        try:
            head = git(["rev-parse", f"HEAD:{rel}"], cwd=cwd).strip()
        except subprocess.CalledProcessError:
            head = None
        out[rel] = {"working": work, "head": head, "equal": work == head}
    return out


def check_blobs(rec: dict) -> None:
    bad = [k for k, v in rec.items() if not v["equal"]]
    if bad:
        raise LabRefused(f"I-7 failed: uncommitted changes to {', '.join(bad)}")


def load_ledger(path: Path = LEDGER_PATH) -> dict:
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        doc = {"schema": dp.LEDGER_SCHEMA, "rows": []}
    dp.verify_chain(doc.get("rows") or [])
    return doc


def append_ledger(rows_new: list[dict], path: Path = LEDGER_PATH) -> dict:
    """Append rows to the hash-chained ledger; returns its head record."""
    doc = load_ledger(path)
    rows = doc.setdefault("rows", [])
    for r in rows_new:
        dp.append_chained(rows, r)
    dp.verify_chain(rows)
    Path(path).write_text(json.dumps(doc, indent=1), encoding="utf-8")
    return dp.chain_head(rows)


def tracked_blind_docs(reader) -> dict:
    """The tracked files the blindness check reads, by kind; ``reader(rel)``
    returns parsed JSON or None (the working tree for --prelook, git show of
    the adding commit for the ledger re-check)."""
    docs = {}
    for rel, kind in (("data/fa_dpw_series.json", "fa_dpw_series"), ("data/fa_meta.json", "fa_meta"),
                      ("data/fa_class.json", "fa_class"), ("data/fa_class_2028.json", "fa_class"),
                      ("data/fa_class_2029.json", "fa_class"),
                      ("data/dpw_forecast_eval.json", "dpw_forecast_eval"),
                      ("data/fa_archive.json", "fa_archive")):
        doc = reader(rel)
        if doc is not None:
            docs[rel] = (kind, doc)
    return docs


def working_reader(rel: str):
    p = ROOT / rel
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def deal_count_db(winter: int) -> int:
    """Condition 2: class o+1 signings in prospects.db passing the estimator's
    deal filter (MLB deal with years, guarantee and MLBAM id)."""
    import storage
    return sum(1 for s in storage.load_fa_signings(int(winter)).values()
               if s.get("mlb_deal") and s.get("years") and s.get("guarantee_usd") and s.get("mlbam_id"))


def blindness(origin: int, reader=working_reader, deal_count=deal_count_db, scrape_at: str | None = None) -> dict:
    chk = dp.realized_level_check(tracked_blind_docs(reader), origin + 1)
    n = int(deal_count(origin + 1))
    return {**chk, "deal_count": n, "scrape_at": scrape_at, "blind": dp.is_blind(chk, n)}


def owner_record_at(commit: str | None, cwd: Path | None = None, rel: str | None = None) -> dict:
    """owner_at_amendment: OD-6 and OD-7 as they stood in the AMENDMENT tree,
    as option codes, dates and row hashes (never text), with the chain head and
    count. Never the live file."""
    if commit is None:
        raise LabRefused("owner_at_amendment needs the amendment commit")
    rel = rel or repo_rel(OWNER_PATH)
    try:
        doc = json.loads(show_at(commit, rel, cwd=cwd))
    except subprocess.CalledProcessError:
        doc = None
    return dp.owner_record_for_block(doc)


def read_block(path: Path = EVAL_PATH) -> dict | None:
    try:
        return (json.loads(Path(path).read_text(encoding="utf-8")) or {}).get(BLOCK_KEY)
    except FileNotFoundError:
        return None


def write_block(block: dict, path: Path = EVAL_PATH) -> None:
    """Write the dpw_path_gate block into the eval artifact, leaving every other
    key (the tool's own, its top-level generated_at included) as it is."""
    try:
        doc = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        doc = {}
    doc[BLOCK_KEY] = block
    Path(path).write_text(json.dumps(doc, indent=1), encoding="utf-8")


RESULT_KEYS = ("power", "cells", "verdict_detail", "descriptive", "DeltaUSD", "flags", "sentence")


def step_z_entry(text: str | None = None) -> str | None:
    """I-1: the dated step Z entry in part 9 of the epoch gate, or None."""
    if text is None:
        try:
            text = EPOCH_DOC.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None
    if "## 9. Results" not in text:
        return None
    part9 = text.split("## 9. Results", 1)[1]
    import re
    m = re.search(r"(\d{4}-\d{2}-\d{2})[^\n]*\bstep Z\b", part9)
    return m.group(1) if m else None


# ---------------------------------------------------------------------------
# --prelook
# ---------------------------------------------------------------------------

def prelook(*, series_doc: dict | None = None, eval_path: Path = EVAL_PATH, ledger_path: Path = LEDGER_PATH,
            reader=working_reader, deal_count=deal_count_db, scrape_at: str | None = None,
            today: str | None = None, check_epoch: bool = True) -> dict:
    """Write the STUB block (verdict REGISTERED) and, if blind, the origin-2026
    ledger forecast rows. Computes forecasts only: no error of any arm, and the
    oracle search is never called."""
    existing = read_block(eval_path)
    if existing is not None:
        if existing.get("verdict") != REGISTERED or any(k in existing for k in RESULT_KEYS):
            raise LabRefused("--prelook refused: the block already carries a verdict or a result")
    if check_epoch and step_z_entry() is None:
        raise LabRefused("--prelook refused: no step Z entry in FWAR_LABEL_EPOCH_GATE.md part 9")
    doc = series_doc if series_doc is not None else json.loads(SERIES_PATH.read_text(encoding="utf-8"))
    blk = doc.get("dpw_path")
    if not blk:
        raise LabRefused("--prelook refused: data/fa_dpw_series.json carries no dpw_path block")
    truth = {int(k): float(v) for k, v in blk["truth"]["by_winter"].items()}
    served = {int(k): float(v) for k, v in blk["served_level"]["by_winter"].items()}
    n = int(blk["clock"]["last_realized_winter"])
    sha = dp.sha256_of({k: blk["truth"][k] for k in
                        ("estimator", "by_winter", "tau_by_winter", "term_mix_index")})
    if sha != blk["truth"].get("sha256"):
        raise LabRefused("--prelook refused: the truth sha256 does not recompute")
    i5 = parity_records(truth)
    switches = blk["enrichment"].get("projection_switches") or {}
    sw_ok = all(v.get("raw") is None or v.get("raw") == v.get("resolved") or
                str(v.get("raw")) == str(v.get("resolved")) for v in switches.values())
    stub = {"verdict": REGISTERED, "blind_status": "NOT_ARMED",
            "generated_at": today or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "doc": GATE_DOC_REL, "truth_sha256": sha,
            "I3": {"p20": blk["enrichment"].get("p20"),
                   "disc_war_per_deal_note": "class 2021, 2022 and 2023 discounted WAR per deal on the pinned "
                                             "block (series properties, not errors)",
                   "scheduled_share_by_winter": blk["truth"].get("scheduled_share_by_winter")},
            "I5": {**i5, "projection_switches": switches, "switches_pass": sw_ok},
            "stamps": {"estimator": blk["truth"]["estimator"], "enrichment": blk["enrichment"],
                       "basis_id": blk.get("basis_id")},
            "g_I_N": {"truth": dp.g_destale(truth, n), "served_basis": dp.g_destale(served, n),
                      "N": n}}
    chk = blindness(n, reader=reader, deal_count=deal_count, scrape_at=scrape_at)
    stub["blind_check_origin"] = {"origin": n, **chk}
    if chk["blind"]:
        rows = dp.forecast_rows(truth, n, made_at=stub["generated_at"], truth_sha256=sha,
                                basis_id=blk.get("basis_id"), g_ref=float(blk["discount"]["g_ref"]),
                                blind_check=chk)
        stub["ledger"] = append_ledger(rows, ledger_path)
    write_block(stub, eval_path)
    return stub


def parity_records(truth: dict) -> dict:
    """I-5 on the pinned block, forecasts only: carry_destale against
    fa_market._destale_rate and trend_line against fa_market._fit_log_trend at
    every development origin, to 1e-12 relative."""
    import fa_market as fm
    rows = []
    ok = True
    for o in ORIGINS:
        if o not in truth or len(dp.available(truth, o)) < dp.MIN_WINTERS:
            continue
        prior = {w: v for w, v in truth.items() if w <= o}
        g_fm = fm._destale_rate(prior, o + 1)
        g_dp = dp.g_destale(truth, o)
        t_fm = fm._fit_log_trend(prior, with_cbt=False)(o + 1)
        t_dp = dp.forecast("trend_line", truth, o, 1)
        good = (abs(g_fm - g_dp) <= 1e-12 * max(1.0, abs(g_fm))
                and abs(t_fm - t_dp) <= 1e-12 * abs(t_fm))
        ok = ok and good
        rows.append({"origin": o, "g_destale_fa_market": g_fm, "g_destale_dpw_path": g_dp,
                     "trend_fa_market": t_fm, "trend_dpw_path": t_dp, "parity": good})
    return {"parity_rows": rows, "parity_pass": ok}


# ---------------------------------------------------------------------------
# --real, the look
# ---------------------------------------------------------------------------

def preflight_real(cwd: Path | None = None) -> dict:
    """Refuses unless exactly one amendment commit exists and the block AT that
    commit reads REGISTERED; returns what the look reads from that commit."""
    commits = amendment_commits(cwd=cwd)
    if len(commits) != 1:
        raise LabRefused(f"--real refused: {len(commits)} amendment commits (exactly one is required)")
    c = commits[0]
    eval_rel = repo_rel(EVAL_PATH)
    try:
        blk = json.loads(show_at(c, eval_rel, cwd=cwd)).get(BLOCK_KEY)
    except (subprocess.CalledProcessError, ValueError):
        blk = None
    if not blk or blk.get("verdict") != REGISTERED:
        raise LabRefused("--real refused: the dpw_path_gate block at the amendment commit is not REGISTERED")
    series_doc = json.loads(show_at(c, repo_rel(SERIES_PATH), cwd=cwd))
    pinned = series_doc.get("dpw_path") or {}
    truth_obj = pinned.get("truth") or {}
    sha = dp.sha256_of({k: truth_obj.get(k) for k in
                        ("estimator", "by_winter", "tau_by_winter", "term_mix_index")})
    if sha != blk.get("truth_sha256"):
        raise LabRefused("--real refused (I-2): the committed truth sha256 differs from the recorded one")
    return {"commit": c, "stub": blk, "series_doc": series_doc, "truth_sha256": sha,
            "owner_at_amendment": owner_record_at(c, cwd=cwd)}


def run_look(truth: dict, *, n_draws: int = N_DRAWS, b_plant: int = B_PLANT_BOOT, search=plant_search,
             log=None) -> dict:
    """The look's computation on a truth series, in the registered order:
    power block FIRST, then the cells of A and the verdict, then the
    descriptive arms and BAND_COVERAGE. Returns the result part of the block."""
    log = log if log is not None else []
    ctx = build_context(truth)
    power = power_block(ctx, n_draws=n_draws, b_plant=b_plant, search=search, log=log)
    log.append("cells")
    cell = cells(ctx, power["c"])
    verdict = decide(cell, power)
    log.append("descriptive")
    desc = descriptive_arms(ctx)
    cov = band_coverage(ctx)
    flags = {"INCUMBENT_BELOW_FLOOR": power["INCUMBENT_BELOW_FLOOR"], "BAND_COVERAGE": cov}
    blind = dp.blind_status(verdict["verdict"], None, [])
    return {"ctx": ctx, "power": power, "cells": cell, "verdict_detail": verdict,
            "verdict": verdict["verdict"], "blind_status": blind["status"], "descriptive": desc,
            "flags": flags, "sentence": sentence(verdict, cell, power),
            "floor_sentence": floor_sentence(power)}


def real(cwd: Path | None = None) -> dict:
    """THE LOOK. Run once, by F-C, on the registration's clock."""
    md5_start = md5_file(SERIES_PATH)
    pre = preflight_real(cwd=cwd)
    blobs = blob_shas(cwd=cwd)
    check_blobs(blobs)
    z = step_z_entry()
    pinned = pre["series_doc"]["dpw_path"]
    if z is None or pinned["enrichment"].get("war_provider") != "fwar":
        verdict = "NOT_AVAILABLE" if z is None else "VOID"
        raise LabRefused(f"--real: I-1 not met ({verdict}); the look slips")
    today = date.today().isoformat()
    amend_day = git(["show", "-s", "--format=%cs", pre["commit"]], cwd=cwd).strip()
    earliest = max(date.fromisoformat(z).toordinal() + 7, date.fromisoformat(amend_day).toordinal() + 1)
    if date.today().toordinal() < earliest or today in OTHER_LOOK_DAYS:
        raise LabRefused("--real refused (I-8): not on the registration's clock")
    truth = {int(k): float(v) for k, v in pinned["truth"]["by_winter"].items()}
    t0 = time.time()
    res = run_look(truth)
    with tempfile.TemporaryDirectory() as td:
        copy = Path(td) / "fa_dpw_series_amendment.json"
        copy.write_text(json.dumps(pre["series_doc"]), encoding="utf-8")
        X = exposure_by_horizon(ROOT / "data", copy)
    det = res["power"]["detection"]
    tm_rho = min(det, key=lambda k: det[k]["detection_full"])
    du = delta_usd(res["ctx"], taper_fold(X["X"]), det[tm_rho]["type_m"])
    ledger = load_ledger()
    block = {**pre["stub"], "verdict": res["verdict"], "blind_status": res["blind_status"],
             "look": {"date": today, "amendment_commit": pre["commit"], "wall_time_s": time.time() - t0},
             "integrity": {"I1": {"step_z": z, "war_provider": pinned["enrichment"].get("war_provider")},
                           "I2": {"truth_sha256": pre["truth_sha256"]}, "I7": blobs,
                           "I6": check_md5_unchanged(md5_start)},
             "owner_at_amendment": pre["owner_at_amendment"],
             "ledger": dp.chain_head(ledger.get("rows") or []),
             "power": _jsonable(res["power"]), "cells": _jsonable(res["cells"]),
             "verdict_detail": res["verdict_detail"], "descriptive": res["descriptive"],
             "flags": res["flags"], "DeltaUSD": {**du, "exposure": X},
             "sentence": res["sentence"], "floor_sentence": res["floor_sentence"],
             "unconditional": UNCONDITIONAL_SENTENCE,
             "seeds": {"seed": SEED, "B_boot": B_BOOT, "B_plant": B_PLANT_BOOT, "draws": N_DRAWS}}
    write_block(block)
    for k in ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"):
        print(CRITERIA[k])
        print("    ->", "PASS" if res["cells"]["criteria"][k]["pass"] else "FAIL")
    print("verdict:", res["verdict"])
    return block


def owner_after_look(eval_path: Path = EVAL_PATH, owner_path: Path = OWNER_PATH) -> dict:
    """Copy an OD-7 zero_if_floor row from the live owner file into
    owner_after_look; refuses unless INCUMBENT_BELOW_FLOOR is true."""
    blk = read_block(eval_path)
    if not blk or not ((blk.get("flags") or {}).get("INCUMBENT_BELOW_FLOOR") is True):
        raise LabRefused("--owner-after-look refused: INCUMBENT_BELOW_FLOOR is not raised")
    doc = json.loads(Path(owner_path).read_text(encoding="utf-8"))
    row = dp.last_answer(doc, "OD-7")
    if not row or row["option"] != "zero_if_floor":
        raise LabRefused("--owner-after-look refused: the last OD-7 row is not zero_if_floor")
    rows = dp.validate_owner_doc(doc)
    head = dp.chain_head(rows)
    blk["owner_after_look"] = {"OD-7": {"option": row["option"], "date": row.get("date"),
                                        "row_sha256": dp.sha256_of(row)},
                               "chain_head_sha256": head["head_sha256"], "row_count": head["row_count"]}
    write_block(blk, eval_path)
    return blk


def _jsonable(obj):
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items() if k != "ctx"}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    return obj


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--prelook", action="store_true")
    g.add_argument("--real", action="store_true")
    g.add_argument("--owner-after-look", action="store_true")
    ap.add_argument("--scrape-at", default=None, help="--prelook: the same-day class scrape time")
    args = ap.parse_args(argv)
    if args.prelook:
        if not args.scrape_at:
            raise LabRefused("--prelook needs --scrape-at (the same-day fa_pipeline.refresh_current_class run)")
        print(json.dumps(_jsonable(prelook(scrape_at=args.scrape_at)), indent=1)[:4000])
        return 0
    if args.real:
        real()
        return 0
    if args.owner_after_look:
        owner_after_look()
        return 0
    print("synthetic mode: the lab's functions are exercised by test_dpw_path_lab.py; "
          "--prelook, --real and --owner-after-look are the registered runs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
