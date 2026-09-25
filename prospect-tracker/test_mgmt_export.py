"""The /management/ payload and the page that renders it.

THE POINT OF THIS PAGE IS THAT IT HAS NO PLUS METRIC. The gate battery was frozen before
it ran, it came back a BOUNDED null, and the verdict set the scope: a club's decision value
in the running game does not repeat between halves of its own season, so no club may be
ranked by it.

What the null buys is the right to say what the league is doing, and the league result is
the page: 13,973 priced attempts, second stolen at almost exactly its own break-even, third
worth having and home not.

THE SIX MISTAKES THESE TESTS EXIST FOR:

  1. SHIPPING A PLUS METRIC ANYWAY. Summed decision value per club is the obvious column and
     it is a ranking of noise. It must not reach the payload, let alone the page.
  2. QUOTING THE RAW SPLIT-HALF. It is 0.7789 and it looks like a strong repeatable skill.
     Both halves of a club-season sit in the same season, so a league-wide year effect reads
     as agreement: season explains 79.6 percent of the variance and the club 2.2 percent.
  3. PUBLISHING AN UNBOUNDED NULL. A null with no detection floor says nothing. This one
     would have seen 0.0005 wins per attempt, which makes it a ceiling.
  4. LOSING THE EXCLUSIONS. Two-out attempts are excluded because the caught-stealing case
     crosses the half-inning boundary where two estimators meet and nothing calibrates them;
     11,783 attempts leave that way and the count belongs on the page. It read 9,328 until
     2026-09-11, because every caught stealing that ENDED a plate appearance lives only on
     the play's own result and was never read (audit F02-01); the census sentence now shows
     the table closing against the corpus.
  5. TYPING A FIGURE INTO THE HTML OR JS.
  6. LETTING THE MANAGER SECTION LOOK DEFERRED RATHER THAN DECIDED. It is not "coming soon":
     the null says building the manager entity to attribute this family is not worth doing.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

ART = ROOT / "data" / "management_board.json"
PAGE = ROOT / "management" / "index.html"
JS = ROOT / "assets" / "management.js"
GATE = ROOT / "docs" / "IN_GAME_MANAGEMENT_GATE.md"


@pytest.fixture(scope="module")
def d():
    if not ART.exists():
        pytest.skip("run python mgmt_export.py")
    return json.loads(ART.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# No plus metric, anywhere
# --------------------------------------------------------------------------

def test_the_club_board_carries_no_decision_value_column(d):
    """MISTAKE 1. The gate allows volume and refuses the plus metric.

    EXTENDED 2026-09-23 to the decision ledger's `clubs` block: the same rule scans
    every club-season row there, so decision value above state (DVS) cannot reach a
    club-season row under a new block name. The realized columns are named
    mwpa_<family> and are a different quantity (what happened, not what the
    decision was worth); the count keys are n_all / n_<family>."""
    t = d["teams"]
    if t.get("status") != "built":
        pytest.skip(f"club board not built: {t.get('status')}")
    for r in t["rows"]:
        for k in r:
            assert "dv" not in k and "decision" not in k, (
                f"the club board carries {k}, which is the plus metric the gate "
                "withheld")
    c = d.get("clubs") or {}
    for r in c.get("rows") or []:
        for k in r:
            assert "dv" not in k and "decision" not in k, (
                f"the clubs block carries {k}: a per-club decision value column is "
                "the rank the gate withheld, whatever the header tag says")
            if isinstance(r[k], dict):
                for kk in r[k]:
                    assert "dv" not in kk and "decision" not in kk, (k, kk)


def test_the_style_board_and_the_club_rows_share_one_club_code(d):
    """M10-03. The club page joins teams.rows to clubs.rows on the code, so the two
    blocks must key every season on the same canonical org. The style board keyed
    the Athletics OAK for 2018-2024 while the clubs block keyed them ATH, and six
    ATH club pages printed no steal block."""
    t = d["teams"]
    c = d.get("clubs") or {}
    if t.get("status") != "built" or not c.get("rows"):
        pytest.skip("club board or clubs block not built")
    ts = {(r["team"], r["season"]) for r in t["rows"]}
    cs = {(r["club"], r["season"]) for r in c["rows"]}
    assert ts == cs, (sorted(ts - cs), sorted(cs - ts))


def test_the_running_and_bunt_blocks_carry_the_corpus_they_were_priced_from(d):
    """M10-05. The Running Game and Bunt tabs printed no date. Each block now carries
    its artifact's corpus build; the through-date is the ledger's, and only when the
    two share one build."""
    dec = d.get("decisions") or {}
    for blk in (d["running_game"], d["sections"]["sacrifice_bunt"]):
        v = blk.get("vintage")
        assert v is not None and v["corpus_built_at"], "the block does not say which corpus priced it"
        if v["same_corpus_as_ledger"]:
            newest = str(max(int(s) for s in dec["seasons"]))
            assert v["through"] == dec["through_by_season"][newest]
        else:
            assert v["through"] is None


def test_the_headline_totals_sum_the_attempts_on_the_cards(d):
    """M10-05. The headline's net and pool were read off the frozen gate eval, so a
    corpus rebuild left "net -0.69 wins" beside cards summing to -0.39. They are read
    off the running artifact; on the gate's own corpus the two agree to the digit
    (-0.6922524899426303 and 47.504259623449755, re-measured 2026-09-25)."""
    h, bt = d["headline"], d["running_game"]["by_target"]
    cards = sum(v["sum_dv_wins"] for v in bt.values())
    assert abs(h["net_dv_all_seasons_wins"] - cards) < 0.02, (h["net_dv_all_seasons_wins"], cards)
    run = json.loads((ROOT / "data" / "management_running.json").read_text(encoding="utf-8"))
    if "net_dv_wins" in run:
        assert h["net_dv_all_seasons_wins"] == round(run["net_dv_wins"], 2)
        assert h["redistributable_pool_abs_dv_wins"] == round(run["sum_abs_dv_wins"], 2)
        assert h["games"] == run["games_in_corpus"]


def test_the_payload_says_why_there_is_no_plus_metric(d):
    s = d["sections"]["team_style"]
    assert s["plus_metric"] is False
    assert "ranking of noise" in s["why_no_plus_metric"]


def test_the_gate_verdict_travels_with_the_payload(d):
    assert "DESCRIPTIVE ONLY" in d["gate_verdict"]
    assert d["gate_doc"] == "docs/IN_GAME_MANAGEMENT_GATE.md"
    assert d["gate_frozen_at"]


def test_the_page_states_what_it_does_not_claim(d):
    txt = d["what_this_page_does_not_claim"]
    assert "bounded null" in txt and "0.0005" in txt


# --------------------------------------------------------------------------
# The gate, reported honestly
# --------------------------------------------------------------------------

def test_the_split_half_sits_inside_its_null_band(d):
    g = d["gate"]
    lo, hi = g["null_band"]
    assert lo < g["split_half_r"] < hi, (
        "the season-controlled split-half now CLEARS its permutation band, which "
        "would mean club decision value repeats after all. That is a real finding "
        "and the whole page scope changes with it")
    assert g["clears_null"] is False


def test_the_raw_number_is_published_beside_the_controlled_one(d):
    """MISTAKE 2. Publishing only the controlled number invites a reader who finds
    the raw one elsewhere to think it was hidden."""
    g = d["gate"]
    assert g["raw_split_half_r_for_comparison"] > 0.7
    assert g["split_half_r"] < 0.2
    why = g["why_the_raw_number_is_not_the_finding"]
    # The sentence is built from the gate fields beside it, so it must quote them,
    # never a typed figure (it quoted 79.6 for weeks after the field read 78.7).
    assert "same season" in why
    assert f"{100.0 * g['variance_explained_by_season']:.1f}" in why


def test_the_null_is_bounded_by_a_detection_floor(d):
    """MISTAKE 3."""
    g = d["gate"]
    assert g["smallest_detectable_per_attempt_sd"] > 0
    assert "ceiling" in g["detection_floor_reading"]


def test_the_null_construction_is_published(d):
    c = d["gate"]["null_construction"]
    assert "WITHIN season" in c
    assert "attempt count" in c


def test_variance_attribution_is_published(d):
    g = d["gate"]
    assert g["variance_explained_by_season"] > 0.5
    assert g["variance_explained_by_team"] < 0.1


# --------------------------------------------------------------------------
# The league result
# --------------------------------------------------------------------------

def test_the_headline_numbers_come_from_the_running_artifact(d):
    h, bt = d["headline"], d["running_game"]["by_target"]
    assert h["league_steals_second_at"] == bt["2B"]["success_rate"]
    assert h["against_a_breakeven_of"] == bt["2B"]["swing_weighted_breakeven_p"]
    assert h["sum_dv_wins_second"] == bt["2B"]["sum_dv_wins"]


def test_second_is_a_coin_and_third_pays_and_home_does_not(d):
    """The finding, pinned. If any of the three flips sign the page's whole lede
    changes and a human should look at it."""
    bt = d["running_game"]["by_target"]
    assert abs(bt["2B"]["success_rate"] - bt["2B"]["swing_weighted_breakeven_p"]) < 0.01
    assert bt["3B"]["sum_dv_wins"] > 0
    assert bt["HOME"]["sum_dv_wins"] < 0


def test_the_swing_weighted_breakeven_is_the_one_that_predicts_the_sign(d):
    """Three break-evens are published and only one determines the verdict. A
    reader comparing the success rate against the MEDIAN would get the sign
    wrong on steals of second."""
    txt = d["running_game"]["which_breakeven_predicts_the_sign"]
    assert "swing-weighted" in txt
    bt = d["running_game"]["by_target"]["2B"]
    assert bt["median_breakeven_p"] != bt["swing_weighted_breakeven_p"]


def test_the_exclusions_are_published_with_their_counts(d):
    """MISTAKE 4."""
    ex = d["running_game"]["excluded"]
    assert ex["two_outs_crosses_the_boundary"] > 1000
    txt = d["running_game"]["why_two_out_attempts_are_excluded"]
    assert "half-inning" in txt and "boundary" in txt


def test_the_census_sentence_is_read_off_the_payload(d):
    """MISTAKE 4 AGAIN, the way it actually happened (audit F02-01). The page
    said the excluded attempts "are excluded and counted" while 2,455 of them
    were neither, and nothing on the page let a reader check. The census
    sentence puts the corpus count beside the priced and excluded counts, every
    figure interpolated from the same payload the table is drawn from."""
    rg = d["running_game"]
    c = rg.get("attempt_census")
    s = rg.get("attempt_census_sentence")
    assert c and s, "rebuild: python management.py, then python mgmt_export.py"
    ex = sum(rg["excluded"].values())
    for n in (c["total"], c["from_the_events_table"],
              c["from_the_play_result_only"], rg["n_attempts_priced"], ex):
        assert f"{n:,}" in s, f"{n:,} is not in the census sentence: {s}"
    if rg["n_attempts_priced"] + ex == c["total"]:
        assert "one or the other" in s
    else:
        assert "one or the other" not in s, (
            "the sentence says the table closes and the payload says it does not")


def test_a_census_gap_is_said_rather_than_hidden():
    """The sentence reports a gap from the counts themselves, never from a flag,
    so a future loss of the same shape reaches the page as a stated number."""
    import mgmt_export as X
    run = {"n_attempts_priced": 10, "excluded": {"a": 3, "b": 0},
           "attempt_census": {"total": 15, "from_the_events_table": 12,
                              "from_the_play_result_only": 3,
                              "seasons": ["2098", "2099"]}}
    s = X._census_sentence(run)
    assert "2 attempts neither priced nor counted" in s
    assert "one or the other" not in s
    run["attempt_census"]["total"] = 13
    assert "one or the other" in X._census_sentence(run)
    assert X._census_sentence({"n_attempts_priced": 1, "excluded": {}}) is None


def test_the_decision_execution_identity_is_exact(d):
    dec = d["running_game"]["decomposition"]
    assert dec["identity_max_abs_error"] == 0.0
    assert "DV + ER" in dec["identity"]


def test_the_league_average_runner_is_deliberate_and_said_so(d):
    txt = d["running_game"]["why_the_league_average_runner"]
    assert "roster fact" in txt


# --------------------------------------------------------------------------
# The reference tables
# --------------------------------------------------------------------------

def test_the_run_expectancy_matrix_has_all_twenty_four_cells(d):
    re = d["reference"]["run_expectancy"]
    assert len(re) == 24
    assert {r["outs"] for r in re} == {0, 1, 2}
    assert len({r["base_code"] for r in re}) == 8


def test_run_expectancy_falls_with_outs_in_every_base_state(d):
    """The one property a reader would notice if it broke."""
    re = d["reference"]["run_expectancy"]
    by = {}
    for r in re:
        by.setdefault(r["base_code"], {})[r["outs"]] = r["runs"]
    for base, cells in by.items():
        assert cells[0] > cells[1] > cells[2], (
            f"base state {base} does not fall monotonically with outs")


def test_the_bases_are_labelled_and_not_left_as_a_bit_code(d):
    re = d["reference"]["run_expectancy"]
    labels = {r["bases"] for r in re}
    assert "loaded" in labels and "empty" in labels and "1B 3B" in labels


def test_the_win_model_disclosures_travel(d):
    """Three things a reader has to be told about a win model built to be
    differenced: that the base state enters only through run expectancy (which
    is what makes differencing safe), that smoothing costs the ninth-inning
    tails, and that the state deliberately excludes everything that would let a
    manager's roster leak into his grade."""
    ref = d["reference"]
    assert "run expectancy" in ref["monotone_by_construction"]
    assert "positive coefficient" in ref["monotone_by_construction"]
    assert "less sharp" in ref["smoothing_costs_the_tails"]
    assert "ninth" in ref["smoothing_costs_the_tails"]
    assert "park" in ref["state_excludes"] and "batter" in ref["state_excludes"]


