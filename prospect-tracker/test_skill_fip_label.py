# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The served `fip` field is Skill FIP, and every surface says so (audit F05-02).

rem_plus.reliever_row and sem_plus.starter_row serve `"fip": fip_skill`: each of
the K, BB, HBP and HR rates shrunk toward the ROLE pool by sample size, plus a
constant solved on that role pool. The number is exactly what REM+ and SEM+ are
built on. The defect was the label: both boards headed it "FIP", the starter
board linked the standard `fip` glossary entry (the FanGraphs formula, no
shrink, one league constant), and the free-agent current-line tile carried it as
"FIP" with a tooltip that asserted the standard statistic. Measured against the
standard formula at the audit, 291 of 505 bullpen rows and 49 of 229 starter
rows sat more than half a run away from it.

The JSON key is NOT renamed: build_site.build_current_lines_payload and
assets/fa.js read it. So the fix is copy on three surfaces plus a glossary entry
that says what the number is, and the real defect, that nothing asserted which
quantity the label names, is closed by the invariants below:

  * both board columns are labelled Skill FIP and link `skill_fip`; nothing on
    the boards links the standard `fip` entry any more, and the rendered header
    says so in the real mlbstats.js;
  * the glossary entry's constants are the code's constants and its worked
    example is recomputed through rem_plus.fip_skill, so the copy cannot drift
    from the model;
  * over the SERVED artifacts, every row's `fip` reproduces its own REM+ / SEM+
    as 100 x pool mean / fip within rounding. That is what makes the label
    true. If someone swaps the field to standard FIP, this fails, and the label
    has to come back through review with it;
  * the current-lines payload lifts the field verbatim and its note names it,
    and the FA tile renders the Skill FIP label and an honest tooltip.

Read-only: nothing here writes to data/.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import rem_plus as RP
import sem_plus as SP

ROOT = Path(__file__).parent
MLBSTATS_JS = ROOT / "assets" / "mlbstats.js"
FA_JS = ROOT / "assets" / "fa.js"
GLOSSARY = ROOT / "data" / "glossary.json"

_DASHES = (chr(0x2014), chr(0x2013))    # em dash, en dash (owner copy rule)


def _js() -> str:
    return MLBSTATS_JS.read_text(encoding="utf-8")


def _column(js: str, array: str, key: str) -> str:
    """The source text of one column object inside a column array."""
    block = js.split(f"var {array} = [")[1].split("\n  ];")[0]
    start = block.index(f'{{ key: "{key}"')
    nxt = block.find("\n    { key:", start + 1)
    return block[start:nxt if nxt > 0 else len(block)]


def _glossary() -> dict:
    return {e["id"]: e for e in
            json.loads(GLOSSARY.read_text(encoding="utf-8"))["entries"]}


# --------------------------------------------------------------------------- #
# the boards
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("array,pool,index", [("REL_COLS", "reliever", "REM+"),
                                              ("STARTER_COLS", "starter", "SEM+")])
def test_board_column_is_labelled_skill_fip_and_links_its_own_entry(array, pool, index):
    col = _column(_js(), array, "fip")
    assert 'label: "Skill FIP"' in col, col
    assert 'term: "skill_fip"' in col, col
    assert 'term: "fip"' not in col, "the standard FIP entry is wired to the skill number"
    assert f'skillFipTitle("{pool}", "{index}")' in col, col


def test_no_board_column_is_headed_plain_fip_or_links_the_standard_entry():
    js = _js()
    assert not re.search(r'label: "FIP"', js), "a column is still headed plain FIP"
    assert 'term: "fip"' not in js, "a column still links the standard FIP entry"


def test_history_boards_inherit_the_relabel():
    """Past-season rows come from the same score_pool, so their `fip` is the
    same skill number. The history boards reuse the live column objects, so the
    relabel reaches them only while `fip` stays in the allow-list and out of
    the drop-list."""
    js = _js()
    rel_keys = js.split("var REL_HISTORY_KEYS =")[1].split(";")[0]
    sp_drop = js.split("var STARTER_HISTORY_DROP =")[1].split(";")[0]
    assert "fip: 1" in rel_keys
    assert "fip" not in sp_drop
    assert "REL_COLS.filter(" in js and "STARTER_COLS.filter(" in js


def test_rendered_headers_name_the_skill_number():
    """The real mlbstats.js, both boards, as the browser paints them. The CSV
    export scrapes these headers from the DOM, so it carries the same label."""
    smoke = pytest.importorskip("test_mlbstats_smoke")
    for html, pool, index in ((smoke._render(""), "reliever", "REM+"),
                              (smoke._render_starters("#section=starters"), "starter", "SEM+")):
        assert 'data-gl="skill_fip">Skill FIP</span>' in html, html[:600]
        assert 'data-gl="fip"' not in html
        assert ">FIP<" not in html
        head = html.split("<thead>")[1].split("</thead>")[0]
        th = head.split('data-col="fip"')[0].rsplit("<th ", 1)[1]
        assert "not the standard FIP" in th, th
        assert f"toward the {pool} pool" in th and f"{index} is built on" in th, th
        assert "undefined" not in html


