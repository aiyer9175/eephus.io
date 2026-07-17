# Expansion E10 — Organizational Promotion Behavior

- universe: 21508 AA/AAA pre-debut seasons, org attributed to 90%
- player-only OOF debut model on 17984 seasons (target years 2011-2026); AUC 0.888

## Org aggressiveness leaderboard (mean debut residual, all years)
(+ = promotes prospects FASTER than talent predicts)
Most aggressive:
   New York Yankees         +0.047
   Toronto Blue Jays        +0.038
   Houston Astros           +0.033
   Kansas City Royals       +0.029
   Los Angeles Angels       +0.028
   St. Louis Cardinals      +0.026
Most conservative:
   Chicago Cubs             +0.003
   New York Mets            +0.001
   Milwaukee Brewers        -0.000
   Florida Marlins          -0.002
   Philadelphia Phillies    -0.005
   Office of the Commissioner -0.015

## Persistence
- year-over-year AR(1) of org aggressiveness: r = 0.074 (n=397 org-year pairs)
- split-half (odd vs even seasons): r = 0.295 (n=31 orgs)
- between-org variance share of org-season aggressiveness: 9.4% (rest = year-to-year noise)

## OOS predictive value — does PAST org behavior predict FUTURE debut?
 year    n  AUC_base  AUC_org  Brier_base  Brier_org
 2019 1219    0.9231   0.9295      0.0504     0.0479
 2020 1452    0.9484   0.9547      0.0271     0.0273
 2022 1201    0.9284   0.9269      0.0719     0.0705
 2023  836    0.8542   0.8563      0.0699     0.0693
 2024  832    0.8578   0.8569      0.0762     0.0756
 2025  786    0.8804   0.8734      0.0800     0.0810
 2026  814    0.8945   0.8932      0.0566     0.0565

  pooled AUC: base 0.8981 -> +org 0.8987  (Δ +0.0006)
  pooled Brier: base 0.0617 -> +org 0.0612  (Δ -0.0006)

## Verdict
See AR(1)/split-half (is it stable?) + OOS Δ (does it predict?). Feature ships to Playing Time+ ONLY if OOS AUC/Brier improves.

---

## Supplementary — is the org effect mediated by the 40-man decision?

The player-only model includes `selected_40man` (added to the 40-man roster
by Mar 25) — itself the org's promotion decision, observed at the prediction
date. Removing it and re-testing the org increment:

| model | pooled OOS AUC (2019-26) |
|---|---|
| player WITH 40-man + org trailing | .8987 (Δ +0.0006 vs base) |
| player WITHOUT 40-man, base | .8793 |
| player WITHOUT 40-man + org trailing | .8886 (**Δ +0.0094**) |

Org tendency is a real but ~16× larger signal when the 40-man move is hidden.
**The org effect is fully mediated by the 40-man selection.** Teams express
their promotion aggressiveness through a concrete, observable roster action —
and Playing Time+ already uses that action.

## VERDICT (Q5)

- Orgs have a **weak, mostly-noise** promotion tendency: split-half r .295,
  AR(1) .074, only **9.4%** of org-season aggressiveness is stable between-org
  identity. The popular "aggressive org" narrative is weakly supported at best
  (Astros/Royals/Angels top; Rays/Dodgers/Orioles NOT at the extremes).
- The tendency **does not predict future debut** beyond features Playing
  Time+ already has (+0.0006 AUC). Its real signal (+0.0094 without 40-man)
  is **fully captured by the 40-man-selection feature**.
- **REJECT org fixed effects for the debut target.** Per the FINAL RULE
  (must improve OOS prediction + complexity justified), org dummies/hierarchy
  do not earn inclusion.

## Implication for GM (Q6) and Manager (Q7)

If the *organization's* promotion signal is fully mediated by the observable
40-man move, GM and manager identity are very unlikely to help the **debut**
target either — their influence also flows through roster moves we already
observe. GM/manager effects should be tested on targets NOT mediated by a
single observable transaction: **platoon share, in-season rest/start rate
given equal roster status, role assignment**. Manager data (E02) is ready;
GM data still needs external collection. Debut-target GM/manager work is
DEPRIORITIZED on this evidence.
