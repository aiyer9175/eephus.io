"""Guards for the two accountability surfaces built on data/model_registry.json.

Part 1, Model Report Cards v0. The card blocks put proof numbers on the
Models & Proofs view, so the load-bearing risk is a card number drifting from
its eval artifact. These tests are the anti-drift fence: every card names the
artifact path of each number it prints (card.derived_from) and equals that
path's value exactly, the card schema must validate, and the number must
survive refresh_stamps().

Part 2, the /models/ accountability hub (build_site.build_models). The risk
there is different and worse: the page's whole claim is that its verdicts are
read rather than written and that its receipts resolve. A link to an artifact
the deploy does not ship is a 404 on a page about honesty, and a verdict string
the page invented would be the exact failure the ledger exists to prevent. Both
are pinned here against the registry, the artifacts and the deploy manifests.

build_models() only reads, so these tests dirty nothing.
"""
import functools
import json
import re
from pathlib import Path

import model_registry as mr

HERE = Path(__file__).parent


def _cards():
    reg = mr.load()
    return [m for m in reg["models"] if m.get("card")]


def test_at_least_the_flagship_cards_exist():
    ids = {m["model_id"] for m in _cards()}
    assert {"fa_projection_marcel", "eta", "consensus_fv", "sem_plus"} <= ids


def test_registry_validates_with_cards():
    assert mr.validate() == []


def test_every_card_is_derived():
    """Census X01-04 (2026-09-25). The old fence accepted a typed number within
    max(0.02, 2 percent) of ANY leaf of the artifact: the FA card's 0.63 matched
    13 leaves (among them the artifact's own baseline 0.6242) and the ETA card's
    0.585 matched a DSL survival point. A card now names the path of every
    number it prints, and test_derived_cards_equal_their_artifact_exactly holds
    it to that path exactly."""
    literal = [m["model_id"] for m in _cards() if not m["card"].get("derived_from")]
    assert not literal, (
        f"cards with typed numbers: {literal}; give each a card.derived_from spec")


def test_eta_card_scores_both_arms_on_the_same_rows():
    """The ETA card compared the champion on every debuted row (n 4,159) with
    the naive table on the subset it covers (3,508 today). It reads the
    champion_on_baseline_rows block now, whose n equals the baseline's."""
    row = next(m for m in _cards() if m["model_id"] == "eta")
    spec = row["card"]["derived_from"]
    assert spec["n"] == "champion_on_baseline_rows.n"
    for hs in spec["headline"]:
        assert hs["champion"].startswith("champion_on_baseline_rows.")
        assert hs["baseline"].startswith("baseline_naive_level_table.")
    art = json.loads((HERE / "data" / "eta_eval.json").read_text(encoding="utf-8"))
    assert art["champion_on_baseline_rows"]["n"] == art["baseline_naive_level_table"]["n"]
    assert row["card"]["n"] == art["baseline_naive_level_table"]["n"]


def test_refresh_stamps_preserves_card(tmp_path, monkeypatch):
    """refresh_stamps() rewrites the registry monthly; the card field must
    round-trip. A literal card comes back unchanged. A derived card comes back
    as its artifact reading with its spec intact (and
    test_derived_cards_equal_their_artifact_exactly holds that reading equal
    to the committed card). Run it against a temp copy so the committed file
    is untouched."""
    reg = mr.load()
    before = {m["model_id"]: m for m in reg["models"] if m.get("card")}
    want = {mid: (mr.derive_card(m) if m["card"].get("derived_from") else m["card"])
            for mid, m in before.items()}
    tmp = tmp_path / "reg.json"
    tmp.write_text(json.dumps(reg, ensure_ascii=False, indent=1), encoding="utf-8")
    monkeypatch.setattr(mr, "REGISTRY_PATH", tmp)
    mr.refresh_stamps()
    after = json.loads(tmp.read_text(encoding="utf-8"))
    got = {m["model_id"]: m.get("card") for m in after["models"]}
    for mid, card in want.items():
        assert got.get(mid) == card, f"{mid} card lost or altered by refresh_stamps"


# --------------------------------------------------------------------------- #
# Derived cards (audit L18-01, 2026-09-11)
# --------------------------------------------------------------------------- #
# consensus_fv served a weighted-vs-equal pair its own notes said had been
# removed, with a star on a Spearman lead its own artifact calls not
# resolvable, and every test above stayed green: the tolerance trace accepts a
# number within max(0.02, 2 percent) of ANY leaf of a file with thousands of
# leaves. A card over an artifact the pipeline regenerates now names the path
# of each number (card.derived_from) and refresh_stamps() re-reads it.
#
# Artifacts run_monthly regenerates on every run, whose cards therefore cannot
# hold typed numbers. The ETA card quotes the row-matched champion block
# (champion_on_baseline_rows), not champion_heuristic, so both arms are scored
# on the same rows.
REGENERATED_CARD_ARTIFACTS = {"data/source_backtest.json", "data/eta_eval.json"}


def _derived_cards():
    return [m for m in _cards() if m["card"].get("derived_from")]


def _champ_beats(h) -> bool:
    return (h["champion"] < h["baseline"] if h["better"] == "lower"
            else h["champion"] > h["baseline"])


def test_derived_cards_equal_their_artifact_exactly():
    """Provenance, not proximity: a derived card is held to the value at the
    path it names, exactly. A failure means the artifact was regenerated and
    refresh_stamps() has not run since (`python model_registry.py`)."""
    cards = _derived_cards()
    assert cards, "no derived cards; consensus_fv's card must be derived"
    problems = []
    for m in cards:
        reading = mr.derive_card(m)
        if reading != m["card"]:
            problems.append(f"{m['model_id']}: committed card {m['card']} "
                            f"!= artifact reading {reading}")
    assert not problems, "\n".join(problems)


