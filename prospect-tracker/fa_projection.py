# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Projection engine for the MLB Free Agency module (Stage 2).

Architecture (per the approved plan): COMPONENTS FIRST, COMPOSITES SECOND.
Component rates (K%, BB%, ISO, BABIP, HR rate for hitters; K%, BB%, HR/BF
for pitchers) are Marcel-weighted [5, 3, 2], regressed to the league mean
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
import os
import pickle
import time
from collections import defaultdict
from pathlib import Path

import fa_class
import fa_sources

log = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / ".cache"
CORPUS_CACHE = CACHE_DIR / "fa_corpus.pkl"
CURVES_PATH = Path(__file__).parent / "data" / "fa_aging_curves.json"

# The SHAPE of the corpus WAR columns, stamped onto every corpus this module
# builds and read by everything keyed off the label. Bumped when the MEANING of
# a row's `war` changes, which is a label change even when the WAR provider has
# not moved. 'side_keyed_v1' is the 2026-09-18 two-sided repair: a row's `war`
# is THIS SIDE'S WAR and `war_total` is the player-season's whole WAR. A corpus
# pickled without the stamp predates the repair and carries the whole-player
# total on the hitter row AND on the pitcher row, so _corpus_label_shape_stale
# refuses it and proj_ml._war_tag keeps its caches apart from it.
LABEL_SHAPE = "side_keyed_v1"

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


def _side_war_age_maps(provider: str | None = None) -> tuple[dict, dict]:
    """{(side, mlbam, season): war} KEYED BY WAR_DAILY SIDE ('bat' | 'pit'),
    and {(mlbam, season): age}, from the war_daily stint frames read through
    the war_source facade on ``provider`` (None = the facade DEFAULT, eWAR v2
    since 2026-09-03).

    THE SIDE KEY IS THE REPAIR (2026-09-18, the label lane). _war_age_maps
    below returns these same rows SUMMED ACROSS SIDES, and build_corpus used
    to write that whole-player total onto the hitter row AND onto the pitcher
    row through one side-blind lookup. 671 of 35,825 corpus player-seasons
    carry a row on both sides and every one of them held the IDENTICAL value
    on each row; proj_ml.build_training_frame and proj_eval._assemble then
    summed across sides again, so a player who both hit and pitched trained
    and scored at EXACTLY TWICE his real WAR (Ohtani 2023 entered the frame at
    17.08 against a real 8.54, 2025 at 16.72 against 8.36, while 2024 - a year
    he did not pitch - was correct at 9.04). Keying by side gives the hitter
    row his hitting WAR and the pitcher row his pitching WAR, and the two
    downstream sums become H + P = T by arithmetic instead of T + T.

    Per-side is also what the per-side FITS have always needed. fit_war_map
    regresses a hitter's WAR on PA and a pitcher's WAR on IP, and
    fit_aging_curves ages a per-side war_rate; handing either the other side's
    WAR is incoherent whatever the doubling does, and it reached far more rows
    than the 671 - every corpus row whose player-season has war_daily rows on
    both sides, 9,087 of 36,496 on the 2026-09-17 corpus.

    THE LABEL IS A DIFFERENT QUANTITY and keeps its own column. The training
    and eval label is the player's TOTAL WAR (docs/PROJ_PATH_SHAPE_GATE.md L2:
    each side-keyed model estimates E[TOTAL player WAR | this side's line]),
    so build_corpus stamps `war_total` alongside `war` and war_actual_map
    reads it ONCE per player-season. The repair removes the DOUBLING, not the
    TOTALITY, and a player-season carrying a corpus row on one side only keeps
    the label it already had.

    Age rides the same rows, is basis-invariant and is deliberately NOT
    side-keyed: it is a property of the player-season and both frames carry
    it. provider='bwar' reproduces the pre-epoch corpus. The basis is a
    decision, not an accuracy claim: data/ewar_eval.json gate 1 team wins
    r 0.8595 vs bWAR 0.8803, gate 2 pitcher persistence 0.3617 vs 0.1768."""
    import pybaseball  # noqa: F401 - availability probe; frames come via war_source
    import war_source
    provider = provider or war_source.DEFAULT_PROVIDER
    war: dict[tuple[str, int, int], float] = {}
    age: dict[tuple[int, int], int] = {}
    for side in ("bat", "pit"):
        try:
            df = war_source.stint_frame(side, provider=provider)
        except Exception as e:                                # noqa: BLE001
            log.warning("war_daily %s frame (%s) unavailable: %s", side, provider, e)
            continue
        sub = df[df["mlb_ID"].notna() & df["WAR"].notna()]
        for row in sub.itertuples(index=False):
            try:
                ps = (int(row.mlb_ID), int(row.year_ID))
            except (TypeError, ValueError):
                continue
            key = (side, ps[0], ps[1])
            war[key] = war.get(key, 0.0) + _f(row.WAR)
            try:
                age[ps] = int(row.age)
            except (TypeError, ValueError):
                pass
    return war, age


def _sum_sides(side_war: dict) -> dict:
    """Collapse a side-keyed WAR map onto {(mlbam, season): TOTAL player WAR}.

    Iteration runs in the side-keyed map's insertion order - the whole bat
    frame, then the whole pit frame - which is the order the pre-repair
    accumulation used, so the summed value is float-identical to what
    _war_age_maps returned before the side key existed. That identity is what
    lets `war_total` leave a one-sided player-season's label exactly where it
    was."""
    out: dict[tuple[int, int], float] = {}
    for (_side, mlbam, season), w in side_war.items():
        out[(mlbam, season)] = out.get((mlbam, season), 0.0) + w
    return out


def _war_age_maps(provider: str | None = None) -> tuple[dict, dict]:
    """{(mlbam, season): war} (bat+pit summed) and {(mlbam, season): age}.

    THE WHOLE-PLAYER VIEW, kept deliberately and with its contract unchanged.
    A player-season's TOTAL WAR is the right quantity for a LABEL, and
    war_actual_map builds the training and eval label from it. What was wrong
    was writing this total onto a SIDE-KEYED corpus row: build_corpus now
    reads _side_war_age_maps for a row's own `war` and this map for its
    `war_total`. See _side_war_age_maps for the defect and its measurement."""
    side_war, age = _side_war_age_maps(provider)
    return _sum_sides(side_war), age


# _war_age_maps is a documented OFF HOOK, not only a function.
# tools/build_ewar.live_fip_corpus rebuilds a FIP-only corpus for the nightly
# eWAR artifact and switches the WAR and age join off by replacing this name
# with a stub returning empty maps - it has to, because the war_daily frames it
# would otherwise read are priced by the very artifact it is rebuilding, which
# is the re-entrancy war_source's own docstring warns about. build_corpus now
# reads the SIDE-keyed map instead, so it compares the name against this alias
# to see whether the hook has been taken, rather than silently defeating it.
_WHOLE_PLAYER_WAR_AGE_MAPS = _war_age_maps


# ============================================================================
# P-CTTL: corpus cache invalidation on DATA age, not calendar year
# ============================================================================
# The old accept condition was `cached["last"] >= date.today().year`, which is
# permanently true from January onward: within a season the pickle NEVER
# expired. Measured 2026-07-24: a corpus frozen 2026-06-23 (88,517 league PA,
# season_fraction 0.484) was serving a payload stamped the same day, against a
# StatsAPI source cache that had been refetched that morning. Everything keyed
# on corpus['last'] (fitted_models, the proj_ml frame cache) inherited the
# freeze, and the in-progress reliability blend over-weighted the prior season
# by ~22 points of weight for every veteran. Two triggers, both cheap:
#   1. a SOURCE file for the in-progress season is newer than the pickle
#   2. the pickle is older than CORPUS_TTL_DAYS while an in-progress season is
#      in it (catches a source refetched in place with an unchanged mtime)
# Completed-season-only corpora (last < current year) never expire: their
# inputs are final apart from bWAR revisions, which the annual rollover picks
# up anyway.
CORPUS_TTL_DAYS = 3


def _corpus_stale_reason(cached: dict, last: int) -> str | None:
    """Why the cached corpus must be rebuilt, or None to accept it."""
    from datetime import date
    if last < date.today().year:
        return None                              # no in-progress season in it
    try:
        c_mtime = CORPUS_CACHE.stat().st_mtime
    except OSError:
        return None
    newest = 0.0
    for group in ("hitting", "pitching"):
        p = CACHE_DIR / f"fa_statsapi_{group}_{last}.json"
        try:
            newest = max(newest, p.stat().st_mtime)
        except OSError:
            continue
    if newest > c_mtime:
        return f"source {last} newer than corpus ({newest - c_mtime:.0f}s)"
    age_days = (time.time() - c_mtime) / 86400.0
    if age_days > CORPUS_TTL_DAYS:
        return f"in-progress season {last}, corpus {age_days:.1f}d old"
    return None


def _war_provider() -> str:
    """The WAR basis a corpus built now is labelled on: the facade default."""
    import war_source
    return war_source.DEFAULT_PROVIDER


