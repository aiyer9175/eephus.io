# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Projection engine for the MLB Free Agency module (Stage 2).

Architecture (per the approved plan): COMPONENTS FIRST, COMPOSITES SECOND.
Component rates (K%, BB%, ISO, BABIP, HR rate for hitters; K%, BB%, HR/BF
for pitchers) are Marcel-weighted (5/4/3), regressed to the league mean
with component-specific stabilization points, and aged with delta-method
curves fitted from the corpus (survivorship-corrected, era-adjusted, by
role group). Composites are assembled from components: wOBA -> wRC+
(park-neutral, fixed linear weights — documented), FIP (per-season
constant), and WAR via a transparent linear map FITTED ON THE TRAINING
CORPUS ONLY (coefficients published in the eval artifact). Playing time
is its own model (classic Marcel PT + the fitted PT aging delta).

WAR is bWAR (war_daily) — one WAR source site-wide; the projection's WAR
map is calibrated against it, so "projected WAR" means projected bWAR.

v1 simplifications (documented, gate-checked): defense/baserunning are not
separately projected — the fitted WAR map + the uncertainty bands absorb
them; bands are parametric (P50 ± z·sigma with sigma fitted per reliability
bucket on TRAIN years); two-way players project on their primary role.

Corpus: MLB StatsAPI league-wide season stats (playerPool=All, 2000->now)
joined to B-Ref war_daily for age + per-season bWAR by MLBAM id. Cached at
.cache/fa_corpus.pkl; aging curves are a committed artifact
(data/fa_aging_curves.json) with fit metadata, mirroring the
value_framework_fitted.json pattern.
"""

from __future__ import annotations

import json
import logging
import math
import pickle
from collections import defaultdict
from pathlib import Path

import fa_class
import fa_sources

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache"
CORPUS_CACHE = CACHE_DIR / "fa_corpus.pkl"
CURVES_PATH = Path(__file__).parent / "data" / "fa_aging_curves.json"

HIT_COMPONENTS = ("k_pct", "bb_pct", "iso", "babip", "hr_pa")
PIT_COMPONENTS = ("k_pct", "bb_pct", "hr_bf")
# Direction of HARM for the survivorship correction: dropouts were headed
# the bad way; +1 means "higher is worse" for the player.
HARM_DIR = {"hit": {"k_pct": +1, "bb_pct": -1, "iso": -1, "babip": -1, "hr_pa": -1,
                    "war_rate": -1, "pt": -1},
            "pit": {"k_pct": -1, "bb_pct": +1, "hr_bf": +1, "war_rate": -1, "pt": -1}}


def _pcfg() -> dict:
    return fa_class.get_config()["projection"]


# ============================================================================
# Corpus construction
# ============================================================================

def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _ip_to_float(raw) -> float:
    """'190.1' style innings → 190.333."""
    s = str(raw or "0")
    if "." in s:
        whole, frac = s.split(".", 1)
        return _f(whole) + {"0": 0.0, "1": 1 / 3, "2": 2 / 3}.get(frac[:1], 0.0)
    return _f(s)


def _war_age_maps() -> tuple[dict, dict]:
    """{(mlbam, season): war} (bat+pit summed) and {(mlbam, season): age}
    from the war_daily tables — the corpus's WAR + age source."""
    import pybaseball as pyb
    war: dict[tuple[int, int], float] = {}
    age: dict[tuple[int, int], int] = {}
    for fn, label in ((pyb.bwar_bat, "bwar_bat"), (pyb.bwar_pitch, "bwar_pitch")):
        try:
            df = fn(return_all=True)
        except Exception as e:                                # noqa: BLE001
            log.warning("%s unavailable: %s", label, e)
            continue
        sub = df[df["mlb_ID"].notna() & df["WAR"].notna()]
        for row in sub.itertuples(index=False):
            try:
                key = (int(row.mlb_ID), int(row.year_ID))
            except (TypeError, ValueError):
                continue
            war[key] = war.get(key, 0.0) + _f(row.WAR)
            try:
                age[key] = int(row.age)
            except (TypeError, ValueError):
                pass
    return war, age


