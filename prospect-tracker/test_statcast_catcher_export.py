# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Statcast catcher runs (statcast_catcher_export.py, owner decision EW3-38).

Pins: the cached FanGraphs leaderboard rows are carried verbatim (whole runs,
innings from baseball thirds), blocking is null before Statcast measured it, a
changed file shape is refused for its season and never fills a column, the
writer is byte-deterministic and writes only where it is told, the served file
keeps its invariants, and the two pages, the glossary and the registry carry it
as Statcast's measurement with no model claim.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

import statcast_catcher_export as SC

ROOT = Path(__file__).resolve().parent
SERVED = ROOT / "data" / "statcast_catcher_runs.json"
HEAD = "Name,Season,Pos,Inn,fFRP,bFRP,tFRP,FRP,CFraming,xMLBAMID"


def _csv(season: int, n: int = 45, extra: list[str] | None = None) -> str:
    rows = [HEAD]
    for k in range(n):
        rows.append(f"C{k},{season},C,{500 + k}.{k % 3},{k % 5 - 2},{k % 3 - 1},{k % 2},"
                    f"{(k % 5 - 2) + (k % 3 - 1) + (k % 2)},0.5,{9000 + k}")
    rows.append(f"Infielder,{season},SS,900.0,0,0,0,7,,{8000}")
    rows.append(f"No Id,{season},C,100.0,1,1,1,3,,")
    return "\n".join(rows + (extra or [])) + "\n"


def _cache(tmp_path: Path, seasons=(2017, 2018)) -> tuple[Path, Path]:
    raw = tmp_path / "raw"
    raw.mkdir()
    man = {}
    for s in seasons:
        (raw / f"fg_field_full_{s}.csv").write_text(_csv(s), encoding="utf-8")
        man[f"fg_field_full_{s}.csv"] = {"fetched_at": f"2026-10-1{s % 10}T03:00:00+00:00",
                                         "raw_sha256": "ab" * 32, "url": "https://example.invalid"}
    mpath = tmp_path / "fetch_manifest.json"
    mpath.write_text(json.dumps(man), encoding="utf-8")
    return raw, mpath


def test_innings_come_from_baseball_thirds():
    assert SC.innings_from_thirds("995.2") == 995.7
    assert SC.innings_from_thirds("959.1") == 959.3
    assert SC.innings_from_thirds("12") == 12.0
    assert SC.innings_from_thirds("") is None
    with pytest.raises(SC.ShapeChanged):
        SC.innings_from_thirds("10.5")


def test_catcher_rows_are_carried_verbatim_and_blocking_waits_for_2018():
    rows17 = SC.parse_season(_csv(2017), 2017)
    rows18 = SC.parse_season(_csv(2018), 2018)
    assert len(rows17) == 45 and len(rows18) == 45      # the SS row and the id-less row are out
    by = {r[0]: r[1:] for r in rows18}
    k = 7
    assert by[9000 + k] == [2018, round(507 + 1 / 3, 1), k % 5 - 2, k % 3 - 1, k % 2,
                            (k % 5 - 2) + (k % 3 - 1) + (k % 2)]
    assert all(r[4] is None for r in rows17), "blocking must be null before Statcast measured it"
    assert all(isinstance(r[4], int) for r in rows18)


@pytest.mark.parametrize("bad,why", [
    (_csv(2018).replace("tFRP,", "tFRPX,", 1), "missing columns"),
    (_csv(2018, extra=["Dup,2018,C,10.0,1,1,1,3,,9003"]), "two catcher rows"),
    (_csv(2018, n=12), "outside"),
    (_csv(2018).replace("C0,2018,", "C0,2019,", 1), "stamped"),
])
def test_a_changed_shape_is_refused(bad, why):
    with pytest.raises(SC.ShapeChanged, match=why):
        SC.parse_season(bad, 2018)


