# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The fWAR label epoch's measurement (docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md),
runbook step H: a copy of tools/efv_ewar_label_epoch_lab.py read under part 4.1's
substitution ("bWAR" reads "eWAR v2", the incumbent; "eWAR" reads "published fWAR", the
candidate) and extended with the clause (i) arm table.

Clauses (b) to (e) and (i) live here and write ONE artifact,
data/xfv_fwar_label_epoch_eval.json. Clause (f), the blast radius, is `--blast`: it reads
the step A snapshot at ../_pre_epoch_fwar_2026-10/ (read-only; the run REFUSES when that
directory is absent, and it NEVER reads the previous epoch's snapshot directory or the
2026-09-25 archive, which are named only in FORBIDDEN_SNAPSHOT_NAMES) and writes
data/xfv_fwar_label_epoch_blast.json. This lab FITS NOTHING that ships, writes nothing to
prospects.db, never writes a served matrix and edits no document: part 9 of the gate is
written by hand at step Z from what this prints.

THE THREE LABEL BASES, all on the SAME rows (the Estar arm of step F, the full candidate
as built), the same window and the same weights, so every comparison is paired and the
only thing that varies is the WAR series:

    ewar_v2  career_war.seasons_ewar_v2, the incumbent the step C rebase keeps (gate
             note 2: the incumbent column of the cross-label matrix is the eWAR v2 label,
             reconstructible from the table itself, never from the live provider)
    fwar     career_war.seasons, what the table serves after step C
    twin     clause (e)'s zero-information control: the per-season fWAR-minus-eWAR v2
             deltas are PERMUTED ACROSS PLAYERS WITHIN (season, side) and added back to
             eWAR v2, so the twin has fWAR's marginal distribution and none of its
             information. Note 1: the twin per side, together with the clause (i) arms,
             is the control that replaces clause (a)'s voided regen control.

The predecessor's fourth basis (`nopp`, position-player mop-up pitching) measured the FIP
swap's artifact and has no reading under the substitution; it is not carried.

THE ARM TABLE (clause (i)). For every published quantity Q the lab can read off a matrix
and its own same-label fit (the forward-chained E_cond margin on the debuted and the
full-pool cuts, the blend and consensus rhos, the row census), per side:
`effect_f = Q(Estar) - Q(Estar minus f)` for each factor F1 to F5, and the residual
`Q(Estar) - Q(E0) - sum_f effect_f`, labelled "interaction, unattributed", COMPUTED AND
PUBLISHED. A factor whose arm the manifest omits (a FAILED ARM) or whose file is missing is
recorded as UNAVAILABLE and never inferred from the total or the other arms; the residual
then says which factors it sums over. Each candidate factor's OWN clauses are printed beside
it: Arm R's from docs/efv-2026-10-02/BUST2_GATE.md, A1's four pre-registered clauses and
A2's level clause plus the A1/A2 sign-agreement rule from the predecessor's Appendix A.
F1 and F2 are owner decisions and carry no ship clause (part 0).

STRATA are side, season, fold and debut cohort band. Never a consensus-FV cell
(docs/PROSPECT_ANCHOR_GATE.md). Never the reserved frames R-LV and R-VM: the lab scores
efv_model.SCORED_YEARS forward-chained folds on matrix rows only.

Run (step H, after steps F and G; re-run after P):
    python tools/efv_fwar_label_epoch_lab.py                 # clauses b, c, d, e, i
    python tools/efv_fwar_label_epoch_lab.py --quick         # small B, for wiring checks
    python tools/efv_fwar_label_epoch_lab.py --blast         # clause f, needs the step A snapshot
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

for _v in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS", "NUMEXPR_NUM_THREADS"):
    os.environ[_v] = "1"

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import efv_dataset as ds                    # noqa: E402  READ ONLY
import efv_model as E                       # noqa: E402  READ ONLY
import storage                              # noqa: E402  READ ONLY (one select)

sys.path.insert(0, str(ROOT / "tools"))
import efv_mde_lab as M                     # noqa: E402  the floors' own primitives
import efv_fwar_epoch_arms as A             # noqa: E402  the step F arm manifest

OUT_PATH = ROOT / "data" / "xfv_fwar_label_epoch_eval.json"
BLAST_PATH = ROOT / "data" / "xfv_fwar_label_epoch_blast.json"
GATE = "docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md"
BUST2 = "docs/efv-2026-10-02/BUST2_GATE.md"

#: The step A snapshot (gate part 7 row A). Read-only, refused when absent.
SNAP_DIR = ROOT.parent / "_pre_epoch_fwar_2026-10"
#: Directory NAMES this lab never reads: the previous epoch's evidence and the archive.
FORBIDDEN_SNAPSHOT_NAMES = ("_pre_epoch_2026-09", "_pre_epoch_2026-09-25")

SEED = 20260807                 # the standard's seed; do not change
SIDES = ("hit", "pit")
BASES = ("ewar_v2", "fwar", "twin")
TOST_MARGIN = 0.02              # the owner's registered equivalence margin
COHORT_BANDS = ((2011, 2015), (2016, 2019), (2020, 2025))
B_PERM_MIN = 2000               # clause (e) 2: the permutation band, B >= 2,000
MIN_TIME_SPLITS = 4             # clause (e) 3

INCUMBENT_KEY = A.INCUMBENT_LABEL_KEY       # seasons_ewar_v2
CANDIDATE_KEY = A.CANDIDATE_LABEL_KEY       # seasons
A2_FLAG = "efv_model.NEUTRAL_MILB_IMPUTE"
A1_FLAG = "efv_dataset.SERVICE_ALIGNED_WINDOW"
RT_FLAG = "efv_dataset.RESOLVED_THROUGH"

#: The quantities the arm table attributes (clause (i)), all per side.
Q_KEYS = ("margin_debuted", "blend_rho_debuted", "consensus_rho_debuted",
          "margin_full_pool", "blend_rho_full_pool", "consensus_rho_full_pool",
          "n_debuted_scored", "n_full_pool_scored", "rows", "debuted_rows", "busts_in_pool",
          "bust_share_full_pool", "debuted_censored_share", "resolved_labels_le_0_share")

#: Pre-registered expectations carried into the printout, never used as a criterion.
A1_EXPECTED = {"hit": {"resolved_to_censored": 57, "resolved_n": 129, "mean_dlabel": 1.047},
               "pit": {"resolved_to_censored": 101, "resolved_n": 136, "mean_dlabel": 0.496}}
A2_EXPECTED = {"level_rank_slope_off": 0.154, "level_rank_slope_on": (0.209, 0.253)}


# ------------------------------------------------------------------ the label bases
def _career_war() -> dict[str, dict]:
    with storage.connect() as con:
        return {r["player_key"]: json.loads(r["payload_json"])
                for r in con.execute("select player_key, payload_json from career_war")}


def _int_seasons(d: dict | None) -> dict[int, float]:
    return {int(y): float(v) for y, v in (d or {}).items() if v is not None}


def incumbent_series(row: dict) -> tuple[dict[int, float], int]:
    """(the eWAR v2 series, fell_back): the kept `seasons_ewar_v2` when the payload
    carries it as a dict (an empty dict is an answer), else `seasons`, counted. The same
    reading efv_dataset._label_seasons gives the E0 and F1 arms off its default."""
    alt = (row or {}).get(INCUMBENT_KEY)
    if isinstance(alt, dict):
        return _int_seasons(alt), 0
    return _int_seasons((row or {}).get(CANDIDATE_KEY)), 1