def _corpus_provider_stale(cached: dict) -> str | None:
    """Why a cached corpus must be rebuilt on WAR BASIS grounds, or None.

    A corpus pickled before the 2026-09-03 epoch carries no 'war_provider'
    and was built on bWAR; one pickled after carries the facade default it
    was built under. Either is stale the moment the default differs, whatever
    its data age: the WAR column IS the label, so an accepted mismatch would
    fit the aging curves, the WAR map, proj_ml's frames and every free-agent
    price on the other series and nothing downstream could tell (the P-CTTL
    triggers see only mtimes). Kept apart from _corpus_stale_reason, which
    is about data age and lets a completed-season corpus live forever."""
    want = _war_provider()
    have = cached.get("war_provider") or "bwar"
    if have != want:
        return f"WAR provider {have} != facade default {want}"
    return None


def _corpus_label_shape_stale(cached: dict) -> str | None:
    """Why a cached corpus must be rebuilt on LABEL SHAPE grounds, or None.

    A corpus pickled before the 2026-09-18 two-sided label repair carries no
    'label_shape' and holds the player's TOTAL WAR on his hitter row AND on
    his pitcher row, which the training frame and the eval harness then sum
    again. Nothing else on this path can see that: the pickle is fresh, the
    provider matches, and the WAR column is simply the wrong quantity. So the
    shape is stamped and compared, and a mismatch is stale whatever the data
    age - the same argument _corpus_provider_stale makes for the basis, and
    the reason the repair cannot be half-applied by an operator who forgot
    ``force=True``."""
    have = cached.get("label_shape")
    if have != LABEL_SHAPE:
        return (f"label shape {have or 'pre-side-keyed (2x on two-sided rows)'} "
                f"!= {LABEL_SHAPE}")
    return None


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
    cached = None
    if CORPUS_CACHE.exists() and not force:
        with open(CORPUS_CACHE, "rb") as fh:
            cached = pickle.load(fh)
        if cached.get("first") == first and cached.get("last") >= last - 0:
            reason = (_corpus_provider_stale(cached)
                      or _corpus_label_shape_stale(cached)
                      or _corpus_stale_reason(cached, last))
            if reason is None:
                return cached
            log.info("fa corpus cache stale (%s) - rebuilding", reason)
        else:
            cached = None
    try:
        if _war_age_maps is _WHOLE_PLAYER_WAR_AGE_MAPS:
            # The normal path: ONE pull of the war_daily frames. `war_side`
            # feeds each row's own `war`; `war_map` is the same rows summed per
            # player-season, in the same order the pre-repair lookup summed
            # them, and feeds the `war_total` LABEL column.
            war_side, age_map = _side_war_age_maps()
            war_map = _sum_sides(war_side)
        else:
            # The OFF hook has been taken (see _WHOLE_PLAYER_WAR_AGE_MAPS).
            # Honour it exactly: whatever the override returns is the whole
            # WAR and age join, and there is no per-side column to write.
            war_map, age_map = _war_age_maps()
            war_side = {}
    except Exception as e:                       # noqa: BLE001 - fail-soft
        # P-CTTL: the staleness rebuild must never be able to take a surface
        # DOWN that a stale-but-usable pickle would have served. Any source
        # failure (pybaseball / network) falls back to the cached corpus.
        if cached is not None:
            mismatch = _corpus_provider_stale(cached)
            log.warning("fa corpus rebuild failed (%s) - serving the STALE cache%s", e,
                        f"; WAR BASIS MISMATCH, {mismatch}" if mismatch else "")
            return cached
        raise
    # P-CTTL guard: _side_war_age_maps is fail-SOFT (a bwar fetch failure logs and
    # returns an EMPTY map), so without this a network blip would pickle a corpus
    # with war=None on every row — silently zeroing the WAR map, the war_rate
    # aging curves and every projection. Refuse to overwrite a good cache with
    # a WAR-less one.
    if cached is not None and len(war_map) < 0.5 * sum(
            1 for r in cached.get("hit", []) + cached.get("pit", [])
            if r.get("war") is not None):
        log.warning("fa corpus rebuild produced a degenerate WAR map (%d keys) — "
                    "serving the STALE cache", len(war_map))
        return cached
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
            # P-LGPIT (MEASURED NON-SHIP, 2026-07-24 projections lane). The
            # accumulation above deliberately runs BEFORE this `continue`, so the
            # league denominators include PITCHERS BATTING for every
            # pre-universal-DH season (K% +0.0058 in 2015/2019/2021 vs +0.00001 in
            # 2023 - a fake step that accounts for 76% of the observed 2021->2022
            # league K% drop). That IS a distortion, and removing it was tested as
            # a proper arm. It LOST, resolvably: over 7 forward-chained bases
            # (2014-2021 ex-2020, 90 paired bootstrap draws, curves + WAR map refit
            # per draw PER VARIANT) taking pitchers out of the denominators cost
            # hitter h1 MAE +0.0191 (CI95 [+0.0174, +0.0207] against a 0.0018 noise
            # floor) and moved hitter h1 bias +0.0289 -> +0.0745. The narrower
            # variant that fixes only the Marcel REGRESSION TARGETS and keeps the
            # all-batters wOBA/r_pa wRAA baseline still cost +0.0145 (hit h1).
            # Mechanism: the too-high league K% is an unintended DEFLATOR that has
            # been offsetting a structural hitter over-projection, so the league
            # means and the hitter level have to be re-fitted TOGETHER. Do not
            # "clean up" this ordering on its own.
            if pos == "P":
                continue                       # pitchers batting: exclude from the hitter CORPUS
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
                # THIS SIDE'S WAR, and the only WAR the per-side fits may see
                # (fit_war_map's hitter regression, fit_aging_curves' war_rate,
                # realwar_residual). Before 2026-09-18 this read the side-blind
                # total, so a player who also pitched carried his pitching WAR
                # on his hitter row - see _side_war_age_maps.
                "war": war_side.get(("bat", *key)) if key else None,
                # THE LABEL, and a different quantity: the player-season's
                # WHOLE WAR, identical on his hitter and his pitcher row and
                # read ONCE by war_actual_map rather than summed across them.
                "war_total": war_map.get(key),
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
                # This side's WAR and the whole-player label; see the hitter
                # row above and _side_war_age_maps for why they are two columns.
                "war": war_side.get(("pit", *key)) if key else None,
                "war_total": war_map.get(key),
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
              "first": first, "last": last,
              # the WAR basis the rows were labelled on (_side_war_age_maps
              # read the facade default); _corpus_provider_stale invalidates
              # on it
              "war_provider": _war_provider(),
              # the SHAPE of the two WAR columns; _corpus_label_shape_stale
              # invalidates on it and proj_ml._war_tag keys the frame and the
              # point-in-time bundle caches on it
              "label_shape": LABEL_SHAPE}
    CACHE_DIR.mkdir(exist_ok=True)
    with open(CORPUS_CACHE, "wb") as fh:
        pickle.dump(corpus, fh)
    log.info("fa corpus: %d hitter-seasons, %d pitcher-seasons, %d league-years",
             len(hit_rows), len(pit_rows), len(league))
    return corpus


def war_actual_map(corpus: dict) -> dict:
    """{(mlbam, season): TOTAL player WAR} - THE LABEL, taken ONCE per
    player-season instead of accumulated across sides.

    ONE IMPLEMENTATION, because the training frame and the eval harness must
    agree: proj_ml.build_training_frame and proj_eval._assemble both call
    this. Scoring against a truth that is built differently from the one you
    trained on is how the two-sided defect stayed invisible - both sides of
    the comparison were doubled, so the error cancelled in every published
    receipt and showed up only in the level.

    WHY NOT SUM `war` ACROSS SIDES. After the repair a row's `war` is its own
    side's WAR, so hit + pit does recover the total for a player-season that
    carries a corpus row on BOTH sides. It does NOT for one that carries a row
    on one side only: a pitcher's plate appearances are excluded from the
    hitter corpus by position (build_corpus skips pos == 'P'), so summing the
    rows would silently drop his batting WAR. Measured on the 2026-09-17
    corpus that is 7,745 player-seasons and +44.3 WAR of label movement that
    has nothing to do with the defect being repaired, and it would change the
    estimand L2 registers. `war_total` is the whole quantity, identical on
    both of a two-way player's rows, so this assigns it rather than adding it.

    A corpus pickled before the 2026-09-18 repair carries no `war_total`. Such
    a corpus is already refused by _corpus_label_shape_stale, so this branch is
    reachable only from a hand-built fixture; it reproduces the old summing
    behaviour, doubling and all, and says so in the log rather than inventing
    a label it cannot source."""
    out: dict[tuple, float] = {}
    if corpus.get("label_shape") == LABEL_SHAPE:
        for side in ("hit", "pit"):
            for r in corpus.get(side) or []:
                if r.get("mlbam") and r.get("war_total") is not None:
                    out[(r["mlbam"], r["season"])] = r["war_total"]
        return out
    log.warning("war_actual_map: corpus label_shape %s (want %s) - falling back "
                "to summing `war` across sides, which DOUBLES every "
                "player-season carrying a row on both sides",
                corpus.get("label_shape") or "absent", LABEL_SHAPE)
    for side in ("hit", "pit"):
        for r in corpus.get(side) or []:
            if r.get("mlbam") and r.get("war") is not None:
                key = (r["mlbam"], r["season"])
                out[key] = out.get(key, 0.0) + r["war"]
    return out


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


