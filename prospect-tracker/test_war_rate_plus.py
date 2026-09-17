# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""WAR/PA+ and WAR/IP+ (the 2026-07-29 Arkmetric lane).

Pins the parts of the design that a later reader is most likely to break:

  * the scale is 100 + 10z, so the ANCHOR POOL's spread is exactly ten points
    per sigma. This is the aStuff+ defect class (an index advertising ten points
    per sigma while delivering 7.16 because mu/sd came from a different pool),
    so it gets a direct test rather than a comment.
  * batting and pitching WAR stay on SEPARATE keys, so a two-way player's
    pitching WAR is never divided by his plate appearances.
  * a silent WAR failure is REFUSED, never served as a board of zeros.
  * a player with no WAR row gets NO field, not a zero.
  * two-tier volume floors: the pool floor anchors, the display gate publishes.
    The counting stat `war` is NOT gated: every covered row with a positive
    denominator carries it (a count needs no floor), the two-way card row too.
  * no clamp (true-to-model policy): a real outlier prints past 160.
  * the 3-year companion is a FROZEN vintage read verbatim, carrying its
    generated_at disclosure, and it is dropped from the history boards.

Offline: every test builds its own rows and its own WAR map. Nothing fetches.
The map is basis-agnostic: since the 2026-09-03 epoch the exporters read the
war_source default (eWAR v2), and this file pins the scale, the side split and
the refusal rules, none of which depend on which series fills the map.
"""
from __future__ import annotations

import json
from pathlib import Path

import bullpen_export as be
import hitter_export as he
import starter_export as se

ROOT = Path(__file__).parent


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _war_map(season: int, bat=None, pit=None) -> dict:
    out: dict = {}
    for side, src in (("bat", bat or {}), ("pit", pit or {})):
        for mid, w in src.items():
            out.setdefault(int(mid), {}).setdefault(int(season), {})[side] = w
    return out


def _patch_war(monkeypatch, war):
    monkeypatch.setattr(be, "_side_war_by_season", lambda: war)


# --------------------------------------------------------------------------- #
# the scale claim
# --------------------------------------------------------------------------- #
def test_anchor_pool_delivers_exactly_ten_points_per_sigma(monkeypatch):
    """The whole point of convention 3. mu/sd come from the pool the index is
    anchored on, so the pool's plus values have SD 10.0. If a future change takes
    mu/sd from anywhere else, this fails - which is what the aStuff+ row on
    GATED_CANDIDATES.md is about."""
    n = 60
    rows = [{"mlbam": 1000 + i, "pa": 300.0 + i} for i in range(n)]
    bat = {1000 + i: (i - n / 2) * 0.01 for i in range(n)}   # spread of WAR
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"] and meta["n_stamped"] == n
    # *_raw is serialized at one decimal (the rem_plus_raw / hem_plus_raw house
    # convention), so the tolerance is the serialization step, not slack in the
    # scale. The lab never reads this field: it recomputes from the WAR frame, which is how
    # the harness-v2 unrounded-predictor rule is satisfied.
    vals = [r["war_pa_plus_raw"] for r in rows]
    mu = sum(vals) / n
    sd = (sum((v - mu) ** 2 for v in vals) / (n - 1)) ** 0.5
    assert abs(mu - 100.0) < 0.02, mu
    assert abs(sd - 10.0) < 0.02, f"{sd} points per anchor-pool sigma, want 10"
    assert meta["per_sigma"] == 10.0


def test_adj_companion_delivers_exactly_ten_points_per_sigma(monkeypatch):
    """The _adj column re-standardises on the SHRUNK pool. Taking mu/sd from the
    unshrunk pool instead would leave it advertising ten points per sigma while
    delivering fewer, which is precisely the aStuff+ 7.16 defect (GATED_CANDIDATES
    C3). Shipped 2026-07-30 when the owner closed the shrink call."""
    n = 60
    rows = [{"mlbam": 1000 + i, "pa": 300.0 + i * 10} for i in range(n)]
    bat = {1000 + i: (i - n / 2) * 0.01 for i in range(n)}
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"]
    vals = [r["war_pa_plus_adj_raw"] for r in rows if "war_pa_plus_adj_raw" in r]
    assert len(vals) == n
    mu = sum(vals) / n
    sd = (sum((v - mu) ** 2 for v in vals) / (n - 1)) ** 0.5
    assert abs(mu - 100.0) < 0.02, mu
    assert abs(sd - 10.0) < 0.02, f"{sd} points per SHRUNK-pool sigma, want 10"


def test_adj_pulls_thin_samples_toward_average(monkeypatch):
    """The whole reason the column exists: a hot short sample must not outrank a
    strong full season once the rate is regressed for playing time."""
    rows = [{"mlbam": 1, "pa": 110.0},            # hot but thin
            {"mlbam": 2, "pa": 600.0}]            # strong and full
    rows += [{"mlbam": 100 + i, "pa": 300.0 + i} for i in range(40)]
    bat = {1: 1.9, 2: 6.0}
    bat.update({100 + i: 1.0 + i * 0.01 for i in range(40)})
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    he._join_war_pa_plus(rows, 2026)
    thin, full = rows[0], rows[1]
    assert thin["war_pa_plus"] > full["war_pa_plus"], (
        "precondition: unadjusted must favour the hot thin sample")
    assert full["war_pa_plus_adj"] > thin["war_pa_plus_adj"], (
        "adjusted must favour the full season")
    # and the raw column must be untouched by the companion's existence
    assert thin["war_pa_plus"] == int(round(thin["war_pa_plus_raw"]))


def test_raw_column_still_reproduces_the_rate_on_the_row(monkeypatch):
    """The reason _adj got its own NAME rather than replacing the column: the raw
    index must stay checkable from the row's own war and denominator against the
    published pool_mean_rate / pool_sd_rate. The adjusted one deliberately does
    not reproduce anything on the row, which is exactly why it is a new column.

    The check is approximate, and its error bound is not slack: TWO display
    roundings sit between the row and the identity. The served `war` is rounded
    to one decimal, so the recomputed rate can be off by up to 0.05 WAR over the
    denominator (10 * 0.05 / (denom * pool_sd) index points), and `*_raw` is
    itself rounded to one decimal (another 0.05). The bound is derived from both
    rather than hardcoded, so if a rounding convention or the scale ever changes
    the bound moves with it instead of silently going slack."""
    n = 40
    rows = [{"mlbam": 1000 + i, "pa": 400.0 + i} for i in range(n)]
    bat = {1000 + i: 1.0 + i * 0.05 for i in range(n)}
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    for r in rows:
        expect = (100.0 + 10.0 * ((r["war"] / r["pa"]) - meta["pool_mean_rate"])
                  / meta["pool_sd_rate"])
        bound = 10.0 * 0.05 / (r["pa"] * meta["pool_sd_rate"]) + 0.05
        assert abs(r["war_pa_plus_raw"] - expect) <= bound, (
            r["mlbam"], r["war_pa_plus_raw"], expect, bound)


def test_one_year_percentile_chip_is_midrank_over_served_rows(monkeypatch):
    """Mirrors war_rate_plus_lab._pct_map so the 1yr chip and the 3yr chip mean
    the same thing on the same row. Added because a 10-points-per-sigma scale
    hides how rare a modest-looking number is."""
    n = 50
    rows = [{"mlbam": 1000 + i, "pa": 400.0} for i in range(n)]
    bat = {1000 + i: 0.5 + i * 0.1 for i in range(n)}       # strictly increasing
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    he._join_war_pa_plus(rows, 2026)
    pcts = [r["war_pa_plus_pct"] for r in rows]
    assert all(p is not None for p in pcts)
    assert min(pcts) >= 0 and max(pcts) <= 100
    # monotone in the underlying value, and the best row is at the top
    best = max(rows, key=lambda r: r["war_pa_plus_raw"])
    assert best["war_pa_plus_pct"] >= 99, best["war_pa_plus_pct"]


def test_no_clamp_a_real_outlier_prints_past_the_band(monkeypatch):
    """True-to-model policy: no silent clamp. If a display cap is ever wanted it
    goes in as the AP+ two-field pattern, not as a clamp here."""
    rows = [{"mlbam": 1, "pa": 500.0}] + [
        {"mlbam": 100 + i, "pa": 500.0} for i in range(40)]
    bat = {1: 9.0}
    bat.update({100 + i: 1.0 + i * 0.01 for i in range(40)})
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    he._join_war_pa_plus(rows, 2026)
    assert rows[0]["war_pa_plus"] > 160, rows[0]["war_pa_plus"]


# --------------------------------------------------------------------------- #
# the WAR source
# --------------------------------------------------------------------------- #
def test_two_way_player_keeps_the_sides_apart(monkeypatch):
    """A two-way player carries BATTING WAR over his PA on the hitter board and
    PITCHING WAR over his IP on a pitcher board. Never a summed side: summing is
    what fa_projection._war_age_maps does, and it would divide his pitching WAR by
    his plate appearances."""
    two_way = 660271
    war = _war_map(2026,
                   bat={two_way: 4.0, **{i: 1.0 + i * 0.001 for i in range(40)}},
                   pit={two_way: 3.0, **{i: 1.0 + i * 0.001 for i in range(40)}})
    _patch_war(monkeypatch, war)
    hit_rows = [{"mlbam": two_way, "pa": 500.0}] + [
        {"mlbam": i, "pa": 400.0} for i in range(40)]
    sp_rows = [{"mlbam": two_way, "ip": 100.0}] + [
        {"mlbam": i, "ip": 120.0} for i in range(40)]
    he._join_war_pa_plus(hit_rows, 2026)
    se._join_war_ip_plus(sp_rows, 2026)
    # the hitter row used batting WAR, the starter row used pitching WAR
    assert hit_rows[0]["war"] == 4.0
    assert sp_rows[0]["war"] == 3.0
    # and both boards carry him, with two different indexes
    assert hit_rows[0]["war_pa_plus"] is not None
    assert sp_rows[0]["war_ip_plus"] is not None


def test_missing_bwar_row_leaves_the_field_absent(monkeypatch):
    """Absent is not zero. A player with no WAR row must render blank, never as
    a real replacement-level season."""
    rows = [{"mlbam": 500 + i, "pa": 400.0} for i in range(40)]
    rows.append({"mlbam": 999999, "pa": 400.0})       # no WAR row
    rows.append({"pa": 400.0})                        # no mlbam at all
    bat = {500 + i: 1.0 + i * 0.05 for i in range(40)}
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["n_stamped"] == 40
    assert "war_pa_plus" not in rows[-1] and "war" not in rows[-1]
    assert "war_pa_plus" not in rows[-2] and "war" not in rows[-2]


def test_degenerate_bwar_fetch_is_refused(monkeypatch):
    """A silent WAR-fetch failure must be DETECTED and refused, never served as a
    board of zeros (the fa_projection.py:191-201 pattern)."""
    rows = [{"mlbam": 500 + i, "pa": 400.0} for i in range(40)]
    _patch_war(monkeypatch, {})                     # empty map = failed fetch
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"] is False and meta["n_stamped"] == 0
    assert "refused" in meta
    assert all("war_pa_plus" not in r for r in rows)

    # a raising fetch is refused the same way, and never propagates
    def _boom():
        raise RuntimeError("pybaseball down")
    monkeypatch.setattr(be, "_side_war_by_season", _boom)
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"] is False and "refused" in meta


def test_thin_coverage_is_refused_not_anchored(monkeypatch):
    """Coverage under the floor means the pool would be anchored on a handful of
    rows. Refuse instead."""
    rows = [{"mlbam": 500 + i, "pa": 400.0} for i in range(40)]
    bat = {500 + i: 1.0 + i * 0.05 for i in range(5)}   # 5 of 40 covered
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"] is False and "refused" in meta


# --------------------------------------------------------------------------- #
# two-tier volume floors
# --------------------------------------------------------------------------- #
def test_two_tier_floors_pool_anchors_display_gate_publishes(monkeypatch):
    """Pool floor 50 PA contributes to mu/sd; only 100+ PA gets a value. Two
    tiers, not one unified floor, and never no gate at all (the registered SC+
    defect)."""
    rows = ([{"mlbam": 100 + i, "pa": 400.0} for i in range(30)]
            + [{"mlbam": 200 + i, "pa": 70.0} for i in range(10)]     # pool only
            + [{"mlbam": 300 + i, "pa": 20.0} for i in range(10)])    # neither
    bat = {}
    bat.update({100 + i: 1.0 + i * 0.05 for i in range(30)})
    bat.update({200 + i: 0.2 for i in range(10)})
    bat.update({300 + i: 0.1 for i in range(10)})
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["pool_n"] == 40, meta["pool_n"]        # 30 regulars + 10 part-time
    assert meta["n_stamped"] == 30                      # only the 100+ PA rows
    assert all("war_pa_plus" not in r for r in rows if r["pa"] < 100)
    assert meta["pool_min"] == 50.0 and meta["display_min"] == 100.0


def test_sub_floor_rows_carry_war_but_never_the_index(monkeypatch):
    """E1 (MLB Stats overhaul, wave 0). eWAR is a counting stat, so it prints
    for every covered row with a positive denominator, while the RATE index and
    its companions stay behind the display gate. A row with WAR but no
    denominator gets no `war` (constraint b), and an uncovered row stays blank
    (absent, never zero)."""
    rows = ([{"mlbam": 100 + i, "pa": 400.0} for i in range(30)]
            + [{"mlbam": 200 + i, "pa": 70.0} for i in range(10)]     # pool only
            + [{"mlbam": 300 + i, "pa": 20.0} for i in range(10)]     # neither
            + [{"mlbam": 400, "pa": 0.0},                             # no denominator
               {"mlbam": 401},                                        # no pa field
               {"mlbam": 999999, "pa": 70.0}])                        # no WAR cell
    bat = {}
    bat.update({100 + i: 1.0 + i * 0.05 for i in range(30)})
    bat.update({200 + i: 0.24 for i in range(10)})
    bat.update({300 + i: -0.16 for i in range(10)})
    bat.update({400: 0.3, 401: 0.3})
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["n_stamped"] == 30 and meta["n_war"] == 50
    for r in rows[30:50]:
        assert r["war"] == round(bat[r["mlbam"]], 1), r
        for k in ("war_pa_plus", "war_pa_plus_raw", "war_pa_plus_adj",
                  "war_pa_plus_adj_raw", "war_pa_plus_pct"):
            assert k not in r, (r["mlbam"], k)
    assert rows[40]["war"] == -0.2                 # a negative count is still a count
    for r in rows[50:]:
        assert "war" not in r and "war_pa_plus" not in r, r
    # the 1-year chip ranks the SERVED index rows only, never the sub-floor war rows
    assert sum(1 for r in rows if "war_pa_plus_pct" in r) == 30


def test_sub_floor_reliever_carries_war_below_the_30_ip_gate(monkeypatch):
    """The same rule on a pitcher board: a 25-inning reliever sits in the pool
    (20+ IP) but under the 30-IP display gate, and a 12-inning arm is in
    neither. Both print their pitching eWAR; neither gets WAR/IP+."""
    rp = ([{"mlbam": 200 + i, "ip": 60.0} for i in range(30)]
          + [{"mlbam": 1, "ip": 25.0}, {"mlbam": 2, "ip": 12.0}])
    war = _war_map(2026, pit={**{200 + i: 0.5 + i * 0.03 for i in range(30)},
                              1: 0.44, 2: -0.31},
                   bat={2: 1.5})                    # a batting side is never read here
    _patch_war(monkeypatch, war)
    meta = be._join_war_ip_plus(rp, 2026)
    assert meta["available"] and meta["n_stamped"] == 30 and meta["n_war"] == 32
    assert rp[30]["war"] == 0.4 and "war_ip_plus" not in rp[30]
    assert rp[31]["war"] == -0.3 and "war_ip_plus" not in rp[31]


def test_a_refused_pool_stamps_no_war_anywhere(monkeypatch):
    """The refusal is the degenerate-fetch detector: a board of a few surviving
    WAR values is the failure it stops, so widening `war` must not leak past it."""
    rows = [{"mlbam": 500 + i, "pa": 400.0} for i in range(40)]
    bat = {500 + i: 1.0 + i * 0.05 for i in range(5)}   # 5 of 40 covered
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    meta = he._join_war_pa_plus(rows, 2026)
    assert meta["available"] is False and meta["n_war"] == 0
    assert all("war" not in r for r in rows)


def test_stamp_side_war_reads_one_side_and_one_rule(monkeypatch):
    """The helper the two-way card rows use: the named side only, a positive
    denominator only, absent never zero, and a raising fetch stamps nothing."""
    war = _war_map(2026, bat={660271: 4.04, 7: 1.0}, pit={660271: 2.96, 8: 0.5})
    _patch_war(monkeypatch, war)
    rows = [{"mlbam": 660271, "ip": 85.7}, {"mlbam": 7, "ip": 30.0},
            {"mlbam": 8, "ip": 0.0}, {"ip": 10.0}]
    assert be.stamp_side_war(rows, 2026, side="pit", denom_key="ip") == 1
    assert rows[0]["war"] == 3.0                     # pitching, never 7.0 or 4.0
    assert all("war" not in r for r in rows[1:])

    def _boom():
        raise RuntimeError("pybaseball down")
    monkeypatch.setattr(be, "_side_war_by_season", _boom)
    fresh = [{"mlbam": 660271, "ip": 85.7}]
    assert be.stamp_side_war(fresh, 2026, side="pit", denom_key="ip") == 0
    assert "war" not in fresh[0]


def test_a_rounded_zero_war_serves_zero_never_negative_zero(monkeypatch):
    """The house -0 rule holds in the SERVED JSON, not only in the page
    formatter: a small negative eWAR rounds to 0.0 through both stamps, so no
    reader of the artifact (the player-card pass-through, a later sum of the
    two sides) meets a -0.0."""
    rows = ([{"mlbam": 100 + i, "pa": 400.0} for i in range(30)]
            + [{"mlbam": 1, "pa": 70.0}])
    bat = {100 + i: 1.0 + i * 0.05 for i in range(30)}
    bat[1] = -0.04
    _patch_war(monkeypatch, _war_map(2026, bat=bat))
    he._join_war_pa_plus(rows, 2026)
    assert rows[-1]["war"] == 0.0 and str(rows[-1]["war"]) == "0.0"
    assert json.dumps(rows[-1]["war"]) == "0.0"

    _patch_war(monkeypatch, _war_map(2026, pit={9: -0.04}))
    card = [{"mlbam": 9, "ip": 20.0}]
    assert be.stamp_side_war(card, 2026, side="pit", denom_key="ip") == 1
    assert str(card[0]["war"]) == "0.0"


def test_stamp_side_war_skips_a_row_it_cannot_read(monkeypatch):
    """A payload build must not abort over one malformed id: the row is left
    blank and the rest of the block is stamped."""
    _patch_war(monkeypatch, _war_map(2026, pit={5: 1.24}))
    rows = [{"mlbam": "not-an-id", "ip": 30.0}, {"mlbam": 5, "ip": 30.0}]
    assert be.stamp_side_war(rows, 2026, side="pit", denom_key="ip") == 1
    assert "war" not in rows[0] and rows[1]["war"] == 1.2


def _sp_line(pid: int, so: int, *, gs: int = 22, ip: str = "130.0", pos=None) -> dict:
    """One flat StatsAPI pitching row (bullpen_export.rows_from_pitching_splits
    shape) for an offline starter export."""
    row = {"mlbam": pid, "name": f"Arm {pid}", "team": "LAA", "G": gs, "GS": gs,
           "SV": 0, "HLD": 0, "IP": ip, "ER": 55, "R": 60, "BB": 40, "SO": so,
           "HR": 15, "HBP": 5, "BF": 560, "Pit": 2100, "IR": 0, "IRS": 0,
           "CG": 0, "GO": 160, "AO": 130, "Strk": 1350}
    if pos:
        row["pos"] = pos
    return row


def _offline_starter_export(monkeypatch, tmp_path, war) -> dict:
    lines = [_sp_line(1000 + i, 100 + 3 * i) for i in range(40)]
    lines.append(_sp_line(660271, 105, gs=14, ip="85.2", pos="TWP"))
    monkeypatch.setattr(se, "load_season_pitching", lambda season, positions=("P",): [
        dict(r) for r in lines if (r.get("pos") or "P") in positions])
    monkeypatch.setattr(se, "_active_mlbam_ids", lambda season: None)
    monkeypatch.setattr(se, "_join_sem_plus_3yr", lambda s: {"n_stamped": 0})
    monkeypatch.setattr(se, "_join_xsem_plus", lambda s, season: 0)
    monkeypatch.setattr(se, "_join_war_ip_plus_3yr", lambda s: {"n_stamped": 0})
    monkeypatch.setattr(se, "_war_source_vintage", lambda as_of=None: {"as_of": as_of})
    monkeypatch.setattr(se, "guard_nonempty_block",
                        lambda fresh, out_path, **kw: (fresh, {"n": len(fresh)}))
    _patch_war(monkeypatch, war)
    out = tmp_path / "starter_leaderboards.json"
    se.export(2026, out_path=out, log=lambda *a, **k: None, today="2026-09-11")
    return json.loads(out.read_text(encoding="utf-8"))


def test_the_two_way_starter_row_carries_its_pitching_war(monkeypatch, tmp_path):
    """E1b. The two-way starter's row carries his PITCHING eWAR, the side that
    matches the innings beside it (his batting side rides the hitter board).
    Found wherever the export puts him: starters[] while two-way lines are
    admitted to the board (ADMIT_TWO_WAY_TO_BOARD, owner decision 2026-09-11),
    the card-only block while they are not. Exactly one row either way, so the
    card never double-counts the board."""
    war = _war_map(2026, pit={**{1000 + i: 1.0 + i * 0.05 for i in range(40)},
                              660271: 2.96},
                   bat={660271: 4.04})
    d = _offline_starter_export(monkeypatch, tmp_path, war)
    assert d["ewar_vintage"] == {"as_of": "2026-09-11"}, "the payload's as_of rides in"
    rows = [r for r in d["starters"] + (d.get("two_way_card_only") or {}).get("starters", [])
            if r.get("mlbam") == 660271]
    assert len(rows) == 1, rows
    assert rows[0]["war"] == 3.0, "pitching, never the 4.0 batting side"
    if rows[0].get("card_only"):
        assert d["two_way_card_only"]["n_war"] == 1
        assert "war_ip_plus" not in rows[0], "the card row gets the count, not an index"
    else:
        assert d["two_way"]["mlbam"] == [660271], "the board names the line it admitted"
        assert (d["two_way_card_only"].get("starters") or []) == []


def test_the_card_only_row_carries_its_pitching_war_with_the_flag_off(monkeypatch,
                                                                     tmp_path):
    """The same rule through the other door. With ADMIT_TWO_WAY_TO_BOARD False
    the two-way line is scored for its card alone, and that row carries the
    pitching count (stamp_side_war) and no index, because it never entered the
    scored pool that publishes one."""
    monkeypatch.setattr(se, "ADMIT_TWO_WAY_TO_BOARD", False)
    war = _war_map(2026, pit={**{1000 + i: 1.0 + i * 0.05 for i in range(40)},
                              660271: 2.96},
                   bat={660271: 4.04})
    d = _offline_starter_export(monkeypatch, tmp_path, war)
    assert all(r.get("mlbam") != 660271 for r in d["starters"]), "off the board"
    tw = d["two_way_card_only"]
    assert tw["n_war"] == 1 and tw["n"] == 1
    row = tw["starters"][0]
    assert row["mlbam"] == 660271 and row["war"] == 3.0
    assert "war_ip_plus" not in row, "the card row gets the count, not an index"


def test_a_refused_starter_pool_leaves_the_two_way_row_blank(monkeypatch, tmp_path):
    d = _offline_starter_export(monkeypatch, tmp_path, {})
    assert d["war_rate"]["available"] is False
    tw = d.get("two_way_card_only") or {}
    assert "n_war" not in tw
    assert all("war" not in r for r in d["starters"] + tw.get("starters", []))


def test_a_refused_pool_leaves_the_card_only_row_blank_with_the_flag_off(monkeypatch,
                                                                        tmp_path):
    monkeypatch.setattr(se, "ADMIT_TWO_WAY_TO_BOARD", False)
    d = _offline_starter_export(monkeypatch, tmp_path, {})
    assert d["war_rate"]["available"] is False
    tw = d["two_way_card_only"]
    assert tw["n"] == 1 and "n_war" not in tw, "scored, but no WAR was stamped"
    assert all("war" not in r for r in tw["starters"])


def test_pitcher_floors_differ_by_role():
    assert be.WAR_RATE_POOL_MIN_IP == 20.0
    assert be.WAR_RATE_DISPLAY_MIN_SP_IP == 40.0
    assert be.WAR_RATE_DISPLAY_MIN_RP_IP == 30.0
    # the two pitcher surfaces must not share one gate or one pool
    assert be.WAR_RATE_DISPLAY_MIN_SP_IP != be.WAR_RATE_DISPLAY_MIN_RP_IP


def test_starter_and_reliever_pools_are_anchored_separately(monkeypatch):
    """Same field name, two payloads, two anchor pools. The identical raw rate
    must index differently on the two boards, because a reliever banks more WAR
    per inning than a starter of equal talent
    (ARKMETRIC_SCALE_CONVENTIONS.md:77)."""
    war = _war_map(2026,
                   pit={**{100 + i: 2.0 + i * 0.05 for i in range(30)},
                        **{200 + i: 1.0 + i * 0.02 for i in range(30)},
                        7: 1.0})
    _patch_war(monkeypatch, war)
    sp = [{"mlbam": 7, "ip": 100.0}] + [{"mlbam": 100 + i, "ip": 150.0}
                                        for i in range(30)]
    rp = [{"mlbam": 7, "ip": 100.0}] + [{"mlbam": 200 + i, "ip": 60.0}
                                        for i in range(30)]
    m_sp = se._join_war_ip_plus(sp, 2026)
    m_rp = be._join_war_ip_plus(rp, 2026)
    assert m_sp["anchor"] != m_rp["anchor"]
    assert "starters" in m_sp["anchor"] and "relievers" in m_rp["anchor"]
    # the SAME player at the SAME rate scores differently on the two boards
    assert sp[0]["war_ip_plus"] != rp[0]["war_ip_plus"]


# --------------------------------------------------------------------------- #
# the frozen 3-year vintage
# --------------------------------------------------------------------------- #
def test_frozen_3yr_join_stamps_and_discloses(tmp_path, monkeypatch):
    art = {"generated_at": "2026-07-29", **be.served_war_basis(),
           "proposed_values": {"hit": {
               "season": 2026, "window": [2024, 2025, 2026],
               "anchor_pool": "hitters with 50+ PA",
               "players": {"670541": {"war_pa_plus_3yr": 131, "pct": 97,
                                      "tag": "established"},
                           "111111": {"war_pa_plus_3yr": 104, "pct": 60,
                                      "tag": "provisional"}}}}}
    p = tmp_path / "war_rate_plus_multiyear_eval.json"
    p.write_text(json.dumps(art), encoding="utf-8")
    monkeypatch.setattr(be, "WAR_RATE_MULTIYR_PATH", p)

    rows = [{"mlbam": 670541}, {"mlbam": 111111}, {"mlbam": 222222}, {}]
    meta = he._join_war_pa_plus_3yr(rows)
    assert meta["available"] and meta["n_stamped"] == 2
    assert rows[0]["war_pa_plus_3yr"] == 131
    assert rows[0]["war_pa_plus_3yr_pct"] == 97
    assert rows[0]["war_pa_plus_3yr_tag"] == "established"
    assert rows[1]["war_pa_plus_3yr_tag"] == "provisional"
    assert "war_pa_plus_3yr" not in rows[2] and "war_pa_plus_3yr" not in rows[3]
    # the vintage block must disclose that this is FROZEN and as-of generated_at
    assert meta["generated_at"] == "2026-07-29"
    assert meta["window"] == [2024, 2025, 2026]
    assert "FROZEN" in meta["note"] and "generated_at" in meta["note"]
    assert meta["n_in_artifact"] == 2
    assert meta["war_provider"] == be._served_war_provider()
    assert meta["ewar_generated_at"] == be.served_war_basis()["ewar_generated_at"]

    # missing artifact is a clean no-op, never an exception
    monkeypatch.setattr(be, "WAR_RATE_MULTIYR_PATH", tmp_path / "nope.json")
    assert he._join_war_pa_plus_3yr(rows)["available"] is False


def test_three_blocks_are_three_metrics(tmp_path, monkeypatch):
    """One artifact, three blocks, because the three anchor pools are three
    metrics. A join must read its OWN block."""
    art = {"generated_at": "2026-07-29", **be.served_war_basis(),
           "proposed_values": {
        "hit": {"players": {"1": {"war_pa_plus_3yr": 120, "pct": 90, "tag": "established"}}},
        "sp": {"players": {"1": {"war_ip_plus_3yr": 80, "pct": 10, "tag": "established"}}},
        "rp": {"players": {"1": {"war_ip_plus_3yr": 111, "pct": 70, "tag": "established"}}},
    }}
    p = tmp_path / "war_rate_plus_multiyear_eval.json"
    p.write_text(json.dumps(art), encoding="utf-8")
    monkeypatch.setattr(be, "WAR_RATE_MULTIYR_PATH", p)
    h, s, r = [{"mlbam": 1}], [{"mlbam": 1}], [{"mlbam": 1}]
    he._join_war_pa_plus_3yr(h)
    se._join_war_ip_plus_3yr(s)
    be._join_war_ip_plus_3yr(r)
    assert h[0]["war_pa_plus_3yr"] == 120
    assert s[0]["war_ip_plus_3yr"] == 80
    assert r[0]["war_ip_plus_3yr"] == 111


def test_3yr_join_refuses_an_artifact_on_another_war_basis(tmp_path, monkeypatch):
    """Audit F10-01. From the 2026-09-03 epoch the 1-year columns read eWAR while
    the lab kept writing bWAR, and the pair sat on one board under copy asserting
    one scale (4 to 5 points apart on the pitcher boards). The join now refuses
    any artifact whose provider is not the one the 1-year column serves; an
    UNSTAMPED artifact predates the stamp and is bWAR, so it is refused too.
    Blank is honest, a mixed-basis pair is not."""
    players = {"1": {"war_ip_plus_3yr": 111, "pct": 70, "tag": "established"}}
    p = tmp_path / "war_rate_plus_multiyear_eval.json"
    monkeypatch.setattr(be, "WAR_RATE_MULTIYR_PATH", p)
    for stamp in ({}, {"war_provider": "bwar"}):
        p.write_text(json.dumps({"generated_at": "2026-09-04", **stamp,
                                 "proposed_values": {"rp": {"players": players}}}),
                     encoding="utf-8")
        r = [{"mlbam": 1}]
        meta = be._join_war_ip_plus_3yr(r)
        assert meta["available"] is False and meta["n_stamped"] == 0, stamp
        assert "refused" in meta and "war_rate_plus_lab" in meta["refused"]
        assert "war_ip_plus_3yr" not in r[0], "a mixed-basis value was served"
    # and the served basis is accepted
    p.write_text(json.dumps({"generated_at": "2026-09-11", **be.served_war_basis(),
                             "proposed_values": {"rp": {"players": players}}}),
                 encoding="utf-8")
    r = [{"mlbam": 1}]
    assert be._join_war_ip_plus_3yr(r)["available"] is True
    assert r[0]["war_ip_plus_3yr"] == 111


def test_3yr_join_refuses_an_artifact_on_another_ewar_build(tmp_path, monkeypatch):
    """F10-01 must not recur INSIDE one provider. A full eWAR rebuild (the
    WAR_BASIS_RUNBOOK cascade) can re-price completed seasons while the provider
    id stays ewar_v2, so a provider-only check would serve the frozen 3-year
    values on the old build beside a 1-year column on the new one. The artifact
    stamps the eWAR build (the eWAR payload's generated_at, which the nightly
    live-season rebuild does not move), and the join refuses a mismatch."""
    players = {"1": {"war_ip_plus_3yr": 111, "pct": 70, "tag": "established"}}
    p = tmp_path / "war_rate_plus_multiyear_eval.json"
    monkeypatch.setattr(be, "WAR_RATE_MULTIYR_PATH", p)
    monkeypatch.setattr(be, "served_war_basis", lambda: {
        "war_provider": "ewar_v2", "ewar_generated_at": "2026-10-01T09:00:00"})
    p.write_text(json.dumps({"generated_at": "2026-09-11", "war_provider": "ewar_v2",
                             "ewar_generated_at": "2026-09-03T12:35:09",
                             "proposed_values": {"rp": {"players": players}}}),
                 encoding="utf-8")
    r = [{"mlbam": 1}]
    meta = be._join_war_ip_plus_3yr(r)
    assert meta["available"] is False and "refused" in meta
    assert "2026-09-03T12:35:09" in meta["refused"] and "2026-10-01T09:00:00" in meta["refused"]
    assert "war_ip_plus_3yr" not in r[0], "a value on a stale eWAR build was served"


def test_served_war_basis_names_the_frozen_build_not_the_nightly():
    """The build identity is the eWAR payload's own generated_at (the frozen
    series), never war_source.ewar_vintage()'s artifact_generated_at, which the
    nightly rebuild turns into the live season's build time."""
    import inspect
    src = inspect.getsource(be.served_war_basis)
    body = src.split('"""', 2)[2]
    assert ".get(\"generated_at\")" in body
    assert "ewar_vintage" not in body and "live_built_at" not in body
    b = be.served_war_basis()
    assert set(b) == {"war_provider", "ewar_generated_at"}