def test_every_run_expectancy_cell_carries_its_sample_size(d):
    """A run-expectancy cell is only as good as the plays behind it, and
    bases-loaded-two-out is an order of magnitude thinner than
    bases-empty-none-out."""
    for r in d["reference"]["run_expectancy"]:
        assert r["runs"] is not None, (
            f"base {r['base_code']} outs {r['outs']} came back null; the cells "
            "are dicts and reading one as a scalar gives a matrix of nulls")
        assert r["n"] and r["n"] > 100


# --------------------------------------------------------------------------
# The dark sections
# --------------------------------------------------------------------------

def test_the_manager_section_is_decided_and_not_merely_deferred(d):
    """MISTAKE 6. The null says building the manager entity to attribute THIS
    family is not worth doing. That is a decision, not a queue position."""
    s = d["sections"]["manager_attribution"]
    assert s["live"] is False
    assert "UPPER BOUND" in s["why"]
    assert "not there" in s["why"] or "is not there" in s["why"]


def test_the_other_families_are_explicitly_not_covered(d):
    s = d["sections"]["bullpen_and_lineup"]
    assert s["live"] is False
    assert "have not been measured" in s["why"] or "not been measured" in s["why"]


# --------------------------------------------------------------------------
# Nothing is typed, and the page is reachable
# --------------------------------------------------------------------------