# --------------------------------------------------------------------------- #
# the glossary entry, pinned to the code
# --------------------------------------------------------------------------- #
def test_skill_fip_entry_is_registered_on_the_right_shelf():
    e = _glossary()["skill_fip"]
    assert e["category"] == "custom-index" and e["shelf"] == "ark"
    assert "mlbstats" in e["module"]
    assert "eephus.io" in e["origin"]
    assert "not the standard FIP" in e["definition"]
    assert "ROLE pool" in e["definition"]
    for ref in ("fip", "rem_plus", "sem_plus"):
        assert ref in e["seeAlso"]


def test_the_standard_entry_and_both_indexes_point_at_it():
    g = _glossary()
    for eid in ("fip", "rem_plus", "sem_plus"):
        assert "skill_fip" in g[eid].get("seeAlso", []), eid
    assert "Skill FIP column is a sample-shrunk version" in g["fip"]["methodology"]


def test_entry_constants_are_the_code_constants():
    """Typed constants in copy drift the day someone tunes the model. These are
    the model's, rebuilt from the module rather than repeated here."""
    assert SP.K_STRIKEOUT is RP.K_STRIKEOUT and SP.K_HOMERUN is RP.K_HOMERUN
    assert (RP.FIP_HR, RP.FIP_BBHBP, RP.FIP_K) == (13.0, 3.0, 2.0)
    e = _glossary()["skill_fip"]
    k = [int(RP.K_STRIKEOUT), int(RP.K_WALK), int(RP.K_HBP), int(RP.K_HOMERUN)]
    assert (f"pseudo-count of {k[0]} batters for strikeouts, {k[1]} for walks, "
            f"{k[2]} for hit batters and {k[3]} for home runs") in e["methodology"]
    assert f"k = {k[0]} (K), {k[1]} (BB), {k[2]} (HBP), {k[3]} (HR)" in e["formula"]
    assert f"relievers with {int(RP.POOL_MIN_TBF)} or more batters faced" in e["methodology"]
    assert f"starters with {int(SP.POOL_MIN_IP)} or more innings" in e["methodology"]
    assert f"reaches the {k[3]} batters the home-run term needs" in e["methodology"]


def _example_reliever(tbf, ip, so, bb):
    pool = RP.Pool()
    pool.mean_k_pct, pool.mean_bb_pct = 0.22, 0.09
    pool.mean_hbp_pct, pool.mean_hr_rate, pool.cfip = 0.01, 0.025, 3.10
    r = RP.Reliever(key="example", ip=ip, tbf=tbf, so=so, bb=bb, hbp=0, hr=0)
    unshrunk = (RP.FIP_HR * 0 + RP.FIP_BBHBP * bb - RP.FIP_K * so) / ip + pool.cfip
    return unshrunk, RP.fip_skill(r, pool)


def test_worked_example_is_recomputed_through_the_model():
    ex = _glossary()["skill_fip"]["example"]
    raw60, skill60 = _example_reliever(60, 15.0, 24, 3)
    _, skill240 = _example_reliever(240, 60.0, 96, 12)
    assert f"unshrunk FIP of {raw60:.2f}" in ex, (raw60, ex)
    assert f"Skill FIP of {skill60:.2f}" in ex, (skill60, ex)
    assert f"read {skill240:.2f}" in ex, (skill240, ex)
    assert raw60 < skill240 < skill60      # more sample, less pull, never all the way


def test_the_floor_the_entry_states_is_the_floor_the_model_applies():
    assert "floored at 1.00" in _glossary()["skill_fip"]["methodology"]
    pool = RP.Pool()
    ace = RP.Reliever(key="x", ip=30.0, tbf=400, so=260, bb=0, hbp=0, hr=0)
    assert RP.fip_skill(ace, pool) == 1.0


# --------------------------------------------------------------------------- #
# the served artifacts: the label is true only while this holds
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("fname,key,raw_key", [
    ("bullpen_leaderboards.json", "relievers", "rem_plus_raw"),
    ("starter_leaderboards.json", "starters", "sem_plus_raw")])
def test_served_fip_is_the_index_denominator(fname, key, raw_key):
    """REM+ and SEM+ are 100 x pool mean skill FIP / the pitcher's skill FIP.
    Every served row's `fip` must reproduce its own index from the rounded
    fields: raw index to 0.1, pool mean and fip to 0.01, so the bound is the
    first-order rounding error of 100 x m / f plus half a display step."""
    path = ROOT / "data" / fname
    if not path.exists():
        pytest.skip(f"{fname} not built")
    d = json.loads(path.read_text(encoding="utf-8"))
    rows = [r for r in d.get(key) or [] if r.get("fip") is not None
            and r.get(raw_key) is not None]
    if not rows:
        pytest.skip(f"{fname} carries no scored rows")
    m = d["pool"]["mean_fip"]
    bad = []
    for r in rows:
        f = r["fip"]
        assert f >= 1.0, f"{r.get('name')}: fip {f} under the model's 1.00 floor"
        tol = 100.0 * (0.005 / f + m * 0.005 / f ** 2) + 0.05 + 1e-9
        if abs(100.0 * m / f - r[raw_key]) > tol:
            bad.append((r.get("name"), f, r[raw_key]))
    assert not bad, (f"{len(bad)} of {len(rows)} rows serve a `fip` that is not "
                     f"the {raw_key} denominator, so 'Skill FIP' would be false: {bad[:5]}")


