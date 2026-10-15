# B3: the winner-take-all level cliff, a PA-weighted blend, and its NULL

> ## VERDICT: NO-SHIP (measured 2026-07-30, same day as pre-registration)
>
> The blend was built, both matrices were rebuilt under it, and the shipped
> forward-chained eval was re-run on both sides. **The primary metric regresses on
> both sides**, which is no-ship condition 1 as written below, before any result was
> seen.
>
> | cut | baseline | with blend | delta |
> |---|---|---|---|
> | **hit debuted_km (PRIMARY)** | 0.3900 | 0.3818 | **-0.0082** |
> | hit debuted_resolved | 0.3272 | 0.3279 | +0.0007 |
> | hit full_pool_km | 0.2874 | 0.2873 | -0.0001 |
> | **pit debuted_km (PRIMARY)** | 0.3060 | 0.2898 | **-0.0162** |
> | pit debuted_resolved | 0.2432 | 0.2439 | +0.0007 |
> | pit full_pool_km | 0.2560 | 0.2491 | -0.0069 |
>
> Both primary deltas are negative and sit at or inside their MDE95 (0.017 hit /
> 0.016 pit), so the honest reading is **a null that leans negative**, not a proven
> loss. Either way it does not clear the bar, and the bar was set first. The four
> mandatory controls were NOT run, because they are a test of whether a gain is real
> and there is no gain to defend.
>
> **The code stays, DEFAULT OFF**, as a registered candidate with its mechanism
> intact (`efv_dataset.LEVEL_BLEND_RATES` / `LEVEL_BLEND_ANCHOR_MOST_EXPOSED`).
> Matrices were restored from backup and verified byte-identical afterwards
> (arias ops_rel back to 0.24769633507853406, level AA).
>
> ### Why this is interesting rather than embarrassing
>
> The mechanism demonstrably does what it claims. mlbam 821041, scored on 51 A+
> plate appearances while 378 at A were discarded, moves from `ops_rel` -0.0375 to
> +0.1423; 691024 moves -0.0600 to +0.1409. These players really were being priced
> as below-average on an eighth of their own season, and the blend really does fix
> that. **It just does not predict better.**
>
> The most likely reason, and the pre-registered follow-up if anyone reopens this:
> **the level a player holds is itself signal.** Being promoted and surviving 51 PA
> at A+ may carry more information about a prospect than 378 good PA at A, because
> the promotion is an organisation's own revealed judgement. Winner-take-all reads
> that judgement; exposure-weighting deliberately dilutes it. If that is right, the
> repair is not to blend the rates but to keep the highest-level read AND add the
> lower level as a separate feature, so the model can price both rather than being
> handed an average of them. That is a different experiment with a different gate.
>
> ### What this does NOT resolve
>
> The Arias cliff is still there and is now a documented, accepted behaviour rather
> than a bug awaiting a fix. When he crosses 50 AAA plate appearances his 332-PA AA
> season leaves the feature set and his grade will move for a mechanical reason. The
> honest options are to accept it, or to run the separate-feature experiment above.
> **What is not an option is shipping this blend anyway because it would help him**:
> it loses on the metric the board is scored by, and the whole point of writing the
> gate first was to make that call unarguable.

---

# B3 pre-registration: the winner-take-all level cliff, and a PA-weighted blend

Pre-registered 2026-07-30, BEFORE any model change is written or measured, per ground
rule 12 of `docs/master-plan-2026-07-30-nine-asks.md` and `docs/EFV_GATE_STANDARD.md`.
Lane E2. Nothing in this file has been fitted yet; the numbers below are descriptive
measurements of the CURRENT shipped behaviour.

## 1. The defect, stated mechanically

`efv_dataset._milb_features` picks ONE level per season and throws the rest away:

```python
present = sorted(levels, key=lambda lv: -_LEVEL_RANK[lv])   # highest level first
for lv in present:
    if exposure(lv) >= minpa:      # 50 PA hitters / 60 BF pitchers
        level, row = lv, level_row(lv)
        break                      # <- every other level discarded
```

The loop walks DOWN from the highest level and stops at the first that clears a fixed
exposure floor. A player who takes 51 plate appearances at a higher level is scored
entirely on those 51, and a 378-PA season one rung below vanishes from every production
feature, from `level_rank`, and from `age_rel_level`.

The floor is not the problem; a floor is right. The problem is that clearing the floor is
treated as *sufficient* to discard everything else, so exposure is used as a gate and
never as a weight.

## 2. Measured blast radius on the CURRENT live board (2026 season, 2026-07-30)

Descriptive, read-only, no model change involved.

| | hitters | pitchers |
|---|---|---|
| live rows joined to a 2026 MiLB season | 1,965 | 2,298 |
| with a MULTI-LEVEL 2026 season | 701 | 790 |
| **scored on a level with LESS exposure than one being discarded** | **151 (22%)** | **149 (19%)** |
| total exposure discarded (PA / batters faced) | **52,746** | **49,946** |

Worst current cases, selected level first:

| mlbam | scored on | discarded | ratio |
|---|---|---|---|
| 821041 | 51 PA at A+ | 378 PA at A | 7.4x |
| 827759 | 66 PA at A+ | 347 PA at A | 5.3x |
| 691024 | 53 PA at AAA | 318 PA at AA | 6.0x |
| 816142 | 67 BF at A+ | 321 BF at A | 4.8x |
| 802000 | 62 BF at AA | 316 BF at A+ | 5.1x |

