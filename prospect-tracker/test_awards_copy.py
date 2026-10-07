"""awards_core.py: the copy rules on every label builder (AWARDS_2_RULES_CORE; AWARDS_PLAN
5.15 'Copy and credits' and 6 'Invariants and tests' row I12, the payload part).

Every string a card can print is built in awards_core from fields; this file runs every
builder on two providers and two seasons and checks no em or en dash, no tools/copy_lint.py
BAN hit, none of the plan's verdict words and no "luck" reaches a payload string, that every
WAR unit label and the 'does not claim' line (5) name their block's war_provider, and that
no WAR unit label is a typed constant outside the one map. No test opens a socket.
"""
from __future__ import annotations

import ast
import json
import re
import socket
import sys
from pathlib import Path

import pytest

import awards_core as A

ROOT = Path(__file__).resolve().parent
FIX = ROOT / "test_fixtures" / "awards" / "core"
sys.path.insert(0, str(ROOT / "tools"))
import copy_lint  # noqa: E402

DASHES = re.compile("[" + chr(0x2013) + chr(0x2014) + "]")
#: An independent grep of the plan's list, so the scan does not rest on awards_core alone.
VERDICT = re.compile(
    r"\b(snub\w*|robbed|deserv\w*|undeserving|should have won|wrong|correct\w*|right call|mistake|"
    r"lock|shoo-in|frontrunner|favou?rite|clear winner|runaway|unworthy|worthy|overrated|underrated|"
    r"over(performer|achiever)|under(performer|achiever)|breakout|bust|disappointment|luck\w*|"
    r"unlucky|clutch|choke|best player|predict\w*|projected winner|odds|chance to win|pick|"
    r"regress\w*|trending|sleeper)\b", re.IGNORECASE)


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def _refuse(*a, **k):
        raise AssertionError("an awards copy test opened a socket")
    monkeypatch.setattr(socket, "socket", _refuse)
    monkeypatch.setattr(socket, "create_connection", _refuse)


def _strings(obj):
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for k, v in obj.items():
            yield from _strings(k)
            yield from _strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from _strings(v)


def _clean(obj, where: str) -> None:
    for s in _strings(obj):
        assert not DASHES.search(s), f"{where}: dash in {s!r}"
        assert not copy_lint.BAN_RE.search(s), f"{where}: banned word in {s!r}"
        assert not VERDICT.search(s), f"{where}: verdict word in {s!r}"
        assert "luck" not in s.lower(), f"{where}: {s!r}"
        assert A.verdict_hits(s) == [], f"{where}: {s!r}"


def _load(name: str):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def ballots():
    rows = A.league_split({"bat": _load("stint_bat_2026.json"), "pit": _load("stint_pit_2026.json")},
                          season=2026, war_provider="ewar_v2")
    wpa = {int(k): v for k, v in _load("wpa_2026.json").items()}
    out = {}
    for lg in A.LEAGUES:
        out[("MVP", lg)] = A.mvp_ballot(rows, lg, 2026, wpa=wpa)
        out[("CY", lg)] = A.cy_young_ballot(rows, lg, 2026)
        out[("ROY", lg)] = A.rookie_ballot(rows, lg, 2026, rookies=_load("rookies_2026.json"), wpa=wpa)
        out[("MOY", lg)] = A.manager_ballot(_load("standings_2026.json")["clubs"],
                                            _load("team_outlook_2026.json")["team_outlook"],
                                            _load("board_2026.json")["teams"], lg, 2026,
                                            war_provider="ewar_v2")
    return out


# --- every label builder, clean -----------------------------------------------------------

def test_every_rules_label_is_clean_on_both_providers_and_a_short_season():
    for award in A.AWARDS:
        for season in (2026, 2020):
            for prov in ("ewar_v2", "ewar_v3"):
                block = A.rules_block(award, season, prov)
                _clean(block, f"rules_block({award}, {season}, {prov})")
                assert block["label"].endswith("Not a forecast of the BBWAA vote.")
                assert block["label"].startswith("The eephus selection by ")
                _clean(A.two_way_label(award, prov), "two_way_label")
            _clean(A.floor_label(award, season), "floor_label")
        _clean(A.tie_label(award), "tie_label")
        _clean(A.eligibility_label(award), "eligibility_label")
    _clean(A.rookie_gates_label(), "rookie_gates_label")
    assert "130" in A.rookie_gates_label() and "50" in A.rookie_gates_label() and "45" in A.rookie_gates_label()
    assert "45-day" in A.eligibility_label("ROY") and "estimate" in A.eligibility_label("ROY")
    assert A.eligibility_label("MVP") is None and A.two_way_label("MOY", "ewar_v2") is None
    assert A.two_way_label("CY", "ewar_v2") == "Pitching side only."


