# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FA destination model's one feature builder (model id fa_destination).

Registered in docs/fa-2026-10/FA_DESTINATION_GATE.md (2026-10-08) before any
code or number existed; this module is the build of that registration (task
Q9_04a) and the lab (tools/fa_destination_lab.py) and the future export both
import it, so the features the gate scores are the features that would serve.

ESTIMAND. P(club signs player | the player signs a major-league deal this
winter): for each free agent a 30-vector over fa_fit_backtest.ORGS, entries in
(0, 1), summing to 1.

FEATURES (gate section 5), all as of the winter start:
  F   fit_analog      0.40 need + 0.05 window + 0.05 afford + 0.05 park
                      + 0.45 behavior_cond, the build_rows fields verbatim; the
                      weights are read from fa_config at run time and
                      check_weights() stops the run if they differ.
  L1  fa_share_3      the club's share of league major-league-deal NPV
                      guarantees over winters Y-3..Y-1.
  L2  payroll_level   z of the club's season Y-1 tax payroll across the clubs
                      with a value (population SD); a club with none takes 0.
  L3  tax_multiplier  1 + (bill(T + a) - bill(T)) / a through the Ledger's
                      computed_cbt_bill at threshold(Y) and the club's tier.
  L4  qo_cost         QO attached x club is not his club x picks forfeited.
  I1  incumbent       the build_rows field.

MODEL (gate section 6). A conditional logit over the 30 clubs,
u = tau F + beta . L + gamma I1, fitted by L-BFGS-B from zeros with an analytic
gradient (gtol 1e-8, maxiter 2000) and a ridge penalty 0.5 x 1.0 x sum(beta^2)
on the four L terms only. L1, L3 and L4 are standardized inside each training
fold; L2, F and I1 enter as defined.

CLUB CODES. The Gate 3 frame keeps its own literal club codes (its rows stay
byte-identical). The club-side inputs read here (the signings corpus and the
Spotrac pages) still carry the Athletics as OAK through 2024, so the L features
map every club code through trades.canonical_org before testing it against the
30 clubs, and count each remapped row. Without that mapping the Athletics would
read a zero spending share and no payroll in most winters of the frame.

Serving is off: FA_DESTINATION_SERVE stays False until a gate pass and an
owner flip; while it is off nothing here writes under data/.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import defaultdict
from datetime import date
from pathlib import Path

import numpy as np

import fa_fit_backtest as fb

ROOT = Path(__file__).resolve().parent
MODEL_ID = "fa_destination"
GATE_DOC = "docs/fa-2026-10/FA_DESTINATION_GATE.md"
#: section 17 of the gate document; the lab stops when the document's text no
#: longer hashes to it (a change belongs in a dated section 18 amendment).
PROTOCOL_SHA256 = "cab64290169c7577c74db3181fae35ffffd505389010113d836749818155bda8"
PROTOCOL_FROM = "## 0. Read to write this"
PROTOCOL_TO = "## 18. Amendments"

#: The serve flag (gate section 16). Off: the payload may go only to
#: PREVIEW_DIR, and nothing is served.
FA_DESTINATION_SERVE = False
PREVIEW_DIR = ROOT / ".cache" / "fa_destination" / "preview"

ORGS = fb.ORGS
N_CLUBS = len(ORGS)
#: The Fit's five weights inside F (gate section 5, row F). Read from
#: fa_config.yaml at run time and compared with these; a difference stops.
REGISTERED_WEIGHTS = {"need": 0.40, "window": 0.05, "afford": 0.05,
                      "park": 0.05, "behavior": 0.45}