def twin_series(cw: dict[str, dict], keys, rng: np.random.Generator
                ) -> dict[str, dict[int, float]]:
    """Clause (e) 1 on this epoch: within each season, the fWAR-minus-eWAR v2 deltas of the
    players in `keys` (ONE SIDE's pool) are permuted across those players and added back
    to eWAR v2. A player outside `keys` is not in the twin at all, so no delta crosses a
    side; a season's delta multiset is preserved exactly."""
    deltas: dict[int, list[float]] = {}
    owners: dict[int, list[str]] = {}
    twin: dict[str, dict[int, float]] = {}
    for pk in sorted(keys):
        row = cw.get(pk)
        if row is None:
            continue
        inc, _fb = incumbent_series(row)
        fw = _int_seasons(row.get(CANDIDATE_KEY))
        twin[pk] = dict(inc)
        for y, v in fw.items():
            deltas.setdefault(y, []).append(v - inc.get(y, v))
            owners.setdefault(y, []).append(pk)
    for y in sorted(deltas):
        arr = np.array(deltas[y], dtype=float)
        for pk, d in zip(owners[y], arr[rng.permutation(len(arr))]):
            twin[pk][y] = twin[pk].get(y, 0.0) + float(d)
    return twin


def build_series(cw: dict[str, dict], keys, rng: np.random.Generator) -> dict:
    """{basis: {player_key: {year: war}}} for one side's keys, plus receipts."""
    out: dict[str, dict] = {b: {} for b in BASES}
    fallback_rows = moved_seasons = n_seasons = 0
    for pk in sorted(keys):
        row = cw.get(pk)
        if row is None:
            continue
        inc, fb = incumbent_series(row)
        fw = _int_seasons(row.get(CANDIDATE_KEY))
        fallback_rows += fb
        out["ewar_v2"][pk] = inc
        out["fwar"][pk] = fw
        for y, v in fw.items():
            n_seasons += 1
            if abs(v - inc.get(y, v)) > 1e-9:
                moved_seasons += 1
    out["twin"] = twin_series(cw, keys, rng)
    return {"series": out,
            "receipts": {"players": len(out["fwar"]), "incumbent_fallback_rows": fallback_rows,
                         "seasons": n_seasons, "seasons_moved_by_the_basis": moved_seasons}}


# ------------------------------------------------------------------ relabelling
def label_date_for(r: dict) -> str | None:
    """The debut date the build passed to _label_6yr for this row, reconstructed from the
    row: None for a rerouted bust (fabricated Jan 1 cutoff), a placeholder day, or a
    window the debuted loop already re-dated to the first WAR season (debut_year is then
    not the cutoff's year); else the cutoff itself."""
    if r.get("rerouted_from_bust") or r.get("debut_date_is_placeholder"):
        return None
    dd = r.get("cutoff")
    dy = r.get("debut_year")
    if not dd or dy is None or len(str(dd)) < 10:
        return None
    if int(str(dd)[:4]) != int(dy):
        return None
    return str(dd)


def relabel(raw: list[dict], series: dict[str, dict[int, float]], flags: dict) -> list[dict]:
    """The matrix rows with the label recomputed on one WAR series under the ARM'S OWN
    window rule (A1 and RESOLVED_THROUGH from its recorded flags), so the only thing that
    varies between bases is the series. Bust rows carry a label that does not come from
    career_war and pass through untouched. A terminal transaction's resolution is
    re-applied exactly as the build applies it."""
    saved = (ds.SERVICE_ALIGNED_WINDOW, ds.RESOLVED_THROUGH)
    try:
        ds.SERVICE_ALIGNED_WINDOW = bool(flags.get(A1_FLAG, False))
        ds.RESOLVED_THROUGH = int(flags.get(RT_FLAG, ds.RESOLVED_THROUGH))
        out = []
        for r in raw:
            if r.get("kind") != "debuted":
                out.append(r)
                continue
            seasons = series.get(r.get("player_key"))
            dy = r.get("debut_year")
            if not seasons or dy is None:
                out.append(r)
                continue
            try:
                t_res, t_cens, cflag, w, n_obs = ds._label_6yr(seasons, int(dy), label_date_for(r))
            except ValueError:
                out.append(r)
                continue
            q = dict(r)
            q["target_resolved"], q["target_censored"] = t_res, t_cens
            q["censored"], q["weight"], q["observed_seasons"] = cflag, w, n_obs
            if r.get("terminal_resolved") and cflag:
                q["target_censored"], q["censored"] = t_res, False
                q["weight"], q["observed_seasons"] = 1.0, ds.TARGET_SEASONS
            out.append(q)
        return out
    finally:
        ds.SERVICE_ALIGNED_WINDOW, ds.RESOLVED_THROUGH = saved


def parity_mismatches(raw: list[dict], relabelled: list[dict]) -> list[str]:
    """Rows whose relabelling on the arm's OWN basis does not reproduce the stored label.
    Non-empty means the bases would not be paired, and the run stops."""
    bad = []
    for a, b in zip(raw, relabelled):
        if a.get("kind") != "debuted":
            continue
        for k in ("target_resolved", "target_censored", "weight"):
            va, vb = a.get(k), b.get(k)
            if va is None or vb is None:
                if va is not vb:
                    bad.append(a.get("player_key"))
                    break
                continue
            if abs(float(va) - float(vb)) > 1e-6:
                bad.append(a.get("player_key"))
                break
        else:
            if bool(a.get("censored")) != bool(b.get("censored")):
                bad.append(a.get("player_key"))
    return bad


# ------------------------------------------------------------------ pools and the chain
def pool_rows(raw: list[dict], cut: str) -> list[dict]:
    """The rows one cut scores: `debuted` (efv_model's debuted_km) or `full_pool` (debuted
    plus the never-MLB busts the pool marker keeps, efv_model's full_pool_km: a
    CENSORED-NEVER row is excluded through the same marker)."""
    if cut == "debuted":
        return [r for r in raw if r.get("kind") == "debuted"]
    if cut == "full_pool":
        return [r for r in raw if not (r.get("kind") == "bust" and r.get("bust_recent"))
                and r.get("kind") in ("debuted", "bust")]
    raise ValueError(cut)


def pool_for(side: str, raw: list[dict], cut: str = "debuted", a2: bool = False) -> dict:
    """Same shape as efv_mde_lab.load_side, from rows already relabelled, plus the prepped
    rows themselves so an A2 arm can impute per fold."""
    prep = E._prep(pool_rows(raw, cut), "target_censored", side)
    keys, mono = E._feature_spec(side)
    X = np.array([[r["feats"].get(k, 0.0) for k in keys] for r in prep], dtype=float)
    return {
        "side": side, "cut": cut, "a2": bool(a2), "keys": list(keys), "mono": mono, "X": X,
        "prep": prep,
        "y": np.array([r["target"] for r in prep], dtype=float),
        "w": np.clip(np.array([float(r.get("weight", 1.0) or 0.0) for r in prep]), 1e-3, None),
        "fv": np.array([r["fv"] for r in prep], dtype=float),
        "dy": np.array([r["decision_year"] for r in prep], dtype=int),
        "pk": [r.get("player_key") for r in prep],
        "lam": E.blend_lambda(side),
        "n": len(prep),
    }


