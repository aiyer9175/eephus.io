# Master plan 2026-08-05: Omnibus 2 (prune, fonts, eFV, FA/AAV, PAL, leaks, Diamond, UI/UX, pipeline, artifacts)

STATUS: PLANNING. Written for the executing session (Claude Opus 5) to run end to end.
Recon: an 11-agent read-only sweep ran 2026-08-05 (~2.2M tokens, 791 tool calls),
followed by a 3-reviewer adversarial verification of this doc; findings are folded in
with file:line evidence. Where a line number has drifted by the time you execute, trust
the symbol name and the described behavior.
Baseline: main @ f20e85c pushed, suite 3,395 recorded. ENVIRONMENT NOTE: during the
planning session, agents accidentally triggered writers despite read-only instructions.
An unattributed partial regen (52 tracked files, 2026-08-05 ~17:57-18:02) was REVERTED
by the planning session per the fingerprint discipline; the GITIGNORED tier-2 artifacts
it refreshed remain on disk at the 08-05 vintage (rosters_by_org.json NOW CARRIES
fv_synthetic_only, 2,737 true of 10,684; xfv_ungraded.json now scores 5,972 players
from a reviewer's accidental run; data/dfs.json now EXISTS, untracked, from the maiden
dfs_export run). Consequences for you: (a) tracked-vs-gitignored vintage drift exists,
so single-basis guards may red at baseline - do not chase them, Wave 0's deliberate
full monthly re-coheres everything; (b) the routing fix and dfs_export are CONFIRMED
WORKING by those accidental runs; (c) fantasy_schedule fetch succeeded from this
sandbox at 22:01Z (41 games), answering G2's discriminator: the empty committed
schedule was transient/environmental, not a code regression.
origin/beta UNTOUCHED at 03c1428 and the sync REMAINS HELD by owner decision. Do not
push to beta.

## 0. How to use this doc

Execute in wave order (section 5). Each lane carries: root cause(s) pinned by recon,
the exact fix or experiment design, the gate that decides ship/no-ship, and the
verification steps. When a recon claim disagrees with what you find on disk, TRUST THE
DISK, note the correction in the execution record, and proceed with the corrected fact.
Never skip a gate because a change "looks obviously good." Prior sessions shipped
exactly one change on owner override (RoS de-aging) and refused everything that failed
its gate; keep that discipline. Report refusals as first-class results with evidence.

## 1. Standing rules (violations have burned prior sessions; all are load-bearing)

- Run pytest from `prospect-tracker/`, NEVER the repo root (root collects a vendored
  swing-plus dir, 6 collection errors). `--timeout` is not available. NEVER edit source
  while the suite runs (conftest git-restores churned data files at session end; your
  half-written edit can be reverted or committed with churn).
- The ONLY expected reds on this sandbox: 4 live Tankathon scrapes (SSL cert chain),
  verified to reproduce with changes stashed. Lane F item F2.5 fixes their gating; after
  it ships, expect ZERO reds. Anything else red is yours.
- `data/mlb_projections.json` and `data/trade_values.json` (and mlb_player_detail.json)
  are GITIGNORED tier-2 artifacts. `git checkout -- data/` reverts TRACKED files but not
  these, which can create single-basis drift; re-running `python proj_export.py` heals
  it. `git checkout -- data/` also silently reverts your own registry-row edits: stash
  or re-apply.
- A pathless `git commit` sweeps other agents' staged deletions into your commit. Always
  commit with explicit paths when subagents are active.
- Any consensus/eFV/valuation BASIS change needs TWO export passes (the first pass
  re-freezes anchors, the second prices off them). `tools/export_trade_values.py`
  regenerates the board alone with the two passes built in ("TWO PASSES, ALWAYS",
  tools/export_trade_values.py:13-16). Emit a movers table for any basis change (count,
  median move, sign flips, top-20).
- Golden fingerprint + single-basis guard tests are tripwires, not noise. If the
  fingerprint fires on files you did not intend to regenerate, REVERT the regen rather
  than shipping a partial data refresh inside a feature commit.
- `test_methodology_freshness` demands a MODEL_GLOSSARY entry for every new
  MODEL_REGISTRY.md row. MODEL_REGISTRY.md is GENERATED (line 1): edit
  data/model_registry.json and regenerate via tools/gen_audit_docs.py, never hand-edit.
- Copy rules (owner): NO em-dashes in user-facing prose (`tools/strip_emdashes.py
  --check` + copy_lint). FV and tool grades DISPLAY as CEILING; eFV and "+" stats round
  nearest. Healthy players get no injury penalty.
