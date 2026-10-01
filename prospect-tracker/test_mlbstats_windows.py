# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The multi-year window contract (tools/mlbstats_window_lab.py plus the
per-season substrate war_board_export writes beside the eWAR board).

WHAT THIS FILE IS ABOUT. A window board publishes three kinds of number and it
must never publish a fourth:

  * a COUNT, summed, which travels because addition does not care how many
    seasons it adds;
  * a POOLED RATE, one numerator over one NAMED denominator, computed by handing
    the summed counts back through the shipped derivation, so no second formula
    for AVG or ERA exists anywhere;
  * an INDEX, recomputed by the house recipe (the denominator-weighted mean of
    the per-season index, each season scored against its own pool), carrying the
    seasons and the denominator behind it, its percentile inside the window's own
    pool, and NO value ruler, because ten points is not one standard deviation of
    a window pool.

The fourth kind is the one this file exists to stop: a one-season number, or a
one-season scale, reprinted on a window under its one-season name.

Two of these tests read the SERVED FILES rather than the export path, because
the defect this whole program was blocked on was exactly that shape: four
history payloads documented as carrying eWAR, a test that covered the exporter,
and served files with zero such rows. Those tests skip when the artifact has not
been built on this machine.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pytest

import data_catalog
import war_board_export as wbe
from tools import mlbstats_window_lab as lab

ROOT = Path(__file__).parent
DATA = ROOT / "data"
SERVED_BOARD = DATA / "war_leaderboards.json"
SERVED_SEASONS = DATA / "war_seasons.json"
HISTORY = ("hitter_history.json", "starter_history.json", "bullpen_history.json",
           "leverage_history.json", "defense_history.json")


def _load(path: Path):
    if not path.exists():
        pytest.skip(f"{path.name} has not been built on this machine")
    return json.loads(path.read_text(encoding="utf-8"))


def _fold(doc: dict, lo: int, hi: int) -> dict:
    """The fold the page performs: counts added, the two eWAR sides summed
    UNROUNDED and rounded once."""
    f = {k: i for i, k in enumerate(doc["fields"])}
    out = {}
    for mid, (name, rows) in (doc.get("players") or {}).items():
        acc = {"name": name, "bat": 0.0, "pit": 0.0, "yrs": 0}
        has = {}
        for r in rows:
            y = r[f["season"]]
            if y < lo or y > hi:
                continue
            acc["yrs"] += 1
            for key in ("war_bat", "war_pit", "pa", "ip", "g", "gs"):
                v = r[f[key]]
                if v is None:
                    continue
                has[key] = True
                short = {"war_bat": "bat", "war_pit": "pit"}.get(key, key)
                acc[short] = (acc.get(short) or 0.0) + v
        if not acc["yrs"]:
            continue
        out[int(mid)] = {
            "war": round(acc["bat"] + acc["pit"], 1),
            "war_bat": round(acc["bat"], 1) if has.get("war_bat") else None,
            "war_pit": round(acc["pit"], 1) if has.get("war_pit") else None,
            "pa": int(acc["pa"]) if has.get("pa") else None,
            "ip": round(acc["ip"], 1) if has.get("ip") else None,
            "gs": int(acc["gs"]) if has.get("gs") else None,
            "_bat": acc["bat"], "_pit": acc["pit"], "yrs": acc["yrs"],
        }
    return out


# --------------------------------------------------------------------------- #
# the per-season substrate: it IS the board, or it is a second opinion
# --------------------------------------------------------------------------- #
def test_the_substrate_folds_to_the_served_board():
    """A one-season window and the Current view are the same numbers.

    This is the whole reason build_seasons is written in war_board_export's own
    process from the map build() used: measured 2026-09-17, the served board and
    data/ewar.json disagreed on 173 of the top 400 rows, and a year range would
    have made that disagreement visible on one page."""
    board, sub = _load(SERVED_BOARD), _load(SERVED_SEASONS)
    if board.get("generated_at") != sub.get("generated_at"):
        pytest.skip("the board and the substrate are from different runs")
    live = int(board["season"])
    folded = _fold(sub, live, live)
    rows = {r["mlbam"]: r for r in board["players"]}
    assert set(rows) == set(folded), (
        "the fold and the board do not cover the same players")
    bad = []
    for mid, r in rows.items():
        q = folded[mid]
        for key in ("war", "war_bat", "war_pit", "pa", "ip", "gs"):
            a, b = r.get(key), q.get(key)
            if (a is None) != (b is None) or (a is not None and abs(a - b) > 1e-9):
                bad.append((mid, key, a, b))
    assert not bad, f"the one-season fold differs from the board: {bad[:5]}"


def test_the_substrate_folds_to_the_served_league_block():
    """One number that makes a fold error visible at a glance. The league block
    sums the UNROUNDED sides, so the fold has to as well."""
    board, sub = _load(SERVED_BOARD), _load(SERVED_SEASONS)
    if board.get("generated_at") != sub.get("generated_at"):
        pytest.skip("the board and the substrate are from different runs")
    live = int(board["season"])
    folded = _fold(sub, live, live)
    lg = board["league"]
    assert round(sum(v["_bat"] + v["_pit"] for v in folded.values()), 1) == lg["war"]
    assert round(sum(v["_bat"] for v in folded.values()), 1) == lg["war_bat"]
    assert round(sum(v["_pit"] for v in folded.values()), 1) == lg["war_pit"]
    assert len(folded) == lg["n_players"]


def test_the_substrate_shares_the_board_basis():
    """The sibling of test_war_rate_plus's 3yr basis check. A substrate stamped
    with another eWAR build is a different series, and the window lab drops the
    Overall board rather than serving two series under one name."""
    sub = _load(SERVED_SEASONS)
    import bullpen_export as be
    basis = be.served_war_basis()
    assert sub["war_provider"] == basis["war_provider"]
    assert sub["ewar_generated_at"] == basis["ewar_generated_at"]


def test_absent_is_blank_not_zero_in_the_substrate():
    """A season a player did not pitch has a null pitching side and a null IP,
    never a 0.0 that reads as a replacement-level year."""
    sub = _load(SERVED_SEASONS)
    f = {k: i for i, k in enumerate(sub["fields"])}
    seen_null_pit = seen_null_pa = False
    for _mid, (_name, rows) in list(sub["players"].items())[:2000]:
        for r in rows:
            if r[f["war_bat"]] is None and r[f["war_pit"]] is None:
                pytest.fail("a substrate row carries neither side")
            seen_null_pit = seen_null_pit or (r[f["war_pit"]] is None
                                              and r[f["ip"]] is None)
            seen_null_pa = seen_null_pa or (r[f["pa"]] is None)
    assert seen_null_pit, "no row leaves the pitching side absent"
    assert seen_null_pa, "no row leaves plate appearances absent"