def _woba_scale(season) -> float:
    """The wOBA scale for `season`: SOLVED from the published identity where we
    have it, the config constant otherwise (audit F01-03).

    `fa_config.yaml assembly.woba_scale` was 1.15 for every season from 2000 to
    2026 while the reference says in as many words that the value varies
    year to year to keep wOBA on the league-OBP scale. Measured, 1.15 is 7.2
    percent low against 2026, and the served projected wRC+ was that much too
    wide on 3,205 rows. league_constants solves it exactly from MLB's own
    sabermetrics feed (r = 1.0 to eight places); the config value remains the
    fallback for seasons the feed does not cover, so an absent artifact degrades
    to the old behaviour rather than to a crash."""
    cfg = float(_pcfg()["assembly"]["woba_scale"])
    try:
        import league_constants as _lc
        v = _lc.woba_scale(int(season), default=cfg)
        return float(v) if v else cfg
    except Exception:   # noqa: BLE001 - a missing artifact must not break a fit
        return cfg


def _corpus_sig(corpus: dict) -> str:
    """Eight hex chars identifying the corpus CONTENT.

    THE STALENESS THIS CLOSES (plan item F1.5). The fits cache was keyed on
    (max_season, corpus.first, corpus.last) and nothing else, so it carried no
    information about the ROWS. Baseball-Reference revises bWAR, signings get
    added to a winter already in range, and identity repairs move players
    between rows. Every one of those changes the fit and none of them changes
    the key, so the cache kept serving the previous vintage and the only symptom
    was numbers that quietly refused to move.

    Cheap enough to be unconditional: a full refit measures 0.5s against a 0.01s
    cached read, so invalidating on real change costs almost nothing, and a
    stale WAR map costs a wrong price on every free agent.

    MEMOISED ONTO THE CORPUS. fa_backtest calls fitted_models once per target
    year over one corpus, so without this the digest would be recomputed over
    36k rows a dozen times per gate run. The key is underscore-prefixed and
    never serialised."""
    cached = corpus.get("_sig")
    if cached:
        return cached
    import hashlib
    h = hashlib.md5()
    for side in ("hit", "pit"):
        rows = corpus.get(side) or []
        h.update(f"{side}:{len(rows)}|".encode())
        # Digest the fields the fit actually consumes. Hashing whole dicts would
        # make the key depend on incidental columns and on dict ordering, so it
        # would churn for changes that cannot move a coefficient. `war_total` is
        # deliberately absent for that reason: it is the LABEL column and no fit
        # keyed here reads it. What DOES key on it is proj_ml._war_tag, through
        # the corpus-level label_shape stamp.
        for r in rows:
            h.update(f"{r.get('mlbam')},{r.get('season')},{r.get('war')},"
                     f"{r.get('pa') or r.get('ip')}|".encode())
    lg = corpus.get("league") or {}
    h.update(repr(sorted(lg.items()))[:4000].encode())
    # THE SCALE IS AN INPUT TO THE FIT, so it belongs in the key (audit F01-03).
    # The WAR map is fitted on wraa_pa and scored on wraa_pa, so it is invariant
    # to the scale ONLY when both sides see the same one. Without this line a
    # changed scale would load a fit built on the old constant and score it with
    # the new one, which moves WAR rather than leaving it alone.
    try:
        seasons = sorted({r.get("season") for side in ("hit", "pit")
                          for r in (corpus.get(side) or []) if r.get("season")})
        h.update(repr([(y, _woba_scale(y)) for y in seasons])[:4000].encode())
    except Exception:   # noqa: BLE001 - a key that cannot be built must not fit
        h.update(b"woba_scale:unavailable")
    sig = h.hexdigest()[:8]
    corpus["_sig"] = sig
    return sig