- index.html and generated pages come from build_site.py (the homepage drawer lives
  there). Never edit generated HTML; edit the generator. Hand-maintained pages
  (prospx/index.html, collegesavant/*) are content-hash restamped by build_site.
- `prospect-tracker/.env` (gitignored) holds EEPHUS_ODDS_API_KEY and
  EEPHUS_CARD_SCRAPE=1. NOTHING auto-loads it: `set -a; source .env; set +a` before any
  step that needs them. Never print the key.
- git push needs `http.sslBackend schannel` on this box. Node runs via
  ELECTRON_RUN_AS_NODE. Ruff IS installed. fonttools 4.60.1 is installed; brotli is NOT
  (Lane B needs `pip install brotli`).
- py_mini_racer smoke harnesses use SYNCHRONOUS fake thenables that cannot satisfy
  Promise.all; do not gate a first render on Promise.all or the harness sees "Loading"
  forever.
- The deploy box runs `git checkout -- .` nightly: anything that must survive on the box
  lives OUTSIDE the checkout (`.cache/leaderboard_vintages/`, `.cache/odds/`).
- origin/beta stays untouched. All work lands on main.

## 2. Banned / closed experiment ledger (do NOT re-attempt or re-recommend)

Each was measured to failure or adjudicated closed; the burden to reopen is a NEW data
source or a NEW owner instruction, not a hunch. Consolidated receipts are on disk at
the cited locations.

eFV / consensus:
- K-prior (closed permanently). Surrogate-label backfill; old-cohort milb backfill
  (docs/SURROGATE_LABEL_PROGRAM.md "SPENT").
- Statcast-into-projections blind port. Tools arm (dead). Athleticism blend that
  REPLACES tool_speed (-0.014) or uses frame/athl (FG-only, 0/843 trainable;
  data/xfv_physical_eval.json "rejected - decisive regression").
- Lambda cap raise (retracted; data/xfv_lambda_band_eval.json). Blend lambda stays
  pinned {hit 0.70, pit 0.57} (`_BLEND_LAMBDA_RESELECT`, efv_model.py:448).
- The SIX 2026-08-05 experiments (docs/efv-sb-athleticism-2026-08-05/RESULTS.md; best
  was SB-rate at 0.45x its 0.017 MDE floor). sb_rate_rel re-test only under the new
  power protocol of Lane C3, never a rerun of the same underpowered design.
- B3 level-blend: measured NO-SHIP 2026-07-30 (docs/efv-2026-07-30/
  B3_LEVEL_BLEND_GATE.md header "VERDICT: NO-SHIP"; BOTH primaries negative, hit
  -0.0082 / pit -0.0162). The machinery stays built+OFF. Re-open ONLY as a
  null-resolution run under the C3 re-powered protocol with a pre-registered
  commitment that a confirmed negative closes B3 permanently - and only after
  sb_rate_rel and positions_played (whose priors point positive) have spent the
  rebuild budget first.
- Model-grade-into-consensus substitution (refused 2026-08-05, owner agreed).
- Draft-anchor backfill: RETIRED and the owner ACCEPTED (docs/
  draft-anchor-validation-2026-08-05/REPORT.md header; module deleted at 85981e0). This
  is CLOSED, not awaiting anyone. The 2,608 players on a fabricated FV 35 remain an
  open COVERAGE gap addressed by the Wave-0 routing regen, not by seeded anchors.
- eWAR v2 forward-leg win was FALSE; catcher-framing ingest refused (inert season
  param); relief-shape arms SPENT (efv_model.py:962-976); pace-from-entry CLOSED
  (efv_model.py:385-398); cohort interactions reverted; NEVER sum ML quantile points.
- CSW/SwStr MiLB as eFV feature REJECTED 2026-07-25 (0.0059 vs floor 0.016, 0.80-
  correlated with served k_rel). IFA bonus-to-WAR curve FAIL (data/ifa_pedigree_eval.json).
- Consensus source reweighting stays FLAT (weights {} since 2026-07-25); reopen only
  through source_backtest's vintage A/B with gain > its own MDE 0.0068.

FA:
- AAV_CONSISTENT re-litigation (two measured losses: wave3 arms 3.096/3.204 vs champion
  3.045). BAND_SCALE_GUAR (measured null vs zero-info control, fa_market.py:144-168).
  ML paths as market inputs (failed Gate 2, fa_market.py:2051-2058). Unbounded
  prediction-dependent recal forms ("fit"/"fit_group" overshoot the top tier +$10.5/
  +$15.0M, fa_market.py:131-136) - any new recal form repeats the overshoot check.

PAL / defense:
- The naive "3B needs elite arm" gate NO-SHIPPED 2026-07-30 (docs/efv-2026-07-30/
  CONVERSION_ARM_GATE_VERDICT.md): context-adjusted infield arm spread is 1.94 mph vs
  3.80 within-position SD. Any anthro/arm work must be context-adjusted and must act
  only where OAA evidence is absent (Lane E4's design does).
- PAL stamina lane (rp_sp_fit_v2) FAILED its gate (delta-rho +0.0004, lo95 -0.0672);
  built, correctly unshipped. Do not wire without a new feature design + gate.

Valuation / identity:
- Production valuation set is clemens_2026; check `vf.active_valuation_set()` before
  claiming anything about served prices. proj_export._winter_dpw reads
  data/fa_dpw_series.json DIRECTLY (proj_export.py:429-437), which is why the R7
  re-anchor moved 841 board rows.
- `active_roster_days` is NOT MLB service time. Spelling splits are fixed via
  consensus.PLAYER_KEY_ALIASES (read-time), never a DB key remap (PK collision on
  23/30 rows).

## 3. Corrections to memory established by this recon (cite these, do not re-litigate)

1. The draft-board leak is DELETED (owner-authorized, applied 2026-07-16b via
   tools/delete_draft_board_leak.py; 0 rows match the leak predicate today). The
   2026-07-15 "OWNER PENDING" memory line is stale. Residual: test hardening (F1.4).
2. Draft-anchor backfill: RETIRED, owner accepted, module deleted. Not an open decision.
3. "Nightly monthly does NOT run efv_export" is MISLEADING: monthly main() never calls
   it directly, but the chained d9 -> rebuild_only -> efv_export.regen_all runs on
   EVERY nightly (run_monthly.py:903-908).
4. "Hand pages load site.css unversioned" is FALSE now; restamp_hand_authored_pages()
   ships. The stale prose lives in tools/gen_audit_docs.py:291 (fix in H9).
5. The positional ladder is ALREADY correct and zero-summing on both bases (Lane E1);
   the owner's ask (a) is substantively done - verify, document, and fix the stale
   display comments rather than refitting.
6. FA "verdict terciles" are now PER-POSITION-GROUP (fa_market.py:1861-1865), not the
   pooled 223/109 edges.
7. fa_backtest after A2: literally never re-run, but ZERO-DELTA by import graph (A2
   touched only proj_export/bayes_trade_value, which fa_* never imports). The current
   fa_gate2_eval.json IS the post-dpw-re-anchor state. Nothing owed there.
8. The production discount rate IS 0.07, not 0.09: value_framework._config() applies
   the clemens_2026 net_7_flat overlay (valuation_sets.py:289-292) over the base 0.09
   (value_framework_config.yaml:258). The fa_market.py:12-13 docstring is CORRECT.
9. The 2026-08-04d recon's "B3 level-blend pending its gate" was WRONG: the gate ran
   2026-07-30 and NO-SHIPPED (see section 2).
10. efv_ungraded.py has NO argparse: ANY invocation (including --help) runs the build
    and rewrites data/xfv_ungraded.json. Check its sys.argv handling before running.

## 4. Owner decision queue

Pre-answered (locked in prior sessions, do not re-ask): Odds API + card scraping + cache
pruning all ON (prune = dry-run first; dry-run now DONE, Lane A); RoS de-aging SHIPPED
on override with the `proj_export.ROS_TALENT_BASIS` one-line revert; negative rentals
have NO floor; Supabase not live in prod (gate stays cosmetic); betting publishes no
pick-of-day until the 600-vintage-graded-game gate; plan without Cloudflare.

OPEN - the executor should proceed with the RECOMMENDED default where one is given and
surface the rest in the final report:
1. Font pick (Lane B): default PixelMplus12; publish the specimen artifact and let the
   owner veto. Also: does the owner want the LOGO face (DotGothic16) replaced too?
   Default NO (logo stays DotGothic16).
2. CLV grade storage (F2.2): record rows are append-only by contract
   (betting_export.py:214-237). RECOMMEND a sidecar artifact (data/betting_clv.json)
   keyed by record row id, leaving the ledger contract intact.
3. Doubleheader close policy (F2.1/F2.2): one close snapshot per slate cannot capture
   game 2's close. RECOMMEND: exclude DH game 2 from CLV grading and say so on-page.
4. The 6 org='CWS' / 36 org='OAK' prospects.db rows (F2.4): RECOMMEND one-off UPDATE
   repair in the same commit as the mlbam_ingest fix (served artifacts already clean).
5. data/dfs.json policy (F2.11): RECOMMEND commit-once-generated, matching sibling
   data/betting.json.
6. Diamond extras build-or-cut (G4): RECOMMEND build exports/API now (trivial), defer
   alerts until Supabase is live, and REWORD the newsletter card to "planned" or cut it.
7. graduates.json (I10): no producer exists, warned every run. RECOMMEND retiring the
   declared input unless the owner wants the producer built.
8. RP->SP re-gate target (E3): RECOMMEND re-gating on the expanded event set with the
   INCUMBENT war_delta target (more data is not a protocol change; the expanded set is
   the PAL gamelog lab's lane_a recovery, data/pal_gamelog_eval.json: 50 mid_year + 39
   swing_bridge tagged events = +89, n~100 total). Switching the target to held-role
   IS a pre-registration change - surface to the owner in the final report; do not run
   the held-role variant without sign-off.
9. Box actions bundle (owner must run on the box; document in webmaster runbook):
   source /etc/eephus.env in the nightly cron line (or 9e never fires), install the
   vintage belt-and-braces cron + close-job crontab, set the prune env knobs
   (EEPHUS_PRUNE_VERSIONED_DAYS=30, EEPHUS_PRUNE_CACHE_DAYS=400, first run with
   EEPHUS_PRUNE_DRY_RUN=1), install the card-ingest cron (G2), and run ONE-OFF
   `EEPHUS_FULL=1` (or full `python run_monthly.py`) so the box's own
   rosters_by_org.json gets the fv_synthetic_only stamps NOW rather than Sep 1 -
   rosters_by_org.json is gitignored, so it cannot travel via git, and the box's
   nightly rebuild_only PRESERVES its stale copy (run_monthly.py:783-794): without
   this, production routing stays inert regardless of anything the executor commits.
10. Still open from prior sessions: delete old prospects.db backups (~4.3-5.7GB, keep
    prospects.backup-20260804T212141.db); Supabase go-live + Cloudflare uniques; the 5
    [NEEDS] cost placeholders in the monetization artifact.

## 5. Wave order

- Wave 0: preflight + regen debts (activates already-shipped-but-inert fixes).
- Wave 1: Lane A (finish cache prune) + Lane F (leak fixes first - the betting park
  leak is time-sensitive - then the bug list).
- Wave 2: Lane B (font) + Lane H (UI/UX theme) + Lane G (Diamond).
- Wave 3: Lane C (eFV) + Lane D (FA/AAV) + Lane E (PAL) - gated experiments, each with
  its own ship/no-ship verdict.
- Wave 4: Lane I (pipeline hardening) + Lane J (creative additions).
- Wave 5: Lane K (artifact + registry refresh, LAST so it reflects reality) + execution
  record + memory update.

Within a wave, lanes are independent; parallelize freely but commit per-lane with
explicit paths. EXCEPTIONS: within Wave 2, serialize Lanes B and H on site.css (either
order - both edit the token region), and run H2 (table-dialect port) BEFORE G6's
DFS-background item (drop that item if H2's port resolves it). Across ALL waves,
serialize pytest invocations: no lane edits source while any suite run is in flight.

---

## WAVE 0: Preflight + regen debts

W0.1 Baseline: `git log --oneline -3`; expect the tree clean of TRACKED churn (the
planning session reverted the unattributed 52-file regen) with three untracked paths:
.claude/, data/dfs.json (keep - decision #5), and this doc. Gitignored tier-2
artifacts sit at the 08-05 vintage while tracked ones are at HEAD, so single-basis
guards MAY red at baseline - record, do not chase; W0.2 heals them. Run the suite once
from prospect-tracker/ and record the count (expect ~3,395 passed / 4 Tankathon reds
until F2.5 lands, plus possibly the vintage-drift reds just described).

W0.2 **Clear the rosters_by_org.json regen debt with a DELIBERATE, attributed run.**
The fv_synthetic_only routing fix (fbdfb1f) is code-live; the accidental 08-05 partial
regen already proved it works (rosters_by_org.json on disk carries 2,737 true stamps;
data/xfv_ungraded.json scores 5,972 players, 2,409 hit / 3,563 pit - up from 3,296),
but that run was unattributed and partial, so do it properly: run ONE full local
monthly (`python run_monthly.py`, ~45 min + ~10 min chain; `set -a; source .env;
set +a` first so 9e can fire, or note it skipped cleanly). Then commit ONLY the
TRACKED artifacts the run touched (data/xfv.json plus whatever `git status` shows -
leaderboards, fa_*, fantasy.json, betting sidecars) as their own attributed data-regen
commit. **rosters_by_org.json, timeseries.json, and xfv_ungraded.json are GITIGNORED
tier-2 artifacts (.gitignore:32, :27, :20) - verify them on disk, NEVER `git add -f`
them** (timeseries.json is 74MB). Verify: (a) rosters_by_org.json rows carry
fv_synthetic_only; (b) xfv_ungraded.json population ~5,900+ (2,650 scoreable of the
2,720 constant-only cohort - so 2,632 of the 2,720 stop being flagship-routed);
(c) suite green after W0.4's restamp; (d) single-basis guards pass. This is also the
maiden in-pipeline execution of the steps added by the PRIOR omnibus's waves 4 and 7
(6f, 6g, 9d-bis, 9e, 9e-pre) - read their log lines; all 59 dynamically imported entry
points were signature-verified 2026-08-05, so surprises should be data-shaped, not
call-shaped. NOTE: production stays inert until the box regenerates ITS OWN
rosters_by_org.json (gitignored, cannot travel via git; the box nightly preserves its
stale copy) - hence the box one-off in decision #9. The fantasy-schedule discriminator
is ALREADY ANSWERED (22:01Z fetch got 41 games - environmental, not a regression); if
schedule.games comes back empty anyway, retry before diagnosing code.

W0.3 Refresh the provisional eval in the same pass (efv_ungraded.py has NO argparse -
any invocation builds and writes; check its sys.argv handling for the --eval path
before running). The on-disk eval (2026-07-14) says pit low-minors rho 0.0867 while
the module docstring and artifact note advertise ~0.24 - a 3x discrepancy. Update the
docstring/notes to the measured numbers. IF the refreshed eval confirms pit low-minors
materially below ~0.24, record it as a NAMED open gap in the execution record and
owner report (candidate for a future gated efv_ungraded feature lane) - do not just
rewrite the docstring and move on. This matters more now: the routing fix roughly
doubles this model's served population.

W0.4 Commit hygiene: the data-regen commit must NOT carry code edits, with ONE
sanctioned exception done as an immediate companion commit: restamp the GOLDEN
fingerprint constant in test_efv_export.py from the regen output, with a changelog
entry naming the fv_synthetic_only routing regen as the cause. (The test's own
changelog records a restamp-from-production-box convention; this deliberately
overrides it for the routing activation - say so in the entry. The box check runs in
EEPHUS_DEPLOY_RUN=1 shape mode and is unaffected.) Without the restamp, W0.2(c)
"suite green" is unsatisfiable.

---

## LANE A: Cache prune (dry-run DONE at planning time; finish + harden)

Measured 2026-08-05 on this machine (commands are repeatable):
- `python tools/prune_cache.py --report`: SAFE_CACHES total 53.89 GB / 285,024 files
  (win_prob 19.56G, statcast_metrics 15.35G, game_feeds 13.12G, zone_metrics 5.18G);
  777.9 GB free on fs - NO local disk pressure.
- `--max-age-days 400 --dry-run` and `200 --dry-run`: **0 files** (prune_by_age logs
  only when n>0; nothing in the allowlist is older than 90 days - the caches are young).
- `--prune-versioned-orphans --dry-run`: **115,523 files / 18.78 GB** - orphaned
  pre-CACHE_VERSION-bump entries in statcast_metrics + zone_metrics not re-touched in
  30 days (live entries are re-touched within 1d/7d TTLs each build).
- Safety VERIFIED: prune only walks the 13-name exact-match SAFE_CACHES allowlist
  (prune_cache.py:52-66, 90-104); .cache/leaderboard_vintages, .cache/odds,
  .cache/betting are unreachable by construction.

A1. Execute the real orphan prune locally: `python tools/prune_cache.py
--prune-versioned-orphans` (the standing owner decision authorized prune after a dry
run; this reclaims 18.78 GB of provably-orphaned files; everything is refetchable).
Record before/after `--report` output in the execution doc. Do NOT run age-based or
target-based prunes locally - nothing qualifies and there is no pressure.

A2. Harden the tool (small, tested):
- Fix the zero-byte dry-run miscount: `if sz or not p.exists()` (prune_cache.py:153)
  excludes 0-byte old files from dry-run counts but deletes them for real.
- Note in the module docstring that EXCLUDED (prune_cache.py:78) is documentation-only,
  and add: odds + leaderboard_vintages + betting are NON-REFETCHABLE and must never be
  added to SAFE_CACHES.
- Note that `--report` totals SAFE_CACHES only (~53.9 of ~55 GB).

A3. Box-side prescription (goes in the owner bundle, decision #9): env knobs
EEPHUS_PRUNE_VERSIONED_DAYS=30 + EEPHUS_PRUNE_CACHE_DAYS=400, first night with
EEPHUS_PRUNE_DRY_RUN=1, run manual prunes outside the 03:10 ET build window (TOCTOU
between scan and delete, prune_cache.py:196-199), never lower --min-keep-days below the
current-season window.

---

## LANE B: The Mac/iPhone font (MS Gothic lookalike)

Ground truth: MS Gothic is the PRIMARY face for essentially ALL site copy - two tokens
(`--font-retro` site.css:76-78, `--font-retro-mono` site.css:79-81, mirrored at
prospx/index.html:240-248), ~315 declarations, body rule included (site.css:284). On
Apple both tokens resolve to ui-monospace = SF Mono for 100% of copy, headings, tables,
and the nav wordmark. Only the logo lockups (`--font-logo`, DotGothic16 self-hosted)
keep the pixel look. The prior DotGothic16-as-body experiment failed MECHANICALLY: a
16px-native pixel face at 12-13px is 0.75-0.8x its grid = mush (comment at
site.css:71-75). The site's dominant sizes are 12-14px, weights 400 + pervasive
700/800, and `font-synthesis: none` is set (site.css:288, prospx:945) - so ANY
single-weight webfont silently flattens bold on Apple. That filter kills Ark Pixel,
Fusion Pixel, Unifont, and DotGothic16 itself.

B1. **Ship PixelMplus12, weights 400 + 700, as the Apple fallback.** (M+ FONT LICENSE,
verified maximally permissive; outline conversion of the M+ bitmap gothic family - the
same genre as MS Gothic's embedded strikes; 12px-native = 1.0-1.08x at the site's
12-13px; real Bold survives font-synthesis:none; monospaced half-width Latin preserves
the tabular chrome identity.) Runner-up if on-device QA reads too austere: Galmuri11 +
Galmuri11 Bold (OFL, active, 12px-native, slightly rounder DS-lineage Latin). Zpix is
DISQUALIFIED (USD $1000 commercial license).

B2. Integration (clone the DotGothic16 pattern exactly):
1. `pip install brotli` (fonttools present). Subset with pyftsubset --flavor=woff2 to
   assets/fonts/pixelmplus12-latin.woff2 + -bold variant. Unicode census BEFORE
   subsetting: U+0020-00FF plus the symbols the UI renders in retro tokens - at minimum
   U+25B2/25BC (movement arrows), U+25C6 (glossary.js:1016), U+21C4 (glossary.js:1018),
   U+2501/2508 (glossary.js:1010-1012), and the typographic set (middle dot, bullet,
   endash-in-data, curly quotes, ellipsis, trademark). Scan built pages incl. the wire
   feed. A missed glyph = per-glyph SF Mono fallback mid-word (ransom-note effect).
2. Vendor the two source TTFs + LICENSE_E into branding/fonts/ (precedent:
   DotGothic16-Regular.ttf + OFL.txt).
3. Two @font-face blocks in site.css after line 25: family "PixelMplus12", weights 400
   and 700, font-display: swap, unicode-range matching the subset. NOT preloaded
   (Windows must never download it; lazy loading means MS Gothic short-circuits it).
4. Token edits IN LOCKSTEP (both copies, site.css:76-81 AND prospx/index.html:240-248):
   insert "PixelMplus12" immediately after the MS Gothic entries in BOTH tokens.
   Windows rendering and network are byte-identical (MS Gothic matches first).
   `--font-logo` UNCHANGED (DotGothic16 stays the brand face; keeps
   tools/generate_brand_assets.py PIL parity and the branding SVGs coherent).
5. Canvas: gfx/hub/export use their own MONO constants, not the tokens - if the logo
   face stays DotGothic16, ZERO canvas changes. But the prospx DOM-capture path WILL
   rasterize the new face: add "700 13px PixelMplus12" + "400 13px PixelMplus12" specs
   to `_gfxAwaitAssets` (prospx/index.html:33380-33381). Optional hardening while
   there: eephus-hub.js `shareCard`/`openCard` (531/540) and eephus-export.js
   `_brandCompose` have NO font wait - reuse gfx's awaitFonts pattern (gfx:614-632).
6. Add a cheap test: the two token definitions stay mirrored; the @font-face src files
   exist on disk.

B3. QA gate (this is the ship gate): generate a SPECIMEN ARTIFACT - side-by-side
PixelMplus12 vs Galmuri11 vs current SF Mono fallback at 12/12.5/13/14px, weights
400+700, dark + light, table chrome + body copy samples - and publish it for the owner.
Then on-device pass (real iPhone if available; otherwise DevTools iOS emulation +
macOS Safari if reachable) over: prospx board, a data table, article body, glossary
chips, at fs-xs..fs-md, both themes. KNOWN SOFT SPOT: the 8-10px micro-chrome roles
render a 12px face at 0.67-0.83x (the pixel-font failure mode). If QA finds them rough,
the follow-up is registering PixelMplus10 (also has real Bold) behind a new
`--font-retro-micro` token pointed at only the micro roles - do NOT block the main ship
on it. ESCAPE HATCH if body copy reads rough at 400: scope `--font-retro` back to the
SF Mono ladder for `.article-body`/`.meth-prose` only; the retro-mono chrome alone
restores ~80% of the brand look.

B4. iOS reality to encode in comments: AA cannot be disabled on iOS; the target is
"pixel-shaped outlines under grayscale AA", crisp at 2x/3x retina when the grid
aligns. Keep `-webkit-font-smoothing: antialiased`; never render the face below its
native 12px.

---

## LANE C: eFV + consensusFV/provisionalFV improvement program

Current verified state: hit blend rho 0.3882 vs baseline 0.3521 (beats Spearman, not
MAE); pit blend 0.3208 vs 0.2671 = the only two-metric win; committed evals
(2026-08-03) are ONE MATRIX VINTAGE STALE vs the 2026-08-05 rebuild - any gate baseline
must be re-derived on current matrices first. The ship-gate eval scores only
SCORED_YEARS=(2020..2023) (efv_model.py:50) -> pooled n=353 hit / 438 pit -> MDE95
~0.017/0.016 - the eval is UNDERPOWERED BY CONFIGURATION while the audit labs already
run 11 forward-chained splits.

Ordered work:

C1. (Done in Wave 0) Routing regen + provisional eval refresh. Then surface the new
provisional population on /prospx/ with honest provenance: rows whose grade comes from
efv_ungraded get a "model-graded (no scout consensus)" chip, never a bare FV.

C2. **Fix the stale-anchor discount date basis** (verified defect): the E-STALE
discount reads the consensus POINT date (`row["asof_date"]` = latest event date,
efv_dataset.py:1153, assigned at efv_dataset.py:311), so any constant stamp or rank-only event
refreshes it - measured 0.00 FV discount on constant-refreshed rows where honoring the
per-source date gives 38/68 the full 10-point decay. Fix: read the max per-source
FV-BEARING snapshot_date from per_source (available at consensus.py:653). Live-path
only; mostly a no-op on the current board (gap is 0 for 1,930 of 1,946 graded actives).
BUT it touches fv_effective = the model anchor: treat as a BASIS-ADJACENT change - two
export passes, mover table, expect small movement concentrated in the stale cohort.
Regression test: a synthetic player whose only fresh row is a constant stamp must show
a nonzero discount.

C3. **Re-power the eval, then spend the earned re-tests.** Pre-registered protocol
change (document in docs/, registry note): (a) promote the 11-split forward chain to
the primary gate (pooled test n roughly doubles; MDE -> ~0.012); (b) add the 2024 fold
(DEBUT_YEARS already includes 2024; SCORED_YEARS just stops at 2023 - censored labels
with weights are the design norm); (c) for side-agnostic candidates use the sanctioned
block-rho (n=1001, MDE95 0.0149, EFV_GATE_STANDARD.md:49-50). Refresh
xfv_eval.json/xfv_eval_pitcher.json on current matrices under the OLD protocol first
(so the protocol change itself has a before/after). THEN, in order, one variant run
each, ship only on the standard's two-metric + control battery:
  1. sb_rate_rel (now on disk in BOTH matrices, 1,134/1,134 train + 2,038/2,038 live;
     re-test = emit in `_vec` + one feature key). Ledger says re-run triggers are CS
     ingest or higher coverage OR materially higher power - C3a/b IS that power change.
  2. positions_played census rebuild WITHOUT the pre-debut filter (the leak-shaped
     31.8%-train / 93.0%-live coverage split is the ONLY blocker on
     POS_PREMIUM_USES_OBSERVED, efv_model.py:759-797) - a data job, then re-gate.
  3. OPTIONAL, only if budget remains: B3 level-blend null-resolution per the section-2
     entry (measured NO-SHIP with negative primaries; pre-register that a confirmed
     negative closes it permanently).
Recon screened and disqualified the full candidate inventory; the only four non-ledger
candidates were: bat_speed (untrainable pre-2023 cohorts), park-line (M-FAIL verdict),
injury history (coverage-starved), org-tendencies (no per-player history substrate).
The numbered re-tests above are the COMPLETE set of live candidates - do not re-derive
and re-screen ideas the ledger already disqualified.

C4. Consensus hygiene (small, non-basis):
- `n_sources` counts the fabricated constant: `_prior_features` excludes only
  auto_detect (efv_dataset.py:288-289); exclude CONSTANT_ANCHOR_SOURCES. Currently
  inert (n_sources not a feature) - fix while it cannot hurt.
- Update the stale comment at efv_model.py:309 (still quotes the retired -0.0619; the
  module self-flags it at efv_model.py:201; efv_score.py's block was ALREADY corrected).
  The hit-age thread at efv_model.py:139-146 is C5.
- Do NOT touch source weights, single-source pull k, or PLAYER_KEY_ALIASES semantics.

C5. Bounded diagnostic (timebox: half a day): the 2026-08-04 rebuild moved the hit-age
marginal sign and nobody identified which label repair did it (efv_model.py:139-146).
Bisect the label-side repairs on the current frame; write the answer into the docstring.
No model change without a gate.

C6. Leak-lab (from Lane F, S4, run here because it shares the harness): rebuild
`_label_6yr` with RESOLVED_THROUGH = Y-1 per fold and compare pooled rho vs the current
protocol. If the gap is material, adopt per-fold censoring in the eval harness (an
eval-protocol change, pre-register alongside C3). This sizes the one systemic
optimism-shaped caveat every prospect eval shares.

---

## LANE D: FA / AAV improvement program

Verified current state (data/fa_gate2_eval.json, n=1,199, post-re-anchor): pooled AAV
MAE $3.135M (beats comps $3.359M) BUT bias is negative in every slice except catchers -
guarantee bias by predicted tier -$2.6M/-$9.1M/-$16.9M/-$24.2M; aav ptier:10to20 bias
-$2.99M (-28%). 9 of the 12 biggest AAV misses have |years error| <= 1: AAV misses are
LEVEL misses, not term-allocation misses. AAV is never fitted - it is
guarantee/round(years) (fa_market.py:1746-1747). Gate 1 star slices: act_ge4 model MAE
WORSE than naive carry-forward both sides (hit 2.96 vs 2.37, bias -2.93 WAR).

Ordered work (gates: fa_backtest.run_market_gate paired bootstrap; mega slice must not
regress; the E5a overshoot check - the 2026-07-30 FA program's gate ID, cited in the
fa_market.py:109-136 comment block, NOT this plan's Lane E5 - on any recal form):

D1. **Instrument before repairing** (the recon's open question #1): re-run Gate 2
logging `model.recal` per fold + the ptier bias table. The shipped RECAL shift measured
-2.11/-6.27/-15.04/-3.70 at ship time (fa_market.py:120-130) but the CURRENT artifact
shows near-PRE-recal biases (-2.62/-9.12/-16.89/-24.17). Determine: recal=None on early
folds by construction (fa_market.py:1482-1507) vs the Jul-31 defense-in-WAR-map corpus
change re-widened it. The answer decides whether D-repair is "recal engagement where
the dollars are" or "a new bounded correction form."

D2. **Prior-contract / name-anchor features** for the injury-return + pillow-deal
market (5 of the 12 biggest misses: Verlander, Syndergaard, Buehler, Bauer, Scherzer -
Marcel sees a thin platform, market pays for track record): log prior AAV (fa_signings
self-join across winters, player_key; missing-dummy for partial coverage), career-to-
date + peak-3 WAR from war_daily, and flip the fully-implemented `tj` arm ON
(fa_market.py:1276-1312, X_FEATURES["tj"]=False today) with its survivorship caveat.
Gate: wave-lab paired bootstrap vs placebo columns (fa_market.py:1320-1333 standard);
track the biggest-misses list directly.

D3. **Star-tier WAR input repair** (Gate 1 feeding Gate 2): reduced shrinkage or a
star-cohort term in `fit_war_map` (fa_projection.py:1537), or a market-side max-season-
WAR-last-3y feature. Gate: Gate 1 pooled holds while act_ge4 improves; then Gate 2 mega
+ ptier:ge50 bias.

D4. **Direct AAV head**: third regression on log(NPV AAV) (npv_aav_usd exists on all
1,615 rows) with guarantee-stage features + years_f; serve as projAav (guarantee/years
columns unchanged) with an explicit coherence disclosure. Attacks the tier biases
directly without re-litigating the banned coherence arms.

D5. Cheap hygiene: re-run the dpw forecast eval (data/dpw_forecast_eval.json is
2026-06-10, decided flat5-vs-trend on the PRE-re-anchor series; on the CURRENT
re-anchored series the last two winter moves are +15.6% then -0.9% - re-run the eval
and let it decide, do not assume a rising market). Expand the deferral ledger (6 of 26
entries have schedules; 0 missing above $200M but 26 flagged unverified). The
fa_market.py:12-13 discount docstring is CORRECT at 0.07 (clemens_2026 net_7_flat
overlay, valuation_sets.py:289-292, over the base 0.09 at
value_framework_config.yaml:258) - optionally add that provenance parenthetical, do
NOT change the number (correction #8).

D6. /fa/ UI (with Lane H): render the pooled_by_pos_group BIAS table in the
accountability panel (it is already exported in fa_meta.json, fa_export.py:833-834, and
rendered NOWHERE - the actual evidence of systematic under-pricing is hidden); fix the
AAV band absurdity (flat 9.65x guarantee ratio / point term gives Grisham a $77.4M P90
- either per-tier band scaling behind a lab gate or an explicit on-page disclosure);
make P10-P90 visible on touch (currently title-attribute-only, fa.js:632-635).

D7. Leak items S2 (test-winter supply counts eventual signees - recompute from
constructed class membership, assert Gate-2 insensitivity) lands here with D1's
instrumentation run.

---

## LANE E: Alchemy Lab (ladder, RP<->SP, position-change model)

E1. **Ladder: verify-and-document, do NOT refit.** Verified 2026-08-05: exposure-
weighted sum = -0.0 exactly (imposed by _recentre, positional_fit.py:210-222); served
values_fielder_centred 8 fielders sum to 0.01 (pure rounding of exact 0); the +1.22
folklore offset = 9.77/8 confirmed; display and model agree bit-for-bit up to the
stated constant; NO served number rides a non-zero-sum ladder anywhere (POS_ADJ
exposure basis; proj_ml pos_adj_prior is player-own-observed, not a table; ewar centres
FRP within (season,position); fa_projection uses observed runs). 14 tests pin this.
Remaining actions: fix the stale pal.js:907-908 comment (claims R2 0.9779/9,101; artifact
is 0.9759/4,968); fix pal/index.html meta description (says "computed from Statcast";
it is a BRef runs_position inversion, and the description predates 4 of 7 tabs);
document the two real calibration sensitivities on-page if not already (window choice
2012-2026 vs 2018-2026 moves rungs ~0.3; DH-exposure spec moves C ~0.11).

E2. Registry truth: MODEL_REGISTRY pal_conversion row says "provisional" while
data/pal_eval.json verdict.status is "downgraded" and the gate rule says a failing
direction downgrades the row. Fix in data/model_registry.json + regen (or document why
provisional IS the downgraded state, if that is the intended semantics - check the
gate rule text first).

E3. **RP->SP and SP->RP models** (RP->SP FAILED its gate: rho -0.2062 vs war_delta,
n=25; SP->RP PASSED +0.2916, n=61 - do not change its shipped weights without a gate):
- RP->SP: the binding constraint is n, not features. Path: expand the closed-event set
  with the PAL gamelog lab's lane_a recovery (+89 mid-year/swing-bridge tagged events,
  data/pal_gamelog_eval.json - NOT this plan's Lane A) and re-gate the RP->SP
  direction on the expanded set with the INCUMBENT war_delta target per decision #8's
  recommended default; the held-role target variant waits for owner sign-off.
- SP->RP gets a tested deliverable too (the owner asked to improve BOTH): run a
  pre-registered CONFIRMATION re-gate of the shipped SP->RP model on the expanded
  n~100 set (a free power upgrade; ship nothing unless it FAILS, in which case
  escalate to the owner). Note tools/pal_xrv_lab.py gates BOTH directions
  (DIRECTIONS tuple) - its verdicts apply per-direction.
- Run the never-run W3 ARM-1 aStuff+ blend gate (tools/pal_xrv_lab.py, pre-registered
  thresholds COVERED_MIN=12, PAL_XRV_W=0.5) now that data/stuff_plus_aaa.json covers
  1,379 AAA arms. If it passes, flip EEPHUS_PAL_XRV on in the pipeline env; if
  COVERAGE-STARVED, record the verdict and keep the flag off.
- NEW FEATURE LANE (pre-register first): TTO splits are ingested NOWHERE; the cheapest
  honest source is deriving times-through-order deltas from the play-by-play already
  cached in .cache/game_feeds for betting. Build the derivation as a data job, then
  gate a tto_leakage-style feature for the RP->SP direction. Do not touch the shipped
  SP->RP weights without a gate.

E4. **Position-change model for hitters (the owner's arm/height ask), designed to
respect the standing refutations:** positional_fit.py is already a validated engine for
MOVE SIZE (MAE 5.682 vs carry-over 6.733, CI [0.45,1.63]) with a NULL on who-gets-
demoted; it has NO anthropometrics. The arm gate NO-SHIP proved raw arm-by-position is
confounded by throw context (1.94 mph context-adjusted spread vs 3.80 within-position
SD) and OAA already contains legs+arm (double-count risk). The defensible shape:
- Add anthro/tools as a PRIOR ON z AT UNOBSERVED POSITIONS ONLY - where the current
  model extrapolates blind - never as an additive bonus at observed positions. Prior
  inputs: height/BMI (ingest MLB heights by extending the sports/1/players bulk call
  PAL already makes per season, pal_export.py:175-188 - VERIFY field names on a cached
  response first; prospect heights exist: draft_players 2,178/2,860, FG frame extras),
  sprint (OF destinations only - CF r=+0.428 vs OAA rate, infield r~0), context-
  adjusted arm (C and OF only per the verdict), scouted throw/field for prospects
  (coverage 48%/61%).
- Test the owner's specific claims DIRECTLY as pre-registration hypotheses: P(1B
  innings | height<70in) among feasibility counts; "weak arm pushes 2B" context-
  adjusted (the verdict doc predicts SMALL in the infield - report whatever it says).
- Validation: add the anthro-prior as a FIFTH scored arm in the existing
  conversion_accuracy (positional_fit.py:864-1024) + backtest (:1049-1244) harnesses on
  identical rows; ship only on a positive MAE advantage CI. If it fails, ship the
  MEASUREMENT (the owner's intuitions tested honestly) as the deliverable.
- Surface: posfit tab gains a "projected fit at new positions" view with the prior
  clearly labeled; prospect_def_value's BMI migration pressure (the only current
  body-frame effect) gets cross-referenced, not duplicated.

E5. Wire the positional_fit feeders into the pipeline (currently ALL manual and 12
days stale vs the Aug-3 fit): savant_oaa, fielding_innings, savant_arm_strength,
savant_sprint as monthly best-effort steps + a positional_fit refit step behind a
freshness gate, then build_positional_fit_payload picks it up on the next build. Add
registry freshness stamps accordingly.

E6. PAL UI fixes (with Lane H): null-guard the converter percentile line (pal.js:543
renders "converters at th pct" when rp2sp is empty); tooltip/link on the bare
"[downgraded]" chip (pal.js:1130-1133); split the mixed-basis "FV" label (fvE
Math.round vs consensus fv fCeil under one label, pal.js:689); fix the chart reference
line mislabel (60 is the prospect band edge, not the MLB FIT tier break, pal.js:141);
dedupe the payload (pitch_mix carried twice, prospect_watch strict subset of
prospect_watch_all - ~halves those sections of the 1.04MB file); drop ALL dead
desc:true attrs (pal.js:305, 316, 331, 847-851 - nothing reads .desc); remove the
duplicate reverse_platoon computation (pal_conversion.py:346 result discarded,
recomputed at pal_export.py:634).

---

## LANE F: Leaks + bugs (fix everything, pin everything)

### F1. Leaks (from a full-model audit; flagship boundaries verified CLEAN)

Numbering note so completeness is attestable: the recon leak sweep produced S1-S8.
S3 (eFV blend lambda selected on the pooled OOS folds) is DISCLOSED-AND-ADJUDICATED -
the 2026-07-15 nested-selection adjudication measured the protocol
(data/xfv_lambda_adjudication_eval.json) and the pin discipline stands; no action.
S5 (Gate-1 T1.2 band scale fit on the pooled panel) is in-sample BY ADMISSION with a
permuted zero-info control written alongside and the OOF verdict in the lab; no
action. S3 and S5 are intentionally absent from the fix list below.

F1.1 **S1 - Betting vintage park leak (MED-HIGH, time-sensitive, currently latent).**
The vintage mode's park input is NOT vintage-dated: park_index() reads live
data/fa_meta.json Savant year-2026 factors (betting_model.py:316-328); vintage records
carry no park columns (betting_model.py:363-408); _grade passes live parks into fit and
pricing (betting_model.py:1316, 1340-1344) while the mode label claims "no leakage"
(betting_model.py:1488-1490). Latent today (0 vintage-graded games) but it contaminates
the 600-game gate sample as the box archive matures - fix BEFORE the archive is worth
anything. Fix (all three): (a) add the park index to the nightly vintage record (schema
bump in leaderboard_vintages; parks near-static in-season so no backfill needed); (b)
pin backtest parks to the PRIOR season's Savant factors where vintages lack them; (c)
correct the mode label. Regression test: mutate fa_meta park_factors, assert the
vintage-mode grade is byte-identical.

F1.2 S2 - Gate-2 test-winter supply counts eventual signees (fa_backtest.py:507-509,
fa_market.py:1438-1446). Fix with D1/D7: compute test-winter supply from constructed
class membership; assert pooled guarantee MAE moves < noise floor.

F1.3 S4 - label-window lookahead lab: executed as C6.

F1.4 S7 - draft-leak test hardening: drop the date predicate in
test_no_draft_in_milb.py:106-112 (assert 0 rows match LEAK_WHERE over ALL dates, so a
DB restore from a pre-purge backup cannot silently resurrect 936 rows); fix the two
stale "cleanup pending" docstrings.

F1.5 S8 - stale-frame cache keys: add a corpus content hash to proj_ml's frame cache
key (proj_ml.py:308-313) and the fa fits cache (fa_projection.py:339-351), mirroring
the train_hash pattern (proj_ml.py:391-397).

F1.6 S6 - trade-machine forward backtest: verify the nightly trade_value_history
snapshots (storage.py:3962-3975, wired post-chain at run_monthly.py:4167-4173) give the
documented forward cohort, and point tools/trade_machine_backtest.py at them so the
hindsight-ordering caveat starts retiring itself.

### F2. Bugs (ranked by user-visible severity; every fix gets a test)

F2.1 **Doubleheaders collapse to one odds event** (HIGH): betting_export.team_bets keys
by org pair only (betting_export.py:410-426) while the schedule yields two games and
The Odds API lists two events - last-parsed wins, both slate rows get the same prices.
Fix: key (home_org, away_org) -> list, match each game's datetime to the nearest
commence_time (parse_events already retains it, betting_ingest.py:291).

F2.2 **CLV grading is built but never wired** (HIGH): grade_clv + closing_snapshot have
ZERO production callers; record_summary reads beat_close/clv_pct that nothing writes;
the close job spends 3 real credits/day producing snapshots NOTHING consumes. Build the
back-fill grader: for each dated record row, closing_snapshot(date) -> match
event/market/side -> grade_clv -> write per decision #2 (sidecar recommended). Handle
DH game 2 per decision #3. Note: no production caller of append_record exists yet
either, so this can land before the first pick exists and be correct on day one.

F2.3 Postponed/final games neither filtered from the slate nor the closing window
(betting_export.py:320-329 ignores the status field it carries;
betting_ingest.py:364-369 lets a postponed early game anchor the close capture). Filter
both on abstractGameState.

F2.4 mlbam_ingest org codes map to the WRONG canonical side (mlbam_ingest.py:283-312:
_DIRECT maps CHW->CWS backwards, WHITE SOX->CWS, 2-letter StatsAPI codes fall through
raw): 6 org='CWS' + 36 org='OAK' rows in prospects.db today; served artifacts clean
only because exports canonicalize. Fix at the producer (_abbr_to_org ends in
trades.canonical_org) + the one-off DB repair per decision #4. Also: fantasy_export
_LB_TO_CANON lacks OAK->ATH (fantasy_export.py:406-407, dormant); card watchlist mixes
code bases (card_prices_ingest.py:695 canonical vs :715 raw team codes).

F2.5 Tankathon tests are NOT quarantined (test_scrape_lottery_spotrac.py:51,
test_lottery_extra_fields.py:73-75 skip only when the cache FILE is absent; the 24h TTL
refetches live and SSL failure returns [] -> 4 assertion failures). Gate on cache
FRESHNESS (mtime within TTL) or a use_cache_always test flag. This retires the 4
standing sandbox reds - after this, the suite must be ZERO-red.

F2.6 Em-dash gate does not cover the 7 Diamond pages or their 4 exporters
(tools/strip_emdashes.py:37-85 TARGETS). All measured clean TODAY - add them so they
stay clean. Also close the smarty hole: render_markdown enables the smarty extension
(build_site.py:568-571) which converts --/--- in article markdown to en/em-dashes
DOWNSTREAM of the source lint - configure smarty to leave dashes alone (keep quotes)
or lint the rendered output.

F2.7 Close-snapshot UTC-midnight bug: filenames use UTC capture date
(betting_ingest.py:106-108) but the slate date is US-local officialDate - an all-late
slate (~8:05pm ET first pitch) writes under UTC date+1, the once-per-slate guard fails
(double-fire risk) and CLV can never find its close. Stamp the slate date INSIDE the
snapshot wrapper at write time and filter on it.

F2.8 Canvas text clamps: eephus-gfx board renderer clamps only cell.sub - main cell
text (eephus-gfx.js:225, 239), headers (:209), legend (:252), caption (:256) are
unclamped; eephus-hub meta/sub/section rows/caption (eephus-hub.js:454-484) can
overlap. Apply the fitTxt pattern everywhere text meets a column edge.

F2.9 NaN guard: `allow_nan=False` appears NOWHERE across 216 json.dump sites (all
11,737 served JSONs parse clean today - keep it that way). Add it to the shared
writers: build_site.py:1159/1735/5251, proj_export.py:1539/2006, efv_export.py:184/307,
betting_export.py:169, fantasy_export.py:785/798, dfs_export.py:513,
card_market_export.py:599-601. One NaN reaching a payload hard-breaks the consuming
page.

F2.10 Small: eephus-ui.js favorites Promise.all with no .catch (eephus-ui.js:649-653);
delete the 4 HTML-saved-as-.json files under data/sources/samples/ (nothing reads
them); betting payload copy defects (betting_export.py:886 appends the status note
"odds feed configured" into empty_reasons - a reader is told the board is empty
BECAUSE the feed is configured; :782 says "no odds feed is configured" even when the
real state is key-configured-but-no-snapshot - branch on status.odds_feed which
already distinguishes).

F2.11 data/dfs.json policy per decision #5 (commit once generated, matching
data/betting.json), and document the tier policy in DATA_SOURCES.md or the module
docstring.

---

## LANE G: Diamond section (make it worth $15/mo)

The recon bottom line: the posture (receipts, append-only record, preregistered evals)
is genuinely differentiated, but today a paying user finds an empty DFS page, an
unpriced card screen, no streamers/two-start, no picks (correctly, until validation),
and three advertised member benefits that do not exist. Order of operations:

G1. **Preserve the QA record**: the itemized 55-finding Diamond QA lives ONLY in the
prior session's temp scratchpad (C:\Users\noah\AppData\Local\Temp\claude\
c--Users-noah-baseball-projects-BaseballR\b288db78-dd0e-4852-a112-85566e12c99e\
scratchpad\recon\qa_0.txt, qa_1.txt, qa_2.txt - verified still present 2026-08-05
evening). Copy them into docs/diamond-qa-2026-08-05/ FIRST. The 20 unfixed, as
re-verified by this recon (3 since fixed/superseded/no-action):
qa_0: (1) dynasty/callup single-basis - FIXED ffa2810; (2) streamers Date column
repeats day-pill date - OPEN (G6); (3) Buy/Sell luck-gap mixes scales - OPEN (G6);
(4) FG==SABR hitter points - correct-by-design, no action; (5) redraft missing GFX
chip - OPEN (G6); (6) invalid hash not rewritten - OPEN (G6); (7) masthead clamp -
by design; (8) /fantasy/ redirect - verified working.
qa_1: (9) mergeLocalBets orphans logged-out bets - OPEN (G5); (10) pick_reason bare
fragment - FIXED Wave 7; (11) starfield shows through DFS tables - OPEN (G6/H2);
(12) --transition-hover dead token - OPEN (G6); (13) data/dfs.json never existed -
NOW EXISTS untracked from the maiden run (decision #5).
qa_2: (14) cards section-sub mid-word ellipsis - OPEN (H/G6); (15) "Developers" nav
clip - OPEN (H); (16) cards method prose lowercase - OPEN (G6); (17) per-card GFX not
gated on priced - OPEN (G6); (18) method view lacks SCREEN banner repeat - OPEN
minor; (19) /diamond/ ragged 6-in-4 grid - OPEN (G6); (20) record guard message -
OPEN (G6). If the scratchpad is gone, treat the union of G5 + G6 + the
Diamond-touching items in F2/H2/H3 as the open list; do not chase the exact count.

G2. **Turn the two dead data taps on** (zero new modeling):
- DFS/fantasy schedule: the discriminator is ANSWERED (header note): a 22:01Z
  2026-08-05 refresh fetched a real 41-game schedule and the maiden dfs_export run
  produced data/dfs.json - the committed empty schedule (schedule.games == [], empty
  LIST, in HEAD's fantasy.json) was transient/environmental. Remaining work: commit
  the regenerated fantasy.json + dfs.json (decision #5) out of Wave 0's deliberate
  run, and verify the box's nightly 9d/9d-bis produces both the morning after deploy.
- Cards: card_prices_ingest has NO scheduled invocation anywhere (run_monthly 6g only
  EXPORTS; the crontab example never calls the ingest) - EEPHUS_CARD_SCRAPE=1 currently
  arms a scraper nothing calls, which is why /cards/ is 40 tracked / 0 priced with no
  card_comps table at all. Wire the docs/diamond-cards.md:169-178 cadence (daily
  --drops + --scrape --hot + export; weekly full sweep) into the box crontab example +
  the owner bundle, and move step 6g to the daily tail once comps exist. Locally: run
  one ingest with the env sourced to surface the parse-or-not question ("40 tracked /
  0 priced after a run = parse problem"); fix parsers if so.

G3. **DFS context joins** (the difference between a toy and a tool; all joins, no new
models): confirmed lineups/batting order (StatsAPI lineups endpoint, free), MLB park
factors (Savant park index already sits in fa_meta.json - reuse the betting join),
Vegas implied team totals (from .cache/odds snapshots the close job already pays for).
Label each honestly (the payload already carries no-backtest disclaimers).

G4. Extras per decision #6: build the exports/API page (the JSONs are already public;
a documented-schema page + per-module CSV endpoints is a build_site page + a small
exporter), defer alerts (needs accounts), reword-or-cut the newsletter card. The
pricing page currently advertises vapor on a receipts brand - do not leave it.

G5. **mergeLocalBets fix** (guaranteed data-hiding bug on account go-live day):
betting.js stores under "eephus_bets_v1" and passes rows to a.mergeLocalBets(rows);
eephus-account.js:443 mergeLocalBets() IGNORES arguments, reads its own key
"eephus.bets.v1", uploads that (nothing), clears it, and loadBets() then hides the
user's local rows. Fix in eephus-account.js (accept the caller's rows argument;
betting.js's key is pinned by test_betting.py). Land BEFORE any Supabase go-live.

G6. Remaining QA polish batch (all verified still open): streamers Date column repeats
the day-pill date on every row (redraft.js:389 - drop the column); luck-gap column
mixes plus-stat and wOBA-points scales (unify exporter-side in fantasy_export);
/redraft/ gets the GFX chip + shareSpec parity with /dynasty/; DFS tables get opaque
backgrounds (dfs.js:1075-1090); cards method strings start lowercase
(card_market_export.py method block); per-card GFX gates on priced-or-not (or renders
the screen framing); /diamond/ 6-cards-in-4-column ragged grid; invalid-hash rewrite;
diamond.js record guard message when picks exist but grades don't (diamond.js:206);
section-sub clamp + "Developers" nav clip (site.css, with Lane H); the dead
--transition-hover token (betting.js:1422).

G7. Navigation for conversion: every Diamond page's stage chip + "Diamond funds the
free site" footer line become LINKS to /diamond/ (today the only route to the pricing
page is the nav dropdown); homepage cross-module strip gains Diamond cards (today only
/redraft/ appears, build_site.py:2837-2860); 404 rail gains Trade Machine + Diamond
(build_site.py:4578-4585).

G8. **Betting daily leaderboard refresh** (lifts the 30-day vintage staleness ceiling
docs/diamond-betting.md:349-359 names, and freshens team bets/fair lines): a cheap
team-level daily recompute from .cache/game_feeds, wired as a run_daily step feeding
9e-pre. This raises the quality of every vintage the clock accrues from here - build it
EARLY so the 2027 validation grades the best model, not a handicapped one.

G9. Fantasy personalization (the moat; scope as its own mini-lane, ship incrementally):
league roster import (paste/CSV, reuse the DFS salary-importer pattern), league-size-
aware replacement baselines for the redraft ranks, and a dynasty trade evaluator on the
Trade Machine chassis with fantasy value instead of $ surplus. All inputs on disk.

---

## LANE H: Site-wide UI/UX + theme

The system is healthy (one nav constant, one token block, guarded nav copies, universal
starfield/glossary/export runtimes); these are the seams, ranked by visibility:

H1. `--border-subtle` is referenced without a definition in build_site.py:3457/3459
(-> the trademachine shell), trademachine.css:278, AND 6x in prospx/index.html (lines
~26121-46787, no fallbacks); assets/fantasy.js's 8 uses are safe (literal fallbacks).
Invalid at computed-value time, border falls back to full-strength currentColor.
Define the alias of --border in BOTH the site.css token block AND prospx's own token
block (prospx tokens win by design, H10).

H2. Diamond table dialect unification: dynasty/redraft/dfs/betting each inject a
private table dialect (.dyn-/.rd-/.dfs-/.bt-table) violating the documented ONE TABLE
DIALECT rule (site.css:1473-1480) and getting NO sticky headers. Port all four onto
.mlbstats-table inside .mlbstats-scroll (cards.js:409 already does) - deletes 4
dialects, buys the sticky/frozen machinery for free (site.css:1729-1806).

H3. Glossary tooltip coverage: five surfaces emit ZERO data-gl spans (trademachine,
betting, cards, diamond, parks; dfs wires but emits none; pal has 2). Betting (edge,
vig, closing line, units, EV, Kelly) and Trade Machine (surplus, posterior) are exactly
the jargon pages. The contract is a span + wire() (eephus-gl.js:23-26).

H4. Dim-text AA pass: replace opacity-dimming with a --text-dim token tuned to 4.5:1
per theme. Failures: .proj-dim 2.48/2.71 (chart captions, provisional markers across
/mlbstats/, /pal/, /cards/), .fa-dim/.fa-band 3.75-3.81 light on 11-12px data,
--byline-lilac 1.95 light, gold-as-text 2.13, .eephus-beta 4.04 marginal.

H5. Trade Machine shell modernization: the only module without .section-head--byline,
~15 inline styles in the generator body (build_site.py:3404-3465), no _stage_chip().
Extract to classes, adopt the standard masthead, unify MODULE_STAGE call sites onto
_stage_chip() across the seven older shells (build_site.py:377-380 documents the split).

H6. Homepage: add a data-qk-open ⌘K affordance to the sidebar (palette JS already
loads there; today the only button lives in _nav which home never renders).

H7. Dead CSS deletion (~30 orphaned selector families, ~120 lines, all verified
unreferenced): .hero/.hero-rule, .module-grid/.card.module-card, the developer-badge
family (.lead-dev-badge/.ldb-*/.dev-plus-*), .dot-sep, .mod-stage, .masthead-follow,
.lead-story .lead-img, .fa-comps, .fa-gloss*, .fa-fitorg, .bp-pos/.bp-neg,
.gl-tip-link.

