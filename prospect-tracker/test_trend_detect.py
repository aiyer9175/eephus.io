# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""trend_detect on synthetic trend frames (League Trends plan 3.1, 3.6 to 3.8;
task TR_2A_DETECT_DARK).

A planted velocity change clears its bar and shrinks toward no change; 300
unchanged pitchers give a false count inside the binomial band; the shrink fit
refuses the scored season or a later one; a Gaussian placebo reproduces the
normal tail; games after D change nothing at D; a league-wide shift flags
nobody; entry leverage carries no drift term; more left-handed batters with an
unchanged per-side mix is no mix shift; a cutter relabelled a slider with
cutter physics is not a new pitch; a regular's absence and return is not 'in
the lineup'; the rotation rule reads pal_gamelogs' constants; the mix shrink
null is the selected max of three. Every frame is built in memory here.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats as sst

import pal_gamelogs
import trend_detect as TD
from trend_frames import PHYSICS, TrendFrame

SEASON = 2025
DAY0 = date(SEASON, 3, 27)


def day(i: int, season: int = SEASON) -> str:
    return (date(season, 3, 27) + timedelta(days=int(i))).isoformat()


def _ars(pid, pk, seq, dt, ptype, side, n, speed, ivb=16.0, hb=-8.0, spin=2300.0, ext=6.5,
         wsd=1.0):
    row = {"season": int(dt[:4]), "game_pk": pk, "game_seq": seq, "date": dt, "pitcher": pid,
           "pitch_type": ptype, "bat_side": side, "n": int(n)}
    for v, m, s in (("start_speed", speed, wsd), ("ivb", ivb, 1.0), ("hb", hb, 1.0),
                    ("spin", spin, 40.0), ("ext", ext, 0.1)):
        row[f"n_{v}"] = int(n)
        row[f"s_{v}"] = float(n * m)
        row[f"q_{v}"] = float(n * m * m + (n - 1) * s * s)
    return row