def test_the_lab_reads_the_served_war_provider():
    """The lab's frames come through war_source on the provider the 1-year
    columns serve, never from pybaseball directly (that direct read is how the
    3-year columns stayed bWAR after the epoch)."""
    import sys
    sys.path.insert(0, str(ROOT / "tools"))
    import war_rate_plus_lab as lab
    assert lab.war_provider() == be._served_war_provider()
    assert lab.served_war_basis() == be.served_war_basis()
    src = (ROOT / "tools" / "war_rate_plus_lab.py").read_text(encoding="utf-8")
    body = src.split("def load_frames", 1)[1].split("\ndef ", 1)[0]
    assert "pyb.bwar" not in body and "import pybaseball" not in body


def test_the_served_3yr_artifact_shares_the_1yr_basis():
    """The committed multiyear artifact must carry the served basis (provider
    AND eWAR build), or the join blanks all three 3-year columns. A failure here
    means the lab was not re-run after a basis change or an eWAR hand rebuild:
    python tools/war_rate_plus_lab.py."""
    served = be.served_war_basis()
    art = json.loads((ROOT / "data" / "war_rate_plus_multiyear_eval.json")
                     .read_text(encoding="utf-8"))
    got = {"war_provider": art.get("war_provider") or "bwar",
           "ewar_generated_at": art.get("ewar_generated_at")}
    assert got == served, f"multiyear artifact measured on {got}, served {served}"
    ev = json.loads((ROOT / "data" / "war_rate_plus_eval.json")
                    .read_text(encoding="utf-8"))
    assert {"war_provider": ev.get("war_provider") or "bwar",
            "ewar_generated_at": ev.get("ewar_generated_at")} == served


