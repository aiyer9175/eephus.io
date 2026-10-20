# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The eWAR v3 gate RESULT pins (docs/ebr-2026-09-30/EBR_GATE.md part 12).

Part 12.1 holds the eBR outcome look (parts 5 and 6), run once on 2026-10-19 by
tools/ebr_gate.py as an OWNER-WAIVED EARLY READ (owner EW3-5). Part 12.2 holds the
eWAR v3 skill look (parts 9.5 and 9.6, as amended by part 11), run once on
2026-10-19 by tools/swar_lab.py, also an OWNER-WAIVED EARLY READ, with its
machine-readable record in the TRACKED file docs/ebr-2026-09-30/swar_eval.json.
This file pins both results so they cannot be edited after the fact, and asserts
that the tracked record's dispositions and admissions equal the part 12.2 text.
It lives apart from test_ebr_gate_registration.py on purpose: a result pin that
lives beside a criterion pin invites editing the criterion to match the result
(the reason test_arb_gate_c2_registration.py gives). Part 12.3 (the skill
holdout) stays asserted EMPTY by the registration pin until its own run, which
extends this file.

No correlation against runs or wins is pinned here; those stay in parts 12.1 and
12.2, the preview look block and the tracked record's look block only (EBR_GATE.md
parts 5.3, 5.10 and 11.2.4).
"""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "ebr-2026-09-30" / "EBR_GATE.md"
RECORD = ROOT / "docs" / "ebr-2026-09-30" / "swar_eval.json"


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _part_12_1() -> str:
    doc = _doc()
    i = doc.index("### 12.1 The outcome look (parts 5 and 6)")
    return doc[i:doc.index("### 12.2 The skill look (parts 9.5 and 9.6)", i)]


def test_part_12_1_holds_exactly_one_run_dated_with_its_commit_and_the_waiver():
    sec = _part_12_1()
    assert sec.count("`python -u tools/ebr_gate.py` at") == 1, "the outcome look runs once"
    assert ("**2026-10-19, `python -u tools/ebr_gate.py` at `4924a5eb`, OWNER-WAIVED EARLY READ "
            "(owner EW3-5, 2026-10-14).**") in sec
    assert sec.count("eBR OUTCOME LOOK 2026-10-19 at 4924a5eb") == 1
    assert "EMPTY." not in sec


def test_the_inputs_it_read_are_stamped_before_any_statistic():
    sec = _part_12_1()
    vint = sec.index("fWAR vintage 2026-10-02-57bf90f7143e sha256 "
                     "c4de5ca2e4a1492167f2a47666503112c916a67dcfd38389de39f910187550fa")
    bref = sec.index("Baseball-Reference frame (cached, never fetched) sha256 "
                     "e9571c428cb4db444e4b8214bb9adc5834925529e7d10db4271993f79fc3fd55")
    assert vint < bref < sec.index("LEG E (5.2)")
    assert "substrate rows the record no longer reproduces, per season: {'2018': 0, '2019': 0, '2021': 0" in sec
    assert "FRAME (5.1): 1181 runner-pairs, 475 players" in sec
    assert "rows dropped for a missing series: none; vintage PA differing from the official line on 0" in sec


def test_leg_e_its_twin_and_its_guards():
    sec = _part_12_1()
    floors = sec.index("floors Leg E: bootstrap sd 0.0244, half-width 0.0402")
    leg = sec.index("Leg E: mean rho E +0.4449, mean rho B +0.6499, d -0.2050, interval [-0.2452, -0.1648], "
                    "disposition RESOLVED_LOSS")
    assert floors < leg, "the floors print before the estimate"
    assert "Leg E twin: mean rho E -0.0234, mean rho B +0.6499, d -0.6734" in sec
    assert re.search(r"Leg E twin: [^\n]*disposition RESOLVED_LOSS", sec)
    assert "frame U d -0.1746; club changers d -0.2089" in sec
    assert re.search(r"LEG T \(5\.3\): 240 club-seasons; [^\n]*passes True", sec)


def test_the_dp_leg():
    sec = _part_12_1()
    assert ("E-DP: mean rho G +0.4182, mean rho R +0.4909, d -0.0727, interval [-0.1196, -0.0258], "
            "disposition RESOLVED_LOSS") in sec
    assert re.search(r"E-DP twin: [^\n]*disposition RESOLVED_LOSS", sec)
    assert "E-DP frame U d_DP -0.0730; club changers d_DP -0.0359" in sec
    assert "floors DP-1: bootstrap sd 0.0283, half-width 0.0466" in sec
    assert "DP-1: mean rho of eGDP per opportunity +0.4211; estimate - 1.645 sd +0.3745; floor clears True" in sec
    assert "DP-1 passes True (the permuted eGDP must fail it: it fails)" in sec
    assert re.search(r"DP-2: [^\n]*passes True", sec)


def test_reliability_flags_and_bem_plus():
    sec = _part_12_1()
    for part in ("SB runs", "XB runs", "DP runs", "eBR", "sb", "pk", "xb_adv", "xb_oob", "dp"):
        assert re.search(rf"^  {re.escape(part)}: \[[^\n]*\]; NOISE False\r?$", sec, re.M), part
    assert "NOISE True" not in sec
    assert "BEM+ CONSTANTS (5.8, fit before any gate statistic, frozen here): SB k 5889.6" in sec
    assert sec.index("BEM+ CONSTANTS") < sec.index("LEG E (5.2)"), "BEM+'s constants are fit first"
    assert '"pass": false' in sec and '"twin_fails": true' in sec


def test_what_part_6_licenses():
    flat = _flat(_part_12_1())
    assert ("- candidate part 1: not admitted (Leg E RESOLVED_LOSS, Leg T pass True, d frame U -0.1746, "
            "d club changers -0.2089); eWAR v3 keeps FanGraphs' BsR") in flat
    assert ("- candidate part 2: not admitted (E-DP RESOLVED_LOSS, DP-1 True, DP-2 True); eWAR v3 carries no "
            "double-play part from 2016 on") in flat
    assert "- copy: repeats less from one season to the next than FanGraphs' BsR on the same runners" in flat
    assert ("- dp copy: repeats less from one season to the next than Baseball-Reference's double-play runs "
            "on the same runners") in flat
    assert "- dp repeatable word: allowed (DP-1 passes)" in flat
    assert "- bem_plus: not served (FAIL)" in flat
    assert "- noise flags: none" in flat


def test_the_owner_waived_early_read_note_follows_the_last_section():
    doc = _doc()
    note = "**Dated note, 2026-10-19: the outcome look of part 12.1 is an OWNER-WAIVED EARLY READ.**"
    assert doc.count(note) == 1
    assert doc.index(note) > doc.index("licenses under part 1's recorded answers.")
    flat = _flat(doc[doc.index(note):])
    assert "--owner-waived-early-read`, which lifts only part 7.2's date clauses" in flat
    assert "the look itself fetched nothing and read that cached copy as it stood" in flat


# ---- part 12.2: the skill look ------------------------------------------------

SKILL_HEADER = ("**2026-10-19, `python -u tools/swar_lab.py --out docs/ebr-2026-09-30/swar_eval.json` at "
                "`210fb38a`, OWNER-WAIVED EARLY READ (owner EW3-5, 2026-10-14).**")


def _part_12_2() -> str:
    doc = _doc()
    i = doc.index("### 12.2 The skill look (parts 9.5 and 9.6)")
    return doc[i:doc.index("### 12.3 The skill holdout (part 9.5)", i)]


def _record() -> dict:
    return json.loads(RECORD.read_text(encoding="ascii"))


def _verbatim(sec: str) -> str:
    return sec[sec.index("```text"):sec.rindex("```")]


def test_part_12_2_holds_exactly_one_run_dated_with_its_commit_and_the_waiver():
    sec = _part_12_2()
    assert sec.count(SKILL_HEADER) == 1
    assert sec.count("`python -u tools/swar_lab.py --out") == 1, "the skill look runs once"
    assert "EMPTY." not in sec
    v = _verbatim(sec)
    assert v.count("swar_lab swar_lab/2 look on 2026-10-19: preview vintage 2026-10-02-a020cf64844a") == 1
    assert "[holdout]" not in v, "the holdout is not read in the look"


def test_the_tracked_record_is_the_one_scored_look():
    rec = _record()
    assert rec["status"] == "SCORED" and rec["mode"] == "look" and rec["date"] == "2026-10-19"
    assert rec["holdout"] is None, "the holdout appends its own block in its own commit"
    assert rec["fwar_vintage_id"] == "2026-10-02-a020cf64844a"
    assert rec["params"]["seed"] == 20261008 and rec["params"]["boot"] == 2000
    assert rec["params"]["predictor_seasons"] == [2021, 2022, 2023, 2024]
    sec = _part_12_2()
    assert rec["preview_generated_at"] in sec and rec["inputs"]["preview_sha256"] in sec


def test_inputs_floors_and_the_hr_arm_clause_print_before_any_gap():
    v = _verbatim(_part_12_2())
    gaps = v.index("[look] GAPS AND DISPOSITIONS, primary")
    assert v.index("inputs (sha256, read only, never fetched)") < v.index("[look] FLOORS, primary") < gaps
    assert v.index("[look] HR-ARM CLAUSE (primary target)") < gaps
    assert ("[look] HR-ARM CLAUSE (primary target): P-rate gap hr_shrunk over hr_fwar, 2016-2018 +0.0003, "
            "2021-2024 -0.0122: fails; home-run term hr_fwar") in v
    rec = _record()
    assert rec["hr_arm_clause"]["holds"] is False and rec["hr_arm_clause"]["variant"] == "hr_fwar"
    flat = _flat(_part_12_2())
    assert "positive in both blocks: False. The clause fails, so the home-run term reverts to fWAR's (hr_fwar)" in flat


def test_every_cell_disposition_in_the_record_equals_the_part_12_2_text():
    sec = _part_12_2()
    v = _verbatim(sec)
    primary = v[v.index("[look] GAPS AND DISPOSITIONS, primary"):v.index("[look] POSITION PART")]
    lines = primary.splitlines()
    rec = _record()
    n = 0
    for part, fam in rec["look"]["cells"].items():
        for cell, c in fam.items():
            n += 1
            disp = c["disposition"]
            pat = re.compile(rf"^\s+{re.escape(part)}\s+{re.escape(cell)}\s+n\s+{c['n_pairs']}\s.*=> "
                             rf"{re.escape(disp)}\s*$")
            assert sum(bool(pat.match(ln)) for ln in lines) == 1, (part, cell, disp)
            rows = [ln for ln in sec.splitlines() if ln.startswith("| ") and f" | {cell} | " in ln]
            assert len(rows) == 1, (part, cell)
            ship = "n/a (not a WIN) |" if not disp.startswith("WIN") else f"{bool(c['ship_flag_no_weight'])} |"
            assert rows[0].rstrip().endswith(f"| {disp} | {c['counts_as']} | {ship}"), rows[0]
    assert n == 18, "parts 4, 5, 6 (with S2b, S3t and S3c), PE-P and PE-H: 18 cells"


def test_every_admission_in_the_record_equals_the_part_12_2_text():
    sec = _part_12_2()
    v = _verbatim(sec)
    flat = _flat(sec)
    adm = _record()["look"]["admission"]
    assert set(adm) == {"batting", "pitching", "fielding", "pe_p", "pe_h", "position"}
    for part, a in adm.items():
        assert a["admitted"] is False, part
        assert re.search(rf"ADMIT {re.escape(part)}\s*: False \({re.escape(a['reason'])}", v), part
        assert a["reason"] in flat, part
    assert adm["fielding"]["catcher_component"]["admitted"] is False
    assert adm["batting"]["arm"] is None and adm["pitching"]["arm"] is None and adm["fielding"]["arm"] is None
    for label in ("candidate part 3 (position, our ladder): not admitted",
                  "candidate part 4 (batting): not admitted, no arm enters",
                  "candidate part 5 (pitching): not admitted, no arm enters",
                  "candidate part 6 (fielding): not admitted, no arm enters",
                  "the catcher component S3c not admitted",
                  "PE-P (pitch economy, pitching): not admitted",
                  "PE-H (pitch economy, batting): not admitted"):
        assert label in flat, label
    assert ("no candidate part is admitted: under part 9.7 eWAR v3 equals fWAR on every row, its meta says so, "
            "and the column label reads \"eWAR v3 (equals FanGraphs WAR: no part admitted)\"") in flat


def test_the_team_guard_and_the_licensed_sentences_match_the_record():
    sec = _part_12_2()
    v = _verbatim(sec)
    flat = _flat(sec)
    rec = _record()["look"]
    assert "[look] TEAM GUARD dT" in v
    for key, g in rec["team_guard"].items():
        verdict = "NON-INFERIOR" if g["non_inferior"] else "NOT NON-INFERIOR"
        assert re.search(rf"^  {re.escape(key)}\s+guard: {verdict}\b", v, re.M), key
    for part, s in rec["sentences"].items():
        if s is not None:
            assert f'"{s}"' in flat, part
    assert rec["sentences"]["batting"] is None and rec["sentences"]["position"] is None
    assert "no sentence cites the secondary estimand or the team guard's r values" in flat


def test_the_descriptive_legs_are_labelled_descriptive():
    sec = _part_12_2()
    flat = _flat(sec)
    assert "**Descriptive legs (descriptive: no verdict weight; claims nothing, part 8).**" in flat
    assert "Exposure-band bias, descriptive" in flat and "The L-B leverage disclosure, descriptive" in flat
    assert "[look] DESCRIPTIVE LEGS (descriptive: no verdict weight; claims nothing (part 8))" in sec
    assert _record()["look"]["descriptive"]["label"].startswith("descriptive")


def test_the_skill_look_owner_waived_early_read_note_follows_the_last_section():
    doc = _doc()
    note = "**Dated note, 2026-10-19: the skill look of part 12.2 is an OWNER-WAIVED EARLY READ.**"
    assert doc.count(note) == 1
    assert doc.index(note) > doc.index("**Dated note, 2026-10-19: the outcome look of part 12.1")
    flat = _flat(doc[doc.index(note):])
    assert "part 7.3 item 3 (on or after 2026-11-17)" in flat
    assert "part 7.5's own-day clause under EWV3-Q3 (a)" in flat
    assert "The look ran once and is not rerun whatever it printed (part 9.5)" in flat