class Builder:
    """Accumulates pitcher appearances, batter games and swings; frame() is a
    trend_frames.TrendFrame with the producer's column names."""

    def __init__(self, season: int = SEASON):
        self.season = season
        self.pit, self.ars, self.bat, self.sw = [], [], [], []
        self.games: dict = {}
        self.prior_cut: dict = {}

    def dt(self, d: int) -> str:
        return day(d, self.season)

    def clone(self) -> "Builder":
        c = Builder(self.season)
        c.pit, c.ars, c.bat, c.sw = list(self.pit), list(self.ars), list(self.bat), list(self.sw)
        c.games, c.prior_cut = dict(self.games), dict(self.prior_cut)
        return c

    @staticmethod
    def key(d: int, slot: int) -> tuple:
        return d * 100000 + slot, d * 100000 + slot

    def appear(self, pid, d, *, start, fb=95.0, n_fb=30, wsd=1.0, ivb=16.0, hb=-8.0,
               spin=2300.0, li=1.0, fb_type="FF", side="R", extra=()):
        pk, seq = self.key(d, pid)
        self.games.setdefault(pk, (seq, d, None, None))
        self.pit.append({"season": self.season, "game_pk": pk, "game_seq": seq,
                         "start_time": self.dt(d) + "T23:05:00Z", "date": self.dt(d), "pitcher": pid,
                         "club": None, "start": bool(start), "li": li, "bf": 5, "so": 1,
                         "bb": 0, "hbp": 0, "outs": 3, "np": n_fb, "swings": 5, "whiffs": 1,
                         "ooz": 3, "chases": 1})
        if n_fb:
            self.ars.append(_ars(pid, pk, seq, self.dt(d), fb_type, side, n_fb, fb, ivb, hb,
                                 spin, wsd=wsd))
        for ptype, s2, n, sp, iv, h in extra:
            self.ars.append(_ars(pid, pk, seq, self.dt(d), ptype, s2, n, sp, iv, h))

    def game(self, d, slot, home, away):
        pk, seq = self.key(d, slot)
        self.games[pk] = (seq, d, home, away)
        return pk, seq

    def bat_game(self, pid, pk, seq, d, club, started):
        self.bat.append({"season": self.season, "game_pk": pk, "game_seq": seq,
                         "start_time": self.dt(d) + "T23:05:00Z", "date": self.dt(d), "batter": pid,
                         "club": club, "started": bool(started), "pa": 4, "ab": 4, "h": 1,
                         "bb": 0, "hbp": 0, "sf": 0, "so": 1, "seen": 15, "swings": 7,
                         "whiffs": 2, "ooz": 5, "chases": 1, "bbe": 2, "ls_sum": 180.0,
                         "ls_sq": 16200.0, "la_sum": 20.0, "hard": 1})

    def swings(self, pid, d, speeds, length=7.3, angle=10.0):
        pk, seq = self.key(d, 90000 + pid % 10000)
        self.games.setdefault(pk, (seq, d, None, None))
        for v in speeds:
            self.sw.append({"season": self.season, "game_pk": pk, "game_seq": seq, "date": self.dt(d),
                            "batter": pid, "bat_speed": float(v), "swing_length": length,
                            "attack_angle": angle})

    def frame(self) -> TrendFrame:
        g = pd.DataFrame([{"season": self.season, "game_pk": pk, "game_seq": s,
                           "start_time": self.dt(d) + "T23:05:00Z", "date": self.dt(d), "home": h,
                           "away": a, "home_score": 0, "away_score": 0, "sb": 0, "cs": 0}
                          for pk, (s, d, h, a) in sorted(self.games.items(), key=lambda x: x[1][0])])
        ars_cols = (["season", "game_pk", "game_seq", "date", "pitcher", "pitch_type", "bat_side", "n"]
                    + [f"{p}_{v}" for v in PHYSICS for p in ("n", "s", "q")])
        pit = pd.DataFrame(self.pit) if self.pit else pd.DataFrame(
            columns=["season", "game_pk", "game_seq", "date", "pitcher", "start", "li"])
        ars = pd.DataFrame(self.ars, columns=ars_cols)
        bat = pd.DataFrame(self.bat) if self.bat else pd.DataFrame(
            columns=["game_pk", "game_seq", "date", "batter", "club", "started"])
        sw = pd.DataFrame(self.sw, columns=["season", "game_pk", "game_seq", "date", "batter",
                                            "bat_speed", "swing_length", "attack_angle"])
        return TrendFrame(self.season, g, pit, ars, bat, sw, dict(self.prior_cut),
                          {"season": self.season})


def starters(b: Builder, rng, n=60, last_day=140, skip=()):
    """n starters every 5 days, each at his own mean with game SD 0.7."""
    for pid in range(1, n + 1):
        if pid in skip:
            continue
        mu = rng.uniform(92.0, 96.0)
        for d in range(pid % 5, last_day + 1, 5):
            b.appear(pid, d, start=True, fb=mu + rng.normal(0, 0.7), n_fb=40)


def relievers(b: Builder, rng, ids, last_day=200, game_sd=0.75, shift=None, li_shift=None):
    """Relievers every 2 days at their own mean; ``shift`` (day, mph) adds a
    league-wide change from that day on."""
    for pid in ids:
        mu = rng.uniform(93.0, 97.0)
        li_mu = rng.uniform(0.6, 1.6)
        for d in range(pid % 2, last_day + 1, 2):
            v = mu + rng.normal(0, game_sd)
            li = li_mu * np.exp(rng.normal(0, 0.4))
            if shift is not None and d >= shift[0]:
                v += shift[1]
            if li_shift is not None and d >= li_shift[0]:
                li *= li_shift[1]
            b.appear(pid, d, start=False, fb=v, n_fb=10, li=li)


