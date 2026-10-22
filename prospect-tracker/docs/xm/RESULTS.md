# xM$ results (read 2026-10-22)

Gate: `docs/xm/XM_GATE.md` (registered alone at `70864a33`; crash and resume
recorded in its section 14). Artifact: `data/xm_eval.json`. Registry row: `xm`.

## The answer

**Verdict: INCUMBENT.** The best way we found to price free agents is the
market model the /fa/ page already uses. Neither new model beat it. On the two
most recent winters, which no model was fitted on, it beat a simple rule
(last season's WAR times the going price per WAR). The registry row is
`provisional` (`inherits_parent_gate`), not `validated`: those two winters
were already published by the /fa/ model's own gate, so they are not a fresh
test for it.

What the site may say, once the owner turns xM$ on: "xM$ uses the /fa/ market
model, generalized to every player. On the two most recent winters it beat a
WAR-times-price rule." Nothing more about accuracy.

## How it was read

1. **A rehearsal on fake data.** The whole reporting path ran on a made-up set
   of signings first, written to a scratch folder. It passed.
2. **Planted tests.** We fed each model data with a known answer.
   - The censoring test passed: the hurdle model's Tobit part found the
     planted line (error 0.053) better than ordinary least squares did
     (0.059).
   - The signal test: the incumbent came within 1.128 times the best possible
     error and the hurdle within 1.098. The gradient-boosting model reached
     1.179, past the 1.15 limit, so it was ruled out.
   - The shuffled-labels test: no model found signal in noise.
3. **Development, winters 2018 to 2024 (893 signings).** Each winter was
   priced by models fitted only on earlier winters. Typical miss on the total
   guarantee, on a log scale (lower is better):

   | Model | Miss |
   |---|---|
   | (a) the /fa/ model (incumbent) | 0.742 |
   | (b) hurdle model | 0.768 |
   | (c) gradient boosting, ruled out | 0.734 |
   | WAR-times-price rule | 1.015 |
   | Same price for everyone at a position | 1.141 |

   The rule picks the lowest miss among the models still eligible, so the
   incumbent was selected and no challenger went on to the holdout.
4. **Holdout, winters 2025 and 2026 (306 signings, 260 players), read once.**

   | Model | Miss |
   |---|---|
   | The /fa/ model | 0.736 |
   | WAR-times-price rule | 0.899 |
   | Same price for everyone at a position | 1.163 |

   The /fa/ model's edge over the rule is 0.163, and the cautious
   (one-sided 95 percent) lower end of that edge is 0.092, above zero. Its
   10th-to-90th-percentile band held the actual guarantee 85.3 percent of the
   time (target 80), and it got the number of years exactly right 76.5
   percent of the time.

## The first attempt crashed

The first read died partway through step 4, the holdout, with exit code 139
(a native crash, no error message). The development results had been saved;
no holdout number had been written or seen. The owner chose to resume once
(XM1-Q1). The crash and the resume rule were committed to the gate before the
resume ran. The resume read the saved selection and band settings instead of
recomputing them. The one code change was to how the bootstrap counts its
draws. It now uses a single count, which gives exactly the same numbers and
avoids a numpy pattern this machine's Python has crashed on before. The resume
finished cleanly.

## MLB Trade Rumors does better

Both were scored against the headline (sticker) guarantee:

- **Development:** on 309 shared players, MLBTR missed by 0.453 and the model
  by 0.832.
- **Holdout:** on 92 shared players, MLBTR missed by 0.452 and the model by
  0.712. MLBTR's edge clears the bootstrap bound.

We make no claim against MLBTR.

## Pricing everyone else as a free agent (descriptive)

xM$ also prices players who are not free agents, as if they were free agents
this winter. These prices carry no accuracy claim.

- **Outside the range the model was fitted on:** 61.4 percent of prospects,
  6.0 percent of pre-arbitration players and 0.3 percent of arbitration
  players. They were pulled back to the edge of that range and flagged.
- **Extensions:** the salary teams actually pay for free-agent years they
  bought through an extension sits at 1.034 times xM$ (101 players; 95
  percent interval 0.813 to 1.352). That cannot tell a discount from a
  premium, so it is inconclusive.
- **Postings and international professionals:** 48 deals could not be
  checked, because we have no WAR path for players with no recent MLB
  seasons.

## What changes

Nothing served. The selected model is the same /fa/ model XM_2 already used
to export xM$ (dark), so no file needs regenerating.