def fold_X(D: dict, tr, te, a2: bool):
    """(X_train, X_test) for one fold. With A2 on, a milb_unavailable row's MiLB keys are
    moved to the has-MiLB mean of THIS FOLD'S TRAIN rows (efv_model._has_milb_impute_means
    and _impute_feats, the arm's own functions), on train and test alike, so the lab
    applies A2 exactly where efv_model._fit_ridge applies it."""
    if not a2:
        return D["X"][tr], D["X"][te]
    means = E._has_milb_impute_means([D["prep"][i] for i in tr])
    keys = D["keys"]

    def _x(idx):
        return np.array([[E._impute_feats(D["prep"][i]["feats"], means).get(k, 0.0)
                          for k in keys] for i in idx], dtype=float)
    return _x(tr), _x(te)


def chain_cross(D, y_fit, y_score, sel=None, years=None, lam=None, D_score=None):
    """Forward-chained margin with the FIT label and the SCORE label decoupled. Both legs,
    consensus OLS and the ridge, are fitted on y_fit and scored against y_score, so a cell
    never advantages one leg with information the other lacks.

    `D_score`, when given, is a DIFFERENT pool whose test rows of each year are scored by
    the models fitted on D's train rows (Arm R's rank clause scores one pool's fit against
    both pools); y_score then indexes D_score. `sel` resamples D's rows (E_refit) and is
    only valid without D_score."""
    years = tuple(E.SCORED_YEARS) if years is None else tuple(years)
    lam = D["lam"] if lam is None else lam
    S = D if D_score is None else D_score
    if sel is None:
        sel = np.arange(D["n"])
    elif D_score is not None:
        raise ValueError("sel and D_score together are not a paired design")
    X, w, fv, dy = D["X"][sel], D["w"][sel], D["fv"][sel], D["dy"][sel]
    yf = y_fit[sel]
    YR, C, B, T, W = [], [], [], [], []
    for yr in years:
        tr = np.flatnonzero(dy < yr)
        te = np.flatnonzero(S["dy"] == yr) if D_score is not None else np.flatnonzero(dy == yr)
        if len(te) < 15 or len(tr) < 60:
            continue
        if D_score is None:
            Xtr, Xte = fold_X(D, sel[tr], sel[te], D["a2"])
            fv_te, w_te, y_te = fv[te], w[te], y_score[sel][te]
        else:
            # the fit pool's train rows; the SCORE pool's test rows, imputed (A2 on) at
            # the fit pool's train mean exactly as a test fold would be
            Xtr, _ = fold_X(D, sel[tr], sel[tr][:0], D["a2"])
            Xte = _impute_with(D, sel[tr], S, te) if D["a2"] else S["X"][te]
            fv_te, w_te, y_te = S["fv"][te], S["w"][te], y_score[te]
        o = M.ols_fit(fv[tr], yf[tr])
        rg = M.ridge_fit(Xtr, yf[tr], w[tr])
        if o is None or rg is None:
            continue
        cons = np.maximum(0.0, o[0] + o[1] * fv_te)
        mod = M.ridge_pred(rg, Xte)
        YR.append(np.full(len(te), yr))
        C.append(cons)
        B.append((1 - lam) * cons + lam * mod)
        T.append(y_te)
        W.append(w_te)
    if not B:
        return None
    return tuple(np.concatenate(a) for a in (YR, C, B, T, W))


def _impute_with(D_fit, tr, S, te):
    """Test rows of pool S imputed at the has-MiLB mean of pool D_fit's train rows."""
    means = E._has_milb_impute_means([D_fit["prep"][i] for i in tr])
    return np.array([[E._impute_feats(S["prep"][i]["feats"], means).get(k, 0.0)
                      for k in S["keys"]] for i in te], dtype=float)


def margin_of(parts, weighted=True):
    if parts is None:
        return None
    _yr, cons, blend, tgt, w = parts
    ww = w if weighted else None
    c = float(M.wrho(cons, tgt, ww))
    b = float(M.wrho(blend, tgt, ww))
    return {"n": int(len(tgt)), "consensus": round(c, 5), "blend": round(b, 5),
            "margin": round(b - c, 5)}


def margin_from_parts(parts, sel, weighted=True):
    """A margin on a bootstrap resample of the SCORED rows (E_cond: no refit)."""
    _yr, cons, blend, tgt, w = parts
    ww = w[sel] if weighted else None
    return float(M.wrho(blend[sel], tgt[sel], ww)) - float(M.wrho(cons[sel], tgt[sel], ww))


def rho_from_parts(parts, sel, leg="blend", weighted=True):
    _yr, cons, blend, tgt, w = parts
    ww = w[sel] if weighted else None
    return float(M.wrho((blend if leg == "blend" else cons)[sel], tgt[sel], ww))


def per_fold_margins(D, y_fit, y_score):
    out = {}
    for yr in E.SCORED_YEARS:
        m = margin_of(chain_cross(D, y_fit, y_score, years=(yr,)))
        if m:
            out[str(yr)] = m["margin"]
    return out


def _ci(a):
    a = np.array([v for v in np.asarray(a, dtype=float) if np.isfinite(v)])
    if not len(a):
        return None
    return [round(float(np.percentile(a, 2.5)), 5), round(float(np.percentile(a, 97.5)), 5)]


def tost_disposition(ci, margin=TOST_MARGIN) -> str:
    if not ci:
        return "UNDECIDED"
    if ci[0] >= -margin and ci[1] <= margin:
        return "RULED OUT (equivalent within the registered margin)"
    if ci[0] > margin:
        return "SWAP GAIN"
    if ci[1] < -margin:
        return "SWAP LOSS"
    return "UNDECIDED"


def non_inferiority(ci, margin=TOST_MARGIN) -> str:
    """One-sided: the arm is NON-INFERIOR when the interval's lower bound clears -margin."""
    if not ci:
        return "UNDECIDED"
    return "NON-INFERIOR" if ci[0] > -margin else ("INFERIOR" if ci[1] < -margin else "UNDECIDED")


# ------------------------------------------------------------------ clause (c)
def coverage(cw: dict[str, dict], pools: dict) -> dict:
    """Share of LABEL SEASONS (debut year through debut+5, capped at RESOLVED_THROUGH)
    served by the frozen fWAR vintage against eWAR v2 fallback, per side, per debut
    cohort band and PER FOLD (decision year), plus the debuted players with no mlbam id.
    A season is joined on fWAR when the row's `fwar_coverage` receipt (the step C rebase
    writes it) lists it in neither fallback set. A pitcher cohort under 90 percent is
    REPORTED with its number, never hidden and never pooled."""
    out = {}
    for side in SIDES:
        D = pools[side]
        by_band, by_fold = {}, {}
        for lo, hi in COHORT_BANDS:
            by_band[f"{lo}-{hi}"] = {"players": 0, "label_seasons": 0, "join_fwar": 0,
                                     "players_no_id": 0}
        for pk, dyv, decision in zip(D["pk"], D["dy"], [p["decision_year"] for p in D["prep"]]):
            row = cw.get(pk)
            if not row:
                continue
            dy = int(dyv)
            band = next((f"{lo}-{hi}" for lo, hi in COHORT_BANDS if lo <= dy <= hi), None)
            cov = row.get("fwar_coverage") or {}
            fb = set(cov.get("fallback_pre_years") or []) | set(cov.get("fallback_post_years") or [])
            mid = cov.get("mlbam") if cov else (row.get("ewar_coverage") or {}).get("mlbam")
            seasons = _int_seasons(row.get(CANDIDATE_KEY))
            n_lab = n_fw = 0
            for y in range(dy, dy + ds.TARGET_SEASONS):
                if y > ds.RESOLVED_THROUGH or y not in seasons:
                    continue
                n_lab += 1
                if cov and y not in fb:
                    n_fw += 1
            for key, table in ((band, by_band), (str(int(decision)), by_fold)):
                if key is None:
                    continue
                t = table.setdefault(key, {"players": 0, "label_seasons": 0, "join_fwar": 0,
                                           "players_no_id": 0})
                t["players"] += 1
                t["label_seasons"] += n_lab
                t["join_fwar"] += n_fw
                t["players_no_id"] += 1 if mid is None else 0
        for table in (by_band, by_fold):
            for t in table.values():
                n_lab = t["label_seasons"]
                t["share"] = round(t["join_fwar"] / n_lab, 4) if n_lab else None
                t["under_90_pct"] = bool(n_lab and (t["join_fwar"] / n_lab) < 0.90)
        out[side] = {"by_cohort_band": by_band, "by_fold": dict(sorted(by_fold.items())),
                     "reported_not_pooled": [k for k, t in by_band.items() if t["under_90_pct"]]}
    return out