def test_ballot_sentences_and_rows_are_clean(ballots):
    for key, b in ballots.items():
        _clean(b, f"ballot {key}")
        assert b["lead"] is not None
        for r in b["top"]:
            if r.get("share"):
                _clean(A.split_label(r, "ewar_v2"), "split_label")
        for e in b["excluded"]:
            _clean(A.excluded_label(e), "excluded_label")
    _clean(A.selection_caption(2026, frozen=True), "caption")
    _clean(A.selection_caption(2026, frozen=False), "caption")
    assert A.selection_caption(2026, frozen=False) == "Current leaders on the rule, 2026"
    assert A.selection_caption(2026, frozen=True) == "The eephus selection, 1st place, 2026"
    _clean(A.drift_tooltip("2026-09-28"), "drift_tooltip")


def test_superlative_titles_definitions_and_blocks_are_clean():
    assert len(A.SL_TITLES) == 11 and tuple(A.SL_TITLES) == A.SL_IDS
    assert set(A.SL_TITLES) == {"prospect_above", "prospect_below", "proj_above", "proj_below",
                                "next_rise", "next_drop", "glove", "contact_ahead", "results_ahead",
                                "relief", "pitching_changes"}
    for sl_id in A.SL_IDS:
        _clean(A.sl_title(sl_id, 2026), f"title {sl_id}")
    assert A.sl_title("next_rise", 2026) == "Largest projected rise for 2027"
    with pytest.raises(ValueError):
        A.sl_title("next_drop")
    frames = {"lv_first": 2020, "vm_first": 2025}
    prow = [{"mlbam": 1, "name": "A", "club_code": "BOS", "player_key": "a", "debut_season": 2017,
             "efv_at_debut": 20.0, "war": 4.0, "pa": 600, "ip": 0}]
    nrow = [{"mlbam": 1, "name": "A", "club_code": "BOS", "war_realized": 1.0, "war_next": 2.0,
             "pa": 600, "ip": 0}]
    hit = [{"mlbam": 1, "name": "A", "team": "PHI", "pa": 600, "luck_gap": 0.04, "xwoba": 0.38, "woba": 0.34}]
    fld = [{"mlbam": 1, "name": "A", "team": "DET", "pos": "C", "inn": 900.0, "qualified": True,
            "dem_plus": 130, "dem_plus_raw": 130.1, "def_runs": 20.0}]
    rel = [{"mlbam": 1, "name": "A", "team": "SD", "rem_plus": 190, "rem_plus_raw": 190.2, "qualified": True,
            "ip": 70.0, "gmli": 1.9, "wpa": 5.0, "saves": 30}]
    clubs = [{"club": "TBR", "season": 2026, "n_pitching_change": 500, "mwpa_pitching_change": 8.0}]
    blocks = [
        A.prospect_above(prow, 2026, war_provider="ewar_v2", frames=frames),
        A.prospect_below(prow, 2026, war_provider="ewar_v3", frames=frames),
        A.proj_above(nrow, 2026, war_provider="ewar_v2"),
        A.proj_below(nrow, 2027, war_provider="ewar_v2"),
        A.next_rise(nrow, 2026, bundle_provider="ewar_v2", realized_provider="ewar_v2"),
        A.next_drop(nrow, 2026, bundle_provider="ewar_v3", realized_provider="ewar_v3"),
        A.glove(fld, 2026), A.contact_ahead(hit, 2026), A.results_ahead(hit, 2026),
        A.relief(rel, 2026), A.pitching_changes(clubs, 2026),
    ]
    for b in blocks:
        _clean(b, f"superlative {b['id']}")
        assert b["title"] and b["definition"] and b["floor_label"] and b["frame_label"]
        assert b["producer"] and b["registry"]
    assert blocks[7]["rows"][0]["xwoba_minus_woba"] == 0.04
    _clean(A.prospect_frame_label(frames), "prospect_frame_label")
    assert "2020" in A.prospect_frame_label(frames) and "2025" in A.prospect_frame_label(frames)


