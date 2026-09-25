# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""The league anchors under /fantasy/#m=dfs and the streamer board, and the
laws whose absence let four of them ship wrong (audit L17, 2026-09-10).

1. `_PA_PER_START` was 4.15 and the league is 4.0169. Nine starters at 4.15 take
   37.35 of the 37.86 plate appearances a club gets in a game, leaving 0.51 for
   every substitute combined against a measured 1.70. That is an arithmetic
   check, not a modelling opinion, and nothing in the suite was making it. Every
   line conditional on a start was about 3.2% long and every start rate about
   3.1% short.

2. THE PLATE APPEARANCE IDENTITY WAS NOT AN IDENTITY. The DFS matchup and park
   multiplier moved walks and hit batsmen and left the at bat and the plate
   appearance alone, so `ab + bb + hbp` ran past `pa` on 14 of 109 rows on the
   2026-09-10 board. The FanDuel table then charged -0.25 an out (`ab - h`), so the
   break was priced. The at bat now absorbs what the walk took, and the law that
   pins that form also pins its DISCLOSED cost: with the plate appearance held
   fixed, the implied one-game batting average moves by more than the
   multiplier.

3. ONE START, TWO MATCHUP BANDS. The streamer score clamped 100 / Offense+ into
   [0.6, 1.5] while the DFS pitcher line on the SAME served row clamped
   Offense+ / 100 into [0.82, 1.22], and those are not reciprocals. There is one
   band now and one function, and both boards read it.

4. The quality-start hand rule returned 0.26607 at the mean real start against a
   measured league rate of 0.37749. Its level moved; its slopes did not.

The builder laws inject their own inputs. The served-artifact law reads
data/dfs.json and skips ONLY for a board priced at an anchor this module no
longer holds, which is a board an earlier exporter built; a board priced at the
current anchor must carry the receipt and close the identity or it FAILS. The
same law is run against a board built to break it, so a green suite means the
law was exercised rather than merely present.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"

# One rest-of-season hitter vector shaped exactly like fantasy_export._hitter_ros
# builds one: pa = ab + bb + hbp + sf, with the sacrifice fly left implicit
# because the payload does not publish it.
_ROS_HIT = {"pa": 600.0, "ab": 535.2, "bb": 54.0, "hbp": 6.0,
            "h": 150.0, "single": 95.0, "double": 30.0, "triple": 2.0, "hr": 23.0,
            "so": 120.0, "sb": 10.0, "cs": 3.0, "r": 80.0, "rbi": 75.0}
_ROS_SF = 600.0 - 535.2 - 54.0 - 6.0        # 4.8


# ---------------------------------------------------------------------------
# 1. The anchor
# ---------------------------------------------------------------------------
def test_nine_starters_fit_inside_one_team_game():
    """THE CHECK THAT NEEDED NO DATASET, and the one the old anchor failed."""
    import dfs_export as dx
    assert 9 * dx._PA_PER_START < dx._LG_PA_PER_TEAM_GAME
    subs = dx._LG_PA_PER_TEAM_GAME - 9 * dx._PA_PER_START
    assert subs > 1.0, f"only {subs:.2f} PA left for every substitute combined"
    # The value this replaced passes the bare inequality, which is the lesson:
    # the inequality alone is not the law. Nine bats at 4.15 take 37.35 of the
    # 37.85, leaving 0.50 plate appearances for every substitute a club uses in
    # a game, against a measured 1.70. The floor above is the half that bites.
    assert dx._LG_PA_PER_TEAM_GAME - 9 * 4.15 < 0.6


def test_the_anchor_publishes_its_receipt():
    """A constant with a stated basis has to state one that closes."""
    import dfs_export as dx
    b = dx._PA_PER_START_BASIS
    assert b["value"] == dx._PA_PER_START
    lo, hi = b["ci95"]
    assert lo < b["value"] < hi
    assert hi - lo < 0.1
    assert b["n_starter_games"] > 10000 and b["n_games"] > 1000
    assert b["league_pa_per_team_game"] == dx._LG_PA_PER_TEAM_GAME
    assert b["measured_on"] and ".cache" in b["source"]
    # The old hand anchor sits outside the interval. If a later pass re-measures
    # and 4.15 comes back inside it, this line is the one to read first.
    assert not (lo <= 4.15 <= hi)


