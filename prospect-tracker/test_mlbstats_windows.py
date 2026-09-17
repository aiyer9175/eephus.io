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
             "last_season", "denoms", "war_n", "pli_n", "gmli_n"}
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
        for col, meta in (spec[board].get("pool") or {}).items():
            assert meta.get("denom") and meta.get("formula"), (board, col)


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


def test_a_thin_window_is_refused_rather_than_published():
    """A window with a season missing, a board with almost no rows, or an index
    pool too small for a mean and a spread is REFUSED. A published thin window
    is an invisible wrong answer; a refused one is a visible absence."""
    panels = {2025: {"hit": {1: {}}}, 2026: {"hit": {}}}
    assert lab.guard_window({}, [2025, 2026], panels)
    block = {"boards": {"hitters": {"hitters": [{"mlbam": 1}]}}, "pool_stats": {}}
    assert lab.guard_window(block, [2025], {2025: {"hit": {1: {}}}})
    block = {"boards": {"hitters": {"hitters": [{} for _ in range(60)]}},
             "pool_stats": {"hitters": {"hem_plus": {"n": 10, "mean": 100.0,
                                                     "sd": 12.0}}}}
    assert lab.guard_window(block, [2025], {2025: {"hit": {1: {}}}})


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
    assert '_lab_should_skip(out_dir / "mlbstats_windows.json"' in src
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