def test_no_figure_is_typed_into_the_page_html(d):
    """MISTAKE 5."""
    h = PAGE.read_text(encoding="utf-8")
    for n in (d["running_game"]["n_attempts_priced"],
              d["gate"]["agent_seasons"],
              d["headline"]["games"]):
        assert str(n) not in h, f"{n} is typed into the page and will go stale"


def test_the_js_reads_its_copy_from_the_payload():
    js = JS.read_text(encoding="utf-8")
    for key in ("why_no_plus_metric", "why_the_raw_number_is_not_the_finding",
                "detection_floor_reading", "why_two_out_attempts_are_excluded",
                "attempt_census_sentence",
                "columns_are_style_not_skill", "what_this_page_does_not_claim"):
        assert key in js, f"the page does not render the payload's {key}"
    assert "NOT ONE FIGURE IN THIS FILE IS TYPED" in js


def test_the_page_has_no_banned_dash():
    for f in (PAGE, JS, ROOT / "assets" / "management.css", ROOT / "mgmt_export.py"):
        txt = f.read_text(encoding="utf-8")
        assert "—" not in txt and "–" not in txt, f"banned dash in {f.name}"


def test_management_is_in_the_deploy_publish_list():
    lines = (ROOT / "deploy" / "publish_paths.txt").read_text(
        encoding="utf-8").splitlines()
    assert "management" in lines, (
        "omit this and every test stays green while /management/ 404s in "
        "production")


