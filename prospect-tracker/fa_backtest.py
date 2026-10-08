# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""HARD GATES for the MLB Free Agency module's models.

Gate 1 (projection): train through season N-1, project season N, for every
target season in fa_config projection.eval.target_seasons. NO LOOKAHEAD:
aging curves, the WAR map, and band sigmas are all refitted per target on
data strictly before it (band sigmas roll forward from PREVIOUS targets'
residuals, seeded by two warmup targets excluded from the gate metrics).

Baseline to beat: the 5/4/3 weighted average of each player's ACTUAL
final-metric seasons — no regression, no aging, classic naive carry-forward.

Pass criteria (ship/no-ship):
  - pooled model MAE < baseline MAE on ALL of WAR, wRC+ (PA>=150), FIP (BF>=150)
  - P10-P90 band coverage on WAR within [0.75, 0.85]

Population honesty: every player with >=1 input season is predicted; a
player ABSENT from the target season scores actual WAR = 0 (they delivered
nothing) for BOTH model and baseline; rate metrics evaluate only where the
target season has real exposure (disclosed thresholds). The age-30+ slice
(the FA-relevant population) is reported alongside the full pool.

Results persist to fa_model_eval (the Model Accountability surface renders
them verbatim) — misses and all.
"""

from __future__ import annotations

import argparse
import logging
import math
import statistics
from collections import defaultdict

import fa_class
import fa_projection as fp
import storage

log = logging.getLogger(__name__)

MODEL_VERSION = "fa_proj_v1"
WARMUP_TARGETS = [2013, 2014]          # seed band sigmas; excluded from gate metrics


def _actual_metrics(row: dict, side: str, league: dict) -> dict:
    """Actual final metrics for one corpus row, computed with the SAME
    assembly the projections use (consistent comparison)."""
    out = {"war": row.get("war"), "expo": row.get("pa" if side == "hit" else "bf") or 0}
    if side == "hit":
        a = fp._assemble_hitter({**row, "babip": row.get("babip") or 0.29},
                                league, row["season"] + 1)
        out["wrc_plus"] = a["wrc_plus_proj"]
    else:
        out["fip"] = row.get("fip")
    return out


def _baseline(history: list[dict], side: str, target: int, league: dict) -> dict:
    """5/4/3 weighted average of the player's ACTUAL final metrics — the
    naive carry-forward the model must beat. Rate metrics exposure-weighted;
    WAR plain 5/4/3 over present seasons."""
    weights = {1: 5.0, 2: 4.0, 3: 3.0}
    wn = wd = 0.0
    rn = rd = 0.0
    for h in history:
        lag = target - h["season"]
        if lag not in weights:
            continue
        w = weights[lag]
        if h.get("war") is not None:
            wn += w * h["war"]; wd += w
        act = _actual_metrics(h, side, league)
        rate = act.get("wrc_plus") if side == "hit" else act.get("fip")
        expo = act["expo"]
        if rate is not None and expo > 0:
            rn += w * expo * rate; rd += w * expo
    return {"war": (wn / wd) if wd else None,
            ("wrc_plus" if side == "hit" else "fip"): (rn / rd) if rd else None}


def _mae(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    return sum(abs(p - a) for p, a in pairs) / len(pairs)


def _rmse(pairs: list[tuple[float, float]]) -> float | None:
    if not pairs:
        return None
    return math.sqrt(sum((p - a) ** 2 for p, a in pairs) / len(pairs))


def _bias(pairs: list[tuple[float, float]]) -> float | None:
    """Signed mean error (pred - actual). MAE alone cannot tell a side
    correction which way to move; every sliced metric reports this too."""
    if not pairs:
        return None
    return sum(p - a for p, a in pairs) / len(pairs)


def _cell(pairs: list[tuple[float, float]], base: list[tuple[float, float]] | None = None) -> dict:
    """One reported slice: MAE + signed bias + levels, for model (and baseline).
    `bias_model` is mean(pred - actual): positive means the cell is OVER-stated."""
    n = len(pairs)
    out = {"mae_model": _mae(pairs), "bias_model": _bias(pairs), "n": n,
           "mean_pred": (sum(p for p, _ in pairs) / n) if n else None,
           "mean_actual": (sum(a for _, a in pairs) / n) if n else None}
    if base is not None:
        out["mae_base"] = _mae(base)
        out["bias_base"] = _bias(base)
    return out


# E1 (2026-07-30): Gate 1 reports WAR per SIDE as well as pooled. The owner's
# "overprojecting pitchers" read has to be tested against a measured per-side
# level, and MAE alone is sign-blind.
# Headline metrics stay EXACTLY these four: the Model Accountability surface
# renders Object.entries(gate1.pooled) verbatim (assets/fa.js:1131), so a slice
# added here would become a served table row. Slices live in `pooled_by_side`.
GATE1_HEADLINE = ("war", "wrc_plus", "fip", "war30")
# `*:act_ge4` are the star-compression DIAGNOSTIC cells (E2). They condition on
# the ACTUAL, so regression to the mean guarantees a negative bias there and the
# cell can never be a ship criterion on its own - it is read only as "how much
# of the star tail does the map reach", against the pooled MAE as the gate.
# `expo:*` are the E3 playing-time cells: PROJECTED exposure vs ACTUAL, scored
# only where the target season exists with real exposure (a player who never
# appears has actual 0, which is an attendance fact, not a playing-time miss).
# Hitters in PA, pitchers in BF. This is the 456-vs-511 cell.
GATE1_SLICES = ("war:hit", "war:pit", "war:hit:act_ge4", "war:pit:act_ge4",
                "expo:hit", "expo:pit")
GATE1_METRICS = GATE1_HEADLINE + GATE1_SLICES

# Lab hook, same contract as GATE2_COLLECT below: set to a list and every scored
# WAR row is appended as (target, side, mlbam, pred, actual) so two model
# settings can be compared PAIRED ROW BY ROW. None in production.
GATE1_COLLECT: list | None = None


def _fit_band_scale(panel: list[dict]) -> dict:
    """Fit the T1.2 location-scale band on the Gate-1 residual panel and
    grade it, IN SAMPLE for the diagnostics and out of fold for the verdict.

    The out-of-fold verdict is not recomputed here (that is the lab's job and
    it is expensive); what is written is the fitted model the serve path
    consumes plus the honest served-side dispersion and the conditional
    coverage table. Returns {} when the panel is too thin, in which case the
    serve path keeps the four-bucket bands."""
    if not panel:
        return {}
    import fa_bands
    ages = [r["age"] for r in panel if r["age"] is not None]
    age_mean = statistics.mean(ages) if ages else 29.0
    Z = [fa_bands.war_z(r["side"], r["pred"], r["expo"], r["age"],
                        r["thin"], r["tj_n"], age_mean) for r in panel]
    model = fa_bands.fit(Z, [r["resid"] for r in panel],
                         [r["side"] for r in panel],
                         names=fa_bands.WAR_Z_NAMES, age_mean=age_mean)
    if model is None:
        return {}
    out = {"band_scale": model,
           "band_scale_widths": fa_bands.width_summary(
               model, [(z, r["side"]) for z, r in zip(Z, panel)])}
    # ZERO-INFORMATION CONTROL, written into the artifact next to the model:
    # the identical estimator on a row-permuted residual column must return a
    # flat sigma. If sigma_sd here is not ~0, the fit is reading noise.
    ctl = fa_bands.fit(Z, [r["resid"] for r in panel],
                       [r["side"] for r in panel],
                       names=fa_bands.WAR_Z_NAMES, age_mean=age_mean,
                       permute_seed=1)
    if ctl:
        out["band_scale_permuted_control"] = {
            "sigma_mean": round(ctl["sigma_mean"], 5),
            "sigma_sd": round(ctl["sigma_sd"], 5),
            "note": ("row-permuted residuals: sigma_sd must collapse toward 0. "
                     "Compare against band_scale.sigma_sd.")}
    # Conditional coverage of the fitted bands, which is the test the pooled
    # P10-P90 hit rate cannot do (it reads 0.79996 against nominal 0.80 and is
    # uninformative about whether the bands are calibrated anywhere).
    try:
        import fa_calibration as fc
        rows = []
        for z, r in zip(Z, panel):
            o = fa_bands.offsets(model, z, r["side"], (0.10, 0.90))
            if o:
                rows.append({"y": r["resid"], "q": {0.10: o[0.10], 0.90: o[0.90]},
                             "pred": r["pred"], "age": r["age"] or age_mean,
                             "expo": r["expo"], "tj": "tj" if r["tj_n"] else "none"})
        if rows:
            out["band_scale_conditional_coverage"] = {
                "marginal": fc.coverage(rows),
                "by_pred_decile": fc.conditional_coverage(
                    rows, lambda r: r["pred"], n_bins=10),
                "by_age": fc.conditional_coverage(
                    rows, lambda r: ("<25" if r["age"] < 25 else "25-29"
                                     if r["age"] < 30 else "30-34"
                                     if r["age"] < 35 else "35+")),
                "by_expo_decile": fc.conditional_coverage(
                    rows, lambda r: r["expo"], n_bins=10),
                "by_prior_tj": fc.conditional_coverage(rows, lambda r: r["tj"]),
            }
    except Exception:                                   # noqa: BLE001
        log.warning("band_scale conditional coverage failed - continuing")
    return out


def run_projection_gate(persist: bool = True, reexport: bool = True) -> dict:
    """Gate 1. ``persist=True`` writes the artifact and then, with ``reexport``
    (the default, owner answer M14-1), re-runs the FA export so the served
    sidecars follow the gate at once (reexport_fa_sidecars)."""
    cfg = fp._pcfg()
    corpus = fp.build_corpus()
    league = corpus["league"]
    targets = list(cfg["eval"]["target_seasons"])
    min_pa = cfg["eval"]["rate_eval_min_pa"]
    min_bf = cfg["eval"]["rate_eval_min_bf"]

    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r

    # rolling residual store for band sigmas: bucket -> [residuals]
    resid: dict[str, list[float]] = defaultdict(list)
    # T1.2 - the SAME residuals with their covariates attached, so the band
    # width can be a continuous function of the player instead of a two-bit
    # bucket. Collected here rather than in a second pass because this loop
    # is already the point-in-time one.
    panel: list[dict] = []
    try:
        import tj_surgery
        _tj_store = tj_surgery._load_store()
    except Exception:                      # noqa: BLE001 - fail soft to tj_n 0
        tj_surgery, _tj_store = None, {}

    def _bucket(side: str, expo_proj: float) -> str:
        lo = 350 if side == "hit" else 250
        return f"{side}:{'hi' if expo_proj >= lo else 'lo'}"

    per_season: list[dict] = []
    pooled = {k: {"m": [], "b": []} for k in GATE1_METRICS}
    coverage_hits = coverage_n = 0

    for target in WARMUP_TARGETS + targets:
        is_warmup = target in WARMUP_TARGETS
        curves, war_map = fp.fitted_models(corpus, target - 1)
        season_stats: dict = {k: {"m": [], "b": []} for k in GATE1_METRICS}
        season_stats["cov_hits"] = 0
        season_stats["cov_n"] = 0
        new_resid: dict[str, list[float]] = defaultdict(list)
        for side in ("hit", "pit"):
            rate_key = "wrc_plus" if side == "hit" else "fip"
            for mlbam, seasons in by_player[side].items():
                hist = [seasons[s] for s in (target - 1, target - 2, target - 3) if s in seasons]
                if not hist:
                    continue
                age_prev = next((h.get("age") for h in hist if h.get("age")), None)
                age = (age_prev + (target - hist[0]["season"])) if age_prev else None
                proj = fp.project_player(hist, side, target, curves, league, age)
                if proj is None:
                    continue
                war_pred = fp.war_from_projection(proj, side, war_map, league, target)
                base = _baseline(hist, side, target, league)
                actual_row = seasons.get(target)
                act = _actual_metrics(actual_row, side, league) if actual_row else {"war": 0.0, "expo": 0}
                act_war = act.get("war") if act.get("war") is not None else 0.0
                # WAR pool (everyone)
                if base["war"] is not None:
                    if GATE1_COLLECT is not None and not is_warmup:
                        GATE1_COLLECT.append((target, side, mlbam,
                                              float(war_pred), float(act_war)))
                    season_stats["war"]["m"].append((war_pred, act_war))
                    season_stats["war"]["b"].append((base["war"], act_war))
                    season_stats[f"war:{side}"]["m"].append((war_pred, act_war))
                    season_stats[f"war:{side}"]["b"].append((base["war"], act_war))
                    if act_war >= 4.0:
                        season_stats[f"war:{side}:act_ge4"]["m"].append((war_pred, act_war))
                        season_stats[f"war:{side}:act_ge4"]["b"].append((base["war"], act_war))
                    if age and age >= 30:
                        season_stats["war30"]["m"].append((war_pred, act_war))
                        season_stats["war30"]["b"].append((base["war"], act_war))
                    # bands: EMPIRICAL residual quantiles from PRIOR targets
                    # only (the spec's preferred mode — self-calibrating;
                    # the parametric normal alternative over-covered at
                    # 0.858 because WAR residuals are fat-middled).
                    bk = _bucket(side, proj["pt_proj"])
                    pool = resid.get(bk) or []
                    if len(pool) >= 50 and not is_warmup:
                        qs = statistics.quantiles(pool, n=10)
                        q10, q90 = qs[0], qs[-1]
                        if q10 <= (act_war - war_pred) <= q90:
                            season_stats["cov_hits"] += 1
                        season_stats["cov_n"] += 1
                    new_resid[bk].append(act_war - war_pred)
                    # 2020 is a 60-game season: realized WAR is compressed by
                    # ~2.7x, so its residuals are a different scale entirely
                    # and would distort a fitted variance function. The gate's
                    # own target list already excludes it; the panel does too.
                    if target != 2020:
                        platform = seasons.get(target - 1)
                        vol = ((platform.get("pa" if side == "hit" else "bf") or 0)
                               if platform else 0)
                        tj_n = 0.0
                        if tj_surgery is not None:
                            try:
                                tj_n = float(tj_surgery.tj_features(
                                    mlbam, f"{target}-01-01",
                                    _tj_store).get("tj_count_pre") or 0)
                            except Exception:            # noqa: BLE001
                                tj_n = 0.0
                        panel.append({
                            "season": target, "side": side,
                            "pred": float(war_pred), "resid": act_war - war_pred,
                            "age": float(age) if age else None,
                            "expo": float(proj["pt_proj"]),
                            "thin": 1.0 if (platform is None or vol < 180.0) else 0.0,
                            "tj_n": tj_n})
                # E3 exposure cell: projected vs actual playing time
                if actual_row and (act["expo"] or 0) > 0:
                    season_stats[f"expo:{side}"]["m"].append(
                        (float(proj["pt_proj"]), float(act["expo"])))
                # rate pool (target exposure gate)
                min_expo = min_pa if side == "hit" else min_bf
                if actual_row and act["expo"] >= min_expo and base.get(rate_key) is not None:
                    rate_pred = proj["wrc_plus_proj"] if side == "hit" else proj["fip_proj"]
                    rate_act = act.get(rate_key)
                    if rate_pred is not None and rate_act is not None:
                        season_stats[rate_key]["m"].append((rate_pred, rate_act))
                        season_stats[rate_key]["b"].append((base[rate_key], rate_act))
        for bk, vals in new_resid.items():
            resid[bk].extend(vals)
        if is_warmup:
            continue
        row = {"season": target}
        for k in GATE1_METRICS:
            if k in GATE1_HEADLINE:
                row[f"{k}_mae_model"] = _mae(season_stats[k]["m"])
                row[f"{k}_mae_base"] = _mae(season_stats[k]["b"])
                row[f"{k}_n"] = len(season_stats[k]["m"])
            elif ":act_ge4" not in k:    # per-side: MAE + signed level per season
                row[f"{k}_mae_model"] = _mae(season_stats[k]["m"])
                row[f"{k}_bias_model"] = _bias(season_stats[k]["m"])
                row[f"{k}_n"] = len(season_stats[k]["m"])
            pooled[k]["m"].extend(season_stats[k]["m"])
            pooled[k]["b"].extend(season_stats[k]["b"])
        row["coverage"] = (season_stats["cov_hits"] / season_stats["cov_n"]
                          if season_stats["cov_n"] else None)
        coverage_hits += season_stats["cov_hits"]
        coverage_n += season_stats["cov_n"]
        per_season.append(row)
        log.info("gate1 %d: WAR mae %.3f vs base %.3f (n=%d) | wRC+ %.1f vs %.1f | "
                 "FIP %.3f vs %.3f | cov %s",
                 target, row["war_mae_model"], row["war_mae_base"], row["war_n"],
                 row["wrc_plus_mae_model"] or -1, row["wrc_plus_mae_base"] or -1,
                 row["fip_mae_model"] or -1, row["fip_mae_base"] or -1,
                 f"{row['coverage']:.3f}" if row["coverage"] else "n/a")

    coverage = coverage_hits / coverage_n if coverage_n else None
    summary = {
        "model_version": MODEL_VERSION,
        "targets": targets,
        "pooled": {k: {"mae_model": _mae(pooled[k]["m"]), "mae_base": _mae(pooled[k]["b"]),
                       "bias_model": _bias(pooled[k]["m"]), "bias_base": _bias(pooled[k]["b"]),
                       "rmse_model": _rmse(pooled[k]["m"]), "rmse_base": _rmse(pooled[k]["b"]),
                       "n": len(pooled[k]["m"])} for k in GATE1_HEADLINE},
        # E1 (2026-07-30): per-side WAR MAE **and signed bias**, plus the E2
        # star-compression diagnostic. Kept out of `pooled` on purpose (see
        # GATE1_HEADLINE) so the served accountability table is unchanged.
        "pooled_by_side": {k: _cell(pooled[k]["m"], pooled[k]["b"])
                           for k in GATE1_SLICES},
        "coverage_p10_p90": coverage,
        "per_season": per_season,
        # The label basis is READ from the corpus, never asserted: this string said
        # "bWAR" for 20 days after the 2026-09-03 epoch moved the facade default.
        "war_provider": corpus.get("war_provider") or fp._war_provider(),
        "label_shape": corpus.get("label_shape"),
        "notes": [
            f"WAR label = {corpus.get('war_provider') or fp._war_provider()} through the war_source facade "
            f"(bWAR/war_daily before the 2026-09-03 epoch), label_shape {corpus.get('label_shape')}; "
            "absent target seasons score actual WAR 0 for model AND baseline",
            "HISTORY, measured on the bWAR label of its day and SUPERSEDED IN SCOPE on 2026-09-03, when the "
            "facade default moved to ewar_v2 site-wide by owner decision, and again on 2026-10-03, when the fWAR label "
            "epoch moved the training label to published fWAR (the war_provider above names the label this "
            "gate scores): "
            "so the smaller pitcher margin measured below is the expected shape of the current numbers, not a "
            "regression. eWAR LABEL SWAP MEASURED 2026-08-04 (lane R3b) and NOT ADOPTED then. "
            "Swapping the realized label to eWAR on the 6 fully covered targets "
            "(12,934 rows) makes the margin over the 5/4/3 carry-forward baseline "
            "SMALLER on pitchers, not larger: -0.0387 WAR against a pre-registered "
            "floor of +0.020, CI95 [-0.0472, -0.0309], negative in all six targets. "
            "THE TRAP IS WORTH NAMING because it will recur: the eWAR pitching "
            "label IS more forecastable (label r 0.5033 -> 0.5779, persistence "
            "0.4528 -> 0.5823), so it is easy to read that as evidence for the "
            "swap. But this gate scores MARGIN OVER A PERSISTENCE BASELINE, and a "
            "5/4/3 carry-forward IS a persistence bet, so a more persistent label "
            "helps the BASELINE more than it helps the model. A cleaner label "
            "raises the floor before it raises the ceiling. If eWAR is ever wired "
            "into the FA stack it needs a justification other than Gate 1, and "
            "Gate 1's floors would have to be re-derived on the new label.",
            f"wRC+ park-neutral, assembled from components (eval PA >= {min_pa})",
            f"FIP per-season constant (eval BF >= {min_bf})",
            "baseline = 5/4/3 weighted average of actual final metrics, no regression, no aging",
            "bands = EMPIRICAL residual q10/q90 per reliability bucket, rolled forward from prior targets only",
            "defense/BsR not separately projected in v1 — absorbed by WAR map + bands",
        ],
        # Per-bucket band quantiles from the FULL rolling residual pools —
        # the live projection's band source (documented in the artifact).
        "band_quantiles": {bk: {"q10": statistics.quantiles(v, n=10)[0],
                                "q90": statistics.quantiles(v, n=10)[-1],
                                "n": len(v)}
                           for bk, v in resid.items() if len(v) >= 50},
    }
    # ---- T1.2: player-specific band width -------------------------------
    # Fitted on the SAME pooled residual panel band_quantiles is cut from, so
    # the two are alternative readings of one dataset and band_quantiles stays
    # as the documented fallback. Measured lift and its floor live in
    # fa_bands' module docstring; the conditional-coverage table below is the
    # evidence that a marginal 0.79996 could never have produced.
    summary.update(_fit_band_scale(panel))
    gates = {
        "war": summary["pooled"]["war"]["mae_model"] < summary["pooled"]["war"]["mae_base"],
        "wrc_plus": summary["pooled"]["wrc_plus"]["mae_model"] < summary["pooled"]["wrc_plus"]["mae_base"],
        "fip": summary["pooled"]["fip"]["mae_model"] < summary["pooled"]["fip"]["mae_base"],
        "coverage": coverage is not None and 0.75 <= coverage <= 0.85,
    }
    summary["gates"] = gates
    summary["pass"] = all(gates.values())
    if persist:
        storage.upsert_fa_model_eval(MODEL_VERSION, "projection", summary)
        # Repo-visible copy (prospects.db is gitignored): the committed
        # gate verdict the Accountability surface + tests key off.
        import json
        from datetime import datetime as _dt, timezone as _tz
        from pathlib import Path
        # M04-03: self-dating, as Gate 2 is, so /fa/#view=model can say when
        # the table was measured.
        summary["generated_at"] = _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        (Path(__file__).parent / "data" / "fa_gate1_eval.json").write_text(
            json.dumps(summary, indent=1), encoding="utf-8")
        if reexport and reexport_on_persist():
            reexport_fa_sidecars("Gate 1 persisted")
    return summary


# ============================================================================
# M14-1: a saved gate re-runs the FA export (owner answer, 2026-09-25)
# ============================================================================
# fa_meta.json carries a COPY of both gate artifacts (the /fa/ Model view renders
# it) and the class bands read band_scale at export time, so a persisted gate
# used to sit unserved until someone ran fa_export by hand; the Model view served
# a superseded Gate 1 for days that way (census M04-02). A persisted gate now
# re-runs the export itself. Page reads go through scrapers.cache_only(): a cached
# Spotrac, Savant or StatsAPI page is read whatever its age and a missing one is
# not fetched, so the re-export costs no new page request. Every rewrite is
# logged with its size and a short content hash, before and after.
# Never called on persist=False: a lab that reads a gate without saving it (the
# GATE2_COLLECT labs, the FA destination lab) cannot trigger a served write.

def reexport_on_persist() -> bool:
    """False only where FA_GATE_REEXPORT is "0": the test harness sets it
    (conftest.py), so a test that persists a gate can never rewrite the served
    sidecars as a side effect."""
    import os
    return os.environ.get("FA_GATE_REEXPORT", "1") != "0"


def _sidecar_stamps(data_dir, names) -> dict:
    import hashlib
    out = {}
    for name in names:
        try:
            b = (data_dir / name).read_bytes()
        except OSError:
            out[name] = None
            continue
        out[name] = (len(b), hashlib.sha256(b).hexdigest()[:12])
    return out


def reexport_fa_sidecars(reason: str, *, export=None, data_dir=None,
                         names=None) -> dict:
    """Re-run the FA export from cached pages and log what it rewrote.

    Returns {"reason", "rewritten": {name: [before, after]}, "unchanged": [...],
    "error": str | None}, each stamp [bytes, sha256 prefix] or None for an
    absent file. A failed export is logged and reported, never raised: the
    gate artifact is already on disk and the nightly export catches up."""
    from pathlib import Path
    import scrapers
    if export is None or data_dir is None or names is None:
        import fa_export
        export = export or fa_export.export_all
        data_dir = data_dir or fa_export.DATA_DIR
        names = names or (["fa_class.json", "fa_archive.json", "fa_meta.json"]
                          + [f"fa_class_{y}.json" for y in fa_export.FUTURE_CLASS_YEARS])
    data_dir = Path(data_dir)
    before = _sidecar_stamps(data_dir, names)
    out = {"reason": reason, "rewritten": {}, "unchanged": [], "error": None}
    log.info("fa re-export (%s): rewriting the served FA sidecars from cached "
             "pages only", reason)
    try:
        with scrapers.cache_only():
            export()
    except Exception as e:                                # noqa: BLE001
        log.exception("fa re-export (%s) failed; the served sidecars still "
                      "carry the previous gate until the nightly export", reason)
        out["error"] = f"{type(e).__name__}: {e}"
    after = _sidecar_stamps(data_dir, names)
    for name in names:
        b, a = before.get(name), after.get(name)
        if a == b:
            out["unchanged"].append(name)
            continue
        out["rewritten"][name] = [list(b) if b else None, list(a) if a else None]
        log.info("fa re-export: rewrote data/%s  %s -> %s", name,
                 f"{b[0]:,} B {b[1]}" if b else "absent",
                 f"{a[0]:,} B {a[1]}" if a else "absent")
    if out["unchanged"]:
        log.info("fa re-export: unchanged %s", ", ".join(out["unchanged"]))
    return out


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--gate1", action="store_true")
    ap.add_argument("--gate2", action="store_true")
    args = ap.parse_args()
    if args.gate1:
        s = run_projection_gate()
        print("\n==== HARD GATE 1 — projection engine ====")
        for k, v in s["pooled"].items():
            print(f"  {k:9s} model MAE {v['mae_model']:.4f}  vs base {v['mae_base']:.4f}  (n={v['n']})")
        print(f"  coverage P10-P90: {s['coverage_p10_p90']:.3f}" if s["coverage_p10_p90"] else "  coverage: n/a")
        print(f"  gates: {s['gates']}")
        print(f"  PASS: {s['pass']}")
    if args.gate2:
        s = run_market_gate()
        print("\n==== HARD GATE 2 — market model ====")
        for k, v in s["pooled"].items():
            print(f"  {k:10s} model MAE {v['mae_model']:.3f}  vs base {v['mae_base']:.3f}  (n={v['n']})")
        print(f"  gates: {s['gates']}")
        print(f"  PASS: {s['pass']}")
    if args.gate1 or args.gate2:
        # M14-1: each persisted gate above already re-ran the FA export from
        # cached pages (reexport_fa_sidecars logs every file it rewrote).
        print("\n  The FA sidecars were re-exported from cached pages after "
              "each saved gate; see the log for the files rewritten.")




# ============================================================================
# HARD GATE 2 — predicted market price vs the nearest-comps naive baseline
# ============================================================================
# Forward-chained winters (the honest ex-ante stance): train on winters
# strictly BEFORE the held-out winter, with $/WAR levels carried forward;
# warmup winters seed the first train set and are never scored. Baseline =
# median of the 5 nearest comps from prior winters, inflated by the naive
# $/WAR trend. Misses are published, not hidden.

GATE2_WARMUP_THROUGH = 2017          # train-only winters; scoring starts after
GATE2_MODEL_VERSION = "fa_mkt_v2"

# Lab hook. Set to a list and every scored row is appended as
# (winter, player_key, pred_guar_mm, act_guar_mm, pred_aav_mm, act_aav_mm,
# pred_years, act_years). None in production and nothing else reads it; it
# exists so an A/B of two model settings can be PAIRED ROW BY ROW instead of
# compared on two pooled MAEs, which cannot tell a real 1% move from noise.
GATE2_COLLECT: list | None = None


def _pct_label(rate: float) -> str:
    """The percent a rate prints as in copy: 0.07 -> '7', 0.075 -> '7.5'."""
    return f"{float(rate) * 100:g}"


def gate2_notes(discount_rate: float) -> list[str]:
    """The notes the Model Accountability page renders verbatim under the Gate-2
    table (assets/fa.js renderModel joins gate2.notes).

    The NPV line names the discount rate the table was PRICED AT, interpolated
    from the argument, never typed. Until 2026-09-11 it was the literal
    "deferral-adjusted at the platform 9% rate" over a 1,199-row table whose
    actuals fa_market.deferral_npv_usd had discounted at 7 percent (audit
    F12-01; the table's own Ohtani row reads 274.8, the 7 percent NPV, not the
    214.9 a 9 percent rate would give). A typed rate cannot have been true at
    any generation once the valuation set moved, and nothing compared it with
    the engine. run_market_gate passes fm._discount_rate(), the same call the
    engine makes when it prices the actuals, and stamps the rate into the
    artifact beside the notes so test_claims_freshness can hold the two
    together."""
    return [
        "forward-chained: trained on winters strictly before each test winter",
        (f"guarantee/AAV in $M NPV (deferral-adjusted at the platform's "
         f"{_pct_label(discount_rate)}% discount rate; no-schedule deals keep sticker)"),
        "baseline = median of 5 nearest comps (prior winters), naive $/WAR-trend inflated, NPV basis",
        "$/WAR level per test winter forecast ex-ante (method per data/dpw_forecast_eval.json)",
    ]


# ============================================================================
# Verdict edge re-derivation (owner answer M14-2; docs/fa-2026-10-08/GATE2_RESAVE.md
# section 4). The edges are corpus terciles of Deal+ by construction, so they go
# stale whenever the pricing basis moves. This is the one recipe that cuts them:
# basis A (expected rational value over the ACTUAL NPV guarantee), forward-chained
# train-only $/WAR, the ex-ante destale rate, term capped at 10, per _pos_group,
# p33 / p67 linearly interpolated and rounded half up. run_market_gate(persist=True)
# runs it on every persist and records it beside the served constants.
# ============================================================================

VERDICT_EDGE_PROTOCOL = "docs/fa-2026-10-08/GATE2_RESAVE.md"
VERDICT_EDGE_MIN_TRAIN = 100        # a winter is cut only with this many prior rows
VERDICT_EDGE_MAX_TERM = 10
VERDICT_EDGE_PCTS = (33, 67)
VERDICT_EDGE_GROUPS = ("SP", "RP", "C", "POS")


def verdict_edge_corpus(enriched: list[dict]) -> tuple[list[dict], int]:
    """(rows, dropped): one {winter, group, deal_plus} per corpus signing with a
    WAR path, Deal+ on basis A, each winter priced by a model trained on the
    winters strictly before it. `dropped` counts rows whose value raised."""
    import fa_market as fm
    rows: list[dict] = []
    dropped = 0
    for W in sorted({s["class_year"] for s in enriched}):
        train = [s for s in enriched if s["class_year"] < W]
        test = [s for s in enriched if s["class_year"] == W]
        if len(train) < VERDICT_EDGE_MIN_TRAIN or not test:
            continue
        series = fm.dollars_per_war_by_winter(train)
        model = fm.MarketModel(train, series)
        model.supply_by_year[W] = fm._supply(test, W)
        dpw = fm.winter_dpw(series, W)
        infl = fm._destale_rate(series, W)
        for s in test:
            path = s.get("_war_path") or {}
            if not path.get("war_by_year"):
                continue
            pred = model.predict(s)
            yrs = min(int(pred["proj_years"]), VERDICT_EDGE_MAX_TERM)
            try:
                val = fm.expected_rational_value_usd(path, yrs, W, dpw, infl=infl)
            except Exception:                         # noqa: BLE001
                dropped += 1
                continue
            rows.append({"winter": W, "group": fm._pos_group(s.get("position")),
                         "deal_plus": 100.0 * val / max(fm._npv_of(s), 1)})
    return rows, dropped


def _pct_linear(sorted_vals: list[float], p: float) -> float:
    """The p-th percentile, linear between order statistics at p/100 * (n - 1)."""
    pos = (p / 100.0) * (len(sorted_vals) - 1)
    lo = int(math.floor(pos))
    hi = min(lo + 1, len(sorted_vals) - 1)
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * (pos - lo)


def _round_half_up(x: float) -> int:
    return int(math.floor(x + 0.5))


def _band(d: float, edges) -> str:
    lo, hi = edges
    return "value" if d >= hi else "overpay" if d < lo else "market"


def _band_counts(vals, edges) -> dict:
    c = {"overpay": 0, "market": 0, "value": 0}
    for d in vals:
        c[_band(d, edges)] += 1
    return c


def derive_verdict_edges(rows: list[dict], served: dict | None = None) -> dict:
    """Per-group and pooled terciles of corpus Deal+, with the counts under the
    derived edges and, given `served` ({"pooled" | group: (lo, hi)}), under the
    edges that were served before and the rows whose verdict flips."""
    by = {"pooled": [r["deal_plus"] for r in rows]}
    for g in VERDICT_EDGE_GROUPS:
        by[g] = [r["deal_plus"] for r in rows if r["group"] == g]
    out = {}
    for k, vals in by.items():
        if not vals:
            continue
        sv = sorted(vals)
        p33, p67 = (_pct_linear(sv, p) for p in VERDICT_EDGE_PCTS)
        edges = [_round_half_up(p33), _round_half_up(p67)]
        cell = {"n": len(vals), "p33": round(p33, 3), "p67": round(p67, 3),
                "edges": edges, "counts": _band_counts(vals, edges)}
        old = (served or {}).get(k)
        if old:
            cell["served_edges"] = list(old)
            cell["served_counts"] = _band_counts(vals, old)
            cell["flips"] = sum(1 for d in vals if _band(d, old) != _band(d, edges))
        out[k] = cell
    return out


def _served_board_counts(edges_by_group: dict, path=None) -> dict | None:
    """Verdict counts on the served class board (data/fa_class.json) re-banded
    on `edges_by_group` from each row's served Deal+ and position group."""
    import json as _json
    from pathlib import Path as _Path
    import fa_market as fm
    p = _Path(path) if path else _Path(__file__).parent / "data" / "fa_class.json"
    try:
        members = _json.loads(p.read_text(encoding="utf-8")).get("members") or []
    except (OSError, ValueError):
        return None
    c = {"overpay": 0, "market": 0, "value": 0}
    for m in members:
        if m.get("dealPlus") is None:
            continue
        g = fm._pos_group(m.get("pos"))
        c[_band(float(m["dealPlus"]), edges_by_group[g])] += 1
    return c