H8. Version the last unstamped asset: /data/value_framework.js on /glossary/
(build_site.py:4187).

H9. Doc/generator truth: fix the stale UNVERSIONED-css cache note at
tools/gen_audit_docs.py:291 (propagates into SITE_MAP.md); betting shell docstring
omits the record tab (build_site.py:3838); the draft war-room banner's phantom
--brand-navy + dead border-radius + hardcoded #fff (build_site.py:3186-3197); the
#6f8a76 inline fallback (build_site.py:3139).

H10. DO NOT touch: the CRT ticker palette (deliberately theme-fixed), the starfield
reduced-motion exemption (owner ask, eephus-bg.js:23-27), prospx's own token block
(wins by design). The tertiary-on-dark-cards 4.39 near-miss is a note, not a change.

---

## LANE I: Pipeline hardening + cleanup

I1. (Wave 0 does the regen and the live watching.) Re-read the saved Wave-0 monthly
log for 6f/6g/9d-bis/9e/9e-pre and record data-shaped surprises in the execution doc.

I2. **Failure notification** (there is NONE today; a crashed nightly freezes the site
silently): MAILTO or a 2-line curl deadman ping in deploy/nightly-build.sh next to the
build_info.json heartbeat (nightly-build.sh:196-199). Minutes of work, converts every
silent-failure class into a page.