# ------------------------------------------------------------------ the arms
def load_manifest(side: str) -> dict | None:
    p = A.manifest_path(side)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def arm_rows(side: str, manifest: dict, arm: str) -> list[dict] | None:
    e = (manifest.get("arms") or {}).get(arm)
    if not e or not e.get("file"):
        return None
    p = A.OUT_DIR / e["file"]
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def arm_flags(manifest: dict, arm: str) -> dict:
    return dict(((manifest.get("arms") or {}).get(arm) or {}).get("flags") or {})


def row_census(raw: list[dict]) -> dict:
    """Counts read off a matrix. Nulls are tolerated: a row without a label counts in
    `rows` and nowhere else."""
    deb = [r for r in raw if r.get("kind") == "debuted"]
    busts = pool_rows(raw, "full_pool")
    busts = [r for r in busts if r.get("kind") == "bust"]
    res = [r for r in deb if not r.get("censored") and r.get("target_resolved") is not None]
    le0 = [r for r in res if float(r["target_resolved"]) <= 0.0]
    n_pool = len(deb) + len(busts)
    return {
        "rows": len(raw), "debuted_rows": len(deb), "busts_in_pool": len(busts),
        "bust_share_full_pool": round(len(busts) / n_pool, 4) if n_pool else None,
        "debuted_censored_share": (round(sum(1 for r in deb if r.get("censored")) / len(deb), 4)
                                   if deb else None),
        "resolved_labels_le_0_share": round(len(le0) / len(res), 4) if res else None,
    }


def arm_quantities(side: str, raw: list[dict], flags: dict) -> dict:
    """Q(arm): the same-label E_cond margins on both cuts, the rhos, the census. The
    arm's own label, its own pool marker, A2 at fit from its recorded flag."""
    a2 = bool(flags.get(A2_FLAG, False))
    q = row_census(raw)
    for cut in ("debuted", "full_pool"):
        D = pool_for(side, raw, cut, a2)
        m = margin_of(chain_cross(D, D["y"], D["y"]))
        q[f"margin_{cut}"] = m["margin"] if m else None
        q[f"blend_rho_{cut}"] = m["blend"] if m else None
        q[f"consensus_rho_{cut}"] = m["consensus"] if m else None
        q[f"n_{cut}_scored"] = m["n"] if m else 0
    return q


def arm_table(q_by_arm: dict[str, dict | None], manifest: dict) -> dict:
    """Clause (i)'s reading per quantity: effect_f = Q(Estar) - Q(Estar minus f) for every
    factor, UNAVAILABLE for an omitted or missing arm (never inferred), and the residual
    Q(Estar) - Q(E0) - sum of the AVAILABLE effects, labelled "interaction, unattributed",
    with the factors it sums over named."""
    omitted = set((manifest.get("omitted") or {}).keys())
    table = {}
    for key in Q_KEYS:
        qs = q_by_arm.get("Estar") or {}
        q0 = q_by_arm.get("E0") or {}
        row = {"Q_Estar": qs.get(key), "Q_E0": q0.get(key), "effects": {}, "summed_over": []}
        total = (None if qs.get(key) is None or q0.get(key) is None
                 else qs[key] - q0[key])
        row["total_move_Estar_minus_E0"] = (round(total, 5) if isinstance(total, (int, float))
                                            else None)
        s = 0.0
        for fid in A.FACTORS:
            if fid in omitted:
                row["effects"][fid] = {"status": "UNAVAILABLE",
                                       "reason": manifest["omitted"][fid].get("reason"),
                                       "note": "FAILED ARM: never inferred"}
                continue
            qf = q_by_arm.get(fid)
            if not qf or qf.get(key) is None or qs.get(key) is None:
                row["effects"][fid] = {"status": "UNAVAILABLE",
                                       "reason": "arm matrix missing or quantity not computed"}
                continue
            eff = qs[key] - qf[key]
            row["effects"][fid] = {"effect": round(eff, 5), "Q_arm": qf[key]}
            s += eff
            row["summed_over"].append(fid)
        if total is not None:
            row["interaction_unattributed"] = round(total - s, 5)
            row["interaction_note"] = ("Q(Estar) - Q(E0) - sum of the leave-one-out effects over "
                                       f"{row['summed_over'] or 'no available factor'}; a main-effect "
                                       "reading under an additivity assumption this design does "
                                       "not test (clause (i) points 2 and 3)")
        else:
            row["interaction_unattributed"] = None
        table[key] = row
    return table


# ------------------------------------------------------------------ the candidates' own clauses
def _by_pk(rows):
    return {(r.get("player_key"), r.get("kind")): r for r in rows}