def test_cards_on_regenerated_artifacts_are_derived():
    literal = [m["model_id"] for m in _cards()
               if m["eval_artifact"] in REGENERATED_CARD_ARTIFACTS
               and not m["card"].get("derived_from")]
    assert not literal, (
        f"typed card numbers over an artifact run_monthly regenerates: {literal}. "
        "They go stale on the next run; give the card a derived_from spec.")


def test_consensus_fv_card_carries_only_the_leg_its_artifact_resolves():
    """The row's own reading: blending buys discrimination, not ordering. The
    ordering (Spearman) leg of accuracy.consensus_vs_inputs is not resolvable
    at this power, so this row's card is the AUC leg alone, read from that
    block, with n read from the common set it was measured on."""
    row = next(m for m in mr.load()["models"] if m["model_id"] == "consensus_fv")
    card = row["card"]
    spec = card.get("derived_from")
    assert spec, "consensus_fv's card is typed again; it must be derived"
    assert spec.get("n") == "accuracy.common_n"
    paths = [p for hs in spec["headline"] for p in hs.values()]
    assert paths and all(p.startswith("accuracy.consensus_vs_inputs.auc.")
                         for p in paths), paths
    assert not any("spearman" in h["label"].lower() for h in card["headline"]), (
        "a Spearman headline is back on consensus_fv; the row does not claim to "
        "order realized WAR better than its best input")


def test_fa_projection_marcel_card_reads_gate1_pooled_war():
    """The literal 0.63 vs 0.73 card outlived two Gate 1 re-measures (0.574 on
    2026-08-03, 0.5157 on 2026-09-23). It is read from pooled.war now, rounded
    to three places for display, with the star gated on the artifact's own WAR
    gate."""
    row = next(m for m in mr.load()["models"] if m["model_id"] == "fa_projection_marcel")
    spec = row["card"].get("derived_from")
    assert spec, "fa_projection_marcel's card is typed again; it must be derived"
    assert spec["headline"] == [{"champion": "pooled.war.mae_model",
                                 "baseline": "pooled.war.mae_base",
                                 "resolvable": "gates.war"}]
    art = json.loads((HERE / "data" / "fa_gate1_eval.json").read_text(encoding="utf-8"))
    h = row["card"]["headline"][0]
    assert h["champion"] == round(art["pooled"]["war"]["mae_model"], spec["digits"])
    assert h["baseline"] == round(art["pooled"]["war"]["mae_base"], spec["digits"])
    assert row["card"]["n"] == art["pooled"]["war"]["n"]


def test_derived_card_digits_must_be_a_small_integer():
    import pytest
    art = {"a": 0.123456, "b": 0.2}
    card = {"headline": [{"label": "x", "champion": 0, "baseline": 0, "better": "lower"}],
            "derived_from": {"headline": [{"champion": "a", "baseline": "b"}]}}
    got = mr.derive_card({"card": dict(card, derived_from=dict(card["derived_from"], digits=2))}, art)
    assert got["headline"][0]["champion"] == 0.12
    assert mr.derive_card({"card": card}, art)["headline"][0]["champion"] == 0.123456
    for bad in (True, -1, 7, 2.0, "3"):
        with pytest.raises(ValueError):
            mr.derive_card({"card": dict(card, derived_from=dict(card["derived_from"], digits=bad))}, art)


def test_a_validated_derived_card_shows_a_resolved_win():
    """`validated` means the champion beats its stated baseline. When a
    derived card is the proof, at least one headline must be a strict win on a
    leg the artifact resolves. If a regeneration moves every leg inside its
    floor the verdict needs an owner look, and this is where that surfaces.
    An artifact that states no resolvability for any leg (eta_eval.json and
    draft_slot_curve.json carry no interval) cannot resolve one, so such a card
    needs a strict win on the plain comparison, as a typed card did. A
    `contest: false` card is a descriptive contrast, not the registered
    benchmark, so it is no proof either way and is not held to this."""
    problems = []
    for m in _derived_cards():
        if m["verdict"] != "validated" or m["card"].get("contest") is False:
            continue
        declares = any("resolvable" in hs
                       for hs in m["card"]["derived_from"]["headline"])
        if not any(_champ_beats(h) and (h.get("resolvable") is True or not declares)
                   for h in m["card"]["headline"]):
            problems.append(f"{m['model_id']}: validated, but its derived card "
                            "shows no resolved win")
    assert not problems, "\n".join(problems)


def _card_js():
    """assets/glossary.js::_cardHeadline, run in a real JS engine. The function
    is pure (card in, markup out) and needs only escapeHtml beside it."""
    import pytest
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    js = (HERE / "assets" / "glossary.js").read_text(encoding="utf-8").replace("\r\n", "\n")
    i = js.index("function _cardHeadline(card) {")
    j = js.index("\n}\n", i) + 2
    ctx = MiniRacer()
    ctx.eval('function escapeHtml(s) { return String(s == null ? "" : s)'
             '.replace(/&/g, "&amp;").replace(/</g, "&lt;")'
             '.replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }')
    ctx.eval(js[i:j])
    return ctx


def _render(ctx, card) -> str:
    return ctx.eval(f"_cardHeadline({json.dumps(card)})")


STAR = "★"


def test_the_card_star_needs_a_strict_resolved_win():
    ctx = _card_js()
    base = {"label": "x", "champion": 0.75, "baseline": 0.70, "better": "higher"}
    literal = _render(ctx, {"headline": [base]})
    assert literal.count(STAR) == 1, "a literal card lost its star"
    unresolved = _render(ctx, {"headline": [dict(
        base, resolvable=False, verdict="not resolvable at this power")]})
    assert unresolved.count(STAR) == 0, (
        "the star went to a lead its artifact calls not resolvable")
    assert "not resolvable at this power" in unresolved, (
        "the artifact's verdict is not shown beside an unresolved bar pair")
    resolved = _render(ctx, {"headline": [dict(base, resolvable=True,
                                               verdict="the blend wins")]})
    assert resolved.count(STAR) == 1 and "the blend wins" in resolved
    tie = _render(ctx, {"headline": [dict(base, champion=0.70)]})
    assert tie.count(STAR) == 0, "a tie was starred as a win"
    lower = _render(ctx, {"headline": [dict(base, better="lower", champion=0.60)]})
    assert lower.count(STAR) == 1