# --------------------------------------------------------------------------- #
# the planted change, the false count, the shrink fit and the placebo
# --------------------------------------------------------------------------- #
def test_planted_velocity_change_clears_the_bar_and_shrinks_toward_zero():
    rng = np.random.default_rng(1)
    b = Builder()
    starters(b, rng, n=60, last_day=139, skip=(7,))
    # pitcher 7: 25 starts at 95.0 with game SD 0.7, then 3 at 92.5
    days = list(range(0, 140, 5))[:28]
    for i, d in enumerate(days):
        b.appear(7, d, start=True, fb=(95.0 + rng.normal(0, 0.7)) if i < 25 else 92.5, n_fb=40)
    f = b.frame()
    D = day(days[-1])
    t = TD.detect(f, D, "sp_velo")
    me = t[t["pid"] == 7].iloc[0]
    assert (me["nW"], me["nB"]) == (3, 25)
    assert me["mean_w"] == pytest.approx(92.5)
    assert abs(me["z_adj"]) >= TD.bar_for("sp_velo") == 4.5
    fit = {"kind": "normal", "pi0": 0.3, "tau": 0.6, "identified": True}
    fl = TD.flag(t, "sp_velo", TD.bar_for("sp_velo"), fit)
    me = fl[fl["pid"] == 7].iloc[0]
    assert 0 < me["shrunk"] / me["raw"] < 1 and me["shrunk"] / me["d"] < 1
    assert bool(me["flag"])
    assert int(fl["flag"].sum()) == 1


def test_unchanged_pitchers_false_count_inside_the_binomial_band():
    rng = np.random.default_rng(21)
    b = Builder()
    relievers(b, rng, range(1, 301), last_day=200)
    f = b.frame()
    dates = [day(d) for d in range(60, 200, 7)][:20]
    assert len(dates) == 20
    bar = 3.0
    tests = pd.concat([TD.detect(f, D, "rp_velo") for D in dates], ignore_index=True)
    n = len(tests)
    assert n >= 20 * 290
    tail = 2 * sst.norm.sf(bar)
    lo, hi = sst.binom.ppf(0.0005, n, tail), sst.binom.ppf(0.9995, n, tail)
    false = int((tests["z_adj"].abs() >= bar).sum())
    assert lo <= false <= hi, (false, n * tail, lo, hi)


def test_shrink_fit_refuses_the_scored_season_or_later():
    rng = np.random.default_rng(3)
    t = pd.DataFrame({"d": rng.normal(0, 1, 400), "se": np.full(400, 0.8)})
    by = {2023: t, 2024: t, 2025: t}
    for bad in ([2023, 2025], [2025], [2026], [2024, 2026]):
        with pytest.raises(ValueError, match="only completed seasons before"):
            TD.shrink_fit(by, 2025, bad)
        with pytest.raises(ValueError, match="only completed seasons before"):
            TD.shrink_fit_mix(by, by, 2025, bad)
    fit = TD.shrink_fit(by, 2025, [2023, 2024])
    assert fit["seasons"] == [2023, 2024] and fit["scored_season"] == 2025
    # the first swing season: no earlier season, no fit; the floor reads the raw change
    assert TD.shrink_fit(by, 2024, []) is None
    fl = TD.flag(pd.DataFrame({"d": [1.5, 0.5], "z_adj": [5.0, 5.0], "se": [0.3, 0.1]}),
                 "bat_speed", 4.25, None)
    assert fl["shrunk"].isna().all() and fl["flag"].tolist() == [True, False]


def test_gaussian_placebo_reproduces_the_normal_tail():
    rng = np.random.default_rng(4)
    b = Builder()
    relievers(b, rng, range(1, 301), last_day=200)
    f = b.frame()
    z = pd.concat([TD.placebo(f, day(d), "rp_velo", R=8, seed=11)["z_adj"]
                   for d in (90, 130, 170)], ignore_index=True)
    assert len(z) > 6000
    assert float(z.std()) == pytest.approx(1.0, abs=0.08)
    share = float((z.abs() >= 2.0).mean())
    assert share == pytest.approx(2 * sst.norm.sf(2.0), rel=0.25)


