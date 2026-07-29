# Box maintenance bundle - approved 2026-07-23

Three idempotent prospects.db repairs, owner-approved to run together in one
box session. All three have code-side guards already deployed-or-pending that
stop NEW corruption; these repair the EXISTING rows. Take a DB backup first
(the standard nightly backup is sufficient; note the 14-day auto-prune).

## 1. Valdez key collision (script, dry-run then apply)
    python tools/repair_valdez_collision.py            # review output
    python tools/repair_valdez_collision.py --apply
Re-keys the 2026 DSL Giants signee (mlbam 838649, an OF) from jose_a_valdez
to jose_valdez_sfg across statlines / career_stats / player_transactions /
roster_status / player_photos / players / acquisitions; the retired Tigers
RHP keeps jose_a_valdez with his snapshots + career_war. Do NOT hand-edit
.cache/mlbam_ids.json - the resolver's collision guard heals the stale
binding on the next resolve. He surfaces on the board via performance_ingest
once his clean record has a snapshot anchor.

## 2. Vilade-class debut-snapshot repair (41 rows, pending since 2026-07-15)
The 41 run-date-stamped veteran re-appearance debut snapshots. The re-fire
guard (storage.auto_debut_player) stops new ones; the existing rows still
need the UPDATE documented in the 2026-07-15 session notes (stats-projections
program). Verify count first:
    SELECT COUNT(*) FROM snapshots WHERE source='auto_detect'
      AND status='debuted' AND snapshot_date > '2026-01-01';
and cross-check against the documented list before updating debut dates from
roster_status.mlb_debut_date.

## 3. Draft-board leak DELETE (~936 rows, pending since 2026-07-15)
    DELETE FROM snapshots WHERE source='fangraphs'
      AND interval_label GLOB '20[0-9][0-9]draft';
FG draft boards leaked org-less rows into MiLB snapshots. The seed guard +
regression test (pinned to post-2026-06-01) already prevent recurrence; this
removes the historical rows. Expect ~936; investigate if wildly different.

## After all three
Run the box's normal regen (nightly or manual efv_export + timeseries) so
exports pick up the repaired records, and let the golden restamp on the box's
own run per convention.