def build_corpus(first_season: int | None = None, last_season: int | None = None,
                 force: bool = False) -> dict:
    """{"hit": [rows], "pit": [rows], "league": {season: {...}}}.

    Hitter row: mlbam, season, age, role(C|H), pa, k_pct, bb_pct, iso,
    babip, hr_pa, woba, war. Pitcher row: mlbam, season, age, role(SP|RP),
    bf, ip, k_pct, bb_pct, hr_bf, fip, war. League context per season
    carries the means + FIP constant the assembly/regression anchors use.
    """
    from datetime import date
    cfg = _pcfg()
    first = first_season or int(cfg["corpus_first_season"])
    last = last_season or date.today().year
    if CORPUS_CACHE.exists() and not force:
        with open(CORPUS_CACHE, "rb") as fh:
            cached = pickle.load(fh)
        if cached.get("first") == first and cached.get("last") >= last - 0:
            return cached
    war_map, age_map = _war_age_maps()
    raw = fa_sources.fetch_statsapi_season_range(first, last)
    hit_rows: list[dict] = []
    pit_rows: list[dict] = []
    league: dict[int, dict] = {}
    for season in range(first, last + 1):
        lg = {"season": season}
        # ---- hitters --------------------------------------------------------
        tot = {k: 0.0 for k in ("pa", "ab", "h", "d", "t", "hr", "bb", "so", "hbp", "sf", "r")}
        for s in raw.get((season, "hitting"), []):
            st = s.get("stat") or {}
            pa = _f(st.get("plateAppearances"))
            if pa <= 0:
                continue
            mlbam = (s.get("player") or {}).get("id")
            ab, h = _f(st.get("atBats")), _f(st.get("hits"))
            d, t, hr = _f(st.get("doubles")), _f(st.get("triples")), _f(st.get("homeRuns"))
            bb, so = _f(st.get("baseOnBalls")), _f(st.get("strikeOuts"))
            hbp, sf = _f(st.get("hitByPitch")), _f(st.get("sacFlies"))
            for k, v in (("pa", pa), ("ab", ab), ("h", h), ("d", d), ("t", t), ("hr", hr),
                         ("bb", bb), ("so", so), ("hbp", hbp), ("sf", sf), ("r", _f(st.get("runs")))):
                tot[k] += v
            pos = ((s.get("position") or {}).get("abbreviation") or "").upper()
            if pos == "P":
                continue                       # pitchers batting: exclude from hitter corpus
            babip_den = ab - so - hr + sf
            key = (int(mlbam), season) if mlbam else None
            hit_rows.append({
                "mlbam": mlbam, "season": season,
                "age": age_map.get(key), "role": "C" if pos == "C" else "H",
                "pa": pa,
                "k_pct": so / pa, "bb_pct": bb / pa,
                "iso": ((d + 2 * t + 3 * hr) / ab) if ab > 0 else 0.0,
                "babip": ((h - hr) / babip_den) if babip_den > 0 else None,
                "hr_pa": hr / pa,
                "war": war_map.get(key),
            })
        if tot["pa"] > 0:
            w = _pcfg()["assembly"]["woba_weights"]
            singles = tot["h"] - tot["d"] - tot["t"] - tot["hr"]
            lg_woba_num = (w["bb"] * tot["bb"] + w["hbp"] * tot["hbp"] + w["single"] * singles
                           + w["double"] * tot["d"] + w["triple"] * tot["t"] + w["hr"] * tot["hr"])
            lg.update({
                "_total_pa": tot["pa"],
                "woba": lg_woba_num / tot["pa"],
                "r_pa": tot["r"] / tot["pa"],
                "k_pct": tot["so"] / tot["pa"], "bb_pct": tot["bb"] / tot["pa"],
                "iso": (tot["d"] + 2 * tot["t"] + 3 * tot["hr"]) / tot["ab"],
                "babip": (tot["h"] - tot["hr"]) / (tot["ab"] - tot["so"] - tot["hr"] + tot["sf"]),
                "hr_pa": tot["hr"] / tot["pa"],
            })
        # ---- pitchers -------------------------------------------------------
        ptot = {k: 0.0 for k in ("bf", "ip", "so", "bb", "hbp", "hr", "er")}
        season_pit: list[dict] = []
        for s in raw.get((season, "pitching"), []):
            st = s.get("stat") or {}
            bf = _f(st.get("battersFaced"))
            ip = _ip_to_float(st.get("inningsPitched"))
            if bf <= 0 or ip <= 0:
                continue
            mlbam = (s.get("player") or {}).get("id")
            so, bb = _f(st.get("strikeOuts")), _f(st.get("baseOnBalls"))
            hbp, hr = _f(st.get("hitByPitch")), _f(st.get("homeRuns"))
            gs, g = _f(st.get("gamesStarted")), max(_f(st.get("gamesPlayed")), 1.0)
            for k, v in (("bf", bf), ("ip", ip), ("so", so), ("bb", bb),
                         ("hbp", hbp), ("hr", hr), ("er", _f(st.get("earnedRuns")))):
                ptot[k] += v
            key = (int(mlbam), season) if mlbam else None
            season_pit.append({
                "mlbam": mlbam, "season": season,
                "age": age_map.get(key),
                "role": "SP" if (gs / g) >= 0.5 else "RP",
                "bf": bf, "ip": ip,
                "k_pct": so / bf, "bb_pct": bb / bf, "hr_bf": hr / bf,
                "_fip_core": (13 * hr + 3 * (bb + hbp) - 2 * so) / ip,
                "war": war_map.get(key),
            })
        if ptot["ip"] > 0:
            lg_era = 9 * ptot["er"] / ptot["ip"]
            fip_const = lg_era - (13 * ptot["hr"] + 3 * (ptot["bb"] + ptot["hbp"]) - 2 * ptot["so"]) / ptot["ip"]
            lg.update({"fip_constant": fip_const, "era": lg_era,
                       "p_k_pct": ptot["so"] / ptot["bf"], "p_bb_pct": ptot["bb"] / ptot["bf"],
                       "p_hr_bf": ptot["hr"] / ptot["bf"],
                       "lg_fip": fip_const + (13 * ptot["hr"] + 3 * (ptot["bb"] + ptot["hbp"]) - 2 * ptot["so"]) / ptot["ip"]})
            for r in season_pit:
                r["fip"] = r.pop("_fip_core") + fip_const
        league[season] = lg
        pit_rows.extend(season_pit)
    corpus = {"hit": hit_rows, "pit": pit_rows, "league": league,
              "first": first, "last": last}
    CACHE_DIR.mkdir(exist_ok=True)
    with open(CORPUS_CACHE, "wb") as fh:
        pickle.dump(corpus, fh)
    log.info("fa corpus: %d hitter-seasons, %d pitcher-seasons, %d league-years",
             len(hit_rows), len(pit_rows), len(league))
    return corpus