# --------------------------------------------------------------------------- #
# as of D
# --------------------------------------------------------------------------- #
def _population(b: Builder, rng, last_day: int, first_day: int = 0, mus=None):
    mus = mus if mus is not None else {}
    for pid in range(1, 26):
        mu = mus.setdefault(pid, rng.uniform(92.0, 96.0))
        for d in range(pid % 5, last_day + 1, 5):
            if d >= first_day:
                b.appear(pid, d, start=True, fb=mu + rng.normal(0, 0.7), n_fb=40)
    for pid in range(101, 141):
        mu = mus.setdefault(pid, rng.uniform(93.0, 97.0))
        for d in range(pid % 2, last_day + 1, 2):
            if d < first_day:
                continue
            nR, nL = 20, 10
            extra = [("SL", "R", int(rng.binomial(nR, 0.3)), 85.0, 2.0, 5.0),
                     ("CH", "L", int(rng.binomial(nL, 0.5)), 86.0, 6.0, -14.0),
                     ("SL", "L", int(rng.binomial(nL, 0.1)), 85.0, 2.0, 5.0)]
            b.appear(pid, d, start=False, fb=mu + rng.normal(0, 0.7), n_fb=12,
                     li=float(np.exp(rng.normal(0, 0.5))), extra=extra)
    for pid in range(501, 531):
        mu = mus.setdefault(pid, rng.uniform(68.0, 76.0))
        for d in range(first_day, last_day + 1):
            if (d + pid) % 6 == 0:
                continue
            b.swings(pid, d, mu + rng.normal(0, 3.0, 5), length=7.0 + rng.normal(0, 0.3),
                     angle=10 + rng.normal(0, 4))
            b.swings(pid, d, [30.0])                      # a slow swing, never competitive
    return mus


def test_games_after_d_change_nothing_at_d():
    D_day, extra_days = 120, 40
    a = Builder()
    mus = _population(a, np.random.default_rng(5), D_day)
    b = a.clone()                                          # the same games, then 40 more days
    _population(b, np.random.default_rng(6), D_day + extra_days, first_day=D_day + 1, mus=mus)
    for d in range(D_day + 1, D_day + extra_days):         # and players who appear only after D
        b.appear(900, d, start=False, fb=99.0, n_fb=12, li=2.0)
        b.swings(950, d, [80.0, 81.0, 82.0, 83.0])
    for x in (a, b):
        x.prior_cut = {501: 66.0, 502: 70.0}
    fa, fb = a.frame(), b.frame()
    assert len(fb.pit) > len(fa.pit) and len(fb.swings) > len(fa.swings)
    D = day(D_day)
    for key in ("sp_velo", "rp_velo", "rp_entry_li", "mix", "bat_speed", "attack_angle"):
        ta, tb = TD.detect(fa, D, key), TD.detect(fb, D, key)
        assert len(ta) > 0, key
        pd.testing.assert_frame_equal(ta, tb, check_dtype=False)
        pa, pb = (TD.placebo(fa, D, key, R=3, seed=9), TD.placebo(fb, D, key, R=3, seed=9))
        pd.testing.assert_frame_equal(pa, pb, check_dtype=False)
        if key != "mix":
            assert TD.sigma(fa, D, key) == TD.sigma(fb, D, key)
    pd.testing.assert_series_equal(TD.competitive_cut_as_of(fa, D), TD.competitive_cut_as_of(fb, D))
    # and the date matters: one day later the frame with later games moves
    assert not TD.detect(fb, day(D_day + 30), "rp_velo").equals(TD.detect(fb, D, "rp_velo"))


def test_competitive_cut_takes_the_previous_season_until_100_swings():
    b = Builder()
    for d in range(10):
        b.swings(501, d, [60.0 + d, 70.0, 72.0, 74.0, 76.0])
    b.prior_cut = {501: 66.5}
    f = b.frame()
    assert TD.competitive_cut_as_of(f, day(9))[501] == 66.5         # 50 swings
    for d in range(10, 25):
        b.swings(501, d, [70.0, 72.0, 74.0, 76.0, 78.0])
    f = b.frame()
    own = b.frame().swings
    own = own[(own["date"] <= day(24)) & (own["bat_speed"] >= 50)]["bat_speed"].quantile(0.10)
    assert TD.competitive_cut_as_of(f, day(24))[501] == pytest.approx(own)   # 125 swings
    assert 502 not in TD.competitive_cut_as_of(f, day(24)).index


# --------------------------------------------------------------------------- #
# drift
# --------------------------------------------------------------------------- #
def test_league_wide_shift_flags_nobody():
    rng = np.random.default_rng(6)
    b = Builder()
    relievers(b, rng, range(1, 81), last_day=160, game_sd=0.2, shift=(149, 0.5))
    f = b.frame()
    D = day(160)
    t = TD.detect(f, D, "rp_velo")
    assert len(t) == 80
    assert t["raw"].mean() == pytest.approx(0.5, abs=0.05)
    assert t["drift"].iloc[0] == pytest.approx(t["raw"].mean())
    assert int((t["z_adj"].abs() >= TD.bar_for("rp_velo")).sum()) == 0
    # with the drift term switched off the same shift would flag most of them
    from dataclasses import replace
    nodrift = replace(TD.FAMILIES["rp_velo"], drift=False)
    t0 = TD.detect(f, D, nodrift)
    assert int((t0["z_adj"].abs() >= TD.bar_for("rp_velo")).sum()) > 40


