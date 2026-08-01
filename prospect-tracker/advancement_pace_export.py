# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
#
# ============================================================================
# DESCRIPTIVE DISPLAY ONLY. model_eligible = False. NEVER A MODEL INPUT.
#
# Advancement Pace+ (AP+) describes how quickly a hitter has moved through
# the affiliated minor-league ladder relative to comparable peers. It is a
# rebuild of Will Cahoon's advancement_pace method (the vendored module at
# ../advancement_pace is the method spec) from the platform's own
# .cache/milb_stats season files, sanctioned for DISPLAY by that module's
# permitted-consumer list and FORBIDDEN by its own contract from any
# predictive or valuation use.
#
# This module must NEVER import from (and must never be imported by)
# efv_* / proj_* / fa_* / valuation / trade-value code. Forbidden consumers
# (verbatim from the source provenance contract): Career Outcome+, p_reach,
# xWAR, xFV, eFV, eWAR, eoWAR, readiness, opportunity, career-state routing,
# any predictive or valuation head. Its outputs are a prospx card panel and
# a glossary entry. Nothing else.
#
# ---------------------------------------------------------------------------
# AMENDMENT 2026-07-31 (owner decision, recorded here because a contract that
# changes silently is not a contract).
#
# SCOPE CLARIFIED, NOT WIDENED. The bar is on PREDICTIVE and VALUATION use, and
# it stands unchanged: AP+ may not enter a model that produces a grade, a WAR
# projection, an outcome probability or a dollar figure. That includes eFV.
#
# What the amendment permits: AP+ may be read by DISPLAY and EDITORIAL surfaces
# outside this module's own card - a chip, a tooltip, a sort key, a filter, a
# narration decision - provided the number itself is not an input to any fitted
# or priced quantity. Rationale: the owner asked why a DSL climber's card says
# "slow", and AP+ is the platform's own answer to exactly that question. Keeping
# it locked in one panel meant the site contradicted itself in public.
#
# What is STILL FORBIDDEN, and why it is not merely policy:
#   * Any efv_* / proj_* / fa_* / valuation import, in either direction.
#   * Joining the SERVED artifact to training rows. data/advancement_pace.json
#     is latest-as-of, so every historical row would carry a post-decision
#     value. That is a leak, not a contract question.
#   * Hitters-only remains a hard limit; there is no pitcher panel.
#
# The eFV-side answer to the same question is a SEPARATE, eFV-native column
# computed from the same StatsAPI substrate with no AP+ import and no as-of
# violation: efv_dataset._pace_from_entry, gated at efv_model.PACE_FROM_ENTRY,
# docs/efv-2026-07-31/PACE_FROM_ENTRY_GATE.md. If someone later proposes
# "just use AP+ in eFV", that document explains why the answer is still no.
# ---------------------------------------------------------------------------
#
# NAME-COLLISION HAZARD: the eFV pipeline has its own level_rank on a
# DIFFERENT 0-5 DSL-separate scale. Every ladder quantity here is
# ap_-prefixed (ap_level_rank, ap_starting_level, ...) so the two scales
# can never be confused in code or data.
# ============================================================================
"""Advancement Pace+ display bake: data/advancement_pace.json (+ QC eval).

Method (mirrors the vendored spec, adapted honestly to platform data):
  ladder     Rk(1, CPX+DSL folded at the sportId 16 grain) A(2) A+(3) AA(4)
             AAA(5); MLB is a terminal event, never a rung
  panel      .cache/milb_stats/hitting_{11,12,13,14,16}_{2014..2026}.json,
             one row per player-season-level, PA summed; sportId 15
             (short-season) excluded and counted; hitters only
  meaningful PA >= 30 at a level-season; active season = >= 1 meaningful
             assignment; post-debut seasons dropped (debut season kept, the
             score freezes at the last as-of); 2020 has no MiLB rows so it
             can never count as development time
  entries    2015+ only. 2014 is the left-censor guard year: a player whose
             first observed season is 2014 may have pre-panel history, so
             those entries are excluded from the scoreable pool. (The source
             panel starts 2009 with a 2008 guard; this is the documented
             divergence forced by our cache depth.)
  raw pace   area_pace = mean PA-weighted ladder height per active season
  baseline   joint fixed-effects OLS (np.linalg.lstsq): one dummy per
             starting_level x experience_year cell + additive drop-first
             dummies for entry-age bucket (<=17/18/19-20/21-22/23+), era
             (2015-16/2017-19/2021+), position group (C/MIF/CIF/OF/UT/UNK),
             pathway (draft_hs/draft_college/intl_amateur/undrafted_other)
  score      AP+ = 100 + 10 * z * m/(m+1), m = meaningful assignments.
             Published under TWO keys that must never be confused:
             ap_plus is the MODEL value (uncapped) and ap_plus_display
             is that value clipped to 70-130 for display only. The
             clamp used to be written back over the plain ap_plus name,
             so the model number was discarded at export and 21 of
             3,069 published rows read exactly 130.0.
             Percentile within experience-year scoreable pool; tiers
             Insufficient (score suppressed) / Early / Developing /
             Established

Documented divergences from the source build (recorded in meta.divergences):
  - entry cohorts 2015+ (source: 2009+), guard year 2014 (source: 2008)
  - position group from games shares in data/positions_played.json (source:
    innings-weighted primary MiLB position); players outside that file fall
    into an UNK bucket the joint OLS holds flat like any other margin
  - pathway: draft tables cover 2017+ drafts, so 2015-16 entries classify by
    the DSL-league / entry-age heuristic only
"""
from __future__ import annotations