# ============================================================================
# Aging curves — delta method, era-adjusted, survivorship-corrected
# ============================================================================

def _era_adjust(rows: list[dict], league: dict, comp: str, side: str) -> dict:
    """{(mlbam, season): rate − league_year_mean} for one component."""
    lg_key = {"hit": comp, "pit": {"k_pct": "p_k_pct", "bb_pct": "p_bb_pct",
                                   "hr_bf": "p_hr_bf"}[comp]}[side]
    out = {}
    for r in rows:
        v = r.get(comp)
        lg = (league.get(r["season"]) or {}).get(lg_key)
        if v is None or lg is None or r.get("mlbam") is None:
            continue
        out[(r["mlbam"], r["season"])] = v - lg
    return out


def fitted_models(corpus: dict, max_season: int, use_cache: bool = True) -> tuple[dict, dict]:
    """(curves, war_map) fitted on seasons <= max_season, disk-cached per
    max_season — Gate 2 and the live market model reuse Gate 1's twelve
    point-in-time fits instead of recomputing them (load-time ask)."""
    cache = CACHE_DIR / f"fa_fits_{max_season}_{corpus['first']}.pkl"
    if use_cache and cache.exists():
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    curves = fit_aging_curves(corpus, max_season=max_season, write=False)
    war_map = fit_war_map(corpus, max_season=max_season)
    CACHE_DIR.mkdir(exist_ok=True)
    with open(cache, "wb") as fh:
        pickle.dump((curves, war_map), fh)
    return curves, war_map