def _served_edges(ve: dict | None) -> dict:
    """{"pooled" | group: (lo, hi)} from a verdict_edges block, falling back to
    the fa_market constants for anything the block does not carry."""
    import fa_market as fm
    out = {"pooled": (fm.VERDICT_OVERPAY_MAX, fm.VERDICT_VALUE_MIN),
           **{g: tuple(v) for g, v in fm.VERDICT_GROUP_EDGES.items()}}
    ve = ve or {}
    pooled = ve.get("pooled") or {}
    if pooled.get("overpay_max") is not None and pooled.get("value_min") is not None:
        out["pooled"] = (int(pooled["overpay_max"]), int(pooled["value_min"]))
    for g, v in (ve.get("group") or {}).items():
        out[g] = tuple(v)
    return out


def verdict_edges_block(enriched: list[dict], prev_block: dict | None,
                        war_provider: str | None, today: str) -> dict:
    """The artifact's verdict_edges block for one persist: the served constants,
    the fresh derivation (`derived`), every earlier dated re-cut record carried
    forward, and a new `recut_<date>` record when the derived edges differ from
    the edges served before this persist."""
    import fa_market as fm
    rows, dropped = verdict_edge_corpus(enriched)
    served_before = _served_edges(prev_block)
    cells = derive_verdict_edges(rows, served_before)
    derived_groups = {g: cells[g]["edges"] for g in VERDICT_EDGE_GROUPS if g in cells}
    derived = {
        "date": today,
        "protocol": VERDICT_EDGE_PROTOCOL,
        "basis": ("deal_plus = 100 * expected rational value / ACTUAL NPV guarantee; "
                  "forward-chained train-only $/WAR per winter, ex-ante destale rate, "
                  f"predicted term capped at {VERDICT_EDGE_MAX_TERM}"),
        "quantile": "linear between order statistics at p/100 * (n - 1), p 33 and 67, rounded half up",
        "war_provider": war_provider,
        "winters": sorted({r["winter"] for r in rows}),
        "n": len(rows),
        "dropped": dropped,
        "pooled": cells.get("pooled"),
        "group": {g: cells[g] for g in VERDICT_EDGE_GROUPS if g in cells},
        "served_board": {
            "served_before": _served_board_counts(
                {g: served_before[g] for g in VERDICT_EDGE_GROUPS}),
            "derived": _served_board_counts(derived_groups),
        },
    }
    block = {
        "band_mode": fm.VERDICT_BAND_MODE,
        "pooled": {"overpay_max": fm.VERDICT_OVERPAY_MAX,
                   "value_min": fm.VERDICT_VALUE_MIN},
        "group": {g: list(v) for g, v in fm.VERDICT_GROUP_EDGES.items()},
        "protocol": VERDICT_EDGE_PROTOCOL,
        "derived": derived,
    }
    for k, v in (prev_block or {}).items():
        if k.startswith("recut_"):
            block[k] = v
    moved = (tuple(cells["pooled"]["edges"]) != tuple(served_before["pooled"])
             or any(tuple(derived_groups[g]) != tuple(served_before[g])
                    for g in derived_groups))
    if moved:
        block["recut_" + today.replace("-", "_")] = derived
    return block


