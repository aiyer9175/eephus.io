# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Shared harness for prototyping the PITCHER LABEL INSTRUMENT.

=============================================================================
INVALID AS A GATE. DO NOT SHIP ANYTHING ON THIS HARNESS'S NUMBERS.
Refuted 2026-07-24 by its own adversarial verification (docs/PITCHER_LABEL_LEDGER.md).
Three independent defects, all measured:

  1. IT MEASURES LABEL DAMAGE, NOT LABEL INFORMATION. Zero-information control
     labels on the mid block score: constant-at-KM-mean 86.8% of "headroom",
     uniform noise 113.0%, a rank-identical "+1.8" level shift 37.3%. The
     KM-labelled censored block is actively destructive to the small unweighted
     ridge, so ANYTHING that neutralizes its leverage scores well while carrying
     no information. Percentages off this harness are meaningless without a
     rank-identical level twin and a random-label null band printed beside them.
  2. THE FIT IS NOT THE SHIPPED FIT. _model_arm below trains 348 resolved
     debuted rows UNWEIGHTED. Production (prospect_path._fit_ridge sample_weight
     = observed_seasons/6, efv_model.fit_production_stack) trains ~1989 pitcher
     rows INCLUDING ~1008 busts, which drops the censored block's leverage from
     37.9% to 14.3%. Under production config a PERFECT label is worth +0.0518 at
     span 3 and +0.0248 at production's real mixed spans, NOT the +0.1096 this
     harness reports.
  3. THE EFFECT IS INSIDE THE NOISE FLOOR. Permutation null (B=1500, mid labels
     shuffled, marginal preserved): the ORACLE itself has p(null >= real) = 0.183.
     Test-only bootstrap understates sd by 1.6-1.8x; the honest arm-level sd on
     blend Spearman is ~0.074-0.09 against effects of ~0.02.

To rebuild it correctly see "Arm 0" in docs/PITCHER_LABEL_LEDGER.md: production
fit config, real mixed spans (2021@5 / 2022@4 / 2023@3 / 2024@2), the three
mandatory controls, train-resampling bootstrap, >=6 averaged time splits, and pin
_BLEND_LAMBDA_RESELECT["pit"] for the duration of any label experiment.
=============================================================================

Context (docs/SURROGATE_LABEL_PROGRAM.md, 2026-07-24 gate): for pitchers the ORACLE
(true first-6yr WAR on the recently-censored cohorts) nearly doubles model rank vs the
shipped KM censoring (0.226 vs 0.122), so pitcher LABELS carry large real headroom. The
univariate 3-season WAR surrogate is too noisy to capture it (rho 0.768 vs true on the
mid cohorts) and only ties KM. This harness exists to find an instrument that does.

Every candidate is measured IDENTICALLY here, on two axes:
  LABEL FIDELITY  instrument(mid) vs TRUE first-6yr WAR on the mid cohorts (rho + MAE)
  MODEL LIFT      train the eFV pitcher model on {early true + mid instrument-label},
                  test on the now-resolved 2019-2020 cohorts' TRUE WAR (rho + MAE)

Production-mirroring simulation (leakage-clean, strictly time-ordered):
  early 2011-2015 resolved  -> fit the instrument (the deep historical window)
  mid   2016-2018 resolved  -> stand in for "recently censored"; get an instrument label
  test  2019-2020 resolved  -> held out, scored against TRUE first-6yr WAR

HARD DESIGN CONSTRAINT (circularity): an instrument may use ONLY post-debut REALIZED
outcome data (WAR, IP, role, rates, injury, age). It must NEVER use a pre-debut scouting
feature (consensus FV, tool grades, draft pick/bonus) - those are the MODEL's predictors,
and a label built from them would teach the model to reproduce its own inputs.

API for a candidate instrument:
    def fit(train_rows) -> state            # train_rows = early cohort, each with .true6
    def predict(state, row, span) -> float  # first-6yr-WAR-equivalent from `span` seasons
Register it in CANDIDATES (see efv_pitcher_label_lab.py) and the gate runs it.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import storage                                       # noqa: E402
import milb_history as mh                            # noqa: E402
from prospect_path import _spearman, _score, _fit_ridge, _predict   # noqa: E402
from efv_model import _vec, _fit_ols_fv, _pred_ols, _feature_spec   # noqa: E402

DATA = ROOT / "data"
TARGET_SEASONS = 6
EARLY = (2011, 2015)
MID = (2016, 2018)
TEST = (2019, 2020)
LAM_PIT = 0.63            # shipped-ish pitcher blend weight; identical across arms


# ---------------------------------------------------------------------------
# pool assembly
# ---------------------------------------------------------------------------

def _career_war():
    out = {}
    with storage.connect() as con:
        for r in con.execute("SELECT player_key, payload_json FROM career_war"):
            try:
                out[r["player_key"]] = {int(y): float(w) for y, w
                                        in (json.loads(r["payload_json"]) or {}).get("seasons", {}).items()}
            except ValueError:
                pass
    return out