def test_the_substrate_publishes_the_window_rule_and_the_short_seasons():
    """The page reports what the payload states: the qualified rule and each
    season's share of a normal one, so 2020 and a live season are disclosed from
    a number rather than from a literal typed into the JS."""
    sub = _load(SERVED_SEASONS)
    rule = sub["qualified_rule_window"]
    assert rule["min_pa"] == int(wbe.QUAL_MIN_PA)
    assert rule["min_ip"] == int(wbe.QUAL_MIN_IP)
    share = sub["season_share"]
    assert share, "no season_share block"
    if "2020" in share:
        assert share["2020"] < 0.5, "the 60-game season reads as a full one"
    live = str(sub["seasons"][-1])
    assert live in share


# --------------------------------------------------------------------------- #
# the recipe
# --------------------------------------------------------------------------- #
def _panels(blocks: dict) -> dict:
    return {y: {"hit": rows} for y, rows in blocks.items()}


def test_the_window_index_is_the_denominator_weighted_mean():
    """The house recipe, in one assertion: each season weighted by its own
    denominator, which is what hem_plus_lab._multiyear_proposed and
    war_rate_plus_lab.window_values both do."""
    panels = _panels({
        2024: {1: {"hem": 120.0, "pa": 600}},
        2025: {1: {"hem": 90.0, "pa": 200}},
        2026: {1: {"hem": 100.0, "pa": 0}},        # no exposure: contributes nothing
    })
    out = lab.window_index(panels, [2024, 2025, 2026], "hit", "hem", "pa",
                           tag=(2, 600.0))
    got = out[1]
    assert got["n_seasons"] == 2
    assert got["denom_total"] == 800.0
    assert abs(got["value"] - (120 * 600 + 90 * 200) / 800.0) < 1e-9
    assert got["tag"] == "established"


def test_a_partial_window_is_tagged_provisional():
    """A count is self-protecting against a short sample and an index is not, so
    the row says which it is, with the labs' own thresholds."""
    panels = _panels({2026: {7: {"hem": 155.0, "pa": 480}}})
    out = lab.window_index(panels, [2024, 2025, 2026], "hit", "hem", "pa",
                           tag=(2, 600.0))
    assert out[7]["tag"] == "provisional"
    assert out[7]["n_seasons"] == 1


def test_the_universe_is_every_season_not_the_qualified_ones():
    """A season in which the player did not qualify is still inside the
    denominator. Folding the shipped history payloads instead would silently
    drop it, which is a rate on a basis it was not computed on."""
    panels = _panels({
        2025: {3: {"hem": 110.0, "pa": 620, "qual": True}},
        2026: {3: {"hem": 70.0, "pa": 90, "qual": False}},
    })
    out = lab.window_index(panels, [2025, 2026], "hit", "hem", "pa", tag=(2, 600.0))
    assert out[3]["n_seasons"] == 2
    assert out[3]["denom_total"] == 710.0


def test_the_pooled_rate_equals_the_denominator_weighted_fold():
    """AVG over a window is H / AB over the window, which is also the AB-weighted
    mean of the seasons. The counts go back through the shipped derivation, so
    there is no second formula to drift."""
    acc = {"pa": 1100, "ab": 1000, "h": 300, "2b": 50, "3b": 5, "hr": 40,
           "bb": 90, "ibb": 5, "hbp": 10, "sf": 8, "so": 200, "sb": 10, "cs": 3}
    rates = lab._hitter_rates(acc)
    assert abs(rates["avg"] - round(300 / 1000, 3)) < 1e-9
    # the corrected BABIP denominator: AB - SO - HR + SF, not AB
    assert abs(rates["babip"] - round((300 - 40) / (1000 - 200 - 40 + 8), 3)) < 1e-9
    assert abs(rates["obp"] - round((300 + 90 + 10) / (1000 + 90 + 10 + 8), 3)) < 1e-9


def test_ops_is_recomposed_not_pooled():
    """OPS is the pooled OBP plus the pooled SLG. Pooling it as a ratio of its
    own is a different number under the same header."""
    acc = {"pa": 1100, "ab": 1000, "h": 300, "2b": 50, "3b": 5, "hr": 40,
           "bb": 90, "ibb": 5, "hbp": 10, "sf": 8, "so": 200, "sb": 10, "cs": 3}
    r = lab._hitter_rates(acc)
    assert abs(r["ops"] - round(r["obp"] + r["slg"], 3)) < 2e-3


def test_the_pitching_rates_pool_on_their_own_denominators():
    """ERA is ER / IP x 9 over the window and K% is SO / TBF over it, both from
    the shipped derivation on the summed counts."""
    acc = {"g": 60, "gs": 60, "outs": 1080, "tbf": 1500, "er": 140, "r": 150,
           "bb": 120, "so": 400, "hr": 45, "hbp": 12, "pit": 6000, "strk": 3900,
           "cg": 1, "go": 500, "ao": 400, "sv": 0, "hld": 0}
    r = lab._pitcher_rates(acc, starter=True)
    assert abs(r["era"] - round(140 * 9 / 360.0, 2)) < 1e-9
    assert abs(r["k_pct"] - round(400 / 1500, 4)) < 1e-9
    assert abs(r["gb_pct"] - round(500 / 900, 4)) < 1e-9


def test_skill_fip_never_appears_on_a_window():
    """sem_plus.fip_skill shrinks toward that season's pool means and adds that
    season's FIP constant. Five season parameters, so a window FIP would be a
    different statistic wearing the same header."""
    acc = {"g": 60, "gs": 60, "outs": 1080, "tbf": 1500, "er": 140, "r": 150,
           "bb": 120, "so": 400, "hr": 45, "hbp": 12, "pit": 6000, "strk": 3900,
           "cg": 1, "go": 500, "ao": 400, "sv": 0, "hld": 0}
    for starter in (True, False):
        assert "fip" not in lab._pitcher_rates(acc, starter=starter)
    for board in ("starters", "bullpen"):
        assert "fip" in lab.columns_spec()[board]["hidden"], (
            f"the {board} window does not say why Skill FIP is gone")