def test_entry_leverage_has_no_drift_term():
    assert TD.FAMILIES["rp_entry_li"].drift is False
    assert all(f.drift for k, f in TD.FAMILIES.items() if k != "rp_entry_li")
    rng = np.random.default_rng(7)
    b = Builder()
    relievers(b, rng, range(1, 81), last_day=160, li_shift=(145, 3.0))
    t = TD.detect(b.frame(), day(160), "rp_entry_li")
    assert len(t) > 60
    assert (t["drift"] == 0.0).all()
    assert t["d"].equals(t["raw"])
    assert t["raw"].mean() == pytest.approx(np.log(3.0), abs=0.15)


# --------------------------------------------------------------------------- #
# mix and new pitch
# --------------------------------------------------------------------------- #
_MIX = {"R": {"FF": 0.6, "SL": 0.3, "CH": 0.1}, "L": {"FF": 0.4, "SL": 0.1, "CH": 0.5}}
_PHYS = {"FF": (95.0, 16.0, -8.0), "SL": (85.0, 2.0, 5.0), "CH": (86.0, 6.0, -14.0)}


def _mix_game(b, pid, d, sides, rng=None):
    rows = []
    for side, n in sides.items():
        for pt, p in _MIX[side].items():
            k = int(rng.binomial(n, p)) if rng is not None else int(round(n * p))
            sp, iv, h = _PHYS[pt]
            rows.append((pt, side, k, sp, iv, h))
    ff = [r for r in rows if r[0] == "FF"]
    rest = [r for r in rows if r[0] != "FF"]
    b.appear(pid, d, start=False, fb=95.0, n_fb=0, extra=ff + rest)


def test_more_lefties_with_an_unchanged_per_side_mix_is_no_mix_shift():
    rng = np.random.default_rng(8)
    b = Builder()
    for pid in range(1, 81):
        for d in range(pid % 2, 161, 2):
            _mix_game(b, pid, d, {"R": 20, "L": 10}, rng)
    # pitcher 99: exact per-side mix; facing mostly lefties over his last 8
    days = list(range(0, 161, 2))
    for i, d in enumerate(days):
        sides = {"R": 20, "L": 10} if i < len(days) - 8 else {"R": 10, "L": 20}
        _mix_game(b, 99, d, sides)
    f = b.frame()
    t = TD.detect(f, day(160), "mix")
    me = t[t["pid"] == 99].iloc[0]
    assert me["nW"] == 8 and abs(me["t"]) < 2.0 and abs(me["z_adj"]) < TD.bar_for("mix")
    # the naive total change in changeups was 13 points, above the 8-point floor
    a = f.arsenal[f.arsenal["pitcher"] == 99]
    win = a["date"] >= day(days[-8])
    ch = lambda m: a[m & (a["pitch_type"] == "CH")]["n"].sum() / a[m]["n"].sum()  # noqa: E731
    assert ch(win) - ch(~win) >= 0.08
    assert me["expected_w"] == pytest.approx(me["share_w"], abs=1e-9)


def _arsenal_game(b, pid, d, mix, start=True):
    rows = [(pt, "R", n, sp, iv, h) for pt, n, sp, iv, h in mix]
    b.appear(pid, d, start=start, n_fb=0, extra=rows)


