# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The FA destination gate registration pins (docs/fa-2026-10/FA_DESTINATION_GATE.md).

The registration is committed ALONE, before any code, coefficient or number of
the destination model exists (plan Part 8 P8.5, FAA-0, task Q9_02). This file
pins the protocol text by its hash, the clauses and floors as text of the
document, the 'Read to write this' section, and an EMPTY results section. It
reads the document only.

Prose assertions run against a whitespace-flattened copy of the document, so a
re-wrapped paragraph is not a failure; an edited criterion is, and so is any
change to the hashed sections (file a dated amendment in section 18 instead).

When the look fills section 19, its result pins go in their own file and the
empty-results test below is retired in that same commit, for the reason
test_dpw_path_gate_registration.py gives: a result pin beside a criterion pin
invites editing the criterion to match the result.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "fa-2026-10" / "FA_DESTINATION_GATE.md"
FROZEN_FROM = "## 0. Read to write this"
AMENDMENTS_HEADING = "## 18. Amendments"
RESULTS_HEADING = "## 19. Results"
#: sha256 of the whitespace-flattened text from section 0 up to section 18's
#: heading, as registered on 2026-10-08 (section 17 of the document).
PROTOCOL_SHA256 = "cab64290169c7577c74db3181fae35ffffd505389010113d836749818155bda8"


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _has_all(text: str, phrases) -> None:
    flat = _flat(text)
    missing = [p for p in phrases if _flat(p) not in flat]
    assert not missing, "registration text no longer carries: " + repr(missing)


def _section(start: str, end: str) -> str:
    d = _doc()
    i = d.index(start)
    return d[i:d.index(end, i)]


def _protocol_text() -> str:
    return _flat(_section(FROZEN_FROM, AMENDMENTS_HEADING))


def test_document_is_dated_and_registered():
    lines = _doc().splitlines()
    assert lines[0] == "# FA destination gate: FA_DESTINATION_GATE (registered 2026-10-08)"
    status = [ln.strip() for ln in lines if ln.strip().startswith("Registration status:")]
    assert status == ["Registration status: REGISTERED"]


def test_protocol_hash_is_frozen_and_printed():
    got = hashlib.sha256(_protocol_text().encode("utf-8")).hexdigest()
    assert got == PROTOCOL_SHA256, (
        "sections 0 to 17 changed; file a dated amendment in section 18 instead")
    printed = re.findall(r"^Protocol hash: `([0-9a-f]{64})`", _doc(), flags=re.M)
    assert printed == [PROTOCOL_SHA256]


def test_no_dash_characters():
    d = _doc()
    assert chr(0x2014) not in d and chr(0x2013) not in d


def test_estimand_registry_row_and_reserved_names():
    _has_all(_doc(), [
        "Model id `fa_destination`.",
        "P(club signs player | the player signs a major-league deal this winter): for each free agent, a 30-vector over the 30 clubs",
        "whose entries lie in (0, 1) and sum to 1.",
        "**Registry row** `fa_destination`",
        "This commit writes no registry row.",
        "`FA_DESTINATION_SERVE` (default False)",
    ])


def test_owner_answers_and_the_incumbency_statement_precede_any_result():
    _has_all(_section("## 1. The question", "## 2. Estimand"), [
        "FA-DEST-1 (a) yes, with re-signing",
        "FA-DEST-3 (b) also a retro comparator",
        "FA-DEST-4 (a) no market-size arm",
        "**Stated before any number, under FA-DEST-1 (a).** Clauses C1 and C2 are expected to pass from re-signing alone: on these winters Gate 3's logistic with incumbency already scored MRR 0.2679 and top-1 0.1787 against the served analog's 0.1669 and 0.0520. A serve therefore says nothing about the Ledger block. Only C3 (P against N, with the L_perm twin) answers the owner's ask.",
    ])
    d = _doc()
    assert d.index("**Stated before any number") < d.index(RESULTS_HEADING)


def test_what_never_moves():
    _has_all(_section("## 3. What never moves", "## 4. The frame"), [
        "**The Fit** (`fa_fit.fit_scores`, `fa_config.yaml` `fit.weights`) stays byte-identical",
        "`data/fa_class.json`, `data/fa_meta.json`, `data/fa_gate2_eval.json` and `data/fa_dpw_series.json` stay byte-identical.",
        "`persist=False, persist_dpw=False`",
        "never calls `run_fit_gate`",
        "`data/fa_gate3_eval.json` stays byte-identical.",
        "The lab never calls `fa_export`.",
    ])