# --------------------------------------------------------------------------- #
# what a window may never carry
# --------------------------------------------------------------------------- #
_LADDER = ("tier", "band", "ruler", "_adj", "_3yr", "gmli_3yr", "wrc_plus",
           "swstr_pct", "rate_1000_shrunk", "woba", "xhem_plus", "xsem_plus",
           "xrem_plus", "fwdhem_plus", "pwoba", "luck")


def _served_windows():
    idx = DATA / "mlbstats_windows.json"
    if not idx.exists():
        pytest.skip("the window artifacts have not been built on this machine")
    doc = json.loads(idx.read_text(encoding="utf-8"))
    out = {}
    for w in doc.get("windows") or []:
        p = DATA / w["file"]
        if p.exists():
            out[w["key"]] = json.loads(p.read_text(encoding="utf-8"))
    if not out:
        pytest.skip("no window payload on disk")
    return doc, out


def test_no_window_row_carries_a_one_season_scale():
    """THE HEADLINE TEST. Nothing on a window board may be a number measured on
    a pool the window is not: no tier, no band, no frozen three-year column, no
    column whose components we do not hold (wRC+, SwStr%), no shrunk value whose
    target is a season pool, and no forecast."""
    _idx, windows = _served_windows()
    bad = []
    for key, doc in windows.items():
        for board, blocks in (doc.get("boards") or {}).items():
            for block, rows in blocks.items():
                if not isinstance(rows, list):
                    continue
                for r in rows[:200]:
                    for field in r:
                        if any(field == t or field.endswith(t) for t in _LADDER):
                            bad.append((key, board, block, field))
    assert not bad, f"a one-season scale rode onto a window: {sorted(set(bad))[:8]}"


def test_every_window_index_publishes_its_pool_and_its_receipt():
    """100 is the average of each contributing season's pool, not of this
    window's, so the payload says what this window's pool actually is, and every
    value carries the seasons, the denominator, the tag and the percentile
    inside that pool."""
    _idx, windows = _served_windows()
    for key, doc in windows.items():
        pools = doc.get("pool_stats") or {}
        assert pools, f"{key} publishes no pool_stats"
        for board, metrics in pools.items():
            for metric, st in metrics.items():
                assert st["n"] >= lab.MIN_POOL_N, (key, board, metric, st)
                assert st["mean"] is not None and st["sd"] is not None
                rows = [r for blk, rr in doc["boards"][board].items()
                        if isinstance(rr, list) for r in rr]
                with_value = [r for r in rows if r.get(metric) is not None]
                assert with_value, f"{key}/{board}/{metric} has no values"
                for r in with_value[:200]:
                    for suffix in ("_pct", "_tag", "_n", "_denom", "_raw"):
                        assert f"{metric}{suffix}" in r, (metric, suffix, r["mlbam"])
                    assert r[f"{metric}_tag"] in ("established", "provisional")


def test_every_window_column_is_declared():
    """Every key a window row serves is either one of the row's own identity
    fields or a column the artifact DECLARES as summed, pooled, recomposed or
    an index, and every pooled column names a denominator and a formula."""
    idx, windows = _served_windows()
    spec = idx["columns"]
    ident = {"mlbam", "name", "team", "pos", "age", "yrs", "clubs", "qualified",
             "last_season", "denoms", "war_n", "pli_n", "gmli_n",
             "gmli_entries", "gmli_tag"}
    for key, doc in windows.items():
        for board, blocks in (doc.get("boards") or {}).items():
            s = spec[board]
            declared = set(s.get("sum") or []) | set(s.get("pool") or {}) \
                | set(s.get("recomposed") or {}) | set(s.get("index") or {})
            for metric in (s.get("index") or {}):
                declared |= {f"{metric}{x}" for x in
                             ("_raw", "_pct", "_tag", "_n", "_denom")}
            for block, rows in blocks.items():
                if not isinstance(rows, list):
                    continue
                for r in rows[:200]:
                    for field in r:
                        assert field in ident or field in declared, (
                            f"{key}/{board}: {field} is served and not declared")
            # INSIDE the board loop. This assertion used to sit outside it and
            # reuse the leaked `board`, so it only ever checked the last board.
            for col, meta in (s.get("pool") or {}).items():
                assert meta.get("denom") and meta.get("formula"), (board, col)
            for metric, meta in (s.get("index") or {}).items():
                assert meta.get("from"), (
                    f"{board}/{metric} does not name the shipped builder its "
                    f"recipe came from")


def test_a_pooled_rate_publishes_its_denominator_total():
    """The window says how much sample is behind each pooled rate: `denoms`
    carries the total of every denominator the column table names for that
    board, and `yrs` says over how many seasons the counts were gathered. One
    `yrs` covers every pooled rate on the row because the counts of a season
    travel together: a season is in the row or it is not."""
    idx, windows = _served_windows()
    for key, doc in windows.items():
        for board, blocks in (doc.get("boards") or {}).items():
            if board == "overall":
                continue          # its two rates divide the served PA and IP
            declared = {m["denom"] for m in (idx["columns"][board].get("pool")
                                             or {}).values()}
            if not declared:
                continue
            for block, rows in blocks.items():
                if not isinstance(rows, list):
                    continue
                for r in rows[:50]:
                    assert r.get("denoms"), (key, board, r["mlbam"])
                    assert set(r["denoms"]) <= declared | {"gs", "pitches", "bip",
                                                           "tbf", "ip"}, (
                        key, board, set(r["denoms"]) - declared)
                    assert r.get("yrs"), (key, board, r["mlbam"])


def test_no_index_window_contains_an_excluded_season():
    """Every index lab carries EXCLUDE_SEASONS = {2020}, so no window the lab
    publishes may contain it. A 60-game season inside a window index would be a
    season the one-season column refused, folded in through the back door."""
    idx, _windows = _served_windows()
    excluded = set(idx["excluded_seasons"])
    assert 2020 in excluded
    for w in idx["windows"]:
        assert not (set(w["seasons"]) & excluded), w


def _panel_ok(n: int = 200) -> dict:
    """A season that loaded every block, at a plausible width."""
    rows = {i: {} for i in range(n)}
    return {"hit": dict(rows), "pit": dict(rows), "dfn": dict(rows),
            "lev_bat": dict(rows), "lev_sp": dict(rows), "complete": True,
            "sources": {"hitting": True, "pitching": True, "defense": True,
                        "leverage": True}}


