"""Arithmetic laws over the SERVED artifacts. One file, cheap, and it would have caught
four live defects this session on its own.

WHY THIS FILE EXISTS. Every defect found on 2026-09-06 was invisible for the same reason:
a law that must hold was never asserted anywhere.

  - A club served playoffPct 1.001. Nothing checked that a probability is at most one.
  - Twenty of thirty clubs were projected over a 161-game season. Nothing checked that
    games played plus games remaining equals a season.
  - The Hall of Fame label called Charlie Gehringer a non-inductee. Nothing checked that
    a player in the induction ledger carries a positive label.
  - Arizona vanished from the standings reader. Nothing checked that thirty clubs resolve.

Each of those is one line of arithmetic. None of them needed a model, a gate or a
backtest, and each was reader-visible.

WHAT BELONGS HERE AND WHAT DOES NOT. Only laws that hold in ANY build, fresh or stale:
identities, bounds, partitions, conservation. Freshness and cross-artifact coherence do
NOT belong here, because the artifacts are gitignored build products that suite chunks
regenerate, and a coherence assertion over them goes red on housekeeping rather than on a
defect. That mistake was made earlier the same day and is not repeated: an assertion that
cannot tell a defect from a rebuild trains a reader to ignore reds.

Every check skips loudly when its artifact is absent. A missing artifact is a build state,
not a failure.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"


def _load(name: str):
    p = DATA / name
    if not p.exists():
        pytest.skip(f"data/{name} has not been built")
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except ValueError as exc:
        pytest.fail(f"data/{name} is not valid JSON: {exc}")


def _is_prob(v) -> bool:
    return isinstance(v, (int, float)) and 0.0 <= float(v) <= 1.0


# --------------------------------------------------------------------------
# The season simulator
# --------------------------------------------------------------------------

def _outlook():
    rows = (_load("mlb_projections.json").get("team_outlook") or [])
    if not rows:
        pytest.skip("team_outlook is empty")
    return rows


def test_every_club_is_present_exactly_once():
    """Arizona was silently dropped by a len<=3 name guard and nothing noticed."""
    rows = _outlook()
    teams = [r.get("team") for r in rows]
    assert len(teams) == 30, f"{len(teams)} clubs in team_outlook, not 30"
    assert len(set(teams)) == 30, "a club appears twice"


def test_no_published_probability_leaves_the_unit_interval():
    """Milwaukee served playoffPct 1.001."""
    rows = _outlook()
    keys = ("playoffPct", "divisionPct", "wildcardPct", "byePct",
            "wcRoundPct", "ldsPct", "lcsPct", "pennantPct", "wsPct")
    bad = []
    for r in rows:
        cur = r.get("current") or {}
        for k in keys:
            v = cur.get(k)
            if v is not None and not _is_prob(v):
                bad.append((r.get("team"), k, v))
    assert not bad, f"probabilities outside [0, 1]: {bad[:8]}"


def test_the_playoff_identity_holds_on_every_club():
    """divisionPct and wildcardPct are disjoint and exhaust playoffPct. The UI
    stacks its bar widths on that."""
    rows = _outlook()
    bad = []
    for r in rows:
        c = r.get("current") or {}
        p, d, w = c.get("playoffPct"), c.get("divisionPct"), c.get("wildcardPct")
        if None in (p, d, w):
            continue
        if abs((d + w) - p) > 1e-9:
            bad.append((r.get("team"), p, d, w))
    assert not bad, f"divisionPct + wildcardPct != playoffPct: {bad[:8]}"


def test_every_club_plays_a_whole_season():
    """Twenty of thirty clubs were projected over 161 games because live games
    counted as neither played nor remaining."""
    rows = _outlook()
    short = []
    for r in rows:
        c = r.get("current") or {}
        gp, rem = c.get("gamesPlayed"), c.get("remGames")
        if gp is None or rem is None:
            continue
        if gp + rem != 162:
            short.append((r.get("team"), gp, rem, 162 - gp - rem))
    assert not short, (
        f"clubs whose season does not add up to 162: {short[:8]}. A club short a "
        "game is projected over a schedule it does not have")


def test_the_postseason_rounds_are_nested():
    """A club cannot win the pennant without reaching the championship series."""
    rows = _outlook()
    bad = []
    for r in rows:
        c = r.get("current") or {}
        if c.get("wsPct") is None:
            continue
        for a, b in (("ldsPct", "lcsPct"), ("lcsPct", "pennantPct"),
                     ("pennantPct", "wsPct"), ("playoffPct", "ldsPct")):
            if c.get(a) is not None and c.get(b) is not None and c[a] < c[b] - 1e-9:
                bad.append((r.get("team"), a, c[a], b, c[b]))
    assert not bad, f"a later round is more likely than an earlier one: {bad[:6]}"


def test_the_postseason_conserves_its_own_totals():
    """One champion, two pennants, four byes, twelve berths. If a sum drifts the
    bracket is double-counting or dropping a series."""
    rows = _outlook()
    have = [r for r in rows if (r.get("current") or {}).get("wsPct") is not None]
    if len(have) < 30:
        pytest.skip("no postseason block on this build")
    tot = lambda k: sum((r["current"].get(k) or 0) for r in have)   # noqa: E731
    for key, want, tol in (("wsPct", 1.0, 0.03), ("pennantPct", 2.0, 0.04),
                           ("byePct", 4.0, 0.05), ("playoffPct", 12.0, 0.05)):
        got = tot(key)
        assert abs(got - want) <= tol, f"sum({key}) = {got:.3f}, expected {want}"


def test_the_win_band_brackets_the_mean():
    rows = _outlook()
    bad = []
    for r in rows:
        c = r.get("current") or {}
        lo, mid, hi = c.get("projWinsP10"), c.get("projWinsMean"), c.get("projWinsP90")
        if None in (lo, mid, hi):
            continue
        if not (lo <= mid <= hi):
            bad.append((r.get("team"), lo, mid, hi))
    assert not bad, f"the projected-wins band does not bracket its mean: {bad[:6]}"


# --------------------------------------------------------------------------
# The futures board
# --------------------------------------------------------------------------

def test_the_futures_board_is_whole_or_empty():
    d = _load("futures.json")
    clubs = d.get("clubs") or []
    assert len(clubs) in (0, 30), (
        f"{len(clubs)} clubs on the futures board. A partial board is the defect "
        "signature; a board of none is the honest degrade")
    if not clubs:
        assert d.get("empty_reason")


def test_the_futures_board_never_prices_a_certainty():
    """p = 0 and p = 1 are both live in the artifact, and an infinity rendered
    into a price cell looks like a number."""
    clubs = (_load("futures.json").get("clubs") or [])
    if not clubs:
        pytest.skip("degraded board")
    for c in clubs:
        for pk, ak in (("wsPct", "impliedAmericanWS"),
                       ("pennantPct", "impliedAmericanPennant"),
                       ("divisionPct", "impliedAmericanDivision")):
            p, a = c.get(pk), c.get(ak)
            if p in (0.0, 1.0):
                assert a is None, f"{c['team']} priced a certainty on {pk}"
            if a is not None:
                assert isinstance(a, (int, float)) and abs(a) < 1e6


def test_no_futures_probability_is_published_with_a_zero_width_interval():
    clubs = (_load("futures.json").get("clubs") or [])
    if not clubs:
        pytest.skip("degraded board")
    for c in clubs:
        mc = c.get("mcWs") or {}
        if not mc:
            continue
        assert mc["hi95"] > mc["lo95"], (
            f"{c['team']} publishes a World Series probability with an interval "
            "of zero width, which asserts the simulator has no sampling noise")


# --------------------------------------------------------------------------
# The Hall of Fame board
# --------------------------------------------------------------------------

def test_the_hall_of_fame_bands_partition_their_population():
    d = _load("hof_board.json")
    c = d["counts"]
    assert c["n_eligible"] + c["n_watch"] + c["n_not_yet_eligible"] == c["n_ten_plus_seasons"]


def test_no_hall_of_famer_is_labelled_a_non_inductee():
    """The defect: the shipped label called Charlie Gehringer, Ed Delahanty and
    Eddie Plank non-Hall-of-Famers because an id crosswalk that was on disk was
    never used."""
    d = _load("hof_board.json")
    lab = d["labels"]["label_any"]
    led = d["ledger"]
    assert lab["positive"] >= led["n_in_eligible_universe"], (
        f"{led['n_in_eligible_universe']} inductees are inside the eligible "
        f"universe but only {lab['positive']} carry a positive label")


def test_the_label_census_accounts_for_every_row():
    d = _load("hof_board.json")
    for name, lab in d["labels"].items():
        if not isinstance(lab, dict):
            continue
        assert lab["positive"] + lab["negative"] + lab["censored"] == d["labels"]["n_rows"], name


def test_the_hall_of_fame_quantile_ladder_is_monotone():
    q = _load("hof_board.json")["line"]["quantiles"]
    vals = [q[k] for k in sorted(q)]
    assert all(a <= b for a, b in zip(vals, vals[1:])), f"ladder not monotone: {vals}"


# --------------------------------------------------------------------------
# In-Game Management
# --------------------------------------------------------------------------

def test_the_decision_and_execution_split_is_exact():
    d = _load("management_board.json")
    assert d["running_game"]["decomposition"]["identity_max_abs_error"] == 0.0


def test_every_priced_attempt_is_accounted_for():
    """An uncounted exclusion is where every defect this session came from."""
    d = _load("management_board.json")["running_game"]
    ex = d["excluded"]
    assert all(isinstance(v, int) and v >= 0 for v in ex.values())
    assert d["n_attempts_priced"] > 0


def test_the_management_board_publishes_no_per_club_plus_metric():
    """The gate withheld it. A column of it would be a ranking of noise that a
    reader has no way to recognise as one."""
    t = _load("management_board.json")["teams"]
    if t.get("status") != "built":
        pytest.skip("club board not built")
    for r in t["rows"]:
        for k in r:
            assert "dv" not in k and "decision" not in k, k


def test_the_success_rates_are_rates():
    t = _load("management_board.json")["teams"]
    if t.get("status") != "built":
        pytest.skip("club board not built")
    for r in t["rows"]:
        for k in ("success_rate", "share_2B", "share_3B", "mean_breakeven_faced"):
            v = r.get(k)
            assert v is None or _is_prob(v), f"{r['team']} {k} = {v}"
        if r.get("share_2B") is not None and r.get("share_3B") is not None:
            assert r["share_2B"] + r["share_3B"] <= 1.0 + 1e-9


# --------------------------------------------------------------------------
# The eFV claim instruments
# --------------------------------------------------------------------------

def test_every_claim_cell_carries_a_floor():
    """A delta without a floor is a number a reader will treat as a result."""
    a = _load("source_backtest.json").get("accuracy") or {}
    ci = a.get("claim_instruments") or {}
    if not ci:
        pytest.skip("claim instruments are not in this build")
    missing = []
    for frame, cells in (ci.get("head_to_head_floors") or {}).items():
        if not isinstance(cells, dict) or "point_delta" not in cells:
            continue
        if (cells.get("floor_E_cond_in_run") or {}).get("mde95") is None:
            missing.append(frame)
    assert not missing, f"claim cells with a delta and no floor: {missing}"


def test_the_disagreement_share_travels_with_its_interval():
    """The site published this as a bare percentage once. It was a coin flip."""
    a = _load("source_backtest.json").get("accuracy") or {}
    det = a.get("xfv_vs_consensus_detail") or {}
    if not det:
        pytest.skip("the disagreement detail is not in this build")
    assert det.get("xfv_right_share_ci95"), "the share has no interval beside it"
    lo, hi = det["xfv_right_share_ci95"]
    assert lo <= det["xfv_right_share_on_disagreements"] <= hi


# --------------------------------------------------------------------------
# MUTATION: prove each guard fires on the defect it names
# --------------------------------------------------------------------------
#
# A guard that has never failed is a guard nobody has tested. Each mutation
# below is the ACTUAL defect that shipped, injected into a copy of the served
# artifact, and each asserts the corresponding check rejects it. Without this
# section the file above is twenty assertions that happen to pass.

import copy as _copy                                          # noqa: E402
import test_served_invariants as _self                        # noqa: E402


def _with(name, mutate):
    """Run a check against a mutated copy of one artifact."""
    real = _self._load

    def fake(n):
        d = real(n)
        return mutate(_copy.deepcopy(d)) if n == name else d
    return fake


def _apply(monkeypatch, name, mutate):
    monkeypatch.setattr(_self, "_load", _with(name, mutate))


def test_mutation_a_probability_above_one_is_caught(monkeypatch):
    """Milwaukee served playoffPct 1.001."""
    def m(d):
        d["team_outlook"][0]["current"]["playoffPct"] = 1.001
        return d
    _apply(monkeypatch, "mlb_projections.json", m)
    with pytest.raises(AssertionError, match="outside"):
        _self.test_no_published_probability_leaves_the_unit_interval()


def test_mutation_a_club_short_a_game_is_caught(monkeypatch):
    """Twenty of thirty clubs were projected over a 161-game season."""
    def m(d):
        d["team_outlook"][0]["current"]["remGames"] -= 1
        return d
    _apply(monkeypatch, "mlb_projections.json", m)
    with pytest.raises(AssertionError, match="does not add up"):
        _self.test_every_club_plays_a_whole_season()


def test_mutation_a_missing_club_is_caught(monkeypatch):
    """Arizona vanished on a len<=3 name guard."""
    def m(d):
        d["team_outlook"] = [r for r in d["team_outlook"] if r.get("team") != "ARI"]
        return d
    _apply(monkeypatch, "mlb_projections.json", m)
    with pytest.raises(AssertionError, match="not 30"):
        _self.test_every_club_is_present_exactly_once()


def test_mutation_a_broken_playoff_identity_is_caught(monkeypatch):
    def m(d):
        d["team_outlook"][0]["current"]["wildcardPct"] = 0.5
        return d
    _apply(monkeypatch, "mlb_projections.json", m)
    with pytest.raises(AssertionError, match="!= playoffPct"):
        _self.test_the_playoff_identity_holds_on_every_club()


def test_mutation_an_unreachable_later_round_is_caught(monkeypatch):
    def m(d):
        for r in d["team_outlook"]:
            if (r.get("current") or {}).get("wsPct") is not None:
                r["current"]["wsPct"] = 0.99
                break
        return d
    _apply(monkeypatch, "mlb_projections.json", m)
    with pytest.raises(AssertionError, match="more likely than an earlier"):
        _self.test_the_postseason_rounds_are_nested()


def test_mutation_a_lost_champion_is_caught(monkeypatch):
    def m(d):
        for r in d["team_outlook"]:
            if (r.get("current") or {}).get("wsPct"):
                r["current"]["wsPct"] = 0.0
        return d
    _apply(monkeypatch, "mlb_projections.json", m)
    with pytest.raises(AssertionError, match=r"sum\(wsPct\)"):
        _self.test_the_postseason_conserves_its_own_totals()


def test_mutation_a_priced_certainty_is_caught(monkeypatch):
    """An infinity in a price cell looks like a number."""
    def m(d):
        if d.get("clubs"):
            d["clubs"][0]["wsPct"] = 1.0
            d["clubs"][0]["impliedAmericanWS"] = -999999999
        return d
    _apply(monkeypatch, "futures.json", m)
    with pytest.raises(AssertionError, match="priced a certainty"):
        _self.test_the_futures_board_never_prices_a_certainty()


def test_mutation_a_partial_futures_board_is_caught(monkeypatch):
    def m(d):
        d["clubs"] = (d.get("clubs") or [])[:17]
        return d
    _apply(monkeypatch, "futures.json", m)
    with pytest.raises(AssertionError, match="partial board"):
        _self.test_the_futures_board_is_whole_or_empty()


def test_mutation_a_zero_width_interval_is_caught(monkeypatch):
    def m(d):
        if d.get("clubs"):
            d["clubs"][0]["mcWs"] = {"lo95": 0.0, "hi95": 0.0}
        return d
    _apply(monkeypatch, "futures.json", m)
    with pytest.raises(AssertionError, match="zero width"):
        _self.test_no_futures_probability_is_published_with_a_zero_width_interval()


def test_mutation_a_hall_of_famer_labelled_out_is_caught(monkeypatch):
    """The Gehringer defect, injected."""
    def m(d):
        d["labels"]["label_any"]["positive"] = 3
        return d
    _apply(monkeypatch, "hof_board.json", m)
    with pytest.raises(AssertionError, match="positive label"):
        _self.test_no_hall_of_famer_is_labelled_a_non_inductee()


def test_mutation_a_broken_band_partition_is_caught(monkeypatch):
    def m(d):
        d["counts"]["n_not_yet_eligible"] = 0
        return d
    _apply(monkeypatch, "hof_board.json", m)
    with pytest.raises(AssertionError):
        _self.test_the_hall_of_fame_bands_partition_their_population()


def test_mutation_a_plus_metric_on_the_club_board_is_caught(monkeypatch):
    """The gate withheld it; this is what stops it coming back."""
    def m(d):
        if (d.get("teams") or {}).get("rows"):
            d["teams"]["rows"][0]["sum_dv_wins"] = 1.4
        return d
    _apply(monkeypatch, "management_board.json", m)
    with pytest.raises(AssertionError):
        _self.test_the_management_board_publishes_no_per_club_plus_metric()


def test_mutation_a_broken_decision_identity_is_caught(monkeypatch):
    def m(d):
        d["running_game"]["decomposition"]["identity_max_abs_error"] = 0.02
        return d
    _apply(monkeypatch, "management_board.json", m)
    with pytest.raises(AssertionError):
        _self.test_the_decision_and_execution_split_is_exact()


# --------------------------------------------------------------------------
# The prospect board
# --------------------------------------------------------------------------

def test_the_board_ranks_are_a_contiguous_permutation():
    """A board rank is an ORDERING, so the ranked set must be exactly 1..n with
    no gaps and no ties. A duplicate rank means two players claim one row and a
    gap means a row was dropped after the ordering was assigned, which is what a
    silently-filtered board looks like from the outside."""
    d = _load("timeseries.json")
    ranked = sorted(p["overall_rank"] for p in (d.get("players") or [])
                    if p.get("overall_rank"))
    if len(ranked) < 100:
        pytest.skip("no baked board ranks on this build")
    assert len(ranked) == len(set(ranked)), (
        f"{len(ranked) - len(set(ranked))} duplicate board ranks")
    assert ranked == list(range(1, len(ranked) + 1)), (
        f"board ranks are not contiguous: min {ranked[0]}, max {ranked[-1]}, "
        f"n {len(ranked)}")


def test_a_graduated_player_never_holds_a_board_rank():
    d = _load("timeseries.json")
    bad = [p.get("player_key") for p in (d.get("players") or [])
           if p.get("status") == "debuted" and p.get("overall_rank")]
    assert not bad, f"debuted players holding a board rank: {bad[:6]}"


# --------------------------------------------------------------------------
# The betting board
# --------------------------------------------------------------------------

def _team_bets():
    d = _load("betting.json")
    tb = d.get("team_bets") or []
    if not tb:
        pytest.skip("no games on the slate")
    return d, tb


def test_every_game_probability_complements():
    """Two teams play; one wins. If these ever fail to sum to one the devig or
    the model has produced something that is not a probability pair."""
    _d, tb = _team_bets()
    bad = []
    for r in tb:
        m = r.get("model") or {}
        ph, pa = m.get("p_home"), m.get("p_away")
        if ph is None or pa is None:
            continue
        if not (_is_prob(ph) and _is_prob(pa)) or abs((ph + pa) - 1.0) > 1e-6:
            bad.append((r.get("game_pk"), ph, pa))
    assert not bad, f"home and away win probabilities do not complement: {bad[:5]}"


def test_the_run_rates_are_physically_possible():
    _d, tb = _team_bets()
    bad = []
    for r in tb:
        m = r.get("model") or {}
        for k in ("lam_home", "lam_away"):
            v = m.get(k)
            if v is not None and not (0.0 < v < 20.0):
                bad.append((r.get("game_pk"), k, v))
    assert not bad, f"implausible expected run rates: {bad[:5]}"


def test_the_fair_total_is_the_sum_of_its_own_run_rates():
    """A total that has drifted from the lambdas it is built on means two
    different models are being published side by side."""
    _d, tb = _team_bets()
    bad = []
    for r in tb:
        m = r.get("model") or {}
        ft, lh, la = m.get("fair_total"), m.get("lam_home"), m.get("lam_away")
        if None in (ft, lh, la):
            continue
        if abs(ft - (lh + la)) > 0.06:
            bad.append((r.get("game_pk"), ft, round(lh + la, 3)))
    assert not bad, f"fair_total disagrees with lam_home + lam_away: {bad[:5]}"


def test_the_record_arithmetic_closes():
    """The record is append-only and is the one number on the page that can
    embarrass us, so it has to add up."""
    rec = (_load("betting.json").get("record") or {})
    if not rec:
        pytest.skip("no record block")
    settled = rec.get("n_settled")
    parts = (rec.get("won"), rec.get("lost"), rec.get("push"))
    if settled is None or any(p is None for p in parts):
        pytest.skip("record block is partial")
    assert sum(parts) == settled, (
        f"won + lost + push = {sum(parts)} against n_settled {settled}")
    if rec.get("n_rows") is not None and rec.get("n_open") is not None:
        assert rec["n_open"] + settled == rec["n_rows"], (
            f"open {rec['n_open']} + settled {settled} != rows {rec['n_rows']}")


# --------------------------------------------------------------------------
# The arbitration ladder
# --------------------------------------------------------------------------

def _arb_rows():
    rows = (_load("arbitration.json").get("rows") or [])
    if not rows:
        pytest.skip("no arbitration rows")
    return rows


def test_the_arbitration_total_is_the_sum_of_its_own_ladder():
    """`tot` is what the page shows as a club's remaining arbitration cost. If
    it drifts from the ladder beneath it, the summary and the detail are two
    different numbers."""
    bad = []
    for r in _arb_rows():
        lad = r.get("l") or []
        if r.get("tot") is None or not lad:
            continue
        s = sum(x[1] for x in lad if x[1] is not None)
        if abs(s - r["tot"]) > 1:
            bad.append((r.get("n"), s, r["tot"]))
    assert not bad, f"tot != sum of the ladder: {bad[:5]}"


def test_every_arbitration_projection_sits_inside_its_own_band():
    bad = []
    for r in _arb_rows():
        for x in (r.get("l") or []):
            season, proj, lo, hi = x[0], x[1], x[2], x[3]
            if None in (proj, lo, hi):
                continue
            if not (lo <= proj <= hi):
                bad.append((r.get("n"), season, lo, proj, hi))
    assert not bad, f"a projection sits outside its own low-high band: {bad[:5]}"


def test_the_arbitration_ladder_and_the_war_series_are_aligned():
    """`w` is documented as aligned to `l`. A length mismatch silently pairs a
    season's dollars with a different season's WAR."""
    bad = []
    for r in _arb_rows():
        lad, w = r.get("l") or [], r.get("w") or []
        if lad and w and len(lad) != len(w):
            bad.append((r.get("n"), len(lad), len(w)))
    assert not bad, f"ladder and WAR series are different lengths: {bad[:5]}"


def test_the_ladder_seasons_are_strictly_increasing():
    bad = []
    for r in _arb_rows():
        yrs = [x[0] for x in (r.get("l") or [])]
        if yrs != sorted(yrs) or len(set(yrs)) != len(yrs):
            bad.append((r.get("n"), yrs))
    assert not bad, f"ladder seasons repeat or run backwards: {bad[:5]}"


def test_the_control_years_match_the_ladder_length():
    bad = [(r.get("n"), r.get("yl"), len(r.get("l") or []))
           for r in _arb_rows()
           if r.get("yl") is not None and r["yl"] != len(r.get("l") or [])]
    assert not bad, f"club-control years disagree with the ladder length: {bad[:5]}"


def test_mutation_a_duplicate_board_rank_is_caught(monkeypatch):
    def m(d):
        ranked = [p for p in d["players"] if p.get("overall_rank")]
        ranked[1]["overall_rank"] = ranked[0]["overall_rank"]
        return d
    _apply(monkeypatch, "timeseries.json", m)
    with pytest.raises(AssertionError, match="duplicate board ranks"):
        _self.test_the_board_ranks_are_a_contiguous_permutation()


def test_mutation_a_non_complementing_game_is_caught(monkeypatch):
    def m(d):
        if d.get("team_bets"):
            d["team_bets"][0]["model"]["p_away"] = 0.9
        return d
    _apply(monkeypatch, "betting.json", m)
    with pytest.raises(AssertionError, match="do not complement"):
        _self.test_every_game_probability_complements()


def test_mutation_a_drifted_fair_total_is_caught(monkeypatch):
    def m(d):
        if d.get("team_bets"):
            d["team_bets"][0]["model"]["fair_total"] = 99.0
        return d
    _apply(monkeypatch, "betting.json", m)
    with pytest.raises(AssertionError, match="disagrees with"):
        _self.test_the_fair_total_is_the_sum_of_its_own_run_rates()


def test_mutation_a_record_that_does_not_add_up_is_caught(monkeypatch):
    def m(d):
        d["record"] = {"n_rows": 10, "n_open": 2, "n_settled": 8,
                       "won": 5, "lost": 2, "push": 0}
        return d
    _apply(monkeypatch, "betting.json", m)
    with pytest.raises(AssertionError, match="n_settled"):
        _self.test_the_record_arithmetic_closes()


def test_mutation_an_arbitration_total_that_drifts_is_caught(monkeypatch):
    def m(d):
        d["rows"][0]["tot"] = (d["rows"][0].get("tot") or 0) + 1_000_000
        return d
    _apply(monkeypatch, "arbitration.json", m)
    with pytest.raises(AssertionError, match="sum of the ladder"):
        _self.test_the_arbitration_total_is_the_sum_of_its_own_ladder()


def test_mutation_a_projection_outside_its_band_is_caught(monkeypatch):
    def m(d):
        for r in d["rows"]:
            if r.get("l"):
                r["l"][0][1] = (r["l"][0][3] or 0) + 1
                break
        return d
    _apply(monkeypatch, "arbitration.json", m)
    with pytest.raises(AssertionError, match="outside its own"):
        _self.test_every_arbitration_projection_sits_inside_its_own_band()


def test_mutation_a_misaligned_war_series_is_caught(monkeypatch):
    def m(d):
        for r in d["rows"]:
            if r.get("l") and r.get("w"):
                r["w"] = r["w"][:-1] if len(r["w"]) > 1 else [0.0, 0.0]
                break
        return d
    _apply(monkeypatch, "arbitration.json", m)
    with pytest.raises(AssertionError, match="different lengths"):
        _self.test_the_arbitration_ladder_and_the_war_series_are_aligned()