import json
import logging
import math
import sqlite3
from datetime import date
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

ROOT = Path(__file__).parent
DATA = ROOT / "data"
CACHE = ROOT / ".cache" / "milb_stats"
DB_PATH = ROOT / "prospects.db"
OUT_PATH = DATA / "advancement_pace.json"
EVAL_PATH = DATA / "advancement_pace_eval.json"

METHODOLOGY_VERSION = "1.0.0-eephus"
MEANINGFUL_PA = 30
ALT_THRESHOLD = 20          # QC-only threshold-stability rebuild
K_STABILIZE = 1
DISPLAY_CAP = (70.0, 130.0)
MIN_SD_N = 50               # per-experience-year residual SD pooling floor

SEASONS = range(2014, 2027)
LEFT_CENSOR_GUARD = 2014    # first cache season; entries seen here are censored
SPORT_TO_LEVEL = {11: "AAA", 12: "AA", 13: "A+", 14: "A", 16: "Rk"}
EXCLUDED_SPORT = 15         # historical short-season leagues, counted not used
# ap_ ladder scale. NOT the eFV level_rank scale (that one is 0-5 with DSL
# separate); the ap_ prefix is load-bearing, never drop it.
AP_LEVEL_RANK = {"Rk": 1, "A": 2, "A+": 3, "AA": 4, "AAA": 5}
AP_RANK_LEVEL = {v: k for k, v in AP_LEVEL_RANK.items()}

AGE_BUCKETS = ((0, 17, "<=17"), (18, 18, "18"), (19, 20, "19-20"),
               (21, 22, "21-22"), (23, 99, "23+"))
ERA_BUCKETS = ((2015, 2016, "2015-16"), (2017, 2019, "2017-19"),
               (2021, 2030, "2021+"))
ADJUST_COLS = ("age_bucket", "era", "position_group", "entry_pathway")
POSGROUP = {"C": "C", "SS": "MIF", "2B": "MIF", "1B": "CIF", "3B": "CIF",
            "LF": "OF", "CF": "OF", "RF": "OF", "OF": "OF"}
UT_SHARE = 0.40             # primary-position games share below this -> UT

FOOTNOTE_2020 = ("2020 minor-league season cancelled; never counted as "
                 "development time")
FOOTNOTE_2026 = ("2026 reflects the season in progress through the latest "
                 "stats cache refresh")


def _age_bucket(age) -> str:
    if age is None:
        return "unknown"
    for lo, hi, lab in AGE_BUCKETS:
        if lo <= age <= hi:
            return lab
    return "unknown"


def _era_bucket(season) -> str:
    for lo, hi, lab in ERA_BUCKETS:
        if lo <= season <= hi:
            return lab
    return "other"