def fitted_models(corpus: dict, max_season: int, use_cache: bool = True,
                  *, use_def: bool | None = None) -> tuple[dict, dict]:
    """(curves, war_map) fitted on seasons <= max_season, disk-cached per
    max_season — Gate 2 and the live market model reuse Gate 1's twelve
    point-in-time fits instead of recomputing them (load-time ask)."""
    # Key on corpus['last'] too (mirrors proj_ml's frame-cache key): a corpus
    # refresh strictly advances 'last' (annual rollover + the in-progress season
    # going partial->full + bWAR revisions), so omitting it served the PREVIOUS
    # vintage's stale aging curves + WAR map from disk forever (2026-07-19 fix).
    # F-DEF changes the hitter map's COLUMN SET, and the key above carries
    # nothing about model settings, so without this suffix an A/B of the arm
    # would silently read the other arm's map off disk. Off = the historical
    # filename, so no existing cache is invalidated.
    # `use_def` is a CALL-SCOPED override. run_monthly builds /fa/ and
    # /projections/ in ONE process, so a module-level flip would contaminate
    # whichever ran second. The cache key already carries the arm in its
    # suffix, so the two fits coexist on disk.
    _use_def = _def_enabled() if use_def is None else bool(use_def)
    _suffix = "_def" if _use_def else ""
    # No WAR-provider tag needed here: _corpus_sig digests every row's `war`,
    # so the eWAR epoch (pitcher labels move) re-keys this cache on its own.
    cache = (CACHE_DIR /
             f"fa_fits_{max_season}_{corpus['first']}_{corpus['last']}"
             f"_{_corpus_sig(corpus)}{_suffix}.pkl")
    if use_cache and cache.exists():
        with open(cache, "rb") as fh:
            return pickle.load(fh)
    curves = fit_aging_curves(corpus, max_season=max_season, write=False)
    war_map = fit_war_map(corpus, max_season=max_season, use_def=_use_def)
    # P-FITCACHE: use_cache=False must not WRITE either. The cache key is
    # (max_season, corpus.first, corpus.last) and carries nothing about the
    # ROWS, so a caller that passes a modified corpus - a bootstrap resample, a
    # league-variant arm, an ablation - was silently overwriting the production
    # fits for every other consumer, and the next reader picked them up. That is
    # how a measurement harness can corrupt the served model. proj_ml's frame
    # cache already guards its write the same way (proj_ml.py `if use_cache`).
    if use_cache:
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
    cached. NaN expected-stats cells are dropped: pybaseball returns NaN
    for absent est_slg/est_ba and float(nan) does NOT raise, so an
    unguarded subtraction would store NaN and poison _blend_iso (and any
    other consumer) for that player-season; a missing entry instead falls
    through to the raw season line, the intended no-op. Empty dict when
    the fetch fails — the blend simply no-ops. (Cache ``v`` bumped to 2 to
    discard any NaN-contaminated cache written before this guard.)"""
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
        if cached.get("last", 0) >= last - 1 and cached.get("v") == 2:
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
                    pid, yr = int(row.player_id), int(row.year)
                    xiso = float(row.est_slg) - float(row.est_ba)
                except (TypeError, ValueError):
                    continue
                if xiso == xiso:                  # drop NaN (float(nan) doesn't raise)
                    data[(pid, yr)] = xiso
    except Exception as e:                                 # noqa: BLE001
        log.warning("xstats unavailable (%s) — statcast blend no-ops", e)
    CACHE_DIR.mkdir(exist_ok=True)
    with open(_XSTATS_CACHE, "wb") as fh:
        pickle.dump({"last": last, "v": 2, "data": data}, fh)
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


# ============================================================================
# W1 PT-RISK: injury-history playing-time adjustment (gated, DEFAULT OFF)
# ============================================================================
# Registered 2026-07-23 (docs/wills-2026-07-23/GATES.md section W1). Env flag
# EEPHUS_PT_RISK ("1" = on) is read at CALL time; with the flag unset the
# projection path is byte-identical to the pre-hook engine. The sidecar
# data/pt_risk_adjust.json carries per-side frozen ridge blocks (coef, mu,
# sigma on the FROZEN feature list, fit by tools/pt_risk_lab.py) plus the
# per-player IL season table reconstructed from the league transactions log.
# Uncovered rows (no mlbam, no age, target season before the transactions
# substrate, side not enabled, sidecar absent) no-op exactly.

PT_RISK_DEFAULT = False                     # central flip lives here
_PT_RISK_PATH = Path(__file__).parent / "data" / "pt_risk_adjust.json"
PT_RISK_FEATURES = ("il_days_prior1", "il_stints_prior1", "career_il_days",
                    "career_il_stints", "age", "age_x_il_days_prior1")
PT_RISK_CLAMP = {"hit": 150.0, "pit": 60.0}  # a-priori bounds: PA / IP-equiv
PT_RISK_MIN_FEATURE_SEASON = 2016            # transactions substrate floor
_pt_risk_state: dict | None = None
_pt_risk_loaded = False


def _pt_risk_enabled() -> bool:
    env = os.environ.get("EEPHUS_PT_RISK")
    if env is not None:
        return env.strip() == "1"
    return PT_RISK_DEFAULT


def _pt_risk_load() -> dict | None:
    """Sidecar loader (memoized). Absent/corrupt sidecar -> None -> no-op."""
    global _pt_risk_state, _pt_risk_loaded
    if _pt_risk_loaded:
        return _pt_risk_state
    _pt_risk_loaded = True
    try:
        raw = json.loads(_PT_RISK_PATH.read_text(encoding="utf-8"))
        il = {int(p): {int(y): (float(v[0]), int(v[1])) for y, v in yrs.items()}
              for p, yrs in (raw.get("il") or {}).items()}
        _pt_risk_state = {"hit": raw.get("hit"), "pit": raw.get("pit"), "il": il}
    except (OSError, ValueError, TypeError, AttributeError):
        _pt_risk_state = None
    return _pt_risk_state


def pt_risk_features(il_seasons: dict, target_season: int, age: int) -> list[float]:
    """FROZEN feature vector (order = PT_RISK_FEATURES) from completed-season
    IL history STRICTLY before target_season. il_seasons maps
    season -> (il_days, il_stints)."""
    d1, s1 = il_seasons.get(target_season - 1, (0.0, 0))
    cd = cs = 0.0
    for s, (d, n) in il_seasons.items():
        if s < target_season:
            cd += d
            cs += n
    return [float(d1), float(s1), cd, cs, float(age), float(age) * float(d1)]


def pt_risk_apply(block: dict, feats: list[float]) -> float:
    """Standardize with the block's frozen mu/sigma, dot the ridge coef (no
    intercept: the adjustment is mean-zero over the fit population, a pure
    redistribution), clamp at the a-priori bound stored in the block."""
    z = [(f - m) / s if s > 1e-9 else 0.0
         for f, m, s in zip(feats, block["mu"], block["sigma"])]
    adj = sum(c * v for c, v in zip(block["coef"], z))
    cap = float(block["clamp"])
    return max(-cap, min(cap, adj))


def _pt_risk_adjustment(mlbam, side: str, target_season: int, age) -> float | None:
    """Clamped PT adjustment (PA for hitters, IP-equivalent for pitchers) or
    None when the row is uncovered."""
    if not mlbam or not age or target_season - 1 < PT_RISK_MIN_FEATURE_SEASON:
        return None
    state = _pt_risk_load()
    if not state:
        return None
    block = state.get(side)
    if not block or not block.get("enabled"):
        return None
    feats = pt_risk_features(state["il"].get(int(mlbam)) or {}, target_season, age)
    return pt_risk_apply(block, feats)


# ============================================================================
# P-IPAGE: pitcher ip_proj follows the AGED BF exposure (gated arm)
# ============================================================================
# SHIPPED 2026-07-24 after the paired-bootstrap gate below. Dev (7 forward-
# chained bases 2014-2021 ex-2020, 135 draws, refit per draw): pitcher h1 MAE
# 0.5565 -> 0.5295, paired delta -0.0224 CI95 [-0.0302, -0.0134], P(improve)
# 1.000, against a permuted-age placebo of -0.0032 (7x) and a noise floor
# (1.96 sd) of 0.0079; pitcher h1 bias +0.0529 -> +0.0056. TOUCHED-ONCE HOLDOUT
# (bases 2022-2024, 45 draws): pitcher h1 -0.0305, CI95 [-0.0375, -0.0233],
# P 1.000, bias +0.0477 -> -0.0007; pitcher all-horizon -0.0124 CI95
# [-0.0181, -0.0053]. Out-year (h3-h5) MAE moves +0.005 to +0.009 with CIs
# straddling zero - NULL, disclosed - while the LEVEL bias improves at every
# horizon (h5 pit -0.0855 -> -0.0702).
PIT_IP_AGE_DEFAULT = True                   # central flip lives here


def _pit_ip_age_enabled() -> bool:
    env = os.environ.get("EEPHUS_PIT_IP_AGE")
    if env is not None:
        return env.strip() == "1"
    return PIT_IP_AGE_DEFAULT


# ============================================================================
# P-TJPT: pitcher playing time discounted for a RECENT Tommy John surgery
# ============================================================================
# Registered 2026-07-24 (FA lane). Env flag EEPHUS_PT_TJ ("1"/"0") is read at
# CALL time and overrides the default either way; set it to "0" for a
# byte-identical pre-hook projection path.
#
# DEFAULT ON as of 2026-07-25, OWNER-DIRECTED ("implement whatever makes the
# models as accurate as possible"). It shipped OFF only because the blast
# radius (every pitcher projection on the site: FA, /projections/, /fantasy/,
# the leaderboards) was wider than the originating lane owned, NOT because the
# evidence was weak -- see the corrected control block below, where the coded
# arm clears its zero-information band by 8.39x on 11/12 forward-chained folds.
# GOLDEN RESTAMP OWED: ~11 pitchers per season league-wide get pt_proj and
# ip_proj multiplied by PT_TJ_MULT (215 fires across 20 seasons, 135 inside the
# 12 scored folds), which reaches war_from_projection and every surface above.
#
# WHY: playing time is currently a two-season exposure Marcel plus an age
# delta and nothing else -- durability is not a variable anywhere in the
# stack, and data/tj_surgery.json had ZERO consumers in it.
#
# DESIGN THAT DOES NOT CONDITION ON SURVIVAL (the trap the standing ledger
# flags for this source): every pitcher with >= 100 BF in season t-1 is
# projected for t, and a pitcher who never appears in t scores actual BF = 0.
# Attrition is IN the label, so the estimate is not a returnee-only read.
# tj_surgery.tj_features counts only surgeries STRICTLY BEFORE the target
# year, so the feature is ex-ante at every fold.
#
# MEASURED (tools/_fa_tj_gate.py, tools/_fa_tj_war.py; n = 9,505 pitcher
# seasons 2006-2025, 5,839 scored over 12 forward-chained folds 2014-2025):
#   descriptive, as-of bucket        n     survive   actualBF / projectedBF
#     no TJ                        7188      0.859        0.721
#     TJ, last surgery  <24 months  215      0.521        0.477  (median 0.030)
#     TJ, 24-48 months              508      0.852        0.790
#     TJ, 48-96 months              955      0.857        0.735
#     TJ, 96+ months                639      0.806        0.673
#   The whole effect is RECENCY, not "ever": "TJ ever" is 0.706 vs 0.721.
#
#   arm (multiplier fit ex-ante on strictly prior seasons, lt24 only):
#     playing-time MAE (BF)  170.702 -> 169.039  (-1.663), 11/12 folds better
#     pitcher WAR MAE         0.8876 ->  0.8825  (-0.0051), 10/12 folds better
#   controls FOR THE CODED ARM (lt24 only -- this is what the flag turns on;
#   tools/_src_out/tj_lt24_confirm.log, independent re-measurement 2026-07-25):
#     paired bootstrap, resample the pool by season + refit every draw
#       PT  pooled delta -1.6375 CI95 [-2.4416, -0.8515] P(improves) 1.000
#       PT  TJ slice   -70.6638 CI95 [-106.10, -38.51]   P(improves) 1.000
#     zero-information control (bucket labels row-permuted within season)
#       PT  pooled   null95 [-0.1458, +0.1889] max|d| 0.1983
#       PT  TJ slice null95 [-6.3056, +8.1714] max|d| 8.5773
#     -> SNR 8.39x on both, 11/12 forward-chained folds better.
#
#   CORRECTED 2026-07-25. This block previously quoted the ALL-BUCKET control
#   band (pooled max|d| 1.3460) and concluded "clears comfortably, 1.36x" --
#   but the all-bucket arm is NOT the one the flag codes. Permuting five bucket
#   labels admits far more null excursion than permuting one, so borrowing its
#   band UNDERSTATED the coded arm's signal-to-noise by ~6x (1.36x vs 8.39x)
#   and made a decisive result read as marginal. The all-bucket numbers, kept
#   for the record: PT pooled -1.7284 CI95 [-2.9559, -0.3914], TJ slice
#   -6.0317 CI95 [-10.411, -1.3482], null95 max|d| 1.3460 / 4.7006.
#   Match the control to the arm you actually ship.
#
#   WAR follow-on (all-bucket form, measured under P-IPAGE ON): pooled -0.0051
#   CI95 [-0.0085, -0.0017] P 1.000 against null95 max|d| 0.0040 (1.28x); TJ
#   slice -0.0178 CI95 [-0.0300, -0.0059] against max|d| 0.0139. Read PT as the
#   result and WAR as a consistent-sign follow-on, not a second independent win.
#
#   MARKET-SIDE COMPANION RESULT (NULL, ledgered): the same TJ features added
#   to fa_market's log-guarantee stage are a measured null -- Gate-2 pooled
#   guarantee MAE delta +0.0094, sd 0.0357, CI95 [-0.0487, +0.0914],
#   P(improves) 0.390, against its own row-permuted zero-information control
#   at +0.0003 sd 0.0389. The mechanism is visible in the corpus: the 65 FA
#   pitcher signings with a TJ inside 24 months already carry a median
#   projected WAR of 0.35 vs 0.62 for the no-TJ group and a median guarantee
#   of $2.0M vs $5.0M, so the durability information is ALREADY in war_y1 by
#   the time the market stage sees it. Durability belongs in the projection,
#   not in the price.
#
# The multiplier is applied to BOTH pt_proj (BF) and ip_proj so it reaches
# war_from_projection regardless of the P-IPAGE flag's state.
PT_TJ_DEFAULT = True                        # central flip lives here
PT_TJ_RECENT_MONTHS = 24
PT_TJ_MULT = 0.606                          # fit on 2006-2025, shrunk k=30


def _pt_tj_enabled() -> bool:
    env = os.environ.get("EEPHUS_PT_TJ")
    if env is not None:
        return env.strip() == "1"
    return PT_TJ_DEFAULT


def pt_tj_multiplier(mlbam, target_season: int) -> float:
    """Exposure multiplier for a pitcher whose most recent Tommy John
    surgery is inside PT_TJ_RECENT_MONTHS of the target season. 1.0 for
    everyone else, and 1.0 fail-soft when the ledger is unavailable."""
    if not mlbam:
        return 1.0
    try:
        import tj_surgery
        f = tj_surgery.tj_features(mlbam, str(target_season))
    except Exception:                                  # noqa: BLE001 -- fail-soft
        return 1.0
    mo = f.get("months_since_last_tj_pre")
    if f.get("tj_pre") and mo is not None and mo < PT_TJ_RECENT_MONTHS:
        return PT_TJ_MULT
    return 1.0


# ============================================================================
# F-REALWAR: realized-bWAR RESIDUAL channel in the WAR reconstruction (gated)
# ============================================================================
# Registered 2026-07-30 (FA lane, master plan Phase E2). Env flag
# EEPHUS_FA_REALWAR ("1"/"0") is read at CALL time and overrides the default
# either way; "0" gives a byte-identical pre-hook path. Criteria are
# pre-registered in docs/efv-2026-07-30/FA_LANE_GATES.md section E2.
#
# WHY. war_from_projection's only positional term is a catcher dummy
# (fit_war_map, documented as a v1 simplification in this module's docstring:
# "defense/baserunning are not separately projected - the fitted WAR map + the
# uncertainty bands absorb them"). Its target is bWAR, which INCLUDES defense
# and positional value, so a persistently good defender at a premium position
# is persistently ABOVE the map and the map cannot say so. E1 measured the
# consequence on the forward-chained Gate-1 panel: for the 424 hitter-seasons
# that actually produced >= 4 bWAR the map predicts a mean 2.34 against 5.56
# actual, and the naive 5/4/3 carry-forward baseline beats the model outright
# in that cell (MAE 2.37 vs 3.23) - the star tail is where the model LOSES.
#
# WHAT THIS IS NOT. The owner's instinct ("use the 3-year WAR") in its literal
# form - blend map-WAR with a realized-WAR rate - DOUBLE COUNTS: realized WAR
# contains the same offensive rate signal that already flows through the map's
# wRAA term. What is added here is the RESIDUAL rate: for each of the player's
# up-to-three prior seasons, the map's OWN prediction for that season is
# reconstructed from the map's own features and subtracted from realized bWAR.
# Because the map is a pooled least-squares fit, that residual is orthogonal to
# its features by construction on average, so the channel can only carry what
# the map does not represent. Any PLAYER-LEVEL persistence in it is defense,
# baserunning and positional value.
#
# CAVEATS, stated up front: realized bWAR is noisier than a rate and it is
# survivor-tinged (a season only exists if the player played it). Both are
# handled by shrinking on effective exposure rather than by trusting the
# residual, and by capping it a priori.
#
# SHIPPED 2026-07-30, DEFAULT ON. Gate 1, 10 forward-chained targets 2015-2025
# ex-2020, n=20,721, paired on the folds (data/fa_projection_lab_eval.json):
#   pooled WAR MAE  0.61572 -> 0.60087, delta -0.01496,
#                   CI95 [-0.01814, -0.01178], MDE95 0.00270, 10/10 folds
#   hitters         0.75957 -> 0.72509   pitchers 0.50884 -> 0.50857
#   wRC+ / FIP      byte-identical (the channel touches only the WAR map)
#   coverage        0.79919 -> 0.79890 (band 0.75-0.85), hard gates stay True
#   >=4-bWAR hitter cell: mean predicted 2.336 -> 2.658 against 5.556 actual,
#                   cell MAE 3.235 -> 2.922. STILL WORSE than the naive
#                   5/4/3 carry-forward there (2.373): the star tail remains
#                   this engine's weakest region and this arm narrows the gap
#                   without closing it. Disclosed, not hidden.
# ZERO-INFORMATION CONTROL: the same residual column PERMUTED across players
# within each target season (identical marginal distribution, identical shrink,
# no player linkage) moves pooled WAR MAE by +0.01379 - it DEGRADES the model on
# 0 of 10 folds while the candidate improves on 10 of 10. The information is
# player-specific. NOTE the pre-registered clause was written in the
# |delta_candidate| >= 3*|delta_control| magnitude form, which assumes a control
# that could accidentally help; that literal form reads False here purely
# because the control's delta has the OPPOSITE SIGN. Both readings are recorded
# in the artifact (`control_literal_3x_form`) and the discrepancy is written up
# in docs/efv-2026-07-30/FA_LANE_GATES.md rather than quietly resolved.
# SENSITIVITY on the shrink constant (reported, not shopped - the primary values
# below were fixed a priori): K x0.5 -> -0.01533, K x1.0 -> -0.01496,
# K x2.0 -> -0.01135. Monotone, no cliff, and the primary sits on the plateau.
# GOLDEN RESTAMP OWED: this reaches war_from_projection, so every surface built
# on it moves - /fa/ prices, /projections/ vets/prospects/team_outlook,
# fa_fit's contracted-roster projections, and data/fa_class.json.
REALWAR_DEFAULT = True                      # central flip lives here
# Stabilization for the residual rate, in effective PA (hitters) / IP
# (pitchers).
#
# HITTER K 1200 -> 600, 2026-07-31. The 1200 was chosen a priori (~2 full
# seasons) and never swept; the ship note above already flagged that 0.5x
# scored better. Swept properly on Gate 1 (10 forward-chained targets, n=20,721,
# persist=False), pooled WAR MAE by K_hit:
#     150 0.58302 | 300 0.58062 | 600 0.58065 | 900 0.58185
#    1200 0.58318 (shipped) | 1800 0.58539 | 2400 0.58706
# The optimum is a PLATEAU over 300-900, every point of which beats 1200, and
# 600 = one full season of PA is the a-priori anchor inside it. Paired on the
# identical rows: dMAE -0.00253, CI95 [-0.00323, -0.00176], P(better) 1.000;
# signed bias -0.0770 -> -0.0732. The >=4-bWAR hitter cell moves 3.1285 ->
# 3.0196 MAE with bias -3.1122 -> -2.9968 - the star tail was paying most of
# the over-shrink. Pitcher K left at 400: its own sweep (100/200/400/800) moves
# pooled MAE by 0.0006 and the pitcher star cell gets WORSE as K rises.
REALWAR_K = {"hit": 600.0, "pit": 400.0}
# A-priori bound on the residual rate (WAR per 600 PA / per 100 IP). +-2.5 is
# about the full observed range of season defensive value; it stops a 50-PA
# fluke from moving a projection.
REALWAR_CAP = {"hit": 2.5, "pit": 2.5}
# Lab hooks for the pre-registered ZERO-INFORMATION CONTROL. COLLECT records
# (id, target_season, rate, n_eff) per scored row; OVERRIDE replaces the
# computed rate with a value the lab supplies, which is how the permuted-column
# control is run without duplicating the gate loop. Both are None in
# production and neither is read when the arm is off.
REALWAR_COLLECT: list | None = None
REALWAR_OVERRIDE: dict | None = None


def _realwar_enabled() -> bool:
    env = os.environ.get("EEPHUS_FA_REALWAR")
    if env is not None:
        return env.strip() == "1"
    return REALWAR_DEFAULT


# ============================================================================
# F-DEF: OBSERVED defense as a real feature of the hitter WAR map (gated arm)
# ============================================================================
# The hitter map's only positional term is a catcher dummy, so every non-catcher
# is priced as if his glove and his position were league average. F-REALWAR
# carries the consequence indirectly - it infers "whatever the map missed" from
# realized bWAR, which is a NOISY read of a defensive signal that is published
# directly. data/mlb_def_history.json carries bWAR's OWN war_def (fielding runs)
# and runs_position (the positional adjustment) per player-season, in the same
# currency as the target, back to 2000. This arm feeds their sum, per 600 PA and
# point-in-time (prior seasons only, Marcel-weighted, shrunk on PA), into
# fit_war_map as a fourth hitter column so the coefficient is FITTED rather than
# assumed - the map then knows a premium-position plus glove is worth real WAR.
#
# Env flag EEPHUS_FA_DEF ("1"/"0") read at call time; "0" is byte-identical to
# the pre-hook path.
#
# SHIPPED 2026-07-31, DEFAULT ON. Gate 1, 10 forward-chained targets, n=20,721,
# paired on the identical rows AT FIXED REALWAR_K=600 so the two changes in this
# lane are measured separately:
#   pooled WAR MAE  0.58065 -> 0.57357  dMAE -0.00708 CI95 [-0.00863, -0.00559]
#   hitters         0.67767 -> 0.66105     pitchers byte-identical (hitter-only column)
#   wRC+ / FIP      byte-identical (the column touches only the WAR map)
#   coverage        0.79745 -> 0.79750 (band 0.75-0.85), all four gates stay True
#   >=4-bWAR hitter cell: MAE 3.0196 -> 2.9623, bias -2.9968 -> -2.9332,
#                   mean predicted 2.491 -> 2.622 against 5.556 actual. Still
#                   short of the naive 5/4/3 carry-forward (2.373) in that cell.
# ZERO-INFORMATION CONTROL (the one that matters here): re-key the feature to a
# DIFFERENT player with a record in the same season - identical marginal
# distribution, identical exposure profile, no player linkage. Two seeds:
# dMAE +0.00011 CI95 [-0.00005, +0.00027] and -0.00002 CI95 [-0.00006, +0.00002].
# The entire gain is player-specific.
# WHAT THE FIT ITSELF SAYS: the fitted coefficient is 0.2652 on a rate that
# carries a mean shrink of ~0.4, i.e. ~0.106 WAR per run on the unshrunk rate -
# the fit recovers 1/RPW from the data without being told it. And the catcher
# dummy collapses from +0.6217 to -0.1539, because the positional value it was
# standing in for now flows through the real column.
# GOLDEN RESTAMP OWED: this reaches war_from_projection, so every surface built
# on it moves, exactly as F-REALWAR did.
DEF_FEATURE_DEFAULT = True
# Shrink in PA. A-priori (~2 full seasons), NOT swept for the ship decision;
# reported sensitivity is flat: pooled WAR MAE 0.57430 / 0.57379 / 0.57357 /
# 0.57352 at DEF_K 300 / 600 / 1200 / 2400.
DEF_K = 1200.0
# A-priori bound in runs per 600 PA. +-20 is wider than any qualified season's
# combined fielding + positional runs; it only stops a 30-PA sample exploding.
DEF_CAP = 20.0

_DEF_HIST: dict | None = None


def _def_hist() -> dict:
    """{(mlbam, season): (defensive+positional runs, pa)} from bWAR's own
    war_daily split. Empty dict (arm no-ops) when the feed is absent."""
    global _DEF_HIST
    if _DEF_HIST is not None:
        return _DEF_HIST
    out: dict = {}
    try:
        raw = json.loads((Path(__file__).parent / "data" / "mlb_def_history.json")
                         .read_text(encoding="utf-8"))["rows"]
    except (OSError, ValueError, KeyError):
        log.warning("F-DEF: data/mlb_def_history.json unavailable; arm no-ops")
        _DEF_HIST = out
        return out
    for k, v in raw.items():
        try:
            mid, season = k.split(":")
            out[(int(mid), int(season))] = (
                _f(v.get("war_def")) + _f(v.get("runs_position")), _f(v.get("pa")))
        except (ValueError, AttributeError, TypeError):
            continue
    _DEF_HIST = out
    return out


# Lab hook for the ZERO-INFORMATION CONTROL: set to an int and every lookup is
# re-keyed to a different player who has a record in the same season, which
# preserves the feature's marginal distribution and its exposure profile while
# destroying the player linkage. None in production.
DEF_PERMUTE_SEED: int | None = None
_DEF_PERM: dict | None = None


def _def_enabled() -> bool:
    env = os.environ.get("EEPHUS_FA_DEF")
    if env is not None:
        return env.strip() == "1"
    return DEF_FEATURE_DEFAULT


def _def_perm() -> dict:
    """{(mlbam, season): substitute mlbam} - a within-season derangement."""
    global _DEF_PERM
    if _DEF_PERM is not None:
        return _DEF_PERM
    import random as _random
    by_season: dict[int, list[int]] = defaultdict(list)
    for (mid, season) in _def_hist():
        by_season[season].append(mid)
    rng = _random.Random(DEF_PERMUTE_SEED)
    out: dict = {}
    for season, ids in by_season.items():
        ids = sorted(ids)
        shuffled = ids[:]
        rng.shuffle(shuffled)
        for a, b in zip(ids, shuffled):
            out[(a, season)] = b
    _DEF_PERM = out
    return out


def def_rate(mlbam, season: int) -> float:
    """Shrunk prior-seasons defensive+positional runs per 600 PA, point in
    time: only seasons strictly before ``season`` are read, on the same
    5/3/2 recency weights the component rates use."""
    if not mlbam:
        return 0.0
    hist = _def_hist()
    if not hist:
        return 0.0
    w = _marcel_weights()
    num = den = 0.0
    for lag in (1, 2, 3):
        _mid = int(mlbam)
        if DEF_PERMUTE_SEED is not None:
            _mid = _def_perm().get((_mid, int(season) - lag), _mid)
        rec = hist.get((_mid, int(season) - lag))
        if not rec or rec[1] <= 0:
            continue
        wl = float(w[lag - 1]) / float(w[0])
        num += wl * rec[1] * (rec[0] / (rec[1] / 600.0))
        den += wl * rec[1]
    if den <= 0:
        return 0.0
    rate = max(-DEF_CAP, min(DEF_CAP, num / den))
    return rate * (den / (den + DEF_K))


# ============================================================================
# F-PTFIT: playing-time coefficients FITTED, plus an established-workload
# channel (gated arm; master plan Phase E3)
# ============================================================================
# Registered 2026-07-30. Env flag EEPHUS_FA_PTFIT in {"off","hit","both"},
# read at CALL time; "off" is byte-identical to the shipped path.
#
# THE DEFECT. The shipped PT model is a hand-set two-season Marcel
# (fa_config.yaml playing_time: hitters 0.5*PA1 + 0.1*PA2 + 200), which cannot
# reach 700 PA at any input and which measured a mean projPA of 456 against 511
# actual. It also has no way to tell "395 PA of decline" from "395 PA because
# he missed six weeks".
#
# THE ARM. Refit the same linear form by least squares AND add the
# established-workload channel the plan asks for:
#   expo_t ~ b0 + b1*expo_{t-1} + b2*expo_{t-2} + b3*max(0, max3 - expo_{t-1})
# The b3 term is the bounce-back: how much of a drop below the player's own
# three-season peak comes back next season. Pitchers are fit PER ROLE because
# the shipped model already has a role-dependent intercept and SP/RP innings
# distributions do not share one.
#
# NO LOOKAHEAD. Coefficients are fit on corpus seasons <= 2014, STRICTLY before
# Gate 1's first scored target (2015), so a single fixed vector is ex-ante for
# every one of the ten folds and no per-fold cache surgery is needed. The
# full-corpus fit is reported beside it as a stability check; the two agree to
# ~0.04 on b1 and disagree only on b3, which the <=2014 fit sets LOWER (the
# conservative direction).
#
# WHAT THE FIT SAYS, and it is not what the plan expected: on the corpus the
# refit LOWERS the hitter ceiling (579 PA at 700/700 inputs, vs the shipped
# form's 620). It moves weight onto the most recent season (b1 0.71 vs 0.50),
# empties the second (b2 ~0), and cuts the intercept (90 vs 200). Fitted PT MAE
# on the <=2014 population: hitters 127.4 vs the shipped form's 143.0 (a real
# gain); SP 48.7 vs 48.3 (the shipped form is already BETTER); RP 21.4 vs 22.3.
# So the hitter arm and the pitcher arm are separate questions and are gated
# separately ("hit" vs "both"). The 620-ceiling complaint is about a
# CONDITIONAL population (established regulars); a linear refit on the whole
# corpus answers it by lowering the ceiling, which is information.
#
# SHIPPED 2026-07-30 at mode "hit" (data/fa_projection_lab_eval.json):
#   pooled WAR MAE  0.61572 -> 0.59684, delta -0.01889,
#                   CI95 [-0.02399, -0.01378], MDE95 0.00434, 10/10 folds
#   hitters         0.75957 -> 0.71526   pitchers unchanged by construction
#   wRC+ / FIP      byte-identical; coverage 0.7978; hard gates stay True
#   projected PA    mean 364.0 -> 299.1 against 312.7 actual: the level error
#                   falls from +51.3 to -13.6. The SHIPPED model was
#                   OVER-projecting exposure on the gate panel, the opposite
#                   sign to the FA-class measurement (456 vs 511) that motivated
#                   this arm, and both are true: intercept 200 inflates
#                   part-timers while slope 0.50 deflates regulars. The refit
#                   (intercept 90, slope 0.71) corrects both ends at once, which
#                   is why the WAR gain is this large.
#   "both" (pitchers too) FAILED its pre-registered not-worse clause on pooled
#                   FIP MAE and is NOT shipped - consistent with the offline
#                   finding that the shipped hand-set form already beats the
#                   refit on SP innings (48.3 vs 48.7 MAE).
# P3' GUARD (pre-registered): the in-progress reliability blend - the Lindor
# protection at the top of project_player - must stay a FLOOR. Direct assertion
# on the real path over every hitter with >=600 established PA and a partial
# following season: 6 cases, 0 regressed, mean pt lift +132.8 PA. Intact.
# COMBINED with F-REALWAR (the pre-registered combined-winner rule): pooled WAR
# MAE 0.61572 -> 0.58318, delta -0.03263, CI95 [-0.03884, -0.02643],
# MDE95 0.00527, 10/10 folds; hitters 0.75957 -> 0.68360 (delta -0.07573,
# MDE95 0.01074), pitchers -0.00039 (a null, as expected).
PT_FIT_DEFAULT = "hit"                      # central flip lives here
PT_FIT_COEF = {                             # OLS on corpus seasons <= 2014
    "hit": [90.4588, 0.7112, -0.0131, 0.1563],      # n=6,953
    "pit_SP": [73.2245, 0.4724, 0.0211, -0.0005],   # n=2,523
    "pit_RP": [26.3709, 0.3594, -0.0017, 0.0157],   # n=4,089
}


def _pt_fit_mode() -> str:
    env = os.environ.get("EEPHUS_FA_PTFIT")
    return env.strip() if env is not None else PT_FIT_DEFAULT


# ============================================================================
# F-MARCEL: the [5,3,2] vs 5/4/3 doc/config mismatch (gated arm; Phase E4a)
# ============================================================================
# fa_config.yaml ships marcel_weights [5,3,2]; this module's own docstring and
# fa_backtest's naive baseline both say 5/4/3. One of them is wrong and the
# question is decided by measurement, not by editing whichever is easier.
# EEPHUS_FA_MARCEL="5,4,3" overrides the config at call time.
#
# RESOLVED 2026-07-30 BY MEASUREMENT, and the CONFIG won. Gate 1, identical
# folds (data/fa_projection_lab_eval.json arm `marcel_543`): moving to [5,4,3]
# makes pooled WAR MAE WORSE, 0.61572 -> 0.61911, delta +0.00339, CI95
# [+0.00285, +0.00393], MDE95 0.00046, and it loses on 10 of 10 folds while
# also degrading pitcher WAR (0.50884 -> 0.51437), wRC+ (20.070 -> 20.149) and
# FIP (0.72109 -> 0.72434). This is a measured LOSS, not a null, so [5,3,2]
# stands and THIS MODULE'S DOCSTRING was the wrong artifact - it has been
# corrected to [5, 3, 2].
# fa_backtest._baseline keeps 5/4/3 deliberately: it is the NAIVE COMPARATOR
# (the classic Marcel carry-forward the model must beat), a different object
# from the model's own component weights, and its docstring says so.
def _marcel_weights() -> list[float]:
    env = os.environ.get("EEPHUS_FA_MARCEL")
    if env:
        return [float(x) for x in env.split(",")]
    return list(_pcfg()["marcel_weights"])


def _realwar_map_features(h: dict, side: str, league: dict) -> list[float] | None:
    """The WAR map's OWN feature row for a COMPLETED season, built exactly as
    fit_war_map builds it (same exposure floors, same league anchors, same
    wRAA construction). None when the season cannot be reconstructed."""
    lg = league.get(h["season"]) or {}
    if side == "hit":
        pa = h.get("pa") or 0
        if pa < 50 or not lg.get("woba"):
            return None
        woba = _assemble_hitter({**h, "babip": h.get("babip") or lg.get("babip")},
                                league, h["season"] + 1)["woba_proj"]
        wraa_pa = (woba - lg["woba"]) / _woba_scale(h["season"] + 1)
        pa6 = pa / 600.0
        row = [1.0, pa6, wraa_pa * pa6 * 600.0 / 10.0,
               (1.0 if h.get("role") == "C" else 0.0) * pa6]
        if _def_enabled():
            # Must match fit_war_map's column set or the residual reconstruction
            # would subtract a prediction the map never made.
            row.append(def_rate(h.get("mlbam"), h["season"]) * pa6)
        return row
    ip = h.get("ip") or 0
    if ip < 20 or not lg.get("lg_fip") or h.get("fip") is None:
        return None
    ip100 = ip / 100.0
    return [1.0, ip100, (lg["lg_fip"] - h["fip"]) * ip100,
            (1.0 if h.get("role") == "SP" else 0.0) * ip100]


def realwar_residual(proj: dict, side: str, war_map: dict) -> tuple[float, float]:
    """(shrunk residual rate, effective exposure) for one projection.

    Rate units are bWAR per 600 PA (hitters) / per 100 IP (pitchers). The
    per-season residuals are combined with the SAME Marcel recency weights the
    component rates use, exposure-weighted, then shrunk on effective exposure
    toward 0 (no signal) rather than toward a league mean - the residual's
    population mean is already ~0 by the map's construction."""
    rows = proj.get("_rw") or []
    if not rows:
        return 0.0, 0.0
    coef = (war_map.get(side) or {}).get("coef")
    if not coef:
        return 0.0, 0.0
    w = _marcel_weights()
    unit = 600.0 if side == "hit" else 100.0
    season0 = proj.get("season") or 0
    num = den = 0.0
    for r in rows:
        lag = season0 - r["s"]
        if not 1 <= lag <= 3 or r["war"] is None or (r["expo"] or 0) <= 0:
            continue
        wl = float(w[lag - 1]) / float(w[0])
        hat = sum(c * x for c, x in zip(coef, r["x"]))
        rate = (r["war"] - hat) / (r["expo"] / unit)
        num += wl * r["expo"] * rate
        den += wl * r["expo"]
    if den <= 0:
        return 0.0, 0.0
    rate = num / den
    if REALWAR_OVERRIDE is not None:            # zero-information control
        rate = float(REALWAR_OVERRIDE.get((proj.get("_rw_id"), season0), 0.0))
    cap = REALWAR_CAP[side]
    rate = max(-cap, min(cap, rate))
    if REALWAR_COLLECT is not None:
        REALWAR_COLLECT.append((proj.get("_rw_id"), season0, rate, den))
    return rate * (den / (den + REALWAR_K[side])), den


