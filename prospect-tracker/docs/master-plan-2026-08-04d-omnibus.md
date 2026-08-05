# Master plan 2026-08-04d: omnibus (repairs, models, Diamond, artifacts)

STATUS: PLANNING. Written for Claude Opus 5 to execute end to end. Recon behind every
lane ran 2026-08-04 (14-agent workflow, per-lane findings summarized inline; trust the
file:line references, they were verified against the working tree at main 5f03086,
suite 3,051/0 green). Owner decisions in section 1 were collected via decision queue
on 2026-08-04 and are LOCKED; do not re-ask them.

## 0. Standing rules (all lanes)

- Never edit source while pytest runs. conftest git-restores build churn at session end.
- Suite must stay green (3,051/0 baseline). Run the full suite after every lane, and
  after every dead-code batch.
- No `git add -A`. Commit explicit paths. Push needs `git config http.sslBackend schannel`.
- Generated HTML (index.html, fa/, projections/, prospx/, etc.) is owned by build_site.py.
  Never hand-edit it. Exception: the three static nav copies (prospx/index.html ~8732,
  collegesavant/index.html, collegesavant/pitcher_index.html) which are hand-edited IN
  THE SAME COMMIT as any NAV_ITEMS change (pinned by test_collegesavant_nav_in_sync).
- User-facing copy: no em dashes (tools/strip_emdashes.py --check + tools/copy_lint.py
  gate), FV/tool grades display CEILING, eFV and "+" stats round nearest.
- Served prices run valuation set `clemens_2026` with `fa_implied` DISABLED. Check
  vf.active_valuation_set() before claiming anything reaches a served price.
- Any basis change needs TWO export passes. Model changes need a registry row + eval
  artifact + freshness-map entry (model-audit standing rule). Never sum ML quantile points.
- The banned-experiment ledger is binding. Relevant entries are quoted per-lane below;
  when in doubt read data/model_registry.json rows xfv_hitter/xfv_pitcher/xfv_tools and
  docs/master-plan-2026-08-04-repairs-ewar2.md:391-397 before proposing an experiment.
- eFV grade reads go through efv_board_scale.board_value (the single-basis rule,
  fixed 2026-08-03). Never introduce a second basis on any new page.
- OOM: the deploy box runs near a ~6GB ceiling around run_monthly steps 6-6b6. New
  exports must reuse the loaded corpus or run in the daily tail. Respect
  EEPHUS_MAX_WORKERS / EEPHUS_SKIP_INPROC_BUILD conventions.

## 1. Owner decision ledger (LOCKED 2026-08-04)

| # | Decision | Answer |
|---|----------|--------|
| 1 | Betting odds source | The Odds API free tier (500 credits/mo) for daily ML/runline/totals; props deferred or fair-line-only until a paid tier is justified |
| 2 | Bet tracker + badge backend | Supabase accounts (existing layer) |
| 3 | Card pricing source | Scrape sold listings. MITIGATE per lane C4: throttled, cached, immutable raw store, publish DERIVED index values only (never republished raw comps), manual-CSV fallback path built in, SportsCardsPro licensed CSV documented as the clean swap if scraping breaks |
| 4 | Diamond gating at ship | Prep-only, fully public, "Diamond preview" labeling, gate flag wired but OFF; no Stripe yet |
| 5 | Diamond extras | ALL FOUR: data exports + JSON API, eFV movement alerts, DFS lineup optimizer, weekly newsletter |
| 6 | Base site pricing | Everything outside Diamond stays free forever; Diamond $15/mo is the only paid tier |
| 7 | Writer bench | 3-5 writers; schedule sized for 4-6 articles/week |
| 8 | FO job timeline | Flexible/opportunistic; portfolio artifacts kept perpetually current |

Owner asks still OPEN (surface in final report, do not block on them):
- Cloudflare analytics numbers (monthly uniques/pageviews) to replace scenario ranges
  in the monetization artifact.
- Whether the deploy box has a live assets/eephus-config.js (Supabase on in prod).
  Gates C5 entitlements and the server-backed bet tracker actually functioning.
- Confirmation to delete the older untracked prospects.db backups (A8, disk lane).

---

# PART A: REPAIRS AND PLATFORM HYGIENE

## A1. $/WAR page fails to load (owner bug; smallest fix in the plan)