F_TERMS = ("need", "window", "afford", "park", "behavior_cond")
L_FEATS = ("fa_share_3", "payroll_level", "tax_multiplier", "qo_cost")
STANDARDIZED = ("fa_share_3", "tax_multiplier", "qo_cost")
ARM_FEATURES = {
    "P": ("fit_analog",) + L_FEATS + ("incumbent",),
    "N": ("fit_analog", "incumbent"),
    "L_perm": ("fit_analog",) + L_FEATS + ("incumbent",),
}
PENALTY_LAMBDA = 1.0
OPTIMIZER = {"method": "L-BFGS-B", "gtol": 1e-8, "maxiter": 2000, "start": "zeros"}
PERM_SEED_BASE = 7


class WeightsMismatch(RuntimeError):
    """fa_config's fit weights are not the registered ones."""


class ProtocolMismatch(RuntimeError):
    """The gate document no longer hashes to the registered protocol."""


# --------------------------------------------------------------------------
# registration checks
# --------------------------------------------------------------------------

def protocol_sha256(doc_text: str) -> str:
    """Section 17: sha256 of the text from '## 0. Read to write this' up to,
    not including, '## 18. Amendments', every whitespace run made one space
    and the ends stripped."""
    i = doc_text.index(PROTOCOL_FROM)
    j = doc_text.index(PROTOCOL_TO, i)
    flat = re.sub(r"\s+", " ", doc_text[i:j]).strip()
    return hashlib.sha256(flat.encode("utf-8")).hexdigest()


def check_protocol(doc_text: str) -> str:
    got = protocol_sha256(doc_text)
    if got != PROTOCOL_SHA256:
        raise ProtocolMismatch(f"gate protocol hash {got} != registered {PROTOCOL_SHA256}")
    return got


def check_weights(weights: dict | None = None) -> dict:
    """The fa_config fit weights, checked against the registered five. Raises
    WeightsMismatch on any difference, so the lab stops before any fit."""
    w = dict(weights) if weights is not None else fb._live_weights()
    if set(w) != set(REGISTERED_WEIGHTS) or any(
            abs(float(w[k]) - REGISTERED_WEIGHTS[k]) > 1e-12 for k in REGISTERED_WEIGHTS):
        raise WeightsMismatch(f"fa_config fit.weights {w} != registered {REGISTERED_WEIGHTS}")
    return {k: float(w[k]) for k in REGISTERED_WEIGHTS}


# --------------------------------------------------------------------------
# F and the club codes
# --------------------------------------------------------------------------

def fit_analog(comp: dict, weights: dict = REGISTERED_WEIGHTS) -> float:
    """F: the Fit's reduced twin with the banded will-spend term."""
    return (weights["need"] * float(comp["need"])
            + weights["window"] * float(comp["window"])
            + weights["afford"] * float(comp["afford"])
            + weights["park"] * float(comp["park"])
            + weights["behavior"] * float(comp["behavior_cond"]))


def canonical_club(code) -> str | None:
    """One of the 30 clubs for a club code, else None (OAK reads ATH)."""
    if not code:
        return None
    if code in ORGS:
        return code
    from trades import canonical_org
    c = canonical_org(code)
    return c if c in ORGS else None


# --------------------------------------------------------------------------
# club-side features for one winter
# --------------------------------------------------------------------------

def _npv_default(player_key, year, guarantee_usd) -> float:
    import fa_market as fm
    return float(fm.npv_guarantee_usd(player_key, year, guarantee_usd)[0])