def project_player(history: list[dict], side: str, target_season: int,
                   curves: dict, league: dict, age: int | None,
                   role: str | None = None,
                   in_progress: tuple[int, float] | None = None) -> dict | None:
    """Project one player's ``target_season`` from up to three prior
    seasons (the rows must be corpus-shaped). Returns the component dict +
    assembled composites (wRC+/FIP) + playing time — WAR attaches later
    via the fitted map. None when no usable history exists."""
    cfg = _pcfg()
    weights = _marcel_weights()
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
    _ptmode = _pt_fit_mode()

    def _bounce(vals: list[float]) -> float:
        """How far the platform season sits below the player's own 3-season
        peak - the established-workload channel (F-PTFIT)."""
        return max(0.0, max(vals) - vals[0])

    if side == "hit":
        if _ptmode in ("hit", "both"):
            e3 = next((_pt_expo(h, expo_key) for h in hist
                       if h["season"] == target_season - 3), 0)
            b = PT_FIT_COEF["hit"]
            pt = b[0] + b[1] * e1 + b[2] * e2 + b[3] * _bounce([e1, e2, e3])
        else:
            pt = pt_cfg["w1"] * e1 + pt_cfg["w2"] * e2 + pt_cfg["base_pa"]
    else:
        base_ip = pt_cfg["base_ip_sp"] if role == "SP" else pt_cfg["base_ip_rp"]
        ip1 = next((_pt_expo(h, "ip") for h in hist if h["season"] == target_season - 1), 0)
        ip2 = next((_pt_expo(h, "ip") for h in hist if h["season"] == target_season - 2), 0)
        if _ptmode == "both":
            ip3 = next((_pt_expo(h, "ip") for h in hist
                        if h["season"] == target_season - 3), 0)
            b = PT_FIT_COEF["pit_SP" if role == "SP" else "pit_RP"]
            ip = b[0] + b[1] * ip1 + b[2] * ip2 + b[3] * _bounce([ip1, ip2, ip3])
        else:
            ip = pt_cfg["w1"] * ip1 + pt_cfg["w2"] * ip2 + base_ip
        pt = ip * 4.3                                          # BF ≈ 4.3 / IP
        out["ip_proj"] = round(ip, 1)
    if age:
        pt += curve_delta(curves, side, role, "pt", age)
    # W1 PT-RISK (gated, default OFF): injury-history PT adjustment from the
    # frozen-coefficient sidecar. Hitters adjust in PA; pitchers in
    # IP-equivalents (the engine's BF proxy is 4.3 * IP), keeping ip_proj and
    # the pt/ip pairing the FIP algebra below consumes consistent.
    if _pt_risk_enabled():
        _adj = _pt_risk_adjustment(hist[0].get("mlbam"), side, target_season, age)
        if _adj is not None:
            if side == "hit":
                pt += _adj
            else:
                pt += _adj * 4.3
                out["ip_proj"] = round(max(0.0, ip + _adj), 1)
    out["pt_proj"] = max(0.0, round(pt, 1))
    # P-IPAGE (2026-07-24 projections lane): PITCHER PT AGING NEVER REACHED WAR.
    # ip_proj was stamped ABOVE the `pt += curve_delta(...,"pt",age)` line, so the
    # fitted pt curve (which is fit on BF deltas - see fit_aging_curves' expo_key)
    # aged the BF exposure while ip_proj kept the un-aged Marcel value. Downstream:
    #   * war_from_projection reads ONLY ip_proj -> the whole pt decline was discarded
    #   * the FIP algebra below divides the AGED pt by the UN-AGED ip, so an older
    #     pitcher's smaller BF produced a LOWER (better) FIP - backwards
    #   * fm._decay_path's rate = war1/pt_proj*250 paired a war1 built on one exposure
    #     with a different exposure
    # rate_path's own docstring already asserts the invariant this restores
    # ("pt_proj = 4.3 * ip_proj" at year 1). Hitters were never affected (pt_proj
    # feeds PA/600 directly). Env-gated for the paired-bootstrap arm; the flag is
    # read at CALL time so the OFF path is byte-identical to the pre-fix engine.
    if side != "hit" and _pit_ip_age_enabled():
        out["ip_proj"] = round(out["pt_proj"] / 4.3, 1)
    # P-TJPT (gated, default OFF): recent-Tommy-John exposure haircut. Applied
    # to BOTH pt_proj and ip_proj so it reaches war_from_projection whatever
    # state P-IPAGE is in, and applied AFTER P-IPAGE so the two stay paired.
    # See the P-TJPT header for the gate evidence.
    if side != "hit" and _pt_tj_enabled():
        _m = pt_tj_multiplier(hist[0].get("mlbam"), target_season)
        if _m != 1.0:
            out["pt_proj"] = max(0.0, round(out["pt_proj"] * _m, 1))
            out["ip_proj"] = max(0.0, round(out.get("ip_proj", 0.0) * _m, 1))
            out["pt_tj_mult"] = _m
    # F-REALWAR: stash the map's own feature rows for the COMPLETED history
    # seasons so war_from_projection (which owns war_map) can reconstruct the
    # map's prediction for each and take the residual. Only numbers are stored,
    # and only when the arm is on, so the OFF path is byte-identical.
    if _realwar_enabled():
        rw = []
        for h in hist:
            x = _realwar_map_features(h, side, league)
            if x is None:
                continue
            rw.append({"s": h["season"], "war": h.get("war"),
                       "expo": (h.get("pa") if side == "hit" else h.get("ip")) or 0,
                       "x": x})
        out["_rw"] = rw
        out["_rw_id"] = hist[0].get("mlbam")
    # F-DEF: the point-in-time defensive rate the map's fourth hitter column
    # consumes. Computed here (where the history is) rather than in
    # war_from_projection (which only sees the assembled projection).
    if side == "hit" and _def_enabled():
        out["def_rate"] = def_rate(hist[0].get("mlbam"), target_season)
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


