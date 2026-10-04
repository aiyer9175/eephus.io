# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""DS-16 pins (docs/efv-v2/DRIVER_SYSTEM_V2.md s5): the one pre-declared development read
of the assembled V2, the `ds16` block of data/efv_v2_dev_eval.json.

1. It was declared first: the commit it names carries docs/efv-v2/EFV_V2_GATE.md as a
   DRAFT, is an ancestor of HEAD, and predates the read.
2. Frame guards: list vintages 2017 to 2019 only (none reserved, none a combiner-rule
   year), vm base years before 2025, the R-VM pins empty; the reserved_vm rows it kept all
   sit at W3 = 0 (EFV_V2_GATE.md s5 B9b).
3. The statistic is the registered one (efv_v2_stat), primary within, secondary pooled,
   and every leg is E_cond with the registered B and seed; the weights are the
   registration's.
4. It adjudicates and selects nothing; the arm ledger counts its probes.

Reads the committed artifact only; computes no statistic.
"""
from __future__ import annotations

import json
import subprocess
from datetime import datetime
from pathlib import Path

import pytest

import efv_v2_model as H
import efv_v2_stat as S
import efv_vintage_frame as F

ROOT = Path(__file__).parent
DEV = ROOT / "data" / "efv_v2_dev_eval.json"
LEDGER = ROOT / "data" / "xfv_arm_ledger.json"


def _ds16() -> dict:
    if not DEV.exists():
        pytest.skip("data/efv_v2_dev_eval.json not built")
    doc = json.loads(DEV.read_text(encoding="utf-8"))
    if "ds16" not in doc:
        pytest.skip("no DS-16 block yet")
    return doc["ds16"]


def _git(*args) -> str:
    r = subprocess.run(["git", "-C", str(ROOT), *args], capture_output=True, text=True,
                       encoding="utf-8")
    assert r.returncode == 0, r.stderr
    return r.stdout.strip()


def test_the_read_was_declared_in_a_committed_draft_before_it_ran():
    d = _ds16()
    dec = d["declared_in"]
    assert dec["doc"] == F.GATE_DOC and dec["status"] == "DRAFT"
    subprocess.run(["git", "-C", str(ROOT), "merge-base", "--is-ancestor", dec["commit"],
                    "HEAD"], check=True)
    text = _git("show", f"{dec['commit']}:./{F.GATE_DOC}")
    assert F.gate_doc_registered(text) is False
    assert "## 7. The development read registered before it runs (DS-16)" in text
    ran = datetime.fromisoformat(d["generated_at"].replace("Z", "+00:00"))
    committed = datetime.fromisoformat(dec["committed_at"])
    assert committed < ran


def test_frame_guards():
    d = _ds16()
    g = d["reserved_guard"]
    assert g["reserved_vm_pins"] == []
    lv = g["lv_vintages_read"]
    assert lv == [2017, 2018, 2019]
    assert not set(lv) & set(F.RESERVED_LV) and max(lv) < min(F.RESERVED_LV)
    assert min(lv) > H.RULE_LAST_YEAR
    assert max(g["vm_years_read"]) < F.R_VM_FIRST_DEBUT_YEAR
    lvf = d["frames"]["lv_dev"]
    assert sorted({int(gr.split("|")[1]) for gr in lvf["groups"]}) == lv
    assert lvf["reserved_vm_kept_w3_zero"] == sum(
        r["reserved_vm_kept_w3_zero"] for r in lvf["per_vintage"])
    vm = d["frames"]["vm_dev"]
    assert vm["frame_version"] == "vm2"
    assert all(int(gr.split("|")[1]) < F.R_VM_FIRST_DEBUT_YEAR for gr in vm["groups"])


def test_the_statistic_is_the_registered_one():
    d = _ds16()
    st = d["statistic"]
    assert st["primary"] == S.STAT_LABEL[S.PRIMARY]
    assert st["secondary"] == S.STAT_LABEL[S.SECONDARY]
    assert st["min_group_rows"] == S.MIN_GROUP_ROWS
    assert d["bootstrap"] == {"B": S.B_DEFAULT, "seed": S.SEED_DEFAULT,
                              "estimator": "E_cond", "unit": "player cluster"}
    for f in d["frames"].values():
        assert f["statistic"] == S.STAT_LABEL[S.PRIMARY]
        for comp in f["deltas"].values():
            assert set(comp) == {"spearman", "pooled", "auc"}
            assert comp["spearman"]["statistic"] == "within"
            assert comp["pooled"]["statistic"] == "pooled"
            for leg in comp.values():
                assert leg["estimator"] == "E_cond"
                assert leg["B"] == S.B_DEFAULT and leg["seed"] == S.SEED_DEFAULT
                assert leg["reading"].startswith("development only")
        prim = f["deltas"]["v2_vs_prospx_consensus"]["spearman"]
        assert f["raters"]["efv_v2"]["within"] == round(prim["a"], 4)
        assert f["verdict"] == prim["reading"]


def test_the_weights_are_the_registration():
    d = _ds16()
    w = H.load_weights()
    # P5 (2026-10-04, POST_EPOCH_REBUILD) re-derived data/efv_v2_assembly.json once on the
    # frozen fWAR label; DS-16's one re-run on that label is owed (EFV_V2_GATE.md P5). Until
    # it runs, the stored read names the eWAR v2 assembly by its sha256; the pin returns by
    # itself once the re-run reads the current assembly.
    asm = ROOT / "data" / "efv_v2_assembly.json"
    if asm.exists():
        import hashlib
        cur = hashlib.sha256(asm.read_bytes()).hexdigest()
        asm_label = (json.loads(asm.read_text(encoding="utf-8")).get("label") or {})
        if (d.get("assembly_sha256") != cur
                and (d.get("label") or {}).get("provider") != asm_label.get("provider")):
            pytest.xfail("DS-16's re-run on the frozen fWAR label is owed (P5); the stored "
                         "read is on the eWAR v2 assembly")
    assert {s: {k: d["weights"][s][k] for k in ("w_skill", "w_time")}
            for s in F.SIDES} == w


def test_it_adjudicates_and_selects_nothing():
    d = _ds16()
    assert d["role"] == "development" and d["adjudicates"] is False
    assert d["selects"] is False and d["model_id"] == H.V2_ASSEMBLED_ID
    txt = json.dumps(d, ensure_ascii=False)
    assert "—" not in txt and "–" not in txt


def test_the_arm_ledger_counts_its_probes():
    d = _ds16()
    if not LEDGER.exists():
        pytest.skip("ledger absent")
    led = json.loads(LEDGER.read_text(encoding="utf-8"))
    mine = [p for p in led["probes"] if p["probe"].startswith("DS-16:")]
    assert len(mine) == d["n_probes"] == len(d["frames"])