def test_cutter_relabelled_slider_is_not_a_new_pitch():
    b = Builder()
    base = [("FF", 54, 95.0, 16.0, -8.0), ("FC", 22, 89.0, 8.0, 2.0), ("CH", 14, 85.0, 6.0, -14.0)]
    relabel = [("FF", 54, 95.0, 16.0, -8.0), ("SL", 22, 89.0, 8.0, 2.0),
               ("CH", 14, 85.0, 6.0, -14.0)]
    sweeper = [("FF", 54, 95.0, 16.0, -8.0), ("FC", 10, 89.0, 8.0, 2.0),
               ("ST", 12, 81.0, 1.0, 15.0), ("CH", 14, 85.0, 6.0, -14.0)]
    days = list(range(0, 65, 5))
    for i, d in enumerate(days):
        last3 = i >= len(days) - 3
        _arsenal_game(b, 1, d, relabel if last3 else base)
        _arsenal_game(b, 2, d + 1, sweeper if last3 else base)
    f = b.frame()
    r = TD.new_pitch(f, day(days[-1] + 1))
    assert 1 not in set(r["pid"])
    assert r[r["pid"] == 2]["group"].tolist() == ["SL"]


# --------------------------------------------------------------------------- #
# playing time and the rotation
# --------------------------------------------------------------------------- #
def _club_season(b: Builder, n_games: int, lineup: dict):
    """One club AAA, one game a day; lineup: batter -> list of 'S' (started),
    'A' (appeared, not started) or '-' (absent), one entry per club game."""
    for g in range(n_games):
        pk, seq = b.game(g, 1, "AAA", "BBB")
        for pid, marks in lineup.items():
            m = marks[g]
            if m in ("S", "A"):
                b.bat_game(pid, pk, seq, g, "AAA", m == "S")


def test_a_regulars_absence_and_return_is_not_in_the_lineup():
    n = 89
    regular = ["S"] * 60 + ["-"] * 15 + ["S"] * 14
    bench = (["S", "A", "A", "A", "A"] * 15)[:75] + ["S"] * 14
    starter_out = ["S"] * 75 + ["A"] * 12 + ["S", "S"]
    b = Builder()
    _club_season(b, n, {11: regular, 12: bench, 13: starter_out})
    f = b.frame()
    r = TD.playing_time(f, day(n - 1))
    got = dict(zip(r["pid"], r["direction"]))
    assert 11 not in got                    # back from 15 games away: not 'in the lineup'
    assert got.get(12) == "in"              # started 15 of 75, then 14 straight
    assert got.get(13) == "out"             # 2 of the last 14 after starting every game
    ok = TD.available(np.array([m != "-" for m in regular[:75]]))
    assert int((~ok).sum()) == 15


def _rotation_case(b, pid, relief_first=10, starts_after=3):
    d = 0
    for _ in range(relief_first):
        b.appear(pid, d, start=False, n_fb=10)
        d += 2
    for _ in range(starts_after):
        b.appear(pid, d, start=True, n_fb=40)
        d += 5
    return d - 5


def test_rotation_rule_reads_pal_constants(monkeypatch):
    b = Builder()
    last = _rotation_case(b, 1, relief_first=10)
    f = b.frame()
    r = TD.rotation_switch(f, day(last))
    assert r["direction"].tolist() == ["into"] and int(r["earlier_relief"].iloc[0]) == 10
    monkeypatch.setattr(pal_gamelogs, "MIN_PRE_RELIEF", 11)
    assert TD.rotation_switch(f, day(last)).empty
    monkeypatch.undo()
    # out of the rotation: 6 starts then 4 relief outings, gated by START_SEG_START_SHARE_MIN
    b2 = Builder()
    d = 0
    for _ in range(6):
        b2.appear(2, d, start=True, n_fb=40)
        d += 5
    for _ in range(4):
        b2.appear(2, d, start=False, n_fb=10)
        d += 2
    f2 = b2.frame()
    assert TD.rotation_switch(f2, day(d - 2))["direction"].tolist() == ["out of"]
    monkeypatch.setattr(pal_gamelogs, "START_SEG_START_SHARE_MIN", 1.01)
    assert TD.rotation_switch(f2, day(d - 2)).empty
    src = Path(TD.__file__).read_text(encoding="utf-8")
    for name in ("MIN_PRE_RELIEF", "RELIEF_SEG_START_SHARE_MAX", "MIN_PRE_STARTS",
                 "START_SEG_START_SHARE_MIN"):
        assert f"PAL.{name}" in src and f"{name} =" not in src


