# Expansion E27 — Depth-Rank for Prospects

- prospects test n=2454; on OD depth chart 1%; of those listed as starter 32%
- prospects on a DC: debut rate 97% vs not-on-DC 11%; DC-STARTERS debut rate 100%

## Pooled prospect universe (test 2023-25)
- E11 base       debut_AUC 0.8921  PA_MAE 18.7  PA_rho 0.4366
- +depth-rank    debut_AUC 0.8921  PA_MAE 18.7  PA_rho 0.4366

## Prospects ON an Opening-Day depth chart (n=34 — where the signal lives)
- E11 base       debut_AUC 0.9697  PA_MAE 157.7  PA_rho 0.3926
- +depth-rank    debut_AUC 0.9697  PA_MAE 157.7  PA_rho 0.3926

## VERDICT — depth-rank REDUNDANT (no add), incumbents AND prospects
- Incumbents (E26): byte-identical (MAE 94.5→94.5). A regular is always his
  team's listed starter → no info beyond usage history.
- Prospects (E27): byte-identical pooled AND on the covered subset (n=34).
  Depth-chart presence is a near-perfect debut signal (on-DC debut rate 97%,
  DC-starters 100%) BUT it ≈ on_active_od / 40-man-selected, which the model
  already uses. And it's SILENT on the players who actually need projecting —
  mid-season call-ups still in AAA at Opening Day aren't on the MLB depth chart.

WHY it can't close the gap: the depth chart's FACTUAL content (who's rostered,
who's the starter) is already captured by our Opening-Day roster + 40-man
features. It confirms the obvious (broke camp = will play) and is silent on the
uncertain (future call-ups). Same mediation lesson as org/GM/manager/defense/
contract: the published artifact is redundant with the concrete roster move we
already observe.

## What the residual Steamer gap actually is (final)
Not "who's on the roster" (we have that) — it's Steamer's finer PA-MAGNITUDE
calibration for regulars (exactly how many PA), which comes from human-curated
allocation that assigns specific PA totals. That allocation is a PROJECTION
(modeled), not a factual published artifact — so acquiring it reintroduces the
external-projection dependency we deliberately dropped. The owned model is at
its genuine information ceiling; the last ~5 PA of MAE is not obtainable from
factual/owned data.