def fa_share_3(Y: int, load_signings=None, npv_fn=None) -> tuple[dict, dict]:
    """L1 for winter Y: each club's share of the league's major-league-deal
    NPV guarantees over winters Y-3..Y-1. Returns ({org: share}, counts)."""
    if load_signings is None:
        import storage
        load_signings = storage.load_fa_signings
    npv_fn = npv_fn or _npv_default
    sums = {o: 0.0 for o in ORGS}
    counts = {"rows": 0, "remapped_club_code": 0, "not_a_club": 0}
    for y in (Y - 3, Y - 2, Y - 1):
        rows = load_signings(y) or {}
        for s in (rows.values() if isinstance(rows, dict) else rows):
            if not (s.get("mlb_deal") and (s.get("years") or 0) > 0
                    and (s.get("guarantee_usd") or 0) > 0):
                continue
            club = canonical_club(s.get("to_team"))
            if club is None:
                counts["not_a_club"] += 1
                continue
            if club != s.get("to_team"):
                counts["remapped_club_code"] += 1
            sums[club] += npv_fn(s.get("player_key"), y, int(s["guarantee_usd"]))
            counts["rows"] += 1
    total = sum(sums.values())
    counts["league_npv_usd"] = round(total, 2)
    if total <= 0:
        counts["empty_window"] = 1
        return {o: 0.0 for o in ORGS}, counts
    return {o: sums[o] / total for o in ORGS}, counts


def payroll_level(tax_payroll: dict) -> tuple[dict, dict]:
    """L2: z of the club's tax payroll across the clubs with a value (mean and
    population SD over those clubs); a club with no value takes 0."""
    vals = {o: float(v) for o, v in tax_payroll.items() if o in ORGS and v}
    counts = {"clubs_with_value": len(vals), "clubs_without_value": N_CLUBS - len(vals)}
    if len(vals) < 2:
        return {o: 0.0 for o in ORGS}, counts
    mu = sum(vals.values()) / len(vals)
    sd = math.sqrt(sum((v - mu) ** 2 for v in vals.values()) / len(vals))
    if sd <= 0:
        counts["zero_sd"] = 1
        return {o: 0.0 for o in ORGS}, counts
    return {o: ((vals[o] - mu) / sd if o in vals else 0.0) for o in ORGS}, counts


def _threshold(season: int) -> int:
    import fa_market as fm
    return int(fm._cbt_threshold_or_earliest(season))


def _threshold_regime(season: int) -> str | None:
    import fa_cba
    try:
        return fa_cba.cbt_threshold(season).get("regime")
    except LookupError:
        return None


def tier_for_winter(T, threshold_prev, payor_prev) -> str:
    """tier_Y: PAYOR_NEXT of the Y-1 Spotrac token when the Y-1 tax payroll
    is above threshold(Y-1), else Non-Tax (the Ledger's derived-payor rule)."""
    import ledger_export as le
    tok = payor_prev or "Non-Tax"
    if T is not None and threshold_prev is not None and float(T) > float(threshold_prev):
        return le.PAYOR_NEXT.get(tok, "1st-Time")
    return "Non-Tax"


def club_state(Y: int, *, load_signings=None, npv_fn=None, payroll=None,
               pick_forfeiture=None) -> dict:
    """Every club-side input of winter Y, all as of the winter start: L1, L2,
    the Y-1 tax payroll and payor token behind L3, the forfeited-pick count
    behind L4. ``payroll`` is the Y-1 page read ({club code: {tax_payroll_usd,
    payor}}); None reads fa_fit_backtest.team_payroll_state(Y - 1)."""
    import fa_cba
    if payroll is None:
        payroll = fb.team_payroll_state(Y - 1)
    pay: dict[str, dict] = {}
    remapped = 0
    for code, rec in (payroll or {}).items():
        club = canonical_club(code)
        if club is None:
            continue
        if club != code:
            remapped += 1
        pay.setdefault(club, dict(rec or {}))
    share, share_counts = fa_share_3(Y, load_signings, npv_fn)
    tax = {o: (pay.get(o) or {}).get("tax_payroll_usd") for o in ORGS}
    level, level_counts = payroll_level(tax)
    thr_prev, thr_y = _threshold(Y - 1), _threshold(Y)
    pf = pick_forfeiture or fa_cba.pick_forfeiture
    as_of = date(Y - 1, 12, 1)
    clubs = {}
    for o in ORGS:
        tok = (pay.get(o) or {}).get("payor") or "Non-Tax"
        qo_tier = fa_cba.PAYOR_CBT if tok != "Non-Tax" else fa_cba.PAYOR_OTHER
        T = tax[o]
        clubs[o] = {
            "fa_share_3": share[o],
            "payroll_level": level[o],
            "tax_payroll_prev_usd": (float(T) if T else None),
            "payor_prev": tok,
            "tier_Y": tier_for_winter(T if T else None, thr_prev, tok),
            "qo_tier": qo_tier,
            "qo_picks": len(pf(qo_tier, as_of)["picks"]),
        }
    return {
        "winter": Y,
        "threshold_prev_usd": thr_prev,
        "threshold_usd": thr_y,
        "threshold_regime": _threshold_regime(Y),
        "rates": fa_cba.cbt_tax_rates(),
        "tiers": fa_cba.cbt_surcharge_tiers(),
        "clubs": clubs,
        "counts": {"fa_share_3": share_counts, "payroll_level": level_counts,
                   "payroll_remapped_club_code": remapped},
    }