def run_market_gate(persist: bool = True, challenger: bool = False,
                    persist_dpw: bool = False, reexport: bool = True) -> dict:
    """Gate 2. ``challenger=True`` additionally scores the WS-2f LightGBM
    challenger (fa_market_ml.MarketModelML) on the same folds — identical
    train/test rows, identical comps baseline, identical NPV targets.

    ``persist=True`` also re-derives the verdict edges (verdict_edges_block)
    and, with ``reexport`` (the default, owner answer M14-1), re-runs the FA
    export afterwards so the served sidecars follow the gate at once.

    ``persist_dpw=False`` writes the EVAL ARTIFACT ONLY and leaves
    data/fa_dpw_series.json alone. That coupling is this module's single biggest
    write hazard: fa_dpw_series.json is the $/WAR level the ENTIRE valuation
    engine prices against, and until 2026-07-30 there was no way to refresh the
    published gate verdict after a model change without also rewriting it.
    The default is False since VAL_5 (2026-10-02): the one writer already runs
    first in every rebuild, and an owner-decided Gate 2 re-persist must ask for
    the series write by name. With fa_market.WRITE_DPW_PATH_BLOCK off, that write
    carries VAL_1's keys only."""
    import fa_market as fm
    enriched = fm.enriched_signings(2015, 2026)
    # The rate every NPV in this table is priced at (deferral_npv_usd reads the
    # same config). Read once, stamped into the summary and interpolated into
    # the served note, so the note can never name a rate the table was not
    # computed at.
    disc_rate = fm._discount_rate()
    test_years = sorted({s["class_year"] for s in enriched
                         if s["class_year"] > GATE2_WARMUP_THROUGH})
    pooled = {"guarantee": {"m": [], "b": []}, "aav": {"m": [], "b": []},
              "years": {"m": [], "b": []}, "mega_guarantee": {"m": [], "b": []}}
    pooled_ch = {k: [] for k in pooled}
    # E1 (2026-07-30): per-pos-group and per-side price slices with SIGNED bias.
    # Deliberately NOT merged into `pooled` - assets/fa.js:1131 renders
    # Object.entries(gate2.pooled) as the served accountability table.
    grouped: dict[str, dict[str, list]] = defaultdict(lambda: {"m": [], "b": []})
    per_winter: list[dict] = []
    misses: list[dict] = []
    infl = fm._dpw_inflation()
    for W in test_years:
        train = [s for s in enriched if s["class_year"] < W]
        test = [s for s in enriched if s["class_year"] == W]
        if len(train) < 100 or not test:
            continue
        dpw_series = fm.dollars_per_war_by_winter(train)
        model = fm.MarketModel(train, dpw_series)
        # class composition of the test winter is known at winter start —
        # a legitimate ex-ante feature.
        model.supply_by_year[W] = fm._supply(test, W)
        ch_model = None
        if challenger:
            import fa_market_ml
            ch_model = fa_market_ml.MarketModelML(train, dpw_series)
            ch_model.champ.supply_by_year[W] = fm._supply(test, W)
        wstats = {k: {"m": [], "b": []} for k in pooled}
        for s in test:
            pred = model.predict(s)
            if ch_model is not None:
                cp = ch_model.predict(s)
                act_ch = fm._npv_of(s)
                pooled_ch["guarantee"].append((cp["proj_guarantee_usd"] / 1e6, act_ch / 1e6))
                if act_ch >= 100_000_000:
                    pooled_ch["mega_guarantee"].append((cp["proj_guarantee_usd"] / 1e6, act_ch / 1e6))
                pooled_ch["aav"].append((cp["proj_aav_usd"] / 1e6,
                                         act_ch / max(float(s["years"]), 1) / 1e6))
                pooled_ch["years"].append((float(cp["proj_years"]), float(s["years"])))
            comps = fm.comps_for(s, train)
            if not comps:
                continue
            # Phase 2 — NPV basis throughout: actuals, comps baseline and
            # model targets all speak deferral-adjusted present value. A
            # sticker basis let Ohtani-class deferrals distort both sides.
            b_guar = statistics.median(
                (c.get("npv_guarantee_usd") or c["guarantee_usd"])
                * ((1 + infl) ** (W - c["class_year"])) for c in comps)
            b_years = statistics.median(c["years"] for c in comps)
            b_aav = b_guar / max(b_years, 1)
            act_g, act_y = fm._npv_of(s), float(s["years"])
            act_a = act_g / max(act_y, 1)
            wstats["guarantee"]["m"].append((pred["proj_guarantee_usd"] / 1e6, act_g / 1e6))
            wstats["guarantee"]["b"].append((b_guar / 1e6, act_g / 1e6))
            if act_g >= 100_000_000:               # the megadeal slice, measured
                wstats["mega_guarantee"]["m"].append((pred["proj_guarantee_usd"] / 1e6, act_g / 1e6))
                wstats["mega_guarantee"]["b"].append((b_guar / 1e6, act_g / 1e6))
            wstats["aav"]["m"].append((pred["proj_aav_usd"] / 1e6, act_a / 1e6))
            wstats["aav"]["b"].append((b_aav / 1e6, act_a / 1e6))
            wstats["years"]["m"].append((float(pred["proj_years"]), act_y))
            wstats["years"]["b"].append((b_years, act_y))
            if GATE2_COLLECT is not None:
                GATE2_COLLECT.append((W, s.get("player_key") or s["player_name"],
                                      pred["proj_guarantee_usd"] / 1e6, act_g / 1e6,
                                      pred["proj_aav_usd"] / 1e6, act_a / 1e6,
                                      float(pred["proj_years"]), act_y))
            # --- E1 slices: pos group, side, and actual-guarantee tier -------
            _g = fm._pos_group(s.get("position"))
            _side = "pit" if _g in ("SP", "RP") else "hit"
            # Two tier conditionings, and the difference matters. `tier:` bins on
            # the ACTUAL guarantee, which forces a negative bias at the top and a
            # positive one at the bottom by regression to the mean - it is a
            # DESCRIPTIVE cell, never a calibration criterion. `ptier:` bins on
            # the PREDICTED guarantee, which is the decision-relevant
            # conditioning ("when the board says $15M, what do they get") and the
            # one fa_market._fit_recal's own docstring is estimated against.
            _tier = ("lt10" if act_g < 10e6 else "10to20" if act_g < 20e6
                     else "20to50" if act_g < 50e6 else "ge50")
            _pg = pred["proj_guarantee_usd"]
            _ptier = ("lt10" if _pg < 10e6 else "10to20" if _pg < 20e6
                      else "20to50" if _pg < 50e6 else "ge50")
            for _sl in (_g, _side, f"tier:{_tier}", f"ptier:{_ptier}"):
                grouped[f"guarantee:{_sl}"]["m"].append((pred["proj_guarantee_usd"] / 1e6, act_g / 1e6))
                grouped[f"guarantee:{_sl}"]["b"].append((b_guar / 1e6, act_g / 1e6))
                grouped[f"aav:{_sl}"]["m"].append((pred["proj_aav_usd"] / 1e6, act_a / 1e6))
                grouped[f"aav:{_sl}"]["b"].append((b_aav / 1e6, act_a / 1e6))
                grouped[f"years:{_sl}"]["m"].append((float(pred["proj_years"]), act_y))
                grouped[f"years:{_sl}"]["b"].append((b_years, act_y))
            actual_aav_mm = round(act_a / 1e6, 1)
            pred_aav_mm = round(pred["proj_aav_usd"] / 1e6, 1)
            misses.append({"player": s["player_name"], "winter": W,
                           "to_team": s.get("to_team"), "qo": bool(s.get("qo")),
                           "actual_guar_mm": round(act_g / 1e6, 1),
                           "pred_guar_mm": round(pred["proj_guarantee_usd"] / 1e6, 1),
                           "actual_years": act_y, "pred_years": pred["proj_years"],
                           "err_mm": round((pred["proj_guarantee_usd"] - act_g) / 1e6, 1),
                           "actual_aav_mm": actual_aav_mm, "pred_aav_mm": pred_aav_mm,
                           "err_years": pred["proj_years"] - act_y,
                           "err_aav_mm": round(pred_aav_mm - actual_aav_mm, 1)})
        row = {"winter": W, "n": len(wstats["guarantee"]["m"])}
        for k in pooled:
            row[f"{k}_mae_model"] = _mae(wstats[k]["m"])
            row[f"{k}_mae_base"] = _mae(wstats[k]["b"])
            pooled[k]["m"].extend(wstats[k]["m"])
            pooled[k]["b"].extend(wstats[k]["b"])
        per_winter.append(row)
        log.info("gate2 %d: guar mae %.1f vs base %.1f ($M, n=%d) | aav %.2f vs %.2f | yrs %.2f vs %.2f",
                 W, row["guarantee_mae_model"], row["guarantee_mae_base"], row["n"],
                 row["aav_mae_model"], row["aav_mae_base"],
                 row["years_mae_model"], row["years_mae_base"])
    misses.sort(key=lambda m: -abs(m["err_mm"]))
    summary = {
        "model_version": GATE2_MODEL_VERSION,
        "basis": "npv_deferral_adjusted",
        "discount_rate": disc_rate,
        # M04-03 (2026-09-25): the WAR basis the corpus was labelled on, as
        # Gate 1 stamps it. The 2026-08-19 artifact carries none, which is how
        # a pre-epoch table kept serving beside eWAR-priced contracts with
        # nothing on the page saying so. /fa/#view=model compares this with
        # fa_meta.war_provider and discloses a mismatch.
        "war_provider": fp._war_provider(),
        "test_winters": test_years,
        "pooled": {k: {"mae_model": _mae(v["m"]), "mae_base": _mae(v["b"]),
                       "n": len(v["m"])} for k, v in pooled.items()},
        # E1 (2026-07-30): MAE *and signed bias* per pos group / side / actual
        # guarantee tier. bias_model > 0 means the board OVER-prices that cell.
        "pooled_by_pos_group": {k: _cell(v["m"], v["b"])
                                for k, v in sorted(grouped.items())},
        "per_winter": per_winter,
        "biggest_misses": misses[:12],
        "biggest_misses_years": sorted(misses, key=lambda m: -abs(m["err_years"]))[:12],
        "biggest_misses_aav": sorted(misses, key=lambda m: -abs(m["err_aav_mm"]))[:12],
        "deferral_coverage": fm.deferral_coverage_audit(enriched),
        "notes": gate2_notes(disc_rate),
    }
    gates = {k: summary["pooled"][k]["mae_model"] < summary["pooled"][k]["mae_base"]
             for k in ("guarantee", "aav", "years")}
    # tracked (non-gating) slice: the megadeal shortfall, measured per run
    mg = summary["pooled"]["mega_guarantee"]
    summary["mega_slice_note"] = (
        f"megadeals (actual >= $100M, n={mg['n']}): model MAE ${mg['mae_model']:.0f}M "
        f"vs comps baseline ${mg['mae_base']:.0f}M")
    summary["gates"] = gates
    summary["pass"] = all(gates.values())
    if challenger and pooled_ch["guarantee"]:
        import fa_market_ml
        ch = {k: {"mae": _mae(v), "n": len(v)} for k, v in pooled_ch.items()}
        summary["challenger"] = {
            "model_version": fa_market_ml.ML_MARKET_VERSION,
            "pooled": ch,
            "ship_criteria": {
                "guarantee_beats_champion":
                    ch["guarantee"]["mae"] < summary["pooled"]["guarantee"]["mae_model"],
                "mega_not_worse":
                    ch["mega_guarantee"]["mae"] <= summary["pooled"]["mega_guarantee"]["mae_model"],
                "years_not_worse":
                    ch["years"]["mae"] <= summary["pooled"]["years"]["mae_model"],
            },
        }
        summary["challenger"]["ship"] = all(summary["challenger"]["ship_criteria"].values())
    if persist:
        storage.upsert_fa_model_eval(GATE2_MODEL_VERSION, "market", summary)
        import json as _json
        from datetime import datetime as _dt, timezone as _tz
        from pathlib import Path as _Path
        _out = _Path(__file__).parent / "data" / "fa_gate2_eval.json"
        # CARRY-FORWARD (2026-08-19): the artifact self-dates, and blocks
        # written into it by their own labs (verdict_edges, the ptier gate
        # record) must survive a wholesale re-persist. Same pattern as
        # eta_backtest / team_outlook_eval; without this, the next persist
        # strips them and test_fa_ptier_gate.py goes red on purpose.
        summary["generated_at"] = _dt.now(_tz.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            _prev = _json.loads(_out.read_text(encoding="utf-8"))
        except (FileNotFoundError, _json.JSONDecodeError):
            _prev = {}
        # M14-2: the edges are re-derived on this persist's own corpus and
        # recorded beside the served constants (verdict_edges_block).
        summary["verdict_edges"] = verdict_edges_block(
            enriched, _prev.get("verdict_edges"), summary["war_provider"],
            summary["generated_at"][:10])
        try:
            for _k, _v in _prev.items():
                if _k not in summary and (_k == "verdict_edges"
                                          or _k.endswith("_gate")
                                          or _k.startswith("ptier_")):
                    summary[_k] = _v
        except (FileNotFoundError, _json.JSONDecodeError):
            pass
        _out.write_text(_json.dumps(summary, indent=1), encoding="utf-8")
    if persist and persist_dpw:
        # VAL_1 (2026-09-25): the file has ONE writer, fa_market.write_dpw_series,
        # which also writes the pricing level every surface reads. This persist
        # used to write its own copy (series and breakdowns, no level), which is
        # how /projections/ came to price on a series /fa/ did not. The writer
        # re-reads the corpus through the class winter, so the file is identical
        # whichever of the two callers wrote it last.
        from fa_export import CLASS_YEAR as _CLASS_YEAR
        fm.write_dpw_series(_CLASS_YEAR)
    if persist and reexport and reexport_on_persist():
        reexport_fa_sidecars("Gate 2 persisted")
    return summary


if __name__ == "__main__":
    main()