def test_a_thin_window_is_refused_rather_than_published():
    """A window with a season missing, a board with almost no rows, or an index
    pool too small for a mean and a spread is REFUSED. A published thin window
    is an invisible wrong answer; a refused one is a visible absence."""
    panels = {2025: _panel_ok(), 2026: {"hit": {}}}
    assert lab.guard_window({}, [2025, 2026], panels)
    ok = {2025: _panel_ok()}
    block = {"boards": {"hitters": {"hitters": [{"mlbam": 1}]}}, "pool_stats": {}}
    assert lab.guard_window(block, [2025], ok)
    block = {"boards": {"hitters": {"hitters": [{} for _ in range(60)]}},
             "pool_stats": {"hitters": {"hem_plus": {"n": 10, "mean": 100.0,
                                                     "sd": 12.0}}}}
    assert lab.guard_window(block, [2025], ok)
    assert lab.guard_window({"boards": {}, "pool_stats": {}}, [2025], ok) is None


def test_an_incomplete_panel_refuses_the_window_by_name():
    """season_panel already computes `complete` and already refuses to memoise
    without it; the guard has to read it. A season whose defense scoring or
    leverage walk died still carries hitters, so a row-count floor cannot see
    the hole: the defense board would just pool fewer seasons than the eWAR
    column beside it, disclosed nowhere a reader looks."""
    panel = _panel_ok()
    panel["complete"] = False
    panel["sources"]["defense"] = False
    reason = lab.guard_window({}, [2026], {2026: panel})
    assert reason and "defense" in reason and "2026" in reason


def test_a_half_walked_season_refuses_the_window():
    """The leverage walk returns what it walked and reports its coverage, so a
    season can load every block and still be half a season. Each block is
    measured against the window's own median season."""
    thin = _panel_ok()
    thin["lev_bat"] = {i: {} for i in range(20)}
    reason = lab.guard_window({}, [2025, 2026], {2025: _panel_ok(), 2026: thin})
    assert reason and "leverage batters" in reason


def test_the_windows_the_lab_builds_are_the_registered_ones():
    """The window set is pre-registered here, not chosen per run: the trailing
    three (the window the shipped *_3yr columns are already on) and the trailing
    five (the longest that contains no 2020)."""
    assert [w["key"] for w in lab.WINDOWS] == ["l3", "l5"]
    assert lab.window_seasons(2026, 3) == [2024, 2025, 2026]
    assert lab.window_seasons(2026, 5) == [2022, 2023, 2024, 2025, 2026]
    assert 2020 not in lab.window_seasons(2026, 5)


# --------------------------------------------------------------------------- #
# the artifacts, the catalog and the pipeline
# --------------------------------------------------------------------------- #
def test_the_new_artifacts_are_catalogued_and_shipped():
    """A page fetches all four, so all four are in the catalog and none is on
    the deploy's withhold list."""
    excluded = data_catalog.excluded_files()
    for name in ("war_seasons.json", "mlbstats_windows.json",
                 "mlbstats_window_l3.json", "mlbstats_window_l5.json"):
        row = next((a for a in data_catalog.ARTIFACTS if a["file"] == name), None)
        assert row is not None, f"{name} is not in data_catalog.ARTIFACTS"
        assert row["group"] == "mlb"
        assert row["stability"] in (data_catalog.STABLE, data_catalog.EXPERIMENTAL)
        assert name not in excluded


def test_the_pipeline_writes_them():
    """A served artifact nothing rebuilds is a frozen board. The substrate rides
    war_board_export, so it is written on BOTH paths the eWAR board is; the
    window lab is its own step on the lab cadence, with the forcing hatch every
    other lab has."""
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    assert "6b4k" in src
    assert "from tools import mlbstats_window_lab" in src
    assert "_lab_should_skip(" in src and "6b4k multi-year windows" in src
    assert "mlbstats_window_lab.basis_moved(" in src, (
        "the cadence gate asks age; a nightly eWAR rebuild moves the basis, and "
        "nothing would force the window rebuild that clears it")
    i = src.index("SCHEDULED_EXPORTS = (")
    watched = src[i:src.index(chr(10) + ")", i)]
    assert '"war_seasons"' in watched and '"mlbstats_windows"' in watched
    assert watched.index('"mgmt_export"') < watched.index('"mlbstats_windows"'), (
        "test_mgmt_export scans a fixed window of this tuple; the new names go "
        "below mgmt_export or they fail a test about the management board")
    wbe_src = (ROOT / "war_board_export.py").read_text(encoding="utf-8")
    assert "build_seasons(" in wbe_src and "_write_seasons(" in wbe_src
    assert '"war_seasons"' in wbe_src, (
        "the substrate's refusal files under a name run_monthly does not watch, "
        "so it never reaches the deploy shell's INGEST RED")


def test_every_served_history_payload_carries_ewar():
    """THE INVARIANT WHOSE ABSENCE BLOCKED THIS PROGRAM. Commit 1c3938b6 said the
    history boards carried eWAR and a test covered the EXPORT; the served files
    carried zero such rows for eleven days, and coveredCols hid the gap. This
    asserts the FILES ON DISK.

    A window board joins the same column, so it fails here first."""
    for name in HISTORY:
        doc = _load(DATA / name)
        rows = [r for season in (doc.get("history") or {}).values()
                for block in season.values() if isinstance(block, list)
                for r in block]
        if not rows:
            pytest.skip(f"{name} carries no history rows")
        with_war = sum(1 for r in rows if r.get("war") is not None)
        assert with_war == len(rows), (
            f"{name}: {with_war} of {len(rows)} rows carry eWAR")


def test_the_window_artifacts_share_the_served_war_basis():
    """A window's eWAR column and the one-year eWAR column beside it are one
    series, or the window says it is not. This is the guard that closed audit
    F10-01, applied per window artifact."""
    idx, windows = _served_windows()
    import bullpen_export as be
    basis = be.served_war_basis()
    assert idx["war_provider"] == basis["war_provider"]
    assert idx["ewar_generated_at"] == basis["ewar_generated_at"]
    for key, doc in windows.items():
        assert doc["war_provider"] == basis["war_provider"], key
        assert doc["ewar_generated_at"] == basis["ewar_generated_at"], key


