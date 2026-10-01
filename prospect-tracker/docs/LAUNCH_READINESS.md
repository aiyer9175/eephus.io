# Launch readiness: the port to git.eephus.io

Started 2026-10-01 on the owner's answer M23-4 (2026-09-25). It replaces the Beta
checklist and review queue of the 2026-07-11 Beta launch, both archived with their
banners: `docs/archive/BETA_READINESS.md` and `docs/archive/REVIEW_QUEUE.md`.

This is a short checklist, not a spec. Every line names the document it comes from, and
when a line here disagrees with its source, the source wins and this file is what gets
fixed. Legend: [x] done, [ ] open, [-] held by an owner decision.

## 1. Status

- [-] **The port is DEFERRED by the owner (2026-09-18):** "finish the current lanes
  first". No remote is configured for git.eephus.io and nothing has been pushed there.
  Source: `docs/master-plan-2026-09-24-final-pass.md` Part 0.2 and Part 6 (row W5).
- The order is fixed: final pass, then the fWAR label epoch (runbook steps A to Z), then
  port Phase 0 on the old stack. Phase 0 is built on post-epoch numbers so the port does
  not carry numbers that are about to move. Source: master plan 2.3 ("The sequencing
  consequence") and Part 7 Q-0.
- The spec is `docs/port/PORT_SPEC.md` (2026-09-18). Read it before any port work; this
  file only tracks it.

## 2. Rules that bind any launch

- **Do not port and rewrite the backend at once.** Port with served numbers frozen and an
  equivalence check, then replace one component at a time behind it. If both change
  together, a moved number could be a port bug, a rewrite bug or a real data change, and
  nothing can tell which. Source: PORT_SPEC 5.1 and decision D1 (section 12).
- **`beta` is a disjoint history.** It shares no commit with the working branch, so it can
  be neither merged nor fast-forwarded. Seed the new remote from the working branch and
  decide what happens to the beta-only commits (D6). Source: PORT_SPEC 6.1 and 6.3.
- **Leakage is enforced by schema, not by convention.** Every fact row carries a
  knowledge-cutoff column and historical reads go only through an accessor that requires
  an as-of date, so a leaky query cannot be written. Source: PORT_SPEC 4.1 and Gate D.
- **The history carries withheld files** (91 versions of `data/scout_reports.json`). The
  owner picks a remote only he can read plus a filtered mirror, or a filtered history.
  Source: master plan X04-07 and its Part 7 question.

## 3. Open owner actions

- [ ] **Push.** The branch was last pushed 2026-09-25 (`origin/efv-conviction-2026-08-08`
  at `a8f79364`); later commits are local until the owner pushes. Count them with
  `git rev-list --count origin/efv-conviction-2026-08-08..HEAD`. The 2026-10-01 retraction
  of `data/arb_ledger.json` (moved to `data/_labs/`) reaches the webroot only after a push
  and the next nightly, when rsync `--delete` runs on a tree without it. Sources:
  `deploy/data_exclude.txt` header; master plan X04-05.
- [x] **Arm the public betting record.** Armed 2026-09-25 by the owner in writing
  (`RECORD_PUBLISH_ARMED = True` in `betting_export.py`). Turning it off is also an owner
  decision. Source: the comment above that flag.
- [ ] **Reopen the port.** No Phase 0 work starts before this. Source: master plan Part 6
  (row W5).
- [ ] **Answer D1 to D12 in the repo**, not in a chat log (acceptance criterion 16). D10,
  the two-scale Stuff+ in `data/pitch_plots/`, was acted on in `87694815` (2026-09-23: each
  view names its Stuff+ baseline); the answer still needs writing down. Source: PORT_SPEC
  section 12.

## 4. Dated gates and clocks that bind a launch date

A cutover, state transfer or full rebuild must not land on a registered look date or move
a file a pending look reads. Looking early disqualifies a candidate.

| Date | Clock | Source |
|---|---|---|
| 2026-10-03 23:59 | served-change landing window closes; until epoch step Z only docs and registrations land | master plan 8.B |
| from ~2026-10-05 | fWAR label epoch, steps A to Z (step M not before 10-05; step Z proposed about 10-11 to 10-13); every fitted artifact moves once | `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md`; master plan 8.B |
| 10-05, 10-07, 10-11 | betting looks: 5c-B and 5c-C (10-05), 5d and 5k (10-07), 5e handedness and 5i-B park by hand (10-11) | `docs/diamond-betting.md` section 5; master plan 2.3 |
| 10-23, 11-06, 11-13 | projections path-shape looks | `docs/PROJ_PATH_SHAPE_GATE.md` |
| 2026-10-31 | last day for the B4 looks, else INDETERMINATE | master plan 2.3 |
| 2026-11-02 | college pitcher K% challenger, one look | `docs/COLLEGE_PIT_K_CHALLENGER_GATE.md` |
| after 11-15; 11-16 or later | pWOBA re-gate; HEM+ construction re-gate | `docs/HEM_RIV_REGATE_GATE.md` |
| later of 11-20 and step Z + 14 days | PROSPECT_ANCHOR, one look | `docs/PROSPECT_ANCHOR_GATE.md` |
| not before 2026-12-01 | eFV reserved reads (R-LV, R-VM) | `docs/efv-v2/PROGRAM.md` |
| 2026-12-02 | `test_storage_export.py:114` rots unless fixed first | `docs/TIME_ROT_BACKLOG.md`; master plan 2.3 |
| before Opening Day 2027 | betting schema 6 and 7 builders | `docs/BETTING_DUGOUT_GATE.md` |
| 2027-07-01 earliest | 5l club-policy look | `docs/BETTING_DUGOUT_GATE.md` |
| not before 2027-10-15 | PROSPECT_ANCHOR fresh read | `docs/PROSPECT_ANCHOR_GATE.md` |

## 5. What "ready" means, per surface

All five gates pass before any DNS or traffic moves; a gate that cannot be run is a
failed gate. Source: PORT_SPEC section 2 and the list in section 13.

| Surface | Ready when | Source |
|---|---|---|
| Test suite | Gate A passes twice (copy pass, rebuild pass) in both pytest modes, counts equal to `docs/port/BASELINE_PYTEST.txt` captured on the old box | PORT_SPEC Gate A; criteria 1, 7 |
| Routes and deep links | Gate B: every served path answers 200 or redirects, withheld paths 404, the deep links load, including the 4 hand-maintained routes (`/prospx/`, both `/collegesavant/` pages, `/player/`) | PORT_SPEC 1.1, Gate B; criterion 8 |
| Served numbers | Gate C: zero uncategorised differences over `data/**`, each product surface reported on its own | PORT_SPEC Gate C, C.2; criterion 9 |
| Eval sidecars | every FROZEN sidecar byte-identical apart from its timestamp, partitioned in `docs/port/EVAL_PARTITION.json` | PORT_SPEC C.3; criteria 4, 10 |
| State transfer | `prospects.db` and the cache copy set sha256-matched, the point-in-time bundles and `fg_*` pages included | PORT_SPEC 1.4; criterion 6 |
| Leakage | Gate D, all assertions plus its positive control | PORT_SPEC Gate D, 4.1; criterion 11 |
| Refusal | Gate E: an empty upstream keeps yesterday's artifact and files RED; a failing test publishes nothing | PORT_SPEC Gate E; criterion 12 |
| Betting timing | the T1 to T8 jobs scheduled on the new box and `tools/betting_close_job.py --selfcheck` passes | PORT_SPEC criterion 14 |
| Accounts and forums | moves only if D11 says so, as its own migration | PORT_SPEC D11 |

## 6. Phase 0 (old stack), as last censused

On 2026-09-24: not done P0.1 to P0.5, P0.7, P0.8, P0.11, P0.13; partly done P0.6, P0.10
and P0.12; done P0.14, and P0.16 largely. Phase 0 is not scheduled before epoch step Z.
Source: master plan 5.3 (census summary) and PORT_SPEC 5.2.