def test_management_is_in_the_sitemap():
    assert "/management/" in (ROOT / "sitemap.xml").read_text(encoding="utf-8")


def test_management_is_excluded_from_pytest_collection():
    assert "\n    management\n" in (ROOT / "pytest.ini").read_text(encoding="utf-8")


def test_the_export_is_a_watched_scheduled_export():
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index("SCHEDULED_EXPORTS = (")
    assert '"mgmt_export"' in src[i:i + 3200]
    assert "6b7c. In-Game Management board" in src


def test_the_board_is_in_the_data_catalog():
    assert '"management_board.json"' in (ROOT / "data_catalog.py").read_text(
        encoding="utf-8")


def test_the_gate_doc_exists_and_is_frozen():
    assert GATE.exists()
    txt = GATE.read_text(encoding="utf-8")
    assert "2026-09-06" in txt


# --- the two invariants whose absence WAS the defect (audit F07-01, F07-02) ---

def test_every_tied_game_boundary_cell_is_populated_and_carries_its_sample(d):
    """F07-01: the served half-inning-start table shipped 18 of 18 tied-game rows
    BLANK, under copy telling the reader the boundary is priced from exactly this
    table. The numbers existed and were correct in data/win_expectancy.json the
    whole time; the export wrapped them in a shape the renderer could not read,
    and no assertion anywhere compared the two. The absence of this test is the
    whole of the finding, so it is the test that matters more than the fix."""
    his = d["reference"]["half_inning_start"]
    tied = his["tied_game"]
    assert len(tied) == 18, f"expected 18 tied-game rows, got {len(tied)}"
    for r in tied:
        assert r.get("batting_team_win_prob") is not None, (
            f"inning {r.get('inning')} {r.get('half')} serves a blank win "
            "probability; that is F07-01 returning")
        assert 0.0 < r["batting_team_win_prob"] < 1.0
        assert (r.get("n") or 0) > 100, (
            f"inning {r.get('inning')} {r.get('half')} carries n={r.get('n')}; a "
            "served cell must publish the sample it was measured on")