# ---------------------------------------------------------------- data loads
def load_panel():
    """{mlbam: [row...]} one row per player-season-level (PA summed), plus
    names and the excluded short-season row count."""
    obs: dict[int, dict[tuple[int, str], dict]] = {}
    names: dict[int, str] = {}
    excluded_short = 0
    for sid, level in SPORT_TO_LEVEL.items():
        rank = AP_LEVEL_RANK[level]
        for season in SEASONS:
            path = CACHE / f"hitting_{sid}_{season}.json"
            if not path.exists():
                continue
            for r in json.loads(path.read_text(encoding="utf-8")):
                pa = int(r.get("pa") or 0)
                mid = r.get("mlbam")
                if not mid or pa <= 0:
                    continue
                mid = int(mid)
                names[mid] = r.get("name") or names.get(mid) or ""
                key = (season, level)
                rows = obs.setdefault(mid, {})
                e = rows.get(key)
                if e is None:
                    rows[key] = {"season": season, "level": level,
                                 "ap_level_rank": rank, "pa": pa,
                                 "age": r.get("age"),
                                 "league": r.get("league") or ""}
                else:
                    e["pa"] += pa
    for season in SEASONS:
        path = CACHE / f"hitting_{EXCLUDED_SPORT}_{season}.json"
        if path.exists():
            excluded_short += len(json.loads(path.read_text(encoding="utf-8")))
    panel = {mid: sorted(rows.values(),
                         key=lambda e: (e["season"], e["ap_level_rank"]))
             for mid, rows in obs.items()}
    return panel, names, excluded_short


def load_identity():
    """Tracked-player identity: key<->mlbam + is_pitcher, from the statlines
    payloads (actives) plus data/debuts.json (debuted alumni). Same identity
    surfaces the other by_mlbam sidecars join through."""
    key2mlbam: dict[str, int] = {}
    is_pitcher: dict[int, bool] = {}
    with sqlite3.connect(DB_PATH) as con:
        for pk, pj in con.execute(
                "SELECT player_key, payload_json FROM statlines"):
            try:
                p = json.loads(pj)
            except (TypeError, ValueError):
                continue
            mid = p.get("mlbam_id")
            if mid:
                key2mlbam[pk] = int(mid)
                if p.get("is_pitcher") is not None:
                    is_pitcher[int(mid)] = bool(p.get("is_pitcher"))
    debuts_path = DATA / "debuts.json"
    debut_season: dict[int, int] = {}
    if debuts_path.exists():
        for r in json.loads(debuts_path.read_text(encoding="utf-8")):
            mid = r.get("mlbam_id")
            if not mid:
                continue
            mid = int(mid)
            pk = r.get("player_key")
            if pk and pk not in key2mlbam:
                key2mlbam[pk] = mid
            dd = r.get("debut_date") or ""
            if r.get("status") == "debuted" and len(dd) >= 4:
                try:
                    debut_season[mid] = min(int(dd[:4]),
                                            debut_season.get(mid, 9999))
                except ValueError:
                    pass
    return key2mlbam, is_pitcher, debut_season


def load_debuts(key2mlbam: dict[str, int], debut_season: dict[int, int]):
    """MLB debut season per mlbam: debuts.json + first MLB hitting-cache
    appearance + career_war seasons (older-debut fallback)."""
    debut = dict(debut_season)
    for season in SEASONS:
        path = CACHE / f"hitting_1_{season}.json"
        if not path.exists():
            continue
        for r in json.loads(path.read_text(encoding="utf-8")):
            mid = r.get("mlbam")
            if mid:
                mid = int(mid)
                debut[mid] = min(season, debut.get(mid, 9999))
    with sqlite3.connect(DB_PATH) as con:
        for pk, pj in con.execute(
                "SELECT player_key, payload_json FROM career_war"):
            mid = key2mlbam.get(pk)
            if not mid:
                continue
            try:
                seasons = (json.loads(pj) or {}).get("seasons") or {}
                yrs = [int(y) for y in seasons]
            except (TypeError, ValueError):
                continue
            if yrs:
                debut[mid] = min(min(yrs), debut.get(mid, 9999))
    return debut