def test_no_served_card_stars_a_leg_its_artifact_does_not_resolve():
    """Over the live registry: render each headline alone and count stars. A
    star appears exactly where the champion strictly wins and the artifact has
    not marked the leg unresolvable."""
    ctx = _card_js()
    problems = []
    for m in _cards():
        for h in m["card"]["headline"]:
            got = _render(ctx, {"headline": [h]}).count(STAR)
            want = int(_champ_beats(h) and h.get("resolvable") is not False)
            if got != want:
                problems.append(f"{m['model_id']} {h['label']!r}: {got} stars, "
                                f"expected {want}")
    assert not problems, "\n".join(problems)


# --------------------------------------------------------------------------- #
# Census X01-03 (2026-09-25): the card's baseline is named, and a +index card
# shows its gated parent beside the naive stat
# --------------------------------------------------------------------------- #
# HEM+ printed 0.412 against AVG 0.235 with a star while its own artifact holds
# raw wOBA at 0.4087 (gap lo95 -0.0096, a tie); DEM+ printed fielding
# percentage 0.0111 beside a raw rate of 0.4531; SEM+ and REM+ printed ERA beside
# raw FIP. The bar carried no name, so the reader could not tell which
# comparator it was. Each of these four rows was gated on two legs, beat the
# naive stat AND stay non-inferior to the parent, so the card now shows both,
# with the parent leg's resolvability read off the artifact's own gap lo95.
# The parent is the one the gate names (raw wOBA for HEM+, not OPS): the HEM
# re-gate document forbids adding a post-hoc baseline to a settled row.
PARENT_LEGS = {
    "hem_plus": ("forward_spearman_vs_wOBA_next.avg",
                 "forward_spearman_vs_wOBA_next.raw_woba", "gap_ci_vs_raw_woba.lo95"),
    "sem_plus": ("forward_spearman_vs_RA9_next.era",
                 "forward_spearman_vs_RA9_next.raw_fip", "gap_ci_vs_raw_fip.lo95"),
    "rem_plus": ("forward_spearman_vs_RA9_next.era",
                 "forward_spearman_vs_RA9_next.raw_fip",
                 "gap_ci_vs_RA9_next.vs_raw_fip.lo95"),
    "dem_plus": ("forward_spearman_vs_rate_next.fld_pct",
                 "forward_spearman_vs_rate_next.raw_rate", "gap_ci_vs_raw_rate.lo95"),
}


def test_every_card_names_its_baseline():
    """A bar pair whose baseline has no name cannot be read; with two legs on
    one card it cannot even be told apart."""
    missing = [f"{m['model_id']} {h['label']!r}" for m in _cards()
               for h in m["card"]["headline"]
               if not (isinstance(h.get("baseline_label"), str)
                       and h["baseline_label"].strip())]
    assert not missing, "card legs with no baseline_label: " + "; ".join(missing)


def test_plus_index_cards_carry_the_naive_and_the_parent_leg():
    rows = {m["model_id"]: m for m in _cards()}
    for mid, (naive, parent, lo95) in PARENT_LEGS.items():
        spec = rows[mid]["card"].get("derived_from")
        assert spec, f"{mid}: card is typed; it must read its artifact"
        baselines = [hs.get("baseline") for hs in spec["headline"]]
        assert naive in baselines, f"{mid}: the gated naive leg is gone"
        assert parent in baselines, (
            f"{mid}: the card bars the model against the naive stat only, while "
            f"its artifact holds the parent it must not lose to ({parent})")
        hs = spec["headline"][baselines.index(parent)]
        assert hs.get("resolvable") == {"above_zero": lo95}, (
            f"{mid}: the parent leg's resolvability must be read off {lo95}")


def test_a_tie_with_the_parent_carries_no_star():
    """HEM+ and DEM+ are ties with their parents (lo95 below zero). The leg
    shows, unstarred, and says in words that it is not a win."""
    ctx = _card_js()
    rows = {m["model_id"]: m for m in _cards()}
    for mid in ("hem_plus", "dem_plus"):
        leg = next(h for h in rows[mid]["card"]["headline"]
                   if "parent" in h["baseline_label"])
        assert leg["resolvable"] is False
        html = _render(ctx, {"headline": [leg]})
        assert html.count(STAR) == 0
        assert "not a resolved win" in html
        assert "vs " + leg["baseline_label"] in html


