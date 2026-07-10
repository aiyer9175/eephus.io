# xFV Phase 2 plan — modeling/calibration + xFV-primary site organization

Status target: xFV is the site's PRIMARY Future Value, consensus FV a supplementary
comparison. This plan extends the shipped Phase-2 work (main @ d4ffa05): xFV already beats
consensus + FanGraphs + MLB Pipeline out-of-sample (head-to-head Spearman 0.347 vs
0.286 / 0.280 / 0.248), with a WAG-calibrated guarded blend, injury + Statcast tilts, a
per-prospect explainer, and xFV-primary list/detail surfaces. Everything below is gated by
the program's honesty rule: forward-chained OOS, losses committed, no overfitting.

---

## Workstream A — modeling + calibration

- **A1. RPS+ / OPS+ as a backbone feature.** Feed the site's shrunk level-relative
  production (ops_plus_level / era_minus_level, the RPS+ family) into the model instead of /
  alongside the raw `obp_rel` / `iso_rel`. It is better park/level/sample-adjusted than the
  raw rels. Test historically; keep only if it earns OOS. (Franklin-Arias-class cases showed
  the raw rels and the site metric can diverge.)
- **A2. Production trajectory + durability.** Multi-season improving-vs-declining slope,
  peak-vs-final divergence, and games-played/health as real (not just penalty) features.
- **A3. Statcast / Arkmetric Tier-2 overlay (provisional).** Replace the current bounded
  Statcast+ heuristic tilt with a properly-weighted overlay validated on the ~99-pair
  forward cohort, plus faster-resolving proxy targets (reach-AAA, first-MLB K% / ISO) for
  recent cohorts. Flagged provisional; upper-level only; no historical reconstruction.
- **A4. Pitcher depth.** Stuff+ live overlay (OOS r≈0.28, the strongest modern pitcher
  signal), role-aware SP/RP outcome mapping, pitch-shape / arsenal-breadth features.
- **A5. Calibration.** Out-of-fold isotonic on the 5-bucket distribution; reliability
  diagrams overall / per-FV-tier / per-era; recency-weight training (recent cohorts matter
  more — also the cleanest answer to "scouting improved over time"); document the
  display-grade vs realized-grade calibration split.
- **A6. Methodology rigor.** Nested CV for feature selection + the blend λ (removes the
  mild OOS-selection optimism in the current greedy search); per-era + per-archetype gates;
  a track-record feedback loop that refits as cohorts resolve; registry rows stay provisional
  until a committed forward-chained artifact holds.
- **A7. Data.** Pull more historical MiLB seasons (deepen the backtest sample, esp. top
  tiers + pitchers), injury severity, and Statcast where it exists.

## Workstream B — site organization (xFV primary, consensus supplementary)

- **B1. One reusable grade component.** A single `gradeBlock(p)` used on EVERY surface:
  xFV primary badge + tier + colored xFV-vs-consensus delta + a muted "Consensus FV
  (FG / MLB / …)" reference. Replaces the per-surface inline variants so the distinction
  reads identically everywhere.
- **B2. Detail-page "Grade & Outlook" panel.** xFV headline + the explainer (consensus
  prior → ranked factors → xFV) + outcome distribution + surplus + a clean consensus
  comparison row (consensus and each source's FV side by side, with the delta).
- **B3. Finish the sweep.** Extend xFV-primary to the last two surfaces still on consensus:
  the GFX share cards and the #cmp compare view. The "Rank by xFV / Consensus" toggle
  governs which leads, everywhere.
- **B4. Per-player "xFV vs Consensus" read.** Where they agree / disagree and why (the
  factors), plus (after D) the historical track of both.

## Workstream C — glossary source comparison (xFV vs consensus, head-to-head)

- **C1.** Already: xFV is in the head-to-head Spearman/AUC bars + archetype table (OOS).
  Add a dedicated "xFV vs Consensus FV" panel: per-FV-tier and per-era Spearman/AUC, plus
  "biggest disagreements, and who was right" resolved examples (the receipts).
- **C2.** Reliability/calibration diagram for xFV vs consensus on the same cohort.

## Workstream D — FV History charts use xFV over time

- **D1. Backfill an xFV time series.** For each player's `points[]` snapshot date, score the
  as-of features with the model → an `xfv_grade` per date. Emit an `xfv_history` series into
  `xfv.json` (or a sidecar). Reuses the live-scoring path per snapshot.
- **D2. Chart.** Plot xFV as the primary line over time, consensus FV as a secondary/ghost
  line; update the OHLC sparkline + the full FV-history chart; tooltip shows both.
- **D3. Honesty caveat.** xFV history is a current-model retrospective (today's model scoring
  old snapshots), not the grade we would have shown then — labeled as such.

## Sequencing

- **Phase 2a (calibration + organization, lower risk):** B1–B3, C1, A5 (calibration),
  D1–D2.
- **Phase 2b (modeling depth, higher effort):** A1–A4, A6–A7, C2.

Each modeling change ships only if it holds out-of-sample; the loser is committed either way.
