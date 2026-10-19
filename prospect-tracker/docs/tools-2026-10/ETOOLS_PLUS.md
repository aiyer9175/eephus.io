# eTools+ (ETOOLS_PLUS): registration

Owner decision EW3-28 (2026-10-15, "Can we also make eTools+?", answered COMPOSITE): one
overall tools number per player, the eTools weighted by their eFV weights from
EFV_ETOOLS_REWEIGHT, 100 = the average prospect of the side, 10 points per standard deviation,
shown as one tools summary on cards and the board. Registered 2026-10-19, alone, before any
eTools+ value exists and before the descriptive check below is computed. No em-dashes.

## 0. Preconditions

- EFV_ETOOLS_REWEIGHT is done: registered 49ca37be, code 5350c182, read once 518eaf36
  (`docs/efv-v2/EFV_ETOOLS_REWEIGHT_RESULTS.md`). Neither candidate passed its ship rule, so the
  served eFV keeps the consensus tool inputs; the read still carries the production fit of
  every candidate, with each tool slot's weight, in
  `data/_labs/efv5/efv_etools_reweight_fit.json` (`production.<candidate>.tool_weights`).
- ETOOLS_SITEWIDE_FLIP is done (135a0912, owner decision EW3-27): `data/etools.json` carries the
  shown eTools for eHIT, ePOW, eSEL, eBAT, eFB and eCMD.

## 1. The weights (default D-1)

The re-weight read left the owner a question (its owner question 2) with default (a): eTools+
takes the tool weights of candidate E, the head with the eTools in the four tool slots. No
answer is on file, so the default applies. The weight of a tool is the slot's
`weight_pct_equiv` (percentile points of the order per standard deviation of the tool, the
head weight included) in `production.E.tool_weights`, normalized to sum to 1 within the side.

| side | tool | E weight | normalized |
|---|---|---|---|
| hitters | ePOW (game power slot) | 0.009079 | 1 |
| hitters | eHIT (hit slot) | 0 (refused by the one-sign rule DS-06) | 0 |
| pitchers | eFB (fastball slot) | 0.065812 | 0.5397 |
| pitchers | eCMD (command slot) | 0.056141 | 0.4603 |

Tools in the definition that carry no weight, and so contribute nothing:

- hitters: eHIT (refused in its slot); eSEL and eBAT (in no slot of the head: their consensus
  grades start in 2021 and reach one debut class); raw power and speed (eRAW and eSPD are not
  passing eTools; the speed slot is sensitivity arm ES only); consensus field and arm (no slot
  in the head);
- pitchers: consensus slider, curveball and changeup (no slot in the head). The head carries a
  consensus breaking-ball column (`w2s_brk_pit`) among its v2 stat drivers, outside the tool
  slots; it is not a tool slot of the re-weight and is not read here (default D-5, with the
  hitter head's `w2s_posval_hit` and `w2s_pwr_present_hit`).

Plainly: under these weights hitter eTools+ is ePOW rescaled, and pitcher eTools+ is about 54%
eFB and 46% eCMD. The card tooltip names every tool with its weight, zeros included.

## 2. The values

A tool's value is the served eTool (`etool`, two decimals, the re-centred construction) in
`data/etools.json`. A weighted tool with no eTool on file is MISSING; it does not fall back to
the consensus grade (default D-2: eTools+ summarizes eTools).

## 3. The pool for 100 and the refresh rule

The pool of a side is every player of that side in `data/etools.json` carrying at least one
weighted eTool: the live graded prospects the eTools builder scored (default D-3). At
registration that is 829 hitters with ePOW and 803 pitchers with eFB (801 with eCMD). A graded
prospect with no minor-league line the builder can score has no eTool and so no eTools+.

Refresh: `python etools_plus.py` rebuilds the sidecar from the current `data/etools.json`; it
runs after every `python etools.py --preview` (which writes `data/etools.json`). The sidecar
records the sha256 of the `data/etools.json` it read, and a test fails when the two differ, so
a stale sidecar cannot ship.

## 4. The scale

Within a side, over the pool:

- z_t = (x_t - mean_t) / sd_t for each weighted tool t, mean and population sd over the pool
  members carrying t;
- S = sum over available t of w_t z_t, divided by the sum of the available w_t (a missing tool
  takes the weighted mean of the available ones);
- eTools+ = 100 + 10 x (S - mean S) / sd S over the pool, rounded to the nearest whole number
  (halves up; a plus stat rounds to nearest);
- coverage = the sum of the available weights (1 when every weighted tool is on file), shown
  beside the number when below 1; coverage 0 means no eTools+.

Each tool's contribution in eTools+ points is 10 x w_t z_t / (sum of available w) / sd S; a
centring term -10 x mean S / sd S completes the sum to the unrounded eTools+ minus 100.

## 5. Where it shows

- the sidecar `data/etools_plus.json` (per player: eTools+, coverage, each tool's weight, shown
  eTool and points; per side: the weights, pool size, mean and sd of S, the source sha256s);
- PROSPX: an eT+ chip on the list row's tool strip (the card summary) with a tooltip listing
  each tool's contribution; an eTools+ sort on the board; an eTools+ line on the player page's
  Tools card. Shown while the eTools are the shown grades (the eTools flag);
- a glossary entry `etools_plus` and a registry row `etools_plus` (verdict provisional,
  descriptive).

## 6. The descriptive check (registered here, run once after the build)

Frames: the development frames of EFV_ETOOLS_REWEIGHT only, lv_dev (list years 2017 to 2019)
and vm_dev (debut classes 2017 to 2023), the rows each frame scores. Reserved frames (list
vintages 2020 and 2021, debut cohorts 2025 and later) are never read.

As-of eTools: the read's Part 1 values (`part1_pairs`), each eTool from its fold's
forward-chained fit (board years before the decision year, the fold's test players out) at the
row's own consensus grade, so eTools+ is as of the list date. eTools+ is computed by section 4
inside each (frame, side, year) group, the group's rows being the pool.

Statistics, by frame and side: the within-(side, year) Spearman of eTools+ with (a) the eFV
outcome label the re-weight read used (`outcome.war`, the eWAR v2 label) and (b) consensus FV
(`prospx_consensus`), pooled as the row-weighted mean over groups of 20 or more rows. Printed
beside, as references with the same statistic: each weighted eTool alone, and the same weights
applied to the consensus tool grades. Point values and row counts; no bootstrap.

Not done: no cut by consensus-FV level and no stratum named after an FV cell
(`docs/PROSPECT_ANCHOR_GATE.md`); no verdict and no comparison. eTools+ is DESCRIPTIVE: no copy,
registry row or glossary entry may say it beats, predicts better than, or adds to anything. A
claim of that kind needs its own registered comparison that passes.

Artifact: `data/_labs/etools/etools_plus_check.json` (lab; off the webroot). The numbers are
appended to this document under "Check results" after the run.

## 7. Defaults applied

- D-1 weights: candidate E of EFV_ETOOLS_REWEIGHT (its owner question 2, default (a)).
- D-2 no consensus fallback for a weighted tool.
- D-3 pool: the side's players in `data/etools.json` with a weighted eTool.
- D-4 shown under the existing eTools flag, no flag of its own.
- D-5 the head's non-slot consensus columns are not tools of eTools+.

## 8. Owner question recorded with the build

Hitter eTools+ is ePOW alone under D-1. Options: (a) keep D-1; (b) the served eFV's
consensus-slot weights mapped onto the eTools (hitters eHIT alone, pitchers eFB 0.24 and eCMD
0.76); (c) equal weights over each side's passing eTools; (d) weights from each eTool's own
tool-label accuracy.