So roughly one in five multi-level players is currently priced on the smaller half of his
own season, and about 100,000 plate appearances and batters faced are discarded across
the two boards.

## 3. The time-critical case, and why it is NOT the justification

`franklin_arias` currently has **332 PA at AA (.318/.407/.587, ops_rel +0.248, 98.8th
percentile) and 19 PA at AAA**. He is **31 plate appearances** from the 50-PA gate. On the
day he crosses it, the selection flips to AAA, his entire AA season leaves the feature
set, and his grade moves for a reason that is purely mechanical.

**This is stated as a deadline, not as a target.** The gate below is scored on prediction
accuracy across the whole pool. If the blend does not clear its bars, it does not ship,
and Arias drops when he crosses the line. A lever justified by one player is how the
Arias counterfactual lane already produced two refuted arms; see
`ARIAS_COUNTERFACTUAL_GATE.md`. The justification is the 300 players in section 2.

## 4. Proposed mechanism (to be built, then gated)

Replace winner-take-all with an exposure-weighted blend across the levels a player
actually played in that season:

```
w(lv) = exposure(lv) / (exposure(lv) + K)      # per-level reliability weight
rate_blended = sum_lv w(lv) * rate_leveladj(lv) / sum_lv w(lv)
```

with each level's rates converted to the level-relative frame FIRST (the existing
`_resolved_norms` path), so the blend mixes comparable quantities rather than raw lines.

Open design questions to settle BEFORE fitting, and to record here when settled:

1. **K.** Candidate anchors: the existing `rate_stabilization` constants (K_AB 170 /
   K_IP 50) versus a per-level fit. Default to the shipped constants; a fitted K is a
   second arm, not the first.
2. **`level_rank` and `age_rel_level`.** These are NOT rate features and must not be
   silently blended into a fractional level. Proposal: keep them keyed on the
   MOST-EXPOSED level, which is what the existing `level is None` fallback already does
   for the sub-floor case. This is the arm most likely to move the board and should be
   togglable independently.
3. **The floor's remaining job.** With a weight, the 50-PA gate stops being a selector.
   Proposal: keep it only as a guard against a 3-PA cameo setting `level_rank`.

## 5. Gates. Pre-registered, and a miss is a NO-SHIP

Full `docs/EFV_GATE_STANDARD.md` protocol, forward-chained, both sides scored separately.

**Primary (must clear):** pooled OOS Spearman must not regress on either side, against
MDE95 **0.017 hit / 0.016 pit**. A tie is not a pass; this change rebuilds the matrices
and must earn that cost.

**Four mandatory controls:** paired bootstrap on the rho gap (player-clustered), a
zero-information control, a permutation null, and at least four time splits. A win that
does not survive all four is a null, per the label-quality lesson recorded in
`docs/PITCHER_LABEL_LEDGER.md`.

**Secondary (report, do not target):**
- Spearman(old, new) on the top decile of |ops_rel| - the churn this buys among the
  players whose production signal is strongest.
- Board churn: rank moves, top-100 in/out, and the side mix (report, never target).
- The 151 + 149 players from section 2 specifically: their grade movement is the
  mechanism check. If they do not move, the blend is not doing what it claims.

**Coupling that must be handled in the same change:** this is matrix-rebuild-coupled, so
`BOARD_RANK_BASIS_EPOCH`, `BOARD_BASIS_FINGERPRINT` and `PINNED_MIX` all move together,
and the eFV-delta movement signal needs one suppression window (the same dance the
2026-07-30 refit just went through). Coordinate with B5's closed null: reliability-K was
measured and is NOT to be re-opened as part of this.

## 6. What would make this a NO-SHIP, written down in advance

- Pooled Spearman regresses on either side, or gains less than its MDE95.
- The gain does not survive the zero-information control or the permutation null.
- The gain is concentrated entirely in the 300 affected players and reverses on the rest
  (that would be a re-weighting artifact, not a better read).
- The blend requires blending `level_rank` to work, and blending `level_rank` alone
  moves the board more than the accuracy gain justifies.

If it is a null, it gets a loss-ledger row and a registry entry like every other null in
this program, and the Arias cliff is then a known, accepted, documented behaviour rather
than a bug we failed to fix.

---

## Amendment 2026-10-15 (owner decision EW3-21, task EFV_FIX_A_CODE item A5)

Registered before any number. The eFV driver audit found that a 50 to 99 PA stint sets
`level_rank` at face value (317 live hitters took their level from under 100 PA in 2026).
The ANCHOR arm (`efv_dataset.LEVEL_BLEND_ANCHOR_MOST_EXPOSED`) is narrowed to that case: with
the arm on, the level features re-key onto the season's most-exposed level only when the
selected level's own exposure is under twice the selection floor (hitters under 100 PA,
pitchers under 120 BF) and another level carried more. A stint at or above twice the floor
keeps the highest-level read, which the verdict above names as signal (the promotion is
the organisation's own judgement). The RATES arm is untouched.

The flag stays False. It flips only on this gate's section 5 read (primary pooled Spearman
must not regress on either side, MDE95 0.017 hit / 0.016 pit, with the four controls), run on
the development frames by EFV_FIX_B_REFIT with its re-fit, never alone. The task measures
only the outcome-blind count of live rows whose level would move (docs/efv-v2/EFV_FIX_A.md).
