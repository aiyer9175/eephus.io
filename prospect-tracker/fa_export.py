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


TWO_WAY_NOTE = ("Two-way profile — the market model prices one profile only, "
                "so the predicted contract is a FLOOR, not a point estimate.")


def _compact_fit(f: dict, with_org: bool = True) -> dict:
    """Wire-compact fit row. blockedBy entries carry WHO and WHAT KIND —
    {n, t} where t is 'prospect' (PROSPX near-ETA) or 'mlb' (a contracted
    incumbent already producing at the slot)."""
    blocked = [{"n": b["player_name"], "t": b.get("kind", "prospect")}
               for b in f["components"]["need"]["blocked_by"]]
    out = {
        "fit": f["fit"],
        "need": f["components"]["need"]["score"],
        "window": f["components"]["window"]["score"],
        "afford": f["components"]["afford"]["score"],
        "park": f["components"]["park"]["score"],
        "behavior": f["components"]["behavior"]["score"],
        "blockedBy": blocked or None,
    }
    if with_org:
        out = {"org": f["org"], **out}
    return _clean(out)


def _load_overrides() -> dict[str, dict]:
    """Owner-curated per-player overrides (data/fa_overrides.json):
    two_way / note / exclude. Disclosure and curation only — never
    touches the model. '_'-prefixed keys are documentation."""
    try:
        d = json.loads((DATA_DIR / "fa_overrides.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: v for k, v in (d.get("players") or {}).items()
            if not k.startswith("_") and isinstance(v, dict)}


def _prospect_fv_history(keys: set) -> dict[str, dict]:
    """Read-only Prospect-to-Payday source: condensed consensus-FV arcs from
    the PROSPX boot export, for class members who were tracked prospects.
    mlbam rides along so the caller can id-gate name-key collisions (the FA
    Jacob Webb is NOT the FV-40 prospect Jacob Webb)."""
    path = DATA_DIR / "timeseries.json"
    if not path.exists():
        return {}
    try:
        players = json.loads(path.read_text(encoding="utf-8")).get("players") or []
    except ValueError:
        return {}
    out: dict[str, dict] = {}
    for p in players:
        key = p.get("player_key")
        if key not in keys or not p.get("mlbam_id"):
            continue
        pts: list = []
        last = None
        for pt in (p.get("points") or []):
            fv = pt.get("consensus_fv_raw")
            d = (pt.get("snapshot_date") or "")[:10]
            if fv is None or not d:
                continue
            if last is None or fv != last:
                pts.append([d, round(fv, 1)])
                last = fv
        if len(pts) >= 2:
            out[key] = {"mlbam": int(p["mlbam_id"]), "pts": pts[-40:]}
    return out


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
    # Winter-tracker state: in-class signings (terms from the class page) +
    # the first-seen event ledger. Both empty preseason.
    signings = {k: v for (k, yr), v in storage.load_fa_signings(class_year).items()
                if yr == class_year}
    events = storage.load_fa_events(class_year)
    ev_date = {(e["player_key"], e["event_type"]): e["event_date"] for e in events}
    fv_hist = _prospect_fv_history({p.get("player_key") for p in cls})
    model.supply_by_year[class_year] = fm._supply(
        [{"class_year": class_year, "position": p.get("position")} for p in cls], class_year)
    dpw = fm.winter_dpw(dpw_series, class_year)

    overrides = _load_overrides()
    members = []
    full_fits: list[tuple[dict, list[dict]]] = []   # (member, all-org fits)
    n_proj = 0
    for row in cls:
        ovr = overrides.get(row.get("player_key")) or {}
        if ovr.get("exclude"):
            continue
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
        if ovr.get("two_way"):
            m["twoWay"] = True
        if ovr.get("note") or ovr.get("two_way"):
            m["note"] = ovr.get("note") or TWO_WAY_NOTE
        mlbam = fa_ident.resolve(row["player_name"], range(class_year - 4, class_year))
        if mlbam:
            pos_grp = fm._pos_group(row.get("position"))
            side = "pit" if pos_grp in ("SP", "RP") else "hit"
            seasons = by_player[side].get(mlbam) or {}
            hist = [seasons[t] for t in (class_year - 1, class_year - 2, class_year - 3)
                    if t in seasons]
            # Thin-platform disclosure: a projection riding a missing or
            # injury-shortened platform year is the model's weakest case
            # (Burnes-type) — badge it, don't hide it. The exposure floor
            # scales by season_fraction, so a normal in-progress June season
            # never flags; 30% of a regular's pace does.
            platform = seasons.get(class_year - 1)
            if platform is None:
                m["thinPlatform"] = (f"no {class_year - 1} season in the corpus — "
                                     "projection rides older years")
            else:
                # Full-season volume is ROLE-aware: a reliever at 20 IP in
                # June is on pace, not hurt (65 IP RP season vs 180 SP).
                vol_key, full = (("pa", 600) if side == "hit"
                                 else ("ip", 65 if pos_grp == "RP" else 180))
                vol = platform.get(vol_key) or 0
                if vol < 0.3 * full * max(frac, 0.1):
                    m["thinPlatform"] = (f"only {vol:.0f} {vol_key.upper()} in "
                                         f"{class_year - 1} — injury-thin platform")
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
                    yrs = pred["proj_years"]
                    guar = pred["proj_guarantee_usd"]
                    rational = fm.rational_value_usd(path["war_by_year"][:yrs], class_year, dpw)
                    deal_plus = round(100 * rational / max(guar, 1))
                    # Probability buckets: floor/ceiling WAR paths (Gate-1
                    # empirical quantiles decayed along the aging curves)
                    # price to floor/ceiling rational value -> surplus range.
                    p10_path = path.get("war_by_year_p10")
                    p90_path = path.get("war_by_year_p90")
                    rational_p10 = (fm.rational_value_usd(p10_path[:yrs], class_year, dpw)
                                    if p10_path else None)
                    rational_p90 = (fm.rational_value_usd(p90_path[:yrs], class_year, dpw)
                                    if p90_path else None)
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
                        "warPathP10": p10_path[:max(yrs, 5)] if p10_path else None,
                        "warPathP90": p90_path[:max(yrs, 5)] if p90_path else None,
                        "warTotal": round(sum(path["war_by_year"][:yrs]), 1),
                        "warTotalP10": round(sum(p10_path[:yrs]), 1) if p10_path else None,
                        "warTotalP90": round(sum(p90_path[:yrs]), 1) if p90_path else None,
                        "projYears": yrs,
                        "projYearsP10": pred.get("proj_years_p10"),
                        "projYearsP90": pred.get("proj_years_p90"),
                        "projGuar": guar,
                        "projGuarP10": pred.get("proj_guarantee_p10_usd"),
                        "projGuarP90": pred.get("proj_guarantee_p90_usd"),
                        "projAav": pred["proj_aav_usd"],
                        "projAavP10": pred.get("proj_aav_p10_usd"),
                        "projAavP90": pred.get("proj_aav_p90_usd"),
                        "rational": rational,
                        "surplus": rational - guar,
                        "surplusP10": (rational_p10 - guar) if rational_p10 is not None else None,
                        "surplusP90": (rational_p90 - guar) if rational_p90 is not None else None,
                        "dealPlus": deal_plus,
                        "verdict": fm.deal_verdict(deal_plus),
                        "comps": [_clean({"name": c["player_name"], "yr": c["class_year"],
                                          "to": c.get("to_team"), "years": c.get("years"),
                                          "guar": c.get("guarantee_usd")}) for c in comps],
                        "fits": [_compact_fit(f) for f in fits],
                    }))
                    n_proj += 1
        # Winter overrides: the reconciled pipeline status beats the stale
        # as-scraped payload status, and signed members carry their ACTUAL
        # terms next to the prediction (the tracker's whole point).
        key = row.get("player_key")
        sgn = signings.get(key)
        if sgn:
            m["status"] = "signed"
            m.update(_clean({
                "signedTo": sgn.get("to_team"),
                "signedYears": sgn.get("years"),
                "signedGuar": sgn.get("guarantee_usd"),
                "signedAav": sgn.get("aav_usd"),
                "signedDate": ev_date.get((key, "signing")),
                "signedMilb": True if sgn.get("mlb_deal") is False else None,
                "qoAccepted": True if sgn.get("qo_accepted") else None,
            }))
        elif (key, "option_exercised") in ev_date:
            m["status"] = "option_exercised"
        # Prospect-to-Payday arc — id-gated so a name-key collision can
        # never paste a prospect's FV history onto a same-named veteran.
        arc = fv_hist.get(key)
        if arc and mlbam and arc["mlbam"] == mlbam:
            m["fvArc"] = arc["pts"]
        members.append(m)
    members.sort(key=lambda m: -(m.get("projGuar") or 0))
    # Per-team fit lists covering ALL 30 orgs (the member rows only carry
    # top-3, which left half the league without a Fits view). Members are
    # referenced by post-sort index ("i") so nothing is duplicated; top-12
    # per org keeps the block ~40KB.
    idx_of = {id(m): i for i, m in enumerate(members)}
    team_fits: dict[str, list[dict]] = defaultdict(list)
    for m, fits in full_fits:
        for f in fits:
            team_fits[f["org"]].append(_clean({"i": idx_of[id(m)],
                                               **_compact_fit(f, with_org=False)}))
    team_fits = {org: sorted(rows, key=lambda r: -r["fit"])[:12]
                 for org, rows in sorted(team_fits.items())}
    thr = fa_cba.cbt_threshold(class_year)
    return {
        "generated_at": date.today().isoformat(),
        "class_year": class_year,
        "dpw_usd": int(dpw),
        "dpw_infl": fm._dpw_inflation(),
        "cba_carry_forward": bool(thr.get("carry_forward")),
        "n_members": len(members), "n_projected": n_proj,
        "n_signed": sum(1 for m in members if m.get("status") == "signed"),
        "members": members,
        "teamFits": team_fits,
        # First-seen winter events (newest first, capped) — the WIRE and the
        # Signing Tracker timeline. Dates are observation stamps, not
        # Spotrac dates (the source publishes none).
        "events": [_clean({
            "date": e["event_date"], "type": e["event_type"],
            "key": e["player_key"], "name": e.get("player_name"),
            "pos": e.get("position"), "from": e.get("from_team"),
            "to": e.get("to_team"), "years": e.get("years"),
            "guar": e.get("guarantee_usd"), "aav": e.get("aav_usd"),
            "qo": True if e.get("qo") else None,
            "milb": True if e.get("mlb_deal") is False else None,
            "optPrice": e.get("option_price_usd"),
        }) for e in events[:80]],
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


def _source_freshness() -> dict:
    """MAX(fetched_at) per FA source table — the UI's staleness stamps.
    Read-only; missing tables (fresh DB) just drop out."""
    out = {}
    try:
        with storage.connect() as con:
            for label, table in (("class", "fa_class_players"),
                                 ("signings", "fa_signings"),
                                 ("payroll", "fa_team_payroll"),
                                 ("parks", "fa_park_factors")):
                r = con.execute(f"SELECT MAX(fetched_at) FROM {table}").fetchone()
                if r and r[0]:
                    out[label] = str(r[0])[:10]
    except Exception:                                    # noqa: BLE001 — stamps are best-effort
        pass
    return out


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
    # Per-team blocked positions (the needs matrix's blocker lists, both
    # kinds): blocked teams fall OUT of the top-fits lists by construction
    # (their need craters), so the Fits view names the blockers here —
    # "why isn't this team shopping at SS" is half the product.
    needs = fa_fit.needs_matrix(class_year)
    teams = {}
    for org in sorted(set(afford) | set(priors) | set(bases)):
        a, b, w = afford.get(org) or {}, priors.get(org) or {}, bases.get(org) or {}
        blocked = []
        for pos, cell in (needs.get(org) or {}).items():
            for bl in cell.get("mlb_blockers") or []:
                blocked.append({"pos": pos, "n": bl["player_name"], "t": "mlb",
                                "w": bl.get("war_proj")})
            for bl in (cell.get("blockers") or [])[:1]:
                blocked.append({"pos": pos, "n": bl["player_name"], "t": "prospect"})
        teams[org] = _clean({
            "committed": a.get("committed_usd"),
            "taxPayroll": a.get("tax_payroll_usd"),
            "space": a.get("space_usd"),
            "payor": a.get("payor_status"),
            "maxGuar": b.get("max_guarantee_usd"), "n100m": b.get("n_100m"),
            "recentSpend": b.get("recent_spend_usd"),
            "baseWins": w.get("baseline_wins"),
            "blocked": blocked or None,
        })
    try:
        dpw_series = json.loads((DATA_DIR / "fa_dpw_series.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dpw_series = None
    return {
        "generated_at": date.today().isoformat(),
        "class_year": class_year,
        "sources": _source_freshness(),
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