def fit_aging_curves(corpus: dict | None = None, max_season: int | None = None,
                     write: bool = True) -> dict:
    """Delta-method aging curves per (side, role-group, component) +
    playing-time and WAR-rate curves. ``max_season`` caps the pairs used —
    THE NO-LOOKAHEAD HOOK: the gate refits curves per train window.

    Survivorship correction (documented v1): the raw delta only sees
    players who PLAYED season t+1; dropouts were headed the bad way. At
    each age we measure attrition (share of the age-t pool with no t+1
    exposure) and the survivors' selection gap (how much better the
    survivors already were at t, era-adjusted), and push the delta in the
    harm direction by lambda x attrition x |selection gap|.
    """
    cfg = _pcfg()
    corpus = corpus or build_corpus()
    lam = float(cfg["survivorship_lambda"])
    a_lo, a_hi = cfg["age_range"]
    min_pa = cfg["min_exposure_pair"]["pa"]
    min_bf = cfg["min_exposure_pair"]["bf"]
    reg_k = cfg.get("war_rate_regression") or {"hit_pa": 600, "pit_bf": 350}
    curves: dict = {"hit": {}, "pit": {}, "meta": {
        "method": "delta_pa_weighted+survivorship+regressed_rate_v2",
        "lambda": lam, "max_season": max_season,
        "corpus_seasons": [corpus["first"], corpus["last"]],
    }}
    for side, rows, comps, expo_key, min_expo, role_of in (
        ("hit", corpus["hit"], HIT_COMPONENTS + ("war_rate", "pt"), "pa", min_pa,
         lambda r: "C" if r["role"] == "C" else "H"),
        ("pit", corpus["pit"], PIT_COMPONENTS + ("war_rate", "pt"), "bf", min_bf,
         lambda r: r["role"]),
    ):
        rows = [r for r in rows if r.get("age") and a_lo <= r["age"] <= a_hi
                and (max_season is None or r["season"] + 1 <= max_season)]
        by_player: dict[int, dict[int, dict]] = {}
        for r in rows:
            if r.get("mlbam") is not None:
                by_player.setdefault(r["mlbam"], {})[r["season"]] = r
        # League WAR rate per exposure unit per season — the shrink target
        # for the regressed-rate aging (v2).
        per = 600.0 if side == "hit" else 250.0
        k_reg = float(reg_k["hit_pa"] if side == "hit" else reg_k["pit_bf"])
        lg_rate: dict[int, float] = {}
        acc_w: dict[int, float] = defaultdict(float)
        acc_e: dict[int, float] = defaultdict(float)
        for r in rows:
            if r.get("war") is not None and (r.get(expo_key) or 0) > 0:
                acc_w[r["season"]] += r["war"]
                acc_e[r["season"]] += r[expo_key]
        for s, e in acc_e.items():
            if e > 0:
                lg_rate[s] = acc_w[s] / e * per

        # value getter per pseudo-component. war_rate is REGRESSED toward
        # the season league rate at the configured stabilization exposure:
        # raw observed deltas bundle aging with luck regression, and the
        # projection being decayed is already a regressed quantity —
        # chaining raw deltas double-counts the regression (the measured
        # horizon-5 tail collapse).
        def _val(r: dict, comp: str):
            if comp == "war_rate":
                w = r.get("war")
                e = r.get(expo_key) or 0
                if w is None or e < min_expo:
                    return None
                raw = w / e * per
                lg = lg_rate.get(r["season"], 0.0)
                return (raw * e + lg * k_reg) / (e + k_reg)
            if comp == "pt":
                return r.get(expo_key)
            return r.get(comp)
        roles = (("C", "H", "H|pwr", "H|con") if side == "hit"
                 else ("SP", "RP", "SP|pwr", "SP|fin", "RP|pwr", "RP|fin"))
        for role in roles:
            curves[side].setdefault(role, {})
            for comp in comps:
                # Profile cohorts exist for the aging asks only (war_rate,
                # pt) — fragmenting component curves shreds their samples.
                if "|" in role and comp not in ("war_rate", "pt"):
                    continue
                acc: dict[int, dict] = {}
                for mlbam, seasons in by_player.items():
                    for s, r in seasons.items():
                        if (r.get(expo_key) or 0) < min_expo:
                            continue
                        base = role_of(r)
                        if "|" in role:
                            prof = _row_profile(r, side, corpus["league"])
                            if f"{base}|{prof}" != role:
                                continue
                        elif base != role:
                            continue
                        v0 = _val(r, comp)
                        if v0 is None:
                            continue
                        a = r["age"] + 1                       # delta lands at age t+1
                        slot = acc.setdefault(a, {"d": 0.0, "w": 0.0, "pool": [],
                                                  "stay": [], "n_pool": 0, "n_stay": 0})
                        slot["pool"].append(v0)
                        slot["n_pool"] += 1
                        nxt = seasons.get(s + 1)
                        if not nxt or (nxt.get(expo_key) or 0) < min_expo:
                            continue
                        v1 = _val(nxt, comp)
                        if v1 is None:
                            continue
                        w = 2.0 / (1.0 / r[expo_key] + 1.0 / nxt[expo_key])  # harmonic
                        slot["d"] += (v1 - v0) * w
                        slot["w"] += w
                        slot["stay"].append(v0)
                        slot["n_stay"] += 1
                curve = {}
                for a, slot in sorted(acc.items()):
                    if slot["w"] <= 0 or slot["n_pool"] < 12:
                        continue
                    raw_delta = slot["d"] / slot["w"]
                    attrition = 1.0 - slot["n_stay"] / slot["n_pool"]
                    sel_gap = ((sum(slot["stay"]) / len(slot["stay"])) -
                               (sum(slot["pool"]) / len(slot["pool"]))) if slot["stay"] else 0.0
                    harm = HARM_DIR[side].get(comp, -1)
                    corrected = raw_delta + harm * lam * attrition * abs(sel_gap)
                    curve[str(a)] = {"delta": round(corrected, 5),
                                     "raw": round(raw_delta, 5),
                                     "n": slot["n_stay"], "attrition": round(attrition, 3)}
                # 3-age smoothing on the corrected deltas
                ages = sorted(int(a) for a in curve)
                smoothed = {}
                for a in ages:
                    vals = [curve[str(x)]["delta"] for x in (a - 1, a, a + 1) if str(x) in curve]
                    smoothed[str(a)] = round(sum(vals) / len(vals), 5)
                for a in ages:
                    curve[str(a)]["delta_smooth"] = smoothed[str(a)]
                curves[side][role][comp] = curve
    if write and max_season is None:
        CURVES_PATH.write_text(json.dumps(curves, indent=1), encoding="utf-8")
        log.info("fa aging curves written -> %s", CURVES_PATH)
    return curves