def arm_r_clauses(side: str, estar: list[dict], f3: list[dict] | None, rng, B_cond: int,
                  flags_estar: dict) -> dict:
    """Arm R's clauses, in BUST2's order. The resolved-to-censored count FIRST; STOP when the
    full-pool bust share moves more than 10 points; the rank clause (E_cond pooled Spearman,
    non-inferior at the 0.02 TOST margin) scored against BOTH the E0 evaluation label (the
    F3 pool: every never-MLB row resolved except bust_recent) and the Arm R label (the
    Estar pool), both published. Under clause (i) the comparison is Estar against Estar
    minus Arm R."""
    out = {"source": BUST2, "factor": "F3"}
    if f3 is None:
        out["status"] = "UNAVAILABLE"
        out["note"] = "the Arm R leave-one-out arm is omitted or missing: a FAILED ARM, never inferred"
        return out
    b_star, b_f3 = _by_pk(estar), _by_pk(f3)
    r2c = c2r = 0
    for k, r in b_star.items():
        if r.get("kind") != "bust":
            continue
        o = b_f3.get(k)
        if o is None:
            continue
        if r.get("bust_recent") and not o.get("bust_recent"):
            r2c += 1
        elif o.get("bust_recent") and not r.get("bust_recent"):
            c2r += 1
    out["1_resolved_to_censored_count"] = r2c          # reported FIRST
    out["1b_censored_to_resolved_count"] = c2r
    cs, c3 = row_census(estar), row_census(f3)
    share_star, share_f3 = cs["bust_share_full_pool"], c3["bust_share_full_pool"]
    move = (None if share_star is None or share_f3 is None
            else round((share_star - share_f3) * 100.0, 3))
    out["2_full_pool_bust_share"] = {"Estar": share_star, "E0_rule_F3": share_f3,
                                     "move_points": move}
    if move is None:
        out["2_disposition"] = "UNDECIDED (no pool)"
    elif abs(move) > 10.0:
        out["2_disposition"] = "STOP: the full-pool bust share moved more than 10 points"
        out["3_rank_clause"] = "not read (the STOP above)"
        return out
    else:
        out["2_disposition"] = "within 10 points"
    # the rank clause, both pools
    a2 = bool(flags_estar.get(A2_FLAG, False))
    try:
        D_star = pool_for(side, estar, "full_pool", a2)
        D_f3 = pool_for(side, f3, "full_pool", a2)
    except Exception as exc:  # noqa: BLE001  a fixture without features
        out["3_rank_clause"] = {"status": "UNAVAILABLE", "reason": f"pool not scorable: {exc}"}
        return out
    rank = {}
    for score_name, D_s in (("arm_r_label_estar_pool", D_star), ("e0_evaluation_label_f3_pool", D_f3)):
        p_star = chain_cross(D_star, D_star["y"], D_s["y"], D_score=D_s)
        p_f3 = chain_cross(D_f3, D_f3["y"], D_s["y"], D_score=D_s)
        if p_star is None or p_f3 is None:
            rank[score_name] = {"status": "UNDECIDED", "reason": "no fold survived the floors"}
            continue
        n = len(p_star[3])
        if len(p_f3[3]) != n:
            rank[score_name] = {"status": "UNDECIDED", "reason": "the two fits scored different rows"}
            continue
        point = rho_from_parts(p_star, np.arange(n)) - rho_from_parts(p_f3, np.arange(n))
        cond = []
        for _ in range(B_cond):
            sel = rng.integers(0, n, n)
            cond.append(rho_from_parts(p_star, sel) - rho_from_parts(p_f3, sel))
        ci = _ci(cond)
        rank[score_name] = {
            "n_scored": int(n),
            "blend_rho_fit_estar": round(rho_from_parts(p_star, np.arange(n)), 5),
            "blend_rho_fit_f3": round(rho_from_parts(p_f3, np.arange(n)), 5),
            "margin_fit_estar": margin_of(p_star)["margin"],
            "margin_fit_f3": margin_of(p_f3)["margin"],
            "point_difference_blend_rho": round(float(point), 5),
            "E_cond_ci95": ci, "tost_margin": TOST_MARGIN,
            "disposition": non_inferiority(ci),
        }
    out["3_rank_clause"] = rank
    verdicts = [v.get("disposition") for v in rank.values()]
    out["ships_on_its_own_clauses"] = bool(verdicts) and all(v == "NON-INFERIOR" for v in verdicts)
    out["note"] = ("E_cond pooled Spearman of the blend on the full-pool cut, forward-chained; "
                   "floors re-derived at step G are read beside this at step Z")
    return out


def a1_clauses(side: str, estar: list[dict], f4: list[dict] | None, census_estar: dict) -> dict:
    """A1's four pre-registered clauses (EWAR_LABEL_EPOCH_GATE.md Appendix A, corrected
    2026-09-04), read as Estar against Estar minus A1 (F4)."""
    out = {"source": "docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md Appendix A (A1 expectation)",
           "factor": "F4", "pre_registered_expectation": A1_EXPECTED.get(side)}
    if f4 is None:
        out["status"] = "UNAVAILABLE"
        out["note"] = "the A1 leave-one-out arm is omitted or missing: a FAILED ARM, never inferred"
        return out
    b_star, b_f4 = _by_pk(estar), _by_pk(f4)
    r2c = 0
    w_before, w_after, d_res, d_full = [], [], [], []
    for k, r in b_star.items():
        if r.get("kind") != "debuted":
            continue
        o = b_f4.get(k)
        if o is None:
            continue
        if r.get("censored") and not o.get("censored"):
            r2c += 1
        if o.get("weight") is not None and r.get("weight") is not None:
            w_before.append(float(o["weight"]))
            w_after.append(float(r["weight"]))
        if (r.get("target_censored") is not None and o.get("target_censored") is not None):
            d_full.append(float(r["target_censored"]) - float(o["target_censored"]))
        if (not r.get("censored") and not o.get("censored")
                and r.get("target_resolved") is not None and o.get("target_resolved") is not None):
            d_res.append(float(r["target_resolved"]) - float(o["target_resolved"]))
    cs, c4 = row_census(estar), row_census(f4)
    share_move = (None if cs["debuted_censored_share"] is None or c4["debuted_censored_share"] is None
                  else round((cs["debuted_censored_share"] - c4["debuted_censored_share"]) * 100.0, 3))

    def _dist(ws):
        if not ws:
            return None
        hist = {}
        for w in ws:
            hist[str(round(w, 3))] = hist.get(str(round(w, 3)), 0) + 1
        return {"mean": round(float(np.mean(ws)), 4), "by_weight": dict(sorted(hist.items()))}
    out["1_censoring_cost"] = {
        "resolved_to_censored": r2c,
        "extrapolated_label_share_before_F4": c4["debuted_censored_share"],
        "extrapolated_label_share_after_Estar": cs["debuted_censored_share"],
        "share_move_points": share_move,
        "weight_distribution_before": _dist(w_before),
        "weight_distribution_after": _dist(w_after),
        "window_shifted_rows": (census_estar or {}).get("window_shifted"),
    }
    if share_move is not None and abs(share_move) > 10.0:
        out["2_disposition"] = ("STOP: the extrapolated share moved more than 10 points; the arm "
                                "changes the censoring regime more than the estimand and cannot "
                                "be measured on this frame")
        out["3_level_clause"] = "not read (the STOP above)"
        return out
    out["2_disposition"] = "within 10 points" if share_move is not None else "UNDECIDED (no rows)"
    out["3_level_clause"] = {
        "resolved_rows_n": len(d_res),
        "resolved_mean_label_change_WAR": round(float(np.mean(d_res)), 4) if d_res else None,
        "full_pool_rows_n": len(d_full),
        "full_pool_mean_label_change_WAR": round(float(np.mean(d_full)), 4) if d_full else None,
        "reading": "the level clause reads the RESOLVED rows; the full-pool number is beside it "
                   "and is expected to be smaller",
    }
    out["4_percentage_of_label"] = "NOT a clause; not computed (unstable denominator)"
    out["ships_on_its_own_clauses"] = bool(d_res) and float(np.mean(d_res)) > 0.0
    return out


def level_rank_slope(D: dict, a2: bool) -> dict:
    """The ridge's level_rank slope on the RAW scale (standardised weight over the
    column's sd), production-style fit on the whole debuted pool, with A2's imputation
    applied at the pool's has-MiLB mean when on. A2's level clause reads this."""
    if "level_rank" not in D["keys"] or D["n"] < 40:
        return {"status": "UNAVAILABLE", "reason": "no level_rank key or under 40 rows"}
    idx = np.arange(D["n"])
    Xtr, _ = fold_X(D, idx, idx[:0], a2)
    m = M.ridge_fit(Xtr, D["y"], D["w"])
    if m is None:
        return {"status": "UNAVAILABLE", "reason": "the ridge did not fit"}
    mu, sd, ww, b = m
    i = D["keys"].index("level_rank")
    imputed = int(sum(1 for p in D["prep"] if p["feats"].get("milb_unavailable")))
    return {"level_rank_slope_raw_WAR_per_rung": round(float(ww[i] / sd[i]), 4),
            "rows": int(D["n"]), "milb_unavailable_rows": imputed}


