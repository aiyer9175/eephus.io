# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
"""Emit the Phase-4 Star Odds artifacts:

  * data/star_odds_eval.json  -- the tier calibration report (MODEL tier-aggregate
    star odds vs the FanGraphs 2026 PUBLISHED tier odds, per role, max abs dev).
  * data/star_label_view.json -- the xFV training-label view (player, debut class,
    control seasons, star boolean) built from REAL realized MLB WAR. No synthesized
    outcomes: a player appears only if we hold his per-season WAR + a debut year.

Run:  python -m tools.build_star_odds_artifacts     (from repo root)
"""
from __future__ import annotations

import datetime as _dt
import json
import sqlite3
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
_DATA = _ROOT / "data"

# Star window: the clemens_2026 control window (7 seasons) is the star definition
# window. The label counts seasons of >= 4 WAR within [debut_year .. debut_year+6].
_STAR_MIN_SEASONS = 2
_STAR_WAR = 4.0
_CONTROL_YEARS = 7
_RESOLVED_THROUGH = 2025   # last complete MLB season (efv_dataset convention)


def _today() -> str:
    return _dt.date.today().isoformat()


def _debut_years() -> dict[str, dict]:
    """player_key -> {debut_year, name} from data/debuts.json."""
    out: dict[str, dict] = {}
    try:
        rows = json.loads((_DATA / "debuts.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return out
    for r in rows:
        pk = r.get("player_key")
        dd = r.get("debut_date")
        if not pk or not dd:
            continue
        try:
            yr = int(str(dd)[:4])
        except ValueError:
            continue
        out[pk] = {"debut_year": yr, "name": r.get("player_name") or r.get("name")}
    return out


def _career_seasons() -> dict[str, dict]:
    """player_key -> {year(int): war(float)} from the career_war table."""
    db = _ROOT / "prospects.db"
    out: dict[str, dict] = {}
    if not db.exists():
        return out
    con = sqlite3.connect(str(db))
    try:
        cur = con.execute("SELECT player_key, payload_json FROM career_war")
        for pk, pj in cur.fetchall():
            if not pj:
                continue
            try:
                seasons = (json.loads(pj) or {}).get("seasons") or {}
            except ValueError:
                continue
            parsed = {}
            for y, w in seasons.items():
                try:
                    parsed[int(y)] = float(w)
                except (TypeError, ValueError):
                    continue
            if parsed:
                out[pk] = parsed
    finally:
        con.close()
    return out


def build_label_view() -> dict:
    debuts = _debut_years()
    seasons_by_pk = _career_seasons()
    players = []
    n_star = n_star_career = n_resolved = 0
    for pk, seasons in seasons_by_pk.items():
        meta = debuts.get(pk)
        if not meta:
            continue   # no debut year -> cannot define the control window; skip (no synthesis)
        dy = meta["debut_year"]
        window = list(range(dy, dy + _CONTROL_YEARS))
        ctrl = [(y, seasons[y]) for y in window if y in seasons]
        n_ge4_window = sum(1 for _, w in ctrl if w >= _STAR_WAR)
        n_ge4_career = sum(1 for w in seasons.values() if w >= _STAR_WAR)
        star = n_ge4_window >= _STAR_MIN_SEASONS
        star_career = n_ge4_career >= _STAR_MIN_SEASONS
        resolved = (dy + _CONTROL_YEARS - 1) <= _RESOLVED_THROUGH
        n_star += int(star)
        n_star_career += int(star_career)
        n_resolved += int(resolved)
        players.append({
            "player_key": pk,
            "name": meta.get("name"),
            "debut_year": dy,
            "control_window": [window[0], window[-1]],
            "control_seasons": [[y, round(w, 2)] for y, w in ctrl],
            "n_seasons_ge4_window": n_ge4_window,
            "n_seasons_ge4_career": n_ge4_career,
            "star": star,
            "star_career": star_career,
            "window_resolved": resolved,
        })
    players.sort(key=lambda p: (-p["n_seasons_ge4_career"], p["debut_year"]))
    n = len(players)
    return {
        "generated_at": _today(),
        "artifact": "xFV star-label training view (Phase 4)",
        "definition": {
            "min_seasons": _STAR_MIN_SEASONS, "war_threshold": _STAR_WAR,
            "control_years": _CONTROL_YEARS, "window": "debut_year .. debut_year+6",
        },
        "source": "REAL realized MLB WAR: prospects.db career_war (per-season bWAR) "
                  "joined to data/debuts.json debut years. No synthesized outcomes.",
        "control_note": "No true MLB service-time field exists; 'control seasons' is "
                        "the debut+0..+6 proxy (existing efv_dataset convention). "
                        "Windows with debut_year > 2019 are not fully resolved through "
                        f"{_RESOLVED_THROUGH} (window_resolved=false) and may undercount stars.",
        "counts": {
            "n_players": n,
            "n_star_window": n_star,
            "n_star_career": n_star_career,
            "n_window_resolved": n_resolved,
            "base_rate_window": round(n_star / n, 4) if n else None,
            "base_rate_career": round(n_star_career / n, 4) if n else None,
        },
        "small_class_caveat": "The star-positive class is small (~1e2); usable as a "
                              "label SOURCE / view, not yet a trained model.",
        "players": players,
    }


def _realized_calibration() -> dict:
    """GROUND-TRUTH the displayed (published) star odds against REALIZED outcomes:
    join each debuted prospect's pre-debut consensus FV (efv_dataset) to whether he
    actually posted 2+ control seasons of >=4 WAR (star_label_view), bucket by FV
    tier, and compare the realized star rate to the published table value. Real data
    only; window-resolved players only (outcome fully observed). Best-effort: returns
    {} if the eFV dataset / labels are unavailable. This is the accountability answer
    to 'are the star odds accurate' -- it is REPORTED, it does not change the odds."""
    try:
        import efv_dataset
        import value_framework as vf
        labels = {p["player_key"]: p for p in
                  json.loads((_DATA / "star_label_view.json").read_text(encoding="utf-8"))["players"]}
    except Exception:
        return {}
    tiers = [("<50", 20.0, 48.75, 47.5), ("50-55", 48.75, 52.5, 52.5),
             ("55-60", 52.5, 57.5, 57.5), ("60-65", 57.5, 63.75, 62.5),
             ("65+", 63.75, 90.0, 66.0)]
    out = {"note": ("Realized window-star rate (2+ control seasons of >=4 WAR) by pre-debut "
                    "consensus FV, vs the displayed published table. Window-resolved debuts only "
                    "(fully observed outcome). Small classes; a calibration read, not a refit."),
           "definition": "2+ seasons of >=4 WAR in debut..debut+6", "roles": {}}
    for side, is_pit, role in (("hit", False, "hitter"), ("pit", True, "pitcher")):
        try:
            rows = efv_dataset.build_matrix(side)
            rows = rows[0] if isinstance(rows, tuple) else rows
        except Exception:
            continue
        rec = []
        for r in rows:
            if r.get("kind") != "debuted":
                continue
            fv = r.get("consensus_fv_raw")
            lab = labels.get(r.get("player_key"))
            if fv is None or lab is None or not lab.get("window_resolved"):
                continue
            rec.append((float(fv), int(bool(lab.get("star")))))
        role_rows = []
        for label, lo, hi, mid in tiers:
            sub = [y for fv, y in rec if lo <= fv < hi]
            if not sub:
                continue
            role_rows.append({"tier": label, "n": len(sub), "stars": int(sum(sub)),
                              "realized": round(sum(sub) / len(sub), 3),
                              "published": round(float(vf.published_star_odds(mid, is_pit)), 3)})
        out["roles"][role] = {"n": len(rec), "tiers": role_rows}
    return out


def build_calibration_eval() -> dict:
    import value_framework as vf
    cal = vf.star_odds_calibration("clemens_2026")
    surplus_cal = vf.surplus_tier_calibration("clemens_2026")
    recon = vf.fit_tier_reconciliation("clemens_2026")
    max_dev = max((v["max_abs_dev"] for v in cal["roles"].values()), default=None)
    tol = 0.10   # documented per-tier tolerance (see the recalibration spec)
    passed = max_dev is not None and max_dev <= tol
    return {
        "generated_at": _today(),
        "experiment": "star-odds-calibration",
        "model": "star_odds (P>=2 control seasons of >=4 WAR; mixture Poisson-binomial)",
        "seed": None,
        "method": {
            "model_odds": "analytic: per bucket, per control season WAR ~ Gamma(mean=level, "
                          "cv=within_bucket_cv); Poisson-binomial P(>=2 of n); weighted by "
                          "P(bucket|FV); pitchers blend SP/RP by P(reliever|bucket).",
            "published": "FanGraphs 2026 tier star odds (config/valuation_sets/clemens_2026.yaml).",
            "priced_under": "clemens_2026 (control_years=7, star def 2x4 WAR).",
            "note": "Model uses the v47 realized (bust-heavy) WAR anchors, so at the production "
                    "anchor (war_anchor_scale=1) it runs BELOW the published tier odds. The "
                    "DISPLAYED star odds are the published table values (exact by construction); "
                    "the per-player model is a diagnostic. The `reconciliation` block reports the "
                    "single per-role WAR-anchor multiplier (k) that best aligns the model "
                    "aggregates to the published tiers and the RESIDUAL after it -- reported, NOT "
                    "forced onto the live board (the shipped set carries no such scale).",
        },
        "calibration": cal,
        "surplus_calibration": surplus_cal,
        "reconciliation": recon,
        "realized_calibration": _realized_calibration(),
        "gate": {
            "tolerance_abs": tol,
            "max_abs_dev": max_dev,
            "pass": passed,
            "verdict": "provisional",
            "reason": "Displayed odds = published table (exact). Model odds are a diagnostic; at "
                      "the production anchor the deviation exceeds tolerance. The reconciliation "
                      "block characterizes the gap as a best-fit anchor multiplier (k_h, k_p) plus "
                      "an irreducible residual -- a single scalar cannot zero both the surplus and "
                      "star-odds residuals, so the residual is disclosed, not snapped.",
        },
    }


def main() -> None:
    # Build + WRITE the label view FIRST. build_calibration_eval() ->
    # _realized_calibration() reads data/star_label_view.json, so it must be on
    # disk and reflect THIS run before the eval is computed. Previously the eval
    # ran first, so realized_calibration always read the PREVIOUS run's labels
    # (or {} on a first/cleared run). Pure reorder - no model math changes.
    label_doc = build_label_view()
    (_DATA / "star_label_view.json").write_text(
        json.dumps(label_doc, indent=1) + "\n", encoding="utf-8")
    c = label_doc["counts"]
    print(f"wrote {_DATA / 'star_label_view.json'} "
          f"(n={c['n_players']}, star_window={c['n_star_window']}, star_career={c['n_star_career']})")
    eval_doc = build_calibration_eval()
    (_DATA / "star_odds_eval.json").write_text(
        json.dumps(eval_doc, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {_DATA / 'star_odds_eval.json'} "
          f"(max_abs_dev={eval_doc['gate']['max_abs_dev']}, pass={eval_doc['gate']['pass']})")


if __name__ == "__main__":
    main()
