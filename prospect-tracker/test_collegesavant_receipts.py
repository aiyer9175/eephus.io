# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""College-to-pro receipts and the out-of-sample scorecard (owner answer M20-3).

Census M03-13: CollegeSavant pages showed a projected Single-A line but never the
line the player posted, never linked to PROSPX, and the PROSPX draftee card had
no CollegeSavant block. college_translation.build() now writes, per translation
entry, draft_key, milb_key and actual_single_a (the earliest qualifying A/A+
season exactly as load_single_a picks it, with the held-out projection), a
bridge entry carrying CS+ and key percentiles, and the scorecard artifact the
What-to-trust copy reads.

Every test reads the SERVED artifacts and renders the vendored apps.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import college_translation as ct

ROOT = Path(__file__).parent
DATA = ROOT / "data"
CS = ROOT / "collegesavant"
SIDECAR = DATA / "collegesavant_translation.js"


def _sidecar() -> dict:
    text = SIDECAR.read_text(encoding="utf-8")
    return json.loads(text[text.index("{"):text.rstrip().rstrip(";").rindex("}") + 1])


def _scorecard() -> dict:
    return json.loads((DATA / "college_translation_scorecard.json").read_text(encoding="utf-8"))


def _bridge() -> dict:
    return json.loads((DATA / "collegesavant_milb_equiv.json").read_text(encoding="utf-8"))["by_player_key"]


def test_scorecard_loo_equals_the_eval_on_every_leg():
    ev = json.loads((DATA / "college_translation_eval.json").read_text(encoding="utf-8"))["factors"]
    sc = _scorecard()["legs"]
    assert set(sc) == {k for k in ev if ev[k].get("loo")}
    for k, leg in sc.items():
        loo = ev[k]["loo"]
        assert leg["pairs"] == loo["n"], k
        for a, b in (("mae", "mae"), ("null_mae", "null_mae"), ("skill_se", "skill_se"),
                     ("p10_p90_coverage", "p10_p90_coverage")):
            assert leg[a] == loo[b], (k, a)
        assert leg["spearman"] is None or -1 <= leg["spearman"] <= 1
        for r in leg["leave_one_season_out"]:
            assert r["run"] == (r["n_test"] >= ct.LOSO_MIN_PAIRS and r["n_train"] >= ct.LOSO_MIN_PAIRS)
    # The page reads the same numbers off the sidecar.
    emb = _sidecar()["scorecard"]
    assert {k: emb[k]["mae"] for k in emb} == {k: sc[k]["mae"] for k in sc}


def test_spearman_and_ranks_on_a_fixture():
    assert ct._spearman([1, 2, 3, 4], [10, 20, 30, 40]) == 1.0
    assert ct._spearman([1, 2, 3, 4], [4, 3, 2, 1]) == -1.0
    assert ct._ranks([5, 1, 5, 2]) == [3.5, 1.0, 3.5, 2.0]


def test_receipt_picks_the_fit_label_and_guards_identity():
    v = {"year": 2024}
    rows = [(2026, 25.0, 9.0, 0.700, "x_key", "A+", 40), (2025, 30.0, 8.0, 0.650, "x_key", "A", 50)]
    rec, why = ct.single_a_receipt("hit", v, rows, "x_key")
    assert why is None and (rec["season"], rec["level"], rec["k_pct"]) == (2025, "A", 30.0)
    assert rec["identity"] == "draft_record"
    assert ct.single_a_receipt("hit", v, rows, "other_key") == (None, "draft_record_names_another_player")
    two = rows + [(2025, 20.0, 7.0, 0.6, "y_key", "A", 30)]
    assert ct.single_a_receipt("hit", v, two, None)[1] == "name_matches_several_players"
    assert ct.single_a_receipt("hit", {"year": 2026}, rows, None)[1] == "pro_season_before_college_season"


def test_served_receipts_are_consistent():
    T = _sidecar()["translations"]
    recs = [(s, e) for s, e in T.items() if e.get("actual_single_a")]
    sc = _scorecard()["receipts"]
    assert len([1 for _, e in recs if e["side"] == "hit"]) == sc["hitters"] > 150
    assert len([1 for _, e in recs if e["side"] == "pit"]) == sc["pitchers"] > 150
    for slug, e in recs:
        a = e["actual_single_a"]
        assert a["season"] >= e["source_season"], slug
        assert a["level"] in ("A", "A+"), slug
        assert a["in_fit"] is True and a["identity"] in ("draft_record", "name"), slug
        if a["identity"] == "draft_record":
            assert a["pro_key"] == e["milb_key"], slug
        assert a["held_out"].get("k_pct") is not None, slug