# --------------------------------------------------------------------------- #
# plumbing: the ship checklist
# --------------------------------------------------------------------------- #
_JS = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
_GLOSSARY_IDS = {e["id"] for e in json.loads(
    (ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))["entries"]}
_WAR_RATE_TERMS = ("war_pa_plus", "war_pa_plus_3yr", "war_ip_plus_sp",
                   "war_ip_plus_sp_3yr", "war_ip_plus_rp", "war_ip_plus_rp_3yr",
                   # sample-adjusted companions, owner call closed 2026-07-30
                   "war_pa_plus_adj", "war_ip_plus_sp_adj", "war_ip_plus_rp_adj")


def test_every_column_term_slug_has_a_glossary_entry():
    for slug in _WAR_RATE_TERMS:
        assert f'term: "{slug}"' in _JS, f"no column wired to {slug}"
        assert slug in _GLOSSARY_IDS, f"column term {slug} has no glossary entry"


def test_glossary_entries_name_their_anchor_pool():
    """The two WAR/IP+ entries exist precisely so a reader is told WHICH pool the
    100 refers to. If either stops saying so, the pair becomes ambiguous."""
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    by = {e["id"]: e for e in g["entries"]}
    for slug in _WAR_RATE_TERMS:
        e = by[slug]
        assert e["category"] == "custom-index" and e["shelf"] == "ark"
        assert "eephus.io" in e["origin"]
        assert "mlbstats" in e["module"]
        blob = (e["definition"] + " " + e.get("methodology", "")).lower()
        # the compound adjective form ("ten-points-per-standard-deviation") counts
        assert "standard deviation" in blob or "standard-deviation" in blob, slug
    assert "starter" in by["war_ip_plus_sp"]["definition"].lower()
    assert "reliever" in by["war_ip_plus_rp"]["definition"].lower()