# --------------------------------------------------------------------------- #
# the mix shrink null
# --------------------------------------------------------------------------- #
def test_mix_shrink_null_is_the_selected_max_of_three():
    rng = np.random.default_rng(10)
    b = Builder()
    for pid in range(1, 201):
        for d in range(pid % 2, 161, 2):
            _mix_game(b, pid, d, {"R": 20, "L": 10}, rng)
    f = b.frame()
    dates = [day(d) for d in (100, 120, 140, 160)]
    real = pd.concat([TD.detect(f, D, "mix") for D in dates], ignore_index=True)
    pl = pd.concat([TD.placebo(f, D, "mix", R=4, seed=3) for D in dates], ignore_index=True)
    null = TD.mix_null(pl)
    # the selected t is the largest of three: wider than one family's N(0, 1)
    assert float(np.mean(np.abs(null))) > 1.0 > float(sst.halfnorm.mean())
    assert float(np.mean(np.abs(pl["t"]))) == pytest.approx(float(np.mean(np.abs(null))), rel=0.02)
    fit = TD.shrink_fit_mix({2024: real}, {2024: pl}, 2025, [2024])
    assert fit["null"]["source"] == "placebo selected max of three"
    assert len(fit["null"]["t"]) == min(TD.MIX_NULL_MAX, 2 * int(pl["t"].notna().sum()))
    # on changes that are all noise the selected null leaves no real share, or
    # no identified spread, so no shrunk value is printed
    assert fit["pi0"] >= 0.8 or not fit["identified"]
    if not fit["identified"]:
        assert TD.shrink_apply(real, fit)["shrunk"].isna().all()
    # the lane's single-family null reads the same noise as real change
    pi0_single, _tau = TD.two_group_fit(real["d"], real["se"])
    assert pi0_single < fit["pi0"]


def test_mix_shrinks_a_planted_shift_when_identified():
    rng = np.random.default_rng(12)
    b = Builder()
    for pid in range(1, 201):
        for d in range(pid % 2, 161, 2):
            _mix_game(b, pid, d, {"R": 20, "L": 10}, rng)
    # 40 pitchers move 15 points from fastballs to changeups over their last 8
    for pid in range(301, 341):
        days = list(range(pid % 2, 161, 2))
        for i, d in enumerate(days):
            if i < len(days) - 8:
                _mix_game(b, pid, d, {"R": 20, "L": 10}, rng)
            else:
                b.appear(pid, d, start=False, n_fb=0, extra=[
                    ("FF", "R", int(rng.binomial(20, 0.45)), 95.0, 16.0, -8.0),
                    ("SL", "R", int(rng.binomial(20, 0.3)), 85.0, 2.0, 5.0),
                    ("CH", "R", int(rng.binomial(20, 0.25)), 86.0, 6.0, -14.0),
                    ("FF", "L", int(rng.binomial(10, 0.25)), 95.0, 16.0, -8.0),
                    ("SL", "L", int(rng.binomial(10, 0.1)), 85.0, 2.0, 5.0),
                    ("CH", "L", int(rng.binomial(10, 0.65)), 86.0, 6.0, -14.0)])
    f = b.frame()
    D = day(160)
    real = TD.detect(f, D, "mix")
    pl = TD.placebo(f, D, "mix", R=6, seed=4)
    fit = TD.shrink_fit_mix({2024: real}, {2024: pl}, 2025, [2024])
    assert fit["identified"] and 0.0 < fit["pi0"] < 1.0
    s = TD.shrink_apply(real, fit)
    moved = s[s["pid"].between(301, 340) & (s["fam_sel"].isin(["FB", "OS"]))]
    assert len(moved) >= 30
    ratio = (moved["shrunk"] / moved["d"]).to_numpy()
    assert np.all(ratio > 0) and np.all(ratio < 1.0)