def rate_path(proj: dict, side: str, curves: dict, league: dict,
              horizon: int = 5) -> list[dict]:
    """Out-year RATE line for the projections board: walk the year-1
    component projection forward along the SAME per-component aging curves
    the engine already fits, re-assembling the composites each season.

    Season 1 reproduces project_player's own composites exactly (t=0 applies
    no delta; for pitchers the year-1 FIP algebra reduces to the closed form
    below because pt_proj = 4.3 * ip_proj). The league run environment is
    HELD at the year-1 anchor across the horizon — out-year league constants
    don't exist yet, and a moving anchor would put a fake discontinuity
    between the last empirical league season and the fallback defaults.

    DISPLAY machinery only: WAR pricing stays on the war_rate decay path
    (_decay_path); nothing here feeds the WAR map or the valuation stack."""
    if not proj:
        return []
    role = proj.get("role")
    age = proj.get("age")
    season0 = proj.get("season") or 0
    comps = HIT_COMPONENTS if side == "hit" else PIT_COMPONENTS
    cur = {c: proj.get(c) for c in comps}
    if any(v is None for v in cur.values()):
        return []
    # Pitcher FIP core at the engine's fixed BF ≈ 4.3·IP (pt/ip cancels):
    # core = 4.3·(13·hr_bf + 3·(bb_pct + hbp_rate) − 2·k_pct). The engine's
    # own year-1 fip_proj uses the PT-aged pt_proj over the un-aged ip_proj,
    # so it differs from the closed form by a small constant — anchor the
    # path at fip_proj and apply only the aging DELTAS of the core.
    def _fip_core(c):
        return 4.3 * (13 * c["hr_bf"] + 3 * (c["bb_pct"] + 0.008) - 2 * c["k_pct"])
    fip_anchor = proj.get("fip_proj")
    core0 = _fip_core(cur) if side == "pit" else None
    out: list[dict] = []
    for t in range(horizon):
        if t > 0 and age:
            for c in comps:
                cur[c] = max(0.0, cur[c] + curve_delta(curves, side, role, c, age + t))
        if side == "hit":
            snap = dict(proj)
            snap.update(cur)
            asm = _assemble_hitter(snap, league, season0)
            out.append({"season": season0 + t, "woba": asm["woba_proj"],
                        "wrc_plus": asm["wrc_plus_proj"], "avg": asm["avg"]})
        else:
            if fip_anchor is None:
                return []
            fip = fip_anchor + (_fip_core(cur) - core0)
            out.append({"season": season0 + t, "fip": round(max(fip, 1.0), 2)})
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
    wraa_pa = (woba - lg_woba) / _woba_scale(season)
    wrc_plus = ((wraa_pa + lg_rpa) / lg_rpa) * 100 if lg_rpa else None
    return {"avg": round(h / ab, 3) if ab > 0 else None,
            "woba_proj": round(woba, 3),
            "wrc_plus_proj": round(wrc_plus, 1) if wrc_plus is not None else None,
            "wraa_pa": wraa_pa}


