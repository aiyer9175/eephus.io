# Regen then push: the runbook for the 2026-07-30 program

Owner decision 2026-07-30: **regenerate on the box first, then push.** This file is the
sequence. It is written rather than executed because at authoring time the nightly box
pipeline was mid-write (50+ `data/` paths churned uncommitted, a non-session python
process observed restamping artifacts), and firing a production regen into that is how
artifacts get corrupted.

## Why a regen is required before the push

The code is AHEAD of the committed artifacts in four specific places. Pushing without
regenerating publishes code whose own data disagrees with it.

| what | state | clears on |
|---|---|---|
| `data/xfv.json` grades | still the retired `realized_implied_fv` scale | `efv_export.py --all` |
| `data/xfv_history.json` | still the retired per-side quantile basis; the movement gate `storage.xfv_history_is_on_board_basis()` reports False and is SUPPRESSING the eFV delta right now | `score_history` inside the eFV regen |
| the fabricated BA statcast FV | `source_articles.py` emits `fv=None`, but the DB still holds the old value | the next INGEST re-parses the drop file and UPSERTs `fv=NULL` |
| `test_xfv_golden_fingerprint` | RED, owed a restamp since before this program | restamp from the production regen output, never from a post-pytest tree |

## Order of operations

1. **Wait for the nightly to finish.** Check `git status prospect-tracker/data/` is stable
   across two readings a few minutes apart, and that no stray python process is writing.
   The pipeline window observed this session was roughly 00:30 to 04:00 local.
2. **Decide what to do with the 50+ churned `data/` paths.** They are the box's own
   output, not this program's. Either commit them as a pipeline-regen commit of their own
   or discard them, but do NOT let them ride along inside a code commit. Note that
   `data/wire_fv_first_seen.json` is an append-only first-seen ledger and had FV values
   and dates rewritten during the session; check it deliberately rather than assuming.
3. **Run the ingest** so the BA statcast FV removal reaches the database. Verify
   afterwards that `baseballamerica_statcast_by_age` rows carry `fv IS NULL`, and that the
   7 orphaned players (`braylon_whitaker`, `easton_shelton`, `jacob_friend`,
   `jake_cunningham`, `jose_meza`, `mason_guerra`, `michael_martinez`) land in the
   PROVISIONAL pool rather than vanishing.
4. **Run the production eFV regen** (`python efv_export.py --all`). This is what moves
   `xfv.json` onto the outcome-anchored grade and rebuilds `xfv_history.json` on the board
   basis.
5. **Verify the three coordination points, in this order:**
   - `storage.board_basis_fingerprint()` still equals `storage.BOARD_BASIS_FINGERPRINT`
     (currently `xfv_grade|scale=off|grademap=outcome_pooled@6dbe8353f3bb|roles=usage_both`).
   - `storage.xfv_history_is_on_board_basis()` now returns **True**. It is False today by
     design and self-clears on this regen. While False the eFV-delta movement signal is
     suppressed, which is intentional for exactly one run.
   - `test_board_basis_coherence.py` side-mix band still holds; re-record `PINNED_MIX`
     only if it breaches.
6. **Restamp the golden** from THIS regen's output. Never from a working tree that has had
   pytest run against it: a mid-suite test regenerates `data/xfv.json` under fixtures, and
   restamping from that records a fixture state as production truth.
7. **Re-run the full suite.** Expect the 4 documented pre-existing reds to resolve down as
   the artifacts catch up: the golden should go green, and the history xfail should
   XPASS its basis clause while still failing its tilt clause (see below).
8. **Push**, main first, then sync beta to the identical tree (`push HEAD:refs/heads/main`;
   beta is a disjoint webmaster branch and must be synced after main, per the deploy
   memory).

## What will still be red after the regen, and why that is correct

- **The history tilt gap.** `test_board_basis_coherence::test_history_series_is_on_the_board_basis`
  keeps its strict xfail on purpose. Even after the regen, 417 of 1,563 tails carry a tilt
  gap, because `run_live` applies injury / age / Statcast / reliever tilts that
  `score_history` has never had as-of values for (138 have an injury factor, 95 sit at the
  FV20 floor). The BASIS half of the defect is fixed and is covered by a separate
  median-based test that activates on the first regen. Removing the marker would add a red
  without adding information.
- **C5, the inert MLB projection anchor**, and **the $0-bottom-block calibration tripwire**
  are live tripwires for open defects, not stale assertions. They stay red until those
  defects are fixed. Do not silence them.
- **`michael_oliveto`** heals on an identity rebuild, not on this regen.
- **Three regen-induced reds** appeared during the session and are NOT from this program's
  code: `test_bullpen_export::test_data_contract` (a REM+ value of 203 against a
  [40,200] contract), `test_efv_sign_declarations[pit]` (pitcher `age_rel_level` fitted
  +0.0418 against a declared -1 after the nightly matrix refit), and
  `test_team_outlook_calibration::test_recenter_remainder_near_zero` (4.48 against a bound
  of 3, downstream of the FA lane's WAR-path change). Each needs its own triage; none is
  fixed by regenerating.

## The one thing not to do

Do not restamp any pin, band or golden purely to make the suite green after the regen.
Every red in the list above either documents an open defect or is a tripwire doing its
job. The program's whole method this session was to move the record when it disagreed
with the code, and to leave the code alone when the record was right.