# --------------------------------------------------------------------------- #
# the recipes the shipped columns own, followed rather than re-invented
# --------------------------------------------------------------------------- #
def test_gmli_pools_on_relief_entries_and_not_on_innings():
    """THE ONE MULTI-YEAR RECIPE THAT WAS ALREADY DISCOVERABLE.
    tools/leverage_consistency_eval.proposed_values builds the shipped gmli_3yr
    as sum(gmli x appearances) / sum(appearances) and its own docstring calls it
    the relief-entry-weighted mean. Innings are a different weight and a
    different number."""
    from tools import leverage_consistency_eval as lce
    panels = {2025: {"pit": {1: {"gmli": 1.00, "gapp": 60, "outs": 570}}},
              2026: {"pit": {1: {"gmli": 2.00, "gapp": 20, "outs": 480}}}}
    seasons = [2025, 2026]
    entries = lab.window_index(panels, seasons, "pit", "gmli", "gapp", tag=(2, 60))
    innings = lab.window_index(panels, seasons, "pit", "gmli",
                               lambda r: (r.get("outs") or 0) / 3.0, tag=(2, 60))
    assert abs(entries[1]["value"] - (1.0 * 60 + 2.0 * 20) / 80.0) < 1e-9
    assert entries[1]["denom_total"] == 80.0
    assert abs(entries[1]["value"] - innings[1]["value"]) > 0.1, (
        "the two weightings would have to differ for this to be worth pinning")
    # the tag is that module's, not a number typed here
    assert lab._tags()["gmli"] == (lce.TAG_MIN_SEASONS, lce.TAG_MIN_ENTRIES)
    spec = lab.columns_spec()["bullpen"]["pool"]["gmli"]
    assert spec["denom"] == "entries" and "entry" in spec["formula"]


def test_the_defense_window_weights_the_unrounded_per_season_index():
    """dem_plus_lab._dem3 weights `dem_plus_raw`, and this window follows the
    builder it names. HEM+, SEM+ and REM+ weight their ROUNDED per-season value
    and are followed too: the four labs differ, and copying one onto all four
    would be a second method wearing four names."""
    panels = {2025: {"dfn": {1: {"name": "A", "team": "BOS", "pos": "SS",
                                 "dem": 104, "dem_raw": 104.4, "inn": 900.0}}},
              2026: {"dfn": {1: {"name": "A", "team": "BOS", "pos": "SS",
                                 "dem": 96, "dem_raw": 95.6, "inn": 300.0}}}}
    board, pools = lab._defense_board(panels, [2025, 2026], {},
                                      {"min_inn": 400}, {"dem_plus": (2, 400.0)})
    row = board["fielders"][0]
    assert row["dem_plus_raw"] == round((104.4 * 900 + 95.6 * 300) / 1200.0, 2)
    assert row["dem_plus_raw"] != round((104 * 900 + 96 * 300) / 1200.0, 2)
    assert row["dem_plus_n"] == 2 and row["dem_plus_tag"] == "established"
    assert pools["dem_plus"]["n"] == 1


def test_every_window_index_names_the_builder_it_came_from():
    """The module docstring says the method was found in this repo rather than
    invented here. That is true per column, so it is claimed per column, and the
    two places it is NOT true say so in the same block."""
    spec = lab.columns_spec()
    own = []
    for board, s in spec.items():
        for metric, meta in (s.get("index") or {}).items():
            assert meta.get("from"), (board, metric)
            if meta.get("own_choice"):
                own.append((board, metric))
    assert own == [("bullpen", "riv_plus")], (
        "RIV+ has no shipped multi-year column, so its weighting is this "
        "module's own choice and has to be marked as one")


def test_every_served_board_column_is_declared_or_explained():
    """The other direction of the column contract. A column the one-season board
    carries and a window drops must say WHY on the artifact, or the page cannot
    put the one-line reason where the column was."""
    idx, _windows = _served_windows()
    spec = idx["columns"]
    ident = {"mlbam", "name", "team", "pos", "key", "qualified", "bats", "age",
             "boards"}
    served = {
        "overall": ("war_leaderboards.json", ("players",)),
        "hitters": ("hitter_leaderboards.json", ("hitters",)),
        "starters": ("starter_leaderboards.json", ("starters",)),
        "bullpen": ("bullpen_leaderboards.json", ("relievers",)),
        "leverage": ("leverage_leaderboards.json", ("batters", "starters")),
        "defense": ("defense_leaderboards.json", ("fielders",)),
    }
    for board, (fname, blocks) in served.items():
        doc = _load(DATA / fname)
        s = spec[board]
        known = set(s.get("sum") or []) | set(s.get("pool") or {}) \
            | set(s.get("recomposed") or {}) | set(s.get("index") or {}) \
            | set(s.get("hidden") or {}) | ident
        fields = set()
        for block in blocks:
            for r in (doc.get(block) or [])[:50]:
                fields |= set(r)
        unexplained = sorted(f for f in fields
                             if not any(f == k or f.startswith(k + "_")
                                        for k in known))
        assert not unexplained, (
            f"{board}: {unexplained} are on the served board and the window "
            f"neither publishes nor explains them")


# --------------------------------------------------------------------------- #
# the pool the page shows, and the sample under a rate
# --------------------------------------------------------------------------- #
def test_pool_stats_describes_the_pool_the_page_defaults_to():
    """A window pool is 30-40% provisional and the spec defaults the view to
    established-only, so a payload that published only the all-rows mean and sd
    would be describing a pool the page is not showing."""
    _idx, windows = _served_windows()
    for key, doc in windows.items():
        for board, metrics in (doc.get("pool_stats") or {}).items():
            for metric, st in metrics.items():
                assert st["n_established"] + st["n_provisional"] == st["n"], (
                    key, board, metric, st)
                est = st["established"]
                assert est["n"] == st["n_established"]
                if est["n"] >= 2:
                    assert est["mean"] is not None and est["sd"] is not None
                assert "provisional" in st["pct_pool"], (
                    "the payload does not say which pool `pct` is ranked in")


def test_a_window_rate_carries_a_denominator_the_one_season_column_would_print():
    """war_rate_plus_lab gates a contributing season on its DISPLAY floor and
    argues why: a rate off a sample the one-season column would refuse puts
    small-sample noise at the top of the board. Measured before the floor: Ryne
    Nelson, a starting pitcher, read Bat/600 = 42.0."""
    idx, windows = _served_windows()
    spec = idx["columns"]["overall"]["pool"]
    min_pa = spec["bat_600"]["display_min"]
    min_ip = spec["pitch_200"]["display_min"]
    assert min_pa and min_ip
    for key, doc in windows.items():
        for r in ((doc.get("boards") or {}).get("overall") or {}).get("players", []):
            if r.get("bat_600") is not None:
                assert (r.get("pa") or 0) >= min_pa, (key, r["name"], r.get("pa"))
            if r.get("pitch_200") is not None:
                assert (r.get("ip") or 0) >= min_ip, (key, r["name"], r.get("ip"))


