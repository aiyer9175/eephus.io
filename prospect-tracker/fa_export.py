# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Sidecar exports for the MLB Free Agency module (Stage 5).

Three sidecars consumed by the standalone /fa/ surface (assets/fa.js +
build_site.py::build_fa — the FA module is SEPARATE from PROSPX, which
carries zero FA bytes; these are fetched from /data/ directly):

  fa_class.json    the 2026-27 Class Board: every constructed member with
                   status/option flags, and — where identity + history
                   resolve — the gated projection, market prediction with
                   bands (mYears/mGuarantee/mAAV), rational value, Contract
                   Surplus ($), Deal+, real comps, and top team fits.
  fa_archive.json  twelve archived winters: condensed signings with the
                   retrospective ledger, per-winter totals and implied $/WAR.
  fa_meta.json     CBA snapshot (carry-forward flags ride every consumer),
                   the estimated $/WAR series, BOTH gate verdicts verbatim
                   (the Accountability surface renders this — misses and
                   all), park factors, team affordability + behavior priors.

Money is exported in raw USD; the frontend's formatMetric(`moneyM`)
owns display rounding. Nulls are omitted; floats rounded — lean wire
format per the owner's load-time ask.
"""

from __future__ import annotations

import json
import logging
from collections import defaultdict
from datetime import date
from pathlib import Path

import fa_cba
import fa_fit
import fa_ident
import fa_market as fm
import fa_projection as fp
import storage

log = logging.getLogger(__name__)

DATA_DIR = Path(__file__).parent / "data"
CLASS_YEAR = 2027


def _clean(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None and v != [] and v != {}}


def build_fa_class_payload(class_year: int = CLASS_YEAR) -> dict:
    corpus = fp.build_corpus()
    league = corpus["league"]
    curves, war_map = fp.fitted_models(corpus, class_year - 1)
    frac = fp.season_fraction(league, class_year - 1)
    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r

    enriched = fm.enriched_signings(2015, class_year - 1)
    dpw_series = fm.dollars_per_war_by_winter(enriched)
    model = fm.MarketModel(enriched, dpw_series)
    cls = list(storage.load_fa_class_players(class_year).values())
    model.supply_by_year[class_year] = fm._supply(
        [{"class_year": class_year, "position": p.get("position")} for p in cls], class_year)
    dpw = fm.winter_dpw(dpw_series, class_year)

    members = []
    full_fits: list[tuple[dict, list[dict]]] = []   # (member, all-org fits)
    n_proj = 0
    for row in cls:
        m = _clean({
            "key": row.get("player_key"), "name": row["player_name"],
            "pos": row.get("position"), "age": row.get("age"),
            "from": row.get("from_team"), "bt": row.get("bat_throw"),
            "status": row.get("status"), "type": row.get("fa_type"),
            "optPrice": row.get("option_price_usd"),
            "enterProb": row.get("enter_prob"),
            "prevAav": row.get("prev_aav_usd"), "prevWar": row.get("prev_war"),
            "qoValue": row.get("qo_value_usd"),
        })
        mlbam = fa_ident.resolve(row["player_name"], range(class_year - 4, class_year))
        if mlbam:
            pos_grp = fm._pos_group(row.get("position"))
            side = "pit" if pos_grp in ("SP", "RP") else "hit"
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (class_year - 1, class_year - 2, class_year - 3)
                    if t in seasons]
            if hist:
                age_prev = next((h.get("age") for h in hist if h.get("age")), None)
                age = ((age_prev + (class_year - hist[0]["season"])) if age_prev
                       else int(row.get("age") or 30))
                path = fm.contract_war_path(hist, side, class_year, 10, age,
                                            curves, war_map, league,
                                            in_progress=(class_year - 1, frac))
                if path:
                    s = {**row, "_war_path": path, "_age": age, "class_year": class_year}
                    pred = model.predict(s)
                    yrs = pred["m_years"]
                    rational = fm.rational_value_usd(path["war_by_year"][:yrs], class_year, dpw)
                    comps = fm.comps_for(s, enriched, k=3)
                    # Full 30-org fit vector: top-3 rides the member row (the
                    # board's Fits column), the rest feeds the per-team view
                    # via the compact teamFits block below.
                    all_fits = fa_fit.fit_scores(s, pred, class_year, top_n=30)
                    fits = all_fits[:3]
                    full_fits.append((m, all_fits))
                    m.update(_clean({
                        "warY1": path["war_y1"],
                        "warPath": path["war_by_year"][:max(yrs, 5)],
                        "mYears": yrs,
                        "mYearsP10": pred.get("m_years_p10"), "mYearsP90": pred.get("m_years_p90"),
                        "mGuar": pred["m_guarantee_usd"],
                        "mGuarP10": pred.get("m_guarantee_p10_usd"),
                        "mGuarP90": pred.get("m_guarantee_p90_usd"),
                        "mAav": pred["m_aav_usd"],
                        "mAavP10": pred.get("m_aav_p10_usd"), "mAavP90": pred.get("m_aav_p90_usd"),
                        "rational": rational,
                        "surplus": rational - pred["m_guarantee_usd"],
                        "dealPlus": round(100 * rational / max(pred["m_guarantee_usd"], 1)),
                        "comps": [_clean({"name": c["player_name"], "yr": c["class_year"],
                                          "to": c.get("to_team"), "years": c.get("years"),
                                          "guar": c.get("guarantee_usd")}) for c in comps],
                        "fits": [_clean({
                            "org": f["org"], "fit": f["fit"],
                            "need": f["components"]["need"]["score"],
                            "window": f["components"]["window"]["score"],
                            "afford": f["components"]["afford"]["score"],
                            "park": f["components"]["park"]["score"],
                            "behavior": f["components"]["behavior"]["score"],
                            "blockedBy": [b["player_name"] for b in
                                          f["components"]["need"]["blocked_by"]] or None,
                        }) for f in fits],
                    }))
                    n_proj += 1
        members.append(m)
    members.sort(key=lambda m: -(m.get("mGuar") or 0))
    # Per-team fit lists covering ALL 30 orgs (the member rows only carry
    # top-3, which left half the league without a Fits view). Members are
    # referenced by post-sort index ("i") so nothing is duplicated; top-12
    # per org keeps the block ~40KB.
    idx_of = {id(m): i for i, m in enumerate(members)}
    team_fits: dict[str, list[dict]] = defaultdict(list)
    for m, fits in full_fits:
        for f in fits:
            team_fits[f["org"]].append(_clean({
                "i": idx_of[id(m)], "fit": f["fit"],
                "need": f["components"]["need"]["score"],
                "window": f["components"]["window"]["score"],
                "afford": f["components"]["afford"]["score"],
                "park": f["components"]["park"]["score"],
                "behavior": f["components"]["behavior"]["score"],
                "blockedBy": [b["player_name"] for b in
                              f["components"]["need"]["blocked_by"]] or None,
            }))
    team_fits = {org: sorted(rows, key=lambda r: -r["fit"])[:12]
                 for org, rows in sorted(team_fits.items())}
    thr = fa_cba.cbt_threshold(class_year)
    return {
        "generated_at": date.today().isoformat(),
        "class_year": class_year,
        "dpw_usd": int(dpw),
        "cba_carry_forward": bool(thr.get("carry_forward")),
        "n_members": len(members), "n_projected": n_proj,
        "members": members,
        "teamFits": team_fits,
    }


def build_fa_archive_payload(first: int = 2015, last: int = CLASS_YEAR - 1) -> dict:
    try:
        series = json.loads((DATA_DIR / "fa_dpw_series.json").read_text(encoding="utf-8"))
        dpw_by = {int(k): v for k, v in series["usd_per_war_by_winter"].items()}
    except (OSError, ValueError, KeyError):
        dpw_by = {}
    winters = []
    for year in range(first, last + 1):
        rows = []
        spend = 0
        for s in storage.load_fa_signings(year).values():
            led = s.get("ledger") or {}
            rows.append(_clean({
                "key": s.get("player_key"), "name": s["player_name"],
                "pos": s.get("position"), "from": s.get("from_team"),
                "to": s.get("to_team"), "years": s.get("years"),
                "guar": s.get("guarantee_usd"), "aav": s.get("aav_usd"),
                "qo": s.get("qo") or None, "milb": (not s.get("mlb_deal")) or None,
                "warTd": led.get("war_to_date"),
                "surplusTd": led.get("surplus_to_date_usd"),
                "done": led.get("complete"),
            }))
            spend += s.get("guarantee_usd") or 0
        rows.sort(key=lambda r: -(r.get("guar") or 0))
        winters.append({
            "year": year, "n": len(rows), "spend_usd": spend,
            "dpw_usd": int(dpw_by[year]) if year in dpw_by else None,
            "qo_offered": fa_cba.qo_offered_count(year),
            "signings": rows,
        })
    return {"generated_at": date.today().isoformat(), "winters": winters}


def build_fa_meta_payload(class_year: int = CLASS_YEAR) -> dict:
    def _gate(path: str):
        try:
            return json.loads((DATA_DIR / path).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    thr = fa_cba.cbt_threshold(class_year)
    afford = fa_fit.affordability(class_year)
    priors = fa_fit.behavior_priors()
    bases = fa_fit.team_baselines(class_year)
    teams = {}
    for org in sorted(set(afford) | set(priors) | set(bases)):
        a, b, w = afford.get(org) or {}, priors.get(org) or {}, bases.get(org) or {}
        teams[org] = _clean({
            "committed": a.get("committed_usd"), "space": a.get("space_usd"),
            "payor": a.get("payor_status"),
            "maxGuar": b.get("max_guarantee_usd"), "n100m": b.get("n_100m"),
            "baseWins": w.get("baseline_wins"),
        })
    try:
        dpw_series = json.loads((DATA_DIR / "fa_dpw_series.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dpw_series = None
    return {
        "generated_at": date.today().isoformat(),
        "class_year": class_year,
        "cba": {"threshold_usd": thr["threshold_usd"],
                "carry_forward": thr["carry_forward"],
                "regime": thr.get("regime"),
                "unverified_records": len(fa_cba.unverified_records())},
        "dpw_series": dpw_series,
        "gate1": _gate("fa_gate1_eval.json"),
        "gate2": _gate("fa_gate2_eval.json"),
        "park_factors": fa_fit.park_factors(class_year - 1),
        "teams": teams,
    }


def export_all() -> dict[str, int]:
    sizes = {}
    for name, payload in (("fa_class.json", build_fa_class_payload()),
                          ("fa_archive.json", build_fa_archive_payload()),
                          ("fa_meta.json", build_fa_meta_payload())):
        raw = json.dumps(payload, separators=(",", ":"))
        (DATA_DIR / name).write_text(raw, encoding="utf-8")
        sizes[name] = len(raw)
    log.info("fa exports: %s", {k: f"{v/1024:.0f}KB" for k, v in sizes.items()})
    return sizes


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(export_all())