def test_the_measured_anchors_are_the_measured_numbers():
    """A pin, so a hand edit to any of these arrives with its own count."""
    import dfs_export as dx
    import fantasy_export as fe
    assert dx._PA_PER_START == 4.0169         # 41,148 starter games, 2,286 games
    assert fe._LG_CS_PER_SB == 0.2999         # 929 CS on 3,098 SB
    assert fe._LG_SB_PER_PA == 0.01790        # 3,098 SB in 173,074 PA
    assert fe._LG_HBP_PER_BF_SP == 0.01063    # 1,047 HBP in 98,470 starter BF
    assert fe._LG_HBP_PER_BF_RP == 0.01275    # 951 HBP in 74,604 reliever BF
    assert fe._QS_INTERCEPT == 0.3114
    # There is no single pooled pitcher rate to reach for by accident.
    assert not hasattr(fe, "_LG_HBP_PER_BF")


def test_the_hit_batsman_rate_follows_the_role_that_reads_it():
    """The plan named 0.01072, which is the audit's STARTER subset; the pooled
    all-pitcher rate is 0.01154 and reliever innings are what pull it up. The
    one served betting surface a ROS pitcher line reaches is the props Hits
    allowed fair line, and every row on it is an announced starter, so the
    starter rate is the one that must price a starter."""
    import fantasy_export as fe
    proj = {"k_pct": 0.22, "bb_pct": 0.08, "hr_bf": 0.030, "fip_proj": 4.00}
    sp = fe._pitcher_ros(proj, 800.0, 190.0, "SP", 5.5)
    rp = fe._pitcher_ros(proj, 800.0, 190.0, "RP", None)
    assert sp["hbp"] == round(800.0 * fe._LG_HBP_PER_BF_SP, 1)
    assert rp["hbp"] == round(800.0 * fe._LG_HBP_PER_BF_RP, 1)
    assert sp["hbp"] < rp["hbp"]
    # A hit batsman is a plate appearance that never becomes a ball in play, so
    # a higher rate means FEWER hits allowed. That is the direction the served
    # props Hits allowed line inherits from this constant.
    assert sp["h"] > rp["h"]
    # And the starter rate sits where the audit put it, within its own rounding.
    assert abs(fe._LG_HBP_PER_BF_SP - 0.01072) < 0.0002


# ---------------------------------------------------------------------------
# 2. The plate appearance identity
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("mult", [0.739, 0.85, 1.0, 1.10, 1.178, 1.25])
def test_the_hitter_line_closes_the_plate_appearance_identity(mult):
    import dfs_export as dx
    line, rate = dx._hitter_line(_ROS_HIT, 150, mult)
    assert 0 < rate <= 1.0
    assert line["ab"] + line["bb"] + line["hbp"] <= line["pa"] + 0.005
    # The sacrifice fly is the only thing left over, so the identity does not
    # merely hold, it closes.
    scale = line["pa"] / _ROS_HIT["pa"]
    slack = line["pa"] - line["ab"] - line["bb"] - line["hbp"]
    assert abs(slack - _ROS_SF * scale) < 0.005


def test_the_old_shape_is_what_broke_it():
    """Holding `ab` at its unmultiplied rescale is what put more events in the
    game than there were turns at the plate. Pinned so the fix is not silently
    reverted into something that merely passes the line above by luck."""
    import dfs_export as dx
    line, _ = dx._hitter_line(_ROS_HIT, 150, 1.178)
    scale = line["pa"] / _ROS_HIT["pa"]
    old_ab = _ROS_HIT["ab"] * scale
    assert old_ab + line["bb"] + line["hbp"] > line["pa"]
    assert line["ab"] < old_ab


def test_a_neutral_matchup_moves_nothing():
    """At a multiplier of 1.0 the new arithmetic is the old arithmetic."""
    import dfs_export as dx
    line, _ = dx._hitter_line(_ROS_HIT, 150, 1.0)
    scale = line["pa"] / _ROS_HIT["pa"]
    assert abs(line["ab"] - _ROS_HIT["ab"] * scale) < 0.002