def _overrides():
    """Verified mlbam id backfills (debuted + bust). The instrument needs an id to
    read MLB season lines; ~60% of old resolved pitcher rows lack a native one."""
    ov = {}
    for name in ("mlbam_id_overrides.json", "mlbam_id_overrides_busts.json"):
        p = DATA / "sources" / name
        if p.exists():
            try:
                ov.update({str(k): int(v) for k, v in json.loads(p.read_text(encoding="utf-8")).items()})
            except ValueError:
                pass
    return ov


def _mlb_pitch_index(lo=2011, hi=2026):
    idx = {}
    for season in range(lo, hi + 1):
        for r in mh.season_splits(1, season, "pitching", fetch=False):
            if r.get("mlbam"):
                idx.setdefault(int(r["mlbam"]), {})[season] = r
    return idx


def _tj_index():
    p = DATA / "tj_surgery.json"
    if not p.exists():
        return {}
    try:
        players = json.loads(p.read_text(encoding="utf-8")).get("players", {})
    except ValueError:
        return {}
    return {int(k): sorted(s.get("year") for s in v if s.get("year")) for k, v in players.items()}


def _f(v, d=0.0):
    try:
        return float(v)
    except (TypeError, ValueError):
        return d


def build_pool(side: str = "pit"):
    """Resolved debuted rows + their post-debut realized early-career record."""
    mf = "xfv_pitcher_matrix.json" if side == "pit" else "xfv_hitter_matrix.json"
    rows = json.loads((DATA / mf).read_text(encoding="utf-8"))
    cw, ov, midx, tj = _career_war(), _overrides(), _mlb_pitch_index(), _tj_index()
    pool = []
    for r in rows:
        if r["kind"] != "debuted" or r.get("censored"):
            continue
        if r.get("target_resolved") is None or r.get("consensus_fv_raw") is None:
            continue
        pk, dy = r["player_key"], r.get("debut_year")
        if dy is None:
            continue
        seasons_war = cw.get(pk) or {}
        mid_ = r.get("mlbam_id") or ov.get(pk)
        lines = midx.get(int(mid_), {}) if mid_ else {}
        rec = {
            "pk": pk, "mlbam": int(mid_) if mid_ else None, "dy": int(dy),
            "true6": float(r["target_resolved"]),
            "row": r,                                  # for _vec (MODEL features only)
            "war": {i: _f(seasons_war.get(dy + i)) for i in range(TARGET_SEASONS)},
            "lines": {i: lines.get(dy + i) for i in range(TARGET_SEASONS)},
            "tj_years": tj.get(int(mid_), []) if mid_ else [],
        }
        pool.append(rec)
    return pool


def window(rec: dict, span: int) -> dict:
    """Post-debut REALIZED features over the first `span` seasons. Outcome data only:
    no scouting/draft inputs (see the circularity constraint in the module docstring)."""
    war = sum(rec["war"].get(i, 0.0) for i in range(span))
    ip = g = gs = so = bb = bf = er_ip = 0.0
    seen = 0
    for i in range(span):
        ln = rec["lines"].get(i)
        if not ln:
            continue
        seen += 1
        ip += _f(ln.get("ip")); g += _f(ln.get("g")); gs += _f(ln.get("gs"))
        so += _f(ln.get("so")); bb += _f(ln.get("bb")); bf += _f(ln.get("bf"))
        er_ip += _f(ln.get("era")) * _f(ln.get("ip"))
    dy = rec["dy"]
    tj_in = sum(1 for y in rec["tj_years"] if dy <= y < dy + span)
    tj_pre = sum(1 for y in rec["tj_years"] if y < dy)
    return {
        "war": war, "war_per_season": war / max(1, span),
        "ip": ip, "ip_per_season": ip / max(1, span),
        "g": g, "gs": gs, "gs_ratio": (gs / g) if g else 0.0,
        "k_pct": (so / bf) if bf else 0.0, "bb_pct": (bb / bf) if bf else 0.0,
        "kbb": ((so - bb) / bf) if bf else 0.0,
        "era": (er_ip / ip) if ip else 0.0,
        "war_per_ip": (war / ip) if ip else 0.0,
        "seasons_pitched": float(seen), "lines_missing": 1.0 if seen == 0 else 0.0,
        "tj_in_window": float(tj_in), "tj_pre_debut": float(tj_pre),
        "span": float(span),
    }


def km_label(rec: dict, span: int) -> float:
    """The SHIPPED censoring label: obs_sum * (6/n_obs). The bar to beat."""
    war = sum(rec["war"].get(i, 0.0) for i in range(span))
    return war * (TARGET_SEASONS / max(1, span))


# ---------------------------------------------------------------------------
# the gate
# ---------------------------------------------------------------------------

def _split(pool):
    def grp(lo, hi):
        return [r for r in pool if lo <= r["dy"] <= hi]
    return grp(*EARLY), grp(*MID), grp(*TEST)