def test_the_last_licks_edge_survives_in_the_served_table(d):
    """The bottom of an inning is worth more than the top of the same inning to
    the batting team, because the home side bats last. A table that lost this
    would be reporting noise."""
    tied = d["reference"]["half_inning_start"]["tied_game"]
    by = {(r["inning"], r["half"]): r["batting_team_win_prob"] for r in tied}
    ninth_top, ninth_bot = by.get((9, "top")), by.get((9, "bottom"))
    assert ninth_top is not None and ninth_bot is not None
    assert ninth_bot > ninth_top, (
        f"bottom of the ninth ({ninth_bot}) must beat the top ({ninth_top})")


def test_the_headline_sentence_agrees_in_sign_with_its_own_number(d):
    """F07-02: the served sentence said the running game was 'worth about one and
    a half wins to the entire league' while the corrected number is NEGATIVE. The
    sentence was TYPED and the number was computed, so nothing could catch the
    disagreement. Both are now derived; this pins that they cannot diverge again.

    The rule is the one the accuracy page already follows: a served number inside
    a string is interpolated from the artifact, never typed."""
    hl = d["headline"]
    net = hl.get("net_dv_all_seasons_wins")
    sentence = hl.get("sentence") or ""
    assert net is not None, "the running game serves no net decision value"
    assert sentence, "the running game serves no headline sentence"
    low = sentence.lower()
    if net < 0:
        assert "cost" in low, (
            f"net is {net} wins but the sentence does not say the running game "
            f"costs anything: {sentence[:160]}")
    else:
        assert ("worth" in low) or ("pay" in low), (
            f"net is {net} wins and the sentence does not say so: {sentence[:160]}")
    nums = [float(x) for x in re.findall(r"(\d+\.?\d*)\s*wins", low)]
    assert any(abs(n - abs(net)) < 0.55 for n in nums), (
        f"the sentence quotes {nums} wins and the artifact says {net}")


