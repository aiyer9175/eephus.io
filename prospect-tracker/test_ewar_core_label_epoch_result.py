# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The core eWAR label epoch's result pin (docs/efv-2026-10-22/EWAR_CORE_LABEL_EPOCH_GATE.md
part 11, the 2026-10-22 entry): the circularity guard did NOT hold, so the label stays
published fWAR. The entry's numbers are asserted against the tracked records, and the
flag is asserted off.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "efv-2026-10-22" / "EWAR_CORE_LABEL_EPOCH_GATE.md"
GUARD = ROOT / "docs" / "efv-2026-10-22" / "ewar_core_label_guard.json"
BLAST = ROOT / "docs" / "efv-2026-10-22" / "ewar_core_label_blast.json"


def _entry() -> str:
    text = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))
    return text.split("### 2026-10-22: the circularity guard does NOT hold", 1)[1]


def test_verdict_and_flag():
    rec = json.loads(GUARD.read_text(encoding="utf-8"))
    v = rec["verdict"]
    assert v == {"g1_non_inferior": False, "g2_non_inferior": False, "guard_holds": False,
                 "twin_also_non_inferior": True}
    assert "**THE GUARD DOES NOT HOLD (part 4.4).**" in _entry()
    import war_source
    assert war_source.LABEL_EWAR_CORE is False and war_source.DEFAULT_PROVIDER == "fwar"


def test_g1_numbers_match_the_record():
    g1 = json.loads(GUARD.read_text(encoding="utf-8"))["g1"]
    e = _entry()
    assert g1["n_pairs"] == 2416 and g1["n_players"] == 713
    for val, txt in ((g1["s_series"], "core label {:.4f}"), (g1["s_fwar"], "published fWAR {:.4f}"),
                     (g1["gap"], "Gap {:.4f}"), (g1["lower"], "5th percentile {:.4f}"),
                     (g1["sd"], "sd {:.4f}"), (g1["mde95"], "MDE95 {:.4f}")):
        assert txt.format(val) in e, txt.format(val)
    assert "gap {:.4f}".format(g1["twin"]["gap"]) in e


def test_g2_numbers_match_the_record():
    g2 = json.loads(GUARD.read_text(encoding="utf-8"))["g2"]
    e = _entry()
    assert g2["n_club_seasons"] == 360 and g2["underpowered"] is False and g2["non_inferior"] is False
    for name, o in g2["outcomes"].items():
        cells = [f"{o['r_frame']:.4f}", f"{o['r_part']:.4f}", f"{o['dT']:+.4f}",
                 f"{o['player']['lower']:.4f}", f"{o['club']['lower']:.4f}"]
        row = " | ".join(cells)
        assert row in e, (name, row)
        assert o["non_inferior"] is (name == "runs_scored")


def test_blast_numbers_match_the_record():
    b = json.loads(BLAST.read_text(encoding="utf-8"))["sides"]
    e = _entry()
    h = b["hit"]["core:w3"]
    assert f"| hitters W3 | {h['n']:,} | {h['pearson_r']:.4f} | {h['mean_change']:+.3f} | {h['sd_change']:.3f} | " \
           f"{h['rows_move_0_5']} | {h['rows_move_1_0']} | {h['contributor_flags_changed']} |" in e
    p = b["pit"]["core:w3"]
    assert p["rows_move_0_5"] == 0 and p["contributor_flags_changed"] == 0


def test_nothing_downstream_ran():
    e = _entry()
    assert "**Not run, because the flip did not happen:**" in e


def test_epoch_closed_after_ewle_q2():
    text = re.sub(r"\s+", " ", DOC.read_text(encoding="utf-8"))
    tail = text.split("### 2026-10-22 (later): EWLE-Q2 answered; this epoch closes without a flip", 1)[1]
    assert "That is option (b) of part 10. So the core label is NOT adopted" in tail
    assert "`war_source.LABEL_EWAR_CORE` stays False permanently under this registration" in tail
    assert "no task EWAR_CORE_EPOCH_RUN is owed" in tail
    import war_source
    assert war_source.LABEL_EWAR_CORE is False and war_source.DEFAULT_PROVIDER == "fwar"
    reg = json.loads((ROOT / "data" / "model_registry.json").read_text(encoding="utf-8"))
    row = next(r for r in reg["models"] if r["model_id"] == "ewar_core_label")
    assert "the core label epoch is closed without a flip" in row["notes"]
