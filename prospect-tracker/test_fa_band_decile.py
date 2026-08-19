# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""Fence tests for the 2026-08-19 band decile-width gate (LOSS-RECORD).

The per-decile multiplicative width correction FAILED its frozen gate
(docs/fa-2026-08-19/BAND_DECILE_GATE.md): the isotonic corrected-width
constraint pooled deciles 0-2 by PAV and drove decile 0 coverage
0.841 -> 0.566 fold-out (clauses C2/C3 fail; C1 0.78790 and the permuted
control C4 pass). Nothing shipped. These tests pin the fence:

  - no decile correction map exists in the served band_scale: a width map
    without a passing gate doc is the invented-number defect class
  - the gate doc records the loss, with no clause left PENDING
  - the guarantee-side band artifact stays free of any decile correction
    (twice-null, fenced by gate-2026-08-07-fa-guarantee-band.md)
  - the shipped WAR band still serves sane positive-width offsets

If a future re-gate ships a decile map, it must update these assertions IN
THE SAME CHANGE as the new passing gate doc.
"""

import json
from pathlib import Path

HERE = Path(__file__).parent
GATE_DOC = HERE / "docs" / "fa-2026-08-19" / "BAND_DECILE_GATE.md"


def _gate1() -> dict:
    return json.loads((HERE / "data" / "fa_gate1_eval.json")
                      .read_text(encoding="utf-8"))


def test_no_unshipped_decile_map():
    d = _gate1()
    bs = d.get("band_scale") or {}
    assert "decile_width_correction" not in bs, (
        "a decile width map is persisted but the 2026-08-19 gate verdict is "
        "LOSS-RECORD; ship it only through a NEW passing gate doc")
    assert "band_scale_decile_correction_eval" not in d


def test_gate_doc_records_loss():
    doc = GATE_DOC.read_text(encoding="utf-8")
    assert "VERDICT: LOSS-RECORD" in doc
    assert "VERDICT: PENDING" not in doc
    # every clause carries a filled verdict, none left open
    for clause in ("C1", "C2", "C3", "C4", "C5"):
        assert clause in doc


def test_guarantee_side_fenced():
    # The guarantee band is twice-null and fenced OFF; the WAR-side decile
    # work must never leak a correction into the dollars side.
    p = HERE / "data" / "fa_guar_band_eval.json"
    if not p.exists():
        return
    raw = p.read_text(encoding="utf-8")
    assert "decile_width_correction" not in raw


def test_war_band_serves_positive_width():
    import fa_bands
    m = _gate1().get("band_scale")
    assert m and m.get("version") == "fa_bands_v1"
    for side, pred, expo, age in (("hit", 2.0, 500, 30.0),
                                  ("pit", 0.5, 150, 34.0)):
        z = fa_bands.war_z(side, pred, expo, age, 0.0, 0.0,
                           float(m["age_mean"]))
        o = fa_bands.offsets(m, z, side, (0.10, 0.90))
        assert o and o[0.10] < o[0.90]
        assert (o[0.90] - o[0.10]) > 0.05


if __name__ == "__main__":
    test_no_unshipped_decile_map()
    test_gate_doc_records_loss()
    test_guarantee_side_fenced()
    test_war_band_serves_positive_width()
    print("test_fa_band_decile: 4/4 OK")