def test_war_rate_columns_are_dropped_from_history_boards():
    """The RATES are standardised on the live pool, so a past-season board drops
    them rather than rendering a blank column. eWAR itself is not a rate: it is a
    season count the history exports join per (player, season) (E6 of the MLB
    Stats overhaul, 2026-09-11), so `war` stays on all four history boards."""
    hit = _JS.split("var HITTER_HISTORY_DROP =")[1].split(";")[0]
    sp = _JS.split("var STARTER_HISTORY_DROP =")[1].split(";")[0]
    rel = _JS.split("var REL_HISTORY_KEYS =")[1].split(";")[0]
    for k in ("war_pa_plus", "war_pa_plus_adj", "war_pa_plus_3yr"):
        assert k + ": 1" in hit, f"{k} not dropped from the hitter history board"
    for k in ("war_ip_plus", "war_ip_plus_adj", "war_ip_plus_3yr"):
        assert k + ": 1" in sp, f"{k} not dropped from the starter history board"
    assert "war: 1" not in hit and "war: 1" not in sp, "the count is not a rate"
    # the reliever map is an ALLOW-list: the RATE keys must be ABSENT from it,
    # and the count key must be IN it
    for k in ("war_ip_plus", "war_ip_plus_adj", "war_ip_plus_3yr"):
        assert k not in rel, f"{k} leaked into the reliever history allow-list"
    assert "war: 1" in rel, "eWAR missing from the reliever history allow-list"