def test_the_overall_window_league_is_summed_unrounded():
    """The league total of a window is the fold of the substrate's unrounded
    sides, rounded ONCE. Summing the rows' printed tenths carries one rounding
    error per row (measured on l3: 2935.9 that way against 2937.5 honestly).

    THE TOLERANCE IS NOT SLOP, IT IS A ROUNDING TIE (2026-09-18). The l3 fold
    sums to EXACTLY 2937.4500000000 over the same 2,072 players the artifact
    carries, which sits precisely on the half-tenth boundary: a left-to-right
    sum rounds it to 2937.5 and math.fsum rounds it to 2937.4 on identical
    inputs. Pinning the exact tenth therefore tests the summation ORDER of a
    few thousand floats, which is not what this test is for. The defect it
    exists to catch is worth 1.6 WAR, so a half-tenth window still catches that
    and every larger error, while a tie no longer fails the suite for the wrong
    reason. The player-count assertion below is exact and unchanged."""
    idx, windows = _served_windows()
    sub = _load(SERVED_SEASONS)
    if sub.get("ewar_generated_at") != idx.get("ewar_generated_at"):
        pytest.skip("the substrate and the windows are on different eWAR builds")
    checked = 0
    for key, doc in windows.items():
        board = (doc.get("boards") or {}).get("overall")
        if not board:
            continue
        seasons = doc["window"]["seasons"]
        folded = _fold(sub, seasons[0], seasons[-1])
        raw = math.fsum(v["_bat"] + v["_pit"] for v in folded.values())
        # The published tenth must be a CORRECT ROUNDING of the unrounded fold.
        # Comparing two already-rounded numbers is what put a tie one whole
        # tenth apart; comparing against `raw` states the invariant directly and
        # still fails the 1.6 WAR round-then-sum error by a factor of thirty.
        assert abs(board["league"]["war"] - raw) <= 0.05 + 1e-9, (
            key, board["league"]["war"], raw)
        assert board["league"]["n_players"] == len(folded)
        checked += 1
    assert checked, "no window published an Overall board"


# --------------------------------------------------------------------------- #
# the decisive reproduction check, and the basis door
# --------------------------------------------------------------------------- #
def test_the_panel_reproduces_the_served_per_season_index_exactly():
    """THE CHECK THAT CANNOT MOVE UNDER ITS OWN FEET. Comparing a window against
    a shipped three-year artifact cannot separate a method difference from a
    build-date difference, because the two are built on different days. A
    COMPLETED season's per-season index can: the stat line is frozen and both
    numbers come out of the same scorer, so any delta is a method difference."""
    idx, _windows = _served_windows()
    per = (idx.get("reproduction") or {}).get("per_season") or {}
    assert per, "the artifact publishes no per-season reproduction block"
    live = str(idx["live_season"])
    for metric, block in per.items():
        if not block.get("available"):
            continue
        for season, st in (block.get("per_season") or {}).items():
            assert season != live, "a live season is not frozen; it cannot check"
            assert st["n_equal"] == st["n"], (
                f"{metric} {season}: {st['n_equal']} of {st['n']} equal, max "
                f"delta {st['max_abs_delta']} - that is a METHOD difference")


def test_a_moved_ewar_basis_forces_a_rebuild(tmp_path):
    """The cadence gate asks age. An eWAR rebuild re-keys the window's `war`
    column under it, which is what run_monthly._artifact_fresh's
    `invalidated_by` hatch exists for; basis_moved applies the same argument one
    step earlier, so the pipeline can clear a red it just created."""
    import bullpen_export as be
    basis = be.served_war_basis()
    p = tmp_path / "mlbstats_windows.json"
    p.write_text(json.dumps({"war_provider": basis["war_provider"],
                             "ewar_generated_at": basis["ewar_generated_at"]}),
                 encoding="utf-8")
    assert lab.basis_moved(p) is False
    p.write_text(json.dumps({"war_provider": basis["war_provider"],
                             "ewar_generated_at": "1999-01-01T00:00:00"}),
                 encoding="utf-8")
    assert lab.basis_moved(p) is True
    assert lab.basis_moved(tmp_path / "absent.json") is False


def test_a_refused_window_stops_being_served(tmp_path, monkeypatch):
    """export() writes only the windows that survived the guard. Without this,
    a window that went thin would vanish from the index while its previous
    payload stayed on disk, catalogued and fetchable."""
    import bullpen_export as be
    filed: list = []
    monkeypatch.setattr(be, "record_ingest",
                        lambda *a, **k: filed.append((a, k)))
    stale = tmp_path / "mlbstats_window_l5.json"
    stale.write_text('{"window": {"key": "l5"}}', encoding="utf-8")
    index = {"generated_at": "2026-09-17", "schema": lab.SCHEMA,
             "war_provider": "x", "ewar_generated_at": "y",
             "excluded_seasons": [2020], "columns": {}, "method": "m",
             "sources": {"season_share": {}}, "build_seconds": 0.1,
             "windows_refused": {"l5": "too thin"}}
    block = {"name": "Last 3", "window": {"key": "l3", "label": "2024-2026",
                                          "years": 3,
                                          "seasons": [2024, 2025, 2026]},
             "boards": {}, "pool_stats": {}, "n_rows": {}}
    monkeypatch.setattr(lab, "build",
                        lambda *a, **k: {"index": index, "windows": {"l3": block}})
    n = lab.export(2026, out_dir=tmp_path, log=lambda *a, **k: None)
    assert n == 1
    assert (tmp_path / "mlbstats_window_l3.json").exists()
    assert not stale.exists(), "a refused window kept serving its old payload"
    assert any(k.get("ok") for _a, k in filed), (
        "a successful run files no heartbeat, so it reads in the ledger exactly "
        "like a step that never ran")


# --------------------------------------------------------------------------- #
# the substrate's own doors
# --------------------------------------------------------------------------- #
def test_the_substrate_is_written_beside_the_board_it_was_built_with(tmp_path,
                                                                    monkeypatch):
    """THE PYTEST TRAP, pinned. Every existing test of this exporter redirects
    OUT_PATH and nothing else, so a second module-level path would write a
    synthetic substrate into the real, git-tracked data/ directory: measured at
    5,149 players down to 24 on one stubbed test."""
    assert not hasattr(wbe, "SEASONS_OUT_PATH"), (
        "a module-level substrate path is a second door a test cannot redirect")
    monkeypatch.setattr(wbe, "OUT_PATH", tmp_path / "war_leaderboards.json")
    assert wbe.seasons_out_path() == tmp_path / "war_seasons.json"