ROOT CAUSE (byte-exact): assets/fa_dpw.js:318 fetches RELATIVE URLs
`["data/fa_meta.json", "data/fa_dpw_series.json"]` from a document served at /fa/, so
they resolve to /fa/data/... and 404. The loop exhausts, ensureData() resolves null,
and lines 363-366 render "The $/WAR series failed to load." The view (/fa/#view=dpw)
has NEVER worked in production. Data is healthy; the clemens_2026/fa_implied context
is a red herring (fa_export.py:811 reads the JSON off disk, not through vf).

SECONDARY: fa_meta.json's inlined dpw_series is STALE pre-R7 (2026: 14,919,577) while
data/fa_dpw_series.json is post-R7 (17,293,779). The JS prefers the stale fa_meta copy.

FIX:
1. fa_dpw.js:318 -> root-absolute: `["/data/fa_meta.json", "/data/fa_dpw_series.json"]`
   (match the working pattern at fa.js:100).
2. Re-run fa_export.py so lines 811/832 re-inline the current series into fa_meta.json.
3. Rebuild site (build_site restamps _FA_DPW_VER, build_site.py:63/3370).
4. New test: assert fa_meta.json's dpw_series equals data/fa_dpw_series.json so a series
   rewrite without a re-export fails loudly (writers: fa_backtest.py:661 series,
   fa_export.py inliner).
DO NOT touch value_framework as part of this; display-only lane.

## A2. Clay Holmes negative rest-of-season surplus (rental valuation)

THE OWNER'S PREMISE IS DISCONFIRMED and the final report must say so plainly: the RoS
leg does NOT charge the full contract or full-season salary. proj_export.py:370-378
(_apply_contract) already computes `ros_d = V(war*ros_frac) - cur_sal*ros_frac` with
ros_frac=0.301 and npv=0 for a rental (Spotrac: Holmes signed through 2026, $8,941,176).
Reproduced: V(0.69*0.301)=$1.9285M minus $2.6913M = -$762,764 ~ served -0.8.

TWO REAL DEFECTS:
(a) Convexity proration penalty: the production leg prices V(f*w) instead of f*V(w).
    The convex tier kernel (value_framework.py:457-482) prices a 0.69-WAR pitcher's 30%
    remainder at a 0.21-WAR player's per-win rate. -$47K for Holmes; up to -$0.79M for
    mid-tier (2.5-3.0 WAR) rentals per the SHIPPED R5.2 measurement documented at
    proj_export.py:340-364. This is a mechanical proration error, not the banned
    unmeasured "premium constant".
(b) Talent basis: war_now = war[0] is the FIRST_SEASON=2027 (age-35) projection, one
    aging year PAST the season being sold. V(0.69)=$6.56M/season < $8.94M salary, so the
    full season prices negative and the remainder inherits the sign. His warPTH[0]=1.23
    would price +$0.75M.

FIX (in order):
1. MECHANICAL (ship): proj_export.py:375 -> `ros_d = ros_frac * (_season_value_usd(float(war_now), 0, dpw) - float(cur_sal))`
   i.e. f*(V(w) - salary). Keep published rosWar = war_now*ros_frac for display.
   Mirror in bayes_trade_value.py:4648-4649 (pre-arb shadow RoS) and the band adjuster
   at 4313-4317 (p10/mid/p90 legs currently all price V(quantile*ros_frac)).
2. MEASURED (gate before ship): de-age the RoS talent basis by one year along the fitted
   aging curve (or blend current-season Marcel) for the RoS leg only. The in-code comment
   chose war[0] deliberately, but it conflates banked value with talent inference: using
   2026 evidence to update the talent ESTIMATE is not double-counting banked production.
   Gate: backtest RoS pricing vs realized deadline-acquisition outcomes if data permits;
   at minimum show the sign/ordering change on the 964 priced vets and eyeball the top
   movers for face validity. Record either way.
3. DECIDE and document (not silently): whether the trade BOARD floors rental
   trade_value_mm at $0 (club can always decline; DFA caps downside). Recommendation: NO
   floor; a negative rental price is real information (salary-retention trades exist).
   Document the convention on the trade machine page.
4. Fix the vacuous test test_rest_of_season_control.py:73-95 (asserts an expression
   equals itself). Pin the new f*V(w) arithmetic with independent constants.
5. Regen: proj_export -> mlb_projections.json, then trade board export (TWO passes:
   apply_platform_surplus re-points at the second).

RISK: f*V(w) raises every mid-tier vet's surTotal (peak ~+$0.79M near 2.5-3 WAR),
shifting trade-board order. Snapshot before/after and include the mover table in the
commit message or execution doc.

## A3. MLB Projections: name truncation + headshots

TRUNCATION ROOT CAUSE: desktop truncation is NOT reproducible on current code (measured
0 clipped names at 360-1536px, both font stacks). The reproducible defect is the phone
collapse: site.css:3030 `@media (max-width:720px) .mlb-card { grid-template-columns:
1fr auto !important }` puts the identity block in the content-sized SECOND column; the
34px rank chip stretches across the 1fr first column; at 320px the fr track collapses
to 14px and long names clip. If the owner saw it at desktop width, the deployed box is
serving a stale pre-2026-07-30 bundle (site.css:2015 .proj-app .proj-player
max-width:320px truncated the old table; memory records the box owing regens).

FIX:
1. In the <=720px blocks (site.css:3029-3032 and 3261-3286):
   `.mlb-card { grid-template-columns: 34px minmax(0,1fr) !important; }` plus
   `.mlb-rank { justify-self: start; }`. One change fixes the stretched rank pill, the
   ragged per-card columns, the 320px collapse, and the only real ellipsis. NOTE: these
   rules are SHARED by /fa/ and /projections/; eyeball both boards at 390px after.
2. Verify deployed asset hashes vs local (site.css 5d06f674, projections.js ba427dc2)
   by view-source on live /projections/; if stale, the fix is the owed deploy regen.
3. Rescope site.css:2015 (.proj-app .proj-player max-width) to team cells only, and give
   .proj-cmp-name the ellipsis box its comment (projections.js:1300) falsely claims.

HEADSHOTS (feature):
1. proj_export.py `_prospect_rows` (~716): add `"mlbam": p.get("mlbam_id")` (vets carry
   it at :496 already; measured 1324/1324 vets vs 0/209 prospects).
2. projections.js renderTable: 24px headshot in the identity block, porting the FA row
   pattern exactly (fa.js:267-286 + .fa-row-photo/.fa-row-headshot css site.css:2758).
   24px fits the 42px identity budget; anything bigger needs a CARD_TRACKS change (one
   constant, projections.js:1157, stamped at 1183/1194) plus the height bump at
   site.css:3197 (heights are virtualization promises).
3. Prospect rows: do NOT use the d_people:generic 67 URL (silhouette-at-200 for
   milb-only ids). Fetch data/photo_ctx.json once and build ctx-aware URLs exactly like
   prospx/index.html:36986-37005.

## A4. Positional ladder "runs/650 must sum to 0" (-3.96)

THIS WAS ALREADY ADJUDICATED (2026-08-03 audit, Owner bug 3, commit 94b11c4): the
model's EXPOSURE-WEIGHTED sum IS exactly zero by construction (positional_fit.py:222
_recentre). The -3.96 is the EQUAL-WEIGHT sum of the nine displayed rungs, nonzero
because DH is 7.53% of exposure, not 1/9; the DH term alone contributes -4.43. The
artifact deliberately publishes it (positional_fit.py:292 sum_equal_weight_9) and
test_positional_ladder_sum.py REQUIRES it nonzero. The equal-weight sum is also
window-dependent (-4.67 / -2.62 across windows), so pinning it to zero would bake a
window artifact into the convention.

RESOLUTION that honors both the owner's ask and the adjudication: change the DISPLAY,
not the model. The artifact already publishes `identification.values_fielder_centred`
(positional_fit.py:298), in which the eight fielding rungs sum to EXACTLY 0 by
construction (the folklore convention readers check against). Make that column the
page's displayed runs/650 (selection in build_site.build_positional_fit_payload,
build_site.py:4299, plus the pal.js renderer), with DH shown against the fielder zero
line and one plain-language sentence on the convention. The model and every downstream
consumer (prospect_def_value.py) keep the exposure-centred `values`. Do NOT change
_recentre. Update the pal.js explainer (assets/pal.js:932-946) and keep
test_positional_ladder_sum.py's invariants (they pin the model, not the display);
add a display-layer assertion that the rendered fielder column sums to 0.000.

## A5. Homepage: human editorials only

ROOT CAUSE: build_site.py:3184 swaps a generated "From the data" lead card into the
lead-story slot whenever the newest human article is older than 21 days
(_data_lead_html, lines 2976-3023; gate _article_is_stale:3025). Generated content
never enters the articles list; there is no flag to filter, just this one call site.

FIX: set `data_lead = ""` at 3184 with a one-line owner-decision comment, DELETE the
now-dead machinery (_data_lead_html, _lead_event_headline, _article_is_stale,
_LEAD_STALE_DAYS, _LEAD_EVENT_FRESH_DAYS, comment block 2937-3031; keep events/players,
they feed the ticker/feed/movers), simplify 3178-3201, rebuild site, commit code +
regenerated index.html together. The same wire facts remain on /news/, the sidebar
feed, ticker, and movers modules; no test pins the generated lead. Rerun
test_news_page.py + copy gates after rebuild. KNOWN CONSEQUENCE to state in the report:
with one article dated 2026-06-05, the homepage lead will look stale until new
editorials publish (that is what the Part D writer schedule fixes).

## A6. generateGFX: face-centered photos on list GFX, geometry-gated

