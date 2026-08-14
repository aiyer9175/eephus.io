# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""REAL-DATA surplus-value backtest (model-audit Phase 0, WS-0d).

backtest.py shipped as a synthetic-only harness ("a real backtest needs
completed-window cohorts... none of which ship with this repo") — but the
platform has since accumulated exactly those inputs: per-source FV
snapshots back to 2017, per-season bWAR for every tracked graduate
(career_war), career level history (career_stats), and a curated
historical $/WAR table. This module builds REAL resolved cohorts and runs
them through the EXISTING harness (run_backtest / assert_no_lookahead) —
no new metric code, no new prediction code.

Cohort construction (every choice documented, every exclusion counted):
  LISTING   per (player, year in 2017-2019): the vintage consensus = the
            MEDIAN of each source's EARLIEST same-year FV snapshot.
            pre_debut only (no MLB season before the listing year).
  ETA proxy historical believed-ETA was never recorded; proxy = highest
            professional level reached by the listing year -> years table
            (AAA 1.0 / AA 2.0 / A+ 2.5 / A 3.0 / short-season 4.0).
  REALIZED  per-season bWAR from career_war; control window = first six
            MLB seasons (service approximated at a full year per season
            with a WAR row — actual service days are not on file).
            Salaries are IMPUTED per the framework's own convention
            (league-minimum schedule for 3 pre-arb years, then the arb
            fractions of that season's tiered market value) — the exact
            imputation docs/sv-backtest.md's caveats call for.
  OUTCOMES  three honest classes:
              scored     career_war rows exist (realized known), or no
                         professional activity since 2024 with no MLB
                         time (washed out -> realized 0)
              excluded   MLB time evident in career_stats but no
                         career_war rows (debuted, outcome unknown —
                         EXCLUDED, never zeroed)
              censored   no MLB time but still active in pro ball (may
                         yet debut — excluded from the bust pool)
  SLICES    full scored pool + a RESOLVED-ONLY slice (debut + 6 seasons
            complete by the last full season, or washed out).

Prediction side: vf.expected_surplus_usd with TODAY'S standing config
(including the v3 FA-implied $/WAR re-anchor). Realized production is
priced at the $/WAR that PREVAILED each season (historical table; seasons
before 2020 fall back to the nearest year). That level difference is part
of what the calibration measures — the harness decomposition attributes
it (FV->WAR layer vs $-layer), per backtest.py's documented convention.

NO calibration is applied here — this is the Phase-0 measurement. The
correction ships (or doesn't) in Phase 4 WS-6, on reweighted-consensus
FVs. Artifact: data/surplus_backtest_real.json.

Run: python surplus_backtest_real.py
"""

from __future__ import annotations

import json
import logging
import os
import statistics
from datetime import date
from pathlib import Path

import storage
import value_framework as vf
from backtest import (ListingView, PlayerRecord, RealizedRecord,
                      RealizedSeason, run_backtest, _SERVICE_FULL_DAYS)

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
OUT_PATH = DATA_DIR / "surplus_backtest_real.json"

LISTING_YEARS = (2017, 2018, 2019)
MIN_FV = 40.0

# --- FV SCALE (2026-07-25 repair) --------------------------------------------
# The listing consensus used to be the median of the RAW per-source snapshot FV,
# with NO grade normalization. PRODUCTION prices on the NORMALIZED consensus
# (consensus.build_timeseries applies grade_normalization.build_remapper before
# aggregation, gated by consensus.ADOPT_NORMALIZED_CONSENSUS, adopted 2026-07).
# So the calibration this module feeds was fit on a scale production does not
# use: measured on the 2017-2019 window the production scale sits 2.135 FV BELOW
# the fit scale (78.3% of cells move, one-sided), and under the shipped
# linearmap-v5 that units gap prices the resolved pool at 59% of its realized
# dollars. FV_SCALE="normalized" puts the pool on production's scale.
#
# FV_SCALE="raw" reproduces the pre-repair pool EXACTLY (3,368 listings /
# 2,236 resolved = the registered n of linearmap-v5-todaypriced-2026-07-24), so a
# reviewer can regenerate the old numbers and diff the two. Override with the
# env var SURPLUS_FIT_FV_SCALE.
FV_SCALE = os.environ.get("SURPLUS_FIT_FV_SCALE", "normalized")

# Which scale the MIN_FV pool gate is applied on. The gate runs AFTER the median,
# so applying it on the normalized scale silently drops the bottom band: 493 of
# the 3,368 fit-window cells (14.6%) fall below 40 once normalized and 0 enter,
# which re-tilts the fit on a pool that changed for a reason unrelated to the
# repair. Gating on RAW holds pool membership fixed at the registered n while the
# SCALE of the inputs is what changes -- one variable at a time. Override with
# SURPLUS_FIT_GATE_SCALE=normalized to move the gate too.
GATE_SCALE = os.environ.get("SURPLUS_FIT_GATE_SCALE", "raw")
CONTROL_YEARS = 6
# Last COMPLETE season available for outcomes (2026 is in progress).
LAST_FULL_SEASON = 2025
# No professional activity in/after this season + no MLB time = washed out.
WASHED_BEFORE = 2024

_LEVEL_ETA = {"AAA": 1.0, "AA": 2.0, "A+": 2.5, "A": 3.0, "A-": 3.5,
              "CPX": 4.0, "ROK": 4.0, "DSL": 4.0, "FRk": 4.0, "Rk": 4.0}
_LEVEL_ORDER = ["DSL", "FRk", "Rk", "ROK", "CPX", "A-", "A", "A+", "AA", "AAA"]


def _age_at(birth_date: str | None, asof: str) -> float | None:
    if not birth_date:
        return None
    try:
        b = date.fromisoformat(birth_date[:10])
        a = date.fromisoformat(asof[:10])
    except ValueError:
        return None
    return round((a - b).days / 365.25, 1)


def _remapper():
    """The PRODUCTION grade-normalization closure (same construction consensus.
    build_timeseries uses: one DB pass, aliased per outlet). None if unavailable,
    in which case the pool degrades to the raw scale and says so.

    AS-OF CUTOFF THREADED 2026-08-14 with the C-4 flip, and this is THE BINDING
    SITE. consensus.py's flip checklist names this file specifically: it prices the
    backtest that prospect_surplus is validated against, so leaving it uncapped
    while the served board is capped puts the board and its own validation on two
    different normalization bases. That is a worse state than either basis alone,
    because the backtest would then be certifying grades it was not computed from.

    The cutoff comes from consensus.grade_norm_cutoff so this site cannot drift
    from the served one; it reads the newest snapshot year in the pool, from the
    data rather than the clock."""
    try:
        import consensus as _cons
        from grade_normalization import build_remapper
        with storage.connect() as con:
            rows = con.execute(
                "SELECT snapshot_date FROM snapshots WHERE snapshot_date IS NOT NULL"
            ).fetchall()
        _snaps = [type("S", (), {"snapshot_date": r[0]})() for r in rows]
        return build_remapper(aliases=_cons.SOURCE_ALIASES,
                              as_of_year=_cons.grade_norm_cutoff(_snaps))
    except Exception as exc:                       # pragma: no cover - defensive
        log.warning("grade normalization unavailable (%s); pool stays RAW", exc)
        return None


def _load_inputs() -> tuple[dict, dict, dict, dict]:
    """(listings, career_war, career_levels, bio) from the DB.
    listings: {(player_key, year): {fv: median, fv_raw, fv_normalized, date}}

    `fv` is the field the cohort prices on and follows FV_SCALE; both scales are
    always carried so a run can be diffed without a second DB pass."""
    remap = _remapper() if FV_SCALE == "normalized" or GATE_SCALE == "normalized" else None
    with storage.connect() as con:
        # earliest same-year snapshot per (player, source, year); `position` comes
        # along because the remapper resolves its (source, role, cycle) cell from it,
        # exactly as consensus.compute_consensus_point does.
        rows = con.execute("""
            SELECT player_key, source, snapshot_date, fv, position
            FROM snapshots WHERE fv IS NOT NULL
              AND substr(snapshot_date,1,4) IN ({})""".format(
            ",".join(f"'{y}'" for y in LISTING_YEARS))).fetchall()
        first: dict[tuple, tuple] = {}
        for r in rows:
            key = (r["player_key"], r["source"], int(str(r["snapshot_date"])[:4]))
            d = str(r["snapshot_date"])
            if key not in first or d < first[key][0]:
                first[key] = (d, float(r["fv"]), r["position"])
        fv_at: dict[tuple, list] = {}
        for (pk, src, y), (d, fv, pos) in first.items():
            fvn = fv if remap is None else remap(fv, src, pos, y)
            fv_at.setdefault((pk, y), []).append(
                (float(fv), float(fv if fvn is None else fvn), d))
        listings = {}
        for key, vals in fv_at.items():
            med_raw = statistics.median(v for v, _, _ in vals)
            med_norm = statistics.median(n for _, n, _ in vals)
            gate_on = med_norm if GATE_SCALE == "normalized" else med_raw
            if gate_on >= MIN_FV:
                listings[key] = {
                    "fv": med_norm if FV_SCALE == "normalized" else med_raw,
                    "fv_raw": med_raw, "fv_normalized": med_norm,
                    "date": min(d for _, _, d in vals), "n_sources": len(vals)}
        cw = {r["player_key"]: json.loads(r["payload_json"])
              for r in con.execute("SELECT player_key, payload_json FROM career_war")}
        cs = {}
        for r in con.execute("SELECT player_key, payload_json FROM career_stats"):
            try:
                cs[r["player_key"]] = json.loads(r["payload_json"])
            except ValueError:
                continue
        bio = {r["player_key"]: dict(r) for r in con.execute(
            "SELECT player_key, position, is_pitcher, birth_date FROM players")}
    return listings, cw, cs, bio


def _mlb_seasons_from_stats(rows: list[dict]) -> set[int]:
    return {int(r["season"]) for r in (rows or [])
            if r.get("level") == "MLB" and r.get("season")}


def _highest_level_through(rows: list[dict], year: int) -> str | None:
    best = None
    for r in rows or []:
        if not r.get("season") or int(r["season"]) > year:
            continue
        lv = r.get("level")
        if lv in _LEVEL_ORDER:
            if best is None or _LEVEL_ORDER.index(lv) > _LEVEL_ORDER.index(best):
                best = lv
    return best


def _last_activity(rows: list[dict]) -> int | None:
    seasons = [int(r["season"]) for r in (rows or []) if r.get("season")]
    return max(seasons) if seasons else None


def _impute_seasons(war_by_year: dict[str, float], debut: int) -> tuple[RealizedSeason, ...]:
    """First six MLB seasons with framework-convention imputed salaries.
    Gap years (no WAR row) don't price and don't accrue service —
    documented approximation of injury/option years."""
    cfg = vf._config()
    fracs = list(cfg["service_time"]["arb_model"]["fractions_of_fa_value"])
    pre_arb = int(cfg["service_time"]["pre_arb_years"])
    lm_by_year = {int(k): float(v) for k, v in
                  (cfg.get("league_min_by_year") or {}).items()}
    lm_default = float(cfg["service_time"]["league_min_usd"]) / 1e6
    out = []
    service_seasons = 0
    for y in sorted(int(y) for y in war_by_year):
        if y > LAST_FULL_SEASON or service_seasons >= CONTROL_YEARS:
            break
        war = float(war_by_year[str(y)])
        if service_seasons < pre_arb:
            sal = lm_by_year.get(y, lm_default)
        else:
            i = service_seasons - pre_arb
            frac = fracs[i] if i < len(fracs) else fracs[-1]
            sal = frac * vf.tiered_war_value_usd(war) / 1e6
        out.append(RealizedSeason(y, round(war, 2), round(sal, 3),
                                  _SERVICE_FULL_DAYS))
        service_seasons += 1
    return tuple(out)


def build_cohorts() -> tuple[list[PlayerRecord], dict]:
    listings, cw, cs, bio = _load_inputs()
    records: list[PlayerRecord] = []
    acct = {"listed": 0, "scored": 0, "scored_busts": 0,
            "excluded_no_war": 0, "censored_active": 0,
            "excluded_post_debut_listing": 0, "excluded_no_bio": 0,
            "resolved": 0}
    for (key, year), li in sorted(listings.items()):
        acct["listed"] += 1
        b = bio.get(key)
        if not b:
            acct["excluded_no_bio"] += 1
            continue
        stats_rows = cs.get(key) or []
        war_seasons = (cw.get(key) or {}).get("seasons") or {}
        mlb_seen = _mlb_seasons_from_stats(stats_rows) | {int(y) for y in war_seasons}
        # pre-debut listings only (the harness's clean prospect backtest)
        if any(s < year for s in mlb_seen):
            acct["excluded_post_debut_listing"] += 1
            continue
        if war_seasons:
            debut = min(int(y) for y in war_seasons)
            seasons = _impute_seasons(war_seasons, debut)
            realized = RealizedRecord(key, debut, seasons)
            resolved = (debut + CONTROL_YEARS - 1) <= LAST_FULL_SEASON
        elif mlb_seen:
            # debuted per the level history, but no WAR rows on file —
            # outcome UNKNOWN. Excluded and counted, never zeroed.
            acct["excluded_no_war"] += 1
            continue
        else:
            last = _last_activity(stats_rows)
            if last is not None and last >= WASHED_BEFORE:
                acct["censored_active"] += 1      # may still debut
                continue
            realized = RealizedRecord(key, None, ())   # washed out -> 0
            resolved = True
            acct["scored_busts"] += 1
        lvl = _highest_level_through(stats_rows, year)
        listing = ListingView(
            player_id=key, name=key, listing_year=year, fv=li["fv"],
            is_pitcher=bool(b.get("is_pitcher")), position=b.get("position"),
            age_at_listing=_age_at(b.get("birth_date"), li["date"]),
            eta_years=_LEVEL_ETA.get(lvl or "", 3.5), pre_debut=True)
        records.append(PlayerRecord(listing, realized))
        acct["scored"] += 1
        if resolved:
            acct["resolved"] += 1
    return records, acct


def _resolved_only(records: list[PlayerRecord]) -> list[PlayerRecord]:
    out = []
    for r in records:
        if r.realized.debut_year is None:
            out.append(r)                          # washed busts are resolved
        elif (r.realized.debut_year + CONTROL_YEARS - 1) <= LAST_FULL_SEASON:
            out.append(r)
    return out


def run(persist: bool = True) -> dict:
    cfg = vf._config()
    dpw_by_year = {int(k): dict(v) for k, v in
                   (cfg.get("historical_dollars_per_war") or {}).items()}
    records, acct = build_cohorts()
    log.info("real surplus cohorts: %s", acct)
    full = run_backtest(records, discount_rate=float(cfg["discount_rate"]),
                        dpw_by_year=dpw_by_year, correction_method="isotonic_binned")
    resolved = run_backtest(_resolved_only(records),
                            discount_rate=float(cfg["discount_rate"]),
                            dpw_by_year=dpw_by_year, correction_method="isotonic_binned")
    # Lean the report: drop the big draw-dependent correction tables from the
    # committed artifact (Phase 4 refits them); keep the verdict metrics.
    def _lean(rep: dict) -> dict:
        rep = dict(rep)
        rep.pop("fitted_correction_full_sample", None)
        return rep
    out = {
        "generated_at": date.today().isoformat(),
        "listing_years": list(LISTING_YEARS),
        "accounting": acct,
        "fv_scale": FV_SCALE,
        "gate_scale": GATE_SCALE,
        "conventions": {
            "listing_fv": ("median of each source's earliest same-year snapshot, "
                           f"on the {FV_SCALE} FV scale (gate on {GATE_SCALE}); "
                           "normalized = production's grade_normalization remap "
                           "applied per source BEFORE the median, matching "
                           "consensus.build_timeseries. SURPLUS_FIT_FV_SCALE=raw "
                           "reproduces the pre-2026-07-25 pool exactly"),
            "eta_proxy": "highest level by listing year -> years table (believed-ETA never recorded)",
            "salaries": "IMPUTED: league-min schedule (3 pre-arb) + arb fractions of tiered season value",
            "service": "one full year per season with a WAR row (actual service days not on file)",
            "realized_dpw": "historical $/WAR per season; pre-2020 falls back to nearest year",
            "prediction": "today's standing config incl. v3 FA-implied re-anchor — the level gap is part of what calibration measures (decomposition attributes it)",
            "calibration_applied": "NONE — Phase-0 measurement; correction decision is Phase 4 WS-6",
        },
        "full_pool": _lean(full),
        "resolved_only": _lean(resolved),
    }
    if persist:
        OUT_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
        log.info("wrote %s", OUT_PATH)
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    for slice_name in ("full_pool", "resolved_only"):
        s = rep[slice_name]
        cal = s["raw_calibration"]
        err = s["raw_errors"]
        pit = s["raw_pit"]
        print(f"\n== {slice_name} ==  n={s['n_players']}")
        print(f"  calibration slope {cal['slope']:.3f} (r2 {cal['r2']:.3f}) | "
              f"binned slope {s['binned_calibration'].get('slope', float('nan')):.3f}")
        print(f"  bias {err['bias']:.2f}M  MAE {err['mae']:.1f}M  spearman {err['spearman']:.3f}")
        print(f"  PIT coverage P10-P90 {pit.get('coverage_p10_p90', float('nan')):.2f} (ks_p {pit.get('ks_p', float('nan')):.3f})")
        dec = s["decomposition"]
        print(f"  decomposition: total bias {dec['total_sv_bias']:.2f}M = WAR-layer "
              f"{dec['explained_by_war_bias']:.2f}M + $-layer {dec['dollar_arb_residual_bias']:.2f}M")
    print("\naccounting:", rep["accounting"])
