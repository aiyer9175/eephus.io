# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026

"""The $/WAR path gate registration pins (docs/dpw-2026-09-25/DPW_PATH_GATE.md).

The registration is committed ALONE, before any code it describes exists and
before any number it governs is computed. This file pins the CRITERIA as TEXT
OF THE DOCUMENT (its section 15 list), not a result and not a code fact: the
DPW_PATH_METHOD default, the arms and the hash chain are pinned by the tests of
the commits that create that code (test_dpw_path_method_guard.py,
test_dpw_path_methods.py, test_dpw_path_lab.py).

Prose assertions run against a whitespace-flattened copy of the document, so a
re-wrapped paragraph is not a failure; an edited criterion is.

When section 18 is filled in, the result pin goes in its own file
(test_dpw_path_gate_result.py), for the reason
test_fwar_label_epoch_registration.py gives: a result pin beside a criterion
pin invites editing the criterion to match the result.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DOC = ROOT / "docs" / "dpw-2026-09-25" / "DPW_PATH_GATE.md"
RESULTS_HEADING = "## 18. Results"
AMENDMENT_HEADING = "## Amendment 1 (pre-look)"


def _doc() -> str:
    return DOC.read_text(encoding="utf-8")


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _above_results() -> str:
    d = _doc()
    return d[:d.index(RESULTS_HEADING)]


def _section(start: str, end: str) -> str:
    d = _doc()
    i = d.index(start)
    return d[i:d.index(end, i)]


def _has_all(text: str, phrases) -> None:
    flat = _flat(text)
    missing = [p for p in phrases if _flat(p) not in flat]
    assert not missing, "registration text no longer carries: " + repr(missing)


def test_the_document_exists_and_names_its_question():
    _has_all(_doc(), [
        "Does a growth rule for the per-winter $/WAR level, built only from the repository's own",
        "forecast the level one to five winters ahead more accurately than the rule",
        "behind the escalator the site serves?",
        "This gate does not govern it (section 0a).",
    ])


def test_the_arm_list_and_formulas_are_closed():
    s = _section("## 3. The candidates.", "## 4. Frames")
    _has_all(s, [
        "| `carry_destale` | `A(o) (1 + g_I(o))^h`, `g_I(o) = fa_market._destale_rate({W: A(W), W <= o}, o + 1)` | **incumbent `I`**",
        "| `carry_zero` | `A(o)` | **floor `F`**",
        "| `robust_drift` | `A(o) (1 + g_A(o))^h`, `g_A(o) = min(0.12, max(0, exp(median of d over winters <= o) - 1))` | **the one challenger `A`** |",
        "| `trend_line` | `exp(a_o + b_o (o+h))`, the OLS of ln A on year over winters <= o | **descriptive `T`**, no pass role; horizon 1 SPENT (G-0) |",
        "| `damped` | growth in step h is `g_I(o) + (g_A(o) - g_I(o)) x 0.8^(h-1)`, compounded | **descriptive `B`**",
        "| `carry_const` | `A(o) (1 + g_ref)^h`, with the `g_ref` recorded when the forecast is made | **prospective comparator only.**",
        "`d = ln(A(W)/A(W')) / (W - W')`. A gap of k winters (a winter dropped as thin, or deleted by the jackknife of section 5) enters once, annualized.",
        "The median of an odd count is the middle value; of an even count, the mean of the two middle values (Python's `statistics.median`).",
        "The [0, 0.12] clip on `g_A` matches `fa_market.py:280`, for parity.",
        "Every method needs at least 4 winters (3 differences). Fewer falls back to `carry_zero`.",
        "No arm may be added, tuned or re-parameterised after this commit. The 0.8, the clip, the 4-winter minimum, the median and the gap rule are fixed here.",
        "No method is scored beyond h = 5.",
    ])
    rows = [ln for ln in s.splitlines() if ln.startswith("| `")]
    ids = [re.match(r"\| `([a-z_]+)`", ln).group(1) for ln in rows]
    assert ids == ["carry_destale", "carry_zero", "robust_drift", "trend_line", "damped",
                   "carry_const"], ids


def test_the_truth_estimator_and_p20_are_fixed():
    _has_all(_doc(), [
        "`A(W) = sum_i G_i / sum_i disc_war_r(i)`",
        "`G_i = sticker_i x PV_r(schedule_i) / PV_r(level_i)`",
        "`G_i` is the sticker of the level deal with the same present value.",
        "estimator id `sticker_leveleq_r_over_disc_war_r_p20_v1`",
        "every exposure read from season 2020 (the hitter terms `e1`, `e2`, `e3` and the pitcher terms `ip1`, `ip2`, `ip3`, including their use inside the bounce term) is multiplied by 162/60.",
        "It is a flag, off by default everywhere. Only the dpw_path writer's enrichment sets it",
        "No other form of 2020 handling may be adopted for this gate's truth.",
    ])


def test_the_error_weights_loss_and_margin_are_fixed():
    _has_all(_doc(), [
        "`u_{o,h}(P) = (P_o(o+h) - A(o+h)) / A(o)`",
        "`w_{o,h} = 1.113763^-h / sum_{k=1..H_o} 1.113763^-k`",
        "The base 1.113763 is fixed now, whatever OD-2 answers.",
        "With all five horizons the weights are 0.2452, 0.2202, 0.1977, 0.1775 and 0.1594.",
        "`S_o(P) = sum_{h <= H_o} w_{o,h} u_{o,h}(P)^2`",
        "`Q(P) = sqrt(mean over the 8 origins of S_o(P))`",
        "**Margin M = 0.025 on the RMS scale**, fixed now.",
        "**P2, practical size.** `Q(I) - Q(A) >= M/2` on the point estimate.",
        "`c = t_{0.95, 7} = 1.894579` (8 origins minus one), unless the size run of section 6 raises it.",
        "If `size_full > 0.05` at any available `rho`, `c` is raised to the larger of the available 95th percentiles of `-Dbar / SE*` across the size draws, and that `c` holds for the rest of the block and for the verdict.",
    ])


def test_the_seeds_draw_counts_and_plant_search_are_fixed():
    s = _section("## 5. The statistic", "## 7. The decision rule")
    _has_all(s, [
        "B = 2000, seed 20260925.",
        "For draw j (seed `20260925 + j`) and each origin:",
        "a bootstrap of B = 500 (declared)",
        "the mean over 1000 draws of `Dbar(C, I)`",
        "`tol` be 0.05 times the median `SE*(C, I)` across the same draws",
        "bisect `kappa` in [0, 1].",
        "bisect `kappa` in [-3, 0] if `f(-3, sigma_g) >= 0`.",
        "halve `sigma` from `sigma_g`, at most 6 times. At EACH halved `sigma`, re-run steps 1 and 2 (the [0, 1] bracket first, then the [-3, 0] bracket) before halving again",
        "Bisection stops after 30 steps or when `|f| <= tol`.",
        "Every run below is made twice, at `rho = 0` and at `rho = 0.8`;",
        "`sigma_g = max(sd across the 8 origins of ln(1 + g_I(o)), 0.01)`;",
        "`size_status` is one of `FULL` (available at both `rho`), `PARTIAL` (available at one `rho` only;",
        "and `UNAVAILABLE` (available at neither; `c` stays 1.894579",
        "`type_m` = the mean of `Q(I) - Q(C)` over passing draws divided by the mean of `Q(I) - Q(C)` over all draws",
        "`type_m` and `detectable_gain_q` are `null` with reason `NO_PASSING_DRAW`",
        "`g*_o` is the constant growth minimising `S_o` from anchor `A(o)` over [-0.20, 0.30]: a grid scan at step 0.0005, then golden-section search inside the two grid cells around the best grid point, to a tolerance of 1e-10.",
        "If `Q(I) - Q(g*) < M/2`, no pass is possible: the block records `P2_UNATTAINABLE`",
    ])


def test_the_order_inside_the_power_block_and_power_before_cells():
    s = _section("## 6. Power and size", "## 7. The decision rule")
    _has_all(s, [
        "The lab writes the `power` block BEFORE computing any error of `A`, `T` or `B`, and the lab's test asserts the order.",
        "first the size run of item 2(a) at each `rho` (it needs the truth and `I` only), which fixes `c` for the rest of the block and for the verdict; then item 1 and its flag, evaluated with the `c` the size run left; then the detection run of item 2(b); then items 3 and 5.",
        "computed once, with the `c` the size run left (raised or 1.894579), never at both values.",
    ])


def test_the_jackknife_and_tie_rule_are_fixed():
    _has_all(_doc(), [
        "**SE_jack (primary): delete winter y EVERYWHERE**, for each y in 2015 to 2026 (12 replicates):",
        "each surviving origin's weights renormalise over its remaining horizons, with h keeping its original value",
        "`SE_jack = sqrt((n-1)/n x sum_y (Dbar_(-y) - mean)^2)`, n = 12.",
        "An origin with `|D_o| < 1e-12` is TIED.",
        "A tie is NULL or NULL_UNDERPOWERED: the incumbent and the owner's lock win ties.",
    ])


def test_the_frames_and_regime_rules_are_fixed():
    _has_all(_doc(), [
        "**Origins.** o in {2018, ..., 2025}, 8 origins.",
        "`H_o = min(5, 2026 - o)`: 5, 5, 5, 5, 4, 3, 2, 1, for **30 (origin, horizon) pairs**.",
        "S1 = origins 2018-2020 (windows cross the 2020-to-2021 step); S2 = origins 2021-2025.",
        "**REGIME targets.** 2021 (covid) and 2022 (lockout), from `fa_config.yaml:38-42`.",
        "- (a) a work stoppage (lockout or strike) is in effect on any day from the day after the previous World Series to opening day of season W;",
        "- (c) W's base CBT threshold differs by more than 10 percent from season W-1's as encoded",
        "- (d) the estimator drops W as thin (`fa_market.py:587`).",
        "A REGIME target can veto and can never confirm (section 10).",
    ])


def test_the_term_mix_weights_and_the_exposure_are_fixed():
    _has_all(_doc(), [
        "that is 0.2517, 0.3177 and 0.4306, which sum to 1.",
        "`season_discount(2026 + h)`, that is, present value at R to the base season B",
        "(`value_framework.dpw_path_forced(True, series_path=<copy>)`, never the environment)",
        "The forced-on accessors read the `dpw_path` block from a temporary copy of `git show <amendment>:data/fa_dpw_series.json`, never from the live file (section 16)",
        "`X*(5) = X(5) + sum_{k=1..4} (1 - k/5) X(5+k)`",
    ])


def test_the_verdict_and_blind_status_vocabularies_are_closed():
    s = _section("## 7. The decision rule", "## 8. The surplus effect")
    verdicts = re.findall(r"^\| \*\*([A-Z_]+)\*\* \|", s, flags=re.M)
    assert verdicts == ["PASS_DEV", "WORSE", "NULL", "NULL_UNDERPOWERED", "VOID",
                        "NOT_AVAILABLE"], verdicts
    _has_all(s, [
        "**Verdicts. The vocabulary is closed:**",
        "**Blind status, a separate closed field:** `NOT_ARMED` (no PASS_DEV), `PENDING`, `CONFIRMED`, `VETOED` (section 10).",
        "a smallest attainable sign-flip p above 0.05, or `P2_UNATTAINABLE` from the power block",
    ])
    for p in ("P1", "P2", "P3", "P4", "P5", "P6", "P7", "P8"):
        assert f"- **{p}," in s, p


def test_the_early_look_definition_and_the_tool_exception():
    _has_all(_doc(), [
        "An EARLY LOOK is any computation, on a real series, before the look of section 14, of a quantity that compares a forecast of `A` (any horizon), `B` (any horizon) or `T` (horizons 2 to 5) with a realized winter level, or of any summary of such quantities; or, on a real series before the look, of the oracle growth `g*_o`, of `Q(g*)`, of the P2 attainability bound, or of any statistic of a planted challenger (section 6).",
        "An early look VOIDS this registration, whatever it measured;",
        "running `tools/fit_dpw_forecast.py` with its registered method list (`flat5`, `trend`, `trend_cbt`) at horizon 1 only, on any series, real or synthetic, including after its build-commit refactor",
        "Horizon 1 is defined mechanically: a target winter is forecast only if the winter before it is present in the series the tool is given, and the refactored tool skips every other target.",
        "Running that tool on a real series after modifying it to compute a horizon above 1, or any method other than `flat5`, `trend`, `trend_cbt`, `carry_destale`, `carry_zero` and `carry_const`, IS an early look.",
    ])


def test_the_serve_condition_reads_od6_by_code_from_owner_at_amendment():
    s = _section("## 9. What ships", "## 10. The prospective frame")
    _has_all(s, [
        "**The SERVE CONDITION.** `DPW_PATH_METHOD` may read `robust_drift` only when the gate block's verdict is PASS_DEV, its blind status is not VETOED, and one of:",
        "- (i) the blind status is CONFIRMED (section 10). This is the conservative default and binds when the amendment commit's `data/dpw_path_owner.json` holds no OD-6 row;",
        "- (ii) the OD-6 answer in the amendment commit's `data/dpw_path_owner.json` is \"serve at the development pass, with the veto armed\" (option code `serve_at_dev_pass`).",
        "It never holds if that answer is \"never under this registration\" (`never`). **OD-6 is read only as it stood in the amendment commit.**",
        "The guard and the SERVE CONDITION read OD-6 from that record, by option code and never by an option number, and never from the live owner file",
        "the TAPER: for k = 1 to 4, `ln P(N+5+k) = ln P_const(N+5+k) + (1 - k/5) x 5 ln((1 + g_A(N)) / (1 + g_ref))`, and from N+10 on `P = P_const`, where `P_const(s) = P_served(N) (1 + g_ref)^(s-N)`.",
    ])
    veto = _section("**Veto, while `A` serves**", "**Successor.**")
    _has_all(veto, [
        "from PASS_DEV under OD-6 option (ii), in which case the single-miss rule above does not apply and the status reads PENDING until two sided non-REGIME targets land on A's side",
        "Revert to `carry_const`, and set the status VETOED, when two consecutive scored, sided blind targets are on `carry_const`'s side.",
    ])


def test_the_od7_rules_and_codes():
    s = _section("## 12. The escalator", "## 13. Served numbers")
    _has_all(s, [
        "- (a) constant: `g_ref` stays 0.0409;",
        "`g_ref` = `fa_market._destale_rate` applied to the then-current truth series through N (P20 included), and nothing else;",
        "- (c) 0, which may be chosen only if `INCUMBENT_BELOW_FLOOR` was raised at the look",
        "(option code `zero_if_floor`)",
        "into the block as `owner_after_look`. That record is valid only while the block's `INCUMBENT_BELOW_FLOOR` is true",
        "its option code `keep_0409` or `remeasure_served_rule`",
        "with no row recorded there, (a) binds. It may not alternate",
        "The value leg is PV-neutral only at `g_ref` = 0.0409 with R = 0.113763",
    ])


def test_the_blindness_check_side_rule_and_hash_chain():
    s = _section("## 10. The prospective frame", "## 11. The two switches")
    _has_all(s, [
        "each row carries `prev_sha256`, the sha256 of the previous row's canonical JSON (the first row carries 64 zeros).",
        "the sha256 of the last row and the row count are written into the `dpw_path_gate` block and into the message of every commit that appends rows, and the ledger test fails unless the file's head and count equal the block's record.",
        "Forecast rows for origin o are BLIND only if NO enriched class o+1 deal exists when they are committed, tested two ways, both recorded in the rows' `blind_check`:",
        "The count is zero, not a threshold",
        "- in `data/fa_dpw_series.json`: `usd_per_war_by_winter`, `breakdown.by_winter` (and every `pos`, `len` and `tier` cell inside it), `breakdown.realized`, `dpw_path.truth.by_winter`, `dpw_path.truth.tau_by_winter`, `dpw_path.truth.term_mix_index.by_winter` and `dpw_path.served_level.by_winter`;",
        "- in every `data/fa_class*.json`: `dpw_series_pricing`;",
        "- in `data/fa_meta.json`: `dpw_series.usd_per_war_by_winter`, `dpw_series.breakdown.by_winter`, `dpw_series.breakdown.realized` and `dpw_pricing.usd_per_war_by_winter`;",
        "- in `data/dpw_forecast_eval.json`: the `test_winters` values and the `per_winter[].winter` VALUES",
        "- in `data/fa_archive.json`: the `winters[].year` values.",
        "2. the count of class o+1 signings in `prospects.db` `fa_signings` that pass the estimator's deal filter (MLB deal with years, guarantee and MLBAM id; the filter of `fa_market.enriched_signings`) is ZERO",
        "The target is on A's side if `|ln(1 + g_A(W-1)) - r| < |ln(1 + g_ref_recorded) - r|` strictly, using the STORED growths of the two forecast rows",
        "a stored forecast is compared with a target only as `A_s(o) x forecast_usd / anchor_usd`, on the scoring vintage's anchor.",
        "An UNSIDED target is skipped by the confirmation, veto and reversion rules below exactly as a REGIME target on A's side is",
    ])


def test_the_switches_and_method_default_text():
    s = _section("## 11. The two switches", "## 12. The escalator")
    _has_all(s, [
        "- `\"carry_const\"`, with no environment override. The writer is its one read site.",
        "The environment variable `EEPHUS_SERVE_DPW_PATH=0` forces it OFF at call time. No environment value turns it ON.",
        "It never reads OD-6 from the live `data/dpw_path_owner.json`.",
        "`c_m`: 1 for `carry_const` and `carry_destale`, pi/2 for `robust_drift`.",
        "`tau_N`: the SE of `ln A(N)` from a within-winter deal bootstrap, B = 500, seed 20260925.",
    ])


def test_the_clock_table_and_the_amendment_lookup():
    s = _section("## 14. The clock.", "## 15. The artifact")
    _has_all(s, [
        "**the LATER of 7 days after the step Z entry and the day after the amendment commit**",
        "**THE LOOK. Once.**",
        "`git log -G '^## Amendment 1 [(]pre-look[)]$' --format=%H -- docs/dpw-2026-09-25/DPW_PATH_GATE.md`",
        "refuses `--real` unless exactly one commit matches.",
        "Every mention of the heading in this document is mid-line, never at the start of a line",
        "any date after this commit, EXCEPT between the fWAR epoch's steps A and Z",
    ])
    rows = [ln for ln in s.splitlines() if ln.startswith("| ")]
    assert len(rows) >= 9, len(rows)


def test_no_line_starts_with_the_amendment_heading():
    """The -G lookup is line-anchored. A heading at the start of a line in the
    registration commit would make that commit match too, and --real would
    refuse forever (or accept the wrong commit)."""
    for ln in _doc().splitlines():
        assert not ln.startswith(AMENDMENT_HEADING), ln


def test_the_single_row_band_has_a_5m_base():
    _has_all(_section("## 13. Served numbers", "## 14. The clock."), [
        "any single row +/- 50 percent (counted only where the row's base exceeds $5M in absolute value, so a near-zero contract row that changes sign does not trip it) or $15M, each listed by name;",
    ])


def test_section_18_is_empty_at_registration():
    d = _doc()
    tail = d[d.index(RESULTS_HEADING):]
    assert "**EMPTY AT REGISTRATION.**" in tail
    body = tail.split("**EMPTY AT REGISTRATION.**", 1)[1]
    # The only text after the marker is the template paragraphs and the closing
    # note; no dated entry, no verdict word used as a result.
    assert not re.search(r"\b20\d\d-\d\d-\d\d\b", body), "a dated entry was written in section 18"
    for word in ("PASS_DEV", "WORSE", "NULL_UNDERPOWERED", "VOID", "NOT_AVAILABLE"):
        assert word not in body, word


def test_no_result_is_recorded_above_the_results_heading():
    above = _above_results()
    for pat in (r"Dbar\(A, I\)\s*=\s*-?\d", r"SE\*\s*=\s*\d", r"verdict\s*:\s*(PASS_DEV|NULL|WORSE)",
                r"detection_full\s*=\s*\d"):
        assert not re.search(pat, above), pat


def test_the_text_says_dpw_path_method_defaults_to_carry_const():
    _has_all(_doc(), [
        "**`DPW_PATH_METHOD`** (`dpw_path.py`).",
        "- `\"carry_const\"`, with no environment override.",
    ])


def test_section_0_last_column_is_filled():
    s = _section("## 0. What is being decided", "### 0a.")
    rows = [ln for ln in s.splitlines() if re.match(r"\| F\d+ \|", ln)]
    assert len(rows) == 20, len(rows)
    for ln in rows:
        cells = [c.strip() for c in ln.strip().strip("|").split("|")]
        assert cells[-1], ln[:40]