I3. **Extend write_ingest_health to scheduled EXPORTS**: SCHEDULED_GRADE_SOURCES covers
only 3 ingests (run_monthly.py:174). Add a SCHEDULED_EXPORTS tuple + _record_ingest
calls in the existing except arms so these go RED on failure: efv_export.regen_all
swallow (run_monthly.py:907-908 - a crash serves yesterday's grades everywhere with
zero signal), d9b proj_export (:1572), d9b2 mlb_player_export (:1587), d10b fa_export
(:1704), 9e-pre leaderboard_vintages (:1649 - a missed night is PERMANENTLY
unrecoverable and deserves RED, not info).

I4. `_patch_export_run_summary` triple-parse: the step-5 patch (run_monthly.py:3989) is
wasted on a monthly night (the chain rewrites the file ~15 min later) - guard it when
chaining. Then the tier-2 shared loader: new ts_doc.py, get() memoized on (path,
mtime_ns, size) + explicit release(), orjson when available; convert the post-d9 tail
consumers first (proj_export, mlb_player_export, headshots, fantasy refresh_live,
fa_export, build_site-in-proc - same process, minutes apart, unchanged file). Respect
the OOM design: never hold the cache across rebuild_only's peak; keep the del+gc
points working (run_monthly.py:1552-1554, 3667-3672). ~13-16 parses/night of a 73.8MB
file today.