def test_step0_reproduces_the_registered_numbers_with_the_drift_rule():
    s = _section("### 4.1 Step 0", "### 4.2")
    _has_all(s, [
        "| random | 1,173 | 0.0333 | 0.1667 | 0.1332 |",
        "| payroll_only | 1,173 | 0.0384 | 0.1722 | 0.1350 |",
        "| behavior_only | 1,173 | 0.0418 | 0.2080 | 0.1515 |",
        "| live_analog | 1,173 | 0.0520 | 0.2293 | 0.1669 |",
        "| fitted_full | 1,080 | 0.1787 | 0.3065 | 0.2679 |",
        "| banded twin (`teamfit_conditional_gate.chain_candidate`) | 1,173 | 0.0546 | 0.2097 | 0.1628 |",
        "**Drift rule (the TEAMFIT gate's):** a difference in any of them is disclosed in the artifact, registered value beside today's, and the run proceeds on the current frame",
    ])


def test_primary_frame_is_the_gate2_forward_prediction():
    s = _section("### 4.2 The primary frame", "## 5. Features")
    _has_all(s, [
        "`fa_backtest.run_market_gate(persist=False, persist_dpw=False)`",
        "`tools/arb_fa_gate_d.py@64bf1bb3:123-130` (in `_gate2_rows()`)",
        "`fa_backtest.py@410cccce:486-491`, appended at `:603-607` (in `run_market_gate()`)",
        "**Join.** On (winter, player_key) against the Gate 3 signings. A Gate 3 signing with no collected tuple is dropped and counted;",
        "`build_rows` gains one keyword argument, `price_override`, default None.",
        "With the default, `build_rows()` returns rows byte-identical to today's, pinned by a row-hash test in the build task.",
        "at least 30 training positives",
    ])


def test_features_and_exclusions():
    s = _section("## 5. Features", "## 6. The model")
    for fid in ("| F | fit_analog |", "| L1 | fa_share_3 |", "| L2 | payroll_level |",
                "| L3 | tax_multiplier |", "| L4 | qo_cost |", "| I1 | incumbent |"):
        assert fid in s, fid
    _has_all(s, [
        "0.40 need + 0.05 window + 0.05 afford + 0.05 park + 0.45 behavior_cond",
        "`ledger_export.py@64bf1bb3:305-341` (in `computed_cbt_bill()`)",
        "`fa_cba.pick_forfeiture(tier, date(Y-1, 12, 1))`",
        "**Excluded, with reasons.** Forward commitments and forward space",
        "market size (FA-DEST-4 (a);",
    ])


def test_model_penalty_and_arms():
    _has_all(_section("## 6. The model", "## 8. Metrics"), [
        "Only tau, beta (four terms) and gamma are fitted, on the scored frame's winters before Y, and scored on Y (forward chain).",
        "**Penalty, fixed now:** minimize the summed negative log likelihood over the fold's signings plus 0.5 x lambda x (the sum of squared beta), lambda = 1.0",
        "**P** (primary): F + L1-L4 + I1.",
        "**N** (ablation): F + I1.",
        "**L_perm** (control): P with L1-L4 permuted across clubs within each winter",
        "`numpy.random.default_rng(7 + Y).permutation(30)`",
        "`payroll_space` (Gate 3's `payroll_only`, ranks by afford); `payroll_level` (ranks by L2, richest first);",
        "`incumbency_only` (his club first, then uniform",
    ])


def test_metrics_and_floors():
    _has_all(_section("## 8. Metrics", "## 10. Clauses"), [
        "uniform = ln 30 = 3.4012",
        "ECE in ten bins",
        "**MRR floor: the paired MDE95 0.0139** on this frame",
        "2,000 draws of `rng.integers(0, n, n)`, the unit one signing with its 30 rows.",
        "`rng = numpy.random.default_rng(7)`",
        "The lab writes the floors block (this SD and floor, and the resample seed and count) to the artifact BEFORE it computes any arm's mean metric, any difference or any clause",
        "Holm at family alpha 0.05 over the two",
    ])