def _row_profile(r: dict, side: str, league: dict) -> str:
    """Season profile cohort for the aging curves: power vs contact hitters
    (ISO relative to league), power vs finesse pitchers (K% relative to
    league). Middle of the distribution returns '' (base cohort)."""
    th = _pcfg().get("profile_cohorts") or {}
    lg = league.get(r["season"]) or {}
    if side == "hit":
        lg_iso = lg.get("iso")
        if not lg_iso or r.get("iso") is None:
            return ""
        rel = r["iso"] / lg_iso
        if rel >= float(th.get("iso_hi", 1.2)):
            return "pwr"
        if rel <= float(th.get("iso_lo", 0.8)):
            return "con"
        return ""
    lg_k = lg.get("p_k_pct")
    if not lg_k or r.get("k_pct") is None:
        return ""
    rel = r["k_pct"] / lg_k
    if rel >= float(th.get("k_hi", 1.15)):
        return "pwr"
    if rel <= float(th.get("k_lo", 0.85)):
        return "fin"
    return ""


def profile_role(hist: list[dict], side: str, role: str, league: dict) -> str:
    """Extended aging-curve role for a player: base role plus his
    exposure-weighted profile cohort across the history rows. Consumers
    pass this to curve_delta for war_rate/pt — the lookup falls back to
    the base role wherever a cohort cell is thin."""
    expo_key = "pa" if side == "hit" else "bf"
    votes: dict[str, float] = defaultdict(float)
    for r in hist:
        p = _row_profile(r, side, league)
        votes[p] += r.get(expo_key) or 0
    if not votes:
        return role
    best = max(votes, key=votes.get)
    return f"{role}|{best}" if best else role


def curve_delta(curves: dict, side: str, role: str, comp: str, age: int) -> float:
    """Smoothed delta applied moving INTO ``age``; clamps to curve support.
    Profile-extended roles ('H|pwr', 'SP|fin') fall back to the base role
    when the cohort has no curve for the component."""
    c = ((curves.get(side) or {}).get(role) or {}).get(comp) or {}
    if not c and "|" in role:
        c = ((curves.get(side) or {}).get(role.split("|")[0]) or {}).get(comp) or {}
    if not c:
        return 0.0
    ages = sorted(int(a) for a in c)
    # NEAREST supported age, not endpoint clamping — thin cohort curves
    # can have holes mid-sequence (cells under the n_pool floor).
    a = min(ages, key=lambda x: abs(x - age))
    return c[str(a)].get("delta_smooth", c[str(a)]["delta"])


# ============================================================================
# Marcel projection
# ============================================================================

_XSTATS_CACHE = CACHE_DIR / "xstats.pkl"
_xstats_mem: dict | None = None