def test_hem_card_shows_both_parents_each_read_from_its_artifact():
    """Owner answer M27-1 (2026-09-25): the HEM+ card shows raw wOBA (the
    parent its gate names, 0.412 vs 0.409) AND OPS (the strongest parent in
    the eval artifact, 0.412 vs 0.411), each labelled with what it is and
    each read from data/hem_plus_eval.json, never typed. Neither is a
    resolved win, so neither carries a star. The gate itself is unchanged:
    it names raw wOBA, and OPS is shown, not added to the bar."""
    ctx = _card_js()
    row = next(m for m in _cards() if m["model_id"] == "hem_plus")
    spec = row["card"]["derived_from"]["headline"]
    doc = json.loads((HERE / row["eval_artifact"]).read_text(encoding="utf-8"))
    want = {
        "forward_spearman_vs_wOBA_next.raw_woba": ("raw wOBA (the parent its gate names)",
                                                   "gap_ci_vs_raw_woba.lo95"),
        "forward_spearman_vs_wOBA_next.ops": ("OPS (the strongest parent in its eval)",
                                              "gap_ci_vs_ops.lo95"),
    }
    for base_path, (label, lo95) in want.items():
        i = next(k for k, hs in enumerate(spec) if hs.get("baseline") == base_path)
        assert spec[i]["champion"] == "forward_spearman_vs_wOBA_next.hem_plus"
        assert spec[i]["resolvable"] == {"above_zero": lo95}
        leg = row["card"]["headline"][i]
        assert leg["baseline_label"] == label
        assert leg["baseline"] == round(mr._dig_path(doc, base_path), 3)
        assert leg["champion"] == round(doc["forward_spearman_vs_wOBA_next"]["hem_plus"], 3)
        assert leg["resolvable"] is (mr._dig_path(doc, lo95) > 0)
        html = _render(ctx, {"headline": [leg]})
        assert "vs " + label in html
        if leg["resolvable"] is False:
            assert html.count(STAR) == 0 and "not a resolved win" in html
    # the gate's parent stays the one the gate names
    assert "raw wOBA" in doc["gate"]["bar"] and "OPS" not in doc["gate"]["bar"]


def test_fwdhem_card_does_not_star_its_unresolved_lead():
    """The xHEM+ Blend card starred 0.461 over xwOBA 0.454 while the re-gate
    arm it quotes reads D4 v1 lo95 -0.0012 and its own notes say not
    separable. It reads the arm's lo95_gt_0 and verdict now."""
    row = next(m for m in _cards() if m["model_id"] == "fwdhem_plus")
    h = row["card"]["headline"][0]
    assert row["card"]["derived_from"]["headline"][0]["resolvable"] == (
        "arms.A2_fwdhem_plus.ladder.D4.v1.lo95_gt_0")
    assert h["resolvable"] is False
    assert _render(_card_js(), {"headline": [h]}).count(STAR) == 0


def test_resolvable_can_be_read_from_a_gap_lower_bound():
    import pytest
    card = {"headline": [{"label": "x", "champion": 0, "baseline": 0, "better": "higher"}]}
    art = {"r": {"m": 0.41, "b": 0.40}, "ci": {"lo95": -0.001, "lo95b": 0.002}}
    spec = {"headline": [{"champion": "r.m", "baseline": "r.b",
                          "resolvable": {"above_zero": "ci.lo95"}}]}
    got = mr.derive_card({"card": dict(card, derived_from=spec)}, art)
    assert got["headline"][0]["resolvable"] is False
    spec["headline"][0]["resolvable"] = {"above_zero": "ci.lo95b"}
    got = mr.derive_card({"card": dict(card, derived_from=spec)}, art)
    assert got["headline"][0]["resolvable"] is True
    for bad in ({"above_zero": "r"}, {"below_zero": "ci.lo95"}):
        spec["headline"][0]["resolvable"] = bad
        with pytest.raises((ValueError, KeyError)):
            mr.derive_card({"card": dict(card, derived_from=spec)}, art)
    spec["headline"][0]["resolvable"] = "ci.lo95"
    spec["headline"][0]["champion"] = {"above_zero": "ci.lo95"}
    with pytest.raises(ValueError):
        mr.derive_card({"card": dict(card, derived_from=spec)}, art)


# --------------------------------------------------------------------------- #
# The edge fields (LIBRARY_10, 2026-10-03)
# --------------------------------------------------------------------------- #
# The Model Updates edge column prints an interval or a resolvable margin for
# every scored leg, and the card is the single source of a leg's numbers. So a
# card leg names the path of its improvement interval (gap_ci), its one-sided
# paired t and its detection floor (mde95) the same way it names its champion,
# carries a short literal `stat`, and a descriptive contrast says so with
# `contest: false`. These pin that every such number is read, never typed, and
# that the star still follows the evidence.
NEW_CARDS = {
    "betting_game_prob": [
        ("vintage.brier", "vintage.brier_home_base", "vintage.n",
         {"t": "vintage.skill_vs_home_base.t"}),
        ("benchmarks.tiers.market_open_devig.same_games.model",
         "benchmarks.tiers.market_open_devig.brier",
         "benchmarks.tiers.market_open_devig.n", {}),
    ],
    "arb_award": [
        ("results.arb1.mdape_champion", "results.arb1.mdape_bar", "results.arb1.n_paired",
         {"mde95": "results.arb1.mde95_onesided"}),
        ("results.arb2plus.mdape_champion", "results.arb2plus.mdape_bar",
         "results.arb2plus.n_paired", {"mde95": "results.arb2plus.mde95_onesided"}),
        ("a6_swartz.ours_mdape", "a6_swartz.swartz_mdape", "a6_swartz.n", {}),
    ],
    "ewar": [
        ("gate_1_team_wins.ewar.r", "gate_1_team_wins.bwar.r",
         "gate_1_team_wins.n_team_seasons", {}),
        ("gate_2_pitcher_persistence.self_r_ewar_fip",
         "gate_2_pitcher_persistence.self_r_bwar_ra",
         "gate_2_pitcher_persistence.n_pairs", {}),
    ],
    "team_win_projections": [
        ("retro_backtest.ship_decision.holdout_mae.served_recentered",
         "retro_backtest.ship_decision.holdout_mae.baseline_prior_wins", None, {}),
    ],
}


def _artifact(m):
    return json.loads((HERE / m["eval_artifact"]).read_text(encoding="utf-8"))


