# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FA destination gate's result pins (the one look, task Q9_04b, 2026-10-14).

Kept apart from test_fa_destination_gate.py, which pins the registered criteria:
a result pin beside a criterion pin invites editing the criterion to match the
result. Every number here is read from data/fa_destination_eval.json; the pins
assert that the gate document's section 19, the registry row and the artifact
agree with one another and with the ship rule applied to the artifact's clauses.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import fa_destination as fd  # noqa: E402
import fa_destination_lab as lab  # noqa: E402

DOC = ROOT / "docs" / "fa-2026-10" / "FA_DESTINATION_GATE.md"
ART = ROOT / "data" / "fa_destination_eval.json"
REG = ROOT / "data" / "model_registry.json"
RESULTS_HEADING = "## 19. Results"


def _art() -> dict:
    return json.loads(ART.read_text(encoding="utf-8"))


def _results() -> str:
    d = DOC.read_text(encoding="utf-8")
    return re.sub(r"\s+", " ", d[d.index(RESULTS_HEADING):])


def _row() -> dict:
    rows = [m for m in json.loads(REG.read_text(encoding="utf-8"))["models"]
            if m["model_id"] == fd.MODEL_ID]
    assert len(rows) == 1
    return rows[0]


def test_the_artifact_is_the_registered_look():
    a = _art()
    assert a["protocol_sha256"] == fd.PROTOCOL_SHA256
    assert fd.protocol_sha256(DOC.read_text(encoding="utf-8")) == fd.PROTOCOL_SHA256
    assert a["dry_run"] is False
    assert a["order"] == ["step0", "gate2_join", "folds", "floors",
                          "metrics_clauses_verdict", "reported", "industry"]
    assert a["generated_at"] == "2026-10-14"


def test_the_verdict_follows_the_ship_rule_from_the_artifacts_clauses():
    a = _art()
    v = lab.ship_verdict(a["clauses"]["P"], a["clauses"]["N_in_P_place"])
    assert v == a["verdict"]
    assert a["verdict"]["serve"] == "N"
    assert a["loss_ledger"] == [lab.NULL_LINE]
    assert a["coef_hash"] == a["reported"]["serving_fit"]["N"]["coef_hash"]


def test_section_19_carries_the_artifact_hash_and_its_numbers():
    a = _art()
    text = _results()
    sha = hashlib.sha256(ART.read_bytes()).hexdigest()
    assert sha in text
    assert "verdict SERVE N" in text
    assert a["coef_hash"] in text
    m = a["metrics"]
    for arm in ("P", "N", "L_perm", "incumbency_only", "payroll_space", "payroll_level",
                "live_analog"):
        assert f"{m[arm]['mrr']:.4f}" in text, arm
    for arm in ("P", "N"):
        assert f"{m[arm]['log_loss']:.4f}" in text, arm
    p = a["clauses"]["P"]["C3_p"]
    assert f"{p['mrr']:.4f}" in text and f"{p['log_loss']:.4f}" in text
    assert f"{a['floors']['log_loss_floor']:.5f}" in text
    h2h = a["industry"]["retro"]["head_to_head"]["N"]
    assert f"{h2h['model_hit_rate']:.4f}" in text and f"{h2h['mlbtr_hit_rate']:.4f}" in text


def test_the_registry_row_matches_the_verdict():
    row = _row()
    a = _art()
    assert row["eval_artifact"] == "data/fa_destination_eval.json"
    assert row["verdict"] == ("validated" if a["verdict"]["serve"] else "unvalidated")
    assert row["champion"].startswith(f"fa_destination {a['verdict']['serve']}:")
    assert "FA_DESTINATION_SERVE" in row["surface"]


def test_serving_stays_off():
    assert fd.FA_DESTINATION_SERVE is False
    assert not (ROOT / "data" / "fa_destinations.json").exists()