CONTEXT: photos were removed from PROSPX list layouts 2026-08-04 ("photos off the
LISTS only; hero cards keep theirs") because they looked janky; this lane supersedes
that decision WHERE GEOMETRY ALLOWS, without regressing the anti-truncation wins.
test_gfx_chip_layout.py:208-233 pins the removal and must be REWRITTEN in the same
commit (its own docstring prescribes this), not deleted.

KEY ENABLER (verified live): the mlbstatic CDN is Cloudinary and honors
`c_fill,g_face,w_{W},h_{H}` transforms on both '67' and 'milb' contexts with
Access-Control-Allow-Origin:* -> genuinely face-centered crops server-side, no client
heuristics. photo_ctx.json is fresh: 7,614 ids, 88.5% real-photo coverage.

IMPLEMENTATION (phases, from the recon):
0. Centralize a face-crop URL builder: extend _gfxHeadshotURL (prospx/index.html:33997)
   to accept a target box -> `c_fill,g_face,w_{2w},h_{2h},q_auto:best`; ctx from
   photo_ctx ('none' emits no URL); keep NO generic overlay so misses 404 into the
   existing degrade chain (team-logo cell -> silhouette). One function so a CDN
   transform lockdown reverts in one place.
1. PROSPX rows layout: in _gfxListGeoFor (35434) add
   `photoW = (rowH >= 40 && colW >= 320) ? Math.round(rowH * 0.75) : 0` and subtract
   photoW+6 from the name budget the search scores. Measured result: photos appear on
   Top 10/25 in ALL 7 formats and Top 50 in landscape/board/story/tall; Top 100 wide
   and portrait self-exclude. Render the well between rank and name in _gfxListRowHtml
   (35491) reusing _gfxAvatar's onerror pattern; photos default ON where the gate
   passes; restore the checkbox for rows lists (35843). TILES stay names-only (their
   charter); FARM legacy untouched (no mlbam).
2. Fix the existing face-squash jank everywhere: eephus-gfx.js:383 and
   eephus-hub.js:406 draw the 2:3 source into a square. Fix by feeding square
   c_fill,g_face URLs (build_site.py:1655-1658 news shotURL; fa.js:281/1250/1342;
   projections.js:1361), zero canvas-code change. Also swap the hero/compare/mini-card
   calls (34500, 35158, 35225) to exact-aspect face crops.
3. Rewrite the test contract: photos on rows lists where geometry allows, face-centered,
   name_field >= 200 WITH photo subtracted, photoW == 0 wherever rowH < 40 or colW < 320,
   the transform string present in _gfxHeadshotURL, tiles still photo-free.
   Update docs/generate-gfx.md.
RISK: c_fill,g_face is not an MLB-documented contract; failure mode must stay "current
pre-photo look", never broken images. Verify transform URLs from a normal browser
(sandbox needed verify=False for local cert chain reasons).

## A7. Glossary: Library section + Sources & Methodology accuracy + ad-card GFX

A7a LIBRARY (new glossary view): register a 'library' view in ALL FOUR places or it
silently hangs (the 2026-06-10 lesson): build_site.build_glossary chip row
(build_site.py:3766-3771) + glossary.js whitelist (:53), view->body map (~:207),
dispatch (~:219), plus renderLibrary(). Content: cards grouped "Full pages" /
"In-module artifact pages" / "Player pages", each row = link + one-line purpose.
Include (recon-verified inventory): /parks/ (+#method), /sources/, /history/, /news/,
/articles/, /team/, /fa/#view=dpw ($/WAR page), /fa/#view=archive + #view=model +
#view=tracker + #view=fits, /projections/#view=teams + #view=accountability,
/prospx/#tab=timemachine + #tab=charts + #tab=draft + war-room + farm tendencies,
/pal/#posfit=ladder (positional ladder page) + the other PAL tabs,
/glossary/#view=models ("Models & Proofs", the eFV artifact page). PUBLIC ONLY per the
owner ask: EXCLUDE the dark previews (#tape=1, #cards=1) and plain module leaderboards.
Cross-check against SITE_MAP.md. Keep it hand-maintained in glossary.js per the ported
prose convention.

A7b SOURCES & METHODOLOGY ACCURACY (all in assets/glossary.js _methProseHTML:324-541
and hand-edited data/glossary.json; build_glossary_data.py must NOT be rerun):
Fix these EIGHT stale claims (verified against ground truth):
1. "accuracy-weighted... Pipeline 1.06 / FanGraphs 0.94" (L373-375, FAQ L533-534):
   source weights REVERTED TO EQUAL 2026-07-25 (data/source_weights.json, unearned).
2. Worked example "$7.7M/$9.7M/$15.1M" (L428): current v44 table is $6.97M/$8.76M/$13.63M.
3. "~3,800 labeled prospects (2011-2023)" (L339): window is 2011-2024; re-count the pool
   during the edit (efv_dataset.DEBUT_YEARS).
4. Outcome buckets "(bust/role player/regular/star)" (L446): engine has FIVE:
   bust/bench/regular/good/star.
5. Surplus section + changelog: add the EV objective change
   (isotonic-real-v6-evframe-2026-07-31, $0 floor gone).
6. No valuation-set disclosure: add clemens_2026 (fa_implied disabled) to references +
   one surplus-section sentence. Wording only; do NOT touch config.
7. Changelog ends 2026-06: add 2026-07 quantile normalization, 07-25 equal-weight
   revert, 07-29/30 anchor + board-scale recalibration + clemens_2026 default, 07-30
   outcome_implied_fv re-key, 07-31 surplus EV frame.
8. data/glossary.json terms: fv_to_war_table (publishes retired survivor anchors
   60->3.0; served empirical EV anchors are 60->1.44 etc; this is the Quantity A/B
   trap), bust_prob (Sickels/McDaniel table vs empirical p_bucket_given_fv),
   value_framework ("v32.1" retired formula), dpw_tier + surplus_value (state the
   fa_implied re-anchor as live; it is not, under clemens_2026), consensus_fv
   definition line ("accuracy-weighted" contradicting its own methodology text).
DO NOT churn the verified-accurate claims: lambda 0.70/0.57, 9% discount, WAG
constants, farm tree 65/18/9/8, backtest window 2017-2023, bWAR-site-wide.
Bump glossary_version, keep slugs stable. Where a number can be computed from a live
artifact instead of re-hardcoded, do that (the _methAccuracyChart pattern) so it
cannot rot again. Registry side-fix found in passing: model-registry
xfv_lambda_confirm row says "pit 0.54", actual 0.57.

A7c S&M AD-CARD GFX: add a generateGFX card for the Sources & Methodology section that
acts as an eephus.io advertisement card: eFV model headline (what it is, one-line
method), the honest eval wins vs consensus (from xfv_eval/model registry artifacts;
pull numbers from artifacts at render time, never hardcode), site URL. Route through
eephus-gfx.js (glossary already has GFX plumbing). Copy gates apply; grades ceiling;
no em dashes. Claims must match A7b's corrected prose (equal weights, EV surplus).

## A8. Dead code purge (batches; suite green after each)

From the full-repo reference graph (all .py/.sh/.md/.yaml/.txt). Re-run the scan at
execution time (docs added since could re-cite a stem). FALSE POSITIVES that look dead
but are LIVE, do not delete: archetype_comps_export.py, statcast_aaa_hitters.py,
aaa_physics_export.py, player_news.py, savant_arm_strength.py, farm_grade_backtest.py,
fix_encoding.py (run_monthly.py:1854 subprocess), scripts/probes/*.

- BATCH 0 (zero risk): git rm qa_out.txt, surplus_backtest_real.py.bak-recalibrate,
  data/xfv_ungraded.json.pbust-backup-20260725, tools/fg_giants_2026/; delete untracked
  0-byte storage.db.
- BATCH 1: the ~379 tools/*.py referenced by NOTHING outside tools/ (~2.4MB; session
  probe families _frontier/_am/_prem/_sweep/_gn/_idea/_arch/_dpw/_cons/_comb etc.)
  EXCLUDING the 12 pinned by kept tools (_am_crossmodel_lab, _am_fa_gate2, _fa_tj_pt,
  _frontier_ablate, efv_cohort_lambda_lab, efv_pitcher_label_harness, ifa_pedigree_lab,
  offline_leverage, pwoba_ev_arm_lab, star_mean_head_backtest, win_prob_walker,
  xwoba_projection_blend_lab). Include orphan _*_out dirs whose entire lab family is
  deleted. KEEP: bucket_age_head/ (registry-cited), pitcher_label_candidates/
  (docs-cited), tools/pbust_thin/ (production-docstring-cited; 29.7MB, archive
  out-of-repo only if size matters).
- BATCH 2 (owner-sign-off tier, but the owner's blanket "delete all dead code" covers
  these; note them in the report): build_glossary_port.py,
  pipeline_international_backfill.py, build_glossary_{copy_pass,v2_update,gmli_add,
  consensus_weight_note,war_rate_add}.py (KEEP build_glossary_data.py),
  draft_anchor_backfill.py ONLY after verifying in prospects.db the backfill ran,
  milb_pitch_rates.py (its deploy-excluded data asset stays).
- BATCH 3 (coupled deletions): (a) park_factors_export.py + its test + the unfetched
  display sidecar; (b) trade_machine_backtest.py + test (only-own-test rule);
  (c) efv_surrogate.py: KEEP the registry loss-ledger row (repo convention: ledgers
  are permanent records); delete the module + lab only if the row can point at the
  eval artifacts without importable code, else keep. Do NOT delete forum_notify.py
  (wired by C5) or export_aaa_ball_by_ball.py (roadmap-cited).
- DISK (not git; owner-confirm in report before doing): drop
  prospects.backup-20260725*, prospects.db.bak-intldate-*, prospects.db.bak-jbchimera-*
  (repairs shipped + verified 2026-08-01); keep the newest 2026-08-04T212141 backup.
  Reclaims ~4.3-5.7GB.
Verification per batch: full suite green; grep deleted stems -> zero dangling refs.

## A9. run_monthly runtime program (ranked; measured or comment-measured baselines)

Byte-exact dead logic found: run_monthly.py:310-312 sets CAREER/ZONE/STATCAST
_FRESH_DAYS = 0, making every v19 freshness gate unreachable (_is_career_fresh:
`days < 0` never true); fielding_positions.py:226-245 fetches versa SEQUENTIALLY with
a 50ms sleep (measured 437s) and its 7-day gate always misses monthly cadence.

Execute in this order (est. total win: 25-40 min off a monthly night):
1. Versa: derive by_pos from the bulk season census (fetch_season_fielding, ~7 cached
   calls/season) with per-player fetch as fallback; or at minimum ThreadPoolExecutor
   (16-24) mirroring run_monthly.py:2630. [~6-7 min, LOW]
2. Statcast 3d-ter incremental: reuse the d5d _statcast_logs_newer_than_metric filter
   (run_monthly.py:483-492) after pass 1; add a metric-schema version stamp so shape
   changes force full rebuild (the silent-staleness class of the 2026-08-03 trim bug);
   EEPHUS_FULL=1 escape hatch. [~8-15 min + OOM relief, MEDIUM]
3. Lab cadence: LAB_EVAL_FRESH_DAYS 30 -> 45 (run_monthly.py:332) so the gate stops
   expiring exactly on the ~30-31-day monthly cadence. Owner-policy change: record it
   in the execution doc. [~10-15 min, LOW]
4. Gate 3d sabermetrics + arsenal fan-outs on has-MLB-career-row (the war_cohort test
   at 2854-2863; endpoints are MLB-only, ~80% of ~6.5K calls return None). Fall back to
   fetching when the career_cache row is absent entirely. [~1-2 min + API load, LOW]
5. Single-parse timeseries.json (70MB, parsed ~15x/night): tiny loader module memoized
   on (path, mtime), orjson, documented READ-ONLY; route efv_dataset.build_live_matrix,
   efv_score.run_backgrade/score_history, proj_export x2, mlb_player_export, headshots,
   fa_export, org_tendencies, identity_audit, fantasy_export, build_site, and the
   monthly tail. CALLERS THAT MUTATE MUST COPY (rebuild_only appends debut rows).
   [15-60s CPU + ~1GB transient per parse on the OOM box, LOW]
6. Transactions TTL: 3-7d freshness for status=="debuted" players, or a league-wide
   /transactions?startDate delta scan to pick per-player refetches. [~1-2 min, MEDIUM]
7. Dedupe _derive_all_level_changes (3a + 3e + chained d9): fetch tx before 3a, derive
   once. In-code staleness comment at 2546-2568 documents the deferral; resolve it.
8. Delete or repair the dead freshness-gate code under the TTL=0 constants (restore a
   1-day TTL so a crash-restart rerun can skip; currently a restart repays everything).
9. Cache pruning: .cache is 55GB; only game_feeds has a pruner. Add mtime/season
   pruning or gzip for win_prob (19G), statcast_metrics (15G), zone_metrics (5G);
   closed-season entries are immutable.
10. Micro: proj_export single timeseries parse (614/928); skip monthly-tail headshots
    backfill when chaining (runs again in d9c); d5e reuse of the warmed feed set.
Also: refresh logs/pipeline_latest.log with a current instrumented run FIRST (the
May-2026 log is pre-labs) so before/after is honest.

## A10. FA / MLB Stats / Projections visual polish (from screenshot survey)

P1 (shared phone collapse, with A3): the grid fix; tape chips crushed to "deal…"/
"rati…" -> `.mlb-chip { flex:none; min-width:max-content }` inside the <=640 block
(site.css:3007-3017), tape scrolls at natural width (affordance already exists).
P2: /mlbstats/ phone shows ~2.5 screens of prose before data -> wrap explainers in the
existing .mlbstats-collapse pattern; tighten .mlb-sortbar margins (3104); allow 2-line
clamp on section-sub instead of mid-sentence ellipsis; right-align numeric header
cells over right-aligned card cells (the .mlbstats-table th pattern).
P3: add the missing CSS for classes projections.js references that have NO rules
(.proj-cmp-name/-head/-heads/-table, .proj-acct-*, .proj-warmap-legend, .proj-legend-*,
.proj-more-wrap, .proj-empty; the compare heads and scatter legend currently render as
raw inline flow); /mlbstats/ 23-24 nowrap columns ~1500-1900px wide at every desktop
width -> core-columns default + "all columns" toggle; title attrs carrying full names
wherever ellipsis remains (rail :1635, td.mlbstats-name :1878).
Theme rules: sharp corners, org-stripe tokens (test_no_hardcoded_colors), keep the
Topps-Chrome refractor identity.

---

# PART B: MODEL PROGRAM (all gated; ledger-aware)

## B1. Build war_source.py (the D0 pluggable WAR facade) FIRST

The spec ALREADY EXISTS at docs/master-plan-2026-08-03-eight-asks.md:267-274 and was
never built (file absent). Wrap: per-season WAR by mlbam, stint frame, run-value
decomposition, name index; provider id ('bwar' | 'ewar_v2' | 'ewar_merged'). Migrate
the 10 direct bwar call sites listed at :255-265 (stats.py:3453, fa_projection.py:87,
fa_ident.py:22, fa_pipeline.py:62, mlb_player_export.py:245, pal_export.py:206,
proj_backtest.py:70, proj_export.py:85, tools/build_def_history.py:51,
bullpen_export.py:490). Pin with a byte-diff test on career_war payloads (provider
'bwar' must be a no-op refactor). ewar.ewar_for (ewar.py:1127) is the already-written
provider call shape. This is what "prep the site for Will's eWAR" concretely means:
after B1, a re-anchor is a data-layer swap plus the Stage-2 runbook.
KNOWN TRAP: bWAR is pinned beyond the 10 call sites (empirical FV curve
value_framework.py:2887, FV_EXPECTED_WAR/survivor/FV_WAR_ANCHORS, draft slot curve,
war_rate_plus frozen vintages, copy gates literally asserting "bWAR"). A partial
re-anchor desyncs fingerprinted artifacts: it is the one coordinated Stage-2 runbook
(master-plan-2026-08-03 D3) or nothing. Stage 2 remains an OWNER CHECKPOINT.

## B2. Will's eWAR merge + SDR prep

FACTS: Will's eWAR exists only as parquet handoffs on his machine
(milb-projections/manifests/BENCHMARK_MANIFEST.yaml: mlb_pitcher_ewar_champion 1.1.0 +
MiLB AAA/AA/A+ variants). NO hitter eWAR exists anywhere, so "merged eWAR" =
Will's pitching + SDR-bearing fielding on the ewar.py bWAR frame (an ewar.py v3,
not an import). The private export bundle is a queued owner action; the merge lane is
BLOCKED on it and the plan prepares everything up to the data boundary:
1. B1 facade (above).
2. Ingest adapter stub: a war_source provider 'ewar_merged' that reads the handoff
   parquet schema from the manifest, with a loud NotImplemented/data-absent state.
3. SDR intake spec (the recon's open questions become the intake form; put this in the
   webmaster/Will handoff artifact): what SDR measures (range-only vs
   range+arm+framing+blocking), outcome- vs grade-based, MiLB coverage by level/year,
   keying (mlbam vs player_key; identity resolution is the known binding constraint;
   prefer mlbam like savant_oaa with consensus-alias fallback).
4. SDR validation harness, pre-registered BEFORE data arrives (registry row + eval
   artifact + freshness map): validate vs realized MLB defensive value against BOTH
   baselines: tool_field/fFld (0.28 Spearman) and prospect_def_value (0.68).
5. Integration points, each with its own gate:
   (i) eWAR fielding: SDR is the intended trigger of the w-grid RE-OPEN CLAUSE at
       ewar.py:806-812 (Savant FRP lost because it is range-only). Re-run the full
       w-grid with SDR replacing the Statcast read; both forward legs must stop being
       monotone-decreasing. The standing ban is "an OAA/rfield fielding blend at any
       w"; the pre-registration must state what is NEW (SDR is not OAA).
   (ii) MLB Projections/FA: SDR as an incremental feature OVER the shipped
        pos_adj_prior in proj_ml (DEF_FEATURE_CANDIDATES seam; forward-chained
        dev/holdout like tools/def_feature_backtest.py). It must beat the incumbent
        that already made def_value redundant. FA pricing inherits via
        fa_market.contract_war_path automatically.
   (iii) eFV driver (alone AND with fielding/arm tools, per the owner ask): run via
        tools/efv_lab_runner.py variants with MDE floors hit 0.017 / pit 0.016,
        zero-info control, >=3/4 fold robustness. The pre-registration MUST name the
        three standing defense-into-eFV refutations (memory:
        wills-models-for-xfv-audit; registry rows) and state the new structure (MiLB
        innings/outcome basis, not grade re-expression). EXPECTED outcome is null
        ("the binding constraint is the TARGET" - prospect_def_value.py:37-42);
        commit the ledger entry either way.
   (iv) PAL: Position Fit panel cells with per-position validity gates (Rng+
        precedent: ship only cells whose CI clears).
   (v) MLB Stats / prospx: display column/chip first; never a rank/sort input without
       its own gate.
6. R3b trap, quote it in any FA gate design (fa_backtest.py:376-388): a more
   persistent label raises the naive baseline's floor before the model's ceiling;
   margin-over-carry designs must anticipate losing for that reason alone.

## B3. eWAR into eFV backtesting

The harness exists: labels enter at efv_dataset.py (career_war table, _label_6yr:715,
KM censoring); experiments run through tools/efv_lab_runner.py on the shipped
protocol. R3a (eWAR label swap margin) ran 2026-08-04: NO-SHIP, "unsupported, not
closed" (margins -0.0011 hit / -0.0115 pit vs floors 0.017/0.016). R3c (the flip) is
an owner checkpoint marked "do NOT run, R3a failed". WHAT THIS LANE DOES NOW: wire the
label-swap harness so any NEW WAR series (Will's merge, SDR-bearing v3) can be
re-tested in one command (a --war-source flag on efv_lab_runner reading through B1's
facade), and document that per ewar.py:58-61 the only legitimate near-term trigger for
a re-run is a genuinely different label (SDR-bearing fielding), since cohort power
only grows as debut years mature. Do NOT re-run R3a on unchanged labels.

## B4. eFV stolen-base driver experiment (CLEAN LANE; no ban exists)

Verified: no SB-adjacent ban anywhere in the ledgers. Facts: MiLB SB is captured as a
COUNT (milb_history.py:173); caughtStealing is NOT captured at MiLB level, so
"SB rate" means attempts/volume per PA, not success rate, unless CS is added to the
milb_history hitting ingest (cache re-walk cost). level_norms.py has no sb norms.
Speed-grade ground truth: SB/600PA by grade corr 0.57 (TOOL_GRADE_TABLES.md 2.6).
SPEC:
1. Feature: SB per 600 PA, level-relative (extend level_norms.py with sb norms; add
   the efv_dataset production block). Optionally add CS ingest first so a success-rate
   variant can also run; state which spec is used.
2. Variants through efv_lab_runner: sb_rate alone; sb_rate + tool_speed (ADD, never
   replace: replacing tool_speed previously cost -0.014, it is protective); blended
   speed composite (w*tool_speed + (1-w)*sb_rate_z, small w grid).
3. Gate: the standard protocol (MDE floors, zero-info control, fold robustness,
   forward-chained OOS). Ship only on a clean win BOTH pooled OOS MAE and Spearman;
   ledger entry either way.

## B5. eFV "athleticism blend" experiment (SCOPED by known refutations)

Constraints that shape the spec: frame/athl grades are FG-ONLY (-2..+2 -> 30-70,
consensus.py:823-847) and UNTRAINABLE on the debuted cohort (0/843 coverage,
data/xfv_physical_eval.json); BMI-for-arms "regress decisively" (banned); isolated
tool_field regresses; tool_hit and tool_speed are ALREADY served eFV features. The
honest blend to test is therefore speed+field+throw composites on the debuted-coverage
tools, NOT frame/athl:
1. Variants: athl_blend = mean-z of {tool_speed, tool_field, tool_throw} (and the
   2-tool subsets), as ADDITIONS alongside served features; never replacements.
2. Same gate as B4. Pre-registration cites the three defense refutations and the
   physical-tools null so the ledger stays coherent. EXPECTED: null on field/throw
   loads (target is offense-dominated); the informative variant is speed+field.
3. If null: record and route the signal to its sanctioned lanes (display chips;
   MLB-side defense-IS-WAR surfaces) per prospect_def_value.py:37-42.

## B6. Arkmetric improvement sweep (the "improve all models" ask, made concrete)

- consensusFV: keep equal weights (the 07-25 revert was measured; do not re-litigate
  without a new season of resolutions). Concrete improvements: extend
  PLAYER_KEY_ALIASES hygiene (the jack_natili pattern) with a periodic alias-audit
  tool; prep BA/BP board ingest slots in consensus.py source registry (roadmap item;
  ingest runbook clone of the FG four-CSV drop with PIN-THE-DATE rule).
- MLB FA projections: fa_market comps cliff smoothing shipped 07-29; next gated item
  is the A2 fix propagating to FA rental fits (same f*V(w) convention appears at
  bayes_trade_value band adjuster). Run fa_backtest after A2 and record deltas.
- MLB Projections (proj_ml): no free wins found in recon; the SDR seam (B2.ii) is the
  next real lever. Do not churn.
- MLB Stats: REM+/SEM+/HEM+/RIV+ are FIP/WPA-family and healthy; the WAR-rate columns
  re-anchor automatically post-B1 if a provider swap ever ships. A10 handles display.
- eWAR v2: leave the model as-is until Will's data lands (B2); the w-grid that dropped
  fielding SURVIVES and stands.
- eFV: B3/B4/B5 are the eFV program. Do not touch blend lambdas (0.70/0.57 pinned).
- Positional ladder: A4 (display convention). Model unchanged.

---

# PART C: THE DIAMOND SECTION

Design tenets (owner-approved): ships fully public with "Diamond preview" labeling
(MODULE_STAGE chips), gate flag wired but OFF; Supabase is the one backend; everything
reuses the shared scaffolding (page() chrome, .fa-app/.mlbstats-app css, sectionnav
tablist, data/*.json sidecar pattern, eephus-hub/eephus-gfx, _asset_ver stamping).
The site remains static: genuinely Diamond-only data CANNOT live in /data/*.json when
gating eventually turns on; it must come from Supabase RLS tables or an edge function.
Build with that seam in mind (exports write both a public preview slice and a
full-detail payload, even while both are public).

## C1. Nav + scaffold (one commit, test-gated)

NAV_ITEMS (build_site.py:158-174): add group "Diamond" with children dynasty, redraft,
dfs, betting ("Sports Betting"), cards ("Card Market"), diamond ("Diamond Pass");
REMOVE the fantasy leaf from MLB Modules. Same commit: hand-edit the three static nav
copies; MODULE_STAGE rows; build_X() builders cloned from build_fantasy's shape;
main() _write registry + build_sitemap rows; six new dirs in deploy/publish_paths.txt
(the 2026-07-14 404 incident); /fantasy/ becomes a build_teams_redirect-style redirect
to /redraft/ and STAYS in publish_paths. Regenerate SITE_MAP/DATA_SOURCES via
tools/gen_audit_docs.py (test_generated_docs_in_sync).

## C2. Fantasy split: Dynasty / Redraft / DFS

Keep ONE fantasy_export.py producing data/fantasy.json (the corpus is the expensive,
OOM-budgeted part; run_monthly 6b6/9d wiring unchanged). Split the CLIENT:
- /dynasty/ (dynasty.js): sections.dynasty + Call-up Watch; dynasty-league framing
  (contend/rebuild timelines, eFV+ETA+surplus blend already in _dynasty_prospects).
  Add: keeper-value calculator (years-of-control vs redraft cost, pure client JS).
- /redraft/ (redraft.js): streamers, two-start, ROS SP/RP/hitters, buy/sell, closer
  grid, with the 4-format scoring selector (already client-side re-scored).
- /dfs/ (dfs.js + dfs_export.py): NET-NEW daily slate payload from
  fantasy_schedule.py's StatsAPI probables + per-player counting-stat vectors
  re-priced per-game with matchup context (REM+/SEM+/HEM+/Offense+ already exported).
  Wire as a daily best-effort _step like 9d. DFS LINEUP OPTIMIZER (owner-approved
  extra): client-side salary-cap solver (greedy + swap improvement is fine at MLB
  slate sizes) over our per-game projections; salaries entered/pasted by the user or
  imported from a CSV the user exports from their DFS site (we do NOT scrape DK/FD
  salary feeds); clearly label projections vs salary provenance.
Preserve the single eFV basis via _board_grade everywhere. Do NOT merge
feat/fantasy-oom-headshots (fully superseded by main; verified).

## C3. Sports Betting module (/betting/)

Sections per the owner spec: Pick of the Day; Team bets (ML/runline/totals); Player
props; Parlays; Calculators; My Bets (tracker).
- ODDS INGEST (betting_ingest.py): The Odds API free tier, ONE snapshot per day of
  MLB h2h/spreads/totals (1 region), scheduled in the daily tail; a credit costs
  markets x regions so a daily 3-market/1-region pull fits 500/mo with headroom.
  Cache raw responses immutably (.cache/odds/). Player props need the per-event
  endpoint and would burn the free tier in ~a day: ship props as MODEL FAIR LINES
  (no book comparison) until/unless the $30-59 tier is approved. Register in
  DATA_SOURCES + SOURCE_AUDIT.
- MODEL (betting_model.py -> data/betting.json): game win probabilities from team
  strength built on OUR surfaces (team Offense+/Bullpen+/rotation REM+/SEM+, probables
  from fantasy_schedule, park factors, home-field constant), calibrated on 2024-2026
  game results (backtest REQUIRED before any pick ships; registry row + eval
  artifact). Edge = our probability vs de-vigged book implied probability. Picks:
  flat 1-unit staking ONLY on the public record; Kelly shown as an informational
  column, never the staked size. PICK OF THE DAY = highest-EV qualifying edge with a
  minimum-edge threshold measured in backtest (do not invent the threshold; fit it).
- HONESTY RAILS (non-negotiable, from research): every pick carries timestamp, book,
  odds-at-post, stake=1u; the published record is APPEND-ONLY (an immutable
  data/betting_record.json the export can only append to; a test asserts prior rows
  never mutate); grade every pick vs the closing line and publish beat-close rate +
  avg CLV + net units + ROI alongside W-L. CLV needs a closing-odds capture: same
  Odds API snapshot taken at first pitch (schedule-aware daily job), Pinnacle-via-
  aggregator only if a paid tier ever lands. Disclaimer block on every page: 21+,
  informational only, not available in all states, 1-800-GAMBLER. NO affiliate links
  (that is where state licensing attaches; revisit only with legal review).
- PARLAYS: parlay builder = client-side calculator over the day's model probabilities
  (product of de-correlated legs, with a same-game correlation warning that blocks
  naive SGP math); "model parlay of the day" only if the backtest supports positive
  EV after correlation haircut, else ship the builder without a featured parlay.
- CALCULATORS (pure client JS, betting.js): american/decimal/implied conversion,
  vig/hold, parlay, expected value, Kelly fraction.
- MY BETS TRACKER: supabase/migrations/0005_diamond.sql adds `bets` cloned from
  watchlist's owner-only RLS shape (user_id FK profiles cascade; sport, market,
  selection, odds int, stake numeric, placed_at, settled_at, result enum
  open/won/lost/void, payload jsonb). EephusAccount.addBet/listBets/updateBet in
  eephus-account.js; localStorage fallback + merge-on-sign-in copying the watchlist
  adapter (FRONTEND_INTEGRATION.md Part 3). Works logged-out; syncs when signed in.

## C4. Baseball Card Market module (/cards/)

DATA (owner chose scraping; build it survivable and low-exposure):
- card_prices_ingest.py: throttled scraper of publicly visible sold listings for a
  CURATED watchlist only (top ~200 board prospects + notable MLB), 1 req/several
  seconds, honest UA, daily for a hot list / weekly long tail, raw comps stored
  immutably in the DB (90-day windows vanish; store forever), NEVER republished raw.
  The module publishes ONLY derived values: a per-card/per-player eephus Card Index
  (trimmed-median comp, grade-mix adjusted), trend, and the model verdict. This is the
  materially safer posture under the owner's choice; the clean licensed swap
  (SportsCardsPro CSV product, PSA paid API) is documented in the module README and
  the ingest is interface-shaped so a CSV drop can replace the scraper without
  touching the model (fg-board-runbook-style manual drop as the built-in fallback).
- MODEL (card_market_export.py -> data/card_market.json): identity via
  bulk_resolve_ids (NOT resolve_mlbam_id; the negative-id cache lesson); join through
  efv_board_scale.board_value; the buy signal is a surplus-style gap: eFV-implied
  future-value tier vs current market price, cloned structurally from
  _dynasty_prospects' blend. v1 SHIPS LABELED AS A SCREEN, not a validated signal
  (PAL RP->SP precedent), because no price-history backtest exists yet; the module
  accumulates its own price history until a real backtest is possible (registry row
  + eval artifact from day one, status "screen").
- UI: card boards (buy screen, biggest movers, watchlist), player pages linkthrough,
  GFX share card. On-theme: sharp corners, refractor identity (this module is
  literally about shiny cardboard; lean into the Topps-Chrome refractor motif).

## C5. Diamond Pass page + entitlements (ships dormant)

- build_diamond(): marketing page. $15/mo price card; what members get (the six
  modules' premium slices + the four extras); model-validation section that reads
  LIVE artifacts (betting record + CLV once they exist, eFV eval wins, projection
  accountability) rather than hardcoded claims; FAQ; sign-in-aware CTA. "Founding
  preview: everything free while we build" banner while gating is off. The
  subsidize-the-analysis framing stays OFF the page (owner instruction); public copy
  is "Diamond funds the free site".
- Entitlements: 0005_diamond.sql adds badges row ('diamond', gem icon) + a
  diamond_until timestamptz on profiles ADDED TO the guard_profile_privileged_cols
  trigger (service-role only, the role/karma pattern). EephusAccount.isDiamond().
  Badge displays via the existing getUserBadges/userFlair flow (zero new UI plumbing).
  Wire forum_notify.py-style box job as the future grant path; STRIPE IS OUT OF SCOPE
  this pass (needs entity + legal review, especially adjacent to betting content).
- Gate flag: a single site-wide DIAMOND_GATING=off constant read by the new modules'
  JS; when later flipped, module JS swaps full payloads for preview slices for
  non-Diamond users. Cosmetic until the Supabase-served data path exists; the honest
  paywall design (RLS/edge-function data) is documented in the webmaster artifact.

## C6. Diamond extras (all four approved)

- Data exports + JSON API: a /diamond/data/ page listing documented CSV/JSON
  downloads (board, eFV, projections, FA, betting record). The artifacts already
  exist as /data/*.json; work = a documented index page + stable-schema note + CSV
  mirrors emitted by build_site. Public during preview.
- eFV movement alerts: extend forum_notify.py (it already computes FV-change
  notifications and was never wired) into the monthly/daily tail: watchlist-based
  in-site notifications first (the notifications table exists); email is out of scope
  until a send provider exists (document in webmaster artifact).
- DFS lineup optimizer: C2.
- Diamond weekly newsletter: NOT built as infrastructure this pass; the roadmap
  artifact carries it as an editorial commitment (members-only digest: model movers,
  betting record, card calls). Add a newsletter section to the writer schedule.

---

# PART D: ARTIFACTS (12)

Shared style rules for ALL artifacts: human voice, de-LLM'd hard. No em dashes. No
"delve/leverage/robust/comprehensive/journey". Short declarative sentences. Numbers
from artifacts, not memory. First person where the owner speaks ("I built", not "we
delivered"). No bullet-splatter where prose reads better. Each artifact gets a stable
emoji favicon and a one-sentence description. All are link-shareable EXCEPT D11
(private). Publish via the Artifact tool; D12 links them all.

D1. BETA-DIFF CATALOG (webmaster incorporation doc). Structure per recon: header state
box (main 5f03086 08-04 suite 3,051/0; origin/beta 03c1428 = deliberate rollback to
the 07-22 fea4cc9 tree, revert restores ab56f7b sync; LOCAL beta ref is STALE at
14e0e32, flag it); delta-at-a-glance (72 commits/295 files vs origin/beta's embedded
sync point ab56f7b; 194/1,340 vs the stale local ref; state that branches are
DISJOINT, raw rev-list counts mislead); six area sections with representative commits
(Models ~85: eWAR v2, eFV refit, surplus EV v6, FA engine, odds recal, gate lanes,
with no-ship loss ledgers sub-listed so labs are not mistaken for features; Site/UI
~45; Data/DB ~45; Deploy ~10; Tests ~25; Docs ~40); the DO-NOT-CLOBBER table visually
dominant (statcast_metrics.py baron fixes; conftest serve_site HTTP/1.1 harness;
consensus.PLAYER_KEY_ALIASES; all generated HTML; box single-writer; sslBackend
schannel; clemens_2026/fa_implied-disabled governs served prices); sync procedure
(next sync is main->beta ONLY, from main tip; verify statcast_metrics + conftest
byte-match after; run identity guard + golden fingerprint). Ask-the-webmaster box:
does he hold unpushed beta work newer than 03c1428?

D2. eFV FOR FRONT OFFICES. Audience: MLB analysts/execs. Simple terms, no code. What
eFV is (a prospect-value model trained on 2011-2024 debut cohorts, labels = first-6yr
bWAR, forward-chained eval), what it beats and by how much (pull from xfv_eval /
model registry; the honest framing: beats the public consensus out-of-sample on both
MAE and rank correlation in the scored years), what it does NOT claim (no-ship
ledger as a FEATURE of the shop's discipline: measured, refused, recorded), the
two-grade system (eFV + outcome-implied FV), calibration receipts (reliability
artifact), and the input floor (public data only; what a team's private data would
add). One page of method, one of receipts, one of "how we'd work with a club".

D3. THE SITE FOR SABR. Audience: sabermetric researchers; the conference-talk
foundation. The whole site as a research program: data pipeline (StatsAPI + public
sources, identity resolution as the hard problem), the model registry discipline
(every model has a registry row + eval artifact + freshness map; loss ledgers are
permanent), the headline models (eFV, surplus-as-EV with isotonic calibration,
FA market model, positional ladder with the exposure-vs-equal-weight identification
story, Arkmetrics family), what was refuted and why that is the point (K-prior,
surrogate labels, def-into-eFV, gmLI crediting), and open problems (MiLB fielding
data, eWAR label persistence trap). Tone: methods talk, not a product pitch.

D4. MONETIZATION PLAN. Audience: owner + partners. Content: the model (free site +
Diamond $15/mo, everything else free forever); competitor price table (FanGraphs
$15/80yr; BP $19.95/74.95yr; BA $19.99/119.99yr; Athletic $7.99 list heavily promo'd;
PitcherList $6-10/60yr, Pro $20/240; Stathead ~$9/80yr; Rotowire ~$19.99/143.88yr;
Prospects Live $5 legacy/$20 new) -> positioning: $15 sits at FanGraphs parity, below
BA/BP, justified only once the betting record + tools are live; launch path =
founding rate $9.99 for the first cohort (grandfathered 12 months), list $15 at gate-
on, revisit $19.99 only after a season of receipts (the Silicon Valley model, made
concrete). Revenue scenarios as ranges until Cloudflare numbers arrive (state the
ask): conversion assumptions 0.5%/1.5%/3% of monthly uniques with churn 8%/5%/3%,
each scenario shows subs, MRR, annual. Cost line: hosting, The Odds API tier, PSA API
if adopted, Supabase, Stripe fees. REVENUE SPLIT (the owner asked "could I ask for
more than 70%?"): recommendation = costs off the top, then 70% owner / 30% split
webmaster+ops. 70% is defensible and probably the ceiling that keeps the webmaster
motivated; going 75-80% is arguable on pure contribution but trades goodwill you
still need (he runs the box). Better lever than a bigger split: owner-retained
ownership of the models/IP and the Diamond price lever. Twitter plan for @eephus_io:
Mon updated Top 100 GFX thread; Tue betting-record receipt card (auto-GFX); Wed
prospect spotlight (movement engine); Thu Arkmetric explainer; Fri FA/trade-machine
scenario; Sat card-market call; Sun week-in-review + article plugs; every post uses
generateGFX cards, every thread ends with a site link; post windows 11am/7pm ET;
event-driven overrides (deadline week, draft, lottery, CBA news).

D5. ROADMAP (Aug 2026 -> Dec 2027). Anchors from research: 2026 season ends Sep 27;
playoffs Sep 29-Oct 31; CBA EXPIRES DEC 1 2026 (lockout likely; every date after is
contingent; plan a lockout content strategy: rankings/analysis/history/cards do not
freeze, transactions do); Winter Meetings + draft lottery ~Dec 7-11 Orlando; intl
signing Jan 15 2027; arb exchange ~Jan 8; 2027 Opening Day Mar 24-25; All-Star +
draft week at Wrigley Jul 11-15 2027; deadline ~Jul 28-Aug 2; 2027 season ends Sep
26. Conferences: Saberseminar Aug 29-30 2026 Chicago (NEAR-TERM: decide attendance
now); CASSIS Sep 12 2026 Vancouver; PitchCon likely late Jan 2027 (free/virtual, low-
cost speaking slot); SSAC Feb 25-26 2027 Boston (paper deadlines Sept-Nov 2026);
SABR Analytics Mar 12-14 2027 Phoenix (reg opens fall; THE presentation target;
Diamond Dollars $1,750/team runs there, HS/undergrad/grad eligible; Yoseloff
deadline ~mid-Dec 2026, up to $1,250); SABR 55 summer 2027 TBA. Milestones: Q3-2026
this plan's Parts A-C ship + beta handoff executes; Q4-2026 out-of-beta launch +
2026 EOY calibration report (the receipts artifact) + BA/BP INGEST (runbook cloned
from FG four-CSV drop; consensus source slots prepped in B6) + Yoseloff application;
Q1-2027 SABR Analytics presentation + betting record's first full quarter + gate-on
decision for Diamond; Q2-2027 draft-board cycle + card market first backtest;
Q3-2027 deadline coverage + Diamond price review. Writer schedule (3-5 writers):
4-6 articles/week: Mon owner flagship; Tue prospect beat; Wed analytics feature;
Thu fantasy/Diamond beat; Fri data feature; Sat/Sun optional roundup. Owner article
series with outlines IN THE ARTIFACT: 1 "How I built eephus.io (and new
sabermetrics)" (origin, the pipeline, the registry discipline, three findings, what
is next); 2 "What 3,800 prospects taught a model about FV"; 3 "Surplus value is an
expected value"; 4 "The no-ship ledger: what we refused to ship"; 5 "Building a $/WAR
series that survives contact with 2026"; 6 "Why our positional ladder does not sum
to zero (and why yours does not either)". Each with a 5-beat outline.

D6. BRANDING GUIDE. Inventory branding/ dir first; document: wordmark + logo usage
(the existing logo set; transparent variants; favicon), the phosphor-starfield dark
identity + Topps-Chrome refractor motif (KEEP per owner rule; deepen only), color
tokens from site.css (org stripes, surface tokens; no hardcoded colors rule),
typography stack, GFX card anatomy (16:9 rows, 2x export, footer brand line), voice
(plain, receipt-driven, no hype), do/do-not examples, and asset export recipes
(sizes for Twitter cards/OG). If gif/animated assets do not exist yet, spec them
(starfield loop, refractor shimmer on the wordmark) rather than pretending.

D7. WEBMASTER SETUP RUNBOOK. Merges D1's do-not-clobber rules with the full local-
parity recipe: clone + LFS-less setup, DB seed REQUIREMENT (deploy memory: box needs
the seed; .cache 47-55GB expectations), python env, run_monthly/run_daily/chained
cadence + EEPHUS_MAX_WORKERS/EEPHUS_SKIP_INPROC_BUILD, deploy/nightly-build.sh, both
--apply passes on the deploy box, publish_paths.txt as the serving contract,
Supabase: apply migrations 0001-0005 in order, set eephus-config.js from the example,
service-role key handling, forums go-live checklist, and the "how to verify you did
not clobber" checks (statcast_metrics/conftest byte-match, identity guard, golden
fingerprint, suite green). Written so a competent person who did not build the system
can execute it top to bottom.

D8. ANALYSTS/WRITERS GUIDE. How to navigate the site (module map in one page);
the ten Arkmetrics they will actually cite with one-line meanings + where each lives
in the glossary; article guidelines (professional, analytical, claims sourced to site
artifacts or public data, numbers double-checked, no em dashes, grades ceiling); the
structure: NO PAY YET, platform-for-exposure, bylines + author pages, first right to
expand pieces when revenue starts; the posting schedule (from D5) with beats; the
pitch/edit workflow (pitch -> outline -> draft -> owner edit -> publish via
content/articles/*.md frontmatter, one page on the md format); and an ARTICLE IDEA
GENERATOR: not software, a method section: 12 evergreen idea patterns (movement
receipts, model-vs-market gaps, ladder/positional stories, org tendencies, draft
class re-checks, calibration reviews...) each with a worked example headline + 5-beat
outline, and a note that ideas/outlines can be generated on request but ALL published
prose is human-written (owner policy).

D9. GLOSSARY/METHODOLOGY artifacts are SITE WORK (A7), not standalone artifacts; D12
links to the live glossary instead.

D10. MASTER ARTIFACT INDEX. One page linking D1-D8 + D11(marked private) + the live
site surfaces (glossary, Models & Proofs, Library). One-line description + intended
audience + last-updated per row. States the methodology version (this plan's date)
and that every artifact above was regenerated against it.

D11. OWNER PERSONAL PLAN (PRIVATE; never share the link; contains strategy the site
does not say publicly). Contents: the actual goal stack (passive revenue via Diamond
subsidizing the free analysis site; delegation map: webmaster = infra, writers =
content, owner = models + editorial direction + the only price-setter); earnings
view (the D4 scenarios with the owner's 70% cut applied, plus the costs-off-the-top
recommendation and the "could I ask for more" answer in full); portfolio strategy
(site + eFV artifact + SABR talk as the resume spine; the no-ship ledger as the
differentiator story in interviews); the FO pipeline: current contacts (Cardinals,
Orioles, Braves) get the D2 artifact + a tailored one-pager each; target list
(Yankees, Mets preferred; Red Sox, Rays, Dodgers next) approached AFTER a public
receipt exists (SABR talk or EOY calibration report), opportunistic timeline per the
locked decision; conference/scholarship calendar with deadlines (Yoseloff ~mid-Dec
2026; SSAC papers Sept-Nov; SABR Analytics reg fall 2026); quarterly review cadence
for this plan itself.

D12 = D10 (the index IS the master artifact). Keep numbering; no separate doc.

---

# PART E: EXECUTION ORDER, DEPENDENCIES, VERIFICATION

Wave 1 (independent quick repairs): A1, A5, A4, A2.1 (mechanical leg), A3 (CSS +
export line), A8 batch 0. Each its own commit; suite green between.
Wave 2: A6 (GFX photos + test rewrite), A7 (glossary trio), A10 polish, A8 batches
1-3, A9 items 1-10 (its own commit series; instrument first).
Wave 3 (models): B1 facade (byte-diff pinned no-op), then B3 harness wiring, B4, B5
(experiments; ledger entries either way), A2.2 measured leg, B2 prep stubs + SDR
intake spec.
Wave 4 (Diamond): C1 scaffold -> C2 split -> C3 calculators+ingest+model (model gated
on its backtest; calculators/tracker ship first) -> C4 (screen-labeled) -> C5/C6.
Wave 5: Part D artifacts, D1 and D7 first (the webmaster is waiting), then D2-D8,
D11, D10 last (it indexes the rest).

Regen/deploy notes: A2 + A1 both end in export+rebuild; batch them into one regen
pass per wave, remembering TWO passes when a basis moves (A2). The deploy box still
owes regens from 2026-08-03 (positional_fit among them); fold those into the first
deploy after Wave 1.

Verification checklist per wave: full pytest suite green; tools/strip_emdashes.py
--check + tools/copy_lint.py on any prose; test_generated_docs_in_sync after nav/doc
regen; view-source hash check on deployed pages after any deploy; grep for dangling
refs after deletions; for every model experiment a ledger entry exists whether it
shipped or not.

FINAL REPORT must include: the A2 premise correction (RoS was already prorated; the
real defects were talent basis + convexity), the A4 adjudication story (display
convention chosen, model untouched), the deleted-code inventory with counts, the
runtime before/after table, every experiment verdict with its artifact path, the
Diamond preview URLs, all artifact links (D11 private), and the open owner asks from
section 1.

---

# APPENDIX: RESEARCH SNAPSHOTS (2026-08-04; cite, do not re-research)

Competitor pricing: FanGraphs $15/mo, $80/yr, $200/3yr (since 2025-08). BP $19.95/mo,
$74.95/yr Premium, $99.95/yr Super-Premium (since 2026-01-01). BA ~$19.99/mo,
$119.99/yr. The Athletic $7.99/mo list, heavy promos, NYT bundle. PitcherList PL+
$6-10/mo or $60/yr; PL Pro $20/mo or $240/yr. Stathead ~$9/mo per sport (~$80/yr;
verify at checkout). Rotowire $19.99/mo, ~$143.88/yr. Prospects Live Patreon: legacy
$5/mo grandfathered, new $20/mo tier (2026-01-02 restructure). Just Baseball: free.

Odds data: The Odds API free 500 credits/mo (credit = markets x regions; ~80-170
practical calls); paid $30/20K, $59/100K. MLB props exist but per-event endpoint
burns free tier in ~a day; historical props paid-only. OddsJam/OpticOdds enterprise
(~$500-5k/mo, sales-gated). SportsGameOdds $99-499 + free delayed tier, carries
Pinnacle (cheapest CLV close source). Pinnacle's public API closed Jul 2025. Legal:
picks/analysis = editorial content, no license needed if no wagers accepted and no
affiliate links; ~8 states license AFFILIATES (AZ CO IN LA MI NJ PA WV); standard
disclaimer 21+/informational/1-800-GAMBLER. Record practice: flat 1u, immutable
timestamped log, CLV vs close as the headline honesty metric (the Action Network
deletable-bets criticism is the cautionary tale).

Card data: eBay Marketplace Insights API closed to new users (Limited Release; 90-day
window). Card Ladder enterprise-only API, daily refresh. 130point free manual tool,
no API, ToS-fragile. PSA APR free on web, public API throttled ~1 call/day free,
paid via collectors-apis@collectors.com. Market Movers consumer app only.
SportsCardsPro sells a documented CSV/price-guide product aimed at small sites (the
clean swap). Post-hiQ: scraping public data is not CFAA but IS breach-of-contract
exposure under eBay ToS; publishing derived indices from stored comps is materially
safer than republishing raw comps. Cadence: daily hot list, weekly long tail, full
sweep well inside 90 days.

Conferences/dates: in D5 above (single source; do not duplicate elsewhere).