def test_every_edge_path_resolves_to_a_number_in_the_rows_own_artifact():
    problems = []
    for m in _derived_cards():
        doc = _artifact(m)
        for hs in m["card"]["derived_from"]["headline"]:
            paths = [hs[k] for k in ("t", "mde95") if k in hs]
            if "gap_ci" in hs:
                paths += [hs["gap_ci"]["lo"], hs["gap_ci"]["hi"]]
            for p in paths:
                v = mr._dig_path(doc, p)
                if not mr._typed(v, "number"):
                    problems.append(f"{m['model_id']}: {p} is {v!r}, not a number")
            if "gap_ci" in hs:
                lo = mr._dig_path(doc, hs["gap_ci"]["lo"])
                hi = mr._dig_path(doc, hs["gap_ci"]["hi"])
                if lo > hi:
                    problems.append(f"{m['model_id']}: gap lo {lo} above hi {hi}")
    assert not problems, "\n".join(problems)


def test_every_card_leg_carries_a_short_stat():
    """The edge column prints `Result (<stat>): ...`; a leg with no stat would
    fall back to the registry `metric` prose, four of which carry a banned
    word."""
    missing = [f"{m['model_id']} {h['label']!r}" for m in _cards()
               for h in m["card"]["headline"]
               if not (isinstance(h.get("stat"), str) and h["stat"].strip()
                       and len(h["stat"]) <= mr.CARD_STAT_MAX)]
    assert not missing, "card legs with no short stat: " + "; ".join(missing)


def test_the_interval_paths_of_the_plan_are_wired():
    rows = {m["model_id"]: m for m in _cards()}
    want = {
        "hem_plus": ["gap_ci_vs_avg.lo95", "gap_ci_vs_raw_woba.lo95", "gap_ci_vs_ops.lo95"],
        "hem_plus_3yr": ["gap_ci_3yr_minus_1yr.lo95"],
        "rem_plus": ["gap_ci_vs_RA9_next.vs_era.lo95", "gap_ci_vs_RA9_next.vs_raw_fip.lo95"],
        "sem_plus": ["gap_ci_vs_era.lo95", "gap_ci_vs_raw_fip.lo95"],
        "dem_plus": ["gap_ci_vs_fld_pct.lo95", "gap_ci_vs_raw_rate.lo95"],
        "xhem_plus": ["arms.A1_xhem_plus.ladder.D4.v1.gap_ci.lo95"],
        "fwdhem_plus": ["arms.A2_fwdhem_plus.ladder.D4.v1.gap_ci.lo95"],
        "eta_fg_blend": ["fg_blend_gate_2026_09_25.clauses.B.boot_vs_CH40.ci_dMAE.0",
                         "fg_blend_gate_2026_09_25.clauses.B.boot_vs_CH40.ci_dW1.0"],
        "spotlights_movement": [f"v2.by_flag_type.{f}.horizons.h30.gap_lo95"
                                for f in ("riser", "rebound", "faller")],
    }
    for mid, los in want.items():
        got = [hs["gap_ci"]["lo"] for hs in rows[mid]["card"]["derived_from"]["headline"]]
        assert got == los, f"{mid}: gap_ci lo paths {got}"
    for mid, legs in (("consensus_fv", ["auc"]), ("source_track_record", ["spearman", "auc"])):
        got = [hs["mde95"] for hs in rows[mid]["card"]["derived_from"]["headline"]]
        assert got == [f"accuracy.consensus_vs_inputs.{lg}.mde95" for lg in legs], mid
    assert [h["stat"] for h in rows["spotlights_movement"]["card"]["headline"]] == [
        "riser hit rate", "rebound hit rate", "faller hit rate"]


def test_a_leg_whose_interval_covers_zero_carries_no_star():
    ctx = _card_js()
    checked = 0
    for m in _cards():
        for h in m["card"]["headline"]:
            gap = h.get("gap_ci")
            if gap is None:
                continue
            assert gap["lo"] <= gap["hi"], f"{m['model_id']}: {gap}"
            if gap["lo"] <= 0:
                checked += 1
                assert h.get("resolvable") is False, (m["model_id"], h["label"])
                assert _render(ctx, {"headline": [h]}).count(STAR) == 0, (
                    f"{m['model_id']} {h['label']!r}: a star on an interval that "
                    "reaches zero")
    assert checked >= 6, "the covered-interval legs (HEM+ x2, DEM+, fwdHEM+, spotlights) went missing"


def test_a_covered_interval_demotes_even_without_an_artifact_flag():
    card = {"headline": [{"label": "x", "champion": 0.42, "baseline": 0.40,
                          "better": "higher"}],
            "derived_from": {"headline": [{"champion": "m", "baseline": "b",
                                           "gap_ci": {"lo": "g.0", "hi": "g.1"}}]}}
    covered = mr.derive_card({"card": card}, {"m": 0.42, "b": 0.40, "g": [-0.01, 0.05]})
    assert covered["headline"][0]["resolvable"] is False
    assert covered["headline"][0]["gap_ci"] == {"lo": -0.01, "hi": 0.05}
    cleared = mr.derive_card({"card": card}, {"m": 0.42, "b": 0.40, "g": [0.01, 0.05]})
    assert "resolvable" not in cleared["headline"][0]
    assert _render(_card_js(), {"headline": cleared["headline"]}).count(STAR) == 1


def test_a_short_t_and_a_gap_inside_its_floor_demote_the_leg():
    base = {"label": "x", "champion": 0.24, "baseline": 0.25, "better": "lower"}
    for spec_extra, art_extra, want in (
            ({"t": "t"}, {"t": 1.2}, False), ({"t": "t"}, {"t": 2.0}, None),
            ({"mde95": "f"}, {"f": 0.02}, False), ({"mde95": "f"}, {"f": 0.005}, None)):
        card = {"headline": [dict(base)], "derived_from": {"headline": [
            dict({"champion": "m", "baseline": "b"}, **spec_extra)]}}
        got = mr.derive_card({"card": card}, dict({"m": 0.24, "b": 0.25}, **art_extra))
        assert got["headline"][0].get("resolvable") is want, (spec_extra, art_extra)