def tax_multiplier(T, a, threshold_usd, tier, rates, tiers, bill_fn=None) -> tuple[float, bool]:
    """L3: 1 + (bill(T + a) - bill(T)) / a. (1.0, True) when T is unknown or
    a is not above 0 (the counted default)."""
    if T is None or a is None or float(a) <= 0:
        return 1.0, True
    if bill_fn is None:
        import ledger_export as le
        bill_fn = le.computed_cbt_bill
    b1 = bill_fn(float(T) + float(a), threshold_usd, tier, rates, tiers)["bill_usd"]
    b0 = bill_fn(float(T), threshold_usd, tier, rates, tiers)["bill_usd"]
    return 1.0 + (float(b1) - float(b0)) / float(a), False


def qo_cost(qo: bool, own_club: bool, picks: int) -> float:
    """L4: q x 1[club is not his club] x k."""
    return float(picks) if (qo and not own_club) else 0.0


def member_features(state: dict, comps: dict, *, aav_usd, qo, from_team) -> dict:
    """The six features of one free agent over the 30 clubs, in ORGS order.

    comps: {org: {need, window, afford, park, behavior_cond, incumbent}}, the
    Fit's reduced components for this player (build_rows rows in the lab).
    aav_usd: the frame's price for L3; qo and from_team: the player's own
    qualifying offer and club for L4. Returns {feature: [30 floats], "flags":
    counts}, plus "third_tier_rows" (rows where T + a passes threshold(Y) +
    the third surcharge offset, counted for 2017-agreement winters)."""
    own = canonical_club(from_team)
    out = {f: [] for f in ("fit_analog",) + L_FEATS + ("incumbent",)}
    flags = {"tax_multiplier_default": 0, "payroll_level_missing": 0}
    third = 0
    t3 = float(state["tiers"][2]) if len(state["tiers"]) > 2 else None
    for o in ORGS:
        c = comps[o]
        club = state["clubs"][o]
        out["fit_analog"].append(fit_analog(c))
        out["fa_share_3"].append(float(club["fa_share_3"]))
        out["payroll_level"].append(float(club["payroll_level"]))
        if club["tax_payroll_prev_usd"] is None:
            flags["payroll_level_missing"] += 1
        T = club["tax_payroll_prev_usd"]
        m, dflt = tax_multiplier(T, aav_usd, state["threshold_usd"], club["tier_Y"],
                                 state["rates"], state["tiers"])
        out["tax_multiplier"].append(m)
        flags["tax_multiplier_default"] += int(dflt)
        if (not dflt and t3 is not None
                and float(T) + float(aav_usd) > float(state["threshold_usd"]) + t3):
            third += 1
        out["qo_cost"].append(qo_cost(bool(qo), own == o, club["qo_picks"]))
        out["incumbent"].append(float(c["incumbent"]))
    out["flags"] = flags
    out["third_tier_rows"] = third
    return out


# --------------------------------------------------------------------------
# the conditional logit
# --------------------------------------------------------------------------

