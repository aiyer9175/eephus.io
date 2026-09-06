# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
"""Tests for the ONE probability-mass source behind every props row.

WHAT THIS FILE IS: the regression fence around the 2026-09-06 repair that gave
/betting/ a single pmf per prop market. Before it, `props_fair_lines` priced
`1+ hits` and `1+ home runs` as a per-PA Bernoulli complement
(`1 - (1 - p) ** exp_pa`) while `props_value_bets` priced the SAME two markets
as a Poisson through `_props_side_probabilities`, so one page carried two
probabilities for one bet. Measured on a slot-1 hitter (exp_pa 4.65, lam 1.60):
0.85929 against 0.79810 at the 0.5 line, a gap of 0.06118.

WHAT IT IS NOT: a calibration test. Nothing here checks that a binomial fits
outcomes better than a Poisson, because no props row has ever settled and no
props row is served (the pull is inert without both arming variables). These
tests pin CONSISTENCY and DISCLOSURE, which is all the evidence supports:

  1. both surfaces return the same number for the same market, line and lambda;
  2. the push mass is handled on a whole-number line, on both distributions;
  3. the distribution name rides every row, fair line and value row alike, and
     a fallback to Poisson is stated rather than silent.

WHAT IT REFUSES TO CLAIM: that the declared distributions are right. It pins
only that each market declares one, states a reason, and that the two surfaces
cannot disagree about which one they used.

Every test doubles as a plain function: `python test_betting_props_pmf.py`
runs them all without pytest, the same no-pytest escape hatch
test_betting_props.py carries.
"""
from __future__ import annotations

from pathlib import Path

import betting_export as be
import betting_ingest as bi
import betting_model as bm

ROOT = Path(__file__).parent


# ===========================================================================
# fixtures (inline; nothing here reads tonight's data/ files)
# ===========================================================================
def _order_row(slot, mid, name):
    return {"slot": slot, "key": str(mid), "name": name, "bats": "R",
            "hem_plus": 100, "pa": 500}


_HIT_LB = {"teams": [
    {"team": "BOS", "orders": {
        "vr": [_order_row(i, 100 + i, f"BOS bat {i}") for i in range(1, 10)],
        "vl": [_order_row(i, 100 + i, f"BOS bat {i}") for i in range(1, 10)]}},
    {"team": "NYY", "orders": {
        "vr": [_order_row(i, 300 + i, f"NYY bat {i}") for i in range(1, 10)],
        "vl": [_order_row(i, 300 + i, f"NYY bat {i}") for i in range(1, 10)]}},
]}


def _fantasy():
    """Hitters whose rates make round lambdas, and pitchers CARRYING `bf`,
    which the older props fixtures do not: the batters-faced trial count is
    the whole reason the strikeout market can be a binomial at all."""
    players = []
    for base in (100, 300):
        for i in range(1, 10):
            players.append({"mlbam": base + i, "side": "hit", "ros": {
                "pa": 500, "h": 130, "hr": 25, "single": 85,
                "double": 30, "triple": 3, "hr2": 0}})
    players.append({"mlbam": 11, "side": "pit", "name": "Home Arm",
                    "ros": {"ip": 150, "gs": 25, "k": 165, "er": 55,
                            "h": 130, "bf": 630}})
    players.append({"mlbam": 22, "side": "pit", "name": "Away Arm",
                    "ros": {"ip": 140, "gs": 25, "k": 150, "er": 60,
                            "h": 140, "bf": 600}})
    return {"players": players}


_GAMES = [{"game_pk": 9, "date": "2026-08-16", "odds_event_id": "ev9",
           "start": "2026-08-16T23:05:00Z",
           "home": {"org": "BOS", "probable": {"mlbam": 11, "name": "Home Arm"}},
           "away": {"org": "NYY", "probable": {"mlbam": 22, "name": "Away Arm"}}}]


class _FakeLoad:
    """Swap betting_export._load for a fixture reader, restore on exit."""

    def __init__(self, files):
        self.files = files

    def __enter__(self):
        self._orig = be._load
        files = self.files
        be._load = lambda name: files.get(name)
        return self

    def __exit__(self, *exc):
        be._load = self._orig


def _fair_lines():
    files = {"hitter_leaderboards.json": _HIT_LB, "fantasy.json": _fantasy()}
    with _FakeLoad(files):
        return be.props_fair_lines(_GAMES, starters={}, pitch_hands={11: "R",
                                                                    22: "R"})