def test_the_gap_orientation_flips_a_lower_is_better_model_minus_baseline_gap():
    card = {"headline": [{"label": "x", "champion": 1.0, "baseline": 1.2,
                          "better": "lower"}],
            "derived_from": {"headline": [{"champion": "m", "baseline": "b",
                                           "gap_ci": {"lo": "lo", "hi": "hi",
                                                      "orientation": "model_minus_baseline"}}]}}
    got = mr.derive_card({"card": card}, {"m": 1.0, "b": 1.2, "lo": -0.3, "hi": -0.1})
    assert got["headline"][0]["gap_ci"] == {"lo": 0.1, "hi": 0.3}
    assert "resolvable" not in got["headline"][0]
    import pytest
    bad = json.loads(json.dumps(card))
    bad["derived_from"]["headline"][0]["gap_ci"]["orientation"] = "sideways"
    with pytest.raises(ValueError):
        mr.derive_card({"card": bad}, {"m": 1.0, "b": 1.2, "lo": -0.3, "hi": -0.1})
    flipped = json.loads(json.dumps(card))
    del flipped["derived_from"]["headline"][0]["gap_ci"]["orientation"]
    with pytest.raises(ValueError):    # lo above hi once read as written
        mr.derive_card({"card": flipped}, {"m": 1.0, "b": 1.2, "lo": 0.3, "hi": 0.1})


def test_a_no_contest_card_prints_no_star():
    ctx = _card_js()
    rows = {m["model_id"]: m for m in _cards()}
    assert rows["draft_slot_curve"]["card"].get("contest") is False
    for m in _cards():
        if m["card"].get("contest") is not False:
            continue
        for h in m["card"]["headline"]:
            assert h.get("resolvable") is False
            assert _render(ctx, {"headline": [h]}).count(STAR) == 0, m["model_id"]


def test_the_four_new_cards_equal_their_artifact_exactly():
    rows = {m["model_id"]: m for m in _cards()}
    for mid, legs in NEW_CARDS.items():
        m = rows.get(mid)
        assert m, f"{mid} has no card"
        spec = m["card"]["derived_from"]
        doc = _artifact(m)
        dig = spec.get("digits")
        rd = (lambda v: round(v, dig)) if dig is not None else (lambda v: v)
        heads = m["card"]["headline"]
        assert len(heads) == len(legs), mid
        for h, hs, (champ, base, n, extra) in zip(heads, spec["headline"], legs):
            assert hs["champion"] == champ and hs["baseline"] == base, (mid, hs)
            assert h["champion"] == rd(mr._dig_path(doc, champ)), (mid, champ)
            assert h["baseline"] == rd(mr._dig_path(doc, base)), (mid, base)
            if n is not None:
                assert hs["n"] == n and h["n"] == mr._dig_path(doc, n), (mid, n)
            for k, p in extra.items():
                assert hs[k] == p and h[k] == rd(mr._dig_path(doc, p)), (mid, k)
            assert isinstance(h.get("baseline_label"), str) and h["baseline_label"].strip()
            assert isinstance(h.get("stat"), str) and h["stat"].strip()
    # the card-level n is the betting window's own count
    assert rows["betting_game_prob"]["card"]["n"] == _artifact(
        rows["betting_game_prob"])["vintage"]["n"]


def test_mlb_projections_prospects_card_shows_the_mae_leg_it_loses():
    row = next(m for m in _cards() if m["model_id"] == "mlb_projections_prospects")
    spec = row["card"]["derived_from"]["headline"]
    assert {"champion": "baseline_pooled_oos.mae",
            "baseline": "challenger_pooled_oos.mae"} in spec
    leg = row["card"]["headline"][spec.index({"champion": "baseline_pooled_oos.mae",
                                              "baseline": "challenger_pooled_oos.mae"})]
    assert leg["better"] == "lower"
    assert _render(_card_js(), {"headline": [leg]}).count(STAR) == int(_champ_beats(leg))


def test_validate_rejects_a_typed_interval_and_an_unknown_field():
    import copy
    reg = mr.load()
    row = next(m for m in reg["models"] if m["model_id"] == "hem_plus")

    def problems_with(mutate):
        r = copy.deepcopy(reg)
        target = next(m for m in r["models"] if m["model_id"] == "hem_plus")
        mutate(target["card"])
        return [p for p in mr.validate(r) if p.startswith("hem_plus:")]

    assert problems_with(lambda c: None) == []
    # a typed interval number on a leg whose spec names no path
    assert problems_with(lambda c: c["derived_from"]["headline"][0].pop("gap_ci"))
    # a typed number in place of the interval's path
    assert problems_with(lambda c: c["derived_from"]["headline"][0].update(
        gap_ci={"lo": -0.01, "hi": 0.02}))
    assert problems_with(lambda c: c["derived_from"]["headline"][0].update(t=2.1))
    assert problems_with(lambda c: c["headline"][0].update(mde95=0.01))
    # unknown fields, on the spec and on the stored leg
    assert problems_with(lambda c: c["derived_from"]["headline"][0].update(lead="x"))
    assert problems_with(lambda c: c["headline"][0].update(lead=True))
    # stat length and contest type
    assert problems_with(lambda c: c["headline"][0].update(stat="x" * (mr.CARD_STAT_MAX + 1)))
    assert problems_with(lambda c: c.update(contest="no"))
    assert row["card"]["headline"][0]["stat"] == "Spearman"


# --------------------------------------------------------------------------- #
# Part 2: the /models/ accountability hub
# --------------------------------------------------------------------------- #
@functools.lru_cache(maxsize=1)
def _models_page() -> str:
    import build_site
    return build_site.build_models()


def _excluded_data_files() -> set:
    out = set()
    for line in (HERE / "deploy" / "data_exclude.txt").read_text(
            encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line)
    return out


def _page_data_links() -> list:
    return sorted(set(re.findall(r'href="(/data/[^"]+)"', _models_page())))