def test_the_bunt_sentence_agrees_with_its_own_total(d):
    """Same rule, the other served paragraph. The bunt total moved 26.6 percent
    on the F07-02 repair and the sentence has to move with it."""
    blk = d["sections"]["sacrifice_bunt"]
    sentence = (blk.get("sentence") or "").lower()
    assert sentence, "the bunt section serves no sentence"
    total = None
    for k in ("total_decision_value_wins", "total_dv_wins", "total_wins"):
        if blk.get(k) is not None:
            total = float(blk[k]); break
    if total is None:
        pytest.skip("no machine-readable bunt total on this build")
    nums = [float(x) for x in re.findall(r"(\d+\.?\d*)\s*wins", sentence)]
    assert any(abs(n - abs(total)) < 1.5 for n in nums), (
        f"the bunt sentence quotes {nums} wins against an artifact total of {total}")
    if total < 0:
        assert "cost" in sentence


# --------------------------------------------------------------------------
# The decision ledger blocks (2026-09-23, D2 Wave A)
# --------------------------------------------------------------------------

def _ledger(d):
    dec = d.get("decisions") or {}
    if not dec.get("live"):
        pytest.skip(f"decision ledger not built: {dec.get('status')}")
    return dec


def test_club_rows_carry_per_family_mwpa_and_no_cross_family_total(d):
    """Per-family sums only: the windows overlap across families, so one composite
    per club-season would double count. The defensive sub's window is stored on
    each decision and never summed."""
    dec = _ledger(d)
    fams = dec["families"]
    summed = [f for f, v in fams.items() if v.get("summed")]
    assert "pitching_change" in summed and "pinch_hit" in summed and "defensive_sub" not in summed
    rows = d["clubs"]["rows"]
    assert len(rows) >= 200
    for r in rows:
        for f in summed:
            assert f"mwpa_{f}" in r, (r["club"], r["season"], f)
            assert f"n_{f}" in r
        for bad in ("mwpa", "mwpa_total", "mwpa_all", "mwpa_sum", "mwpa_defensive_sub"):
            assert bad not in r, (r["club"], r["season"], bad)
        assert r["agent"] == "club-season"
    # and no league sum either: the census prints "stored, not summed" for it
    for f, v in fams.items():
        if not v.get("summed"):
            assert not v.get("league_sum_mwpa_by_season"), f
    assert dec["no_cross_family_total"] is True
    assert d["clubs"]["plus_metric"] is False
    assert "realized" in d["clubs"]["realized_header_tag"]


def test_the_census_steal_sum_is_the_running_game_decomposition(d):
    """Audit MH-01. The League census Steals row and the Running Game tab price the
    same attempts, so per season the realized sum equals DV + ER. It read 2024 -9.95
    against +3.20 while the column carried the feed's plate-appearance figure."""
    dec = _ledger(d)
    sums = dec["families"]["steal"]["league_sum_mwpa_by_season"]
    by = d["running_game"]["by_season"]
    common = sorted(set(sums) & set(by))
    assert len(common) >= 5
    for s in common:
        want = by[s]["sum_dv_wins"] + by[s]["sum_er_wins"]
        assert abs(sums[s] - want) < 0.03, (s, sums[s], want)


def test_the_dark_section_narrowed_to_what_is_still_dark(d):
    """bullpen_and_lineup used to say the bullpen call and the pinch hit were not
    measured. Their REALIZED value now ships; what stays dark is their DECISION
    value (the counterfactual) and lineup value, and the section says exactly that."""
    _ledger(d)
    s = d["sections"]["bullpen_and_lineup"]
    assert s["live"] is False
    assert s["still_dark"] == ["bullpen_decision_value", "pinch_hit_decision_value", "lineup_value"]
    assert "pitching_change" in s["now_live_as_realized_value"]
    assert "pinch_hit" in s["now_live_as_realized_value"]
    assert "M-ENG-1" in s["blocked_on"]
    assert "not been measured" in s["why"]
    assert "not the decision's value" in s["why"]
    for k in ("league", "decisions", "clubs"):
        assert d["sections"][k]["live"] is True, k
    for k in ("managers", "challenges", "lineups"):
        assert d["sections"][k]["live"] is False, k
        assert d["sections"][k]["blocked_on"], k


