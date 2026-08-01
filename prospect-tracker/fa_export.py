# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Sidecar exports for the MLB Free Agency module (Stage 5).

Three sidecars consumed by the standalone /fa/ surface (assets/fa.js +
build_site.py::build_fa - the FA module is SEPARATE from PROSPX, which
carries zero FA bytes; these are fetched from /data/ directly):

  fa_class.json    the 2026-27 Class Board: every constructed member with
                   status/option flags, and - where identity + history
                   resolve - the gated projection, market prediction with
                   bands (mYears/mGuarantee/mAAV), rational value, Contract
                   Surplus ($), Deal+, real comps, and top team fits.
  fa_archive.json  twelve archived winters: condensed signings with the
                   retrospective ledger, per-winter totals and implied $/WAR.
  fa_meta.json     CBA snapshot (carry-forward flags ride every consumer),
                   the estimated $/WAR series, BOTH gate verdicts verbatim
                   (the Accountability surface renders this - misses and
                   all), park factors, team affordability + behavior priors.

Money is exported in raw USD; the frontend's formatMetric(`moneyM`)
owns display rounding. Nulls are omitted; floats rounded - lean wire
format per the owner's load-time ask.
"""

from __future__ import annotations

import json
import logging
import statistics
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


TWO_WAY_NOTE = ("Two-way profile - the market model prices one profile only, "
                "so the predicted contract is a FLOOR, not a point estimate.")


def _compact_fit(f: dict, with_org: bool = True) -> dict:
    """Wire-compact fit row. blockedBy entries carry WHO and WHAT KIND - 
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
    two_way / note / exclude. Disclosure and curation only - never
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


def _class_supply_rows(cls: list[dict], class_year: int,
                       by_player: dict[str, dict[int, dict]]) -> list[dict]:
    """ARM supply_pop: the class-supply population under the ALIGNED
    definition -- members whose identity resolves against war_daily AND who
    carry >=1 corpus season inside the 3-season history window; exactly the
    members the market model can price, and the serve-time analog of the
    enriched TRAINING filter (mlb_deal + mlbam_id + corpus history -- see
    fm.enriched_signings). Fringe class members bound for minors deals fail
    the same bar here that their signings fail at train time, so train and
    serve count the same population definition. fa_ident.resolve rides an
    lru-cached index, so the member loop's later resolve is a dict hit."""
    out = []
    for row in cls:
        mlbam = fa_ident.resolve(row["player_name"], range(class_year - 4, class_year))
        if not mlbam:
            continue
        side = "pit" if fm._pos_group(row.get("position")) in ("SP", "RP") else "hit"
        seasons = by_player[side].get(mlbam) or {}
        if any(t in seasons for t in (class_year - 1, class_year - 2, class_year - 3)):
            out.append({"class_year": class_year, "position": row.get("position")})
    return out


# --- MLB projections bridge (future FA classes) -----------------------------
# For class years beyond CLASS_YEAR the platform season hasn't happened yet, so
# the Marcel engine rides stale history (every member flags thinPlatform). The
# /projections/ module already runs the same FA engine forward (5-year war[]
# from first_season), so for FUTURE classes we overlay its per-player WAR path
# (joined by mlbam, then player_key) and let the market model re-price AAV /
# guarantee / surplus off it. Falls back to the Marcel path when unprojected.
_MLB_PROJ_CACHE: dict | None = None


def _load_mlb_projections() -> dict:
    global _MLB_PROJ_CACHE
    if _MLB_PROJ_CACHE is None:
        try:
            d = json.loads((DATA_DIR / "mlb_projections.json").read_text(encoding="utf-8"))
        except (OSError, ValueError):
            d = {}
        vets = d.get("vets") or []
        _MLB_PROJ_CACHE = {
            "first_season": d.get("first_season"),
            "by_mlbam": {v["mlbam"]: v for v in vets if v.get("mlbam")},
            "by_key": {v["key"]: v for v in vets if v.get("key")},
        }
    return _MLB_PROJ_CACHE