def test_build_is_deterministic_and_writes_only_where_told(tmp_path):
    raw, man = _cache(tmp_path)
    (raw / "fg_field_full_2019.csv").write_text(_csv(2019).replace("tFRP,", "tFRPX,", 1), encoding="utf-8")
    out = tmp_path / "out" / "statcast_catcher_runs.json"
    before = SERVED.read_bytes() if SERVED.exists() else None
    doc = SC.write(out, raw_dir=raw, manifest_path=man, seasons=range(2016, 2020))
    assert doc["seasons"] == [2017, 2018]
    assert doc["missing_seasons"] == [2016]
    assert "2019" in doc["refused_seasons"]
    assert doc["counts"] == {"2017": 45, "2018": 45}
    assert doc["as_of"] == "2026-10-18"
    assert doc["fields"] == ["season", "inn", "frm", "blk", "thr", "tot"]
    first = out.read_bytes()
    assert json.loads(first) == doc
    SC.write(out, raw_dir=raw, manifest_path=man, seasons=range(2016, 2020))
    assert out.read_bytes() == first, "the same cache must write the same bytes"
    after = SERVED.read_bytes() if SERVED.exists() else None
    assert after == before, "a test write reached the served file"


def test_no_readable_season_keeps_the_served_file(tmp_path):
    out = tmp_path / "statcast_catcher_runs.json"
    out.write_text("{}", encoding="utf-8")
    assert SC.write(out, raw_dir=tmp_path / "nothing", manifest_path=tmp_path / "none.json") is None
    assert out.read_text(encoding="utf-8") == "{}"


def test_the_served_file_keeps_its_invariants():
    if not SERVED.exists():
        pytest.skip("data/statcast_catcher_runs.json is not built on this machine")
    doc = json.loads(SERVED.read_text(encoding="utf-8"))
    assert doc["label"] == "Statcast catcher runs"
    assert "not computed" in doc["claim"] and "do not read it" in doc["claim"]
    at = {k: i for i, k in enumerate(doc["fields"])}
    n = 0
    for mid, rows in doc["players"].items():
        assert int(mid) > 0
        seasons = [r[at["season"]] for r in rows]
        assert len(seasons) == len(set(seasons)), mid
        for r in rows:
            n += 1
            s = r[at["season"]]
            assert s in doc["seasons"]
            assert r[at["inn"]] > 0
            if s < doc["blocking_first_season"]:
                assert r[at["blk"]] is None, (mid, s)
            parts = [r[at[k]] for k in ("frm", "blk", "thr")]
            if r[at["tot"]] is not None and all(v is not None for v in parts):
                assert abs(r[at["tot"]] - sum(parts)) <= 1, (mid, r)
    assert n == sum(doc["counts"].values())


def test_the_pages_read_it_as_statcasts_number():
    js = (ROOT / "assets" / "mlbstats.js").read_text(encoding="utf-8")
    assert 'var STATCAST_C_URL = "/data/statcast_catcher_runs.json";' in js
    for key in ("c_sc_runs", "c_sc_frm", "c_sc_blk", "c_sc_thr"):
        assert re.search(r'\{ key: "%s", label: "[^"]+", term: "statcast_catcher_runs"' % key, js), key
    assert '"c_sc_runs", "c_sc_frm", "c_sc_blk", "c_sc_thr"' in js
    proj = (ROOT / "assets" / "projections.js").read_text(encoding="utf-8")
    assert 'fetch("/data/statcast_catcher_runs.json"' in proj
    assert 'section("defense-statcast-c", "Statcast catcher runs"' in proj


def test_glossary_and_registry_rows():
    g = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    e = next(x for x in g["entries"] if x["id"] == "statcast_catcher_runs")
    assert e["shelf"] == "industry" and "Statcast" in e["origin"]
    assert "not computed, shrunk or validated here" in e["methodology"]
    r = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(x for x in r["models"] if x["model_id"] == "statcast_catcher_runs")
    assert row["verdict"] == "provisional" and row["provisional_kind"] == "measurement_only"
    assert row["eval_artifact"] == "data/statcast_catcher_runs.json"


def test_no_model_or_rollup_reads_it():
    """Display only: the series enters eWAR v3 only through the skill look's own
    read of the cache (EBR_GATE.md part 11.6), never through this module."""
    hits = []
    for p in ROOT.glob("*.py"):
        if p.name == "statcast_catcher_export.py" or p.name.startswith("test_"):
            continue
        t = p.read_text(encoding="utf-8", errors="replace")
        if re.search(r"^\s*(import|from)\s+statcast_catcher_export\b", t, re.M) or "statcast_catcher_runs.json" in t:
            hits.append(p.name)
    assert not hits, hits
