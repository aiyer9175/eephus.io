# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Level-relative eBR for the minor leagues: the pure core.

docs/ebr-2026-09-30/EBR_GATE.md part 2 (the definition) carried to the minor
leagues with s = (level, season) in place of the MLB season (owner answer
EBR-Q6 (b), 2026-10-01: show it on prospect cards, per level and season at
150 or more plate appearances, display only).

WHAT IT IS. Runs above an average runner at the same level in the same season,
from the minor-league partition of the runner record (.cache/pbp_runners/milb).
The five parts of ebr.py (eSB, ePK, eXB_adv, eXB_oob, eGDP) with their formulas
untouched; only the run basis and the outcome distribution change their
conditioning:

  * RE24 is fitted per level-season on that level-season's fit set and shrunk
    toward the level's pooled table over its seasons on disk, or toward that
    season's all-MiLB table where the level has one season on disk;
  * K is the method-of-moments constant of ebr.shrink_constant over the level's
    seasons, or, for a level with one season, over every level-season on disk
    (the same rule applied to the units that exist), clipped to [500, 5000];
  * the outcome distribution backs off from the level-season's own contexts to
    the level's pooled counts (a level with two or more seasons) and then to the
    all-MiLB counts;
  * centring is per level-season, which absorbs the minor leagues' rule
    experiments (pickoff and step-off limits, bigger bases, the pitch clock, the
    automated zone) by construction: a player is compared with the average
    runner in his own league-season, never with the majors.

Advances on balls in the dirt (wild pitches and passed balls) are a reported
sub-total ("W"), uncentred, and never in the number, so eBR means the same thing
at every level.

WHAT IT IS NOT. A level-relative number is not comparable across levels or with
the majors' eBR in runs, never an eFV input (no efv_* module reads this file;
tests/test_ebr_milb_isolation.py pins it), never summarised, validated or
stratified by consensus-FV cell (docs/PROSPECT_ANCHOR_GATE.md), and it predicts
nothing.