def test_models_page_links_only_files_the_deploy_actually_ships():
    """Both deploy consumers ship data/ at depth one only. A link to
    /data/<subdir>/<file> or to an excluded file renders as a working link
    locally and a 404 in production, which on a receipts page is worse than
    publishing no link at all."""
    excluded = _excluded_data_files()
    problems = []
    for url in _page_data_links():
        rel = url.lstrip("/")
        if rel.count("/") != 1:
            problems.append(f"{url} is not at data/ depth one")
        elif not (HERE / rel).exists():
            problems.append(f"{url} has no file in the tree")
        elif rel.split("/", 1)[1] in excluded:
            problems.append(f"{url} is held back by deploy/data_exclude.txt")
    assert not problems, "\n".join(problems)


def test_models_page_names_unshippable_artifacts_without_linking_them():
    """Some registry rows point at gate records under docs/ or at lab output
    under tools/. Those paths exist here and do not exist on the webroot, so
    the page must name them and say why they are not linked."""
    page = _models_page()
    unshippable = sorted({
        (m.get("eval_artifact") or "").strip().replace("\\", "/")
        for m in mr.load()["models"]
        if (m.get("eval_artifact") or "").strip()
        and not (m["eval_artifact"].replace("\\", "/").startswith("data/")
                 and m["eval_artifact"].replace("\\", "/").count("/") == 1)})
    for rel in unshippable:
        assert f'href="/{rel}"' not in page, (
            f"the ledger links {rel}, which the deploy does not publish")
        assert rel in page, (
            f"the ledger drops {rel} entirely; it must be named with the "
            "reason it carries no link")
    if unshippable:
        assert "not published:" in page


def test_models_page_verdict_counts_match_the_registry():
    """The tiles and the filter chips are counted off the registry at build
    time. A count that drifts from the rows underneath it would be the page
    making its own claim about the ledger."""
    page = _models_page()
    reg = mr.load()
    counts: dict = {}
    for m in reg["models"]:
        counts[m["verdict"]] = counts.get(m["verdict"], 0) + 1
    for verdict in mr.VERDICTS:
        n = counts.get(verdict, 0)
        # The count is asserted on the verdict's OWN tile, not anywhere on the
        # page: two verdicts can legitimately share a count.
        assert (f'acct-tile--{verdict}"><div class="acct-tilen">{n}</div>'
                in page), f"the {verdict} tile does not show {n}"
        assert (f'data-acct-filter="{verdict}">' in page), f"no {verdict} filter chip"
    assert f'data-acct-filter="all">All <span class="acct-count">{len(reg["models"])}</span>' in page


def test_every_registry_row_is_on_the_page():
    """The ledger's value is that nothing can hide in it, so a row that fails
    to render is the one bug worth a test of its own."""
    page = _models_page()
    missing = [m["model_id"] for m in mr.load()["models"]
               if f"<code>{m['model_id']}</code>" not in page]
    assert not missing, f"registry rows missing from /models/: {missing}"


def test_deprecated_is_rendered_as_a_first_class_group():
    """A loss ledger that files its losses somewhere quieter than its wins is
    not a loss ledger."""
    page = _models_page()
    assert 'data-acct-group="deprecated"' in page
    assert "failed its gate" in page


def test_unvalidated_is_defined_as_ungated_not_as_broken():
    """Owner copy rule for this page: `unvalidated` is a model whose gate has
    not been run. A reader who assumes it means defective has been misled by
    the page, not by the registry."""
    page = _models_page()
    assert "Registered and serving, with no measurement yet" in page
    assert "not the same thing as a model that is wrong" in page


def test_no_verdict_string_on_the_page_is_hand_written():
    """Every quoted artifact verdict must be a byte-for-byte top-level
    `verdict` field of the artifact the same row links. This is the test that
    makes the page's central promise checkable."""
    page = _models_page()
    quoted = re.findall(
        r"<dt>The artifact&#x27;s own words</dt><dd>(.*?)</dd>", page, re.S)
    assert quoted, "no artifact verdicts rendered; has the field label changed?"
    import html as _html
    known = set()
    for path in sorted((HERE / "data").glob("*.json")):
        if path.stat().st_size > 4_000_000:
            continue
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(doc, dict) and isinstance(doc.get("verdict"), str):
            known.add(doc["verdict"].strip())
    unknown = [q for q in quoted if _html.unescape(q) not in known]
    assert not unknown, (
        "verdict text on /models/ that is in no artifact: "
        f"{unknown[:3]}")