def _xstats() -> dict[tuple[int, int], float]:
    """{(mlbam, season): xISO} from Savant expected stats (2015+), disk-
    cached. Empty dict when the fetch fails — the blend simply no-ops."""
    global _xstats_mem
    if _xstats_mem is not None:
        return _xstats_mem
    cfg = _pcfg().get("statcast_blend") or {}
    first = int(cfg.get("first_season", 2015))
    from datetime import date as _date
    last = _date.today().year
    if _XSTATS_CACHE.exists():
        with open(_XSTATS_CACHE, "rb") as fh:
            cached = pickle.load(fh)
        if cached.get("last", 0) >= last - 1:
            _xstats_mem = cached["data"]
            return _xstats_mem
    data: dict[tuple[int, int], float] = {}
    try:
        import pybaseball as pyb
        for season in range(first, last + 1):
            try:
                df = pyb.statcast_batter_expected_stats(season,
                                                        minPA=int(cfg.get("min_pa", 50)))
            except Exception:                              # noqa: BLE001 — season gaps OK
                continue
            for row in df.itertuples(index=False):
                try:
                    data[(int(row.player_id), int(row.year))] = \
                        float(row.est_slg) - float(row.est_ba)
                except (TypeError, ValueError):
                    continue
    except Exception as e:                                 # noqa: BLE001
        log.warning("xstats unavailable (%s) — statcast blend no-ops", e)
    CACHE_DIR.mkdir(exist_ok=True)
    with open(_XSTATS_CACHE, "wb") as fh:
        pickle.dump({"last": last, "data": data}, fh)
    _xstats_mem = data
    return data


def _blend_iso(h: dict, v: float) -> float:
    """Blend a history season's observed ISO toward its Savant xISO —
    contact-quality information the raw line doesn't carry. Same-vintage
    information (no lookahead); seasons without expected stats pass
    through untouched."""
    cfg = _pcfg().get("statcast_blend") or {}
    if not cfg.get("enabled") or not h.get("mlbam"):
        return v
    x = _xstats().get((h["mlbam"], h["season"]))
    if x is None:
        return v
    a = float(cfg.get("alpha", 0.4))
    return (1 - a) * v + a * x


def _league_recent(league: dict, season: int, key: str):
    for s in (season - 1, season - 2, season - 3):
        v = (league.get(s) or {}).get(key)
        if v is not None:
            return v
    return None


def season_fraction(league: dict, season: int) -> float:
    """Elapsed fraction of an IN-PROGRESS season, estimated from the
    league's accumulated PA vs the prior full season. Clamped [0.05, 1]."""
    cur = (league.get(season) or {}).get("_total_pa")
    prev = (league.get(season - 1) or {}).get("_total_pa")
    if not cur or not prev:
        return 1.0
    return max(0.05, min(1.0, cur / prev))