def _side(name, point, over=-110, under=-110):
    return [{"name": "Over", "description": name, "price": over, "point": point},
            {"name": "Under", "description": name, "price": under, "point": point}]


#: One book, all four markets, and the LINES ARE THE FAIR-LINE TABLE'S OWN
#: (K at 6.5, total bases at 1.5, hits at 0.5, home runs at 0.5) so the value
#: row and the fair-line row answer the identical question and can be compared
#: number to number. A book posting a different line is a different bet, and
#: the cross-surface test says so explicitly.
_PROPS_RAW = {
    "id": "ev9", "commence_time": "2026-08-16T23:05:00Z",
    "home_team": "Boston Red Sox", "away_team": "New York Yankees",
    "bookmakers": [
        {"key": "draftkings", "title": "DraftKings",
         "last_update": "2026-08-16T20:00:00Z",
         "markets": [
             {"key": "pitcher_strikeouts", "outcomes": _side("Home Arm", 6.5)},
             {"key": "batter_total_bases", "outcomes": _side("BOS bat 1", 1.5)},
             {"key": "batter_hits", "outcomes": _side("BOS bat 1", 0.5)},
             {"key": "batter_home_runs", "outcomes": _side("BOS bat 1", 0.5)},
         ]},
    ]}


def _snapshots():
    rec = bi.parse_props_snapshot(_PROPS_RAW)
    rec["_captured_at"] = "2026-08-16T20:01:00Z"
    return {"ev9": rec}


def _team_bets():
    return [{"game_pk": 9, "odds_event_id": "ev9",
             "start": "2026-08-16T23:05:00Z",
             "home": {"org": "BOS"}, "away": {"org": "NYY"},
             "moneyline": [{"side": "home", "edge": 0.08, "odds": -110,
                            "book": "dk", "model_prob": 0.6,
                            "market_fair_prob": 0.52}]}]


def _value():
    return be.props_value_bets(_team_bets(), _fair_lines(), slots={},
                               snapshots=_snapshots(), on_date="2026-08-16")


def _fair_prop(pf, section, player, prop):
    for rec in pf[section]:
        if (rec.get("name") or "") == player:
            for pr in rec["props"]:
                if pr["prop"] == prop:
                    return pr
    return None


# ===========================================================================
# 1. THE DEFECT: both surfaces must return the same probability
# ===========================================================================
def test_both_surfaces_return_the_same_probability():
    """THE POINT OF THE WHOLE LANE. For every market whose book line equals
    the fair-line table's own line, the value row's model probability and the
    published p_over must be the SAME number, not two roundings of two
    distributions.

    MUTATION PROOF: restore either old path (make the fair-line 1+ hits row
    `1 - (1 - p) ** exp_pa` again, or drop `dist=` from the value block's
    `_props_side_probabilities` call) and the batter_hits pair fails here."""
    pf = _fair_lines()
    pv = _value()
    overs = {r["market"]: r for r in pv["rows"] if r["side"] == "over"}
    assert len(overs) == 4, (sorted(overs), pv["rejections"])
    checked = 0
    for mkey, row in overs.items():
        section, prop = be.PROPS_MARKET_LAMBDAS[mkey.replace("props_", "")]
        pr = _fair_prop(pf, section, row["player"], prop)
        assert pr is not None, (mkey, row["player"])
        assert pr["over_line"] == row["line"], (
            f"{mkey}: fixture must post the fair-line table's own line so the "
            "two surfaces answer one question")
        assert pr["lam"] == row["lam"], (mkey, pr["lam"], row["lam"])
        assert abs(pr["p_over"] - round(row["model_prob"], 4)) < 1e-12, (
            f"{mkey}: fair line publishes {pr['p_over']} while the value block "
            f"prices {row['model_prob']}; two surfaces, one bet")
        assert pr["pmf"] == row["pmf"], (mkey, pr["pmf"], row["pmf"])
        checked += 1
    assert checked == 4


def test_the_two_entry_points_agree_at_the_function_level():
    """Same market, same line, same lambda, through both doors: `_prop_row`
    (the fair-line table) and `_props_side_probabilities` (the value block).
    Pinned across every declared market so a new market cannot be added down
    one path only."""
    for name, spec in be.PROPS_DISTRIBUTIONS.items():
        if spec["dist"] is None:
            continue
        for lam, trials in ((1.6, 4.65), (0.22, 4.2), (6.6, 22.0)):
            row = be._prop_row(name, lam, n_trials=trials, over_line=1.5)
            direct = be._props_side_probabilities(
                row["lam"], 1.5, dist=spec["dist"], n_trials=row["n_trials"])
            assert row["p_over"] == round(direct["p_over"], 4), (name, lam)
            assert row["pmf"] == direct["pmf"], (name, lam)