def test_the_matchup_takes_the_at_bat_from_the_walk_not_from_the_turn():
    """The form of the fix, and the cost of the form, in one place.

    Walks rise, the plate appearance does not, so the at bat falls and the
    out (ab - h) falls on BOTH of its terms. That is the whole
    repair. It is also the second half of L17-F5 getting LARGER, and this law
    says so rather than letting it ride: with the turns at the plate held fixed
    and the hit rate scaled, the implied line average h / ab moves by MORE than
    the multiplier. The alternative the audit named (scale `pa` too) keeps the
    rate where the ROS vector put it and is rejected in `_hitter_line`, because
    it would publish a 5.5 plate appearance start and undo the anchor above."""
    import dfs_export as dx
    easy, _ = dx._hitter_line(_ROS_HIT, 150, 1.20)
    hard, _ = dx._hitter_line(_ROS_HIT, 150, 0.85)
    assert easy["pa"] == hard["pa"]          # playing time is not a matchup term
    assert easy["bb"] > hard["bb"]
    assert easy["ab"] < hard["ab"]
    assert easy["out"] < hard["out"]
    ros_avg = _ROS_HIT["h"] / _ROS_HIT["ab"]
    assert easy["h"] / easy["ab"] / ros_avg > 1.20
    assert hard["h"] / hard["ab"] / ros_avg < 0.85


def test_a_ros_vector_without_at_bats_still_prices():
    """The residual cannot be computed without `ab`, and a line that cannot
    close the identity is still a line. It must not raise."""
    import dfs_export as dx
    line, rate = dx._hitter_line({"pa": 600.0, "h": 150.0, "hr": 23.0}, 150, 1.1)
    assert rate > 0 and "ab" not in line


# ---------------------------------------------------------------------------
# 3. One matchup band
# ---------------------------------------------------------------------------
def test_one_matchup_band_for_both_boards():
    import dfs_export as dx
    import fantasy_export as fe
    # One band means one NAME for it. A second module-level copy in dfs_export
    # is how the two drifted apart in the first place.
    assert not hasattr(dx, "_PIT_ALLOW_CLAMP")
    assert dx._HIT_MULT_CLAMP != fe.MATCHUP_CLAMP   # the hitter band is its own
    lo, hi = fe.MATCHUP_CLAMP
    assert abs(1.0 / lo - hi) < 0.001        # reciprocally symmetric
    for idx in (55, 82, 95, 100, 105, 122, 180):
        allowed = fe.matchup_mult(idx, side="allowed")
        total = fe.matchup_mult(idx, side="total")
        assert lo <= allowed <= hi and lo <= total <= hi
        if lo < allowed < hi:
            assert abs(allowed * total - 1.0) < 1e-9
    assert fe.matchup_mult(120, side="allowed") > 1.0
    assert fe.matchup_mult(120, side="total") < 1.0


def test_a_missing_index_prices_neutral_rather_than_dividing_by_it():
    import fantasy_export as fe
    assert fe.matchup_mult(None, side="total") == 1.0
    assert fe.matchup_mult(0, side="allowed") == 1.0
    assert fe.matchup_mult("", side="total") == 1.0
    with pytest.raises(ValueError):
        fe.matchup_mult(100, side="sideways")


def test_the_streamer_score_reads_the_same_band():
    """It used to clamp into [0.6, 1.5], so an extreme opponent was worth up to
    50% on the streamer board and at most 22% on the DFS row beside it."""
    import fantasy_export as fe
    p = {"fpts_fgp": 300.0, "ros": {"gs": 30}}
    ctx = {"WEAK": {"offense_plus": 55}, "STRONG": {"offense_plus": 180}}
    weak = fe._start_score(p, "WEAK", ctx)
    strong = fe._start_score(p, "STRONG", ctx)
    assert weak["per_start_base"] == 10.0
    assert weak["per_start_fgp"] == round(10.0 * fe.MATCHUP_CLAMP[1], 1)
    assert strong["per_start_fgp"] == round(10.0 * fe.MATCHUP_CLAMP[0], 1)
    # An unresolved opponent still prices at a labelled neutral 100.
    blank = fe._start_score(p, "NOBODY", ctx)
    assert blank["per_start_fgp"] == 10.0 and blank["opp_off_resolved"] is False


