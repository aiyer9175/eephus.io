# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR v3 skill and position parts (swar.py, tools/build_swar.py): the
eight invariants of docs/ebr-2026-09-30/EBR_GATE.md part 9.4, on fixtures.

  (1) every K at 0 gives every delta 0, so every test value equals fWAR;
  (2) with HEM+'s frozen weights, wOBA~ equals hem_plus.woba_skill;
  (3) with the pool constant and no IFFB, the skill-arm FIP equals fip_skill,
      the floor aside;
  (4) rel x (Fld + Frm) equals DEM+'s rate_1000_shrunk x inn / 1000 for every
      board fielder;
  (5) the fielding part of Pos~ equals dem_plus.ladder_pos_runs;
  (6) every part's re-centred delta sums to 0 per season and side within 1e-9,
      under both home-run variants;
  (7) nopp and pitcher-batter rows carry zero delta;
  (8) a build leaves the sha256 of data/ewar.json unchanged and imports no
      fg_leaderboards.

Plus the spec's two: each part's delta ALONE sums to zero per season and side,
and the xHEM+ arm equals the HEM+ arm's value on every row below 200 PA or
without a Savant value. Nothing here reads real data, and nothing relates a
delta to any next-season quantity.
"""
from __future__ import annotations

import hashlib
import inspect
import json
import re
import sys
from pathlib import Path

import pytest

import dem_plus
import fwar_frame as F
import hem_plus
import rem_plus
import sem_plus
import swar

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import build_swar as B  # noqa: E402

SEASON = 2021

CONSTANTS = {
    "woba_weights": {"ubb": 0.69, "hbp": 0.72, "1b": 0.88, "2b": 1.25, "3b": 1.58, "hr": 2.03},
    "woba_scale": 1.2, "lg_woba": 0.315, "rpw": 9.5, "rpw_constants": 9.5,
    "lg_ra9": 4.6, "lg_era": 4.3, "fip_constant": 3.2,
}
LADDER = {"values": {"C": 10.9, "1B": -8.4, "2B": 5.1, "3B": 3.6, "SS": 9.4,
                     "LF": -6.4, "CF": 4.1, "RF": -6.5, "DH": -13.7},
          "inn_per_pa": 1.97, "window": [2016, 2021], "n_player_seasons": 1900, "r2": 0.97}

# (mlbam, PA, AB, H, 2B, 3B, HR, BB, IBB, HBP, SF, code, innings, fwar, pos_fg, fld, frm, xwoba)
HITTERS = [
    (101, 600, 530, 150, 30, 3, 25, 55, 4, 6, 5, "6", {"SS": 1200.0}, 4.0, 6.0, 5.0, None, 0.360),
    (102, 400, 350, 85, 15, 0, 10, 40, 1, 4, 3, "2", {"C": 900.0}, 2.0, 7.5, 2.0, 8.0, 0.300),
    (103, 650, 580, 160, 35, 1, 30, 60, 8, 3, 6, "3", {"1B": 700.0}, 2.5, -10.0, -3.0, None, None),
    (104, 50, 45, 6, 1, 0, 0, 3, 0, 0, 1, "1", {"P": 150.0}, -0.2, 0.5, 0.0, None, None),
    (105, 150, 135, 33, 6, 1, 3, 12, 0, 2, 1, "7", {"LF": 300.0}, 0.3, -1.5, 1.0, None, 0.330),
    (106, 500, 440, 120, 22, 2, 28, 50, 6, 4, 4, "Y", {}, 3.0, -9.0, 0.0, None, 0.380),
    (107, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, "8", {"CF": 50.0}, 0.1, 0.1, 1.0, None, None),
    (108, 520, 470, 125, 24, 2, 12, 40, 2, 5, 4, "4", {"2B": 1000.0, "SS": 100.0}, 2.8, 4.0, 3.0, 0.2, 0.320),
]

# (mlbam, G, GS, IP, TBF, K, BB, HBP, HR, abbr, fwar, gmli)
PITCHERS = [
    (201, 30, 30, 180.0, 740, 200, 50, 5, 20, "P", 3.5, 0.9),
    (202, 60, 0, 60.0, 240, 70, 20, 2, 5, "P", 1.2, 1.6),
    (203, 40, 8, 90.0, 380, 90, 30, 3, 9, "P", 0.8, 1.1),
    (204, 2, 0, 2.0, 10, 1, 2, 0, 1, "SS", -0.1, 0.1),
    (106, 23, 23, 130.0, 531, 160, 44, 4, 15, "TWP", 3.0, 0.8),
    (205, 15, 0, 10.0, 45, 12, 5, 1, 1, "P", 0.0, 0.7),
    (206, 32, 32, 190.0, 780, 180, 60, 6, 24, "P", 2.9, 0.95),
    (207, 28, 28, 150.0, 640, 140, 55, 4, 22, "P", 1.4, 1.0),
    (208, 25, 24, 120.0, 520, 110, 45, 5, 16, "P", 1.1, 1.0),
    (209, 70, 0, 65.0, 270, 80, 25, 3, 6, "P", 1.5, 1.8),
    (210, 55, 0, 50.0, 215, 50, 22, 2, 7, "P", 0.2, 0.6),
    (211, 65, 1, 62.0, 255, 66, 24, 1, 8, "P", 0.5, 1.2),
]

SAVANT = [(101, 0.360, 590), (102, 0.300, 395), (105, 0.330, 148), (106, 0.380, 490),
          (108, 0.320, 515), (301, 0.345, 400), (302, 0.290, 120), (303, 0.500, 20)]


def _hit_stat(h):
    _m, pa, ab, hits, d, t, hr, bb, ibb, hbp, sf = h[:11]
    return {"plateAppearances": pa, "atBats": ab, "hits": hits, "doubles": d, "triples": t,
            "homeRuns": hr, "baseOnBalls": bb, "intentionalWalks": ibb, "hitByPitch": hbp,
            "sacFlies": sf}


def _pit_stat(p):
    _m, g, gs, ip, tbf, k, bb, hbp, hr = p[:9]
    # the fields part 11.3 reads, derived from the row so every fixture line is coherent
    sf = max(0, tbf // 150)
    ab = tbf - bb - hbp - sf
    hits = int(round(0.22 * (ab - k))) + hr
    return {"gamesPlayed": g, "gamesStarted": gs, "outs": int(round(ip * 3)), "battersFaced": tbf,
            "strikeOuts": k, "baseOnBalls": bb, "hitByPitch": hbp, "homeRuns": hr,
            "atBats": ab, "hits": hits, "doubles": hits // 5, "triples": hits // 40,
            "intentionalWalks": bb // 10, "sacFlies": sf, "runs": int(round(ip * 0.48 + hr * 0.5))}


class FixtureInputs(B.Inputs):
    """A synthetic season: every input the build reads, with no file behind it."""

    def __init__(self, season=SEASON, constants=None, savant=None):
        super().__init__()
        self.season = int(season)
        self._constants = dict(constants or CONSTANTS)
        self._savant = list(SAVANT if savant is None else savant)
        self.chain_calls = []

    def vintage(self):
        return {"vintage_id": "fixture", "seasons": {str(self.season): {}}}

    def frozen_seasons(self):
        return [self.season]

    def vintage_id(self):
        return "fixture"

    def feed_group(self, season, group):
        assert int(season) == self.season
        if group == "hitting":
            rows = {}
            for h in HITTERS:
                mid, fwar, pos_fg, fld, frm = h[0], h[13], h[14], h[15], h[16]
                bat, bsr, lg, rep = 1.0, 0.5, -1.0, 2.0
                rar = bat + bsr + fld + pos_fg + lg + rep + (frm or 0.0)
                rows[mid] = {"war": fwar, "rar": rar, "batting": bat, "baseRunning": bsr,
                             "fielding": fld, "positional": pos_fg, "wLeague": lg, "replacement": rep}
            return rows, []
        return {p[0]: {"war": p[10], "gmli": p[11]} for p in PITCHERS}, []

    def hitting_counts(self, season):
        return {h[0]: {"stat": _hit_stat(h), "code": h[11], "name": f"H{h[0]}"} for h in HITTERS}

    def pitching_counts(self, season):
        return {p[0]: {"stat": _pit_stat(p), "abbr": p[9], "name": f"P{p[0]}"} for p in PITCHERS}

    def fielding(self, season):
        return {h[0]: dict(h[12]) for h in HITTERS}

    def constants(self, season):
        return dict(self._constants)

    def savant(self, season):
        return list(self._savant)

    def ladder(self, season):
        return json.loads(json.dumps(LADDER))

    # -- part 11.3's inputs: a Savant pitcher value for most rows (one left out),
    # every fielder and pitcher on one or two clubs, no runner record
    def savant_pitcher(self, season):
        return {p[0]: (0.300 + 0.002 * (p[0] % 9), 0.305 + 0.003 * (p[0] % 7))
                for p in PITCHERS if p[0] != 205}

    def fielding_by_team(self, season):
        out = {}
        for h in HITTERS:
            out[h[0]] = {pos: {"T1" if h[0] % 2 else "T2": inn} for pos, inn in h[12].items()}
        for p in PITCHERS:
            if p[0] == 203:
                out.setdefault(p[0], {})["P"] = {"T1": p[3] * 0.4, "T2": p[3] * 0.6}
            else:
                out.setdefault(p[0], {})["P"] = {"T1" if p[0] % 2 else "T2": p[3]}
        return out

    def runner_record(self, season):
        return None

    def pitcher_chain(self, season, count_map=None):
        """A stand-in for the replica's feed-only arm: FIP on the (overridden)
        counts, a park factor per row, one league baseline, war0 off
        swar.pitcher_war0 at the published gmLI."""
        self.chain_calls.append(count_map)
        K = self._constants
        out = {}
        for p in PITCHERS:
            mid, g, gs, ip, _tbf, k, bb, hbp, hr, _abbr, _fwar, gmli = p
            cm = (count_map or {}).get(mid) or {}
            hr_, bb_, hbp_, k_ = (cm.get("homeRuns", hr), cm.get("baseOnBalls", bb),
                                  cm.get("hitByPitch", hbp), cm.get("strikeOuts", k))
            fip = F.fip(hr_, bb_, hbp_, k_, ip, K["fip_constant"])
            pf = 1.0 + 0.004 * (mid % 7) - 0.012
            lg9 = K["lg_ra9"] + 0.1
            start_ip = ip * gs / g if g else 0.0
            if gs <= 0:
                start_ip = 0.0
            if g - gs <= 0:
                start_ip = ip
            pfr = swar.pfipr9(fip, pf, K["lg_ra9"], K["lg_era"])
            out[mid] = {"ip": ip, "g": g, "gs": gs, "start_ip": start_ip, "lg9": lg9, "pf": pf,
                        "fip": fip, "gm": gmli, "name": f"P{mid}",
                        "war0": swar.pitcher_war0(ip, g, gs, start_ip, lg9, pfr, gmli)}
        return out


def fixture_hitters():
    inp = FixtureInputs()
    rows, _meta = B.hitter_rows(SEASON, inp)
    return rows, inp


def fixture_pitchers():
    inp = FixtureInputs()
    chain = inp.pitcher_chain(SEASON)
    rows, _meta = B.pitcher_rows(SEASON, inp, chain)
    return rows, chain, inp


@pytest.fixture(scope="module")
def built():
    return B.build([SEASON], inp=FixtureInputs(), out_path=None, log=lambda *a: None)


# --------------------------------------------------------------------------
# (1) every K at 0 gives every delta 0
# --------------------------------------------------------------------------

def test_invariant_1_every_k_at_zero_gives_zero_deltas_and_fwar_test_values():
    rows, _inp = fixture_hitters()
    pool = swar.batting_pool(rows)
    W, scale, rpw = CONSTANTS["woba_weights"], CONSTANTS["woba_scale"], CONSTANTS["rpw"]
    zero_bat = {e: 0.0 for e in swar.BAT_EVENTS}
    zero_inn = {p: 0.0 for p in dem_plus.K_INN}
    g_bat = {r.mlbam: swar.batting_delta(r, pool, W, scale, k=zero_bat) for r in rows}
    g_fld = {r.mlbam: swar.fielding_delta(r, k_inn=zero_inn) for r in rows}
    # zero to floating rounding: with K = 0 the shrunk rate is n / D itself,
    # recombined event by event, so the two arms agree to 1e-9 runs, not bit for bit
    assert all(abs(v) < 1e-9 for v in g_bat.values())
    assert all(v == 0.0 for v in g_fld.values())
    pa = {r.mlbam: r.pa for r in rows}
    for g in (g_bat, g_fld):
        d = swar.recentre(g, pa)
        for r in rows:
            assert swar.hitter_test_value(r.fwar, d[r.mlbam], rpw) == pytest.approx(r.fwar, abs=1e-9)

    prow, chain, _inp = fixture_pitchers()
    sp, rp = swar.pitching_pools(prow)
    zero_pit = {c: 0.0 for c in swar.PIT_COMPONENTS}
    for variant in swar.HR_VARIANTS:
        cm = swar.count_map(prow, sp, rp, variant, k=zero_pit)
        assert set(cm) == {r.mlbam for r in prow if not swar.is_nopp(r.abbr) and r.ip > 0}
        for r in prow:
            if r.mlbam in cm:
                for c in swar.PIT_COMPONENTS:
                    assert cm[r.mlbam][swar.PIT_STAT_KEYS[c]] == pytest.approx(swar.actual_counts(r)[c], abs=1e-9)
        dw = {}
        for r in prow:
            a = chain[r.mlbam]
            tgt = swar.blend_target(swar.start_share(a["start_ip"], a["ip"]), sp, rp)
            df = swar.dfip(r, swar.shrunk_counts(r, tgt, variant, k=zero_pit))
            assert abs(df) < 1e-12
            dw[r.mlbam] = swar.dwar0(a["ip"], a["g"], a["gs"], a["start_ip"], a["lg9"], a["pf"],
                                     a["fip"], df, CONSTANTS["lg_ra9"], CONSTANTS["lg_era"], a["gm"])
        delta = swar.pitching_delta(dw, {r.mlbam: r.ip for r in prow},
                                    [r.mlbam for r in prow if swar.is_nopp(r.abbr)])
        for r in prow:
            assert abs(delta[r.mlbam]) < 1e-9
            assert swar.pitcher_test_value(r.fwar, delta[r.mlbam]) == pytest.approx(r.fwar, abs=1e-9)


# --------------------------------------------------------------------------
# (2) the batting link to HEM+
# --------------------------------------------------------------------------

def test_invariant_2_woba_skill_on_hem_plus_frozen_weights_equals_hem_plus_woba_skill():
    rows, _inp = fixture_hitters()
    pool = swar.batting_pool(rows)
    frozen = {"ubb": hem_plus.W_UBB, "hbp": hem_plus.W_HBP, "1b": hem_plus.W_1B,
              "2b": hem_plus.W_2B, "3b": hem_plus.W_3B, "hr": hem_plus.W_HR}
    n = 0
    for r in rows:
        ours = swar.woba_skill(r, pool, frozen)
        theirs = hem_plus.woba_skill(swar.hem_hitter(r), pool)
        assert (ours is None) == (theirs is None)
        if ours is not None:
            assert ours == pytest.approx(theirs, abs=1e-12)
            n += 1
    assert n >= 6
    # and the constants are HEM+'s own objects, not copies
    assert swar.BAT_K["ubb"] is hem_plus.K_UBB and swar.BAT_K["hr"] is hem_plus.K_HR
    assert swar.BAT_K["2b"] == 1000.0 and swar.BAT_K["3b"] == 1600.0


def test_woba_actual_is_the_frame_woba_on_the_season_weights():
    rows, _inp = fixture_hitters()
    W = CONSTANTS["woba_weights"]
    for r in rows:
        num, den = F.woba_parts(r.bb, r.ibb, r.hbp, r.h, r.doub, r.trip, r.hr, r.ab, r.sf, W)
        assert swar.woba_actual(r, W) == pytest.approx(F.woba(num, den), abs=1e-15)


# --------------------------------------------------------------------------
# (3) the pitching link to SEM+ and REM+
# --------------------------------------------------------------------------

def test_invariant_3_skill_fip_on_the_pool_constant_equals_fip_skill_floor_aside():
    prow, _chain, _inp = fixture_pitchers()
    sp, rp = swar.pitching_pools(prow)
    n_sp = n_rp = 0
    for r in prow:
        if swar.is_nopp(r.abbr):
            continue
        s, rel = swar.starter_object(r), swar.reliever_object(r)
        if sem_plus.is_true_starter(s):
            ours = swar.skill_fip(r, swar.shrunk_counts(r, swar.blend_target(1.0, sp, rp)), sp.cfip)
            assert ours == pytest.approx(sem_plus.fip_skill(s, sp), abs=1e-12) or ours < 1.0
            n_sp += 1
        if rem_plus.is_true_reliever(rel):
            ours = swar.skill_fip(r, swar.shrunk_counts(r, swar.blend_target(0.0, sp, rp)), rp.cfip)
            assert ours == pytest.approx(rem_plus.fip_skill(rel, rp), abs=1e-12) or ours < 1.0
            n_rp += 1
    assert n_sp >= 4 and n_rp >= 4
    assert swar.PIT_K["k"] is rem_plus.K_STRIKEOUT and swar.PIT_K["hr"] is rem_plus.K_HOMERUN
    assert sem_plus.K_HOMERUN is rem_plus.K_HOMERUN


def test_blend_target_endpoints_are_the_two_pools_and_the_swingman_sits_between():
    prow, _chain, _inp = fixture_pitchers()
    sp, rp = swar.pitching_pools(prow)
    assert swar.blend_target(1.0, sp, rp) == swar.pool_rates(sp)
    assert swar.blend_target(0.0, sp, rp) == swar.pool_rates(rp)
    mid = swar.blend_target(0.5, sp, rp)
    for c in swar.PIT_COMPONENTS:
        lo, hi = sorted((swar.pool_rates(sp)[c], swar.pool_rates(rp)[c]))
        assert lo <= mid[c] <= hi
    assert swar.is_swingman(8, 40) and not swar.is_swingman(30, 30) and not swar.is_swingman(0, 60)
    assert not swar.is_swingman(1, 65)   # GS/G 0.015, REM+'s reliever band


def test_hr_fwar_variant_leaves_the_home_run_count_alone():
    prow, _chain, _inp = fixture_pitchers()
    sp, rp = swar.pitching_pools(prow)
    r = next(x for x in prow if x.mlbam == 201)
    tgt = swar.blend_target(1.0, sp, rp)
    shrunk, kept = swar.shrunk_counts(r, tgt, swar.HR_SHRUNK), swar.shrunk_counts(r, tgt, swar.HR_FWAR)
    assert kept["hr"] == r.hr and shrunk["hr"] != r.hr
    for c in ("k", "bb", "hbp"):
        assert shrunk[c] == kept[c]
    with pytest.raises(ValueError):
        swar.shrunk_counts(r, tgt, "hr_other")


def test_dfip_is_the_exact_fip_difference_on_the_shrunk_counts():
    prow, _chain, _inp = fixture_pitchers()
    sp, rp = swar.pitching_pools(prow)
    for r in prow:
        if r.ip <= 0:
            continue
        mt = swar.shrunk_counts(r, swar.blend_target(swar.start_share(r.start_ip, r.ip), sp, rp))
        a = swar.actual_counts(r)
        exact = (F.fip(mt["hr"], mt["bb"], mt["hbp"], mt["k"], r.ip, 3.0)
                 - F.fip(a["hr"], a["bb"], a["hbp"], a["k"], r.ip, 3.0))
        assert swar.dfip(r, mt) == pytest.approx(exact, abs=1e-12)


def test_leverage_la_differs_from_lb_only_through_the_relief_line():
    prow, chain, _inp = fixture_pitchers()
    sp, rp = swar.pitching_pools(prow)
    K = CONSTANTS
    for r in prow:
        a = chain[r.mlbam]
        df = swar.dfip(r, swar.shrunk_counts(r, swar.blend_target(swar.start_share(a["start_ip"], a["ip"]), sp, rp)))
        la = swar.dwar0(a["ip"], a["g"], a["gs"], a["start_ip"], a["lg9"], a["pf"], a["fip"], df,
                        K["lg_ra9"], K["lg_era"], a["gm"])
        lb = swar.dwar0(a["ip"], a["g"], a["gs"], a["start_ip"], a["lg9"], a["pf"], a["fip"], df,
                        K["lg_ra9"], K["lg_era"], 1.0)
        if a["start_ip"] == a["ip"] or a["gm"] == 1.0 or df == 0.0:
            assert la == pytest.approx(lb, abs=1e-12)
        else:
            assert la != lb
            # the relief share is levered by (1 + gmLI) / 2 in both arms, so the
            # L-A and L-B deltas have the same sign
            assert (la > 0) == (lb > 0)


# --------------------------------------------------------------------------
# (4) the fielding link to DEM+
# --------------------------------------------------------------------------

def test_invariant_4_rel_times_runs_equals_dem_plus_shrunk_runs_for_every_fielder():
    rows, _inp = fixture_hitters()
    n = 0
    for r in rows:
        f = swar.dem_fielder(r)
        dem_plus.derive(f)
        rel = swar.fielding_reliability(r)
        if f.rate_shrunk is None:
            assert rel is None
            continue
        tot = dem_plus.fld_total(f)
        assert rel * tot == pytest.approx(f.rate_shrunk * f.inn / dem_plus.PER_INNINGS, abs=1e-12)
        assert rel == pytest.approx(f.rel, abs=1e-15)
        if not swar.is_pitcher_batter(r.code, r.inn_by_pos):
            assert swar.fielding_delta(r) == pytest.approx(-(1.0 - rel) * tot, abs=1e-12)
        n += 1
    assert n >= 6
    # framing counts only on a fielder who caught
    c = next(r for r in rows if r.mlbam == 102)
    nc = next(r for r in rows if r.mlbam == 108)
    assert dem_plus.fld_total(swar.dem_fielder(c)) == c.fld + c.frm
    assert dem_plus.fld_total(swar.dem_fielder(nc)) == nc.fld


# --------------------------------------------------------------------------
# (5) the positional link to the ladder
# --------------------------------------------------------------------------

def test_invariant_5_fielding_part_of_our_positional_equals_dem_plus_ladder_pos_runs():
    rows, _inp = fixture_hitters()
    lad, a = LADDER["values"], LADDER["inn_per_pa"]
    inn_650 = swar.LADDER_PA_BASIS * a
    for r in rows:
        pos = swar.ladder_positional(r.pa, r.inn_by_pos, lad, a)
        fielding_part = dem_plus.ladder_pos_runs(r.inn_by_pos, lad, inn_650)
        dh = swar.dh_exposure(r.pa, r.inn_by_pos, a)
        assert pos == pytest.approx(fielding_part + lad["DH"] * dh / inn_650, abs=1e-12)
    # the DH exposure is the ladder's own spec: PA x a minus fielded innings, floored at 0
    assert swar.dh_exposure(700, {"SS": 1200.0}, 1.97) == pytest.approx(700 * 1.97 - 1200.0)
    assert swar.dh_exposure(600, {"SS": 1200.0}, 1.97) == 0.0    # 1,182 implied innings, all fielded
    assert swar.dh_exposure(500, {"P": 130.0}, 1.97) == pytest.approx(500 * 1.97)   # P is not fielded


def test_position_delta_is_zero_when_our_ladder_prices_as_the_frame_does():
    rows, _inp = fixture_hitters()
    r = next(x for x in rows if x.mlbam == 101)
    pos = swar.ladder_positional(r.pa, r.inn_by_pos, LADDER["values"], LADDER["inn_per_pa"])
    same = swar.HitterRow(**{**r.__dict__, "pos_fg": pos})
    assert swar.position_delta(same, LADDER["values"], LADDER["inn_per_pa"]) == 0.0


# --------------------------------------------------------------------------
# (6) zero sum per season and side, both home-run variants; each part alone
# --------------------------------------------------------------------------

def test_invariant_6_every_part_alone_sums_to_zero_per_season_and_side(built):
    blk = built["seasons"][str(SEASON)]
    # the file rounds each delta to 6 places, so the file's sums carry n x 5e-7
    # of rounding; the unrounded sums are the 1e-9 invariant
    for p in swar.HITTER_PARTS:
        assert abs(sum(h["parts"][p]["d"] for h in blk["hitters"])) < 1e-6 * len(blk["hitters"])
        assert abs(blk["checks"]["zero_sum"][p]) < 1e-9
    for v in swar.HR_VARIANTS:
        assert abs(sum(x["parts"][v]["delta"] for x in blk["pitchers"])) < 1e-6 * len(blk["pitchers"])
        assert abs(blk["checks"]["zero_sum"][v]) < 1e-9
    # and directly, unrounded, on the pure functions
    rows, _inp = fixture_hitters()
    pool = swar.batting_pool(rows)
    pa = {r.mlbam: r.pa for r in rows}
    W, scale = CONSTANTS["woba_weights"], CONSTANTS["woba_scale"]
    g = {r.mlbam: swar.batting_delta(r, pool, W, scale) for r in rows}
    assert any(v != 0.0 for v in g.values())
    assert abs(sum(swar.recentre(g, pa).values())) < 1e-9


def test_recentre_leaves_a_row_with_no_plate_appearance_un_recentred_and_an_excluded_row_at_zero():
    g = {1: 3.0, 2: -1.0, 3: 0.5, 4: 0.0}
    pa = {1: 600, 2: 300, 3: 0, 4: 50}
    d = swar.recentre(g, pa, exclude=[4])
    assert d[3] == 0.5 and d[4] == 0.0
    assert abs(sum(d.values())) < 1e-12
    assert d[1] == pytest.approx(3.0 - 600 * 2.5 / 900)   # the excluded row's 50 PA are outside the sums
    assert swar.recentre({}, {}) == {}


def test_assembled_delta_is_the_sum_of_the_admitted_parts_own_deltas(built):
    rows, _inp = fixture_hitters()
    pa = {r.mlbam: r.pa for r in rows}
    pb = [r.mlbam for r in rows if swar.is_pitcher_batter(r.code, r.inn_by_pos)]
    blk = built["seasons"][str(SEASON)]
    parts = {p: {h["mlbam"]: h["parts"][p]["g"] for h in blk["hitters"]} for p in swar.HITTER_PARTS}
    for admitted in ((), ("pos",), ("bat", "fld"), ("pos", "batx", "fld")):
        d = swar.assembled_delta(parts, admitted, pa, pb)
        assert set(d) == set(pa)
        for mid in pa:
            expect = sum(swar.recentre(parts[p], pa, pb)[mid] for p in admitted)
            assert d[mid] == pytest.approx(expect, abs=1e-9)
        assert abs(sum(d.values())) < 1e-9
        assert all(d[m] == 0.0 for m in pb)
    assert all(v == 0.0 for v in swar.assembled_delta(parts, (), pa, pb).values())


# --------------------------------------------------------------------------
# (7) the nopp and pitcher-batter rules
# --------------------------------------------------------------------------

def test_invariant_7_nopp_and_pitcher_batter_rows_carry_zero_delta(built):
    blk = built["seasons"][str(SEASON)]
    pb = [h for h in blk["hitters"] if h["pitcher_batter"]]
    assert [h["mlbam"] for h in pb] == [104]
    for h in pb:
        for p in swar.HITTER_PARTS:
            assert h["parts"][p]["g"] == 0.0 and h["parts"][p]["d"] == 0.0
            assert h["parts"][p]["test"] == h["fwar"]
    nopp = [x for x in blk["pitchers"] if x["nopp"]]
    assert [x["mlbam"] for x in nopp] == [204]
    for x in nopp:
        for v in swar.HR_VARIANTS:
            assert x["parts"][v]["delta"] == 0.0 and x["parts"][v]["test"] == x["fwar"]
    # the two-way player is on both sides, shrunk as a hitter and as a pitcher;
    # the pitcher-batter has no pitching row in this fixture
    assert blk["census"]["two_way_rows"] == 1 and blk["census"]["rows_on_both_sides"] == 1
    tw_h = next(h for h in blk["hitters"] if h["mlbam"] == 106)
    tw_p = next(x for x in blk["pitchers"] if x["mlbam"] == 106)
    assert not tw_h["pitcher_batter"] and tw_h["parts"]["bat"]["g"] != 0.0
    assert not tw_p["nopp"] and tw_p["parts"]["hr_shrunk"]["delta"] != 0.0
    assert swar.is_pitcher_batter("1", {"P": 10.0}) and not swar.is_pitcher_batter("Y", {})
    assert not swar.is_pitcher_batter("1", {"P": 10.0, "1B": 5.0})
    assert swar.is_nopp("SS") and not swar.is_nopp("P") and not swar.is_nopp("TWP") and not swar.is_nopp("")


def test_count_map_leaves_the_nopp_row_out_so_his_skill_arm_is_the_actual_arm():
    prow, _chain, _inp = fixture_pitchers()
    sp, rp = swar.pitching_pools(prow)
    cm = swar.count_map(prow, sp, rp)
    assert 204 not in cm and 201 in cm and 106 in cm
    assert set(cm[201]) == set(swar.PIT_STAT_KEYS.values())


# --------------------------------------------------------------------------
# (8) the build moves nothing served and imports no fg_leaderboards
# --------------------------------------------------------------------------

def _sha(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else None


def test_invariant_8_a_build_leaves_ewar_json_untouched_and_the_skill_modules_import_no_fg_leaderboards(tmp_path):
    before = _sha(B.EWAR_PATH)
    out = tmp_path / "swar.json"
    payload = B.build([SEASON], inp=FixtureInputs(), out_path=out, log=lambda *a: None)
    assert _sha(B.EWAR_PATH) == before
    assert payload["ewar_json_sha256"] == {"before": before, "after": before}
    assert out.exists() and json.loads(out.read_text(encoding="ascii"))["schema"] == swar.SWAR_VERSION
    for mod in (ROOT / "swar.py", ROOT / "tools" / "build_swar.py"):
        src = mod.read_text(encoding="utf-8")
        assert not re.search(r"^\s*(import|from)\s+fg_leaderboards\b", src, re.M), mod.name
    assert not re.search(r"^\s*(import|from)\s+fg_leaderboards\b", inspect.getsource(swar), re.M)


def test_the_builder_refuses_to_write_under_data_or_docs(tmp_path):
    for bad in (B.ROOT / "data" / "swar.json", B.ROOT / "docs" / "ebr-2026-09-30" / "swar_eval.json"):
        with pytest.raises(B.BuildStop):
            B.write_preview({"schema": "x"}, bad)
    assert B.OUT_PATH == B.ROOT / ".cache" / "swar" / "preview" / "swar.json"


# --------------------------------------------------------------------------
# the xHEM+ arm
# --------------------------------------------------------------------------

def test_the_xhem_arm_equals_the_hem_arm_below_200_pa_or_without_a_savant_value(built):
    blk = built["seasons"][str(SEASON)]
    by = {h["mlbam"]: h for h in blk["hitters"]}
    for mid, h in by.items():
        bat, batx = h["parts"]["bat"], h["parts"]["batx"]
        if h["pa"] < swar.XHEM_ARM_MIN_PA or batx["xwoba"] is None or h["pitcher_batter"]:
            assert batx["arm"] == "hem"
            assert batx["g"] == bat["g"]
        else:
            assert batx["arm"] == "xhem"
    assert by[105]["parts"]["batx"]["arm"] == "hem"        # 150 PA with a Savant value
    assert by[103]["parts"]["batx"]["arm"] == "hem"        # 650 PA, no Savant value
    assert by[101]["parts"]["batx"]["arm"] == "xhem"
    assert by[101]["parts"]["batx"]["g"] != by[101]["parts"]["bat"]["g"]
    assert blk["census"]["xhem_arm_rows"] == 4
    # the re-centred xHEM+ delta differs from the HEM+ delta even where the arm
    # is the HEM+ arm's value, because the re-centring constant moved
    assert by[103]["parts"]["batx"]["d"] != by[103]["parts"]["bat"]["d"]


def test_the_savant_normalizer_is_the_served_columns_pa_weighted_pool_mean():
    xbar = swar.savant_pool_mean(SAVANT)
    rows = [(m, w, pa) for m, w, pa in SAVANT if pa >= 100 and w > 0]
    assert xbar == pytest.approx(sum(w * pa for _m, w, pa in rows) / sum(pa for _m, _w, pa in rows))
    assert swar.savant_pool_mean([]) is None
    assert swar.savant_pool_mean([(1, 0.4, 50)]) is None
    assert swar.xwoba_levelled(0.360, 0.315, 0.320) == pytest.approx(0.360 * 0.315 / 0.320)
    # the pool floor is the served column's own local constant
    src = (ROOT / "hitter_export.py").read_text(encoding="utf-8")
    assert "_XHEM_MIN_PA = %s" % repr(swar.XHEM_POOL_MIN_PA) in src
    assert swar.XHEM_ARM_MIN_PA is hem_plus.QUALIFY_MIN_PA


def test_xbatting_delta_falls_back_to_the_hem_arm_without_a_pool():
    rows, _inp = fixture_hitters()
    r = next(x for x in rows if x.mlbam == 101)
    W, scale, lgw = CONSTANTS["woba_weights"], CONSTANTS["woba_scale"], CONSTANTS["lg_woba"]
    assert swar.xbatting_delta(r, 1.23, None, lgw, scale, W) == 1.23
    assert swar.xbatting_delta(r, 1.23, 0.32, lgw, scale, W) != 1.23


# --------------------------------------------------------------------------
# the build's shape and census
# --------------------------------------------------------------------------

def test_the_preview_carries_the_registered_fields_and_the_census(built):
    assert built["schema"] == swar.SWAR_VERSION
    assert built["registration"] == "docs/ebr-2026-09-30/EBR_GATE.md part 9.4"
    assert built["seasons_built"] == [SEASON] and built["pitcher_arm"] == "plain_fip_loo_pf"
    blk = built["seasons"][str(SEASON)]
    assert blk["ladder"]["window"] == [2016, 2021]
    c = blk["census"]
    assert c["rows_hitters"] == len(HITTERS) and c["rows_pitchers"] == len(PITCHERS)
    assert c["nopp_rows"] == 1 and c["pitcher_batter_rows"] == 1 and c["swingmen"] == 1
    assert c["hitters_pa_zero"] == 1 and c["two_way_rows"] == 1
    assert built["census_total"]["rows_hitters"] == len(HITTERS)
    assert {k for k, _s in B.CENSUS_COLUMNS} <= set(c)
    lines = []
    B.print_census(built, log=lines.append)
    assert lines[-1].startswith("total") and any(l.strip().startswith("pbat") for l in lines)
    for h in blk["hitters"]:
        assert set(h["parts"]) == set(swar.HITTER_PARTS)
        for p in swar.HITTER_PARTS:
            assert h["parts"][p]["test"] == pytest.approx(h["fwar"] + h["parts"][p]["d"] / blk["rpw"], abs=2e-6)
    for x in blk["pitchers"]:
        assert set(x["parts"]) == (set(swar.HR_VARIANTS) | {"pb_" + v for v in swar.HR_VARIANTS}
                                   | {"realized"})
        for v in swar.HR_VARIANTS:
            assert x["parts"][v]["test"] == pytest.approx(x["fwar"] + x["parts"][v]["delta"], abs=2e-6)
            assert "lb_dwar0" in x["parts"][v]
    assert blk["checks"]["chain_gap_max_abs"] <= B.CHAIN_TOL
    # the chain ran once on the actual counts and once per home-run variant
    inp = FixtureInputs()
    B.build([SEASON], inp=inp, out_path=None, log=lambda *a: None)
    assert len(inp.chain_calls) == 1 + len(swar.HR_VARIANTS)
    assert inp.chain_calls[0] is None and all(isinstance(c, dict) for c in inp.chain_calls[1:])


def test_a_missing_savant_season_stops_the_build():
    class NoSavant(FixtureInputs):
        def savant(self, season):
            raise B.MissingSource(f"xwOBA source {season}")
    with pytest.raises(B.MissingSource, match="xwOBA source"):
        B.build([SEASON], inp=NoSavant(), out_path=None, log=lambda *a: None)


def test_the_frame_starts_at_2016_and_ends_at_the_last_complete_season():
    import datetime as dt
    assert B.FIRST_SEASON == 2016
    assert B.last_complete_season(dt.date(2026, 10, 9)) == 2025
    assert B.last_complete_season(dt.date(2026, 11, 1)) == 2026
    assert B.last_complete_season(dt.date(2027, 3, 1)) == 2026
    with pytest.raises(B.MissingSource):
        B.frame_seasons(FixtureInputs(), [2015])
    assert B.frame_seasons(FixtureInputs(), [SEASON]) == [SEASON]


def test_the_pitcher_part_moves_wins_between_pitchers_not_between_sides(built):
    blk = built["seasons"][str(SEASON)]
    for v in swar.HR_VARIANTS:
        tot_fwar = sum(x["fwar"] for x in blk["pitchers"])
        tot_test = sum(x["parts"][v]["test"] for x in blk["pitchers"])
        assert tot_test == pytest.approx(tot_fwar, abs=1e-5)
    for p in swar.HITTER_PARTS:
        tot_fwar = sum(h["fwar"] for h in blk["hitters"])
        tot_test = sum(h["parts"][p]["test"] for h in blk["hitters"])
        assert tot_test == pytest.approx(tot_fwar, abs=1e-5)