def test_condon_carries_his_keys_and_no_receipt():
    """Condon's only statlines row is AAA, so the fit never paired him: no
    actual line, but his draft and MiLB keys link him to PROSPX."""
    e = _sidecar()["translations"]["condon-charlie"]
    assert e["draft_key"] == "draft_2024_charlie_condon"
    assert e["milb_key"] == "charlie_condon"
    assert "actual_single_a" not in e
    b = _bridge()["draft_2024_charlie_condon"]
    assert b["cs"] == {"slug": "condon-charlie", "year": 2024, "side": "hit", "pool_n": b["cs"]["pool_n"]}
    assert b["cs_plus"] is not None and b["pct"]


# --------------------------------------------------------------------------- #
# The Python CS+ port matches the apps, and the pages render the receipts
# --------------------------------------------------------------------------- #
MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
from test_collegesavant_source_season import _ctx  # noqa: E402


@pytest.mark.parametrize("side", ["hit", "pit"])
def test_bridge_cs_plus_and_percentiles_match_the_page(side):
    keys = {lab: key for key, lab, _hb in ct.KEY_PERCENTILES[side]}
    br = [b for b in _bridge().values() if b.get("cs", {}).get("side") == side and "cs_plus" in b]
    assert len(br) > 50
    if side == "hit":
        ctx = _ctx("app.js", ["data.js", "hitter_year_data.js"])
    else:
        ctx = _ctx("pitcher_app.js", ["pitcher_data.js"])
    bad = []
    for b in br[:120]:
        slug, year = b["cs"]["slug"], b["cs"]["year"]
        got = json.loads(ctx.eval(
            f"setActiveYear({year}); JSON.stringify({{c: state.csPlus.get({slug!r}), "
            f"p: state.percentiles.get({slug!r})}})"))
        if got["c"] != b["cs_plus"]:
            bad.append((slug, "cs+", got["c"], b["cs_plus"]))
        for lab, val in b["pct"].items():
            if (got["p"] or {}).get(keys[lab]) != val:
                bad.append((slug, lab, (got["p"] or {}).get(keys[lab]), val))
    assert not bad, bad[:5]


def _player_html(app, data, find, slug, year, render_fn):
    ctx = _ctx(app, data)
    ctx.eval(f"setActiveYear({year});{render_fn}({find}.find(function(x){{return x.slug==='{slug}';}}));")
    return ctx.eval("__html['app']||''")


def test_hitter_page_prints_the_receipt_and_links():
    T = _sidecar()["translations"]
    slug, e = next((s, e) for s, e in T.items() if e.get("side") == "hit"
                   and (e.get("actual_single_a") or {}).get("identity") == "draft_record")
    html = _player_html("app.js", ["data.js", "hitter_year_data.js"], "state.players", slug,
                        e["source_season"], "renderPlayer")
    a = e["actual_single_a"]
    assert "Actual Single-A" in html
    assert f"{a['k_pct']:.1f}%" in html and "held out" in html
    assert f'href="/prospx/#draft={e["draft_key"]}"' in html and "Open on PROSPX" in html
    assert f'href="/prospx/#player={e["milb_key"]}"' in html


def test_condon_page_links_to_prospx_without_a_receipt():
    html = _player_html("app.js", ["data.js", "hitter_year_data.js"], "state.players", "condon-charlie",
                        2024, "renderPlayer")
    assert "Open on PROSPX" in html and "draft_2024_charlie_condon" in html
    assert "Actual Single-A" not in html


def test_pitcher_page_prints_the_receipt():
    T = _sidecar()["translations"]
    slug, e = next((s, e) for s, e in T.items() if e.get("side") == "pit" and e.get("actual_single_a"))
    html = _player_html("pitcher_app.js", ["pitcher_data.js"], "state.pitchers", slug,
                        e["source_season"], "renderPitcher")
    assert "Actual Single-A" in html and f"{e['actual_single_a']['ip']} IP" in html


def test_what_to_trust_reads_the_scorecard():
    sc = _scorecard()["legs"]
    ctx = _ctx("app.js", ["data.js", "hitter_year_data.js"])
    ctx.eval("setActiveYear(2024);renderProjections();")
    html = ctx.eval("__html['app']||''")
    assert f"rank correlation {sc['hit_k']['spearman']:.2f}" in html
    held = [r for r in sc["hit_k"]["leave_one_season_out"] if r["run"]]
    assert f"{held[0]['season']} MAE {held[0]['mae']:.3f} against {held[0]['null_mae']:.3f}" in html


def test_prospx_draftee_card_wires_the_block():
    src = (ROOT / "prospx" / "index.html").read_text(encoding="utf-8")
    body = src[src.index("async function renderDraftDetail"):src.index("async function renderOverseasDetail")]
    assert "await _loadCsEquiv();" in body
    assert "College tracked (CollegeSavant)" in body
    assert 'html: _collegeTabHtml' in body
    # The 2024 class carries no college_stats, so the block is the tab's content.
    ts = json.loads((DATA / "draft_timeseries.json").read_text(encoding="utf-8"))
    p = next(x for c in ts["classes"] for x in c.get("prospects", [])
             if x["player_key"] == "draft_2024_charlie_condon")
    assert not p.get("college_stats")
    assert "cs" in _bridge()["draft_2024_charlie_condon"]
