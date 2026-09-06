"""M-MWAR-4: the In-Game Management gate battery, and the team attribution under it.

WHY THE BATTERY EXISTS. `management.py` prices 13,971 stolen-base decisions. Pricing them
correctly is not the same as those prices meaning anything about the person who made them. A
decision metric that cannot survive a split-half is measuring the schedule, and it would reach
a reader as a manager leaderboard.

THE DEFECT THESE TESTS WERE WRITTEN AGAINST, and it nearly shipped. A first reading of this
gate reported that summed decision value CLEARED its null. It did not. Two things were wrong at
once:

  1. The null reassigned attempt counts across agents, which destroys the structure under test
     and produces a band almost anything clears.
  2. The series was RAW decision value, which correlates at +0.78 across split halves while
     season alone explains 0.7961 of its variance and team identity explains 0.0223. Both
     halves of a team-season sit in the same season, so a league-wide year effect reads as
     agreement about the agent.

Season-controlled, against an opportunity-preserving null, the correlation is +0.0691 inside a
band of [-0.148, +0.120]. The family is a null, and the null is bounded rather than merely
absent, because the battery also reports the smallest effect it could have seen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import mgmt_teams          # noqa: E402

ART = ROOT / "data" / "management_gate_eval.json"
GATE_DOC = ROOT / "docs" / "IN_GAME_MANAGEMENT_GATE.md"


@pytest.fixture(scope="module")
def art():
    if not ART.exists():
        pytest.skip("the gate battery has not been run")
    return json.loads(ART.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# The gate document must predate the numbers
# --------------------------------------------------------------------------

def test_the_gate_document_exists_and_is_frozen():
    import mgmt_gate
    assert GATE_DOC.exists()
    assert mgmt_gate.frozen_at()


def test_the_battery_refuses_to_run_without_a_frozen_document(tmp_path, monkeypatch):
    """A battery whose policies were chosen after the numbers were seen is not a
    battery. The refusal is the only thing enforcing that ordering."""
    import mgmt_gate
    monkeypatch.setattr(mgmt_gate, "GATE_DOC", tmp_path / "absent.md")
    with pytest.raises(FileNotFoundError, match="frozen"):
        mgmt_gate.frozen_at()
    p = tmp_path / "nostamp.md"
    p.write_text("# no freeze stamp here\n", encoding="utf-8")
    monkeypatch.setattr(mgmt_gate, "GATE_DOC", p)
    with pytest.raises(ValueError, match="Frozen"):
        mgmt_gate.frozen_at()


def test_the_document_names_all_three_heuristic_policies():
    """The captured share can change sign between policies, so naming only the
    one that was used would let a friendlier one be swapped in later."""
    txt = GATE_DOC.read_text(encoding="utf-8").lower()
    # The ARTIFACT'S OWN KEYS, not prose names. A policy described in words in
    # one place and keyed in another is how a number ends up attached to the
    # wrong policy string.
    for key in ("random_among_qualifying", "random_among_all", "margin_5pct"):
        assert key in txt, f"the gate document does not name the policy key {key!r}"
    if ART.exists():
        import json as _j
        keys = set((_j.loads(ART.read_text(encoding="utf-8"))
                    ["gate_4_captured_share"]["policies"]))
        assert keys == {"random_among_qualifying", "random_among_all", "margin_5pct"}, (
            f"the artifact publishes policies {sorted(keys)} which the gate "
            "document does not name")


def test_the_document_records_the_series_decision_and_its_reason():
    txt = GATE_DOC.read_text(encoding="utf-8")
    assert "0.7961" in txt and "0.0223" in txt, (
        "the gate document does not carry the variance decomposition that "
        "justifies publishing the season-controlled series")
    assert "season-controlled one" in txt.lower()


def test_the_document_admits_the_target_mix_guess_was_wrong():
    """A prior design note attributed the raw correlation to target mix. It is
    season. Recording a corrected guess is how the next reader avoids it."""
    txt = GATE_DOC.read_text(encoding="utf-8").lower()
    assert "target mix" in txt and "wrong" in txt


# --------------------------------------------------------------------------
# Team attribution
# --------------------------------------------------------------------------

def test_team_attribution_matches_ground_truth():
    """Derived from war_daily plate appearances, checked against real
    home_org / away_org. Anything below the floor is refused rather than
    returned partial, because a partial map drops agent-seasons in a way
    correlated with roster churn."""
    m = mgmt_teams.build_map()
    v = mgmt_teams.validate_against_ground_truth(m)
    assert v["checked"] > 2000
    assert v["agreement"] >= mgmt_teams.MIN_GROUND_TRUTH_AGREEMENT, v["misses"][:5]


def test_every_season_has_thirty_clubs_at_a_plausible_game_count():
    """The internal check that carries the seven seasons ground truth cannot
    reach. Thirty clubs at about 162 games each is the shape; anything else
    means the vote is resolving to the wrong entity."""
    m = mgmt_teams.build_map()
    for season, s in mgmt_teams.season_shape(m).items():
        assert s["clubs"] == 30, f"{season}: {s['clubs']} clubs"
        lo = 130 if season == "2026" else 155
        assert lo <= s["games_min"] and s["games_max"] <= 168, f"{season}: {s}"


def test_a_game_never_attributes_both_halves_to_one_club():
    m = mgmt_teams.build_map()
    bad = [k for k, v in m.items() if v["home"] == v["away"]]
    assert not bad, f"{len(bad)} games attribute both halves to one club"


def test_the_map_is_refused_rather_than_returned_partial():
    src = (ROOT / "mgmt_teams.py").read_text(encoding="utf-8")
    assert "MIN_RESOLVED_SHARE" in src and "raise ValueError" in src


# --------------------------------------------------------------------------
# The published series
# --------------------------------------------------------------------------

def test_the_published_series_is_season_controlled(art):
    g = art["gate_1_split_half"]["published"]
    assert g["column"] == "dv_resid"
    assert "PUBLISHED" in g["series"]


def test_the_raw_series_is_published_beside_it_and_labelled(art):
    raw = art["gate_1_split_half"]["raw_for_comparison"]
    assert raw["column"] == "dv"
    assert "NOT the agent" in raw["series"]
    assert raw["pearson_mean_dv"] > 0.5, (
        "the raw series no longer shows the large correlation the published "
        "series exists to explain away; if that changed, the decomposition and "
        "the gate document's reasoning both need re-reading")


def test_season_dominates_team_in_the_variance_decomposition(art):
    d = art["why_the_published_series_is_season_controlled"]
    s = d["variance_of_agent_summed_dv_explained_by_season"]
    t = d["variance_of_agent_summed_dv_explained_by_team"]
    assert s > 5 * t, (
        f"season explains {s:.4f} and team {t:.4f}; the whole reason the raw "
        "series is refused is that season dominates, and if it stopped "
        "dominating the published series should be reconsidered")


# --------------------------------------------------------------------------
# The null must be the right null
# --------------------------------------------------------------------------

def test_the_null_preserves_attempt_counts(art):
    """THE DEFECT THAT PRODUCED A FALSE PASS. A null that reassigns attempt
    counts across agents destroys the structure under test."""
    c = art["gate_1_split_half"]["null"]["construction"].lower()
    assert "within season" in c
    assert "attempt count" in c and "fixed" in c


def test_the_null_band_is_wide_enough_to_be_a_real_bar(art):
    n = art["gate_1_split_half"]["null"]
    assert n["n_perm"] >= 300
    assert n["hi95"] > 0.03, (
        f"the null band's upper edge is only {n['hi95']}; a band that narrow "
        "on 240 agent-seasons suggests the permutation is not destroying the "
        "structure it is meant to destroy")


def test_the_verdict_agrees_with_the_number(art):
    g = art["gate_1_split_half"]["published"]
    n = art["gate_1_split_half"]["null"]
    assert g["clears_null"] is (g["pearson_mean_dv"] > n["hi95"])
    v = art["verdict"]
    if g["clears_null"]:
        assert v.startswith("CLEARS")
    else:
        assert v.startswith("DESCRIPTIVE ONLY")
        assert "WITHHELD" in v


# --------------------------------------------------------------------------
# The null must be BOUNDED, not merely absent
# --------------------------------------------------------------------------

def test_the_battery_reports_what_it_could_have_seen(art):
    """A null with no detection floor is unbounded and says nothing."""
    f = art["detection_floor"]
    assert f["smallest_detectable_per_attempt_sd"] is not None, (
        "the power sweep never reached 80 percent, so the null is unbounded "
        "and no ceiling may be quoted from it")
    assert any(d["power"] >= 0.8 for d in f["grid"])


def test_the_implied_spread_is_published_in_wins(art):
    h = art["headline"]
    sd = h["implied_true_between_agent_sd_of_summed_dv_wins"]
    assert sd is not None and sd >= 0
    assert sd < 0.5, (
        f"the implied true between-agent spread is {sd} wins, which is large "
        "enough that the null reading needs revisiting")


# --------------------------------------------------------------------------
# Captured share
# --------------------------------------------------------------------------

def test_all_three_policies_are_published(art):
    p = art["gate_4_captured_share"]["policies"]
    assert set(p) == {"random_among_qualifying", "random_among_all", "margin_5pct"}
    for name, v in p.items():
        assert v["policy"], f"{name} carries no policy string"
        assert v["captured_share"] is not None


def test_the_share_uses_the_budget_matched_optimum(art):
    """The unlimited optimum attempts on roughly eight times the real volume.
    Dividing a budget-matched numerator by it compares two different games."""
    g = art["gate_4_captured_share"]
    assert g["optimal_dv_wins_budget_matched"] < g["optimal_dv_wins_unlimited"]
    assert "budget-matched" in g["which_optimum_the_share_uses"].lower()
    n, opp = g["n_attempts_actual"], g["n_opportunities"]
    assert 0.02 < n / opp < 0.15, (
        f"the attempt rate is {n/opp:.4f}; the budget matching is built on it")


def test_the_share_is_read_as_a_bound_not_a_verdict_on_managers(art):
    r = art["gate_4_captured_share"]["reading"].lower()
    assert "fantasy baseline" in r or "bound on available value" in r
    assert "matchup" in r, (
        "the reading does not concede that the heuristic sees p* exactly while "
        "a real manager has matchup information the model cannot see; without "
        "that, a negative share reads as a criticism it cannot support")


def test_the_policies_agree_on_the_sign(art):
    """They need not, and the gate document says so. If they ever disagree the
    headline cannot be stated without its policy and this test should be
    replaced by one that asserts the disagreement is disclosed."""
    shares = [v["captured_share"] for v in art["gate_4_captured_share"]["policies"].values()]
    signs = {s > 0 for s in shares}
    assert len(signs) == 1, (
        f"the captured share changes sign across policies: {shares}. That is "
        "permitted and must then be the headline disclosure, not a footnote.")


# --------------------------------------------------------------------------
# What the null decides
# --------------------------------------------------------------------------

def test_the_artifact_says_what_a_null_decides_about_the_manager_entity(art):
    n = art["what_a_null_decides_about_the_manager_entity"].lower()
    assert "upper bound" in n
    assert "bullpen" in n, (
        "the artifact does not scope its own null; a null on the stolen base "
        "says nothing about families with more room, and omitting that invites "
        "the reading that managers do not matter")


def test_persistence_is_labelled_a_team_proxy(art):
    p = art["gate_2_persistence"]
    assert "upper bound" in p["is_a_team_proxy_and_an_upper_bound"].lower()


def test_the_placebo_publishes_its_own_degeneracy(art):
    g = art["gate_3_placebo"]
    assert g["median_cell_size"] >= 1
    assert "identity" in g["degeneracy_warning"].lower(), (
        "the placebo does not warn that a thin cell cannot be shuffled, so its "
        "band would be taken at face value")


def test_the_artifact_is_dated_and_names_its_gate_document(art):
    assert art.get("generated_at")
    assert art.get("gate_doc_frozen_at")
    assert art["gate_doc"].endswith("IN_GAME_MANAGEMENT_GATE.md")