def stack(members: list[dict], names: tuple) -> np.ndarray:
    """(n, 30, k) design array for the named features."""
    if not members:
        return np.zeros((0, N_CLUBS, len(names)))
    return np.asarray([[[m[f][j] for f in names] for j in range(N_CLUBS)]
                       for m in members], dtype=float)


def permutation_for_winter(Y: int) -> np.ndarray:
    """L_perm's one draw for winter Y (gate section 7)."""
    return np.random.default_rng(PERM_SEED_BASE + int(Y)).permutation(N_CLUBS)


def permute_l(member: dict, perm) -> dict:
    """Club j's L1-L4 replaced by club perm[j]'s values for the same signing."""
    out = dict(member)
    for f in L_FEATS:
        vals = member[f]
        out[f] = [vals[int(perm[j])] for j in range(N_CLUBS)]
    return out


def fold_standardize(X_train: np.ndarray, X_test: np.ndarray, names: tuple):
    """Standardize L1, L3 and L4 by the training fold's mean and population SD
    over all 30 x n rows; a feature with SD 0 enters as 0 (counted)."""
    Xtr, Xte = X_train.copy(), X_test.copy()
    stats = {}
    for i, f in enumerate(names):
        if f not in STANDARDIZED:
            continue
        col = X_train[:, :, i].ravel()
        mu = float(col.mean()) if col.size else 0.0
        sd = float(col.std()) if col.size else 0.0
        if sd <= 0:
            Xtr[:, :, i] = 0.0
            Xte[:, :, i] = 0.0
            stats[f] = {"mean": mu, "sd": sd, "zero_sd": True}
        else:
            Xtr[:, :, i] = (X_train[:, :, i] - mu) / sd
            Xte[:, :, i] = (X_test[:, :, i] - mu) / sd
            stats[f] = {"mean": mu, "sd": sd, "zero_sd": False}
    return Xtr, Xte, stats


def _objective(w, X, y, pen, lam):
    n = X.shape[0]
    u = X @ w
    m = u.max(axis=1, keepdims=True)
    e = np.exp(u - m)
    z = e.sum(axis=1, keepdims=True)
    log_z = (m + np.log(z)).ravel()
    rows = np.arange(n)
    nll = float(np.sum(log_z - u[rows, y]))
    p = e / z
    grad = np.einsum("nj,njk->k", p, X) - X[rows, y].sum(axis=0)
    return nll + 0.5 * lam * float(np.sum(pen * w * w)), grad + lam * pen * w


def fit_clogit(X: np.ndarray, y: np.ndarray, names: tuple,
               lam: float = PENALTY_LAMBDA) -> tuple[dict, dict]:
    """Fit tau, beta and gamma by L-BFGS-B from zeros (gate section 6); only
    the L terms are penalized. Returns ({name: coef}, info)."""
    from scipy.optimize import minimize
    pen = np.asarray([1.0 if f in L_FEATS else 0.0 for f in names])
    y = np.asarray(y, dtype=int)
    res = minimize(_objective, np.zeros(len(names)), args=(X, y, pen, lam),
                   jac=True, method=OPTIMIZER["method"],
                   options={"gtol": OPTIMIZER["gtol"], "maxiter": OPTIMIZER["maxiter"]})
    coefs = {f: float(c) for f, c in zip(names, res.x)}
    info = {"converged": bool(res.success), "nit": int(res.nit),
            "message": str(res.message), "objective": float(res.fun),
            "n_signings": int(X.shape[0])}
    return coefs, info


def predict_proba(X: np.ndarray, coefs: dict, names: tuple) -> np.ndarray:
    """(n, 30) probabilities: softmax of u over the 30 clubs."""
    w = np.asarray([coefs[f] for f in names], dtype=float)
    u = X @ w
    u = u - u.max(axis=1, keepdims=True)
    e = np.exp(u)
    return e / e.sum(axis=1, keepdims=True)