def load_pathway_sources(key2mlbam: dict[str, int]):
    """{mlbam: [(draft_year, 'draft_hs'|'draft_college'), ...]}. mlbam_id is
    only stamped on the newest draft class, so the workhorse join is
    promoted_key (draftee -> tracked player_key) -> key2mlbam. Coverage
    starts with the 2017 draft; earlier draftees classify by heuristic
    (documented divergence)."""
    out: dict[int, list] = {}
    with sqlite3.connect(DB_PATH) as con:
        for mid, pk, yr, pt in con.execute(
                "SELECT mlbam_id, promoted_key, draft_year, player_type "
                "FROM draft_players"):
            pt = str(pt or "").upper()
            if pt.startswith("HS"):
                path = "draft_hs"
            elif pt.startswith("COL"):
                path = "draft_college"
            else:
                continue
            mid = int(mid) if mid else key2mlbam.get(pk or "")
            if mid:
                out.setdefault(int(mid), []).append((int(yr), path))
    return out


def load_position_groups(key2mlbam: dict[str, int]):
    """{mlbam: C/MIF/CIF/OF/UT} from games shares in positions_played.json.
    Divergence from the source (documented): games-based shares, not
    innings-weighted; primary share under UT_SHARE -> UT; players outside
    the file fall to UNK at fit time."""
    path = DATA / "positions_played.json"
    if not path.exists():
        return {}
    players = (json.loads(path.read_text(encoding="utf-8")) or {}).get(
        "players") or {}
    out: dict[int, str] = {}
    for pk, rec in players.items():
        mid = key2mlbam.get(pk)
        if not mid:
            continue
        by_pos = rec.get("by_pos") or {}
        games = {pos: (v.get("g") or 0) for pos, v in by_pos.items()
                 if pos in POSGROUP}          # defensive positions only
        total = sum(games.values())
        if total <= 0:
            out[mid] = "UT"
            continue
        pos, g = max(games.items(), key=lambda kv: kv[1])
        out[mid] = POSGROUP[pos] if (g / total) >= UT_SHARE else "UT"
    return out


# ------------------------------------------------------------- as-of builder
def build_asof(panel, debut, draft_map, posgroup_map, threshold):
    """One dict per player x ACTIVE as-of season (spec raw_pace.build_asof,
    active rows only) + per-player attributes. Returns (asof_rows, players)."""
    players: dict[int, dict] = {}
    asof: list[dict] = []
    for mid, rows in panel.items():
        dseason = debut.get(mid)
        if dseason:
            rows = [r for r in rows if r["season"] <= dseason]
        if not rows:
            continue
        first_obs = min(r["season"] for r in rows)
        entry_ages = [r["age"] for r in rows
                      if r["season"] == first_obs and r["age"] is not None]
        entry_age = min(entry_ages) if entry_ages else None
        dsl_entry = any(r["season"] == first_obs and r["league"] == "DSL"
                        for r in rows)

        # pathway: DSL entry -> intl; else draft record (draft_year <= entry
        # season) -> draft_hs/draft_college; else entry-age heuristic
        pathway = None
        if dsl_entry:
            pathway = "intl_amateur"
        else:
            recs = [(y, p) for (y, p) in draft_map.get(mid, ())
                    if y <= first_obs]
            if recs:
                pathway = max(recs)[1]
            elif entry_age is not None and entry_age <= 18:
                pathway = "intl_amateur"
            else:
                pathway = "undrafted_other"

        by_season: dict[int, list] = {}
        for r in rows:
            by_season.setdefault(r["season"], []).append(r)

        active_seasons = 0
        height_sum = 0.0
        n_assign = 0
        highest = None
        starting_level = None
        first_meaningful = None
        seasons_meaningful: list[int] = []
        level_history: list = []
        last = None
        for season in sorted(by_season):
            msn = [r for r in by_season[season] if r["pa"] >= threshold]
            if not msn:
                continue
            active_seasons += 1
            seasons_meaningful.append(season)
            m_pa = sum(r["pa"] for r in msn)
            season_height = sum(r["pa"] * r["ap_level_rank"] for r in msn) / m_pa
            height_sum += season_height
            n_assign += len(msn)
            top = max(r["ap_level_rank"] for r in msn)
            highest = top if highest is None else max(highest, top)
            if first_meaningful is None:
                first_meaningful = season
                # DIVERGENCE from the source (max-PA level): starting level =
                # LOWEST-rank meaningful level of the first meaningful season.
                # Season aggregates carry no stint order, and on a promotion
                # ladder the lowest rung is where the path began; the max-PA
                # rule mislabels within-season climbers (a player who blitzes
                # A -> A+ -> AA in year 1 would start "A+" and read slow).
                starting_level = min(msn,
                                     key=lambda r: r["ap_level_rank"])["level"]
            level_history.append(
                [season, [[r["level"], r["pa"]] for r in
                          sorted(msn, key=lambda r: r["ap_level_rank"])]])
            last = {
                "mlbam": mid, "season": season,
                "experience_year": active_seasons,
                "area_pace": height_sum / active_seasons,
                "meaningful_assignments": n_assign,
                "highest_rank": highest,
                "meaningful_promotions": highest - AP_LEVEL_RANK[starting_level],
            }
            asof.append(last)

        left_censored = first_obs <= LEFT_CENSOR_GUARD
        players[mid] = {
            "first_pro_season": first_obs,
            "entry_age": entry_age,
            "entry_pathway": pathway,
            "position_group": posgroup_map.get(mid, "UNK"),
            "first_meaningful_season": first_meaningful,
            "starting_level": starting_level,
            "left_censored": left_censored,
            "scoreable": (not left_censored) and first_meaningful is not None,
            "debut_season": dseason,
            "level_history": level_history,
            "spans_2020": bool(seasons_meaningful
                               and min(seasons_meaningful) <= 2019
                               and max(seasons_meaningful) >= 2021),
            "latest_asof": last,
        }
    for row in asof:
        p = players[row["mlbam"]]
        row["scoreable"] = p["scoreable"]
        row["starting_level"] = p["starting_level"]
        row["age_bucket"] = _age_bucket(p["entry_age"])
        row["era"] = _era_bucket(p["first_meaningful_season"] or 0)
        row["position_group"] = p["position_group"]
        row["entry_pathway"] = p["entry_pathway"]
    return asof, players