def test_does_not_claim_and_credits_are_clean():
    lines = A.does_not_claim_lines("ewar_v2")
    assert len(lines) == 7
    _clean(lines, "does_not_claim_lines")
    _clean(A.does_not_claim_lines("ewar_v2", frozen_at="2026-09-28", now_provider="ewar_v3"), "line 5")
    credits = A.credit_lines({"mlb", "bref", "fangraphs", "savant", "eephus"},
                             mlb_copyright="Copyright 2026 MLB Advanced Media, L.P.")
    assert len(credits) == 5 and credits[0].endswith("Copyright 2026 MLB Advanced Media, L.P.")
    _clean(credits, "credits")
    assert A.credit_lines({"eephus"}) == [A.CREDIT_LINES["eephus"]]
    assert A.credit_lines(set()) == []
    assert "45-day" in lines[2]


# --- the provider case: frozen on eWAR v2, live on eWAR v3 -----------------------------------

def test_every_war_unit_label_names_its_blocks_provider(ballots):
    frozen = {award: A.rules_block(award, 2026, "ewar_v2") for award in A.AWARDS}
    live = {award: A.rules_block(award, 2026, "ewar_v3") for award in A.AWARDS}
    for award in ("MVP", "CY", "ROY"):
        f, l = frozen[award], live[award]
        assert f["unit"] == "eWAR v2" and f["war_provider"] == "ewar_v2"
        assert l["unit"] == "eWAR v3" and l["war_provider"] == "ewar_v3"
        for key in ("label", "two_way_label"):
            if f[key] is None or (award == "CY" and key == "two_way_label"):
                continue        # 'Pitching side only.' prints no unit
            assert "eWAR v2" in f[key] and "eWAR v3" not in f[key], (award, key)
            assert "eWAR v3" in l[key] and "eWAR v2" not in l[key], (award, key)
    assert frozen["MOY"]["unit"] == "wins" and "eWAR v2" in frozen["MOY"]["label"]
    assert "eWAR v3" in live["MOY"]["label"]
    assert A.drift_unit_label("ewar_v3") == "Now, eWAR v3"
    assert A.drift_unit_label("ewar_v2") == "Now, eWAR v2"
    line5 = A.does_not_claim_lines("ewar_v2", frozen_at="2026-09-28", now_provider="ewar_v3")[4]
    assert line5 == "The selection reads eWAR v2, as frozen 2026-09-28; Now values read eWAR v3."
    assert A.does_not_claim_lines("ewar_v3")[4] == "The selection reads eWAR v3 on today's files."
    assert A.does_not_claim_lines("ewar_v2", frozen_at="2026-09-28")[4] == (
        "The selection reads eWAR v2, as frozen 2026-09-28.")
    top = ballots[("MVP", "AL")]["top"]
    assert A.lead_sentence("MVP", top, "ewar_v2").endswith(" eWAR v2.")
    assert A.lead_sentence("MVP", top, "ewar_v3").endswith(" eWAR v3.")
    skubal = next(r for r in ballots[("CY", "AL")]["top"] if r.get("share"))
    assert A.split_label(skubal, "ewar_v3").count("eWAR v3") == 2
    nrow = [{"mlbam": 1, "name": "A", "club_code": "BOS", "war_realized": 1.0, "war_next": 2.0,
             "pa": 600, "ip": 0}]
    live_next = A.next_rise(nrow, 2026, bundle_provider="ewar_v3", realized_provider="ewar_v3")
    assert live_next["war_provider"] == "ewar_v3" and "eWAR v3" in live_next["definition"]
    assert "eWAR v2" not in json.dumps(live_next)
    prow = [{"mlbam": 1, "name": "A", "club_code": "BOS", "player_key": "a", "debut_season": 2017,
             "efv_at_debut": 40.0, "war": 4.0, "pa": 600, "ip": 0}]
    frozen_sl = A.prospect_above(prow, 2026, war_provider="ewar_v2", frames={"lv_first": 2020, "vm_first": 2025})
    assert frozen_sl["war_provider"] == "ewar_v2" and "eWAR v2" in frozen_sl["definition"]
    assert A.war_unit_label("fwar") == "fWAR" and A.war_unit_label("bwar") == "bWAR"
    assert A.war_unit_label("some_new_series") == "WAR (some_new_series)"