# ---------------------------------------------------------------------------
# 4. The quality-start level
# ---------------------------------------------------------------------------
def test_the_quality_start_rule_reads_the_measured_league_rate():
    """At the measured mean real start (5.47192 IP) and a league FIP of 4.00 the
    rule has to return the measured league quality-start rate. The slopes are
    untouched conventions; only the level was measured."""
    import fantasy_export as fe
    ipgs = 5.47192
    row = fe._pitcher_ros({"k_pct": 0.22, "bb_pct": 0.08, "hr_bf": 0.030,
                           "fip_proj": 4.00}, 1000.0, ipgs * 45.0, "SP", ipgs)
    assert abs(row["gs"] - 45.0) < 0.05
    assert abs(row["qs"] / row["gs"] - 0.37749) < 0.003
    assert "qs" in row["_est"]              # still a labelled heuristic


def test_the_quality_start_rule_keeps_its_shape():
    import fantasy_export as fe
    base = {"k_pct": 0.22, "bb_pct": 0.08, "hr_bf": 0.030, "fip_proj": 4.00}
    deep = fe._pitcher_ros(base, 1000.0, 6.2 * 30, "SP", 6.2)
    short = fe._pitcher_ros(base, 1000.0, 4.8 * 30, "SP", 4.8)
    assert deep["qs"] / deep["gs"] > short["qs"] / short["gs"]
    bad = fe._pitcher_ros({**base, "fip_proj": 5.60}, 1000.0, 5.4 * 30, "SP", 5.4)
    good = fe._pitcher_ros({**base, "fip_proj": 2.90}, 1000.0, 5.4 * 30, "SP", 5.4)
    assert good["qs"] > bad["qs"]
    assert (good["qs"] / good["gs"]) <= fe._QS_CEILING


# ---------------------------------------------------------------------------
# 5. The served board
# ---------------------------------------------------------------------------
def _board_problems(payload: dict) -> list[str]:
    """Everything wrong with a DFS payload that this repair is responsible for.

    A function rather than a wall of asserts, so the law can be RUN against a
    board built on purpose to break it (the test below this one). A law that
    only ever sees a green artifact has never been shown to fail."""
    import dfs_export as dx
    import fantasy_export as fe
    out = []
    a = payload.get("anchors") or {}
    if not a.get("pa_per_start_basis"):
        out.append(f"no pa_per_start_basis on a board priced at the current "
                   f"anchor; anchors={sorted(a)}")
    else:
        if a["pa_per_start"] != a["pa_per_start_basis"]["value"]:
            out.append("anchors.pa_per_start disagrees with its own basis")
        if not (9 * a["pa_per_start"] < a.get("lg_pa_per_team_game", 0)):
            out.append("nine starters do not fit inside one team game")
    if a.get("hit_matchup_clamp") != list(dx._HIT_MULT_CLAMP):
        out.append(f"published hit_matchup_clamp {a.get('hit_matchup_clamp')} is "
                   f"not the band the hitter rows were priced with")
    if a.get("allow_matchup_clamp") != list(fe.MATCHUP_CLAMP):
        out.append(f"published allow_matchup_clamp {a.get('allow_matchup_clamp')} "
                   f"is not the shared band")
    for g in payload.get("games") or []:
        for me in ("home", "away"):
            side = g.get(me) or {}
            for key, band in (("hit_matchup_mult", "hit_matchup_clamp"),
                              ("allow_matchup_mult", "allow_matchup_clamp")):
                m = side.get(key)
                if m is None or not a.get(band):
                    continue
                lo, hi = a[band]
                if not lo <= float(m) <= hi:
                    out.append(f"{g.get('game_pk')} {me} {key} {m} outside its "
                               f"own published clamp {a[band]}")
    bad = []
    for r in payload.get("players") or []:
        if r.get("side") != "hit":
            continue
        ln = r.get("line") or {}
        pa = float(ln.get("pa") or 0)
        used = sum(float(ln.get(k) or 0) for k in ("ab", "bb", "hbp"))
        if used > pa + 0.005:
            bad.append((r.get("name"), round(used - pa, 3)))
    if bad:
        out.append(f"{len(bad)} rows spend more than a game of plate "
                   f"appearances: {bad[:5]}")
    return out