# --------------------------------------------------------------------------- #
# prior-season mode
# --------------------------------------------------------------------------- #
def test_prior_season_mode():
    rng = np.random.default_rng(13)
    prior = Builder(SEASON - 1)
    cur = Builder(SEASON)
    mus = {pid: rng.uniform(92.0, 96.0) for pid in range(1, 61)}
    for pid, mu in mus.items():
        for d in range(pid % 5, 150, 5):
            prior.appear(pid, d, start=True, fb=mu + rng.normal(0, 0.7), n_fb=40)
        n_now = 9 if pid == 2 else 3
        for i in range(n_now):
            d = 20 + (pid % 5) + 5 * i if pid != 2 else 2 + 4 * i
            shift = -3.5 if pid == 1 else 0.0
            cur.appear(pid, d, start=True, fb=mu + shift + rng.normal(0, 0.7), n_fb=40)
    fp, fc = prior.frame(), cur.frame()
    D = day(34)
    t = TD.detect_prior(fc, fp, D, "sp_velo")
    assert 2 not in set(t["pid"])                   # past the in-season floor
    assert len(t) >= 50 and (t["nW"] == 3).all() and (t["nB"] >= TD.PRIOR_BASELINE_MIN).all()
    me = t[t["pid"] == 1].iloc[0]
    assert abs(me["z_adj"]) >= TD.PRIOR_SEASON_BAR
    assert int((t["z_adj"].abs() >= TD.PRIOR_SEASON_BAR).sum()) == 1
    pl = TD.placebo_prior(fc, fp, D, "sp_velo", R=4, seed=2)
    assert len(pl) == 4 * len(t) and int((pl["z_adj"].abs() >= TD.PRIOR_SEASON_BAR).sum()) <= 1
    with pytest.raises(ValueError, match="excluded from prior-season mode"):
        TD.detect_prior(fc, fp, D, "mix")
    assert TD.detect_prior(fc, fp, D, "bat_speed").empty           # until the build calibrates


# --------------------------------------------------------------------------- #
# the tables and the module
# --------------------------------------------------------------------------- #
def test_families_and_bars():
    strict, looser = TD.BARS["strict"], TD.BARS["looser"]
    assert TD.BAR_POLICY == "strict"
    assert set(strict) == {"sp_velo", "rp_velo", "rp_ivb", "rp_hb", "mix", "rp_entry_li",
                           "bat_speed", "swing_length", "attack_angle"}
    assert set(looser) == set(strict) | {"rp_spin", "rp_ext"}
    assert strict["sp_velo"] == 4.5 and strict["mix"] == 6.0 and strict["rp_entry_li"] == 4.0
    assert [strict[k] for k in ("bat_speed", "swing_length", "attack_angle")] == [4.25] * 3
    assert all(v in TD.BAR_GRID for p in TD.BARS.values() for v in p.values())
    assert set(TD.FAMILIES) == set(looser)
    for k, f in TD.FAMILIES.items():
        assert f.key == k and f.roles and f.window and f.unit and f.label
        assert (f.pool == "all tracked") == (f.kind == "swing")
    assert TD.FAMILIES["sp_velo"].two_component and TD.FAMILIES["sp_velo"].min_per_game == 15
    assert TD.FAMILIES["mix"].window == {"SP": ("count", 3), "RP": ("count", 8)}
    assert TD.FAMILIES["rp_entry_li"].size_floor == pytest.approx(np.log(1.5))
    assert TD.PRIOR_SEASON_BAR == 6.0 and "mix" in TD.PRIOR_EXCLUDED


def test_eval_dates_and_episodes():
    ds = TD.eval_dates(2025, "2025-09-28")
    assert ds[0] == "2025-05-18" and ds[-1] == "2025-09-28" and len(ds) == 20
    fl = pd.DataFrame({"family": "rp_velo", "pid": [1, 1, 1, 1, 2],
                       "D": ["2025-07-01", "2025-07-02", "2025-07-04", "2025-07-05", "2025-07-01"]})
    ep = TD.episodes(fl)
    assert ep[ep["pid"] == 1][["first", "dates"]].values.tolist() == [["2025-07-01", 2],
                                                                        ["2025-07-04", 2]]


def test_the_module_is_pure_and_names_no_gated_string():
    src = Path(TD.__file__).read_text(encoding="utf-8")
    for io in ("open(", "read_parquet", "read_csv", "to_parquet", "write_text", "read_text",
               "urlopen", "requests."):
        assert io not in src, io
    for banned in (".cache", "betting", "odds", "lineup_capture", "leaderboard_vintages",
                   "weather", "game_feeds", "mg_" + "pen_", "mg_" + "hook_", "sp_" + "n365",
                   "sp_" + "budget", "sp_" + "ppo", "sp_" + "xouts", "bat_" + "ppa_l30"):
        assert banned not in src, banned