I5. Second trade-values pass in rebuild_only (run_monthly.py:1006 runs ONE pass; the
two-pass rule is enforced only in the manual tool) - duplicate the call with
_reset_cache() between, verify ~19s runtime cost, closes the one-night lag after any
basis change.

I6. Move snapshot_board_metrics/snapshot_farm_ranks/snapshot_farm_grades AFTER the
chain (run_monthly.py:3995-4017 currently read the intermediate step-5 boot, so monthly
history snapshots record a board the site never serves; the trade-values snapshot was
already moved for exactly this reason, :3976-3985, 4167-4173). Same for
model_registry.refresh_stamps + gen_audit_docs (:4097-4112, currently one cycle stale).

I7. d5e gamelog selection reads yesterday's timeseries (self-heals nightly): note in a
comment, no change. 3a level-change reorder stays parked per the code's own owner note
(run_monthly.py:2799-2824).

I8. Retention: add the leaderboard_vintages + odds never-prune warning to
prune_cache.py's docstring (Lane A2); confirm data-shard cleanup only runs on FULL
export (storage.py:15686-15729) is documented.

I9. Box env: nightly-build.sh never sources any env file, so the box's 9e open
snapshot is a NIGHTLY NO-OP until /etc/eephus.env is exported into the cron line
(betting_ingest.py:71 reads os.environ only; only the close-job crontab line sources
it, betting-crontab.example:27). Fix the crontab example + webmaster runbook; owner
bundle item.

