# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
"""The /fa/ Model view prints Gate 1 and Gate 2 from data/fa_meta.json and
says it reads them "from the committed eval artifacts". fa_meta.json holds a
COPY, taken when fa_export.py last ran, so a gate persisted after that export
is not what the page shows.

That lag was served for a day (audit M04-02, 2026-09-24): fa_backtest --gate1
rewrote data/fa_gate1_eval.json at 16:06 on 2026-09-23 (WAR MAE 0.5157 vs
0.6242, coverage 0.7955), the sidecars had been exported at 15:51, and the
committed fa_meta.gate1 still read 0.574 vs 0.728 and 0.798. The class bands
lag the same way, because fa_market reads band_scale from the gate artifact
at export time. The fix is a re-export; this is the fence that notices.

Reads only. A failure means: run `python fa_export.py` and commit the
fa_meta.json and fa_class*.json it writes.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent / "data"


def _read(name):
    return json.loads((HERE / name).read_text(encoding="utf-8"))


def _meta():
    return _read("fa_meta.json")


def test_fa_meta_gate1_is_the_committed_gate1_artifact():
    served, art = _meta()["gate1"], _read("fa_gate1_eval.json")
    assert served["pooled"] == art["pooled"], (
        "fa_meta.gate1.pooled differs from data/fa_gate1_eval.json; "
        "re-run python fa_export.py")
    assert served["coverage_p10_p90"] == art["coverage_p10_p90"]
    assert served.get("band_scale") == art.get("band_scale"), (
        "the class bands were priced on a different band_scale than the "
        "committed Gate 1 artifact carries")
    assert served == art, (
        "fa_meta.gate1 keys differ from the artifact: "
        f"{sorted(k for k in set(served) | set(art) if served.get(k) != art.get(k))}")


def test_fa_meta_gate2_is_the_committed_gate2_artifact():
    served, art = _meta()["gate2"], _read("fa_gate2_eval.json")
    assert served["pooled"] == art["pooled"]
    assert served == art, (
        "fa_meta.gate2 keys differ from the artifact: "
        f"{sorted(k for k in set(served) | set(art) if served.get(k) != art.get(k))}")


def test_fa_meta_names_the_war_basis_the_board_prices_on():
    """M04-03 (2026-09-25). Gate 2 was persisted on 2026-08-19, before the
    2026-09-03 eWAR label epoch, and names no WAR basis; the page printed it
    beside eWAR-priced contracts with no date and no basis. fa_meta now carries
    the current basis so the Model view can compare."""
    import war_source
    assert _meta().get("war_provider") == war_source.DEFAULT_PROVIDER


def test_model_view_discloses_a_gate_measured_on_another_label():
    js = (Path(__file__).parent / "assets" / "fa.js").read_text(encoding="utf-8")
    body = js.split("function renderModel(rows, meta)", 1)[1].split("\n  function ", 1)[0]
    assert "const gateBasis = g =>" in body
    assert body.count("${gateBasis(g1)}") == 1 and body.count("${gateBasis(g2)}") == 1
    assert "g.war_provider !== now" in body
    assert "a re-run on the current label is owed" in body


def test_gate_writers_stamp_their_basis_and_date():
    src = (Path(__file__).parent / "fa_backtest.py").read_text(encoding="utf-8")
    gate2 = src.split("def run_market_gate(", 1)[1].split("\ndef ", 1)[0]
    assert '"war_provider": fp._war_provider(),' in gate2
    gate1 = src.split("def run_projection_gate(", 1)[1].split("\ndef ", 1)[0]
    assert 'summary["generated_at"]' in gate1
