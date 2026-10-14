# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FA destination forward-read freeze (gate section 14, task Q9_04b).

Pins: the restated F arithmetic (fa_destination.winter_context and
member_comps) equals build_rows field for field on every Gate 3 winter; the class
vector is a probability vector per priced member; the frozen files hash to the
values the gate document's section 18 entry prints, carry the artifact's
coef_hash and are internally whole; the freeze tool refuses to run twice.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "tools"))

import fa_destination as fd  # noqa: E402
import fa_destination_freeze as fz  # noqa: E402
import fa_fit_backtest as fb  # noqa: E402

DOC = ROOT / "docs" / "fa-2026-10" / "FA_DESTINATION_GATE.md"
FROZEN = ROOT / "data" / "_labs" / "fa_destination" / "frozen_2026_27"
FIELDS = ("need", "window", "afford", "park", "behavior", "behavior_cond", "incumbent")


def test_member_comps_reproduce_build_rows_bit_exact():
    import fa_market as fm
    import scrapers
    with scrapers.cache_only():
        rows = fb.build_rows()
        enriched = fm.enriched_signings(2015, 2026)
        grouped = fd.comps_from_rows(rows)
        n = 0
        for Y in sorted({r["winter"] for r in rows}):
            ctx = fd.winter_context(Y, enriched)
            signed = [s for s in enriched if s["class_year"] == Y and s.get("to_team") in fb.ORGS]
            out = fd.outgoing_groups((s.get("from_team"), s.get("position")) for s in signed)
            for s in signed:
                npv = fm._npv_of(s)
                aav = npv / max(int(s["years"]), 1)
                got = fd.member_comps(ctx, position=s.get("position"),
                                      from_team=s.get("from_team"), npv_usd=npv,
                                      aav_usd=aav, outgoing=out)
                want = grouped[(Y, s["player_key"])]
                for o in fb.ORGS:
                    assert {f: got[o][f] for f in FIELDS} == {f: want[o][f] for f in FIELDS}
                    n += 1
    assert n == len(rows)


def _ctx():
    beh = {"NYY": {"max": 3e8, "n100": 3, "recent": 5e8, "guars": [1e7, 1e8, 3e8],
                   "events": [(2024, 1e7), (2025, 1e8), (2026, 3e8)]}}
    return {"winter": 2027, "beh": beh, "max_recent": 5e8,
            "pay": {"NYY": {"tax_payroll_usd": 3e8}, "MIA": {"tax_payroll_usd": 9e7}},
            "wins": {"NYY": 94, "MIA": 70}, "park": {}, "threshold_prev_usd": 244e6,
            "prior_class_years": 12}


def test_class_vectors_are_probability_vectors_and_skip_unpriced():
    members = [{"key": "a", "pos": "SP", "from": "NYY", "projGuar": 2e8, "projAav": 4e7},
               {"key": "b", "pos": "C", "from": None, "projGuar": 5e6, "projAav": 5e6},
               {"key": "c", "pos": "RP", "from": "MIA", "projGuar": None, "projAav": None}]
    rec = {"features": ["fit_analog", "incumbent"], "coefs": {"fit_analog": 0.86, "incumbent": 1.77},
           "standardization": {}}
    vec = fd.class_vectors(members, rec, _ctx())
    assert sorted(vec) == ["a", "b"]
    for v in vec.values():
        p = np.asarray(v)
        assert p.shape == (fd.N_CLUBS,) and np.all(p > 0) and np.all(p < 1)
        assert abs(p.sum() - 1.0) < 1e-9
    assert int(np.argmax(vec["a"])) == fd.ORGS.index("NYY")
    assert fd.class_vectors(members, rec, _ctx()) == vec
    with pytest.raises(ValueError):
        fd.class_vectors(members, {**rec, "features": ["fit_analog", "fa_share_3"]}, _ctx())


def _printed_hash(name: str) -> str:
    flat = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))
    m = re.search(re.escape(name) + r"`, sha256 `([0-9a-f]{64})`", flat)
    assert m, name
    return m.group(1)


@pytest.mark.parametrize("name", [fz.VECTORS, fz.TEAMFITS])
def test_the_frozen_files_hash_to_the_documents_entry(name):
    path = FROZEN / name
    assert hashlib.sha256(path.read_bytes()).hexdigest() == _printed_hash(name)


def test_the_frozen_vectors_are_whole_and_carry_the_artifacts_hash():
    v = json.loads((FROZEN / fz.VECTORS).read_text(encoding="utf-8"))
    art = json.loads((ROOT / "data" / "fa_destination_eval.json").read_text(encoding="utf-8"))
    assert v["arm"] == art["verdict"]["serve"] == "N"
    assert v["coef_hash"] == art["coef_hash"]
    assert v["coefs"] == art["reported"]["serving_fit"]["N"]["coefs"]
    assert v["orgs"] == list(fd.ORGS)
    assert v["frozen_on"] == "2026-10-14" and v["class_year"] == 2027
    assert len(v["members"]) == v["counts"]["vectors"]
    assert v["counts"]["vectors"] + len(v["counts"]["unpriced"]) == v["counts"]["members"]
    for m in v["members"].values():
        assert len(m["p"]) == fd.N_CLUBS and abs(sum(m["p"]) - 1.0) < 1e-9
        assert all(0 < p < 1 for p in m["p"])
    t = json.loads((FROZEN / fz.TEAMFITS).read_text(encoding="utf-8"))
    assert t["fa_class_sha256"] == v["inputs"]["fa_class_sha256"]
    assert set(t["served"]["teamFits"]) == set(fd.ORGS)


def test_the_freeze_refuses_to_run_twice(capsys):
    assert fz.main(["--out-dir", str(FROZEN)]) == 2
    assert "refusing" in capsys.readouterr().out