def test_the_shard_index_matches_the_files_on_disk(d):
    """The board's shard index is what the drill-down fetches from; every entry
    must be a file on disk with the same byte count, every file must be indexed,
    and BOTH deploy consumers must ship the directory or the whole tab 404s in
    production (the debuts_full lesson)."""
    _ledger(d)
    idx = d["shards"]["index"]
    assert idx, "no shards indexed"
    assert d["shards"]["path_template"] == "/data/mgmt_decisions/{season}-{club}.json"
    sdir = ROOT / "data" / "mgmt_decisions"
    on_disk = {p.name: p.stat().st_size for p in sdir.glob("*.json")} if sdir.exists() else {}
    if not on_disk:
        pytest.skip("shards not on this machine (untracked; regenerate with mgmt_decisions.py)")
    for e in idx:
        name = f"{e['season']}-{e['club']}.json"
        assert name in on_disk, f"indexed shard {name} is not on disk"
        assert on_disk[name] == e["bytes"], f"{name}: index says {e['bytes']} bytes, disk {on_disk[name]}"
    indexed = {f"{e['season']}-{e['club']}.json" for e in idx}
    assert set(on_disk) == indexed, sorted(set(on_disk) ^ indexed)
    nightly = (ROOT / "deploy" / "nightly-build.sh").read_text(encoding="utf-8")
    assert "--include='/data/mgmt_decisions/***'" in nightly
    wf = ROOT.parent / ".github" / "workflows" / "deploy-prospect-tracker.yml"
    if wf.exists():
        assert re.search(r"cp\s+-r\s+data/mgmt_decisions\b", wf.read_text(encoding="utf-8"))
    header = (ROOT / "deploy" / "publish_paths.txt").read_text(encoding="utf-8")
    assert "mgmt_decisions/" in header


def test_the_new_step_is_a_watched_scheduled_export():
    """"mgmt_decisions" sits directly BELOW "mgmt_export" in SCHEDULED_EXPORTS (the
    window scan on mgmt_export has 97 characters of slack, so nothing may be added
    above it) and before "hof_export"; step 6b7e exists."""
    src = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    i = src.index("SCHEDULED_EXPORTS = (")
    j = src.index(")", src.index('"hof_export"', i))
    block = src[i:j]
    a, b, c = block.index('"mgmt_export"'), block.index('"mgmt_decisions"'), block.index('"hof_export"')
    assert a < b < c
    assert '"mgmt_export"' in src[i:i + 3200], "the window scan on mgmt_export must still hold"
    assert "6b7e. In-Game Management decision ledger" in src
    assert '_record_ingest("mgmt_decisions"' in src


def test_statsapi_code_maps_every_canonical_club(d):
    """Wave 0 helper: the outbound StatsAPI code for every club the board serves,
    so the club page's link into /mlbstats/#team= never renders an empty board."""
    import trades
    for site, sapi in (("KCR", "KC"), ("CHW", "CWS"), ("WSN", "WSH"), ("ARI", "AZ"),
                       ("SDP", "SD"), ("SFG", "SF"), ("TBR", "TB"), ("ATH", "ATH"), ("NYY", "NYY")):
        assert trades.statsapi_code(site) == sapi, site
    assert trades.statsapi_code("KC") == "KC", "an already-StatsAPI code round-trips"
    assert trades.statsapi_code(None) is None and trades.statsapi_code("ZZZ") is None
    _ledger(d)
    codes = d["clubs"]["statsapi_codes"]
    clubs = {r["club"] for r in d["clubs"]["rows"]}
    assert clubs <= set(codes), sorted(clubs - set(codes))
    assert all(codes[c] for c in clubs)


def test_the_ejection_census_agrees_with_the_managers_fixture(d):
    """Every ejection row the corpus carries is counted (a row with no role word
    parses loosely off the club nickname), so the League census and the Managers
    tab print one number for the family, and a row the parser could not place is
    published rather than dropped in silence."""
    dec = _ledger(d)
    ej = dec["families"]["ejection"]
    assert ej["n"] + ej["unattributed"] + ej["unpositioned"] == ej["n_corpus_rows"]
    assert ej["n_corpus_rows"] == d["managers"]["fixture"]["ejections"]
    assert sum(ej["n_corpus_rows_by_season"].values()) == ej["n_corpus_rows"]
    for s, n in ej["n_by_season"].items():
        assert n <= ej["n_corpus_rows_by_season"][s], s
    assert "n_corpus_rows_by_season" in JS.read_text(encoding="utf-8")