def test_clauses_are_verbatim_from_the_lane():
    s = _section("## 10. Clauses", "## 11. Ship rule")
    _has_all(s, [
        "- C1 vs payroll: P beats `payroll_space` and `payroll_level` on MRR by more than MDE95, and on top-5.",
        "- C2 vs the Fit: P beats `live_analog` on MRR by more than MDE95.",
        "- C3 the Ledger block (the ask's own test; Holm over MRR and log loss): P beats N on at least one after Holm, and L_perm reproduces less than 60% of the P minus N lift (the Gate D control rule, `docs/ARBITRATION_GATE.md:358-401`).",
        "- C4 calibration: out-of-fold log loss below ln 30 by more than its floor; reliability slope within 0.8 to 1.2.",
        "- C5 stability: P at or above `payroll_space` MRR in at least 7 of the scored winters (the Gate 3 \"7 of 9\" reading).",
        "**C5** passes when MRR(P) is at or above MRR(payroll_space) in at least 7 of the scored winters; fewer than 7 scored winters fails C5.",
    ])
    for c in ("C1", "C2", "C3", "C4", "C5"):
        assert f"- **{c}** passes when" in s, c


def test_ship_rule():
    _has_all(_section("## 11. Ship rule", "## 12. Reported"), [
        "C1, C2, C3, C4 and C5 all pass: serve P.",
        "C1, C2, C4 and C5 pass and C3 does not: serve N and record the Ledger block as a NULL in the artifact's loss ledger",
        "N is served only if C1, C2, C4 and C5 also pass with N in P's place; otherwise nothing serves.",
        "C1 or C2 fails: serve nothing and record the loss.",
    ])


def test_industry_comparators_both_registered():
    _has_all(_section("## 13. Industry comparators", "## 14. The forward read"), [
        "(FA-DEST-3 (b))",
        "**Scoring rule, both comparators.**",
        "a tie among k clubs credits 1/k to each tied club.",
        "**Retro, offseasons 2015-16 to 2025-26.** Input `data/_labs/fa_predictions/mlbtr_retro_2015_2025.json`",
        "this task fetches nothing",
        "the head-to-head covers class years 2019-2026",
        "**Forward, the 2026-27 class.** FA_PRED_CAPTURE's November capture keeps MLBTR's predicted team",
    ])


def test_forward_read_lockout_and_regime_flag():
    _has_all(_section("## 14. The forward read", "## 15."), [
        "If the model passed and is frozen before the 2026-27 qualifying-offer acceptance deadline",
        "The Fit stays on the pre-free-agency frame, byte-identical under every OUTLOOK answer",
        "Otherwise the first forward read is the 2027-28 class",
        "A lockout after the 2026-12-01 CBA expiry delays the read",
        "puts a regime flag on L3 and L4, which are reported under the flag and not refit.",
    ])


def test_look_order_crash_protocol_and_early_look():
    _has_all(_section("## 15. Order", "## 16."), [
        "Once, task Q9_04b",
        "(2) stdout and stderr teed to the task's output directory before anything else runs.",
        "On any exception after step (3) begins: STOP, no rerun, and write OWNER_QUESTION.md",
        "An early look VOIDS this registration.",
    ])


def test_read_to_write_this_section_discloses_the_reads():
    s = _section(FROZEN_FROM, "## 1. The question")
    _has_all(s, [
        "**No destination model exists, so no read below was joined to a destination model's output.**",
        "**payroll_only against random comparison**: MRR 0.1350 against 0.1332",
        "**the final-winter logistic without incumbency** signs need +0.513, window -0.168, afford -0.068, park +0.010, behavior +0.337.",
        "**`fitted_full` and its incumbency result**",
        "the per-winter refit (`fitted_transfer`) scored MRR 0.1479",
        "scored 0.1660 against the shipped weights' 0.1669",
        "**The served 2027 class's first-fit counts**",
        "CHW 50, WSN 46",
        "**The 2024-2026 league dollar shares**",
        "None of these reads was joined to a destination model's output, because none exists.",
    ])


def test_results_section_is_empty():
    d = _doc()
    body = d[d.index(RESULTS_HEADING) + len(RESULTS_HEADING):]
    assert _flat(body) == "EMPTY AT REGISTRATION."
    assert not re.search(r"\d", body)
