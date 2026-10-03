"""data/prospx_leaderboard.json, the PROSPX Leaderboards data file (PROSPX_1_LB_DATA).

Reads the served artifact and never writes data/ (the pytest-revert trap: the file is
a nightly product, rewritten by run_monthly step d9d). A missing artifact skips.

What is pinned:
  * the shape the condensed table reads, and no MLB row anywhere;
  * every combined "MiLB" row is the sum of its level rows;
  * OBP from the components equals the served career row's OBP wherever both
    describe the same sample;
  * Season FIP uses the window engine's constant and formula, K-BB% is SO-BB over BF;
  * the current season's level norms are the served ones, and the level indexes
    (OPS+ lvl, ERA- lvl) equal the served statline values;
  * the JS bodies the current-season model indexes mirror (RPS+, POW+, PD+, pStuff+)
    hash to the values they had when the mirror was verified against the browser
    (20,114 of 20,114 values equal on 2026-10-02), so an edit to either side fails
    here instead of drifting;
  * the gzip size, with a 15% ceiling.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import random
import re
from collections import defaultdict
from pathlib import Path

import pytest

from conftest import load_data_doc
import prospx_leaderboard_export as X

HERE = Path(__file__).parent
PROSPX = HERE / "prospx" / "index.html"
LEVELS = set(X.LEVEL_ORDER)

# Measured 2026-10-02 on the first build: 34,022 rows, 4,553 players, 2021-2026.
MEASURED_GZIP_BYTES = 1_224_888
GZIP_CEILING = int(MEASURED_GZIP_BYTES * 1.15)


@pytest.fixture(scope="module")
def doc():
    d = load_data_doc("prospx_leaderboard.json")
    if not d:
        pytest.skip("data/prospx_leaderboard.json not built (run prospx_leaderboard_export.py)")
    return d


@pytest.fixture(scope="module")
def boot():
    d = load_data_doc("timeseries.json")
    if not d:
        pytest.skip("data/timeseries.json not built")
    return d


def _index(doc):
    return {(r["k"], r["s"], r["lvl"], r["side"]): r for r in doc["rows"]}


# ---------------------------------------------------------------------------
# Shape
# ---------------------------------------------------------------------------

def test_schema(doc):
    for key in ("generated_at", "current_season", "seasons", "basis", "team_games",
                "level_norms", "rows", "current"):
        assert key in doc, key
    assert doc["seasons"] == sorted(doc["seasons"]) and doc["seasons"][0] >= X.FIRST_SEASON
    assert doc["current_season"] == doc["seasons"][-1]
    assert doc["basis"]["fip_constant"] == X.FIP_CONSTANT
    assert doc["basis"]["qualifier"]["pa_per_team_game"] == 2.7
    assert doc["basis"]["qualifier"]["ip_per_team_game"] == 0.8
    for s in doc["seasons"]:
        tg = doc["team_games"][str(s)]
        assert set(tg) <= LEVELS and all(isinstance(n, int) and n > 0 for n in tg.values())
        assert set(doc["level_norms"][str(s)]) <= LEVELS
    hit = set(X._HIT_FIELDS)
    pit = set(X._PIT_FIELDS)
    for r in doc["rows"]:
        assert r["side"] in ("hit", "pit")
        assert r["s"] in doc["seasons"]
        assert isinstance(r["k"], str) and r["k"]
        need = hit if r["side"] == "hit" else pit
        missing = need - set(r)
        assert not missing, (r["k"], r["s"], r["lvl"], missing)
        assert all(isinstance(r[f], int) and r[f] >= 0 for f in need), r
        if r["lvl"] == "MiLB":
            assert r["lvls"] and set(r["lvls"]) <= LEVELS
    for pk, rec in doc["current"].items():
        assert set(rec) <= {"statcast", "zone", "indexes"}
        assert set(rec.get("statcast", {})) <= LEVELS
        assert set(rec.get("zone", {})) <= LEVELS
        assert set(rec.get("indexes", {})) <= {"rps_plus", "pow_plus", "pd_plus", "sc_plus",
                                                "dvm_plus", "pstuff_plus", "krp_plus"}


def test_no_mlb_rows(doc):
    lv = {r["lvl"] for r in doc["rows"]}
    assert "MLB" not in lv
    assert lv <= LEVELS | {"MiLB"}
    assert not any("MLB" in r.get("lvls", []) for r in doc["rows"])


def test_every_player_season_has_one_milb_row(doc):
    levels = defaultdict(list)
    combined = defaultdict(int)
    for r in doc["rows"]:
        key = (r["k"], r["s"], r["side"])
        if r["lvl"] == "MiLB":
            combined[key] += 1
        else:
            levels[key].append(r["lvl"])
    assert set(levels) == set(combined)
    assert set(combined.values()) == {1}


# ---------------------------------------------------------------------------
# Combined rows
# ---------------------------------------------------------------------------

def test_combined_rows_sum_their_level_rows(doc):
    by = defaultdict(list)
    comb = {}
    for r in doc["rows"]:
        key = (r["k"], r["s"], r["side"])
        if r["lvl"] == "MiLB":
            comb[key] = r
        else:
            by[key].append(r)
    multi = sorted(k for k, v in by.items() if len(v) > 1)
    sample = random.Random(20261002).sample(multi, 20)
    for key in sample:
        c, parts = comb[key], by[key]
        fields = X._HIT_FIELDS if key[2] == "hit" else X._PIT_FIELDS
        for f in fields:
            assert c[f] == sum(p[f] for p in parts), (key, f)
        assert c["lvls"] == sorted((p["lvl"] for p in parts), key=X.LEVEL_ORDER.index)
    # Every combined row, not only the sample, carries its levels' exposure.
    for key, c in comb.items():
        expo = "pa" if key[2] == "hit" else "outs"
        assert c[expo] == sum(p[expo] for p in by[key]), key


# ---------------------------------------------------------------------------
# Agreement with the served rows
# ---------------------------------------------------------------------------

def test_obp_from_components_matches_the_served_rows(doc, boot):
    """Within 0.0005 (the API's three-decimal half-up string) wherever the served
    career row and the export describe the same sample (equal AB). A served row with
    a different AB is a frozen line: measured 2026-10-02, 9 of 9,244 joined rows
    (career rows last fetched in May for six board keys), so the count is capped."""
    idx = _index(doc)
    joined = same = 0
    frozen = []
    for p in boot["players"]:
        for c in p.get("career_stats") or []:
            if c.get("is_pitcher") or c.get("level") == "MLB":
                continue
            r = idx.get((p["player_key"], c.get("season"), c.get("level"), "hit"))
            if not r:
                continue
            try:
                served = float(c["obp"])
            except (KeyError, TypeError, ValueError):
                continue
            den = r["ab"] + r["bb"] + r["hbp"] + r["sf"]
            if not den:
                continue
            joined += 1
            obp = (r["h"] + r["bb"] + r["hbp"]) / den
            if c.get("ab") != r["ab"]:
                frozen.append((p["player_key"], c["season"], c["level"]))
                continue
            same += 1
            assert abs(obp - served) <= 0.0005 + 1e-9, (p["player_key"], c["season"],
                                                         c["level"], served, obp)
    assert same > 5000
    assert len(frozen) <= max(20, joined // 500), frozen[:20]


def test_current_season_norms_are_the_served_norms(doc, boot):
    cs = str(doc["current_season"])
    served = boot["level_norms"]
    for lvl, rec in doc["level_norms"][cs].items():
        perf = (served.get(lvl) or {}).get("perf") or {}
        for k, v in rec.items():
            if k in perf:
                assert v == perf[k], (lvl, k, v, perf[k])


def test_level_indexes_equal_the_served_statline_values(doc, boot):
    """OPS+ lvl (served wrc_plus_level) and ERA- lvl (served era_minus_level) on the
    current season's level rows. Excluded: a hitter with both a DSL and a complex
    league line that season. The served chip reads milb_history's sport-16 line, which
    the StatsAPI lumps across the two leagues; the export requests each league on its
    own (31 rows measured 2026-10-02)."""
    idx = _index(doc)
    cs = doc["current_season"]
    split16 = {r["k"] for r in doc["rows"]
               if r["s"] == cs and r["lvl"] == "MiLB" and {"DSL", "CPX"} <= set(r["lvls"])}
    n_hit = n_pit = 0
    for p in boot["players"]:
        for sl in p.get("current_season_statlines") or []:
            if sl.get("season") != cs:
                continue
            if sl.get("is_pitcher"):
                r = idx.get((p["player_key"], cs, sl.get("level"), "pit"))
                if not r or r["bf"] != sl.get("tbf"):
                    continue
                n_pit += 1
                assert r.get("era_minus_lvl") == sl.get("era_minus_level"), (p["player_key"], sl.get("level"))
            else:
                r = idx.get((p["player_key"], cs, sl.get("level"), "hit"))
                if not r or r["ab"] != sl.get("ab") or p["player_key"] in split16:
                    continue
                if sl.get("wrc_plus_level") is None:
                    continue
                n_hit += 1
                assert r.get("ops_plus_lvl") == sl["wrc_plus_level"], (p["player_key"], sl.get("level"))
    assert n_hit > 2000 and n_pit > 2000


def test_fip_and_kbb_on_every_pitcher_row(doc):
    n = 0
    for r in doc["rows"]:
        if r["side"] != "pit":
            continue
        if r["outs"] > 0:
            n += 1
            want = round((13 * r["hr"] + 3 * (r["bb"] + r["hbp"]) - 2 * r["so"])
                         / (r["outs"] / 3.0) + 3.10, 2)
            assert r.get("fip") == want, (r["k"], r["s"], r["lvl"])
        if r["bf"] > 0:
            assert r.get("kbb") == round(100.0 * (r["so"] - r["bb"]) / r["bf"], 1)
    assert n > 5000


def test_fip_constant_is_the_window_engines():
    src = PROSPX.read_text(encoding="utf-8")
    m = re.search(r"const _LB_FIP_CONST = ([0-9.]+);", src)
    assert m and float(m.group(1)) == X.FIP_CONSTANT


def test_era_minus_reads_the_apis_half_up_era():
    # 31 ER in 40 IP: the API prints 6.98 (half up); float round gives 6.97.
    assert X.era_minus_lvl(31, 120, 4.25, 50.0) == round(
        ((40.0 * 6.98 + 50.0 * 4.25) / 90.0) / 4.25 * 100)


def test_js_round_is_half_up():
    assert X._js_round(2.5) == 3 and X._js_round(-2.5) == -2 and X._js_round(0.49) == 0


# ---------------------------------------------------------------------------
# The mirrored board code
# ---------------------------------------------------------------------------

# name -> sha256[:16] of the body with // comments and all whitespace removed.
_MIRRORED = {
    "function computeRelProd": "7c6d52906a8ad097",
    "function _buildRpsPlusCache": "4722a49b4c89c0a3",
    "function _rpsAgeBucket": "6a379ea7f4ca8e8c",
    "function _rpsPositionGroup": "01cff7983b6a6097",
    "function _rpsPositionMultiplier": "0664769f9b7f7891",
    "const _RPS_POSITION_MULTIPLIERS": "c8b22b202fd63367",
    "function cohortPosition": "ba8d5819c66b8dd5",
    "function positionBucket": "e6bbd38197e12bf4",
    "function _lvlPlus": "2112f20db2b936c2",
    "function _clampPlus": "ef67cfadcd5a5f1d",
    "function _toolToPlus": "83b5093672e1d6f8",
    "function _blendPlus": "68a349a39f2875c7",
    "function _blendPlus3Rel": "d8d61c17ffaaee02",
    "const PLUS_STABILIZE": "d9b5e80cf66689fd",
    "function _isoPlusRaw": "b35e9eb25c51a1e9",
    "function computeIsoPlus": "36ff6e90fec508a0",
    "function _ebShrinkPlus": "f1c6565390ba4997",
    "function _pwrToolGrade": "50b37a29098ac1da",
    "function _statcastPowerPlus": "713544405b5d44fd",
    "function computePowerPlus": "f5b93de6694b3b52",
    "function _pdSigmas": "98eedf13cd3bed92",
    "function _disciplinePlusRaw": "d561f013307d3635",
    "function computeDisciplinePlus": "bdbdd0f355cc3ad9",
    "function computeStuffPlus": "c7c58a8639221668",
    "function getStatcastPlus": "914033a10ca023ca",
    "function _lbFip": "3b4bb422601a6d1c",
}


def _js_block(src: str, head: str) -> str:
    i = src.index(head + (" =" if head.startswith("const ") else "("))
    j = src.index("{", i)
    depth = 0
    for k in range(j, len(src)):
        if src[k] == "{":
            depth += 1
        elif src[k] == "}":
            depth -= 1
            if depth == 0:
                return src[i:k + 1]
    raise AssertionError(head)


def _norm(block: str) -> str:
    block = re.sub(r"(^|[^:])//[^\n]*", r"\1", block)
    return re.sub(r"\s+", "", block)


def js_pins() -> dict:
    src = PROSPX.read_text(encoding="utf-8")
    return {h: hashlib.sha256(_norm(_js_block(src, h)).encode("utf-8")).hexdigest()[:16]
            for h in _MIRRORED}


def test_the_mirrored_board_constants_are_unchanged():
    src = PROSPX.read_text(encoding="utf-8")
    for line in ("const PD_SIGMA_MIN_N = 30;", "const PD_SIGMA_FALLBACK = 9.0;",
                 "const PLUS_PROVISIONAL_GAMES = 20;"):
        assert line in src, line


def test_the_mirrored_board_code_is_unchanged():
    """prospx_leaderboard_export mirrors these board functions for the current-season
    indexes. A change here means the mirror must change with it (then re-pin)."""
    got = js_pins()
    changed = {h: got[h] for h, want in _MIRRORED.items() if got[h] != want}
    assert not changed, ("board code the export mirrors has changed; update "
                         "prospx_leaderboard_export and re-pin: %r" % changed)


# ---------------------------------------------------------------------------
# Size, wiring, and the export entry point
# ---------------------------------------------------------------------------

def test_gzip_size_is_pinned(doc):
    raw = (HERE / "data" / "prospx_leaderboard.json").read_bytes()
    gz = len(gzip.compress(raw, compresslevel=9))
    assert gz <= GZIP_CEILING, (gz, GZIP_CEILING)


def test_the_nightly_writes_it_after_the_timeseries_export():
    src = (HERE / "run_monthly.py").read_text(encoding="utf-8")
    d9 = src.index('_step("d9. Rebuild timeseries (no scrape)"')
    d9d = src.index('_step("d9d. PROSPX leaderboard data (prospx_leaderboard.json)"')
    assert d9 < d9d
    assert "_plb.export(out=out_dir / \"prospx_leaderboard.json\"" in src[d9d:d9d + 1200]


def test_the_file_is_untracked_like_the_other_nightly_slices():
    gi = (HERE / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert "data/prospx_leaderboard.json" in gi


def test_export_writes_only_where_it_is_told(tmp_path):
    if not X.CACHE_DIR.exists() or not any(X.CACHE_DIR.glob("hitting_*.json")):
        pytest.skip(".cache/prospx_lb not warmed")
    served = HERE / "data" / "prospx_leaderboard.json"
    before = served.stat().st_mtime_ns if served.exists() else None
    out = tmp_path / "prospx_leaderboard.json"
    summary = X.export(fetch=False, out=out)
    assert summary["written"] and out.exists()
    assert (served.stat().st_mtime_ns if served.exists() else None) == before
    assert json.loads(out.read_text(encoding="utf-8"))["rows"]