def a2_clauses(side: str, estar: list[dict], f5: list[dict] | None, flags_estar: dict) -> dict:
    """A2's level clause (Appendix A): the level_rank raw-scale slope moves up when the
    milb_unavailable block is imputed at the has-MiLB mean instead of raw 0."""
    out = {"source": "docs/efv-2026-09-03/EWAR_LABEL_EPOCH_GATE.md Appendix A (A2 row)",
           "factor": "F5", "pre_registered_expectation": A2_EXPECTED}
    if f5 is None:
        out["status"] = "UNAVAILABLE"
        out["note"] = "the A2 leave-one-out arm is omitted or missing: a FAILED ARM, never inferred"
        return out
    try:
        D_on = pool_for(side, estar, "debuted", True)
        D_off = pool_for(side, f5, "debuted", False)
    except Exception as exc:  # noqa: BLE001
        out["level_clause"] = {"status": "UNAVAILABLE", "reason": f"pool not scorable: {exc}"}
        return out
    on, off = level_rank_slope(D_on, True), level_rank_slope(D_off, False)
    out["level_clause"] = {"A2_on_Estar": on, "A2_off_F5": off}
    k = "level_rank_slope_raw_WAR_per_rung"
    if k in on and k in off:
        out["level_clause"]["slope_delta"] = round(on[k] - off[k], 4)
        out["ships_on_its_own_clauses"] = on[k] > off[k]
    else:
        out["ships_on_its_own_clauses"] = None
    return out


def sign_agreement(table: dict, side_note: str = "") -> dict:
    """The Appendix A rule: if A1 and A2 disagree in sign on the same side (their effects
    on the debuted margin), neither ships and both are recorded as a loss."""
    eff = (table.get("margin_debuted") or {}).get("effects") or {}
    a1, a2 = eff.get("F4") or {}, eff.get("F5") or {}
    if "effect" not in a1 or "effect" not in a2:
        return {"status": "UNAVAILABLE", "reason": "an arm is unavailable; the rule cannot be read"}
    s1, s2 = np.sign(a1["effect"]), np.sign(a2["effect"])
    disagree = bool(s1 != 0 and s2 != 0 and s1 != s2)
    return {"effect_A1_on_margin": a1["effect"], "effect_A2_on_margin": a2["effect"],
            "disagree_in_sign": disagree,
            "disposition": ("neither ships; both recorded as a loss with the interaction cell "
                            "published" if disagree else "no sign disagreement")}


def print_candidate_clauses(side: str, cand: dict) -> None:
    print(f"\n=== {side}: each candidate factor's OWN clauses (F1 and F2 ship regardless, part 0) ===")
    for fid, block in cand.items():
        print(f"--- {fid}")
        print(json.dumps(block, indent=1, default=str))