def _docstring_nodes(tree: ast.AST) -> set:
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            body = getattr(node, "body", [])
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                out.add(id(body[0].value))
    return out


def test_no_war_unit_label_is_a_typed_constant_outside_the_one_map():
    src = (ROOT / "awards_core.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    docs = _docstring_nodes(tree)
    allowed = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "WAR_UNIT_LABELS" for t in node.targets):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Constant):
                    allowed.add(id(sub))
    assert allowed, "WAR_UNIT_LABELS is the one map"
    unit = re.compile(r"eWAR v\d|\bfWAR\b|\bbWAR\b")
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and unit.search(node.value):
            if id(node) in allowed or id(node) in docs:
                continue
            offenders.append((node.lineno, node.value))
    assert offenders == [], offenders
    # every builder that prints a unit takes the provider
    for name in ("rule_label", "two_way_label", "split_label", "lead_sentence", "drift_unit_label",
                 "does_not_claim_lines", "rules_block"):
        assert callable(getattr(A, name))


def test_module_strings_are_clean_outside_the_verdict_list():
    src = (ROOT / "awards_core.py").read_text(encoding="utf-8")
    assert not DASHES.search(src)
    tree = ast.parse(src)
    verdict_list = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "VERDICT_WORDS" for t in node.targets):
            for sub in ast.walk(node.value):
                if isinstance(sub, ast.Constant):
                    verdict_list.add(id(sub))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in verdict_list:
            hits = A.verdict_hits(node.value)
            if hits:
                offenders.append((node.lineno, hits, node.value[:60]))
    assert offenders == [], offenders


def test_verdict_hits_finds_the_plan_words_the_ban_list_and_dashes():
    assert A.verdict_hits("a clean sentence about the rule") == []
    assert A.verdict_hits("he was " + "sn" + "ubbed") == ["verdict:snubbed"]
    assert A.verdict_hits("a " + "lo" + "ck for the award") == ["verdict:lock"]
    assert A.verdict_hits("the " + "chance to " + "win") == ["verdict:chance to win"]
    assert A.verdict_hits("a " + "rob" + "ust model") == ["ban:" + "rob" + "ust"]
    assert A.verdict_hits("a" + chr(0x2014) + "b") == ["dash:em"]
    assert A.verdict_hits("a" + chr(0x2013) + "b") == ["dash:en"]
    assert A.verdict_hits({"k": ["x", "the " + "pi" + "ck"]}) == ["verdict:pick"]
    assert A.verdict_hits("blocked and locked") == []            # whole words only
    assert A.verdict_hits("xwoba_minus_woba") == []
    assert len(A.VERDICT_WORDS) == 45


# --- the page strings (AWARDS_7_PAGE_SELECTIONS) ---------------------------------------------

def test_the_page_strings_are_clean():
    """assets/awards.js, assets/awards.css and the My Ballot chunk and stylesheet (AWARDS_9)
    whole (comments included), the /awards/ shell's
    body, its sub line and its meta description: no dash, no BAN word, no verdict word and
    no 'luck'. The /hof/ shelf's own copy is outside this page."""
    import build_site as B

    out = B.build_awards(live=True)
    i = out.index('<div class="fa-app mlbstats-app aw-app">')
    j = out.index('<link rel="stylesheet" href="/assets/awards.css')
    texts = {
        "assets/awards.js": (ROOT / "assets" / "awards.js").read_text(encoding="utf-8"),
        "assets/awards.css": (ROOT / "assets" / "awards.css").read_text(encoding="utf-8"),
        "assets/awards-ballot.js": (ROOT / "assets" / "awards-ballot.js").read_text(encoding="utf-8"),
        "assets/awards-ballot.css": (ROOT / "assets" / "awards-ballot.css").read_text(encoding="utf-8"),
        "the /awards/ shell": out[i:j],
        "sub line": B._AWARDS_SUB, "meta description": B._AWARDS_DESCRIPTION,
    }
    for where, text in texts.items():
        _clean(text, where)
    assert "Not a forecast of the writers' vote." in B._AWARDS_SUB
    assert B._AWARDS_DESCRIPTION.endswith("Not a forecast of the vote.")