def test_a_dead_feed_is_reported_per_group_not_per_season():
    """The failure that happens is ONE of a season's two feeds, not both. A 2019
    pitching read that fails leaves every 2019 pitcher-season without IP or GS
    while the hitting rows sail through, so a payload that only counted whole
    cold seasons would report full coverage over a season with no innings."""
    sub = _load(SERVED_SEASONS)
    src_block = sub["sources"]
    assert "groups_without_a_feed" in src_block
    assert isinstance(src_block["groups_without_a_feed"], dict)
    for season, groups in src_block["groups_without_a_feed"].items():
        assert set(groups) <= {"hitting", "pitching"}, (season, groups)
    assert "groups_without_a_feed" in sub["note"]
    reads = src_block["feed_reads"]
    assert reads["from_memo"] + reads["fetched"] >= 1


def test_the_substrate_g_is_the_max_and_the_boards_g_is_the_pitching_side():
    """TWO DIFFERENT QUESTIONS, PINNED APART. The board's `g` is the pitching
    feed's G alone, so a hitter reads blank; the substrate's `g` is the max of
    the two feeds, because a two-way player's hitting games and pitching games
    are the same games. They disagree on most live rows ON PURPOSE, and the
    payload says so."""
    board, sub = _load(SERVED_BOARD), _load(SERVED_SEASONS)
    if board.get("generated_at") != sub.get("generated_at"):
        pytest.skip("the board and the substrate are from different runs")
    assert "MAX" in (sub.get("field_notes") or {}).get("g", "")
    f = {k: i for i, k in enumerate(sub["fields"])}
    live = int(board["season"])
    sub_g = {}
    for mid, (_name, rows) in sub["players"].items():
        for r in rows:
            if r[f["season"]] == live and r[f["g"]] is not None:
                sub_g[int(mid)] = r[f["g"]]
    blank_on_the_board = 0
    for r in board["players"]:
        mine = sub_g.get(r["mlbam"])
        if mine is None:
            continue
        if r.get("g") is None:
            blank_on_the_board += 1
            continue
        assert mine >= r["g"], (r["name"], mine, r["g"])
    assert blank_on_the_board, (
        "no row is blank on the board and present in the substrate, so the two "
        "G rules no longer differ and this pin is stale")


# --------------------------------------------------------------------------- #
# M17 (owner answers 2026-09-25): the Current *_3yr columns read the l3 window,
# the window rebuilds nightly, and the REM+ pool rule is stated once
# --------------------------------------------------------------------------- #
_BOARD_3YR = (("hitter_leaderboards.json", "hitters", "hitters", "hitters", "hem_plus"),
              ("starter_leaderboards.json", "starters", "starters", "starters", "sem_plus"),
              ("bullpen_leaderboards.json", "relievers", "bullpen", "relievers", "rem_plus"),
              ("defense_leaderboards.json", "fielders", "defense", "fielders", "dem_plus"))


@pytest.mark.parametrize("fname,rblock,wboard,wblock,metric", _BOARD_3YR)
def test_the_current_3yr_column_is_the_l3_window_index(fname, rblock, wboard, wblock,
                                                       metric):
    """Census M06-06, the spec's own test: for every mlbam on both the served
    Current board and the served Last 3 window, the board's *_3yr equals the
    window's index, with the window pool's percentile and tag beside it. One
    2024-2026 number per player per page."""
    board = _load(DATA / fname)
    win = _load(DATA / "mlbstats_window_l3.json")
    meta = board.get("multiyear") or {}
    assert meta.get("kind") == "window" and meta.get("available"), meta
    assert meta.get("source") == "mlbstats_window_l3.json"
    assert meta.get("generated_at") == win.get("generated_at"), (
        "the board was joined from another build of the window")
    wrows = {int(r["mlbam"]): r for r in win["boards"][wboard][wblock]
             if r.get(metric) is not None}
    key = f"{metric}_3yr"
    both = 0
    for r in board[rblock]:
        mid = r.get("mlbam")
        w = wrows.get(int(mid)) if mid is not None else None
        if w is None:
            assert r.get(key) is None, (fname, mid, r.get(key))
            continue
        both += 1
        assert r.get(key) == w[metric], (fname, mid, r.get(key), w[metric])
        assert r.get(f"{key}_pct") == w.get(f"{metric}_pct"), (fname, mid)
        assert r.get(f"{key}_tag") == w.get(f"{metric}_tag"), (fname, mid)
    assert both == meta.get("n_stamped") and both > 0, (fname, both, meta.get("n_stamped"))


def _win_doc(basis: dict, seasons=(2024, 2025, 2026)) -> dict:
    return {"generated_at": "2026-10-01", **basis,
            "window": {"key": "l3", "seasons": list(seasons)},
            "panel_built_at": {str(seasons[-1]): "2026-10-01"},
            "pool_stats": {"bullpen": {"rem_plus": {"n": 2, "mean": 99.5, "sd": 9.2}}},
            "boards": {"bullpen": {"relievers": [
                {"mlbam": 1, "rem_plus": 121, "rem_plus_pct": 90, "rem_plus_tag": "established"},
                {"mlbam": 2, "rem_plus": 88, "rem_plus_pct": 12, "rem_plus_tag": "provisional"}]}}}


def test_the_window_join_refuses_another_build_or_another_season(tmp_path):
    """The guard join_war_rate_3yr applies: a window built beside another eWAR
    build, or one that does not end at the board's season, blanks the column
    rather than serving it."""
    import bullpen_export as be
    basis = be.served_war_basis()
    p = tmp_path / "mlbstats_window_l3.json"
    p.write_text(json.dumps(_win_doc(basis)), encoding="utf-8")
    rows = [{"mlbam": 1}, {"mlbam": 2}, {"mlbam": 3}]
    meta = be.join_window_3yr(rows, board="bullpen", block="relievers",
                              metric="rem_plus", season=2026, path=p)
    assert meta["available"] and meta["n_stamped"] == 2 and meta["kind"] == "window"
    assert rows[0]["rem_plus_3yr"] == 121 and rows[0]["rem_plus_3yr_pct"] == 90
    assert rows[1]["rem_plus_3yr_tag"] == "provisional"
    assert "rem_plus_3yr" not in rows[2]
    assert meta["panel_built_at"] == "2026-10-01" and meta["window"] == [2024, 2025, 2026]
    assert meta["uncoloured"] is True and meta["pool"]["sd"] == 9.2
    p.write_text(json.dumps(_win_doc({**basis, "ewar_generated_at": "1999-01-01"})),
                 encoding="utf-8")
    rows = [{"mlbam": 1}]
    meta = be.join_window_3yr(rows, board="bullpen", block="relievers",
                              metric="rem_plus", season=2026, path=p)
    assert not meta["available"] and "refused" in meta and "rem_plus_3yr" not in rows[0]
    p.write_text(json.dumps(_win_doc(basis, seasons=(2023, 2024, 2025))), encoding="utf-8")
    meta = be.join_window_3yr(rows, board="bullpen", block="relievers",
                              metric="rem_plus", season=2026, path=p)
    assert not meta["available"] and "2026" in meta["refused"]