def coef_hash(obj) -> str:
    """sha256 of the canonical JSON of a coefficient record (sorted keys,
    floats as Python repr), the value a served payload must equal."""
    return hashlib.sha256(json.dumps(obj, sort_keys=True, separators=(",", ":"))
                          .encode("utf-8")).hexdigest()


def comps_from_rows(rows: list[dict]) -> dict[tuple, dict]:
    """Group build_rows output into {(winter, signing): {org: row}}."""
    out: dict[tuple, dict] = defaultdict(dict)
    for r in rows:
        out[(r["winter"], r["signing"])][r["org"]] = r
    return dict(out)


# --------------------------------------------------------------------------
# the class vector (gate section 14's freeze; section 5's serving column)
# --------------------------------------------------------------------------
# F on the serving class is "the same definitions on 2026 inputs and projGuar /
# projAav". build_rows computes those definitions inline for realized signings
# only, so winter_context() and member_comps() restate its per-winter state
# and per-club arithmetic for any priced member. test_fa_destination_freeze.py
# pins the restatement: fed the realized signings of every Gate 3 winter, it
# returns build_rows' rows field for field, bit-exact.

def winter_context(Y: int, enriched: list | None = None) -> dict:
    """Every club-side input of the Fit's reduced twin for winter Y, as
    build_rows reads it at the winter start: the behavior priors from
    signings of winters before Y, season Y-1 tax payroll, wins and park
    factors, and the threshold of season Y-1."""
    import fa_market as fm
    import fa_sources
    from trades import canonical_org
    if enriched is None:
        enriched = fm.enriched_signings(2015, Y - 1)
    prior = [s for s in enriched if s["class_year"] < Y]
    beh: dict[str, dict] = defaultdict(lambda: {"max": 0, "n100": 0, "recent": 0,
                                               "guars": [], "events": []})
    for s in prior:
        t = s.get("to_team")
        if t not in ORGS:
            continue
        g = fm._npv_of(s)
        beh[t]["max"] = max(beh[t]["max"], g)
        beh[t]["guars"].append(g)
        beh[t]["events"].append((s["class_year"], g))
        if g >= 100_000_000:
            beh[t]["n100"] += 1
        if s["class_year"] >= Y - 3:
            beh[t]["recent"] += g
    for v in beh.values():
        v["guars"].sort()
    max_recent = max((b["recent"] for b in beh.values()), default=1) or 1
    park: dict[str, dict] = {}
    try:
        import fa_fit as _ff
        for r in fa_sources.fetch_savant_park_factors(Y - 1):
            club = r.get("name_display_club") or ""
            org = _ff._SAVANT_CLUB_OVERRIDES.get(club) or canonical_org(club)
            park[org or "?"] = {"woba": int(r.get("index_woba") or 100),
                                "hr": int(r.get("index_hr") or 100)}
    except Exception:                                       # noqa: BLE001
        park = {}
    return {"winter": Y, "beh": dict(beh), "max_recent": max_recent,
            "pay": fb.team_payroll_state(Y - 1), "wins": fb.standings_wins(Y - 1),
            "park": park, "threshold_prev_usd": fm._cbt_threshold_or_earliest(Y - 1),
            "prior_class_years": len({s["class_year"] for s in prior})}


def outgoing_groups(entries) -> dict[str, set]:
    """{club: position groups with an outgoing free agent} from (from_team,
    position) pairs, the build_rows need proxy."""
    import fa_market as fm
    out: dict[str, set] = defaultdict(set)
    for frm, pos in entries:
        if frm in ORGS:
            out[frm].add(fm._pos_group(pos))
    return dict(out)