Pure: no network, no writes. tools/build_ebr_milb.py reads the record and writes
the previews.
"""
from __future__ import annotations

from collections import defaultdict

import ebr

#: The display flag. False: tools/build_ebr_milb.py writes only under
#: .cache/ebr/milb_preview/ and the PROSPX card (MILB_EBR_CARD_ON in
#: prospx/index.html, pinned equal to this by a test) fetches nothing. The flip
#: is ONE commit: this flag, data/ebr_milb.json, the registry row ebr_milb and the
#: glossary entries together.
MILB_EBR_LIVE = False

MILB_VERSION = "ebr_milb_v1"
LEVEL_ORDER = ("aaa", "aa", "high_a", "single_a", "rookie")
LEVEL_LABEL = {"aaa": "AAA", "aa": "AA", "high_a": "High-A", "single_a": "Single-A", "rookie": "Rookie"}
#: StatsAPI sportId of each partition (rookie is sportId 16 only: the complex
#: leagues; the Dominican Summer League, sportId 17, is not in the record).
LEVEL_SPORT = {"aaa": 11, "aa": 12, "high_a": 13, "single_a": 14, "rookie": 16}
#: A level-season with fewer final games than this is not a unit (AA 2024 holds
#: one game of a probe).
MIN_UNIT_GAMES = 100
#: The card shows a level-season at this many plate appearances or more.
DISPLAY_PA = 150

FIELDS = ("mlbam", "level", "season", "pa", "starts_on_base", "opp_sb", "opp_xb", "opp_dp",
          "sb", "pk", "xb_adv", "xb_oob", "dp", "ebr", "w_n", "w")

Unit = tuple  # (level, season)


def unit_key(unit: Unit) -> str:
    return f"{unit[0]}|{unit[1]}"


def parse_unit_key(s: str) -> Unit:
    lv, yr = s.split("|")
    return (lv, int(yr))


# --------------------------------------------------------------------------
# the feed's steals typed by event but not by movement reason
# --------------------------------------------------------------------------
_STEAL_EVENT = {"stolen_base_2b": ("1B", "2B", "r_stolen_base_2b"),
                "stolen_base_3b": ("2B", "3B", "r_stolen_base_3b"),
                "stolen_base_home": ("3B", "score", "r_stolen_base_home")}


def normalise_runners(rn):
    """(rn, n): the runner frame with each stolen base the minor-league feed types
    by its event but not by its movement reason put on the steal reason.

    EBR_GATE.md 2.2 keys steals on ``details.movementReason`` because on the MLB
    feed the event type scores caught stealing where the runner was safe. The
    minor-league feed has a few entries (one or two per level-season) whose event
    is the runner's own stolen base (stolen_base_2b from first to second, _3b from
    second to third, _home from third) and whose reason is an ordinary advance;
    the official lines count them as steals. Only a safe entry that moves the
    runner exactly from the event's origin base to its target base qualifies, so
    the second runner of a double steal (event of the lead runner, reason an
    advance) and the duplicate entry with no start base are untouched."""
    out = rn.copy()
    et = out["event_type"].fillna("").astype(str)
    rs = out["movement_reason"].fillna("").astype(str)
    st = out["start"].astype(str)
    en = out["end"].astype(str)
    safe = ~out["is_out"].astype(bool)
    n = 0
    for ev, (a0, a1, reason) in _STEAL_EVENT.items():
        m = (et == ev) & (st == a0) & (en == a1) & safe & ~rs.str.startswith("r_stolen_base")
        k = int(m.sum())
        if k:
            out.loc[m, "movement_reason"] = reason
            n += k
    out.attrs["normalised_sb"] = n
    return out, n


# --------------------------------------------------------------------------
# the plan: which pool and which K each unit is shrunk toward
# --------------------------------------------------------------------------
def make_plan(raw_by_unit: dict) -> dict:
    """{unit: {"pool_kind", "pool_units", "pool", "K", "k_source", "k_detail"}}.

    A level with two or more units: pool = the level's pooled table, K by the
    method of moments over the level's units. A level with one unit: pool = the
    all-MiLB table of that unit's season (every unit of the season), K by the
    method of moments over every unit on disk (the all-MiLB constant). Both K are
    clipped to [500, 5000]; the detail of each is kept for the eval."""
    units = sorted(raw_by_unit)
    by_level: dict = defaultdict(list)
    for u in units:
        by_level[u[0]].append(u)
    pool_all = ebr.pool_table({u: raw_by_unit[u] for u in units})
    k_all = ebr.shrink_constant({u: raw_by_unit[u] for u in units}, pool_all) if len(units) > 1 else None
    plan = {}
    level_cache = {}
    for u in units:
        lv, season = u
        us = by_level[lv]
        if len(us) >= 2:
            if lv not in level_cache:
                pool = ebr.pool_table({x: raw_by_unit[x] for x in us})
                kd = ebr.shrink_constant({x: raw_by_unit[x] for x in us}, pool)
                level_cache[lv] = (pool, kd)
            pool, kd = level_cache[lv]
            plan[u] = {"pool_kind": "level", "pool_units": list(us), "pool": pool,
                       "K": kd["K"], "k_source": "level", "k_detail": kd}
        else:
            same = [x for x in units if x[1] == season]
            pool = ebr.pool_table({x: raw_by_unit[x] for x in same})
            if k_all is None:
                raise ebr.EbrRefusal(f"unit {unit_key(u)} is alone on disk: no constant K can be formed")
            plan[u] = {"pool_kind": "season_all", "pool_units": list(same), "pool": pool,
                       "K": k_all["K"], "k_source": "all_milb", "k_detail": k_all}
    return plan


# --------------------------------------------------------------------------
# the outcome distribution: level-season -> level pool -> all MiLB
# --------------------------------------------------------------------------
class MilbBackoff(ebr.Backoff):
    """ebr.Backoff whose pooled root is the all-MiLB counts, refined at the pooled
    context (c, k, o, L) by the level's pooled counts when the level has two or
    more seasons on disk, with the unit's own contexts layered on top exactly as
    in ebr.Backoff."""

    def __init__(self, opps: list, all_counts: dict, level_counts: dict | None = None,
                 kappa: float = ebr.KAPPA):
        super().__init__(opps, all_counts, kappa)
        self.level_counts = level_counts
        self._lcache = {}

    def _pool_pi(self, c, k, o, lab):
        pi = super()._pool_pi(c, k, o, lab)
        if not self.level_counts:
            return pi
        key = (c, k, o, lab)
        if key in self._lcache:
            return self._lcache[key]
        cnt = self.level_counts.get(f"{c}|{k}|{o}|{lab}") or {}
        n = sum(cnt.values())
        if n:
            ys = ebr._outcome_space(c)
            pi = {y: (cnt.get(str(y), 0) + self.kappa * pi[y]) / (n + self.kappa) for y in ys}
        self._lcache[key] = pi
        return pi


# --------------------------------------------------------------------------
# W: advances on balls in the dirt (reported, never in the number)
# --------------------------------------------------------------------------
def dirt_advances(rn, table: dict) -> tuple[dict, dict]:
    """({mlbam: [n, runs]}, league) for the safe advances of runners on a wild
    pitch or passed ball. A group's run value (its runs plus the run expectancy
    change from its start state to its end state, taken from the unit's RE24)
    is split equally among the group's advancing runners. Uncentred: a count and
    the runs those advances were worth, not a comparison with an average runner."""
    re_ = ebr.RE(table)
    sel = rn[rn["event_type"].isin(("wild_pitch", "passed_ball")) & (~rn["is_out"].astype(bool))
             & (rn["start"].astype(str) != rn["end"].astype(str)) & (~rn["is_batter"].astype(bool))]
    out = defaultdict(lambda: [0, 0.0])
    tot_n, tot_runs = 0, 0.0
    if len(sel):
        grp = sel.groupby(["game_pk", "at_bat_index", "play_index"], sort=False)
        for _, g in grp:
            first = g.iloc[0]
            b0, o0 = ebr._int(first["base_before_group"]), ebr._int(first["outs_before_group"])
            b1, o1 = ebr._int(first["base_after_group"]), ebr._int(first["outs_after_group"])
            r = ebr._int(first["runs_group"]) or 0
            if b0 is None or o0 is None or b1 is None or o1 is None:
                continue
            rv = r + re_(b1, o1) - re_(b0, o0)
            share = rv / len(g)
            for rid in g["runner_id"]:
                m = ebr._int(rid)
                if m is None:
                    continue
                out[m][0] += 1
                out[m][1] += share
                tot_n += 1
                tot_runs += share
    return ({m: [v[0], v[1]] for m, v in out.items()},
            {"advances": tot_n, "runs": round(tot_runs, 3)})


# --------------------------------------------------------------------------
# one unit, end to end
# --------------------------------------------------------------------------
def unit_credits(pa, rn, table: dict, backoff: ebr.Backoff, opps: list) -> tuple[list, dict]:
    re_ = ebr.RE(table)
    c_sb, l_sb = ebr.steal_parts(pa, rn, re_)
    c_xb, l_xb = ebr.xb_parts(opps, re_, backoff)
    c_dp, l_dp = ebr.dp_parts(pa, re_)
    return c_sb + c_xb + c_dp, {"steal": l_sb, "xb": l_xb, "dp": l_dp}


def unit_rows(unit: Unit, players: dict, dirt: dict, *, digits: int = 3) -> list:
    """Rows in FIELDS order for one unit."""
    base = ebr.substrate_rows(unit[1], players, digits=digits)
    ix = {f: ebr.FIELDS.index(f) for f in ebr.FIELDS}
    rows = []
    for r in base:
        mid = r[ix["mlbam"]]
        w = dirt.get(mid) or [0, 0.0]
        rows.append([mid, unit[0], unit[1]] + [r[ix[f]] for f in
                     ("pa", "starts_on_base", "opp_sb", "opp_xb", "opp_dp", "sb", "pk", "xb_adv",
                      "xb_oob", "dp", "ebr")] + [int(w[0]), round(w[1], digits)])
    return rows


def rate600(runs: float, pa: int):
    return None if not pa else round(600.0 * runs / pa, 2)