def test_current_lines_lift_the_field_verbatim_and_name_it(monkeypatch):
    import build_site as B
    boards = {
        "hitter_leaderboards.json": {"season": 2026, "as_of": "2026-09-10", "hitters": []},
        "starter_leaderboards.json": {"season": 2026, "starters": [
            {"mlbam": 1, "team": "NYY", "ip": 120.0, "fip": 3.41, "sem_plus": 118,
             "qualified": True}]},
        "bullpen_leaderboards.json": {"relievers": [
            {"mlbam": 2, "team": "BOS", "ip": 40.0, "fip": 2.97, "rem_plus": 131,
             "qualified": False}]},
    }
    monkeypatch.setattr(B, "_cached_data_json", lambda name: boards.get(name, {}))
    out = B.build_current_lines_payload()
    assert out["players"]["1"]["fip"] == 3.41 and out["players"]["1"]["side"] == "sp"
    assert out["players"]["2"]["fip"] == 2.97 and out["players"]["2"]["side"] == "rp"
    note = out["note"]
    assert "The fip field is Skill FIP" in note and "not the standard FIP" in note
    assert "FIP / SEM+ / REM+" not in note, "the note names the skill number plain FIP again"
    assert "derives no wRC+" in note        # the sibling disclosure is untouched


def test_catalog_says_what_the_key_holds():
    import data_catalog as dc
    by = {a["file"]: a for a in dc.ARTIFACTS}
    for fname, index in (("bullpen_leaderboards.json", "REM+"),
                         ("starter_leaderboards.json", "SEM+")):
        note = by[fname]["note"]
        assert "`fip` is Skill FIP" in note and "not the standard FIP" in note, fname
        assert index in note, fname


# --------------------------------------------------------------------------- #
# the free-agent current-line tile (assets/fa.js)
# --------------------------------------------------------------------------- #
def _fa_tile(line: dict) -> str:
    MiniRacer = pytest.importorskip("py_mini_racer").MiniRacer
    src = FA_JS.read_text(encoding="utf-8")
    esc = src[src.index("  function esc(s) {"):]
    esc = esc[:esc.index("\n  }\n") + 4]
    fn = src[src.index("  function currentLineHTML(line, meta) {"):
             src.index("  function fillCurrentLine(")]
    ctx = MiniRacer()
    ctx.eval(esc + fn)
    return ctx.eval("currentLineHTML(%s, %s)" % (
        json.dumps(line), json.dumps({"season": 2026, "asOf": "2026-09-10"})))


@pytest.mark.parametrize("side,index,pool", [("sp", "SEM+", "starter"),
                                             ("rp", "REM+", "reliever")])
def test_fa_tile_names_the_skill_number(side, index, pool):
    html = _fa_tile({"side": side, "ip": 41.0, "era": 3.10, "fip": 3.55,
                     "kPct": 0.27, "bbPct": 0.08, "sem": 112, "rem": 112,
                     "qual": False})
    assert ">Skill FIP</span>" in html and ">3.55</span>" in html, html
    assert ">FIP</span>" not in html
    assert "FIP - this site does not compute xFIP." not in html, "the old tooltip asserted the standard stat"
    tip = html.split(">Skill FIP</span>")[0].rsplit('title="', 1)[1]
    assert f"{index} is built on" in tip and f"toward the {pool} pool" in tip, tip
    assert "not the standard FIP" in tip, tip
    assert f"100 = the average {pool}" in html
    assert "100 = league average" not in html
    # below the threshold: K%, BB% and ERA are raw; only the skill numbers shrink
    assert "shrunk toward league average" not in html
    assert "raw line" in html and f"shrunk toward the {pool}" in html


def test_fa_tile_hitter_branch_is_untouched():
    html = _fa_tile({"side": "hit", "pa": 300, "hem": 110, "avg": 0.27,
                     "obp": 0.34, "slg": 0.45, "woba": 0.34, "hr": 12})
    assert "HEM+" in html and "Skill FIP" not in html


# --------------------------------------------------------------------------- #
# copy rule
# --------------------------------------------------------------------------- #
def test_no_em_or_en_dashes_in_the_touched_copy():
    for p in (MLBSTATS_JS, FA_JS, ROOT / "build_site.py", ROOT / "data_catalog.py",
              ROOT / "rem_plus.py", ROOT / "sem_plus.py"):
        txt = p.read_text(encoding="utf-8")
        for ch in _DASHES:
            assert ch not in txt, f"{p.name} carries {ch!r}"
    blob = json.dumps(_glossary()["skill_fip"], ensure_ascii=False)
    assert not any(ch in blob for ch in _DASHES)
