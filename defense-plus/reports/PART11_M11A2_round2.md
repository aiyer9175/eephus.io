# Part 11 / M11-A round 2 — regular-retention + Defense+ decomposition
Date: 2026-06-16 · `pipeline/11a2_survivorship_round2.py` (builds on M11-A)

## (a) Survival margin matters: insurance is at the ROSTER margin, not the JOB margin
Premium-position offensive discount (wOBA+ points a C/SS/CF/2B needs *less* than a 1B/LF/RF/DH to survive, equal age/PA):

| Survival bar | base rate | premium discount |
|---|--:|--:|
| **≥50 PA next yr** (stay in MLB) | 0.88 | **11.4 wOBA+ pts** |
| **≥400 PA next yr** (remain a regular) | 0.51 | **4.1 wOBA+ pts** |

**This corrects the going-in hypothesis** (I expected the gap to *widen* for regulars). It does the opposite: the defensive discount is **concentrated at the roster-survival margin and largely collapses at the regular-job margin.** Defense strongly insures your *roster spot* — the glove-first utility/bench/late-defense player sticks around on ~11 fewer points of offense — but to hold a *starting job* (≥400 PA) you still essentially have to hit; premium positions get only a modest ~4-point break. "Defense as career insurance" is real, but it's insurance against being *cut*, not against being *benched*.

## (b) Decomposing the discount: defensive value vs scarcity
Adding the Module-06 **Defense+ talent (total runs, incl. positional adjustment)** as a covariate, on the Statcast-era sample (2021–2024, n=1,263):

| | discount at ≥50 PA margin |
|---|--:|
| base premium discount (no defense control) | 11.5 wOBA+ pts |
| after controlling total Defense+ runs (= residual SCARCITY) | 6.8 pts |
| **explained by measured defensive value** | **4.7 pts (≈41%)** |

- **~41% of the survival discount is genuine, measurable individual defensive value; ~59% is residual "scarcity"** — positional/option value beyond even the standard positional adjustment (which `dplus_total` already includes): roster flexibility, a smaller replacement pool, the difficulty of finding *any* competent SS/C.
- **41% is a lower bound** on the defensive-value share: Defense+ is measured with error, so it under-controls; perfect defensive measurement would explain more, leaving *less* pure scarcity. True scarcity ≤ 59%.
- Defense+ has a direct survival effect: **+0.053 logit per defensive run ≈ 0.69 wOBA+ points of survival value per defensive run** — i.e., defense buys survival directly, not only through position. (The ≥400-PA margin had no discount left to decompose — consistent with (a).)

## Why this needed Defense+ first
Round 1 could only say "premium positions survive on 13 fewer points." Only with a per-player Defense+ talent number could we split that into *defensive value* (≈41%, lower bound) vs *positional scarcity* (≤59%) — the two have very different implications for Career+: defensive-value insurance scales with how good a glove you are; scarcity insurance accrues just from manning the position.

## Caveats
- (b) is Statcast-era only (2021–24), thin per position → directional, not definitive; revisit when more Defense+ seasons accrue.
- `dplus_total` includes the standard positional adjustment, so the residual is "premium survival beyond total measured defensive value incl. posadj" = scarcity + Defense+ measurement error.
- Offense = era-adjusted wOBA+ only (no park/positional offensive adjustment).

## Files
- `pipeline/11a2_survivorship_round2.py`