def _model_arm(train_pairs, test_recs, side="pit"):
    """Fit the eFV model on (rec, label) pairs; score on test TRUE WAR. Blend ==
    the shipped headline: (1-lam)*consensus_OLS + lam*ridge."""
    keys, _m = _feature_spec(side)
    data = [{"feats": _vec(r["row"], side), "target": float(t), "fv": float(r["row"]["consensus_fv_raw"]),
             "player_key": r["pk"]}
            for r, t in train_pairs if t is not None]
    ridge = _fit_ridge(data, keys)
    ols = _fit_ols_fv(data)
    if not ridge or not ols:
        return None
    lam = LAM_PIT if side == "pit" else 0.85
    rp, bp = [], []
    for r in test_recs:
        f = _vec(r["row"], side)
        p = _predict(ridge, f)
        rp.append((p, r["true6"]))
        bp.append(((1 - lam) * max(0.0, _pred_ols(ols, float(r["row"]["consensus_fv_raw"]))) + lam * p,
                   r["true6"]))
    return {"ridge": _score(rp), "blend": _score(bp)}


def run_gate(candidates: dict, span: int = 3, side: str = "pit", verbose=True):
    """candidates: {name: (fit_fn, predict_fn)}. Returns the full result dict."""
    pool = build_pool(side)
    early, mid, test = _split(pool)
    if verbose:
        cov = sum(1 for r in pool if r["mlbam"]) / max(1, len(pool))
        print(f"[{side}] pool={len(pool)} early={len(early)} mid={len(mid)} test={len(test)} "
              f"| mlbam coverage {cov:.0%} | span={span}")
    out = {"side": side, "span": span, "n_early": len(early), "n_mid": len(mid),
           "n_test": len(test), "label_fidelity": {}, "model": {}}

    true_mid = [r["true6"] for r in mid]

    def fidelity(labels):
        pr = [(l, t) for l, t in zip(labels, true_mid) if l is not None]
        if len(pr) < 5:
            return {"n": len(pr)}
        return {"n": len(pr),
                "spearman": round(_spearman([a for a, _ in pr], [b for _, b in pr]), 4),
                "mae": round(sum(abs(a - b) for a, b in pr) / len(pr), 3)}

    # --- reference arms -----------------------------------------------------
    km = [km_label(r, span) for r in mid]
    out["label_fidelity"]["KM_baseline"] = fidelity(km)
    out["model"]["A_KM_baseline"] = _model_arm(
        [(r, r["true6"]) for r in early] + list(zip(mid, km)), test, side)
    out["model"]["C_oracle"] = _model_arm(
        [(r, r["true6"]) for r in early] + [(r, r["true6"]) for r in mid], test, side)
    out["label_fidelity"]["C_oracle"] = {"n": len(mid), "spearman": 1.0, "mae": 0.0}

    # --- candidates ---------------------------------------------------------
    for name, (fit_fn, pred_fn) in candidates.items():
        try:
            state = fit_fn(early)
            labels = [pred_fn(state, r, span) for r in mid]
            out["label_fidelity"][name] = fidelity(labels)
            out["model"][name] = _model_arm(
                [(r, r["true6"]) for r in early] + list(zip(mid, labels)), test, side)
        except Exception as e:                                   # noqa: BLE001
            out["label_fidelity"][name] = {"error": str(e)}
            out["model"][name] = None

    if verbose:
        _report(out)
    return out


def _report(out):
    print(f"\n  LABEL FIDELITY (instrument vs TRUE 6yr WAR on mid, n={out['n_mid']})")
    print(f"    {'label':22} {'rho':>7} {'mae':>7}")
    for k, v in out["label_fidelity"].items():
        if "spearman" in v:
            print(f"    {k:22} {v['spearman']:>7.4f} {v['mae']:>7.3f}")
    print(f"\n  MODEL LIFT (train on that label; test on 2019-20 TRUE WAR, n={out['n_test']})")
    print(f"    {'arm':22} {'ridge_rho':>9} {'blend_rho':>9} {'blend_mae':>9}")
    base = out["model"].get("A_KM_baseline")
    orac = out["model"].get("C_oracle")
    for k, v in out["model"].items():
        if not v:
            print(f"    {k:22} {'FAILED':>9}")
            continue
        print(f"    {k:22} {v['ridge']['spearman']:>9.4f} {v['blend']['spearman']:>9.4f} "
              f"{v['blend']['mae']:>9.3f}")
    if base and orac:
        print(f"\n  headroom: KM blend {base['blend']['spearman']:.4f} -> "
              f"oracle {orac['blend']['spearman']:.4f} "
              f"(+{orac['blend']['spearman']-base['blend']['spearman']:.4f})")
        for k, v in out["model"].items():
            if k in ("A_KM_baseline", "C_oracle") or not v:
                continue
            gain = v["blend"]["spearman"] - base["blend"]["spearman"]
            span_ = orac["blend"]["spearman"] - base["blend"]["spearman"]
            pct = (gain / span_ * 100) if span_ else 0.0
            print(f"    {k:22} gain {gain:+.4f}  = {pct:5.1f}% of the oracle headroom")