def test_the_served_dfs_board_closes_the_identity_it_publishes():
    """Keyed on the BOARD'S OWN ANCHOR, never on a key this repair adds.

    A board priced at an anchor this module no longer holds was built by an
    earlier exporter, cannot be asked for this repair's receipt, and skips. A
    board priced at the CURRENT anchor must carry the receipt and must close the
    identity, so a refactor that drops the basis block fails here.

    The skip cannot hide a revert: an exporter put back to 4.15 would make this
    board skip, but `test_the_measured_anchors_are_the_measured_numbers` pins the
    constant itself and goes red on the same run. That pairing is deliberate.
    Keying this skip on `pa_per_start_basis`, the key this very patch
    introduces, would instead have made the law unfailable by anything at all,
    which is the L17 lesson ("no test was making that check") rewritten as a
    permanently green test."""
    import dfs_export as dx
    p = DATA / "dfs.json"
    if not p.exists():
        pytest.skip("no data/dfs.json in this tree")
    payload = json.loads(p.read_text(encoding="utf-8"))
    served = (payload.get("anchors") or {}).get("pa_per_start")
    built = str(payload.get("generated_at") or "")[:10] or "at an unstated time"
    if served != dx._PA_PER_START:
        pytest.skip(f"data/dfs.json was built {built} at pa_per_start {served}, "
                    f"not the {dx._PA_PER_START} this module prices; the next "
                    f"build arms this law")
    problems = _board_problems(payload)
    assert not problems, f"data/dfs.json ({built}): " + "; ".join(problems)


def test_the_served_board_law_can_actually_fail():
    """The law above, run against a board built to break it. Without this, a
    green suite would only ever mean the law had not been exercised."""
    import dfs_export as dx
    import fantasy_export as fe
    good = {
        "anchors": {"pa_per_start": dx._PA_PER_START,
                    "pa_per_start_basis": dict(dx._PA_PER_START_BASIS),
                    "lg_pa_per_team_game": dx._LG_PA_PER_TEAM_GAME,
                    "hit_matchup_clamp": list(dx._HIT_MULT_CLAMP),
                    "allow_matchup_clamp": list(fe.MATCHUP_CLAMP)},
        "games": [{"game_pk": 1, "home": {"hit_matchup_mult": 1.0,
                                          "allow_matchup_mult": 1.0}}],
        "players": [{"name": "fine", "side": "hit",
                     "line": {"pa": 4.0, "ab": 3.6, "bb": 0.35, "hbp": 0.04}}],
    }
    assert _board_problems(good) == []

    no_receipt = json.loads(json.dumps(good))
    no_receipt["anchors"].pop("pa_per_start_basis")
    assert any("no pa_per_start_basis" in m for m in _board_problems(no_receipt))

    broken = json.loads(json.dumps(good))
    broken["players"].append({"name": "over", "side": "hit",
                              "line": {"pa": 4.0, "ab": 3.9, "bb": 0.4, "hbp": 0.05}})
    assert any("more than a game of plate appearances" in m
               for m in _board_problems(broken))

    one_band = json.loads(json.dumps(good))
    one_band["anchors"]["hit_matchup_clamp"] = list(fe.MATCHUP_CLAMP)
    assert any("hit_matchup_clamp" in m for m in _board_problems(one_band))

    outside = json.loads(json.dumps(good))
    outside["games"][0]["home"]["hit_matchup_mult"] = 1.40
    assert any("outside its own published clamp" in m
               for m in _board_problems(outside))


# ---------------------------------------------------------------------------
# 6. The record the constant is audited by
# ---------------------------------------------------------------------------
def test_the_audited_record_states_the_anchor_the_code_holds():
    """The 4.15 outlived its evidence because it was written down in four
    places and measured in none. The registry row is the audited record of the
    served champion, the runbook is what a reader is sent to, and the function
    docstring is what the next author reads first. All three move with the
    constant or this fails."""
    import dfs_export as dx
    anchor = f"{dx._PA_PER_START}"
    reg = json.loads((DATA / "model_registry.json").read_text(encoding="utf-8"))
    row = next(r for r in reg["models"] if r["model_id"] == "dfs_slate_pricing")
    assert anchor in row["notes"], (
        f"the dfs_slate_pricing registry note does not state {anchor}, so the "
        f"audited record describes code that is not running"
    )
    # The note may still NARRATE the retired anchor (it should), but it must
    # not state it as the formula the served board runs.
    assert "pa_per_team_game / 4.15" not in row["notes"]
    doc = (ROOT / "docs" / "diamond-fantasy.md").read_text(encoding="utf-8")
    assert anchor in doc and "/ 4.15" not in doc and "4.15-PA" not in doc
    fn_doc = dx._hitter_line.__doc__ or ""
    assert anchor in fn_doc and "/ 4.15" not in fn_doc and "4.15-PA" not in fn_doc