# ------------------------------------------------------------ peer baseline
def fit_baseline(asof):
    """Joint fixed-effects OLS on the scoreable pool (spec peer_baseline):
    full one-hot per starting_level x experience_year cell (carries the
    intercept) + drop-first dummies per adjustment margin."""
    pool = [r for r in asof if r["scoreable"]]
    cells = sorted({f"{r['starting_level']}|{r['experience_year']}"
                    for r in pool})
    cats = {c: sorted({str(r[c]) for r in pool}) for c in ADJUST_COLS}
    cell_ix = {c: i for i, c in enumerate(cells)}
    dum_cols = [(c, v) for c in ADJUST_COLS for v in cats[c][1:]]
    ncol = len(cells) + len(dum_cols)
    X = np.zeros((len(pool), ncol))
    y = np.empty(len(pool))
    for i, r in enumerate(pool):
        X[i, cell_ix[f"{r['starting_level']}|{r['experience_year']}"]] = 1.0
        for j, (c, v) in enumerate(dum_cols):
            if str(r[c]) == v:
                X[i, len(cells) + j] = 1.0
        y[i] = r["area_pace"]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    pred = X @ beta
    exp_mean: dict[int, list] = {}
    for r, p in zip(pool, pred):
        r["expected_peer_pace"] = float(p)
        r["advancement_residual"] = r["area_pace"] - float(p)
        exp_mean.setdefault(r["experience_year"], []).append(r["area_pace"])
    return pool, cells, cats