def test_the_restamp_rejoins_only_the_3yr_keys(tmp_path):
    """After the nightly window rebuild the boards are re-joined in place: the
    old *_3yr keys are cleared first (so a refusal blanks them), only those keys
    and the `multiyear` block move, and every other field stands."""
    import bullpen_export as be
    basis = be.served_war_basis()
    (tmp_path / "mlbstats_window_l3.json").write_text(json.dumps(_win_doc(basis)),
                                                      encoding="utf-8")
    board = {"season": 2026, "as_of": "2026-09-30", "multiyear": {"source": "old"},
             "relievers": [{"mlbam": 1, "rem_plus": 130, "rem_plus_3yr": 140,
                            "rem_plus_3yr_pct": 99, "rem_plus_3yr_tag": "established"},
                           {"mlbam": 7, "rem_plus": 95, "rem_plus_3yr": 97}]}
    (tmp_path / "bullpen_leaderboards.json").write_text(json.dumps(board), encoding="utf-8")
    out = be.restamp_window_3yr(data_dir=tmp_path, log=lambda *a, **k: None)
    assert out["bullpen_leaderboards.json"] == 1
    assert out["hitter_leaderboards.json"].startswith("skipped")
    doc = json.loads((tmp_path / "bullpen_leaderboards.json").read_text(encoding="utf-8"))
    a, b = doc["relievers"]
    assert a["rem_plus_3yr"] == 121 and a["rem_plus_3yr_pct"] == 90 and a["rem_plus"] == 130
    assert "rem_plus_3yr" not in b and b["rem_plus"] == 95
    assert doc["multiyear"]["kind"] == "window" and doc["as_of"] == "2026-09-30"


def test_the_live_panel_rebuilds_nightly_after_the_vintage_snapshot():
    """Owner answer M17-1. run_daily rebuilds the windows (only the live season
    is re-walked; completed seasons stay memoised), AFTER the 9e-pre vintage
    snapshot and the 9e-pre0c eWAR board whose substrate the Overall window
    folds, keeps basis_moved, and re-joins the four boards' 3yr columns. The
    6b4k note says the owner reversed its old cadence line; STALE_DAYS is not
    touched."""
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i_snap = src.index('_step("9e-pre. Leaderboard vintage snapshot')
    i_ewar = src.index('_step("9e-pre0c. Refresh eWAR Leaderboard')
    i_win = src.index('_step("9e-pre0d. Live-season window panel')
    assert i_snap < i_ewar < i_win, "the window step left its place after the snapshot"
    body = src[i_win:src.index("# --- 9e-pre-wx.", i_win)]
    assert "_mwl.export(" in body and "_mwl.basis_moved(" in body
    assert "_mwl.built_today(" in body
    assert "restamp_window_3yr(" in body
    k = src.index("# --- 6b4k.")
    note = src[k:src.index("with _step(", k)]
    assert "REVERSED" in note and "2026-09-25" in note
    assert "ON THE LAB CADENCE, not nightly" not in note
    assert "restamp_window_3yr(" in src[k:src.index("# --- 6b5.", k)]
    assert lab.CACHE_DIR.name == "mlbstats_windows"


def test_built_today_reads_the_index_stamp(tmp_path):
    from datetime import date
    p = tmp_path / "mlbstats_windows.json"
    p.write_text(json.dumps({"generated_at": date.today().isoformat()}), encoding="utf-8")
    assert lab.built_today(p) is True
    p.write_text(json.dumps({"generated_at": "2026-09-18"}), encoding="utf-8")
    assert lab.built_today(p) is (date.today().isoformat() == "2026-09-18")
    assert lab.built_today(tmp_path / "absent.json") is False


def test_the_rem_plus_pool_rule_is_stated_once():
    """Census M06-06 asked for the REM+ opener rule to be reconciled between the
    served board and the multi-year lab before the switch. The two filters were
    one expression already (true reliever, not an opener); the residual gap the
    census read (Daniel Lynch IV, 93 against 86) was pool membership: his 2026
    line reached 10 starts in 56 games, past MAX_START_SHARE, so his 2026 season
    left the reliever pool. Both paths now call rem_plus.pool_members, and the
    window's per-season REM+ reproduces the served history exactly."""
    import inspect

    import rem_plus
    from tools import rem_plus_lab
    assert "pool_members(" in inspect.getsource(rem_plus.score_pool)
    assert "rem_plus.pool_members(" in inspect.getsource(rem_plus_lab.load_season)
    r = rem_plus.Reliever(key="1", name="Opener", team="TB", mlbam=1, g=20, gs=0,
                          ip=20.0, tbf=80, so=20, bb=5, hbp=1, hr=2, er=8, r=8,
                          pit=300, sts=None, sv=0, hld=0)
    r.entry_inning = 1.0
    s = rem_plus.Reliever(key="2", name="Swingman", team="TB", mlbam=2, g=20, gs=3,
                          ip=40.0, tbf=170, so=40, bb=12, hbp=1, hr=4, er=18, r=19,
                          pit=650, sts=None, sv=0, hld=0)
    t = rem_plus.Reliever(key="3", name="Setup", team="TB", mlbam=3, g=60, gs=0,
                          ip=60.0, tbf=240, so=70, bb=20, hbp=2, hr=5, er=20, r=22,
                          pit=950, sts=None, sv=2, hld=20)
    assert [x.mlbam for x in rem_plus.pool_members([r, s, t])] == [3]
    idx, _windows = _served_windows()
    per = ((idx.get("reproduction") or {}).get("per_season") or {}).get("rem_plus") or {}
    if per.get("available"):
        assert per["n_equal"] == per["n"], per
