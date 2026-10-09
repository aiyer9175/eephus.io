# eFV v4: results for the owner (2026-10-09)

Plain language. Every number is copied from `data/_labs/efv_v4/efv_v4_select.json` and
`data/_labs/efv_v4/efv_v4_spent.json`; the rule and the full tables are in
`docs/efv-v2/EFV_V4_BACKTEST.md`. No em-dashes. Nothing here is cut by consensus-FV cell.

## The one-line answer

eFV v4 does not ship. One new-source column cleared the development bar (the scouting report's
"writer's implied FV minus stated grade" on pitchers), it lifted the development frames by less
than half a hundredth, and on the reserved list vintages it read slightly below the served
model. The served eFV (V2) stays as it is; the board, grades and dollars do not move; the
honest claim is still "ties consensus".

## What was tried

Everything the research report named as testable today was built, read in its own lane, and
then offered to one selection:

| source | columns offered | what happened in the selection |
|---|---|---|
| MiLB injured-list stints 2008 on, from the cached transactions feed | 13 | none within +0.0020 on list vintages; the hitter timing columns move only the debut frame and by under 0.0015 |
| non-roster spring invitations | 4 | none; -0.0006 to -0.0001 on list vintages |
| pitch-by-pitch discipline (whiff, contact, called strike, first-pitch strike) | 8 | the pitcher called-strike rate qualified in round 1 (+0.0028) and lost to the report field; after it, +0.0014 |
| batted-ball trajectory and spray | 2 | both negative |
| population-fitted MiLB-to-MLB translation (KATOH-style) | 2 | pitchers +0.0103 on list vintages but -0.0147 on the debut frame, outside the tolerance; hitters nothing |
| historical rater panel (BA, BP, FanGraphs 2014 to 2016, ESPN) | 2 | hitters -0.0123; pitchers +0.0019 |
| LLM extraction of the as-of scouting reports (12 fields) | 9 | the pitcher "writer minus stated" field qualified (+0.0081) and was admitted; every hitter field reads 0 against V2 on list vintages |

The 40 columns are the arms the lanes' own reads admitted in at least one fold; 22 more never
entered any fold and were not offered. A step was admitted only if it lifted the list-vintage
development frame by at least +0.0020 and did not lower the debut frame by more than 0.0020,
greedy, at most six steps. One step was taken; the second round admitted nothing.

## The table (within (side, vintage) Spearman, v4 minus served eFV V2; pooled over sides)

| frame | n | v4 | V2 | consensus | v4 minus V2 (CI95) | v4 minus consensus (CI95) | role |
|---|---|---|---|---|---|---|---|
| lv_dev, list vintages 2017 to 2019 | 2,862 | 0.1715 | 0.1676 | 0.1792 | +0.0039 (-0.0018 to +0.0100) | -0.0077 (-0.0308 to +0.0141) | development, chosen on it |
| vm_dev, debut cohorts 2017 to 2023 | 830 | 0.3725 | 0.3713 | 0.3814 | +0.0012 (-0.0060 to +0.0084) | -0.0088 (-0.0389 to +0.0182) | development, chosen on it |
| R-LV, list vintages 2020 and 2021 | 2,349 | 0.1483 | 0.1511 | 0.1494 | -0.0027 (E_refit -0.0105 to 0.0) | -0.0011 (E_refit -0.0242 to +0.0163) | spent (read once by v3 on 10-08) |
| R-VM, the 2025 debut cohort | 147 | 0.3739 | 0.3739 | 0.3333 | 0 (identical rows) | +0.0406 (E_refit -0.0830 to +0.1251) | spent (read once by v3 on 10-08) |

Pipeline still leads every eFV on list vintages (v4 minus Pipeline -0.0422 on R-LV, interval
below zero), as it did for V2 and v3.

## Ship or not

Not. The owner's rule (EW2-10) was: ship only if v4 beats served V2 on all four frames. It beats
V2 on the two development frames it was chosen on and on neither spent frame. `EFV_V4_ON` stays
False. No served number moved in this task; the two development rows now on the Source
Comparison page are drawn hollow as development reads, which is the honest record.

## Why it came out this way, in plain words

- Hitters are where eFV trails consensus (about -0.02 on both development frames), and not one
  of the 24 hitter columns from any new source moved the hitter order on list vintages. The
  graders already price what those columns carry, or the columns are noise at this sample.
- Pitchers took one column, the report field, worth +0.008 on 1,400 development rows. On the
  reserved rows it entered one fold (2021) and cost -0.011 there, the same fold and sign as
  v3's scouting command grade. A +0.002 bar on 1,400 rows fits noise; this is the second time
  a pitcher text or grade column has done exactly that.
- The 2025 debut cohort could not test the column at all: the report extraction covers the
  2013 to 2019 vintages, so 3 of 95 pitchers carried a value and the fit took none. R-VM for v4
  is a repeat of V2's own numbers.
- The reserved floors are 0.016 to 0.018 on R-LV and 0.09 on R-VM. Nothing on this menu was
  ever going to clear them; the research report said so before the build (modal sum under
  +0.01), and the build confirms it.

## What this closes and what stays open

- Closed on the frames that exist: the new-source frontier (seven families, 40 offered columns,
  one admitted, none shippable), on top of the 420 closed arms on existing columns and the v3
  configuration menu.
- Still open, and not measurable before new vintages resolve: the consensus-method item (DS-Q4,
  Pipeline-heavy anchoring, the one lever with a known +0.005 to +0.015 on R-LV, which moves the
  comparator); extending the report extraction to the 2020 to 2026 vintages so a future reserved
  read can test the text family at all; the 2027 registration with the forward sources (tracked
  data, projections retained nightly).

## Questions recorded for the owner (defaults applied, nothing stopped)

1. Spent-read ledger rows. Default taken: NONE (the spent read lives in its artifact and the
   docs; the ledger's reserved rows stay the v3 look). Alternatives: write two rows with role
   reserved labelled spent (they would show as a second look on the chart, which they are not);
   write them as development rows (misnames the frames).
2. The report-extraction corpus. Default taken: left at vintages 2013 to 2019 (what the lane
   built; the reserved frames could not test the text family). Alternative: extract the 2020 to
   2026 documents (about 7,000 more, in-session extraction, no fetch) so the next reserved read
   can; it changes nothing served and costs extraction time only.
3. The population translation pitcher column (+0.0103 on lv_dev, -0.0147 on vm_dev, -0.0150 on
   R-LV spent). Default taken: closed under the rule as written. Alternative: carry it as a
   registered 2027 arm for list-vintage frames only, since the owner line EW2-12 approved the
   row population as a source.