def test_war_rate_columns_use_remcell_not_hemcell():
    """100 + 10z has SD exactly 10, so the +-2-sigma read is 80/120 (remClass).
    hemCell bands for the wRC+-width ratio family and would call a 1.2-sigma
    hitter average. The hitter board is the trap: every column around WAR/PA+
    uses hemCell."""
    for key in ("war_pa_plus", "war_pa_plus_3yr", "war_ip_plus", "war_ip_plus_3yr"):
        marker = 'key: "%s", label:' % key
        starts = [i for i in range(len(_JS))
                  if _JS.startswith(marker, i)]
        assert starts, f"no column definition for {key}"
        for i in starts:
            # the column object ends at the next definition or the array close
            nxt = _JS.find('{ key: "', i)
            body = _JS[i:nxt if nxt > i else i + 1200]
            assert "remCell(" in body, f"{key} column not on remCell"
            assert "hemCell(" not in body, f"{key} column uses hemCell"


def test_registry_rows_and_glossary_map():
    import model_registry as mr
    import test_methodology_freshness as tmf
    ids = {m["model_id"] for m in mr.load()["models"]}
    for mid in ("war_pa_plus", "war_ip_plus_sp", "war_ip_plus_rp",
                "war_rate_plus_3yr"):
        assert mid in ids, f"registry row missing: {mid}"
        assert mid in tmf.MODEL_GLOSSARY, f"MODEL_GLOSSARY mapping missing: {mid}"