I10. graduates.json per decision #7 (retire the declared input or build the producer;
it is warned about EVERY run, run_monthly.py:991-1005).

---

## LANE J: Creative additions (approved shapes; keep each small and honest)

J1. Model accountability hub: one generated page that renders the registry + every
eval artifact verdict (PASS/FAIL/UNVALIDATED with dates and links) - the receipts
culture is the brand and it currently lives scattered across /diamond/ cards, fa
accountability, and betting validation panels. Cheap: the registry JSON already has
everything; add per-module deep links.

J2. Provisional-grade provenance chips site-wide (C1's chip, extended): anywhere an
eFV renders for a player with fv_synthetic_only routing, the UI says "model grade -
no scout consensus yet" with a glossary tooltip. Honesty + it advertises the model.

J3. "Why did this number move?" wire events for the board: the movement engine already
de-noises movers; add an eFV-delta wire event type on rebuild nights (top N absolute
display-grade movers with the driving feature named from the explainer chips). Feeds
the homepage wire + gives Diamond alerts (G4) a data source when accounts arrive.

J4. FA accountability panel bias table (D6) doubles as public receipts for the AAV
improvement program: show before/after when D-lane ships.

J5. Card watchlist self-service: an "add a card" flow writing to localStorage overlay
on the served watchlist (no backend needed pre-Supabase), so collectors can track
cards the curated 40 miss. Clearly labeled local-only.

J6. Parks cross-links: /parks/ park factors link into betting (park term) and DFS
(park-neutral disclaimer) methodology sections and vice versa - three pages explain
the same physics today without linking.

---

## LANE K: Artifacts + registry refresh (LAST - reflects everything above)

Ground rules: WebFetch every artifact before editing (5 of 10 were never fetched this
recon: writers-guide 764b16a0, branding 4e5d4321, webmaster-runbook 48682fec, beta-diff
e621010e, private-plan 94746e21). Redeploy with the `url` parameter so URLs are
preserved; keep favicons stable. NEVER "harmonize" these deliberately-distinct numbers:
the three unscouted denominators (2,720 constant-only / 2,632 routed-away / 2,608
active-only) and the two dpw quantities (series 2026 winter $17.29M vs served ex-ante
2027 forecast dpw_usd $17.97M) are all correct in their frames.

K1. data/model_registry.json: fix the 5 dead/renamed tool paths (xfv_hitter notes ->
xfv_tail_lab.py deleted + xfv_lab_runner.py renamed efv_; xfv_pitcher notes -> same +
xfv_ml_lab.py renamed; xfv_surrogate_label notes -> efv_surrogate_lab.py deleted;
tbs_prospect metric -> tbs_xfv_backtest.py renamed tbs_efv_backtest.py). Leave
archetype_comps ("ABSENT from the tree" is the point) and card_market_index (honest
unvalidated) alone. Regen MODEL_REGISTRY.md via tools/gen_audit_docs.py. Also E2's
pal_conversion status fix. Freshness/glossary coupling is fully green (211/211) -
keep it that way for every row this omnibus adds.

K2. Index artifact (2f184dc8): restamp basis + suite to the post-omnibus-2 values;
"seven waves, 7319b8b to f20e85c" becomes the range through THIS execution's tip;
count commits fresh at edit time (rev-list conventions differ - write ranges). Add the
Wave-7 line (betting validation panel + close scheduler) and an omnibus-2 section.

K3. Roadmap (c135328a): restamp (currently says 5f03086 / 3,051); flip the Q3 omnibus
section to shipped-status (seven waves; draft-anchor RETIRED; six eFV no-ships; RoS
owner-override with one-line revert); add the betting clock start 2026-08-05 + 600-game
gate as dated facts; then add omnibus-2 outcomes. Keep beta "sync HELD".

K4. How-eFV-works (a17c8118): drop the "glossary says 2011-2023" parenthetical (now
2011-2024); choose the tense of the "now reach a production-only model" sentence from
the BOX/SERVED state, not the local file - rosters_by_org.json is gitignored, so the
local Wave-0 regen does NOT change production; production flips when the decision-#9
box one-off runs (or Sep 1). If the box run is pending at edit time, write it as
shipping-with-the-next-box-monthly. Add C-lane outcomes (protocol re-power, any
ships/refusals).

K5. SABR (21c2382f): fix BOTH internal suite counts (3,376 at ~line 190 AND 3,051 at
~line 1249 -> current); do NOT touch the two dpw figures; optionally add the RoS
de-aging override as a fourth worked example (owner call, low priority).

K6. Monetization (75394762): add the measured Odds API plan (3 credits/snapshot, 186
planned/mo vs 500 budget, from data/betting_status.json); tie the Step-1 betting
precondition to the concrete 600-game vintage gate + current t; name scraping as the
live card source with the [NEEDS] quotes as the licensing upgrade path. Keep all 5
[NEEDS] placeholders - they are genuinely open.

K7. Webmaster runbook (48682fec): verify it covers the 15-minute close-job cron, the
vintage snapshot cron, the /etc/eephus.env sourcing fix (I9), the card-ingest cadence
(G2), and the prune knobs (A3) - this is the artifact most likely to have real gaps.
Beta-diff (e621010e): append waves 5-7 + omnibus-2 do-not-clobber entries; sync still
held. Private-plan/writers/branding: verify stamps, propagate deltas.

K8. Suite count discipline: cite the recorded number from the execution doc; never run
pytest just to restamp an artifact.

---

## 6. Verification protocol (every wave)

1. Suite from prospect-tracker/, green (after F2.5: zero reds, no exceptions).
2. Any basis-adjacent change (C2, anything touching consensus/fv_effective/dpw): TWO
   export passes + mover table + single-basis guards + golden fingerprint discipline.
3. UI changes: real-browser pass on the touched pages (the py_mini_racer harness
   cannot see layout), both themes, 390px + 768px + desktop; dash lint + copy_lint.
4. Model changes: pre-registered gate, controls per EFV_GATE_STANDARD (or the lane's
   own gate), ship/no-ship verdict written to docs/ + registry row + MODEL_GLOSSARY
   entry; refusals are deliverables.
5. Pipeline changes: one full local monthly + chained daily after the batch, log read
   end to end, ingest_health green, artifact mtimes sane.
6. Per-lane commits with explicit paths; execution record appended per wave, not at
   the end.

## 7. Reporting requirements

The execution session ends with: (a) docs/EXECUTION_2026-08-XX-omnibus2.md (what
shipped, what was refused with evidence, mover tables, the owner-decision outcomes);
(b) memory record + MEMORY.md index update; (c) the final report to the owner leads
with: the two taps (DFS/cards) state, the font specimen link, the AAV instrumentation
answer (D1), any eFV ships/refusals, and the open owner-decision list from section 4.