def score(pool):
    """z on per-experience-year residual SD (pooled under MIN_SD_N), shrink
    by meaningful assignments, cap for display, percentile within the
    experience-year scoreable pool (spec score.build_scores)."""
    by_exp: dict[int, list] = {}
    for r in pool:
        by_exp.setdefault(r["experience_year"], []).append(r)
    all_res = np.array([r["advancement_residual"] for r in pool])
    pooled_sd = float(all_res.std(ddof=1)) if len(all_res) > 1 else 1.0
    for exp, rows in by_exp.items():
        res = np.array([r["advancement_residual"] for r in rows])
        sd = float(res.std(ddof=1)) if len(rows) >= MIN_SD_N else pooled_sd
        sd = sd if sd > 0 else pooled_sd
        for r in rows:
            z = r["advancement_residual"] / sd
            m = r["meaningful_assignments"]
            r["ap_z_raw"] = z
            r["ap_z_stab"] = z * m / (m + K_STABILIZE)
            r["ap_plus_unshrunk"] = 100 + 10 * z
            r["ap_plus"] = 100 + 10 * r["ap_z_stab"]
            r["ap_plus_display"] = min(max(r["ap_plus"], DISPLAY_CAP[0]),
                                       DISPLAY_CAP[1])
        order = np.argsort([r["ap_z_stab"] for r in rows], kind="stable")
        ranks = np.empty(len(rows))
        ranks[order] = np.arange(1, len(rows) + 1)
        # average ties so equal paces share a percentile
        vals = {}
        for i, r in enumerate(rows):
            vals.setdefault(round(r["ap_z_stab"], 12), []).append(i)
        for ix in vals.values():
            if len(ix) > 1:
                mean_rank = float(np.mean([ranks[i] for i in ix]))
                for i in ix:
                    ranks[i] = mean_rank
        n = len(rows)
        for i, r in enumerate(rows):
            r["ap_percentile"] = int(round(100.0 * ranks[i] / n))


def tier_of(row) -> str:
    if row is None:
        return "Insufficient"
    exp = row["experience_year"]
    if exp >= 3 and row["meaningful_assignments"] >= 3:
        return "Established"
    if exp >= 2 or row["meaningful_promotions"] >= 1:
        return "Developing"
    return "Early"


# ----------------------------------------------------------------- QC bits
def _spearman(a, b) -> float:
    def rank(v):
        v = np.asarray(v, dtype=float)
        order = np.argsort(v, kind="stable")
        r = np.empty(len(v))
        r[order] = np.arange(1, len(v) + 1)
        uniq: dict[float, list] = {}
        for i, x in enumerate(v):
            uniq.setdefault(float(x), []).append(i)
        for ix in uniq.values():
            if len(ix) > 1:
                m = float(np.mean([r[i] for i in ix]))
                for i in ix:
                    r[i] = m
        return r
    ra, rb = rank(a), rank(b)
    if ra.std() == 0 or rb.std() == 0:
        return float("nan")
    return float(np.corrcoef(ra, rb)[0, 1])