def test_the_old_bernoulli_path_is_gone_from_source():
    """The fair-line block computed `1 - (1 - p_hit) ** exp_pa` inline. A
    second probability path is the defect itself, so its absence is pinned on
    source: there is exactly ONE tail sum in the module and it lives behind
    _props_pmf."""
    src = (ROOT / "betting_export.py").read_text(encoding="utf-8")
    assert "(1.0 - p_hit) ** exp_pa" not in src
    assert "(1.0 - p_hr) ** exp_pa" not in src
    # every Poisson pmf in this module is fetched inside _props_pmf; nothing
    # else may build one and price off it.
    head, _, tail = src.partition("def _props_pmf(")
    body, _, rest = tail.partition("\ndef _poisson_over(")
    assert "bm._poisson_pmf(" not in head, \
        "a Poisson pmf is built before the single mass source"
    assert "bm._poisson_pmf(" not in rest, \
        "a second Poisson pmf path exists after the single mass source"
    assert body.count("bm._poisson_pmf(") == 3, \
        "the three Poisson returns of _props_pmf (default, no-trials, p>1)"


# ===========================================================================
# 2. THE PUSH MASS ON WHOLE NUMBERS
# ===========================================================================
def test_push_mass_is_handled_on_whole_numbers_under_both_distributions():
    """A whole-number line refunds. The sides come back CONDITIONED on the bet
    resolving and `p_push` rides beside them, which is what `_priced_side`
    scales EV by. Pinned on both distributions because the binomial changes
    the push mass materially: at lam 1.6 over 4.65 PA the Poisson puts 0.25843
    on exactly two and the binomial 0.32413, and the push is a straight
    multiplier on published EV."""
    for dist, trials in (("poisson", None), ("binomial", 4.65)):
        ps = be._props_side_probabilities(1.6, 2.0, dist=dist, n_trials=trials)
        assert ps["p_push"] > 0, dist
        assert abs(ps["p_over"] + ps["p_under"] - 1.0) < 1e-12, dist
        total = (1.0 - ps["p_push"]) * (ps["p_over"] + ps["p_under"]) \
            + ps["p_push"]
        assert abs(total - 1.0) < 1e-12, dist
        assert ps["pmf"] == dist
    po = be._props_side_probabilities(1.6, 2.0)["p_push"]
    pb = be._props_side_probabilities(1.6, 2.0, dist="binomial",
                                      n_trials=4.65)["p_push"]
    assert abs(po - 0.25843) < 5e-6, po
    assert abs(pb - 0.32413) < 5e-6, pb


def test_a_half_point_line_cannot_push():
    for dist, trials in (("poisson", None), ("binomial", 4.65)):
        ps = be._props_side_probabilities(1.6, 1.5, dist=dist, n_trials=trials)
        assert ps["p_push"] is None, dist
        assert abs(ps["p_over"] + ps["p_under"] - 1.0) < 1e-12, dist


def test_the_fair_line_never_lands_on_a_whole_number():
    """A model fair line has no book to refund it, so the derived over line
    steps past a whole number. Kept from the pre-repair contract."""
    assert be._prop_row("Strikeouts", 5.91, n_trials=22.0)["over_line"] == 6.5
    assert be._prop_row("Strikeouts", 6.0, n_trials=22.0)["over_line"] == 6.5
    assert be._prop_row("Earned runs", 3.0)["over_line"] == 3.5


# ===========================================================================
# 3. THE DISTRIBUTION NAME RIDES EVERY ROW
# ===========================================================================
def test_every_fair_line_row_carries_the_model_and_the_distribution():
    pf = _fair_lines()
    seen = 0
    for section in ("pitchers", "hitters"):
        assert pf[section], section
        for rec in pf[section]:
            for pr in rec["props"]:
                assert pr["model_id"] == be.PROPS_MODEL_ID, pr
                assert "pmf" in pr and "n_trials" in pr, pr
                if pr["p_over"] is None:
                    # a fair-number-only row claims no distribution, and says
                    # why rather than leaving the field bare
                    assert pr["pmf"] is None and pr["pmf_basis"], pr
                else:
                    assert pr["pmf"] in ("poisson", "binomial"), pr
                seen += 1
    assert seen >= 8, seen


