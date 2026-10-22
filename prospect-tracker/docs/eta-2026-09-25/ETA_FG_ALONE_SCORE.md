# FanGraphs-alone ETA score on the 2024 frame (registered 2026-10-22)

Candidate scored: FanGraphs' published `eta_year` alone, against the served ETA blend (registry row `eta_fg_blend`, arm B of `docs/eta-2026-09-25/ETA_FG_BLEND_GATE.md`), once, on that gate's 2024 frame, debut years only. Lab: `tools/eta_fg_alone_score.py`. Artifact of record: `data/eta_eval.json`, block `fg_blend_gate_fg_alone_2026_10_22`.

This document is committed ALONE, before the lab exists and before any read of the frame. Sections 1 to 6 are frozen at that commit. Section 7 is PENDING and receives the verbatim lab output only, after the one run.

## 1. Why, and what was already seen

Owner answer SWEEP-Q3 (2026-10-22, "Score once on 2024") to the null comparator sweep (`docs/NULL_COMPARATOR_SWEEP.md`, section 9.2): register alone one FanGraphs-alone ETA score on the 2024 frame, debut years only, against `eta_fg_blend`; run it once; record it in the row's notes; nothing served moves unless the owner flips.

The blend leans half on FanGraphs' year, and the gate registered FanGraphs alone as NOT scored on its frame (section 3, last sentence), so the served blend was never compared with its own source on the look frame. Seen before this registration, on the research lanes' spent development vintages only (gate section 1): FanGraphs alone MAE 0.874 against the 50/50 blend's 0.981, but 263 more still-active prospects marked overdue than the champion, a failure of the gate's overdue guardrail. The 2024 look (2026-09-30) scored CH40, arm A and arm B; it stored no per-row FanGraphs year for the 2024 frame, so no FanGraphs-alone figure on this frame exists anywhere before this run.

## 2. Arms, exactly

Notation as in the gate's section 2: V = 2024, FG(V) the integer `eta_year` of the player's earliest FanGraphs snapshot dated in 2024 that carries one, CH40 the served champion reconstruction, on40(V) the 40-man flag at the listing date.

- **Arm F (FanGraphs alone).** `max(V, FG(V))`. The floor at V is the floor arms A and B already carry; the number of scored rows it moves is reported.
- **Comparator B (`eta_fg_blend`, served).** `eta.fg_blend_eta_year(CH40, FG, V, on40=on40(V), arm="B")`, the function the served path calls.
- **Reported beside them, adjudicating nothing:** CH40 on the same rows (the reproduction anchor).

No constant is fitted or tuned: arm F has none.

## 3. Frame

- Rows: the gate's own construction, by calling its lab's functions unchanged (`tools/eta_fg_blend_gate.py`): `build_rows((2024,), washed_before=2025, last_full_season=2026)`, then `attach_outcomes_2024` (StatsAPI `mlbDebutDate` fetched at the run, debuts dated on or before 2026-09-27 only), then the C5 leak rule (`c5_clean`).
- Scored rows: debuted rows with a C5-clean FG(V) and a CH40 year, the gate's C1 frame (n 446 at the 2026-09-30 look).
- Debut years only: the run reads the debut year of debuted rows and nothing else. It computes no overdue count, reads no censored or washed-out row's outcome, and computes no eFV, consensus-FV, source-rank or realized-WAR quantity on any row. Nothing is cut or stratified by consensus-FV level (`docs/PROSPECT_ANCHOR_GATE.md`). The 2020 and 2021 lists stay out (the gate lab's assertion).
- Roster pulls read the gate's cached 40-man files through a private copy of that cache, so the shared `.cache` is never written.

## 4. Statistic and verdict

Shared machinery: the gate lab's `paired_boot` (player-clustered paired bootstrap, B = 2000, seed 20260928, percentile CI95), with B as the comparator and F as the arm: dMAE = MAE(B) - MAE(F), positive means FanGraphs alone is closer; dW1 = within-1y(F) - within-1y(B).

- **F BEATS B** if the CI95 of dMAE lies above zero; **B BEATS F** if it lies below zero; **TIES** otherwise.
- Reported, adjudicating nothing: MAE, within-1y and bias of F, B and CH40 on the scored rows; F against CH40 with the same bootstrap; the count of rows where F differs from B (earlier, later); the floor-at-V count.
- Instrument check (the planted-recovery rule): a planted-better arm, B moved halfway to the actual debut year and rounded half up, must read dMAE CI95 above zero against B; a planted-worse arm, B moved one year further from the actual debut year on every row (one year later where B is exact), must read below zero. If either fails the score is VOID and adjudicates nothing.

## 5. Reproduction

Before arm F is computed the lab prints the gate's `frame:` line and the CH40 and arm B row-matched MAE on the scored rows, beside the look's stored values (`fg_blend_gate_2026_09_25`: rows 1394, debuted 503, censored_active 871, fg_debuted_c5_clean 446, CH40 1.0224, B 0.8094). The inputs the frame reads (`prospects.db`, `data/debuts.json`, `.cache/mlbam_ids.json`) were rewritten after the look, so a difference is possible. A difference does not stop the run, because F and B are scored on identical rows either way; it is printed, written into the block, and named in the registry note beside the result.

## 6. The run and what it may change

- Once. The lab refuses a second scored run once the block records one (it can re-print the stored lines). A run that raises before the block is written records nothing and the owner decides on a rerun.
- Before it, the whole reporting path is dry-run on synthetic rows with no outcome read (`--dry-run`).
- Its stdout and stderr are kept in the task's output directory.
- It writes only the block `fg_blend_gate_fg_alone_2026_10_22` into `data/eta_eval.json` (the `fg_blend_gate_` prefix is one `eta_backtest.run()` carries forward). The registry row `eta_fg_blend` gets a dated line in its notes; its verdict, summary, card and served arm do not change.
- Nothing served moves: `eta.ETA_FG_BLEND_ARM` stays "B". Whatever the verdict, FanGraphs alone could not be flipped on this score alone, because the overdue guardrail it failed on the development vintages is not computed here; a flip is the owner's call and would need that guardrail read first.

## 7. Results

PENDING.