# ------------------------------------------------------------------ the main measurement
def run(B_cond: int, B_refit: int, B_perm: int, write: bool = True, sides=SIDES) -> dict:
    t0 = time.time()
    rng = np.random.default_rng(SEED)
    if B_perm < B_PERM_MIN:
        print(f"NOTE: B_perm {B_perm} is under the registered {B_PERM_MIN}; a wiring check, "
              f"not the step H read", flush=True)
    cw = _career_war()
    manifests = {s: load_manifest(s) for s in sides}
    for s in sides:
        if manifests[s] is None:
            raise SystemExit(f"no arm manifest for {s} at {A.manifest_path(s)}: run step F "
                             f"(tools/efv_fwar_epoch_arms.py) first")

    pools, ys, series_receipts, parity, estar_rows, estar_flags = {}, {}, {}, {}, {}, {}
    for side in sides:
        raw = arm_rows(side, manifests[side], "Estar")
        if raw is None:
            raise SystemExit(f"{side}: the Estar arm matrix is missing from the manifest")
        flags = arm_flags(manifests[side], "Estar")
        estar_rows[side], estar_flags[side] = raw, flags
        keys = {r["player_key"] for r in raw if r.get("kind") == "debuted"}
        built = build_series(cw, keys, rng)
        series, series_receipts[side] = built["series"], built["receipts"]
        own = relabel(raw, series["fwar"], flags)
        bad = parity_mismatches(raw, own)
        parity[side] = {"rows_checked": sum(1 for r in raw if r.get("kind") == "debuted"),
                        "mismatches": len(bad), "first": bad[:10]}
        if bad:
            raise SystemExit(f"{side}: relabelling Estar on its own basis does not reproduce "
                             f"{len(bad)} stored labels ({bad[:5]}); the bases would not be paired")
        a2 = bool(flags.get(A2_FLAG, False))
        base_pool = None
        ys[side] = {}
        for b in BASES:
            P = pool_for(side, relabel(raw, series[b], flags), "debuted", a2)
            if base_pool is None:
                base_pool = P
            elif P["pk"] != base_pool["pk"]:
                raise SystemExit(f"basis {b} changed the {side} row set; comparisons "
                                 f"would not be paired")
            ys[side][b] = P["y"]
        pools[side] = base_pool
        print(f"  {side}: {base_pool['n']} rows, lambda {base_pool['lam']}, A2 {a2}, "
              f"series {series_receipts[side]}", flush=True)

    # ---- clause (b): the cross-label matrix (incumbent column = eWAR v2, note 2)
    cross = {}
    for side in sides:
        D = pools[side]
        cells = {}
        for fit_b in BASES:
            for sc_b in ("ewar_v2", "fwar"):
                m = margin_of(chain_cross(D, ys[side][fit_b], ys[side][sc_b]))
                if m:
                    cells[f"fit_{fit_b}__score_{sc_b}"] = m
        same_f = cells["fit_fwar__score_fwar"]["margin"]
        same_e = cells["fit_ewar_v2__score_ewar_v2"]["margin"]
        cells["_diagonal_difference"] = round(same_f - same_e, 5)
        cells["_reading"] = (
            "diagonal difference = the basis's effect on the margin. The off-diagonal cells "
            "separate 'the model learned the new label' (fit_fwar__score_ewar_v2) from 'the "
            "label got easier for everyone' (fit_ewar_v2__score_fwar). Rows are the Estar arm; "
            "every other factor is held at its Estar value, so this cell isolates the basis.")
        cross[side] = cells

    # ---- clause (e) 3: per-fold signs on the diagonal difference
    folds = {}
    for side in sides:
        D = pools[side]
        ff = per_fold_margins(D, ys[side]["fwar"], ys[side]["fwar"])
        fe = per_fold_margins(D, ys[side]["ewar_v2"], ys[side]["ewar_v2"])
        common = sorted(set(ff) & set(fe))
        diffs = {y: round(ff[y] - fe[y], 5) for y in common}
        pos = sum(1 for v in diffs.values() if v > 0)
        folds[side] = {"n_folds": len(common), "per_fold_difference": diffs,
                       "folds_positive": pos, "folds_negative": len(common) - pos,
                       "meets_4_fold_rule": len(common) >= MIN_TIME_SPLITS,
                       "headline_admissible": len(common) >= MIN_TIME_SPLITS}

    # ---- clause (d): TOST on the diagonal difference, E_cond primary
    tost, boot = {}, {}
    for side in sides:
        D = pools[side]
        pf = chain_cross(D, ys[side]["fwar"], ys[side]["fwar"])
        pe = chain_cross(D, ys[side]["ewar_v2"], ys[side]["ewar_v2"])
        n_te = len(pf[3])
        point = margin_of(pf)["margin"] - margin_of(pe)["margin"]
        cond = []
        for _ in range(B_cond):
            sel = rng.integers(0, n_te, n_te)
            cond.append(margin_from_parts(pf, sel) - margin_from_parts(pe, sel))
        cond = np.array([v for v in cond if np.isfinite(v)], dtype=float)
        refit = []
        for i in range(B_refit):
            sel = rng.integers(0, D["n"], D["n"])
            a = margin_of(chain_cross(D, ys[side]["fwar"], ys[side]["fwar"], sel=sel))
            b = margin_of(chain_cross(D, ys[side]["ewar_v2"], ys[side]["ewar_v2"], sel=sel))
            if a and b:
                refit.append(a["margin"] - b["margin"])
            if B_refit >= 100 and (i + 1) % 100 == 0:
                print(f"  {side} E_refit {i+1}/{B_refit}  {time.time()-t0:.0f}s", flush=True)
        refit = np.array([v for v in refit if np.isfinite(v)], dtype=float)
        ci_c = _ci(cond)
        tost[side] = {
            "point_difference": round(float(point), 5),
            "E_cond_ci95": ci_c,
            "E_cond_sd": round(float(cond.std(ddof=1)), 5) if len(cond) > 1 else None,
            "E_refit_ci95": _ci(refit),
            "E_refit_sd": round(float(refit.std(ddof=1)), 5) if len(refit) > 1 else None,
            "tost_margin": TOST_MARGIN, "disposition": tost_disposition(ci_c),
            "estimator_note": "E_cond is primary; E_refit is reported beside it.",
            "floors_note": "nine of the thirteen standard cells carry E_cond floors of 0.0203 "
                           "to 0.0322 (note 4); UNDECIDED is the expected pitcher reading",
        }
        boot[side] = {"B_cond_used": int(len(cond)), "B_refit_used": int(len(refit))}

    # ---- clause (e) 1 and 2: the twin and the permutation band, within (season, side)
    controls = {}
    for side in sides:
        D = pools[side]
        raw, flags = estar_rows[side], estar_flags[side]
        keys = {r["player_key"] for r in raw if r.get("kind") == "debuted"}
        twin_m = margin_of(chain_cross(D, ys[side]["twin"], ys[side]["twin"]))
        same_f = cross[side]["fit_fwar__score_fwar"]["margin"]
        same_e = cross[side]["fit_ewar_v2__score_ewar_v2"]["margin"]
        band = []
        for i in range(B_perm):
            s2 = twin_series(cw, keys, np.random.default_rng(SEED + 1000 + i))
            P = pool_for(side, relabel(raw, s2, flags), "debuted", D["a2"])
            if P["pk"] != D["pk"]:
                continue
            m = margin_of(chain_cross(D, P["y"], P["y"]))
            if m:
                band.append(m["margin"] - same_e)
            if B_perm >= 20 and (i + 1) % 20 == 0:
                print(f"  {side} perm {i+1}/{B_perm}  {time.time()-t0:.0f}s", flush=True)
        band = np.array(band, dtype=float)
        obs = same_f - same_e
        controls[side] = {
            "zero_information_twin_margin": twin_m,
            "twin_minus_ewar_v2": round(twin_m["margin"] - same_e, 5) if twin_m else None,
            "observed_difference": round(obs, 5),
            "permutation_B": int(len(band)),
            "permutation_B_meets_registered_minimum": bool(len(band) >= B_PERM_MIN),
            "permutation_band_ci95": _ci(band) if len(band) else None,
            "p_two_sided": (round(float((np.abs(band) >= abs(obs)).mean()), 4)
                            if len(band) else None),
            "permuted_within": "(season, side)",
            "reading": ("if the twin's difference matches the observed one, there is no "
                        "result to attribute to the basis"),
        }

    # ---- clause (i): the arm table and each candidate's own clauses
    arms_out, candidates = {}, {}
    for side in sides:
        man = manifests[side]
        q_by_arm: dict[str, dict | None] = {}
        rows_by_arm: dict[str, list[dict] | None] = {}
        for arm in A.ARMS:
            rows = arm_rows(side, man, arm)
            rows_by_arm[arm] = rows
            if rows is None:
                q_by_arm[arm] = None
                print(f"  {side} {arm}: UNAVAILABLE", flush=True)
                continue
            q_by_arm[arm] = arm_quantities(side, rows, arm_flags(man, arm))
            print(f"  {side} {arm}: margin_debuted {q_by_arm[arm]['margin_debuted']} "
                  f"full_pool {q_by_arm[arm]['margin_full_pool']}  {time.time()-t0:.0f}s", flush=True)
        table = arm_table(q_by_arm, man)
        arms_out[side] = {"quantities_by_arm": q_by_arm, "table": table,
                          "omitted": man.get("omitted") or {},
                          "manifest_generated_at": man.get("generated_at"),
                          "arm_sha256": {a: (man["arms"].get(a) or {}).get("sha256") for a in A.ARMS}}
        est = rows_by_arm.get("Estar") or []
        census_estar = ((man.get("arms") or {}).get("Estar") or {}).get("census") or {}
        candidates[side] = {
            "F3_arm_r": arm_r_clauses(side, est, rows_by_arm.get("F3"), rng, B_cond, estar_flags[side]),
            "F4_a1": a1_clauses(side, est, rows_by_arm.get("F4"), census_estar),
            "F5_a2": a2_clauses(side, est, rows_by_arm.get("F5"), estar_flags[side]),
            "a1_a2_sign_agreement": sign_agreement(table),
            "F1_F2": "owner decisions (O1, O2): ship regardless, no ship clause (part 0)",
        }
        print_candidate_clauses(side, candidates[side])

    out = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "produced_by": "tools/efv_fwar_label_epoch_lab.py",
        "gate": GATE, "bust2": BUST2,
        "substitution": "bWAR reads eWAR v2 (incumbent); eWAR reads published fWAR (candidate)",
        "seed": SEED,
        "elapsed_s": round(time.time() - t0, 1),
        "strata": "side, season, fold, debut cohort band; never a consensus-FV cell",
        "bootstrap": boot,
        "label_bases": {
            "definitions": {
                "ewar_v2": f"career_war.{INCUMBENT_KEY} (the incumbent the step C rebase keeps)",
                "fwar": f"career_war.{CANDIDATE_KEY} (published fWAR, as the table serves it)",
                "twin": "eWAR v2 plus the fWAR-minus-eWAR v2 deltas permuted across players "
                        "within (season, side)",
            },
            "rows": "the Estar arm of step F, relabelled per basis under Estar's own window rule",
            "receipts": series_receipts, "parity": parity,
        },
        "clause_b_cross_label_matrix": cross,
        "clause_c_coverage": coverage(cw, pools),
        "clause_d_tost": tost,
        "clause_e_controls": controls,
        "clause_e_folds": folds,
        "clause_i_arms": arms_out,
        "candidate_clauses": candidates,
        "clause_f_blast_radius": "run tools/efv_fwar_label_epoch_lab.py --blast (per arm, step A snapshot)",
        "clause_l": "movement is not accuracy; nothing here is an accuracy claim",
    }
    if write:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", OUT_PATH)
    return out