def project_player(history: list[dict], side: str, target_season: int,
                   curves: dict, league: dict, age: int | None,
                   role: str | None = None,
                   in_progress: tuple[int, float] | None = None) -> dict | None:
    """Project one player's ``target_season`` from up to three prior
    seasons (the rows must be corpus-shaped). Returns the component dict +
    assembled composites (wRC+/FIP) + playing time — WAR attaches later
    via the fitted map. None when no usable history exists."""
    cfg = _pcfg()
    weights = cfg["marcel_weights"]
    expo_key = "pa" if side == "hit" else "bf"
    hist = sorted([h for h in history if 0 < target_season - h["season"] <= 3],
                  key=lambda h: -h["season"])
    if not hist:
        return None
    role = role or hist[0]["role"]
    comps = HIT_COMPONENTS if side == "hit" else PIT_COMPONENTS
    kmap = cfg["regression_k"]["hit" if side == "hit" else "pit"]
    lg_key = (lambda c: c) if side == "hit" else \
             (lambda c: {"k_pct": "p_k_pct", "bb_pct": "p_bb_pct", "hr_bf": "p_hr_bf"}[c])
    out: dict = {"role": role, "age": age, "season": target_season}
    for comp in comps:
        num = den = 0.0
        for h in hist:
            v = h.get(comp)
            if v is None:
                continue
            if comp == "iso" and side == "hit":
                v = _blend_iso(h, v)
            w = weights[target_season - h["season"] - 1] * (h.get(expo_key) or 0)
            num += w * v
            den += w
        lg = _league_recent(league, target_season, lg_key(comp))
        if lg is None:
            return None
        k = float(kmap.get(comp, 200)) * weights[0]            # prior in weighted-exposure units
        rate = (num + k * lg) / (den + k) if (den + k) > 0 else lg
        if age:
            rate += curve_delta(curves, side, role, comp, age)
        out[comp] = max(0.0, rate)
    # ---- playing time (its own model: classic Marcel PT + PT aging) ---------
    # In-progress season handling (LIVE path only; the gates always project
    # from completed seasons): a June rebuild sees ~40% of the current season.
    # Naively pro-rating the partial season to a full-season equivalent (e/frac)
    # bakes in whatever PT the player has accrued so far - which UNDER-projects
    # a durable regular who's been hurt for part of the current season: a 700-PA
    # everyday SS sitting at 105 PA in a 41%-elapsed season would pro-rate to
    # ~255 PA and project as a part-timer (the Lindor case). Instead,
    # RELIABILITY-BLEND the in-progress exposure toward the player's ESTABLISHED
    # level (most recent completed season), weighted by elapsed fraction:
    #   frac*(e/frac) + (1-frac)*established  ==  e + (1-frac)*established
    # Early in the year the track record dominates; by season's end the current
    # season takes over (frac -> 1). A healthy regular whose current pace
    # matches their established PT is ~unchanged; only limited/injured veterans
    # with a strong track record lift. (Rate reliability is untouched - the rate
    # Marcel already exposure-weights the partial sample down.) Trade-off: a
    # player limited because they LOST the job, not injury, is lifted too -
    # accepted as the lesser error for a star-heavy surface.
    def _established_expo(key: str) -> float:
        for h in hist:  # sorted most-recent-first; first completed season
            if not (in_progress and h["season"] == in_progress[0]):
                return h.get(key) or 0
        return 0.0
    def _pt_expo(h: dict, key: str) -> float:
        e = h.get(key) or 0
        if in_progress and h["season"] == in_progress[0] and in_progress[1] > 0:
            return e + (1.0 - in_progress[1]) * _established_expo(key)
        return e
    pt_cfg = cfg["playing_time"]["hit" if side == "hit" else "pit"]
    e1 = next((_pt_expo(h, expo_key) for h in hist if h["season"] == target_season - 1), 0)
    e2 = next((_pt_expo(h, expo_key) for h in hist if h["season"] == target_season - 2), 0)
    if side == "hit":
        pt = pt_cfg["w1"] * e1 + pt_cfg["w2"] * e2 + pt_cfg["base_pa"]
    else:
        base_ip = pt_cfg["base_ip_sp"] if role == "SP" else pt_cfg["base_ip_rp"]
        ip1 = next((_pt_expo(h, "ip") for h in hist if h["season"] == target_season - 1), 0)
        ip2 = next((_pt_expo(h, "ip") for h in hist if h["season"] == target_season - 2), 0)
        ip = pt_cfg["w1"] * ip1 + pt_cfg["w2"] * ip2 + base_ip
        pt = ip * 4.3                                          # BF ≈ 4.3 / IP
        out["ip_proj"] = round(ip, 1)
    if age:
        pt += curve_delta(curves, side, role, "pt", age)
    out["pt_proj"] = max(0.0, round(pt, 1))
    # ---- composites ----------------------------------------------------------
    if side == "hit":
        out.update(_assemble_hitter(out, league, target_season))
    else:
        fipc = _league_recent(league, target_season, "fip_constant") or 3.1
        out["fip_proj"] = round(
            (13 * out["hr_bf"] * out["pt_proj"]
             + 3 * (out["bb_pct"] * out["pt_proj"] + 0.008 * out["pt_proj"])
             - 2 * out["k_pct"] * out["pt_proj"]) / max(out.get("ip_proj", 1), 1) + fipc, 2)
    return out


