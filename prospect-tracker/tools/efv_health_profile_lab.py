# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""HEALTH PROFILE as an outcome-grounded eFV driver (owner ask, 2026-09-04).

> "build a predictive machine-learning based driver submodel which will build a player's
> health profile based on their IL history, stints, and injury specifications and weight
> this to boost (durability) or drop (fragility) a prospect's eFV grade. This will replace
> our current system of just penalizing players for being currently on IL ... built by
> testing injury thresholds against bust probability / MLB health outcomes. Ex. what
> correlation is there between Tommy John and a pitcher's MLB production? What correlation
> is there between players who spent a cumulative number of X days on the Injured List
> during their time as a prospect and their eventual outcomes?"

READ THE EXPOSURE SECTION FIRST. The idea is sound and the arithmetic is real, but the
naive reading of it is BACKWARDS, and the reason is not statistical subtlety.

THE ARCHIVE WAS THE FIRST PROBLEM AND IS NOW FIXED. `il_history` is not a history: 1,415 of
its 1,662 placements are 2026 and it was first populated 2026-06-06. The usable source is
`player_transactions`, which carries placements AND activations so cumulative days are
computable. It used to start in 2019 because `stats.TRANSACTIONS_LOOKBACK_SEASONS` was 7,
not because the endpoint stopped there. `tools/backfill_player_transactions.py` widened the
stored window and recovered 16,678 pre-2019 events across 1,684 players, lifting
pre-decision coverage from 33.8 percent to about 60 percent of each side.

THE EXPOSURE CONFOUND IS THE REAL PROBLEM AND IT IS SEVERE. A player cannot be placed on an
injured list unless he is on a roster, so "no IL record" conflates a healthy prospect with
one who never had enough rostered time to be placed on one. On the full pool, 576 of 1,127
observable hitters have no record at all and they BUST 83.7 percent of the time against
68.6 percent for those with a record. Read raw, the data says injuries are GOOD.

That is also why the POOL matters more here than anywhere else in this program. Scoring
debuted rows only conditions on the outcome an injury is most likely to prevent, and it
flips the sign: hitter `il_stints` reads -0.084 on debuted rows and +0.014 on the full pool.
This lab therefore reports BOTH pools and an exposure-controlled correlation beside them,
and the controlled number is the one to read.

WHAT IS MEASURED
  Part 1  descriptive: IL burden buckets against mean first-6yr WAR, star rate and bust
          rate, on BOTH pools.
  Part 2  exposure-controlled correlations, partialling out the scouting grade and the best
          available proxies for rostered time. THIS IS THE ONE THAT ANSWERS THE ASK.
  Part 3  the health SUBMODEL: a forward-chained out-of-fold ridge over the burden features,
          standardised within decision year, added to the main model as one column.
  Part 4  gated: every candidate including the submodel, scored as an incremental
          forward-chained margin with an E_cond floor, a permutation null and Holm across
          the family.

INJURY SPECIFICATION IS NOT AVAILABLE FOR PROSPECTS and no model can recover it. Minor
league placements name the injury in 3.2 percent of cases (319 of 10,039) against 54.5
percent in the majors, so the Tommy John question cannot be answered on the prospect window:
it resolves to n=1 before the archive fix and stays too thin after it. The category flags
are kept so the artifact shows their support rather than implying they were tested.

NOTHING HERE REPLACES THE IL PENALTY BY ITSELF. Replacing it is a serving-path decision and
the serving path sees today's board, where current IL status is densely covered. What this
lab can say is what the OUTCOMES say about the signal the penalty uses, and they say it is
side-asymmetric.

Run:
    python tools/efv_health_profile_lab.py
    python tools/efv_health_profile_lab.py --describe-only