def test_club_page_routes_are_read_off_the_disk(d):
    """The club page links to /franchise/ (D3) and /ledger/ (D1) only once the
    route is built: the export reads the route directory and never assumes it."""
    for route in ("franchise", "ledger"):
        assert d["routes"][route] == (ROOT / route / "index.html").exists()
    assert "DATA.routes" in JS.read_text(encoding="utf-8")


def test_the_dark_ledger_reads_as_a_sentence_not_an_instruction():
    """A missing ledger prints to readers; it must never print a shell command."""
    src = (ROOT / "mgmt_export.py").read_text(encoding="utf-8")
    assert "run python mgmt_decisions.py" not in src
    assert "the decision ledger is not on this build" in src
    rm = (ROOT / "run_monthly.py").read_text(encoding="utf-8")
    e, c = rm.index("6b7e. In-Game Management decision ledger"), rm.index("6b7c. In-Game Management board")
    assert e < c, "the ledger step runs before the board export that reads it"
    body = rm[e:c]
    assert 'if _mdd.get("status") == "built":' in body
    assert body.index('if _mdd.get("status") == "built":') < body.index("_mdc.OUT.write_text"), (
        "a not-built stub must never overwrite the committed ledger")
    assert body.count('_record_ingest("mgmt_decisions", False') == 1, "only a raise is a red"


def test_the_managers_block_is_dark_with_its_fixture(d):
    _ledger(d)
    m = d["managers"]
    if m.get("live"):
        pytest.skip("the manager ledger has landed")
    assert "M-MWAR-2" in m["blocked_on"]
    assert m["fixture"]["ejection_named_managers"] > 0
    assert m["agent_sentence"] == d["decisions"]["agent_sentence"]


# --------------------------------------------------------------------------
# The betting Dugout context block reads these keys (cross-module contract pin)
# --------------------------------------------------------------------------

def test_the_board_carries_the_keys_the_betting_dugout_block_reads(d):
    """betting_dugout.py (the /betting/ Dugout context sidecar) copies these board
    strings verbatim and these row values unchanged. Reading the constant tuples from
    betting_dugout in a MANAGEMENT test is a one-way read of names and is allowed; the
    reverse (betting_dugout importing mgmt_*) is what test_betting_mgmt_fence forbids.
    A rename on the board that this test misses would render as a dark block on every
    game card, so the keys are pinned here where the board is built."""
    c = d.get("clubs") or {}
    if c.get("status") != "built":
        pytest.skip(f"clubs block not built: {c.get('status')}")
    bd = pytest.importorskip("betting_dugout")
    dec = d["decisions"]
    for k in ("realized_sentence", "agent_sentence", "overlap_note", "through_by_season",
              "corpus_built_at"):
        assert dec.get(k), k
    assert dec["units"].get("mwpa") and dec["units"].get("z")
    assert dec["families"]["pitching_change"]["hook_pitch_count"]["median"]
    for k in ("style_sentence", "agent_sentence", "floors", "games_floor", "statsapi_codes"):
        assert c.get(k), k
    for f in bd.REALIZED_FAMILIES:
        assert dec["families"][f].get("label"), f
        assert f in c["floors"], f
    row_keys = ([k for k, _l, _b in bd.STYLE_COLUMNS] + [k for k, _l, _u, _d in bd.RATE_COLUMNS]
                + [f"mwpa_{f}" for f in bd.REALIZED_FAMILIES]
                + [f"n_{f}" for f in bd.REALIZED_FAMILIES] + ["games", "partial", "club", "season"])
    for r in c["rows"]:
        for k in row_keys:
            assert k in r, (r["club"], r["season"], k)
    # the block's own key rule holds on what it would copy: no key contains dv / decision
    for k in row_keys:
        assert "dv" not in k and "decision" not in k