# ---------------------------------------------------------------- pipeline
def run(persist: bool = True) -> dict:
    panel, names, excluded_short = load_panel()
    key2mlbam, is_pitcher, debut_season = load_identity()
    debut = load_debuts(key2mlbam, debut_season)
    draft_map = load_pathway_sources(key2mlbam)
    posgroup_map = load_position_groups(key2mlbam)

    asof, players = build_asof(panel, debut, draft_map, posgroup_map,
                               MEANINGFUL_PA)
    pool, cells, cats = fit_baseline(asof)
    score(pool)

    mlbam2key: dict[int, str] = {}
    for k, m in key2mlbam.items():
        mlbam2key.setdefault(m, k)

    # ---- display artifact: tracked identity universe only (the prospx join
    # universe); scores were fit on the full scoreable panel above
    by_mlbam: dict[str, dict] = {}
    tracked = set(mlbam2key)
    for mid in sorted(tracked):
        p = players.get(mid)
        if p is None or not p["scoreable"] or is_pitcher.get(mid):
            continue
        last = p["latest_asof"]
        tier = tier_of(last)
        rec = {
            "player_key": mlbam2key.get(mid),
            "name": names.get(mid, ""),
            "ap_tier": tier,
            "ap_plus": None, "ap_plus_display": None, "ap_percentile": None,
            "ap_experience_year": None, "ap_meaningful_assignments": None,
            "ap_starting_level": p["starting_level"],
            "ap_current_level": None,
            "ap_asof_season": None,
            "ap_raw_pace": None, "ap_expected_pace": None,
            "ap_entry_pathway": p["entry_pathway"],
            "ap_position_group": p["position_group"],
            "ap_entry_age_bucket": _age_bucket(p["entry_age"]),
            "debut_frozen": bool(p["debut_season"]),
            "debut_season": p["debut_season"],
            "spans_2020": p["spans_2020"],
            "level_history": p["level_history"],
        }
        if last is not None and tier != "Insufficient":
            rec.update({
                # ap_plus is the MODEL value (uncapped). It used to carry the
                # 70-130 clamped DISPLAY value under this plain name, which
                # discarded the model number entirely and pinned 21 of 3,069
                # published rows at exactly 130.0 - the same defect class that
                # was removed from KRP+. Both are emitted now, each under a name
                # that says which it is; consumers must pick deliberately.
                "ap_plus": round(last["ap_plus"], 1),
                "ap_plus_display": round(last["ap_plus_display"], 1),
                "ap_percentile": last["ap_percentile"],
                "ap_experience_year": last["experience_year"],
                "ap_meaningful_assignments": last["meaningful_assignments"],
                "ap_current_level": AP_RANK_LEVEL.get(last["highest_rank"]),
                "ap_asof_season": last["season"],
                "ap_raw_pace": round(last["area_pace"], 3),
                "ap_expected_pace": round(last["expected_peer_pace"], 3),
            })
        by_mlbam[str(mid)] = rec

    n_scored_panel = len({r["mlbam"] for r in pool})
    out = {
        "generated_at": date.today().isoformat(),
        "meta": {
            "methodology_version": METHODOLOGY_VERSION,
            "stat_type": "descriptive",
            "model_eligible": False,
            "display_contract": "descriptive display only; forbidden from "
                                "every predictive or valuation consumer "
                                "(eFV, xFV, projections, FA, surplus, trade "
                                "value, readiness); prospx card + glossary "
                                "are the only consumers",
            "meaningful_pa_threshold": MEANINGFUL_PA,
            "ladder": ["Rk", "A", "A+", "AA", "AAA"],
            "ladder_note": "ap_ ladder scale, Rk folds CPX+DSL at the "
                           "sportId 16 grain; NOT the eFV level_rank scale",
            "scale": "100 = typical peer-adjusted ladder pace for a "
                     "comparable path; 110 is one standard unit faster; "
                     "never percentage language",
            "value_keys": {
                "ap_plus": "MODEL value, uncapped (100 + 10 * shrunk z)",
                "ap_plus_display": f"ap_plus clipped to {DISPLAY_CAP[0]:.0f}-"
                                   f"{DISPLAY_CAP[1]:.0f} for display only",
                "note": "the clamp is a display convention, so it rides its "
                        "own key; ap_plus is never the clamped number",
            },
            "panel": "hitters, entry cohorts 2015+ from "
                     ".cache/milb_stats hitting files 2014-2026; 2014 is "
                     "the left-censor guard year",
            "footnote_2020": FOOTNOTE_2020,
            "footnote_2026": FOOTNOTE_2026,
            "divergences": [
                "entry cohorts 2015+ with 2014 guard (source panel: 2009+ "
                "with 2008 guard, deeper feeds)",
                "position group from games shares in positions_played.json "
                "(source: innings-weighted primary position); uncovered "
                "players form an UNK adjustment bucket",
                "draft tables start 2017, so 2015-16 entries classify by "
                "the DSL-league / entry-age pathway heuristic",
                "starting level = lowest-rank meaningful level of the first "
                "meaningful season (source: max-PA level); season aggregates "
                "carry no stint order and the max-PA rule mislabels "
                "within-season year-1 climbers",
            ],
            "counts": {
                "panel_players": len(panel),
                "panel_scoreable_players": n_scored_panel,
                "tracked_published": len(by_mlbam),
                "short_season_rows_excluded": excluded_short,
            },
        },
        "by_mlbam": by_mlbam,
        "key_to_mlbam": {k: m for k, m in sorted(key2mlbam.items())
                         if str(m) in by_mlbam},
    }

    # ------------------------------------------------------------- QC eval
    latest = {}
    for r in pool:
        cur = latest.get(r["mlbam"])
        if cur is None or r["season"] > cur["season"]:
            latest[r["mlbam"]] = r
    lat_rows = list(latest.values())
    disp = np.array([r["ap_plus_display"] for r in lat_rows])
    modl = np.array([r["ap_plus"] for r in lat_rows])

    def _margin(col):
        agg: dict[str, list] = {}
        for r in pool:
            agg.setdefault(str(r[col]), []).append(r["ap_plus_unshrunk"])
        return {k: {"mean_ap_plus": round(float(np.mean(v)), 2), "n": len(v)}
                for k, v in sorted(agg.items())}

    asof20, _players20 = build_asof(panel, debut, draft_map, posgroup_map,
                                    ALT_THRESHOLD)
    latest20 = {}
    for r in asof20:
        cur = latest20.get(r["mlbam"])
        if cur is None or r["season"] > cur["season"]:
            latest20[r["mlbam"]] = r
    common = sorted(set(latest) & set(latest20))
    rho = _spearman([latest[m]["area_pace"] for m in common],
                    [latest20[m]["area_pace"] for m in common])

    risers = sorted(
        (rec for rec in by_mlbam.values()
         if rec["ap_plus"] is not None
         and rec["ap_tier"] in ("Developing", "Established")
         and (rec["ap_asof_season"] or 0) >= 2024),   # current-era, eyeballable
        key=lambda rec: (-rec["ap_plus"],
                         -(rec["ap_meaningful_assignments"] or 0)))[:5]

    evaluation = {
        "generated_at": date.today().isoformat(),
        "artifact": "data/advancement_pace.json",
        "kind": "descriptive QC only - no predictive claim is made or "
                "permitted anywhere for this statistic",
        "methodology_version": METHODOLOGY_VERSION,
        "n_scored_latest_asof": len(lat_rows),
        "n_asof_rows_fit": len(pool),
        "distribution_ap_plus_display_latest": {
            "mean": round(float(disp.mean()), 2),
            "sd": round(float(disp.std(ddof=1)), 2),
            "p5": round(float(np.percentile(disp, 5)), 1),
            "p25": round(float(np.percentile(disp, 25)), 1),
            "p50": round(float(np.percentile(disp, 50)), 1),
            "p75": round(float(np.percentile(disp, 75)), 1),
            "p95": round(float(np.percentile(disp, 95)), 1),
            "n_at_low_clip": int((disp <= DISPLAY_CAP[0]).sum()),
            "n_at_high_clip": int((disp >= DISPLAY_CAP[1]).sum()),
        },
        # The UNCAPPED model distribution beside the clipped display one, so
        # the size of the display convention is measurable instead of implied.
        "distribution_ap_plus_model_latest": {
            "mean": round(float(modl.mean()), 2),
            "sd": round(float(modl.std(ddof=1)), 2),
            "min": round(float(modl.min()), 1),
            "max": round(float(modl.max()), 1),
            "p5": round(float(np.percentile(modl, 5)), 1),
            "p50": round(float(np.percentile(modl, 50)), 1),
            "p95": round(float(np.percentile(modl, 95)), 1),
        },
        "margin_flatness_fit_pool": {
            "note": "joint-OLS residual means are exactly zero per included "
                    "margin by construction; the per-experience-year SD "
                    "scaling that builds z can move a margin mean up to "
                    "about a point on this panel (residual sign correlating "
                    "with experience year inside a margin)",
            "era": _margin("era"),
            "position_group": _margin("position_group"),
            "entry_pathway": _margin("entry_pathway"),
            "entry_age_bucket": _margin("age_bucket"),
        },
        "threshold_stability": {
            "raw_pace_spearman_T20_vs_T30": round(rho, 4),
            "n_common_players": len(common),
        },
        "named_riser_sanity": [
            {"name": r["name"], "ap_plus": r["ap_plus"],
             "ap_percentile": r["ap_percentile"], "ap_tier": r["ap_tier"],
             "path": f"{r['ap_starting_level']} -> {r['ap_current_level']}"
                     f" in {r['ap_experience_year']} active seasons"}
            for r in risers],
    }

    if persist:
        for path, payload in ((OUT_PATH, out), (EVAL_PATH, evaluation)):
            text = json.dumps(payload, indent=0) + "\n"
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                path.write_text(text, encoding="utf-8")
                log.info("wrote %s", path)
            else:
                log.info("%s unchanged", path)
    return {"out": out, "eval": evaluation}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    rep = run()
    ev = rep["eval"]
    print(json.dumps(ev["distribution_ap_plus_display_latest"], indent=1))
    print("scored", ev["n_scored_latest_asof"], "latest as-of rows;",
          "published", rep["out"]["meta"]["counts"]["tracked_published"],
          "tracked players ->", OUT_PATH.name)