"""

from __future__ import annotations

import argparse
import collections
import json
import os
import re
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_model as E                       # noqa: E402  READ ONLY

sys.path.insert(0, str(ROOT / "tools"))
import efv_mde_lab as M                     # noqa: E402

OUT_PATH = ROOT / "data" / "xfv_health_profile_eval.json"
SEED = 20260807
SIDES = ("hit", "pit")

STAR_WAR = 10.0
BUST_WAR = 0.5

#: The archive's first RELIABLE year, measured rather than assumed (2026-09-04, after
#: tools/backfill_player_transactions.py widened the stored window from 2019 back to 2011).
#: The test is the injured-list rate per ACTIVE player-year, where a player-year counts only
#: if that player has some transaction that year, so the denominator is "tracked and
#: playing" rather than "exists":
#:
#:   2013  6.4%   2014 13.6%   2015 16.8%   2016 15.9%   2017 21.9%   2018 23.7%
#:   2019 24.2%   2020  7.8%   2021 28.2%   2022 26.5%   2023 26.8%   2024 27.2%
#:
#: The rate plateaus around 27 percent from 2017 on and is materially depressed before it,
#: so a missing stint before 2017 is more likely a missing RECORD than a healthy player.
#: 2020 is the COVID season and is genuinely low, not thin.
ARCHIVE_FIRST_YEAR = 2017

#: A row is observable when at least this share of its pre-decision window falls inside the
#: reliable era. Absence of a stint is only evidence of health where a stint would have been
#: recorded, and a prospect's window spans several years, so a single cutoff on the decision
#: year alone would admit players whose formative seasons predate the archive.
WINDOW_COVERED_MIN = 0.5

#: The window this lab treats as "his time as a prospect", ending at the decision date.
PROSPECT_WINDOW_YEARS = 5

IL_RE = re.compile(r"injured list|disabled list", re.I)
PLACE_RE = re.compile(r"\bplaced\b|\btransferred\b", re.I)
ACT_RE = re.compile(r"activated|reinstated|returned", re.I)
TYPE_RE = re.compile(r"on the ([\w-]+?)[- ]?day injured list|on the (full-season) injured list", re.I)
TJ_RE = re.compile(r"tommy john|ucl", re.I)
CATEGORIES = ("elbow", "shoulder", "back", "hamstring", "oblique", "knee",
              "wrist", "forearm", "lat", "hip")


def _d(s: str):
    try:
        y, m, dd = str(s)[:10].split("-")
        return date(int(y), int(m), int(dd))
    except Exception:
        return None


def il_events() -> dict[str, list[dict]]:
    """{player_key: [{date, kind, il_type, text}]} from player_transactions, sorted."""
    con = sqlite3.connect(f"file:{ROOT / 'prospects.db'}?mode=ro", uri=True)
    out: dict[str, list[dict]] = collections.defaultdict(list)
    for pk, payload in con.execute("select player_key, payload_json from player_transactions"):
        try:
            rows = json.loads(payload)
        except Exception:
            continue
        for t in rows:
            txt = t.get("description") or ""
            if not IL_RE.search(txt):
                continue
            dt = _d(t.get("date"))
            if dt is None:
                continue
            if PLACE_RE.search(txt):
                kind = "place"
            elif ACT_RE.search(txt):
                kind = "activate"
            else:
                continue
            m = TYPE_RE.search(txt)
            il_type = (m.group(1) or m.group(2)) if m else None
            out[pk].append({"date": dt, "kind": kind, "il_type": il_type, "text": txt})
    for pk in out:
        out[pk].sort(key=lambda e: e["date"])
    con.close()
    return dict(out)


def profile(events: list[dict], cutoff, first_seen=None) -> dict:
    """The health profile as of the decision date. Days pair a placement with the next
    activation; a stint still open at the cutoff is censored AT the cutoff, never beyond,
    so the number can never see past the decision."""
    p = {"il_stints": 0.0, "il_days": 0.0, "il_60day": 0.0, "il_fullseason": 0.0,
         "il_max_stint_days": 0.0, "tj": 0.0}
    for c in CATEGORIES:
        p[f"cat_{c}"] = 0.0
    open_at = None
    for e in events:
        if e["date"] >= cutoff:
            break
        if e["kind"] == "place":
            if open_at is None:
                open_at = e["date"]
            p["il_stints"] += 1
            t = (e["il_type"] or "").lower()
            if t.startswith("60"):
                p["il_60day"] += 1
            if t.startswith("full"):
                p["il_fullseason"] += 1
            if TJ_RE.search(e["text"]):
                p["tj"] = 1.0
            for c in CATEGORIES:
                if re.search(rf"\b{c}", e["text"], re.I):
                    p[f"cat_{c}"] = 1.0
        elif e["kind"] == "activate" and open_at is not None:
            days = (e["date"] - open_at).days
            if days >= 0:
                p["il_days"] += days
                p["il_max_stint_days"] = max(p["il_max_stint_days"], days)
            open_at = None
    if open_at is not None:                      # still on the IL at the decision date
        days = (cutoff - open_at).days
        if days > 0:
            p["il_days"] += days
            p["il_max_stint_days"] = max(p["il_max_stint_days"], days)
        p["il_open_at_decision"] = 1.0
    else:
        p["il_open_at_decision"] = 0.0
    # OBSERVABILITY IS A PROPERTY OF THE ARCHIVE, NOT OF THE PLAYER. Keying this off
    # "did this player have an IL event" would keep only injured players and drop every
    # healthy one, which destroys the contrast the whole lab exists to measure and would
    # have made `durable_zero_il` unmeasurable by construction.
    #
    # The rule is the SHARE OF THE PROSPECT WINDOW that falls in the reliable era, not a
    # cutoff on the decision year. A player deciding in 2019 whose formative seasons were
    # 2015-2018 is only half observed, and reading his clean sheet as durability would be
    # reading the archive's gap as the player's health.
    yrs = [cutoff.year - i for i in range(PROSPECT_WINDOW_YEARS)]
    covered = sum(1 for y in yrs if y >= ARCHIVE_FIRST_YEAR)
    share = covered / len(yrs)
    p["window_covered_share"] = round(share, 3)
    p["il_observable"] = 1.0 if share >= WINDOW_COVERED_MIN else 0.0
    return p


def build_pool(side: str, ev: dict, full_pool: bool = False) -> dict:
    """The scored pool. `full_pool` keeps the BUST rows.

    THE DEFAULT IS WRONG FOR THIS QUESTION AND THE FULL POOL IS WHY IT EXISTS. Every other
    lane in this program scores debuted rows, which is right when the question is "how much
    WAR did he produce". It is wrong here: an injury's most important consequence is that a
    prospect never reaches the majors at all, and a debuted-only pool conditions on exactly
    the outcome the health signal is supposed to predict. A player who was hurt and washed
    out is in the bust pool carrying a label of 0, and dropping him makes injuries look
    survivable by construction. The full pool is the honest population for the ask, and the
    debuted pool is kept beside it because the two answer different questions.
    """
    from efv_dataset import matrix_path
    raw = json.loads(matrix_path(side).read_text(encoding="utf-8"))
    deb = raw if full_pool else [r for r in raw if r["kind"] == "debuted"]
    prep = E._prep(deb, "target_censored", side)
    keys, _m = E._feature_spec(side)
    by_key = {r["player_key"]: r for r in raw}
    profs = []
    for r in prep:
        src = by_key.get(r.get("player_key")) or {}
        cut = _d(src.get("cutoff")) or date(int(r["decision_year"]), 7, 1)
        e = ev.get(r.get("player_key")) or []
        first = e[0]["date"] if e else None
        profs.append(profile(e, cut, first))
    return {
        "side": side, "keys": list(keys),
        "X": np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float),
        "y": np.array([r["target"] for r in prep], dtype=float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
        "fv": np.array([r["fv"] for r in prep], dtype=float),
        "dy": np.array([r["decision_year"] for r in prep], dtype=int),
        "profs": profs, "n": len(prep), "lam": E.blend_lambda(side),
    }


def observable_mask(P: dict) -> np.ndarray:
    return np.array([p["il_observable"] > 0 for p in P["profs"]], dtype=bool)


def candidates(side: str) -> list[dict]:
    C = []

    def add(name, fn, why):
        C.append({"name": name, "fn": fn, "why": why})

    add("il_stints", lambda p: p["il_stints"], "count of IL placements before the decision")
    add("il_days", lambda p: p["il_days"], "cumulative IL days before the decision")
    add("il_max_stint_days", lambda p: p["il_max_stint_days"], "longest single stint")
    add("il_60day", lambda p: p["il_60day"], "count of 60-day placements")
    add("il_fullseason", lambda p: p["il_fullseason"], "count of full-season placements")
    add("il_open_at_decision", lambda p: p["il_open_at_decision"],
        "on the IL at the decision date: the INCUMBENT signal, included so the new "
        "features are measured against it rather than beside it")
    for t in (30, 60, 90, 120, 180):
        add(f"il_days_ge_{t}", (lambda p, t=t: 1.0 if p["il_days"] >= t else 0.0),
            f"{t}+ cumulative IL days as a prospect")
    for t in (2, 3, 4):
        add(f"il_stints_ge_{t}", (lambda p, t=t: 1.0 if p["il_stints"] >= t else 0.0),
            f"{t}+ separate IL stints as a prospect")
    add("durable_zero_il", lambda p: 1.0 if p["il_stints"] == 0 else 0.0,
        "NO IL placement in an observable window: the durability side of the ask")
    if side == "pit":
        add("tommy_john", lambda p: p["tj"], "a Tommy John or UCL event before the decision")
    for c in CATEGORIES:
        add(f"cat_{c}", (lambda p, c=c: p[f"cat_{c}"]), f"an IL event naming the {c}")
    return C


#: The burden features the health SUBMODEL sees. Deliberately excludes the injury-category
#: flags: minor-league placements name the injury only 3.2 percent of the time (319 of
#: 10,039 measured 2026-09-04) against 54.5 percent in the majors, so a category feature on
#: a prospect window is almost all zeros and the one it is not would be noise. It also
#: excludes il_open_at_decision, which is the INCUMBENT signal and is scored separately so
#: the submodel can be compared against it rather than absorbing it.
HEALTH_KEYS = ("il_stints", "il_days", "il_max_stint_days", "il_60day", "il_fullseason")


def oof_health_index(P: dict, mask: np.ndarray) -> np.ndarray:
    """A forward-chained out-of-fold health score, one number per observable row.

    This is the "health profile submodel" the ask describes, built the only way a driver
    may be built here: every row's score comes from a ridge fitted on STRICTLY EARLIER
    decision years, so no row contributes to its own score and the score can be handed to
    the main model as a feature for train and test rows alike. A score fitted in-sample
    would grade the burden features against outcomes they helped choose, which is the
    stacking mistake that makes a submodel look like a driver.

    Sign convention: the ridge predicts WAR, so a HIGH score is a durable profile and a LOW
    score is a fragile one. Boost and drop are the same coefficient with opposite signs, not
    two rules.
    """
    prof = [p for p, m in zip(P["profs"], mask) if m]
    H = np.array([[float(p.get(k, 0.0)) for k in HEALTH_KEYS] for p in prof], dtype=float)
    y, w, dy = P["y"][mask], P["w"][mask], P["dy"][mask]
    out = np.zeros(len(y), dtype=float)
    for yr in sorted(set(int(v) for v in dy)):
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) == 0:
            continue
        if len(tr) < 40:
            out[te] = np.nan          # no prior data: no score, filled below
            continue
        m = M.ridge_fit(H[tr], y[tr], w[tr])
        if m is None:
            out[te] = np.nan
            continue
        out[te] = M.ridge_pred(m, H[te])
    # STANDARDISED WITHIN DECISION YEAR, and this is load-bearing rather than cosmetic.
    # The raw score is a WAR-scale prediction whose LEVEL drifts by fold: measured on the
    # hitter side the per-fold means ran 4.08, 5.03, 4.36, 3.81, 4.06, 3.63 while the
    # within-fold sd was 0.00 to 1.36, so between-fold movement was as large as the signal
    # and the feature encoded COHORT YEAR at least as much as health. The first fold is
    # worse than that: it has no prior data at all, so every row in it took one identical
    # filled value, which is a constant masquerading as a measurement. Centring inside the
    # year keeps only the thing the ask actually wants, which is whether this player is
    # more or less durable than his own cohort, and it sends a fold with no information to
    # exactly zero instead of to a number.
    fin = np.isfinite(out)
    out[~fin] = np.nan
    for yr in sorted(set(int(v) for v in dy)):
        te = np.flatnonzero(dy == yr)
        v = out[te]
        ok = np.isfinite(v)
        if ok.sum() < 2 or not np.isfinite(v[ok].std()) or v[ok].std() <= 0:
            out[te] = 0.0
            continue
        z = np.zeros(len(v))
        z[ok] = (v[ok] - v[ok].mean()) / v[ok].std()
        out[te] = z
    return out


#: Columns partialled out of the exposure-controlled read. `fv` because eFV already carries
#: the scouting grade, and the rest because they are the best available proxies for HOW MUCH
#: ROSTERED TIME a prospect had, which is the confound that makes an injury record look good.
EXPOSURE_CONTROLS = ("fv", "n_milb_seasons", "level_rank", "seasons_at_level", "age")


def _resid(y: np.ndarray, Z: np.ndarray) -> np.ndarray:
    A = np.column_stack([np.ones(len(y)), Z]) if Z.size else np.ones((len(y), 1))
    beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    return y - A @ beta


def exposure_controlled(P: dict, cands: list[dict], mask: np.ndarray) -> dict:
    """The burden-to-outcome correlation with rostered exposure partialled out.

    THIS IS THE CONTROL THE WHOLE LANE TURNS ON. You cannot be placed on an injured list
    unless you are on a roster, so "no IL record" conflates a healthy player with one who
    never had enough exposure to be placed on one. Measured on the full pool: 576 of 1,127
    observable hitters have no record at all and they BUST 83.7 percent of the time against
    68.6 percent for those with a record, which reverses the debuted-only reading entirely.
    An uncontrolled correlation here measures roster tenure wearing an injury label.
    """
    keys = P["keys"]
    cols = [keys.index(k) for k in EXPOSURE_CONTROLS if k in keys]
    X = P["X"][mask]
    Z = X[:, cols] if cols else np.empty((int(mask.sum()), 0))
    y = _resid(P["y"][mask], Z)
    w = P["w"][mask]
    prof = [p for p, m in zip(P["profs"], mask) if m]
    out = {"controls": [k for k in EXPOSURE_CONTROLS if k in keys], "rows": []}
    for c in cands:
        v = np.array([c["fn"](p) for p in prof], dtype=float)
        if np.allclose(v, v[0]) or (v > 0).sum() < 20:
            continue
        out["rows"].append({
            "name": c["name"],
            "support": int((v > 0).sum()),
            "raw_rho": round(float(M.wrho(v, P["y"][mask], w)), 4),
            "exposure_controlled_rho": round(float(M.wrho(_resid(v, Z), y, w)), 4),
        })
    return out


def penalty_verdict(P: dict, mask: np.ndarray, b: int = 4000) -> dict:
    """Does the SHIPPED injury penalty point the right way, per side?

    `efv_score._injury_factor` is a multiplicative haircut on eFV WAR, gated on `il_on` and
    deepened by trailing days and stints. This tests the rule it implements rather than the
    features around it: conditional on the scouting grade, age and rostered exposure, does
    being ON THE INJURED LIST at the decision point predict a LOWER outcome, and do the
    deepening terms point the same way?

    The bar is the one the owner set: a penalty stays only if it is PROVEN, so the interval
    must exclude zero ON THE NEGATIVE SIDE. Positive or straddling zero means the haircut is
    taxing something the outcomes do not punish, and an unproven penalty is not a neutral
    default, it is a live subtraction from every affected player's grade, rank and dollars.
    """
    keys = P["keys"]
    cols = [keys.index(k) for k in EXPOSURE_CONTROLS if k in keys]
    X = P["X"][mask]
    Z = X[:, cols] if cols else np.empty((int(mask.sum()), 0))
    y_raw = P["y"][mask]
    w = P["w"][mask]
    y = _resid(y_raw, Z)
    prof = [p for p, m in zip(P["profs"], mask) if m]
    rng = np.random.default_rng(SEED)
    out = {"controls": [k for k in EXPOSURE_CONTROLS if k in keys], "B": b, "terms": {}}

    def leg(name, v, sub=None):
        idx = np.arange(len(v)) if sub is None else np.flatnonzero(sub)
        if len(idx) < 30 or np.allclose(v[idx], v[idx][0]):
            return {"n": int(len(idx)), "verdict": "TOO THIN TO READ"}
        vr = _resid(v[idx], Z[idx]) if Z.size else v[idx] - v[idx].mean()
        yr = _resid(y_raw[idx], Z[idx]) if Z.size else y_raw[idx] - y_raw[idx].mean()
        point = float(M.wrho(vr, yr, w[idx]))
        draws = []
        for _ in range(b):
            s = rng.integers(0, len(idx), len(idx))
            val = M.wrho(vr[s], yr[s], w[idx][s])
            if np.isfinite(val):
                draws.append(float(val))
        a = np.array(draws)
        lo, hi = (float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))) if len(a) else (None, None)
        if lo is None:
            verdict = "TOO THIN TO READ"
        elif hi < 0:
            verdict = "PENALTY SUPPORTED (interval below zero)"
        elif lo > 0:
            verdict = "PENALTY CONTRAINDICATED (interval above zero)"
        else:
            verdict = "NOT PROVEN (interval spans zero)"
        return {"n": int(len(idx)), "rho": round(point, 4),
                "ci95": [round(lo, 4), round(hi, 4)], "verdict": verdict}

    on_il = np.array([p["il_open_at_decision"] for p in prof], dtype=float)
    out["terms"]["il_on_gate"] = leg("il_on", on_il)
    # the deepening terms, read ONLY on the players the gate would actually tax
    sub = on_il > 0.5
    for k in ("il_days", "il_stints", "il_max_stint_days"):
        v = np.array([p[k] for p in prof], dtype=float)
        out["terms"][f"{k}_given_on_il"] = leg(k, v, sub=sub)
    verdicts = [t.get("verdict", "") for t in out["terms"].values()]
    out["side_verdict"] = (
        "SUPPORTED" if any(v.startswith("PENALTY SUPPORTED") for v in verdicts)
        else ("CONTRAINDICATED" if any(v.startswith("PENALTY CONTRA") for v in verdicts)
              else "NOT PROVEN"))
    return out


def describe(P: dict, cands: list[dict], mask: np.ndarray) -> dict:
    y, prof = P["y"][mask], [p for p, m in zip(P["profs"], mask) if m]
    pool_star = float((y >= STAR_WAR).mean()) if len(y) else 0.0
    rows = []
    for c in cands:
        v = np.array([c["fn"](p) for p in prof], dtype=float)
        binary = set(np.unique(v)) <= {0.0, 1.0}
        if binary:
            m = v > 0.5
            n_in = int(m.sum())
            if n_in < 10 or n_in == len(v):
                rows.append({"name": c["name"], "why": c["why"], "support": n_in,
                             "note": "too thin to read" if n_in < 10 else "no contrast"})
                continue
            yi, yo = y[m], y[~m]
            rows.append({
                "name": c["name"], "why": c["why"], "support": n_in,
                "support_share": round(n_in / len(y), 4),
                "mean_label_in": round(float(yi.mean()), 3),
                "mean_label_out": round(float(yo.mean()), 3),
                "star_rate_in": round(float((yi >= STAR_WAR).mean()), 4),
                "star_rate_out": round(float((yo >= STAR_WAR).mean()), 4),
                "bust_rate_in": round(float((yi <= BUST_WAR).mean()), 4),
                "bust_rate_out": round(float((yo <= BUST_WAR).mean()), 4),
                "star_lift_vs_pool": (round(float((yi >= STAR_WAR).mean()) / pool_star, 3)
                                      if pool_star > 0 else None),
            })
        else:
            rows.append({"name": c["name"], "why": c["why"], "support": int((v > 0).sum()),
                         "spearman_with_label": round(float(M.wrho(v, y, P["w"][mask])), 5),
                         "mean": round(float(v.mean()), 2),
                         "p90": round(float(np.percentile(v, 90)), 2)})
    return {"n": int(mask.sum()), "pool_star_rate": round(pool_star, 4), "rows": rows}


def chain(P, extra=None, sel=None, years=None, mask=None):
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = P["lam"]
    X = P["X"] if extra is None else np.column_stack([P["X"], extra])
    y, w, fv, dy = P["y"], P["w"], P["fv"], P["dy"]
    if mask is not None:
        X, y, w, fv, dy = X[mask], y[mask], w[mask], fv[mask], dy[mask]
    if sel is None:
        sel = np.arange(len(y))
    X, y, w, fv, dy = X[sel], y[sel], w[sel], fv[sel], dy[sel]
    YR, C, B, T, W = [], [], [], [], []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        o = M.ols_fit(fv[tr], y[tr])
        rg = M.ridge_fit(X[tr], y[tr], w[tr])
        if o is None or rg is None:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv[te])
        mod = M.ridge_pred(rg, X[te])
        YR.append(np.full(len(te), yr)); C.append(cons)
        B.append((1 - lam) * cons + lam * mod); T.append(y[te]); W.append(w[te])
    if not B:
        return None
    return tuple(np.concatenate(a) for a in (YR, C, B, T, W))


def margin(parts, sel=None):
    if parts is None:
        return None
    _yr, cons, blend, tgt, w = parts
    if sel is not None:
        cons, blend, tgt, w = cons[sel], blend[sel], tgt[sel], w[sel]
    return float(M.wrho(blend, tgt, w)) - float(M.wrho(cons, tgt, w))


def holm(p):
    items = sorted(p.items(), key=lambda kv: kv[1])
    m, out, run = len(items), {}, 0.0
    for i, (k, v) in enumerate(items):
        run = max(run, min(1.0, (m - i) * v))
        out[k] = round(run, 5)
    return out


def gate(P, cands, mask, b_cond, b_perm):
    rng = np.random.default_rng(SEED)
    base_parts = chain(P, mask=mask)
    if base_parts is None:
        return {"skipped": "no fold survived on the observable cohort"}
    base = margin(base_parts)
    n_te = len(base_parts[3])
    prof = [p for p, m in zip(P["profs"], mask) if m]
    # THE SUBMODEL IS THE HEADLINE CANDIDATE and it goes in the same family as the singles,
    # not beside it: a composite scored against a Holm family it is not part of would be
    # the search getting a free pass on the multiplicity its own breadth created.
    idx = oof_health_index(P, mask)
    cands = [{"name": "health_index_oof",
              "fn": None, "precomputed": idx,
              "why": "the forward-chained stacked health submodel over "
                     + ", ".join(HEALTH_KEYS)}] + list(cands)
    res, pv = [], {}
    for i, c in enumerate(cands):
        v = (c["precomputed"] if c.get("precomputed") is not None
             else np.array([c["fn"](p) for p in prof], dtype=float))
        if np.allclose(v, v[0]):
            res.append({"name": c["name"], "skipped": "constant on this cohort"})
            continue
        sd = v.std()
        vz = ((v - v.mean()) / sd if sd > 0 else v)
        full = np.zeros(P["n"]); full[np.flatnonzero(mask)] = vz
        parts = chain(P, extra=full.reshape(-1, 1), mask=mask)
        m_ = margin(parts)
        if m_ is None:
            res.append({"name": c["name"], "skipped": "no fold survived"})
            continue
        delta = m_ - base
        cond = []
        for _ in range(b_cond):
            s = rng.integers(0, n_te, n_te)
            a_, b_ = margin(parts, s), margin(base_parts, s)
            if a_ is not None and b_ is not None:
                cond.append(a_ - b_)
        cond = np.array([x for x in cond if np.isfinite(x)], dtype=float)
        null = []
        for j in range(b_perm):
            r2 = np.random.default_rng(SEED + 31337 * (i + 1) + j)
            pv2 = vz[r2.permutation(len(vz))]
            f2 = np.zeros(P["n"]); f2[np.flatnonzero(mask)] = pv2
            mm = margin(chain(P, extra=f2.reshape(-1, 1), mask=mask))
            if mm is not None:
                null.append(mm - base)
        null = np.array(null, dtype=float)
        p = float((np.abs(null) >= abs(delta)).mean()) if len(null) else 1.0
        pv[c["name"]] = p
        floor = 1.96 * float(cond.std(ddof=1)) if len(cond) > 1 else None
        res.append({
            "name": c["name"], "why": c["why"],
            "margin_base": round(base, 5), "margin_with": round(m_, 5),
            "delta": round(delta, 5),
            "E_cond_floor_mde95": round(floor, 5) if floor else None,
            "clears_own_floor": bool(floor and abs(delta) >= floor),
            "permutation_p": round(p, 4), "permutation_B": int(len(null)),
        })
    adj = holm(pv)
    for r in res:
        if r.get("name") in adj:
            r["holm_p"] = adj[r["name"]]
            r["SHIPPABLE"] = bool(r.get("clears_own_floor") and adj[r["name"]] < 0.05
                                  and r.get("delta", 0) > 0)
    return {"baseline_margin": round(base, 5), "n_scored_rows": int(n_te),
            "family_size": len(pv), "results": res}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--side", choices=["hit", "pit", "both"], default="both")
    ap.add_argument("--describe-only", action="store_true")
    ap.add_argument("--b-cond", type=int, default=1000)
    ap.add_argument("--b-perm", type=int, default=200)
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    ev = il_events()
    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_health_profile_lab.py",
        "asked_by": "owner, 2026-09-04: an outcome-grounded health profile driver",
        "label_basis": "eWAR v2 (the 2026-09-04 label epoch)",
        "source": ("player_transactions, which carries 27,255 IL events on 4,887 players "
                   "with placements AND activations so cumulative days are computable. "
                   "il_history is NOT usable as history: 1,415 of its 1,662 placements are "
                   "2026 and it was first populated 2026-06-06."),
        "coverage_constraint": (
            "the IL archive starts in 2019, so pre-decision coverage is 0 percent for debut "
            "years 2016-2018, about 19 percent for 2019 and 39 to 79 percent for 2020-2024. "
            "A feature built on the full pool would encode DEBUT ERA rather than health, so "
            "every gated arm here runs on the observable cohort only."),
        "archive_first_year": ARCHIVE_FIRST_YEAR,
        "players_with_any_il_event": len(ev),
        "sides": {},
    }
    for side in (SIDES if a.side == "both" else (a.side,)):
        cands = candidates(side)
        blk = {}
        for pool_name, full in (("full_pool", True), ("debuted_only", False)):
            t0 = time.time()
            P = build_pool(side, ev, full_pool=full)
            mask = observable_mask(P)
            print(f"=== {side} / {pool_name}: {P['n']} rows, observable cohort "
                  f"{int(mask.sum())} ({mask.mean():.1%}), {len(cands)} candidates "
                  f"({time.time()-t0:.0f}s)", flush=True)
            b = {"n_rows": P["n"], "observable_rows": int(mask.sum()),
                 "observable_share": round(float(mask.mean()), 4),
                 "descriptive": describe(P, cands, mask),
                 "exposure_controlled": exposure_controlled(P, cands, mask),
                 "penalty_verdict": penalty_verdict(P, mask)}
            if not a.describe_only:
                b["gated"] = gate(P, cands, mask, a.b_cond, a.b_perm)
            blk[pool_name] = b
        blk["pool_note"] = (
            "full_pool is the HONEST population for an injury question: it keeps the bust "
            "rows, whose label is 0, so a prospect who was hurt and never reached the "
            "majors still counts. debuted_only conditions on the outcome the health signal "
            "is meant to predict and will make injuries look survivable.")
        out["sides"][side] = blk
    if not a.no_write:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", OUT_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