def test_every_value_row_carries_the_model_and_the_distribution():
    pv = _value()
    assert pv["rows"], pv["rejections"]
    for r in pv["rows"]:
        assert r["model_id"] == be.PROPS_MODEL_ID, r
        assert r["pmf"] in ("poisson", "binomial"), r
        assert r["prop"] in be.PROPS_DISTRIBUTIONS, r
    assert "one_probability_per_bet" in pv["method"]


def test_a_fallback_to_poisson_is_stated_not_silent():
    """A binomial market handed no trial count must NOT quietly become a
    Poisson: it prices as one and the row says so in `pmf_basis`."""
    row = be._prop_row("1+ hits", 1.16, over_line=0.5)
    assert row["pmf"] == "poisson"
    assert "no trial count" in row["pmf_basis"]
    assert row["n_trials"] is None
    # lam above the trial count is not a probability; also stated
    ps = be._props_side_probabilities(6.0, 1.5, dist="binomial", n_trials=4.0)
    assert ps["pmf"] == "poisson"
    assert "exceeds the trial count" in ps["pmf_basis"]
    # and the honest path stays clean
    ok = be._prop_row("1+ hits", 1.16, over_line=0.5, n_trials=4.65)
    assert ok["pmf"] == "binomial" and ok["pmf_basis"] is None


def test_every_priced_market_declares_a_distribution_with_a_reason():
    """No blanket Poisson: the market map and the distribution table are one
    table, and a market cannot be priced without a stated reason for its
    distribution."""
    for mkey, (section, prop) in be.PROPS_MARKET_LAMBDAS.items():
        assert mkey in bi.PROPS_MARKETS, mkey
        assert section in ("pitchers", "hitters"), (mkey, section)
        spec = be.PROPS_DISTRIBUTIONS.get(prop)
        assert spec is not None, f"{mkey} prices {prop!r} with no declaration"
        assert spec["dist"] in ("poisson", "binomial"), (prop, spec)
        assert len(spec["reason"]) >= 60, (prop, "reason is a stub")
    for name, spec in be.PROPS_DISTRIBUTIONS.items():
        assert spec["reason"], name
        if spec["dist"] == "binomial":
            assert spec["trials"], f"{name} is binomial over nothing"


def test_the_method_block_publishes_the_choice_and_its_reason():
    pf = _fair_lines()
    # `distribution` MUST STAY A STRING. assets/betting.js renders it verbatim
    # through one escaper, kv("Distribution", esc(meth.distribution || "-")),
    # and esc() is String(s).replace(...), so a dict here reaches a paying
    # reader as the literal "[object Object]". The per-market table lives in a
    # sibling key no client reads. Found by review 2026-09-06, after this file
    # had already shipped the dict shape.
    assert isinstance(pf["method"]["distribution"], str)
    assert pf["method"]["distribution"].strip()
    dist = pf["method"]["distribution_by_market"]
    assert dist["model_id"] == be.PROPS_MODEL_ID
    assert set(dist["by_market"]) == set(be.PROPS_DISTRIBUTIONS)
    assert "not calibrated" in dist["not_claimed"] or \
        "is calibrated" in dist["not_claimed"]
    for name, cell in dist["by_market"].items():
        assert cell["reason"] == be.PROPS_DISTRIBUTIONS[name]["reason"]


# ===========================================================================
# 4. THE MASS FUNCTION ITSELF
# ===========================================================================
def test_the_binomial_support_is_capped_at_the_trial_count():
    """The structural argument for the whole change: a hitter cannot collect
    six hits in 4.65 plate appearances. The Poisson gave that 0.00604 of its
    mass (measured 2026-09-06); the binomial gives it zero because the outcome
    is not in the sample space."""
    pmf, used, basis = be._props_pmf(1.6, dist="binomial", n_trials=4.65)
    assert used == "binomial" and basis is None
    assert len(pmf) == 6, len(pmf)
    assert abs(sum(pmf) - 1.0) < 1e-12
    ppois = bm._poisson_pmf(1.6, 40)
    assert abs(sum(ppois[6:]) - 0.006040) < 1e-5, sum(ppois[6:])


