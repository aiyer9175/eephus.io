# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""tools/build_ebr.py's substrate (integration.md 4.5's schema, EBR_GATE.md 2.7 and 2.9).

On fixtures: the rows sum to the league blocks, a multi-club runner's stints sum
to his season row, the frozen digests hold (a rebuild that would move a frozen
season refuses), and the builder writes previews only. When a preview build of
the real record is present on this machine, the same identities are read off it
(skipped otherwise; this file never builds it).
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
for _p in (str(ROOT), str(ROOT / "tools")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import build_ebr  # noqa: E402
import ebr  # noqa: E402


def _load_fixtures():
    """test_fixtures/ebr/ebr_fixtures.py, loaded by path (it is not a package)."""
    import importlib.util
    if "ebr_fixtures" in sys.modules:
        return sys.modules["ebr_fixtures"]
    spec = importlib.util.spec_from_file_location(
        "ebr_fixtures", ROOT / "test_fixtures" / "ebr" / "ebr_fixtures.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["ebr_fixtures"] = mod
    spec.loader.exec_module(mod)
    return mod


fx = _load_fixtures()

PREVIEW = ROOT / ".cache" / "ebr" / "preview" / "ebr.json"
AFTER_FREEZE = date(2026, 11, 2)
PARTS = ebr.PARTS


@pytest.fixture()
def unpinned(monkeypatch):
    monkeypatch.setattr(ebr, "FROZEN_K", None)
    monkeypatch.setattr(ebr, "FROZEN_POOL_SHA256", None)
    monkeypatch.setattr(ebr, "POOL_SEASONS", (2023, 2024))


def _pool():
    data = {s: fx.season_frames(s) for s in ebr.POOL_SEASONS}
    raw = {s: ebr.season_raw(pa) for s, (pa, _) in data.items()}
    opps = {}
    for s, (pa, rn) in data.items():
        o = ebr.xb_opportunities(pa, rn)
        ebr.finalize_opportunities(o)
        opps[s] = o
    return ebr.frozen_pool_document(raw, opps)


def _build(tmp_path, seasons=(2023, 2024), *, today=AFTER_FREEZE, out=None, pool=None):
    out = out or tmp_path / "preview"
    data = {s: fx.season_frames(s) for s in seasons}
    sub, ev = build_ebr.build(record_data=(data, {}), out_dir=out, frozen_dir=tmp_path / "frozen",
                              today=today, generated_at="2026-11-02T00:00:00+00:00",
                              comparators=False, pool_doc=pool or _pool(), arm_blob={})
    build_ebr.write(sub, ev, out)
    return sub, ev


def _rows_sum_to_league(sub, tol_per_row=0.0005):
    ix = {f: i for i, f in enumerate(sub["fields"])}
    for s in sub["seasons"]:
        rows = [r for r in sub["rows"] if r[1] == s]
        lg = sub["league"][str(s)]
        assert lg["n_runners"] == len(rows)
        for p in PARTS:
            tot = sum(r[ix[p]] for r in rows)
            assert abs(tot - lg["sum"][p]) <= tol_per_row * len(rows) + 1e-6, (s, p, tot)
            assert abs(lg["sum"][p]) <= 0.01
        assert abs(sum(r[ix["ebr"]] for r in rows)) <= tol_per_row * 6 * len(rows) + 0.01


def _stints_sum_to_rows(sub, tol=0.0026):
    ix = {f: i for i, f in enumerate(sub["fields"])}
    n = 0
    for r in sub["rows"]:
        st = r[ix["stints"]]
        if st is None:
            continue
        n += 1
        assert len(st) >= 2
        assert sum(x[1] for x in st) == r[ix["pa"]]
        for j, p in enumerate(PARTS):
            assert abs(sum(x[2 + j] for x in st) - r[ix[p]]) <= tol * len(st), (r[0], p)
    return n


def test_the_schema(tmp_path, unpinned):
    sub, ev = _build(tmp_path)
    assert sub["schema"] == 1 and sub["model"] == "ebr" and sub["ebr_version"] == "ebr_v1"
    assert sub["fields"] == ["mlbam", "season", "pa", "starts_on_base", "opp_sb", "opp_xb", "opp_dp",
                             "sb", "pk", "xb_adv", "xb_oob", "dp", "ebr", "stints"]
    assert sub["gate"] == "docs/ebr-2026-09-30/EBR_GATE.md"
    for s in ("2023", "2024"):
        cells = sub["re24"][s]["cells"]
        assert len(cells) == 24 and all(len(v) == 2 and v[1] > 0 for v in cells.values())
        assert len(sub["re24"][s]["sha256"]) == 64
        assert sub["stamps"]["re24_sha256"][s] == sub["re24"][s]["sha256"]
    for k in ("K", "kappa", "pool_seasons", "pool_sha256", "record_built_at", "re24_sha256"):
        assert k in sub["stamps"]
    assert ev["descriptive"] is True and "look" not in ev
    assert set(ev["identity"]["2024"]) >= {"I1", "I2", "I3", "I4", "I5", "I6", "I7", "I8", "I9"}


def test_rows_sum_to_the_league_blocks(tmp_path, unpinned):
    sub, _ = _build(tmp_path)
    _rows_sum_to_league(sub)


def test_stints_sum_to_the_season_row(tmp_path, unpinned):
    sub, _ = _build(tmp_path)
    assert _stints_sum_to_rows(sub) >= 1          # A batted for both clubs in the fixtures
    ix = {f: i for i, f in enumerate(sub["fields"])}
    a = next(r for r in sub["rows"] if r[0] == fx.A and r[1] == 2024)
    assert sorted(x[0] for x in a[ix["stints"]]) == [fx.AWAY, fx.HOME]


def test_frozen_digests_hold(tmp_path, unpinned):
    out = tmp_path / "preview"
    pool = _pool()
    sub, _ = _build(tmp_path, out=out, pool=pool)
    dig = sub["cadence"]["frozen_digests"]
    assert set(dig) == {"2023", "2024"} and sub["cadence"]["frozen_seasons"] == [2023, 2024]
    again, ev = _build(tmp_path, out=out, pool=pool)
    assert again["cadence"]["frozen_digests"] == dig
    assert all(ev["identity"][s]["I8"]["unchanged"] is True for s in dig)
    # a frozen season whose rebuild differs refuses
    blob = json.loads((out / "ebr.json").read_text(encoding="utf-8"))
    blob["cadence"]["frozen_digests"]["2023"] = "0" * 64
    (out / "ebr.json").write_text(json.dumps(blob), encoding="utf-8")
    with pytest.raises(ebr.EbrRefusal, match="season 2023 is frozen"):
        _build(tmp_path, out=out, pool=pool)


def test_a_live_season_is_not_frozen(tmp_path, unpinned):
    sub, ev = _build(tmp_path, today=date(2024, 10, 1))
    assert sub["cadence"]["frozen_digests"] == {"2023": sub["cadence"]["frozen_digests"]["2023"]}
    assert sub["cadence"]["live_season"] == 2024
    assert ev["identity"]["2024"]["I8"]["frozen"] is False


def test_the_builder_writes_previews_only(tmp_path):
    for bad in (ROOT / "data", tmp_path / "data"):
        with pytest.raises(ebr.EbrRefusal, match="previews only"):
            build_ebr.write({}, {}, bad)
    assert build_ebr.OUT_DIR == ROOT / ".cache" / "ebr" / "preview"
    assert build_ebr.FROZEN_DIR == ROOT / ".cache" / "ebr" / "frozen"


def test_the_amended_steal_band():
    assert "r_esb_vs_fg_wsb" in build_ebr.BUG_BANDS and "r_sb_vs_fg_wsb" not in build_ebr.BUG_BANDS
    assert build_ebr.BUG_BANDS["r_esb_vs_fg_wsb"] == ("esb_vs_fg_wsb", 300, "pearson", ">=", 0.80)
    rows = [[i, 2024, 400, 0, 0, 0, 0, float(i % 7), float(i % 3) * 0.1, 0.0, 0.0, 0.0,
             float(i % 7) + float(i % 3) * 0.1, None] for i in range(1, 41)]
    comp = {"fg": {i: {"wSb": float(i % 7) * 0.9, "baseRunning": 0.0} for i in range(1, 41)},
            "bref": {}, "savant": {}, "sprint": {}, "lg": None,
            "lines": {i: {"plateAppearances": 400} for i in range(1, 41)}}
    blk = build_ebr.agreement_block(2024, rows, comp)
    f = blk["by_floor"]["pa300"]
    assert f["esb_vs_fg_wsb"]["pearson"] == pytest.approx(1.0)
    assert {"sb_runs_vs_fg_wsb", "epk_vs_fg_wsb"} <= set(f) and "sd_epk" in f["epk_vs_fg_wsb"]
    assert blk["bug_bands"]["r_esb_vs_fg_wsb"]["pass"] is True


@pytest.mark.skipif(not PREVIEW.exists(), reason="no preview build of the record on this machine")
def test_the_preview_build_keeps_the_same_identities():
    sub = json.loads(PREVIEW.read_text(encoding="utf-8"))
    assert sub["ebr_version"] == ebr.EBR_VERSION
    assert sub["stamps"]["pool_sha256"] == ebr.FROZEN_POOL_SHA256
    assert sub["stamps"]["K"] == ebr.FROZEN_K
    _rows_sum_to_league(sub)
    assert _stints_sum_to_rows(sub) > 100
    for s, d in sub["cadence"]["frozen_digests"].items():
        rows = [r for r in sub["rows"] if r[1] == int(s)]
        assert build_ebr._sha_obj({"rows": rows, "re24": sub["re24"][s]["sha256"],
                                   "ebr_version": ebr.EBR_VERSION}) == d
    by = defaultdict(int)
    for r in sub["rows"]:
        by[r[1]] += 1
    assert set(by) == set(sub["seasons"])