# ------------------------------------------------------------------ clause (f)
def _snapshot_dir() -> Path:
    """The step A snapshot, checked: present, and not a forbidden name."""
    snap = Path(SNAP_DIR)
    for bad in FORBIDDEN_SNAPSHOT_NAMES:
        if snap.name == bad or snap.name.startswith(bad):
            raise SystemExit(f"refusing the snapshot {snap}: {bad} is the previous epoch's "
                             f"evidence or the archive and is never read")
    if not snap.exists():
        raise SystemExit(f"no snapshot at {snap}; clause (f) cannot be measured. Step A "
                         f"writes it; this lab never creates it")
    return snap


def _snap_load(snap: Path, name: str):
    a = snap / name
    b = ROOT / "data" / name
    if snap not in a.resolve().parents:
        raise SystemExit(f"refusing to read outside the snapshot: {a}")
    if not a.exists() or not b.exists():
        return None, None
    return (json.loads(a.read_text(encoding="utf-8")),
            json.loads(b.read_text(encoding="utf-8")))


def board_diff(old: dict, new: dict) -> dict:
    ob, nb = old.get("by_player", {}), new.get("by_player", {})
    shared = sorted(set(ob) & set(nb))

    def _ranked(bp, keys):
        vals = [(k, bp[k].get("xfv_war_6yr")) for k in keys]
        vals = [(k, v) for k, v in vals if isinstance(v, (int, float))]
        vals.sort(key=lambda kv: -kv[1])
        return {k: i + 1 for i, (k, _) in enumerate(vals)}

    ro, rn = _ranked(ob, shared), _ranked(nb, shared)
    common = sorted(set(ro) & set(rn))
    d = np.array([abs(ro[k] - rn[k]) for k in common], dtype=float)
    gd = [abs((nb[k].get("xfv_grade") or 0) - (ob[k].get("xfv_grade") or 0)) for k in common]
    gd = np.array([g for g in gd if np.isfinite(g)], dtype=float)
    out = {
        "rows_compared": len(common),
        "rows_moved": int((d > 0).sum()),
        "rank_delta_median": float(np.median(d)) if len(d) else None,
        "rank_delta_p90": float(np.percentile(d, 90)) if len(d) else None,
        "rank_delta_max": float(d.max()) if len(d) else None,
        "grade_moved_rows": int((gd > 1e-9).sum()) if len(gd) else 0,
        "grade_delta_mean": round(float(gd.mean()), 4) if len(gd) else None,
    }
    for cut in (10, 25, 100, 250):
        a = {k for k in common if ro[k] <= cut}
        b = {k for k in common if rn[k] <= cut}
        out[f"membership_change_top{cut}"] = len(a ^ b) // 2
    return out


def star_diff(old, new) -> dict:
    def _flat(o):
        if isinstance(o, dict):
            for k in ("by_player", "players", "rows"):
                v = o.get(k)
                if isinstance(v, dict):
                    return v
                if isinstance(v, list):
                    return {r.get("player_key"): r for r in v
                            if isinstance(r, dict) and r.get("player_key")}
        return o if isinstance(o, dict) else {}
    a, b = _flat(old), _flat(new)
    keys = set(a) & set(b)

    def _star(r):
        for k in ("is_star", "star", "star_window", "star_career"):
            if k in r:
                return bool(r[k])
        return None
    flips = sum(1 for k in keys if _star(a[k]) != _star(b[k]))
    changed = sum(1 for k in keys
                  if json.dumps(a[k], sort_keys=True) != json.dumps(b[k], sort_keys=True))
    return {"compared": len(keys), "star_flag_flips": flips, "rows_changed_any_field": changed,
            "added": len(set(b) - set(a)), "dropped": len(set(a) - set(b))}


def per_arm_blast(sides=SIDES) -> dict:
    """Clause (f) PER ARM (note 5), from what a matrix carries: the row census of E0,
    Estar and each leave-one-out arm, UNAVAILABLE for an omitted or missing arm. The served
    items that need a rebuilt surface per arm (board re-rank, surplus channels, WAG flips,
    star labels, arbitration, the projections pins) are measured by EPOCH_RUN from served
    rebuilds and are named here as UNAVAILABLE from a matrix alone, never estimated."""
    out = {}
    for side in sides:
        man = load_manifest(side)
        if man is None:
            out[side] = {"status": "UNAVAILABLE", "reason": "no arm manifest; run step F"}
            continue
        per = {}
        for arm in A.ARMS:
            if arm in (man.get("omitted") or {}):
                per[arm] = {"status": "UNAVAILABLE", "reason": man["omitted"][arm].get("reason"),
                            "note": "FAILED ARM: never inferred"}
                continue
            rows = arm_rows(side, man, arm)
            if rows is None:
                per[arm] = {"status": "UNAVAILABLE", "reason": "arm matrix missing"}
                continue
            e = man["arms"][arm]
            per[arm] = {"census": row_census(rows), "flags": e.get("flags"),
                        "sha256": e.get("sha256"), "factor_reverted": e.get("factor_reverted")}
        out[side] = {"per_arm": per,
                     "served_items_per_arm": "UNAVAILABLE from a matrix alone (board re-rank, "
                                             "surplus channels, WAG flips, star labels, "
                                             "arbitration, projections pins): measured by "
                                             "EPOCH_RUN from served rebuilds, never estimated here"}
    return out


def blast(write: bool = True) -> dict:
    """Diff the served artifacts against the step A snapshot (the shipped configuration),
    plus the per-arm block. Read-only on the snapshot."""
    snap = _snapshot_dir()
    out: dict = {"snapshot": snap.name,
                 "snapshot_note": "a sibling directory of the repo root, not published",
                 "gate": GATE, "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    old, new = _snap_load(snap, "xfv.json")
    if old and new:
        out["board"] = board_diff(old, new)
        out["board"]["pinned_mix_note"] = ("test_board_basis_coherence.PINNED_MIX is read against "
                                           "Estar only (note 5), by that test")
    old, new = _snap_load(snap, "star_label_view.json")
    if old and new:
        out["star_label"] = star_diff(old, new)
    out["shipped_configuration_note"] = ("the served diff above is the SHIPPED configuration; "
                                         "clause (i) point 5 names it in part 9 if it differs "
                                         "from Estar as built")
    out["per_arm"] = per_arm_blast()
    if write:
        BLAST_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        print("wrote", BLAST_PATH)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--quick", action="store_true", help="small B, for wiring checks")
    ap.add_argument("--blast", action="store_true", help="clause (f) against the snapshot")
    ap.add_argument("--b-cond", type=int, default=2000)
    ap.add_argument("--b-refit", type=int, default=400)
    ap.add_argument("--b-perm", type=int, default=B_PERM_MIN)
    ap.add_argument("--side", default="both", choices=(*SIDES, "both"))
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    if a.blast:
        print(json.dumps(blast(write=not a.no_write), indent=1))
        return 0
    if a.quick:
        a.b_cond, a.b_refit, a.b_perm = 50, 5, 3
    sides = SIDES if a.side == "both" else (a.side,)
    out = run(a.b_cond, a.b_refit, a.b_perm, write=not a.no_write, sides=sides)
    print(json.dumps({"clause_b": out["clause_b_cross_label_matrix"],
                      "clause_d": out["clause_d_tost"],
                      "clause_i_tables": {s: out["clause_i_arms"][s]["table"] for s in sides}},
                     indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