def test_registry_verdict_matches_the_measured_gate():
    """A display index with no forward win ships `unvalidated` with a null
    artifact, and the measurement ledger is cited on the row instead. Validated
    if and only if the artifact is attached, in both directions."""
    import model_registry as mr
    rows = {m["model_id"]: m for m in mr.load()["models"]}
    art = json.loads((ROOT / "data" / "war_rate_plus_eval.json")
                     .read_text(encoding="utf-8"))
    g2 = art["verdict"]["g2_by_pool"]
    pool_of = {"war_pa_plus": "hit", "war_ip_plus_sp": "SP",
               "war_ip_plus_rp": "RP"}
    for mid, pool in pool_of.items():
        row = rows[mid]
        if g2.get(pool):
            assert row["eval_artifact"], f"{mid} passed G2 but carries no artifact"
            assert row["verdict"] in ("validated", "provisional")
        else:
            assert row["verdict"] == "unvalidated", mid
            assert not row["eval_artifact"], mid
            assert "war_rate_plus_eval.json" in row["notes"], (
                f"{mid}: the ledger must be cited so the artifact stays "
                f"registered (test_model_registry.py globs data/*_eval*.json)")


def test_eval_artifact_proves_the_scale():
    """The artifact carries the measured points-per-anchor-pool-sigma for each of
    the three pools, so the scale claim on the board is checkable."""
    art = json.loads((ROOT / "data" / "war_rate_plus_eval.json")
                     .read_text(encoding="utf-8"))
    assert art["conventions"]["shrink"].startswith("NONE")
    assert art["conventions"]["clamp"] == "none (true-to-model policy)"
    for pool in ("hit", "SP", "RP"):
        chk = art["pools"][pool]["live_season_scale_check"]
        assert abs(chk["measured_points_per_anchor_pool_sigma"] - 10.0) < 0.01, pool
        assert chk["advertised_points_per_sigma"] == 10.0