# ============================================================================
# WAR map — transparent OLS on the TRAIN corpus (coefficients published)
# ============================================================================

def fit_war_map(corpus: dict, max_season: int, *,
                use_def: bool | None = None) -> dict:
    """Least-squares WAR maps per side, fitted on seasons <= max_season:
      hitters:  WAR ~ b0 + b1·(PA/600) + b2·(wRAA_proxy·PA/600) + b3·C·(PA/600)
      pitchers: WAR ~ b0 + b1·(IP/100) + b2·((lgFIP−FIP)·IP/100) + b3·SP·(IP/100)
    The wRAA proxy is era-adjusted wOBA distance — defense/BsR live in the
    residual (documented v1)."""
    import numpy as np
    league = corpus["league"]
    out: dict = {}
    # Call-scoped so the FIT and the SCORE agree. Scoring without a term the
    # map was fitted WITH is incoherent: the other coefficients absorbed its
    # contribution. Measured 2026-08-06, that mismatch was WORSE than either
    # arm (guarantee 10.385 against 10.207 with it and 9.690 without).
    _def = _def_enabled() if use_def is None else bool(use_def)
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
        wraa_pa = (woba - lg["woba"]) / _woba_scale(r["season"] + 1)
        pa6 = r["pa"] / 600.0
        row = [1.0, pa6, wraa_pa * pa6 * 600.0 / 10.0, (1.0 if r["role"] == "C" else 0.0) * pa6]
        if _def:
            # Point in time: the feature reads only seasons BEFORE this row's.
            row.append(def_rate(r.get("mlbam"), r["season"]) * pa6)
        X.append(row)
        y.append(r["war"])
    bh, *_ = np.linalg.lstsq(np.asarray(X), np.asarray(y), rcond=None)
    _hf = ["1", "PA/600", "wRAA/10", "C×PA/600"]
    out["hit"] = {"coef": [round(c, 4) for c in bh.tolist()],
                  "features": _hf + (["defRuns600×PA/600"] if _def else []),
                  "n": len(y)}
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
        war = (c[0] + c[1] * pa6 + c[2] * wraa10
               + c[3] * (1.0 if proj["role"] == "C" else 0.0) * pa6)
        # F-DEF: the fitted defensive/positional column, at PROJECTED exposure.
        # Guarded on the coefficient count so a war_map pickled under the other
        # setting cannot silently drop or invent a term.
        if len(c) > 4:
            war += c[4] * proj.get("def_rate", 0.0) * pa6
        expo6 = pa6
    else:
        c = war_map["pit"]["coef"]
        lg_fip = _league_recent(league, target_season, "lg_fip") or 4.1
        ip100 = proj.get("ip_proj", 0.0) / 100.0
        war = (c[0] + c[1] * ip100 + c[2] * (lg_fip - proj["fip_proj"]) * ip100
               + c[3] * (1.0 if proj["role"] == "SP" else 0.0) * ip100)
        expo6 = ip100
    # F-REALWAR (gated): the part of realized bWAR the map structurally cannot
    # represent - defense, baserunning, positional value - carried forward as a
    # shrunk per-exposure rate and applied at the PROJECTED exposure.
    if _realwar_enabled():
        rate, _n = realwar_residual(proj, side, war_map)
        war += rate * expo6
    return war
