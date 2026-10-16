# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The /mlbstats/ ABS Challenges tab (eABS v0, docs/eabs-2026-10-15/EABS_GATE.md):
the flag, the shell, the script's wiring, the served payload's invariants, the
glossary entry and the registry row, and the copy rule of gate part 6."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import eabs as E  # noqa: E402
import eabs_export as X  # noqa: E402

PAYLOAD = ROOT / "data" / "eabs_leaderboards.json"
JS = ROOT / "assets" / "mlbstats.js"


def test_flag_is_on_and_the_exporter_writes_data_when_live():
    assert X.MLBSTATS_EABS_LIVE is True
    assert X.out_dir() == ROOT / "data"


def test_shell_carries_the_tab_while_live_and_not_when_dark(monkeypatch):
    import build_site as B
    live = B.build_mlbstats()
    assert 'data-mlbsection="eabs"' in live and 'id="mlbstats-eabs-root"' in live
    assert live.index('data-mlbsection="defense"') < live.index('data-mlbsection="eabs"') < live.index('data-mlbsection="leverage"')
    assert 'data-gl="eabs"' in live
    monkeypatch.setattr(X, "MLBSTATS_EABS_LIVE", False)
    dark = B.build_mlbstats()
    assert 'data-mlbsection="eabs"' not in dark and "mlbstats-eabs-root" not in dark
    assert 'data-gl="eabs"' not in dark


def test_served_page_matches_the_builder():
    import build_site as B
    page = (ROOT / "mlbstats" / "index.html").read_text(encoding="utf-8")
    assert 'data-mlbsection="eabs"' in page and 'aria-controls="mlbstats-section-eabs"' in page
    assert f"/assets/mlbstats.js?v={B._asset_ver('assets/mlbstats.js')}" in page


def test_script_wires_the_section_and_its_hash_keys():
    js = JS.read_text(encoding="utf-8")
    assert "baserunning|eabs)" in js and 's[1] === "eabs" ? eabsLive()' in js
    assert 'var AB_URL = "/data/eabs_leaderboards.json";' in js
    for needle in ('else if (name === "eabs") initEabs();', 'parts.push("aview=" + abView)',
                   'pushSort(parts, "asort", abSort)', 'readSort(h, "asort", AB_COLS, abSort)',
                   'eabs: "mlbstats-section-eabs"', 'section === "eabs" ? abTeam'):
        assert needle in js, needle
    # gate part 6: the persistence sentence is derived from the payload, and only
    # PERSISTS may say results carry over
    assert 'd[k] === "PERSISTS"' in js


@pytest.mark.skipif(not PAYLOAD.exists(), reason="data/eabs_leaderboards.json is not built")
def test_served_payload_invariants():
    p = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    assert p["version"] == E.EABS_VERSION and p["registration"] == E.GATE_DOC
    inv = p["invariants"]
    assert inv["budget_violations"] <= E.BUDGET_VIOLATION_MAX * p["league"]["all"]["n"]
    assert inv["cell_rate_sum_max_abs"] <= E.TOL and inv["negative_or_nonfinite_values"] == 0
    for role, board in X.ROLE_BOARD.items():
        rows = p["boards"][board]
        assert sum(r["n"] for r in rows) == inv["reconcile"][role]["ledger_n"] == p["league"]["by_role"][role]["n"]
        assert sum(r["won"] for r in rows) == p["league"]["by_role"][role]["won"]
        for r in rows:
            assert r["n"] == r["won"] + r["lost"]
            assert abs(r["raw"] - (r["rg"] - r["fc"])) <= 0.0015
            assert r["fc"] >= 0 and r["rg"] >= 0 and r["stake"] >= r["rg"] - 0.0015
    # the league sums of the boards and the unresolved row equal the league line
    assert sum(p["league"]["by_role"][k]["n"] for k in ("batter", "catcher", "pitcher", "unresolved")) == p["league"]["all"]["n"]
    st = p.get("stability")
    if st is not None:
        assert set(st["dispositions"]) == {"batter", "catcher"}


@pytest.mark.skipif(not PAYLOAD.exists(), reason="data/eabs_leaderboards.json is not built")
def test_registry_row_and_glossary_entry():
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(m for m in reg["models"] if m["model_id"] == "eabs")
    assert row["verdict"] == "provisional" and row["provisional_kind"] == "measurement_only"
    assert row["eval_artifact"] == "data/eabs_leaderboards.json"
    p = json.loads(PAYLOAD.read_text(encoding="utf-8"))
    assert f"{p['league']['all']['n']} zone challenges" in row["notes"]
    gl = json.loads((ROOT / "data" / "glossary.json").read_text(encoding="utf-8"))
    entry = next(e for e in gl["entries"] if e["id"] == "eabs")
    assert "mlbstats" in entry["module"] and len(entry["methodology"]) >= 80
    # never a forecast word on a descriptive number
    for word in (" will ", " luck", " due ", " regress", " trending", " sleeper"):
        assert word not in entry["definition"].lower() and word not in entry["methodology"].lower()


def test_glossary_and_registry_script_is_idempotent(tmp_path, monkeypatch, capsys):
    import shutil
    sys.path.insert(0, str(ROOT / "tools"))
    import eabs_glossary_registry as G
    for name in ("glossary.json", "model_registry.json", "eabs_leaderboards.json"):
        src = ROOT / "data" / name
        if not src.exists():
            pytest.skip(f"data/{name} is not built")
        (tmp_path / "data").mkdir(exist_ok=True)
        shutil.copy(src, tmp_path / "data" / name)
    (tmp_path / "data" / "_labs" / "eabs").mkdir(parents=True)
    stab = ROOT / "data" / "_labs" / "eabs" / "stability.json"
    if stab.exists():
        shutil.copy(stab, tmp_path / "data" / "_labs" / "eabs" / "stability.json")
    monkeypatch.setattr(G, "ROOT", tmp_path)
    monkeypatch.setattr(G, "GLOSSARY", tmp_path / "data" / "glossary.json")
    monkeypatch.setattr(G, "REGISTRY", tmp_path / "data" / "model_registry.json")
    before = {n: (tmp_path / "data" / n).read_bytes() for n in ("glossary.json", "model_registry.json")}
    assert G.main() == 0
    after = {n: (tmp_path / "data" / n).read_bytes() for n in ("glossary.json", "model_registry.json")}
    assert before == after, "the committed files already carry the entry and the row"