def test_the_fractional_trial_mixture_preserves_the_mean():
    """Expected PA are fractional and a binomial needs an integer n. Rounding
    would put a 1.35 point step in the middle of the lineup card (at lam 1.2,
    Binomial(4, 0.30) reads 0.75990 for 1+ against Binomial(5, 0.24)'s
    0.74645). The mixture over the two adjacent trial counts is continuous and
    keeps the mean at exactly lam."""
    for lam, trials in ((1.6, 4.65), (1.2, 4.2), (0.22, 3.85)):
        pmf, used, _ = be._props_pmf(lam, dist="binomial", n_trials=trials)
        mean = sum(k * v for k, v in enumerate(pmf))
        assert used == "binomial"
        assert abs(sum(pmf) - 1.0) < 1e-12, (lam, trials)
        assert abs(mean - lam) < 1e-12, (lam, trials, mean)
    mix = 1.0 - be._props_pmf(1.2, dist="binomial", n_trials=4.65)[0][0]
    assert abs(mix - 0.74781) < 5e-6, mix
    lo = 1.0 - be._binomial_pmf(4, 0.30)[0]
    hi = 1.0 - be._binomial_pmf(5, 0.24)[0]
    assert abs(lo - 0.75990) < 5e-6 and abs(hi - 0.74645) < 5e-6
    assert hi < mix < lo


def test_an_integer_trial_count_is_a_plain_binomial():
    pmf, used, _ = be._props_pmf(2.0, dist="binomial", n_trials=4.0)
    assert used == "binomial" and len(pmf) == 5
    exact = be._binomial_pmf(4, 0.5)
    assert all(abs(a - b) < 1e-12 for a, b in zip(pmf, exact))


def test_the_measured_gap_the_repair_removed():
    """The number on the record. Slot-1 hitter, exp_pa 4.65, lam 1.60: the old
    fair-line Bernoulli read 0.85929, the old value-block Poisson read 0.79810,
    and the one binomial path reads 0.85630. If any of these three move, the
    claim in the module header is stale and must be re-measured."""
    exp_pa, lam = be.SLOT_PA[1], 1.6
    p = lam / exp_pa
    old_fair = 1.0 - (1.0 - p) ** exp_pa
    old_val = be._props_side_probabilities(lam, 0.5)["p_over"]
    new = be._props_side_probabilities(lam, 0.5, dist="binomial",
                                       n_trials=exp_pa)["p_over"]
    assert abs(old_fair - 0.85929) < 5e-6, old_fair
    assert abs(old_val - 0.79810) < 5e-6, old_val
    assert abs(new - 0.85630) < 5e-6, new
    assert abs((old_fair - old_val) - 0.06118) < 5e-6


def test_a_non_positive_lambda_publishes_no_probability():
    assert be._props_side_probabilities(0.0, 0.5) is None
    assert be._props_side_probabilities(1.0, -1.0) is None
    row = be._prop_row("1+ hits", 0.0, over_line=0.5, n_trials=4.2)
    assert row["p_over"] is None and row["pmf"] is None
    assert "not positive" in row["pmf_basis"]


def test_probabilities_stay_inside_zero_and_one():
    for dist, trials in (("poisson", None), ("binomial", 4.65)):
        for line in (0.5, 1.5, 2.5, 4.5, 9.5):
            ps = be._props_side_probabilities(1.6, line, dist=dist,
                                              n_trials=trials)
            assert 0.0 <= ps["p_over"] <= 1.0, (dist, line)
            assert 0.0 <= ps["p_under"] <= 1.0, (dist, line)


# ===========================================================================
# 5. THE DE-VIG DISCIPLINE IS UNTOUCHED
# ===========================================================================
def test_the_market_view_discipline_is_still_the_team_board_s():
    """The lane changed the MODEL side only. The book side must still be
    `_market_view`: consensus line by book count, prices restricted to books
    on that line, min-hold fair book, rejections counted."""
    pv = _value()
    for r in pv["rows"]:
        assert r["fair_book"] is not None, r
        assert r["n_books_on_line"] is not None, r
        assert "hold_pct" in r
    assert "verbatim" in pv["method"]["market_view"]
    assert pv["floor"]["min_edge"] is not None


# ===========================================================================
# runner (the no-pytest rule: python test_betting_props_pmf.py runs everything)
# ===========================================================================
def main() -> int:
    import traceback
    fns = [(k, v) for k, v in sorted(globals().items())
           if k.startswith("test_") and callable(v)]
    failed = 0
    for name, fn in fns:
        try:
            fn()
            print(f"PASS {name}")
        except Exception:
            failed += 1
            print(f"FAIL {name}")
            traceback.print_exc()
    print(f"{len(fns) - failed} passed, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
