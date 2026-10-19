# eFV against consensus on arrival: results for the owner (2026-10-19)

Plain language. Every number is copied from `data/_labs/efv5/efv_beat_tilted_labels.json`; the
method, fixed and committed alone before any number (commit b7798fc8), and the full tables are
in `docs/efv-v2/EFV_BEAT_TILTED_LABELS.md` (sections 14 and 15). Development frames only.
Nothing here is cut by consensus-FV level. No em-dashes.

## The one-line answer

The served eFV does not beat PROSPX consensus at predicting who reaches the majors. On the list
years 2017 to 2019 (reached within three seasons) it reads +0.005, and on the debut classes 2017
to 2023 (how early in the season they arrived) +0.008; both lower bounds are below zero
(-0.009 and -0.013). The verdict is **NOT PASS (ties)**. Nothing on the site moves, no arrival
sentence is drafted, and the copy keeps "ties consensus".

## What was asked

You asked (EW3-11) to use the drivers to beat consensus, and picked tilted labels as one path:
labels that reward arrival, where an eFV with an arrival head should have its edge, with the
site's wording limited to arrival if it passed. The registered claim needed the served eFV to
beat consensus with a one-sided 95 percent lower bound above zero on both development frames,
under both player and club resampling, beyond a random reshuffle of its own adjustments, with
a planted check proving the read could see a real edge.

## Why it did not pass

- **The served eFV no longer has an arrival term.** The registered re-fit you flipped
  (EFV-REFIT-1) set the arrival weight to 0 on both sides, because re-derived it added nothing
  to later WAR. So the served order is consensus moved by the skill head only, and on arrival
  it sits level with consensus.
- **Hitters gain, pitchers lose, and they cancel.** On the list years the served order beats
  consensus for hitters (+0.028 on reaching within three seasons, lower bounds above zero)
  and trails it for pitchers (-0.020). Pooled, +0.005.
- **On the debut classes the small lead is noise.** A random reshuffle of the same
  adjustments gives about the same lead (+0.007 on average; half of the reshuffles reach the
  observed +0.008).
- **The arrival heads alone do worse, not better.** Both arrival heads, read alone, trail
  consensus at who reaches within three seasons (by 0.043 and 0.066).
- **The read had the power.** It could see an edge of about 0.014 (list years) and 0.021
  (debut classes), and a planted rater with real arrival information was found on both frames
  (+0.09 and +0.12, lower bounds well above zero).

## The table (within-year Spearman, served eFV minus consensus)

| label | list years 2017 to 2019 | debut classes 2017 to 2023 | reading |
|---|---|---|---|
| ARRIVAL (decides): reached within 3 seasons / how early in the debut season | +0.005 (lower bound -0.009) | +0.008 (-0.013) | ties |
| Reached within 5 seasons / how early in the debut season | -0.003 (-0.017) | +0.008 (-0.013) | ties |
| Early WAR (first two MLB seasons) | -0.007 (-0.022) | +0.017 (-0.002) | ties |

Every interval spans zero; the club-resampled bounds agree. The pre-refit eFV v5 COMBINED that
the task named also fails the rule (-0.011 on the list years, lower bound -0.035).

## The corroboration read

The 2026 holdout (quoted, not recomputed): the then-served pre-refit eFV beat consensus at
picking who reached the majors in 2026 (AUC +0.049, lower bound +0.034), almost all hitters
(+0.095). That was a different model (with an arrival weight) on one spent season; it does not
enter this verdict. It agrees with the hitter cut here.

## What the read does show (development only, not a claim)

- The hitter arrival edge on the list years (+0.028, lower bounds +0.012 player and +0.011
  club) is real enough to be worth a registered read of its own on unread data.
- The v5 COMBINED arrival head alone is far better than consensus at HOW EARLY in the season a
  player who is about to debut arrives (+0.224, lower bounds +0.162 both ways), while it trails
  consensus at WHO reaches. It reads the level a player has reached in the spring; it is a
  this-season timing signal, not a prospect grade.

## What the site may print

Nothing new. No arrival sentence, no Source Comparison row, no flag. Every eFV claim stays as it
is ("ties consensus").

## Questions recorded for the owner (defaults applied, nothing stopped)

1. **A hitters-only arrival claim.** Default: nothing (a by-side cut chosen after seeing it
   cannot be claimed on the frame it was seen on). Alternatives: (b) register a hitters-only
   arrival read on the next unread data (preseason-2027 lists, reached in 2027), which waits
   for the 2027 season; (c) close the arrival path.
2. **The in-season arrival signal.** Default: nothing (the head is not served and fails the
   who-reaches label). Alternatives: (b) register an in-season "expected debut timing" display
   read on the 2027 debut class; (c) close it.
3. **The debut-class leg (default D-1, arrival day).** Default: as registered. Alternatives:
   (b) the list years alone, or (c) early WAR as the debut-class leg. Neither changes the
   verdict: the list-year lower bound is -0.009 and the early-WAR debut-class bound is -0.002.
4. **The deciding rater (default D-2, the served re-fit).** Default: as registered.
   Alternative: (b) the pre-refit v5 COMBINED the task named. It also fails (list years -0.011,
   lower bound -0.035), so the verdict does not depend on the choice.