def _apply_proj_override(path: dict, pv: dict, class_year: int,
                         first_season: int | None) -> bool:
    """Overlay the projection module's war[] onto `path` (mutates in place),
    aligned so projection season == class_year maps to path year 1. Keeps the
    Marcel-decayed tail for contract years the 5y projection doesn't reach.
    Returns True when applied."""
    if first_season is None:
        return False
    start = class_year - first_season
    # BASIS (2026-07-24 FA lane) -- this used to read pv["war"], proj_ml's q50
    # QUANTILE head, and splice it into a stack whose pricer
    # (rational_value_usd through the convex tier curve) and whose every
    # market feature (war_y1, log_rational, prime_war) are calibrated on
    # champion MEAN paths. Measured on the served payloads: mlb_projections
    # year-1 league sum is 602.8 WAR on `war` vs 984.4 on `warChamp`; across
    # the 212 players the 2027 class shares with it, in the SAME season,
    # fa_class's own champion warY1 sums to 191.4 and warChamp[0] to 191.4
    # (ratio 1.000) while war[0] sums to 90.7 (ratio 0.474). The q50 head is
    # also unfloored, which is why 72 of the served 2028 members carried a
    # negative season in warPath and 176 in warPathP10 while
    # tiered_war_value_usd() truncates negatives at 0 -- warTotal and
    # rational then described different paths on the same row.
    war = pv.get("warChamp") or pv.get("war") or []
    if start < 0 or start >= len(war):
        return False
    new = war[start:]

    def _decay_ratio(seq: list) -> float:
        # Continue the projection's own recent year-over-year decline; clamp to
        # a sane aging band, default ~0.82 when it can't be inferred.
        if len(seq) >= 2 and seq[-2] > 0:
            return max(0.5, min(0.95, seq[-1] / seq[-2]))
        return 0.82

    def _overlay(key: str, src: list | None) -> None:
        # Overlay the projected years, then EXTEND past the projection horizon
        # by decaying the last projected value (not the stale Marcel tail, which
        # collapses to ~0 for young stars on long future-class deals).
        cur = path.get(key)
        seq = (src or [])[start:]
        if not seq or not isinstance(cur, list):
            return
        seq = [max(0.0, float(v)) for v in seq]   # fm._decay_path floors at 0
        cur[:len(seq)] = seq
        ratio = _decay_ratio(seq)
        last = seq[-1]
        for i in range(len(seq), len(cur)):
            last = round(max(0.0, last * ratio), 2)
            cur[i] = last

    _overlay("war_by_year", war)        # champion MEAN path
    path["war_y1"] = new[0]
    # Bands: proj_ml's quantile heads are cut around its OWN q50, so their
    # absolute spread is transferred onto the champion mean rather than
    # spliced raw (a raw splice puts p90 below the mean wherever champ >
    # q90). Floored at 0 like fm._decay_path, then clamped so the invariant
    # p10 <= mean <= p90 holds on every served season.
    q50 = pv.get("war") or []
    for key, src in (("war_by_year_p10", pv.get("warP10")),
                     ("war_by_year_p90", pv.get("warP90"))):
        if src and q50 and len(src) == len(q50) == len(war):
            _overlay(key, [w + (q - m) for w, q, m in zip(war, src, q50)])
        else:
            _overlay(key, src)
    lo, hi = path.get("war_by_year_p10"), path.get("war_by_year_p90")
    for t, w in enumerate(path["war_by_year"]):
        if isinstance(lo, list) and t < len(lo):
            lo[t] = round(min(lo[t], w), 2)
        if isinstance(hi, list) and t < len(hi):
            hi[t] = round(max(hi[t], w), 2)
    path["war_total"] = round(sum(path["war_by_year"]), 2)
    return True


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
    if fm.X_FEATURES.get("supply_pop"):
        # ARM supply_pop (default OFF; pre-registered in
        # tools/fa_market_feature_lab.py): serve-time supply counts the
        # ALIGNED population (identity+history members, the analog of the
        # enriched training filter) instead of the whole scraped class,
        # whose counts z-scored +2.6..+2.8 against the training moments.
        model.supply_by_year[class_year] = fm._supply(
            _class_supply_rows(cls, class_year, by_player), class_year)
    else:
        model.supply_by_year[class_year] = fm._supply(
            [{"class_year": class_year, "position": p.get("position")} for p in cls], class_year)
    dpw = fm.winter_dpw(dpw_series, class_year)
    # The rate this winter carries dollars forward at. Estimated from the
    # module's OWN realized $/WAR series over the training winters (see
    # fm._destale_rate) instead of borrowing value_framework's
    # dollars_per_war_inflation, which is 0.0 in production for a
    # prospect-side reason and silently made three separate FA mechanisms
    # no-ops (comps de-staling, rational-value escalation, the $/WAR carry).
    destale = fm._destale_rate(dpw_series, class_year)

    overrides = _load_overrides()
    proj = _load_mlb_projections()   # future-class WAR override source
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
            # (Burnes-type) - badge it, don't hide it. The exposure floor
            # scales by season_fraction, so a normal in-progress June season
            # never flags; 30% of a regular's pace does.
            platform = seasons.get(class_year - 1)
            if platform is None:
                m["thinPlatform"] = (f"no {class_year - 1} season in the corpus - "
                                     "projection rides older years")
            else:
                # Full-season volume is ROLE-aware: a reliever at 20 IP in
                # June is on pace, not hurt (65 IP RP season vs 180 SP).
                vol_key, full = (("pa", 600) if side == "hit"
                                 else ("ip", 65 if pos_grp == "RP" else 180))
                vol = platform.get(vol_key) or 0
                if vol < 0.3 * full * max(frac, 0.1):
                    m["thinPlatform"] = (f"only {vol:.0f} {vol_key.upper()} in "
                                         f"{class_year - 1} - injury-thin platform")
            if hist:
                if fm.X_FEATURES.get("age_anchor"):
                    # ARM age_anchor (default OFF; pre-registered in
                    # tools/fa_market_feature_lab.py): anchor the offset to
                    # the SEASON of the row that supplied the age -- the
                    # proj_export / fm.enriched_signings (ba3917d)
                    # convention. The stale hist[0] anchor understated age
                    # by the season gap whenever the platform row lacked an
                    # age; training ages are already anchored, so the stale
                    # form is a train/serve skew.
                    age_row = next((h for h in hist if h.get("age")), None)
                    age = ((age_row["age"] + (class_year - age_row["season"]))
                           if age_row else int(row.get("age") or 30))
                else:
                    age_prev = next((h.get("age") for h in hist if h.get("age")), None)
                    age = ((age_prev + (class_year - hist[0]["season"])) if age_prev
                           else int(row.get("age") or 30))
                # CHAMPION paths throughout the FA pricing stack: the market
                # model's Gate-2 verdict holds under champion inputs only
                # (the ML-path version FAILED its gate - see
                # fa_market.enriched_signings). Display, rational value,
                # verdict terciles and market features stay one consistent
                # engine; /projections/ serves the gate-winning ML paths.
                path = fm.contract_war_path(hist, side, class_year, 10, age,
                                            curves, war_map, league,
                                            in_progress=(class_year - 1, frac),
                                            use_ml=False)
                if path and class_year > CLASS_YEAR:
                    # Future class: overlay the projection module's WAR path
                    # (the platform season hasn't happened; Marcel is stale).
                    pv = (proj["by_mlbam"].get(mlbam)
                          or proj["by_key"].get(row.get("player_key")))
                    if pv and _apply_proj_override(path, pv, class_year,
                                                   proj["first_season"]):
                        m["warSource"] = "mlb_projections"
                        m.pop("thinPlatform", None)
                if path:
                    s = {**row, "_war_path": path, "_age": age, "class_year": class_year}
                    pred = model.predict(s)
                    # WS-2d - option-pending members get P(enter) re-priced
                    # from the market model's own band distribution (the v1
                    # $-gap logistic stays for mutual/conditional types and
                    # as the fallback where bands are missing).
                    v2 = fm.enter_probability_v2(pred, row.get("fa_type"),
                                                 row.get("option_price_usd"))
                    if v2 is not None:
                        m["enterProb"] = v2["enter_prob"]
                        m["enterProbSrc"] = v2["method"]
                    # T1.5 - the option, priced as a contingent claim on the
                    # band rather than served as a bare flag. The SIGN is the
                    # point: a player option is a liability the team is SHORT.
                    optv = fm.option_value_usd(pred, row.get("fa_type"),
                                               row.get("option_price_usd"))
                    if optv:
                        m["optValue"] = optv["option_value_usd"]
                        m["optTeamValue"] = optv["team_value_usd"]
                        m["optKind"] = optv["kind"]
                        m["optHeldBy"] = optv["held_by"]
                        m["optBasis"] = optv["basis"]
                    yrs = pred["proj_years"]
                    guar = pred["proj_guarantee_usd"]
                    # T1.4 - the EXPECTATION of the convex tier price over the
                    # shipped band, not the tier price of the mean path.
                    rational = fm.expected_rational_value_usd(
                        path, yrs, class_year, dpw, infl=destale)
                    deal_plus = round(100 * rational / max(guar, 1))
                    # Probability buckets: floor/ceiling WAR paths (Gate-1
                    # empirical quantiles decayed along the aging curves)
                    # price to floor/ceiling rational value -> surplus range.
                    p10_path = path.get("war_by_year_p10")
                    p90_path = path.get("war_by_year_p90")
                    rational_p10 = (fm.rational_value_usd(p10_path[:yrs], class_year,
                                                          dpw, infl=destale)
                                    if p10_path else None)
                    rational_p90 = (fm.rational_value_usd(p90_path[:yrs], class_year,
                                                          dpw, infl=destale)
                                    if p90_path else None)
                    comps = fm.comps_for(s, enriched, k=3)
                    # Full 30-org fit vector: top-3 rides the member row (the
                    # board's Fits column), the rest feeds the per-team view
                    # via the compact teamFits block below.
                    all_fits = fa_fit.fit_scores(s, pred, class_year, top_n=30)
                    fits = all_fits[:3]
                    full_fits.append((m, all_fits))
                    # T1.3 - the TOTAL comes from a correlated-path Monte
                    # Carlo, not from adding the per-year quantiles. Adding
                    # quantiles is only valid under comonotonicity (a player
                    # who lands at his P10 in year 1 landing at his P10 every
                    # remaining year); the measured horizon residual Spearman
                    # is 0.4455 / 0.3594 / 0.3090 / 0.2571 at lags 1-4.
                    mc = None
                    if p10_path and p90_path and yrs >= 1:
                        try:
                            import fa_mc
                            mc = fa_mc.path_quantiles(fa_mc.simulate(
                                path["war_by_year"], p10_path, p90_path, yrs,
                                draws=fa_mc.N_DRAWS))
                        except Exception:                    # noqa: BLE001
                            log.warning("fa mc failed for %s - falling back "
                                        "to the quantile sum", row.get("player_key"))
                            mc = None
                    m.update(_clean({
                        "warY1": path["war_y1"],
                        "warPath": path["war_by_year"][:max(yrs, 5)],
                        "warPathP10": p10_path[:max(yrs, 5)] if p10_path else None,
                        "warPathP90": p90_path[:max(yrs, 5)] if p90_path else None,
                        "warTotal": round(sum(path["war_by_year"][:yrs]), 1),
                        "warTotalP10": (round(mc["p10"], 1) if mc else
                                        (round(sum(p10_path[:yrs]), 1) if p10_path else None)),
                        "warTotalP90": (round(mc["p90"], 1) if mc else
                                        (round(sum(p90_path[:yrs]), 1) if p90_path else None)),
                        # The superseded COMONOTONE total, served alongside so
                        # the Accountability surface can show both. It is not
                        # decoration: measured on 3,913 held 5-year paths the
                        # quantile sum COVERS BETTER (0.647 vs 0.386 against a
                        # nominal 0.80) despite being the invalid aggregation,
                        # because it was compensating for per-year marginals
                        # that are themselves far too narrow conditional on the
                        # player appearing (survived coverage 0.367). Both
                        # numbers are published rather than one being quietly
                        # chosen. See fa_mc for the full ledger.
                        "warTotalP10Comon": (round(sum(p10_path[:yrs]), 1)
                                             if p10_path else None),
                        "warTotalP90Comon": (round(sum(p90_path[:yrs]), 1)
                                             if p90_path else None),
                        # Functionals a quantile sum cannot express at all.
                        "warCvar10": round(mc["cvar10"], 1) if mc else None,
                        "pAnyStar": round(mc["p_any_star"], 3) if mc else None,
                        "totalSrc": "mc_copula" if mc else "quantile_sum",
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
                        # POSITION IS REQUIRED, not optional (2026-07-30). Under
                        # fa_market.VERDICT_BAND_MODE == "group" the edges are keyed by
                        # _pos_group, and _pos_group(None) returns "POS" - so omitting
                        # the position here silently banded EVERY pitcher on the board
                        # against HITTER edges (103/237 instead of SP 86/182, RP 65/146).
                        # That is worse than pooled banding, not better. The mode is a
                        # one-constant flip in fa_market but it is only correct with
                        # this argument present.
                        "verdict": fm.deal_verdict(deal_plus, row.get("position")),
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
            npv_signed, had_sched = fm.npv_guarantee_usd(
                key, class_year, sgn.get("guarantee_usd") or 0)
            m.update(_clean({
                "signedTo": sgn.get("to_team"),
                "signedYears": sgn.get("years"),
                "signedGuar": sgn.get("guarantee_usd"),
                # Deferral-adjusted actual - predictions are NPV-basis, so
                # the tracker's actual-vs-predicted delta must compare like
                # with like (only present when a schedule is on file).
                "signedGuarNpv": npv_signed if had_sched else None,
                "signedAav": sgn.get("aav_usd"),
                "signedDate": ev_date.get((key, "signing")),
                "signedMilb": True if sgn.get("mlb_deal") is False else None,
                "qoAccepted": True if sgn.get("qo_accepted") else None,
            }))
        elif (key, "option_exercised") in ev_date:
            m["status"] = "option_exercised"
        # Prospect-to-Payday arc - id-gated so a name-key collision can
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
        # The rate the module ACTUALLY carries dollars forward at. This used
        # to publish value_framework's dollars_per_war_inflation, which is 0.0
        # in production, while assets/fa.js printed "escalating 5%/yr" from its
        # own default -- the served page and the served number disagreed.
        "dpw_infl": round(destale, 4),
        "cba_carry_forward": bool(thr.get("carry_forward")),
        "n_members": len(members), "n_projected": n_proj,
        "n_signed": sum(1 for m in members if m.get("status") == "signed"),
        "members": members,
        "teamFits": team_fits,
        # First-seen winter events (newest first, capped) - the WIRE and the
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


def serve_alignment_diagnostics(class_year: int = CLASS_YEAR) -> dict:
    """Read-only evidence block for the wave-2 serve-side arms (pre-registered
    in tools/fa_market_feature_lab.py; recorded into its eval artifact by the
    lab). Writes NOTHING, never constructs a MarketModel, never calls
    predict -- safe to run alongside challenger/no-persist gate runs.

      supply -- per-pos-group class counts under the live whole-class
        convention (raw) vs the ALIGNED identity+history population
        (_class_supply_rows), each z-scored against the CHAMPION training
        supply moments (enriched signings 2015..class_year-1, the same
        counts MarketModel.__init__ fits its z-moments on).
      age -- the serve age every member would get under the stale hist[0]
        anchor vs the anchored convention. Deltas (anchored - stale) are
        structurally in [+1, +2] when nonzero: the anchored form adds the
        gap between hist[0]'s season and the age-supplying row's season,
        bounded by the 3-season history window."""
    corpus = fp.build_corpus()
    by_player: dict[str, dict[int, dict]] = {"hit": defaultdict(dict), "pit": defaultdict(dict)}
    for side in ("hit", "pit"):
        for r in corpus[side]:
            if r.get("mlbam"):
                by_player[side][r["mlbam"]][r["season"]] = r
    cls = list(storage.load_fa_class_players(class_year).values())
    enriched = fm.enriched_signings(2015, class_year - 1)
    sup_by = {y: fm._supply(enriched, y) for y in {s["class_year"] for s in enriched}}
    sup_all = [c for by in sup_by.values() for c in by.values()]
    mean = statistics.mean(sup_all) if sup_all else 0.0
    sd = statistics.pstdev(sup_all) if len(sup_all) > 1 else 1.0

    raw = fm._supply([{"class_year": class_year, "position": p.get("position")}
                      for p in cls], class_year)
    aligned = fm._supply(_class_supply_rows(cls, class_year, by_player), class_year)

    def _z(counts: dict) -> dict:
        return {g: round((counts.get(g, 0.0) - mean) / (sd or 1.0), 3)
                for g in fm.POS_GROUPS}

    z_raw, z_aligned = _z(raw), _z(aligned)
    age = {"n_members_with_hist": 0, "n_changed": 0,
           "min_delta": None, "max_delta": None, "changed": []}
    for row in cls:
        mlbam = fa_ident.resolve(row["player_name"], range(class_year - 4, class_year))
        if not mlbam:
            continue
        side = "pit" if fm._pos_group(row.get("position")) in ("SP", "RP") else "hit"
        seasons = by_player[side].get(mlbam) or {}
        hist = [seasons[t] for t in (class_year - 1, class_year - 2, class_year - 3)
                if t in seasons]
        if not hist:
            continue
        age["n_members_with_hist"] += 1
        age_row = next((h for h in hist if h.get("age")), None)
        if age_row is None:
            continue                    # both conventions fall back identically
        stale = age_row["age"] + (class_year - hist[0]["season"])
        anchored = age_row["age"] + (class_year - age_row["season"])
        if anchored != stale:
            d = anchored - stale
            age["n_changed"] += 1
            age["min_delta"] = d if age["min_delta"] is None else min(age["min_delta"], d)
            age["max_delta"] = d if age["max_delta"] is None else max(age["max_delta"], d)
            if len(age["changed"]) < 40:
                age["changed"].append({"key": row.get("player_key"),
                                       "stale": stale, "anchored": anchored})
    return {
        "class_year": class_year,
        "supply": {
            "raw": {g: raw.get(g, 0.0) for g in fm.POS_GROUPS},
            "aligned": {g: aligned.get(g, 0.0) for g in fm.POS_GROUPS},
            "z_raw": z_raw, "z_aligned": z_aligned,
            "train_mean": round(mean, 2), "train_sd": round(sd, 2),
            "mean_abs_z_raw": round(statistics.mean(abs(v) for v in z_raw.values()), 4),
            "mean_abs_z_aligned": round(statistics.mean(abs(v) for v in z_aligned.values()), 4),
        },
        "age": age,
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
                # Any REALIZED $/WAR the client computes needs the money that
                # has actually been paid and how far through the deal we are.
                # Without these, warTd (a partial) divided into guar (the whole
                # contract) reads $40M+/WAR on any recent winter - not a market
                # signal, an arithmetic error. `done` alone cannot fix it: a
                # 6-year deal in year 2 is neither complete nor comparable.
                "paidTd": led.get("paid_to_date_usd"),
                "elapsed": (round(float(led["elapsed_years"])
                                  / max(float(led.get("total_years") or s.get("years") or 1), 1.0), 3)
                            if led.get("elapsed_years") is not None else None),
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


def _source_freshness(class_year: int | None = None) -> dict:
    """Last-successful-check date per FA source - the UI's staleness stamps.

    Two granularity rules, both learned from live defects:

    - The class board is read SCOPED TO `class_year`. A global MAX read fresh
      off the 2028/2029 rows while the served 2027 board sat frozen behind a
      broken parse.
    - Signings take the later of (row MAX, recorded check). Before the winter
      opens a class has zero signing rows, so a row-only read froze on the
      previous class and tripped the UI 14-day flag every day from 2026-07-10.

    Read-only; missing tables (fresh DB) just drop out."""
    out = {}
    checks = storage.load_source_checks()
    try:
        with storage.connect() as con:
            for label, table, scoped in (("class", "fa_class_players", True),
                                         ("signings", "fa_signings", True),
                                         ("payroll", "fa_team_payroll", False),
                                         ("parks", "fa_park_factors", False)):
                if scoped and class_year is not None:
                    r = con.execute(
                        f"SELECT MAX(fetched_at) FROM {table} WHERE class_year = ?",
                        (class_year,)).fetchone()
                else:
                    r = con.execute(f"SELECT MAX(fetched_at) FROM {table}").fetchone()
                stamps = [str(r[0])[:10]] if r and r[0] else []
                chk = checks.get((f"fa_{label}", str(class_year) if class_year else ""))
                if chk and chk.get("checked_at"):
                    stamps.append(str(chk["checked_at"])[:10])
                if stamps:
                    out[label] = max(stamps)
    except Exception: # noqa: BLE001 - stamps are best-effort
        pass
    return out


def _qo_tax_block(class_year: int) -> dict:
    """{payor_tier: qo_tax_usd(...)} for the class winter. Best-effort: a
    missing or unmapped tier drops out rather than failing the export."""
    out = {}
    as_of = f"{class_year - 1}-12-15"
    try:
        tiers = sorted(fa_cba.qo_compensation(as_of)["signing_team_forfeits"])
    except Exception:                                       # noqa: BLE001
        log.warning("qo tax block: compensation matrix unavailable")
        return {}
    for tier in tiers:
        try:
            out[tier] = fm.qo_tax_usd(tier, as_of)
        except Exception:                                   # noqa: BLE001
            log.warning("qo tax block: tier %s failed - skipping", tier)
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
    # (their need craters), so the Fits view names the blockers here - 
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
            # WHERE the baseline came from: "mlb_projections" (the same
            # team_outlook the /projections/ surface serves) or
            # "contracted_core" (the documented fallback). The surface must
            # not describe an outlook win total as a contracted-core number.
            "baseSrc": w.get("baseline_source"),
            "blocked": blocked or None,
        })
    try:
        dpw_series = json.loads((DATA_DIR / "fa_dpw_series.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dpw_series = None
    return {
        "generated_at": date.today().isoformat(),
        "class_year": class_year,
        "sources": _source_freshness(class_year),
        "cba": {"threshold_usd": thr["threshold_usd"],
                "carry_forward": thr["carry_forward"],
                "regime": thr.get("regime"),
                "unverified_records": len(fa_cba.unverified_records())},
        # T1.5 - qo_tax_usd was DEAD CODE: fully implemented, tested, and
        # never called anywhere in the serve path. WIRED rather than deleted,
        # because the pick forfeiture is a real cost that changes who can
        # rationally sign a QO'd free agent and the module already prices it
        # off the platform's own realized draft-slot curve. It is served PER
        # PAYOR TIER instead of per member for a reason a reader can check:
        # the tax is a property of the SIGNING TEAM, and before a signing
        # there is no signing team. The board can apply the right tier once
        # a destination is known.
        "qo_tax_by_payor_tier": _qo_tax_block(class_year),
        "dpw_series": dpw_series,
        "gate1": _gate("fa_gate1_eval.json"),
        "gate2": _gate("fa_gate2_eval.json"),
        "park_factors": fa_fit.park_factors(class_year - 1),
        "teams": teams,
    }


# Future winters exported alongside the current class (the board's year
# selector; current stays the default). Spotrac publishes forward class
# pages, so the SAME constructed-class pipeline runs per year - future
# members are contract-expiry projections with option/QO statuses, no
# signings/events yet (the tracker goes live when their winter does).
FUTURE_CLASS_YEARS = (CLASS_YEAR + 1, CLASS_YEAR + 2)


def export_all() -> dict[str, int]:
    sizes = {}
    exports = [("fa_class.json", build_fa_class_payload()),
               ("fa_archive.json", build_fa_archive_payload()),
               ("fa_meta.json", build_fa_meta_payload())]
    for y in FUTURE_CLASS_YEARS:
        try:
            exports.append((f"fa_class_{y}.json", build_fa_class_payload(y)))
        except Exception:                                     # noqa: BLE001
            log.exception("future class %d export failed - continuing", y)
    for name, payload in exports:
        raw = json.dumps(payload, separators=(",", ":"))
        (DATA_DIR / name).write_text(raw, encoding="utf-8")
        sizes[name] = len(raw)
    log.info("fa exports: %s", {k: f"{v/1024:.0f}KB" for k, v in sizes.items()})
    return sizes


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(export_all())