def member_comps(ctx: dict, *, position, from_team, npv_usd: float, aav_usd: float,
                 outgoing: dict) -> dict:
    """{club: {need, window, afford, park, behavior, behavior_cond,
    incumbent}} for one priced free agent, build_rows' arithmetic."""
    import fa_market as fm
    Y = ctx["winter"]
    beh = ctx["beh"]
    npv, aav = npv_usd, aav_usd
    grp = fm._pos_group(position)
    is_pit = grp in ("SP", "RP")
    cond = {org: fb._cond_terms((beh.get(org) or {}).get("events") or [], npv, Y - 3)
            for org in ORGS}
    max_band_outlay = max(v[0] for v in cond.values())
    out = {}
    for org in ORGS:
        b = beh.get(org) or {"max": 0, "n100": 0, "recent": 0, "guars": []}
        tax = (ctx["pay"].get(org) or {}).get("tax_payroll_usd")
        space = (ctx["threshold_prev_usd"] - tax) if tax else None
        afford = (max(0.0, min(1.0, space / (aav * 2.0))) if space is not None else 0.5)
        out[org] = {
            "need": 1.0 if grp in outgoing.get(org, ()) else 0.0,
            "window": fb._leverage(ctx["wins"].get(org)),
            "afford": afford,
            "park": fb._park_score(ctx["park"], org, is_pit),
            "behavior": (0.5 * fb._reach(b, npv)
                         + 0.3 * min(1.0, b["recent"] / ctx["max_recent"])
                         + 0.2 * min(1.0, b["n100"] / 5.0)),
            "behavior_cond": (
                0.5 * fb._reach(b, npv)
                + 0.3 * (cond[org][0] / max_band_outlay if max_band_outlay > 0 else 0.0)
                + 0.2 * min(1.0, cond[org][1] / 5.0)),
            "incumbent": 1.0 if from_team == org else 0.0,
        }
    return out


def apply_standardization(X: np.ndarray, names: tuple, stats: dict) -> np.ndarray:
    """A fitted record's standardization applied to new rows (a zero-SD
    feature enters as 0, as in the fold)."""
    X = X.copy()
    for i, f in enumerate(names):
        s = stats.get(f)
        if not s:
            continue
        X[:, :, i] = 0.0 if s["zero_sd"] else (X[:, :, i] - s["mean"]) / s["sd"]
    return X


def class_vectors(members: list[dict], fit_record: dict, ctx: dict, *,
                  state: dict | None = None) -> dict:
    """{key: [30 probabilities in ORGS order]} for the priced members of a
    class under one fitted arm (its features, coefs and standardization).

    members: [{key, pos, from, projGuar, projAav, qo}]; the need proxy reads
    every member's (from, pos). A member without projGuar or projAav gets no
    vector (counted by the caller). ``state`` (club_state) is needed only when
    the arm carries a Club Ledger term."""
    names = tuple(fit_record["features"])
    if any(f in L_FEATS for f in names) and state is None:
        raise ValueError("this arm reads Club Ledger terms: pass club_state(Y)")
    outgoing = outgoing_groups((m.get("from"), m.get("pos")) for m in members)
    keys, feats = [], []
    for m in members:
        if not m.get("projGuar") or not m.get("projAav"):
            continue
        comps = member_comps(ctx, position=m.get("pos"), from_team=m.get("from"),
                             npv_usd=float(m["projGuar"]), aav_usd=float(m["projAav"]),
                             outgoing=outgoing)
        if state is not None:
            f = member_features(state, comps, aav_usd=float(m["projAav"]),
                                qo=bool(m.get("qo")), from_team=m.get("from"))
        else:
            f = {"fit_analog": [fit_analog(comps[o]) for o in ORGS],
                 "incumbent": [float(comps[o]["incumbent"]) for o in ORGS]}
        keys.append(m["key"])
        feats.append(f)
    X = apply_standardization(stack(feats, names), names, fit_record.get("standardization") or {})
    P = predict_proba(X, fit_record["coefs"], names)
    return {k: [float(p) for p in P[i]] for i, k in enumerate(keys)}