def _assemble_hitter(p: dict, league: dict, season: int) -> dict:
    """Components → slash → wOBA → park-neutral wRC+ (documented algebra:
    fixed HBP/SF rates + a fixed 2B:3B split invert ISO into hit types)."""
    a = _pcfg()["assembly"]
    pa = 1.0
    bb = p["bb_pct"]; hbp = a["hbp_rate"]; sf = a["sf_rate"]
    ab = pa - bb - hbp - sf
    so = p["k_pct"]                                            # per PA
    hr = p["hr_pa"]
    bip = ab - so - hr + sf
    hits_in_play = max(0.0, (p["babip"] or 0.28) * bip)
    h = hits_in_play + hr
    eb_nonhr = max(0.0, p["iso"] * ab - 3 * hr)                # 2B + 2·3B
    r = a["double_triple_ratio"]
    triples = eb_nonhr / (r + 2)
    doubles = r * triples
    singles = max(0.0, h - hr - doubles - triples)
    w = a["woba_weights"]
    woba = (w["bb"] * bb + w["hbp"] * hbp + w["single"] * singles
            + w["double"] * doubles + w["triple"] * triples + w["hr"] * hr) / pa
    lg_woba = _league_recent(league, season, "woba") or 0.315
    lg_rpa = _league_recent(league, season, "r_pa") or 0.12
    wraa_pa = (woba - lg_woba) / a["woba_scale"]
    wrc_plus = ((wraa_pa + lg_rpa) / lg_rpa) * 100 if lg_rpa else None
    return {"avg": round(h / ab, 3) if ab > 0 else None,
            "woba_proj": round(woba, 3),
            "wrc_plus_proj": round(wrc_plus, 1) if wrc_plus is not None else None,
            "wraa_pa": wraa_pa}


# ============================================================================
# WAR map — transparent OLS on the TRAIN corpus (coefficients published)
# ============================================================================

def fit_war_map(corpus: dict, max_season: int) -> dict:
    """Least-squares WAR maps per side, fitted on seasons <= max_season:
      hitters:  WAR ~ b0 + b1·(PA/600) + b2·(wRAA_proxy·PA/600) + b3·C·(PA/600)
      pitchers: WAR ~ b0 + b1·(IP/100) + b2·((lgFIP−FIP)·IP/100) + b3·SP·(IP/100)
    The wRAA proxy is era-adjusted wOBA distance — defense/BsR live in the
    residual (documented v1)."""
    import numpy as np
    league = corpus["league"]
    out: dict = {}
    # hitters
    X, y = [], []
    a = _pcfg()["assembly"]
    for r in corpus["hit"]:
        if r["season"] > max_season or r.get("war") is None or (r.get("pa") or 0) < 50:
            continue
        lg = league.get(r["season"]) or {}
        if not lg.get("woba"):
            continue
        woba = _assemble_hitter({**r, "babip": r.get("babip") or lg.get("babip")},
                                league, r["season"] + 1)["woba_proj"]
        wraa_pa = (woba - lg["woba"]) / a["woba_scale"]
        pa6 = r["pa"] / 600.0
        X.append([1.0, pa6, wraa_pa * pa6 * 600.0 / 10.0, (1.0 if r["role"] == "C" else 0.0) * pa6])
        y.append(r["war"])
    bh, *_ = np.linalg.lstsq(np.asarray(X), np.asarray(y), rcond=None)
    out["hit"] = {"coef": [round(c, 4) for c in bh.tolist()],
                  "features": ["1", "PA/600", "wRAA/10", "C×PA/600"], "n": len(y)}
    # pitchers
    X, y = [], []
    for r in corpus["pit"]:
        if r["season"] > max_season or r.get("war") is None or (r.get("ip") or 0) < 20:
            continue
        lg = league.get(r["season"]) or {}
        if not lg.get("lg_fip"):
            continue
        ip100 = r["ip"] / 100.0
        X.append([1.0, ip100, (lg["lg_fip"] - r["fip"]) * ip100, (1.0 if r["role"] == "SP" else 0.0) * ip100])
        y.append(r["war"])
    bp, *_ = np.linalg.lstsq(np.asarray(X), np.asarray(y), rcond=None)
    out["pit"] = {"coef": [round(c, 4) for c in bp.tolist()],
                  "features": ["1", "IP/100", "(lgFIP−FIP)×IP/100", "SP×IP/100"], "n": len(y)}
    return out


def war_from_projection(proj: dict, side: str, war_map: dict, league: dict,
                        target_season: int) -> float:
    if side == "hit":
        c = war_map["hit"]["coef"]
        pa6 = proj["pt_proj"] / 600.0
        wraa10 = proj["wraa_pa"] * proj["pt_proj"] / 10.0
        return c[0] + c[1] * pa6 + c[2] * wraa10 + c[3] * (1.0 if proj["role"] == "C" else 0.0) * pa6
    c = war_map["pit"]["coef"]
    lg_fip = _league_recent(league, target_season, "lg_fip") or 4.1
    ip100 = proj.get("ip_proj", 0.0) / 100.0
    return (c[0] + c[1] * ip100 + c[2] * (lg_fip - proj["fip_proj"]) * ip100
            + c[3] * (1.0 if proj["role"] == "SP" else 0.0) * ip100)