def test_the_deploy_rule_the_page_encodes_still_matches_the_deploy_scripts():
    """build_site._acct_artifact_url re-derives 'data/ at depth one, minus the
    exclude list' to decide what it may link. If a deploy consumer changes that
    rule, the page starts publishing 404s and every other test here still
    passes, so the rule itself is pinned."""
    nightly = (HERE / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert "--include='/data/*.json'" in nightly
    workflow = (HERE.parent / ".github" / "workflows"
                / "deploy-prospect-tracker.yml").read_text(encoding="utf-8")
    assert "find data -maxdepth 1" in workflow


# assets/accountability.js drives the one thing on /models/ that is not
# server-rendered: the artifact age, recomputed against the READER's clock so a
# cached page stops advertising the freshness it had on build day. It is run in
# a real JS engine over a DOM shim shaped like the markup build_models() emits
# (the test_betting.py / test_collegesavant_smoke.py pattern), because a filter
# that silently stops filtering on a receipts page hides rows without ever
# failing anything else.
_JS_SHIM = r"""
var __styles = [];
var __url = null;
function __el(tag, attrs, kids) {
  attrs = attrs || {};
  var e = {tag: tag, attrs: attrs, kids: kids || [], textContent: "", title: "",
           style: {}, classes: (attrs["class"] || "").split(" ").filter(Boolean)};
  e.getAttribute = function (k) { return this.attrs[k] === undefined ? null : this.attrs[k]; };
  e.setAttribute = function (k, v) { this.attrs[k] = v; };
  e.classList = {toggle: function (c, on) {
    var i = e.classes.indexOf(c);
    if (on && i === -1) e.classes.push(c);
    if (!on && i !== -1) e.classes.splice(i, 1);
  }};
  e.addEventListener = function (t, fn) { this.__click = fn; };
  e.querySelectorAll = function (sel) { return __find(this, sel); };
  e.querySelector = function (sel) { var r = __find(this, sel); return r.length ? r[0] : null; };
  return e;
}
function __walk(n, out) {
  for (var i = 0; i < n.kids.length; i++) { out.push(n.kids[i]); __walk(n.kids[i], out); }
  return out;
}
function __find(root, sel) {
  return __walk(root, []).filter(function (n) {
    if (sel === ".acct-group") return n.classes.indexOf("acct-group") !== -1;
    if (sel === ".acct-row") return n.classes.indexOf("acct-row") !== -1;
    if (sel === "[data-acct-filter]") return n.attrs["data-acct-filter"] !== undefined;
    if (sel === ".acct-sum>time[datetime]") return n.tag === "time" && n.attrs.datetime !== undefined;
    if (sel.indexOf('[data-acct-filter="') === 0)
      return n.attrs["data-acct-filter"] === sel.slice(19, -2);
    return false;
  });
}
var __app = null;
var document = {
  querySelector: function (s) { return s === ".acct-app" ? __app : null; },
  createElement: function (t) { return {tag: t, textContent: ""}; },
  head: {appendChild: function (n) { __styles.push(n.textContent); }}
};
var history = {replaceState: function (a, b, u) { __url = u; }};
var location = {hash: "", pathname: "/models/"};

function __row(flags, iso) {
  var t = iso ? __el("time", {datetime: iso}) : __el("time", {});
  var attrs = {"class": "acct-row"};
  if (flags) attrs["data-acct-flags"] = flags;
  return __el("details", attrs, [__el("summary", {"class": "acct-sum"}, [t])]);
}
var __groups = [
  __el("div", {"class": "acct-group", "data-acct-group": "validated"},
       [__row("undated", null), __row("", "2026-08-01")]),
  __el("div", {"class": "acct-group", "data-acct-group": "deprecated"},
       [__row("", "2026-08-01"), __row("", "2000-01-01")])
];
var __chips = ["all", "validated", "deprecated", "undated"].map(function (k) {
  return __el("button", {"data-acct-filter": k, "class": "chip"});
});
__app = __el("div", {"class": "acct-app", "data-acct-stale-days": "90"},
             __chips.concat(__groups));
function __click(k) { __find(__app, '[data-acct-filter="' + k + '"]')[0].__click(); }
function __vis() {
  var out = {groups: {}, rows: [], styles: __styles.length, url: __url, times: []};
  __find(__app, ".acct-group").forEach(function (g) {
    out.groups[g.getAttribute("data-acct-group")] = g.style.display || "";
    __find(g, ".acct-row").forEach(function (r) {
      out.rows.push([r.getAttribute("data-acct-flags") || "", r.style.display || ""]);
    });
  });
  __find(__app, ".acct-sum>time[datetime]").forEach(function (t) {
    out.times.push([t.getAttribute("datetime"), t.textContent,
                    t.classes.indexOf("is-stale") !== -1]);
  });
  return JSON.stringify(out);
}
"""


def _js_ctx():
    import pytest
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    ctx = MiniRacer()
    ctx.eval(_JS_SHIM)
    ctx.eval((HERE / "assets" / "accountability.js").read_text(encoding="utf-8"))
    return ctx


def test_client_recomputes_artifact_age_against_the_readers_clock():
    ctx = _js_ctx()
    st = json.loads(ctx.eval("__vis()"))
    assert st["styles"] == 1, "the client must inject exactly one stylesheet"
    ages = {t[0]: t for t in st["times"]}
    assert ages["2026-08-01"][1].endswith("d"), "a dated artifact got no age"
    assert ages["2026-08-01"][2] is False, "a recent artifact was flagged stale"
    assert ages["2000-01-01"][2] is True, "a decades-old artifact did not read stale"


def test_client_filters_by_verdict_and_by_audit_flag():
    """A verdict chip selects a group. An audit chip cuts across groups, which
    is a different code path and the one that can silently show nothing."""
    ctx = _js_ctx()
    ctx.eval('__click("deprecated")')
    st = json.loads(ctx.eval("__vis()"))
    assert st["groups"] == {"validated": "none", "deprecated": ""}
    assert all(r[1] == "" for r in st["rows"]), "a verdict filter hid single rows"
    assert st["url"] == "#verdict=deprecated"

    ctx.eval('__click("undated")')
    st = json.loads(ctx.eval("__vis()"))
    shown = [r for r in st["rows"] if r[1] == ""]
    assert shown == [["undated", ""]], f"the audit filter selected {shown}"
    assert st["groups"]["validated"] == "" and st["groups"]["deprecated"] == "none"
    assert st["url"] == "#show=undated"

    ctx.eval('__click("all")')
    st = json.loads(ctx.eval("__vis()"))
    assert all(r[1] == "" for r in st["rows"])
    assert set(st["groups"].values()) == {""}
    assert st["url"] == "/models/"


def test_the_hub_ships_and_is_crawlable():
    import build_site
    manifest = [ln.strip() for ln in
                (HERE / "deploy" / "publish_paths.txt").read_text(encoding="utf-8").splitlines()
                if ln.strip() and not ln.strip().startswith("#")]
    assert "models" in manifest, (
        "models/ is not in deploy/publish_paths.txt and would 404 in production")
    assert "/models/</loc>" in build_site.build_sitemap([])
    assert 'href="/models/"' in build_site._footer()