# ---------------------------------------------------------------------------
# The contest tables (audit X02-04). Transcribed from the public classic rules
# on 2026-09-25. A table that drifts from this transcription fails here, and a
# weight on a key the line builders never produce scores zero forever, which is
# how a FanDuel quality start went unpaid while the line projected it.
# ---------------------------------------------------------------------------
_PUBLIC_2026_09_25 = {
    "dk": {"hitter": {"single": 3.0, "double": 5.0, "triple": 8.0, "hr": 10.0,
                      "rbi": 2.0, "r": 2.0, "bb": 2.0, "hbp": 2.0, "sb": 5.0},
           "pitcher": {"ip": 2.25, "k": 2.0, "w": 4.0, "er": -2.0,
                       "h": -0.6, "bb": -0.6, "hbp": -0.6}},
    "fd": {"hitter": {"single": 3.0, "double": 6.0, "triple": 9.0, "hr": 12.0,
                      "rbi": 3.5, "r": 3.2, "bb": 3.0, "hbp": 3.0, "sb": 6.0},
           "pitcher": {"ip": 3.0, "k": 3.0, "w": 6.0, "er": -3.0, "qs": 4.0}},
}
_ROS_PIT = {"gs": 30.0, "ip": 170.0, "k": 180.0, "bb": 50.0, "hbp": 6.0,
            "w": 11.0, "qs": 14.0, "h": 150.0, "er": 70.0, "hr": 20.0}


def test_the_contest_tables_match_the_dated_transcription():
    import dfs_export as dx
    assert dx.scoring_tables() == _PUBLIC_2026_09_25
    for site in ("dk", "fd"):
        src = dx.SCORING_SOURCES[site]
        assert src["verified_on"] == "2026-09-25"
        assert src["source_urls"] and all(u.startswith("https://") for u in src["source_urls"])


def test_every_weight_scores_a_key_the_line_builders_produce():
    import dfs_export as dx
    hit, _ = dx._hitter_line(_ROS_HIT, 150, 1.0)
    pit = dx._pitcher_line(_ROS_PIT, 1.0)
    for site, t in dx.scoring_tables().items():
        assert set(t["hitter"]) <= set(hit), (site, set(t["hitter"]) - set(hit))
        assert set(t["pitcher"]) <= set(pit), (site, set(t["pitcher"]) - set(pit))
    # The quality start is paid on FanDuel and not on DraftKings.
    base = dict(pit, qs=0.0)
    assert dx.score_line(pit, "fd", "pit") - dx.score_line(base, "fd", "pit") == pytest.approx(4.0 * pit["qs"], abs=0.02)
    assert dx.score_line(pit, "dk", "pit") == dx.score_line(base, "dk", "pit")
    # Neither site charges a hitter for an out or a caught stealing.
    assert dx.score_line(dict(hit, out=0.0, cs=0.0), "fd", "hit") == dx.score_line(hit, "fd", "hit")
    assert dx.score_line(dict(hit, out=0.0, cs=0.0), "dk", "hit") == dx.score_line(hit, "dk", "hit")


def test_the_served_board_publishes_its_scoring_receipts():
    """Skips only for a board an earlier exporter built (no receipts key)."""
    import dfs_export as dx
    p = Path(__file__).parent / "data" / "dfs.json"
    if not p.exists():
        pytest.skip("no served dfs.json")
    d = json.loads(p.read_text(encoding="utf-8"))
    if "scoring_sources" not in d:
        pytest.skip("board built before the scoring receipts shipped")
    assert d["scoring"] == dx.scoring_tables()
    assert d["scoring_sources"] == dx.SCORING_SOURCES
