# Final site audit, 2026-10

Task SITE_FINAL_AUDIT (owner ask 2026-10-19). Built locally with `python build_site.py`, served on port 9143 and walked in headless Chromium. Worktree wt/s202, branch wt-SITE_FINAL_AUDIT, base 8a5a43da. Nothing pushed.

## 1. Coverage

- 68 sitemap routes and sub-views, plus 21 sampled entities (stars, prospects, relievers, catchers, IFA, retired) on 37 entity routes through /player/, /projections/#player= and /fa/#player=.
- Each at 1280 light, 1280 dark and 375 light: 315 page loads, a screenshot per load (375 px full page to 5,000 px), kept in the lane output directory, not the repository.
- Per load: console errors, page errors, responses of 400 or more, NaN / undefined / null / Infinity / [object Object] in visible text, horizontal overflow at 375 px with the offending element chain, empty tables, stuck loading or failed states, dated stamps, and text contrast in dark mode (WCAG 4.5:1, 3:1 for large text).
- At 1280 light: every visible tab clicked and re-probed; header sorts on 15 numeric columns clicked twice and read back by column x-position.
- Copy: `tools/copy_lint.py --served` (rules L1 to L12) over every built page, script, producer, glossary and registry field; a rendered pass over p, li, dd, td, summary and figcaption blocks for blocks over 40 words and an LLM / evaluative word list.
- Cross-surface numbers: eFV, consensus FV, trade value / surplus and eWAR read off the PROSPX card, the /projections/ player page and the /fa/ card for the same 21 entities. xM$ is dark (`xm_export.XM_DISPLAY_ON = False`), so no xM$ figure is served to compare.

## 2. Result in one table

| check | found | fixed | deferred |
|---|---|---|---|
| console / page errors | 4 console, 0 page | 1 (unknown-key 404 and render loop) | 0 (the other: one ERR_NO_BUFFER_SPACE socket error on this box, not the site) |
| failed requests | 4 | 3 of 3 site 404s (one key, three modes) | 0 |
| NaN / undefined / null rendered | 0 (every 'null' hit is a statistical null result in copy) | - | - |
| overflow at 375 px | 1 page (PROSPX Transactions, 3 px) | 1 | 0 |
| empty sections / stuck states | 0 | - | - |
| sorting | 0 of 15 columns (both directions monotone) | - | - |
| dark-mode contrast below 4.5:1 | 2 surfaces (/projections/ verdict badges 1.12:1, PROSPX farm grade letters 2.31:1) | 2 | 0 |
| light-mode contrast below 4.5:1 | 5 token families (Q4) | 0 | 5 (owner question Q4) |
| numbers that disagree for one entity | 1 pattern (card header consensus vs body, 7 of 13 sampled graduates) | label (Q1) | number basis (Q1), data defect (Q2) |
| stale dates | 1 (MLB moves timeline through 2026-07-23 on worktree data) | 0 | 1 (data, integration note) |
| served-copy lint findings | 251 sentence findings (L1 48, L2 3, L3 3, L5 29, L6 12, L7 19, L8 97, L9 15, L10 23, L12 2) and the gate red at HEAD | 96 fewer, 155 left: L1 22, L2 0, L3 0, L5 13, L6 7, L7 16, L8 64, L9 12, L10 20, L12 1 | the rest (code strings, exporter payload notes, pinned claims) |
| rendered blocks over 40 words | 110 on 15 routes | the mastheads, share cards and tooltips that broke a rule | the list in section 7 |

No served number moved. Every fix is copy, CSS or a rendering path.

## 3. Fixed

| id | surface | defect | fix | verified |
|---|---|---|---|---|
| F1 | /projections/ Model Accountability | The verdict badges inherited the page text colour after the 2026-08-03 move of their inline style to a `.proj-verdict` rule that was never written: light text on a bright fill in dark mode, 1.12:1 on Validated, 1.21:1 on Provisional. | `assets/projections.js` verdictBadge carries the shape and a fixed near-black text colour inline again (the documented pre-regression style). | computed colour rgb(11,11,11) on all four fills; contrast 15.1:1 Validated, 14.0:1 Provisional, 7.2:1 Unvalidated, 5.7:1 Deprecated in dark |
| F2 | PROSPX Farm Systems | Grade letters use a 40% lightness palette: D- 2.31:1 and A+ 3.76:1 on the dark card. | `[data-theme=dark]` lifts `.fg-letter` and `.fg-comp-letter` with `filter: brightness(1.6)`; hue and light mode unchanged. | screenshot shots_after/farm_letters_dark.png; D- moves to 5.0:1, A+ to 9.3:1 |
| F3 | PROSPX Transactions at 375 px | The page scrolled 3 px sideways: the freshness stamp (nowrap) and a promotion row's level move (AA, icon, AAA, club) overflowed their boxes. | `.newsprint-eyebrow` wraps; the level-move span wraps inside its column. | scrollWidth 375 of 375 |
| F4 | PROSPX card for an unknown or non-graduate key | The card fetched `/data/debuts_full/<key>.json` (404 in the console), then fell back to the whole debuts monolith. | `ensureDebutFullFor` skips the shard when the loaded lite rows hold no such key, and records the key so the card's render guard does not loop. | /player/#joey_votto: miss card, 0 console errors, 0 failed requests; graduate cards (Juan Soto) still load their shard |
| F5 | PROSPX card header (graduates) | The header printed the latest consensus point beside eFV ('eFV 49 · consensus 35' for Mason Miller) while the eFV block below prints the consensus locked at debut ('Consensus FV 49'). | The header labels it 'latest consensus' when the grade is locked at debut. No digit moves. | Mason Miller 'eFV 49 · latest consensus 35'; prospects keep 'consensus' |
| F6 | Library glossary (50 edits) | Sentences over 40 words, evaluative words (flagship, actually, simply, meaningful, dominant, dynamic, in short), caps emphasis (ONLY, NOT, EARLY, ENDPOINT DIFFERENCE), a question as a sentence, 'newly launched', docs paths and script names in reader copy, and one methodology sentence printed twice (fa_projection_engine). | Rewritten to shorter factual sentences by an idempotent script; no number, claim or verdict changed. | served lint; Library renders clean at 1280 and 375 |
| F7 | /models/ (registry reader fields, 26 edits) | Script paths, private identifiers and docs paths in `surface`, `metric` and `baseline` text; 60+ word metric sentences; 'honestly' and 'flagship' in two registry notes. | Same facts, identifiers removed, long sentences split. MODEL_REGISTRY.md regenerated. | test_model_registry: no new failure |
| F8 | share cards and chips | /mlbstats/, /pal/ and /standings/ meta descriptions over 25 words; the Scores / Standings beta chip tooltip over 25 words. | Rewritten to 22 to 23 words. | L2 and L3 now 0 |
| F9 | /sources/ | The MLB Stats API use cell and the excerpt paragraph each carried a sentence over 40 words. | Split; the 280-character limit, sources and links are kept. | test_sources_attribution and test_report_excerpt pins updated or kept |
| F10 | PROSPX tooltips | The DvM+ column tooltip and the tracking-head line tooltip ran over 25 words with a dash aside. | Rewritten to 24 words or fewer. | L2 0 |
| F11 | /awards/ My Ballot | The two confirm prompts were questions. | 'Clear your <award> ballot.' and 'Replace your <award> ballot.' beside the same buttons; the asset stays under its 35 KB budget. | test_awards_page budget passes |
| F12 | copy gates | The served copy gate was red at HEAD (new findings from earlier lanes, 15 stale entries); the em-dash gate did not scan /standings/. | Masthead credit lines and 'Perfect game in progress' registered (CREDIT, FIELD_NAME); baseline rewritten after the fixes; `standings/index.html` added to the em-dash targets. | test_copy_gates 30 of 30 |

## 4. Owner questions

Q1. Card header consensus on a graduate's PROSPX card. The header printed the latest consensus point; the eFV block prints the consensus locked at debut. 7 of the 13 sampled graduates print two different numbers (Mason Miller 35 / 49, Edwin Diaz 35 / 46, Tarik Skubal 56 / 51, Emmanuel Clase 41 / 40, Cal Raleigh 48 / 46, William Contreras 46 / 48, Samuel Basallo 59 / 58).
- A (default, built): keep both numbers and label the header 'latest consensus'. No digit moves.
- B: print the debut-locked consensus in the header too. 7 of 13 sampled graduate headers change digits.
- C: drop the consensus from a graduate's header; the eFV block keeps it.

Q2. Placeholder consensus points on debuted players. 105 debuted rows in data/debuts_lite.json end on a '2026_performance' snapshot from performance_ingest at FV 35 (org null), which becomes their fv_close and fv_low: Mason Miller reads 'Consensus range 35 (Oct 2026)-49', Edwin Diaz '35 (Aug 2026)-46'. This is the fixed-35 anchor pattern the RPR03 rule keeps off prospect cards.
- A (recommended, not built: it moves served numbers): exclude performance_ingest points from fv_close, fv_low and the consensus range for debuted players; 105 rows move.
- B: keep the points and print them as 'performance placeholder' wherever a range shows them.
- C: keep as served.

Q3. Retired players on /projections/. Clayton Kershaw (no 2026 MLB line) prints 5Y WAR 0.4, 2027 WAR 0.21 with LAD and status 'arb / pre-arb'. 262 of 1,400 projected veterans have no row on the 2026 eWAR board; most are injured, so a retirement flag needs its own source.
- A (recommended, not built: Team Outlook WAR moves): read MLB's transaction status for retirements and drop retired players from player and team projections.
- B: keep them and print 'no 2026 MLB line' on the card.
- C: keep as served.

Q4. Light-mode contrast of accent tokens (dark mode passes after F1 and F2): farm grade letters B- 2.37:1 on the light card, IL day counts 2.28:1, draft round chips R1 2.09:1, the '+ upside' driver tag 1.78:1, park factor cold cells 4.35:1.
- A (default, nothing built): leave the palette for a design pass.
- B: darken each light-mode token to 4.5:1 (a visible colour change on five chip families).

## 5. Deferred (not a defect of this pass, or blocked by a rule)

- MLB moves timeline 'through Jul 23, 2026' on every /projections/ player page and the /news/ state line. Data: the worktree's data/mlb_events/ copy is dated 2026-07-23 and the main tree has no data/mlb_events/ at all; the nightly step 9e-pre0g writes it. Integration note, no code change.
- Data freshness: pages read 'as of 2026-10-02' (owner pipeline last run). Not a code defect.
- Exporter-written copy with internal identifiers or 40+ word sentences: ledger_export.py payload notes (the farm-dollar note names the clemens_2026 valuation set and the calibration id, 153 words), data_catalog.py, baserunning_export.py, trade_audit_export.py, proj_export.py, source_backtest.py. Fixing them regenerates served artifacts; left for a pass that regenerates them.
- Pinned claims kept verbatim: the /pal/ masthead (53 words, pinned by test_pal_smoke.py), the playoff_odds_sim surface (pinned by test_model_registry.py), the docs path in the Library matrix note (pinned by test_glossary_page_loads.py).
- Lint false positives accepted in the baseline: an inline script in build_site.py read as prose (L1, L9) and the PIXEL_BRAND CSS comment (L8).
- Sorting: no defect. The FA, Projections and Arbitration headers sort through a native button inside the th; mlbstats, PAL and Trade Machine sort on the th.
- Dark-mode contrast was measured where the background is a flat colour; text over the starfield gradient was skipped (most module pages), so a 0 there means not measured, not passed.

## 6. Cross-surface numbers (21 entities, 1280 light)

eFV matched on the PROSPX card and /projections/ for all 18 tracked players. Trade value on the card equals /projections/ surplus to the printed rounding for all 10 players that print both (Ohtani $203.2M / $203M, Soto $83.9M, Skenes $157.4M / $157M, Griffin $135.9M / $136M, McGonigle $423.2M / $423M, Miller $30.7M, Raleigh $123.2M / $123M, Contreras $54.9M, Basallo $58.2M, Diaz -$48.7M). The one disagreement is the header consensus in Q1. xM$ is dark, so it has no served value to compare.

## 7. Rendered blocks over 40 words

110 blocks on 15 routes (the article body is third-party copy and excluded; a duplicate route alias is counted once). Most are receipts made of several short sentences; the lint's sentence rule (L1) is the gate. Mastheads and share cards that broke a rule are fixed in F8 and F10.

| route | words | element | opening |
|---|---|---|---|
| awards | 88 | p.aw-rule | The eephus selection by in-league eWAR v2, both sides, among players who pass the rookie test. Not a forecast ... |
| awards | 66 | p.aw-rule | The eephus selection by in-league eWAR v2, batting plus pitching, summed before rounding. Not a forecast of th... |
| awards | 50 | p.aw-rule | The eephus selection by in-league pitching eWAR v2. Not a forecast of the BBWAA vote. Floor: in-league IP of a... |
| awards | 50 | p.aw-rule | The eephus selection by club-season wins above the club's own earned eWAR v2. Not a forecast of the BBWAA vote... |
| betting | 57 | p. | eephus.io is not a sportsbook: no wagers, no cut, no affiliate links. Nothing here is betting advice. Sports b... |
| diamond | 101 | p.dm-fine | Over 8.0 (2026-09-26) carried the slate total-lean caveat when it was published: "Slate leans Over: model Over... |
| diamond | 45 | p.dm-fine | Tiles and margin share one frame: base year equals the eFV decision year, and eFV's consensus input is the rat... |
| diamond | 43 | p. | 1 of 1 row behind this record carried the slate total-lean caveat, which says the lean is a known model shape ... |
| franchise | 88 | p.fr-count | A Hall of Famer is credited to one franchise: the one with which he accumulated the most Baseball-Reference WA... |
| franchise | 84 | p.fr-count | The MLB leg is the Club Ledger's projected surplus of the club's contract and arbitration-path veterans; no pr... |
| franchise | 79 | p.fr-note | Realized value, not skill. What is shown here is what happened after the club's decisions: the reliever called... |
| franchise | 64 | p.fr-count | flag bits: 1 step not from published service time, 2 step from the debut heuristic, 4 no salary on file, 8 pas... |
| franchise | 47 | p.fr-count | 53 of 63 signings covered · WAR to date 41.9 · paid $779.5M · surplus -$269.0M · method level_proration_backca... |
| franchise | 46 | p.fr-count | Standings 2000-2026 join by StatsAPI team id and need no spine; the bWAR line runs through franchise_spine.jso... |
| franchise | 43 | p.fr-count | In-game management is shown under DUGOUT and not scored: the one decision family the site has gated, the runni... |
| franchise | 41 | p.fr-count | per family, never a cross-family total; defensive subs carry a count only · agent: club-season. The agent is t... |
| gl_calib | 118 | p.meth-note | What an eFV grade is worth: the model's own surplus, WAR and star odds per tier, against the published FanGrap... |
| gl_calib | 77 | p.meth-note | The last two columns are the current active board itself: how many live prospects sit nearest each tier and th... |
| gl_calib | 75 | p.meth-note | ECE (expected calibration error) is the bin-weighted gap between the probability the model assigned an outcome... |
| gl_calib | 73 | p.meth-note | Every night eFV v1's five-bucket outcome distribution, the odds the board served until September 25, 2026, is ... |
| gl_meth | 289 | p. | The build, in order: (1) the FV→WAR anchor converts the scouting grade to an expected WAR/year over seven cont... |
| gl_meth | 160 | p. | The org grade is a weighted tree (Farm grade tree), not a single formula, so each letter is auditable down to ... |
| gl_meth | 157 | p. | The consensus FV is the scout-grade aggregate eFV anchors on, and the reference shown alongside eFV everywhere... |
| gl_meth | 111 | p. | Roll-ups are explicit, not implied. Org surplus is the sum of its active prospects' per-player surplus dollars... |
| gl_meth | 104 | dd. | An org's development credit over trailing windows of one to eight years, scored against the league-mean farm (... |
| gl_meth | 94 | p. | The rule. eFV V2 keeps the consensus FV order inside hitters and inside pitchers. A small set of drivers moves... |
| gl_meth | 88 | dd. | Averaging cancels idiosyncratic source error, and the measured edge is two-legged: on resolved cohorts the ble... |
| gl_meth | 78 | p.meth-note | A price is an expectation, not a median. The median outcome of a low-tier prospect is a bust worth nothing, so... |
| gl_meth | 75 | dd. | Equally: every source votes at exactly 1.0. An accuracy-weighted blend (per-source weights from measured track... |
| gl_meth | 67 | p. | A prospect is an asset because the seven years of club control after debut are paid below market. Surplus valu... |
| gl_meth | 67 | p.meth-note | Every public FV-to-WAR table answers a different question. Some price a single season if the prospect arrives.... |
| gl_meth | 66 | p.meth-verdict | How eFV compares with the public sources is measured, not asserted: the Source Comparison tab runs the out-of-... |
| gl_meth | 66 | p. | Grades are forward-filled: sources publish on different dates, so the consensus on any date uses the latest gr... |
| gl_meth | 65 | dd. | A graduate's career WAR rate projected to a role-typical full season (612 PA for hitters; 175 / 65 / 50 / 60 I... |
| gl_meth | 62 | p. | Graduates keep their earlier grade. Graduates and busts keep the eFV v1 grade, scored at the final pre-debut s... |
| gl_meth | 60 | dd. | The evaluation window spans seven preseason base years (2017-2023): the 2017-2020 cohorts are fully resolved w... |
| gl_meth | 58 | dd. | A side-aware composite of tracked Statcast / zone signals - contact quality + zone discipline for hitters; stu... |
| gl_meth | 55 | p.meth-note | Public tables get thin below FV 45, so the low anchors tend to be constants someone chose. Most of a board liv... |
| gl_meth | 54 | dd. | A position-weighted blend of an org's per-tool DvM+ values (Hit, Power, Field, Arm, Fastball, Command, …). Eac... |
| gl_meth | 53 | dd. | Hitters' wRC+ against their level and pitchers' ERA- against theirs, each with an age-for-level term, indexed ... |
| gl_meth | 52 | p.meth-note | One price of a win. The signings-implied series reads $16.2M per WAR for the 2026 winter (fa_dpw_series.json).... |
| gl_meth | 46 | p.meth-note | Our fix is a hard two-table split: a conditional shape inside the outcome mixture (what a hit looks like) and ... |
| gl_meth | 44 | p.meth-note | A deferred dollar is not a dollar. Contract legs are compared on NPV at 7%/yr, so a heavily deferred sticker d... |
| gl_meth | 43 | p.meth-note | The live board uses equal weights; the accuracy-weighted scheme shipped in June 2026 was reverted on 2026-07-2... |
| gl_meth | 42 | p.meth-note | Baseball America re-based its grade scale for 2026. A consensus that corrected BA with one flat offset would s... |
| gl_sacc | 99 | p.meth-note sacc-headline | The owner question is UNANSWERABLE in most cells. 2 of 25 scored cells clear their own MDE95, against 1.25 exp... |
| gl_sacc | 42 | p.meth-note | After a Holm correction inside each partition, 1 survive: by_age_at_grading:23-24. The survivors are largely T... |
| ledger | 114 | p.ledger-count | Cost+ pool: n 30, mean 100.0, sd 10.0; descriptive index, not a model: projected 2027 WAR, less the 2027 WAR o... |
| ledger | 52 | p.ledger-note | Every pending club, player and mutual option and opt-out on this winter's free-agent class, with the salary at... |
| ledger | 50 | p.ledger-count ledger-foot-note | The two rows differ by $18.0M because Spotrac's league average is the page's average row as fetched 2026-07-07... |
| ledger_club | 153 | p.ledger-count | A farm dollar here is an expected value: the eFV expected surplus of an active prospect, in millions, on the c... |
| ledger_club | 114 | p.ledger-count | MLB leg: MLB Projections surNpv at dpw 16,856,777 (2027 ex-ante), 5-season horizon, every guaranteed season pa... |
| ledger_club | 107 | p.ledger-note | 118 graduates developed here. Graduates are listed by the club that developed them, not the club they play for... |
| ledger_club | 95 | p.ledger-count | MLB Trade Rumors, Matt Swartz, published before settlement; present on 859 history rows, of which the a6 arm s... |
| ledger_club | 94 | p.ledger-count | $DvM+ is 100 + 10z of the prospect's grade pace (eFV change per year, consensus FV where eFV has no history, p... |
| ledger_club | 93 | p.ledger-count | The roll-up leaf is the sum over active prospects of eFV expected surplus minus the signing bonus on file, com... |
| ledger_club | 85 | p.ledger-count | Nominal guarantees, the same dollars as the Spend by winter table, over the thirty clubs' total for the window... |
| ledger_club | 71 | p.ledger-note | Projected pick 25 (93-68, tankathon 2026-10-02). Pick WAR: 2.63 (bucket to pick 35). expected first-6 WAR of t... |
| ledger_club | 69 | p.ledger-count | Spotrac's tax page for each season from 2016 to 2026 as cached, read without a fetch: tax payroll, payor tier,... |
| ledger_club | 60 | p.ledger-note | Deferred dollars outstanding (covered deals only): sticker $0.0M, NPV at the platform 7 pct rate $0.0M. covere... |
| ledger_club | 56 | p.ledger-count | ou_mkt: vs market: actual minus this model; what arbitration paid against comparables. Sums to roughly zero by... |
| ledger_club | 46 | p.ledger-count | joined on draft year and overall pick, never on name; the tracker and graduated counts follow the player where... |
| ledger_club | 45 | p.ledger-count | The stack above prices the club's priced veterans' salary paths; this bar sums the Arbitration Predictor's boa... |
| ledger_club | 45 | p.ledger-foot | Descriptive ledger. No single projected payroll is served: contract dollars on file, projected arbitration ste... |
| ledger_club | 44 | p.ledger-count | the three parts print apart and are never added into a payroll figure; a rung for a player whose 2027 salary i... |
| mgmt_clubs | 75 | p.mgmt-note | Inherited runners: 71 scored of 231 inherited (30.7%); derived: the corpus carries no per-runner scoring id, s... |
| mgmt_clubs | 48 | td. | ahead, inning 1-6: 15, ahead, inning 7: 15, ahead, inning 8: 51, ahead, inning 9+: 44, behind, inning 1-6: 10,... |
| model_updates | 97 | td. | eFV v1, S-XLINE Statcast measurement layer (gate docs/efv-2026-07-23/GATES.md): AAA stat lines from 2023 on we... |
| model_updates | 94 | td. | The fWAR label epoch: the TRAINING label behind eFV, the FV-to-WAR anchors, the projections, the draft slot cu... |
| model_updates | 87 | td. | eFV v1, B-L6 denoised baseline fairness control (gate docs/efv-2026-08-09/DENOISED_BASELINE_GATE.md), measured... |
| model_updates | 85 | td. | Historical backfill: ingested FanGraphs 2017-2020 boards (new-format CSVs) + MLB Pipeline 2017-2020 Top-100 li... |
| model_updates | 83 | td. | eFV v1's level calibration retired: an affine dispersion correction shipped that morning was reverted to ident... |
| model_updates | 78 | td. | eFV v1, P1 V3 slot trust, a train and serve correctness fix for provisional grades (drafted, no pro track reco... |
| model_updates | 65 | td. | The eWAR label epoch: site-wide WAR and every model labelled, anchored or priced in WAR (the eFV label, the FV... |
| model_updates | 65 | td. | Surplus moved to an EXPECTED-VALUE objective (calibration isotonic-real-v6-evframe): the correction map is now... |
| model_updates | 62 | td. | The head-to-head headline moved to the timing-pinned vintage-matched frame vm2, where eFV's consensus input is... |
| model_updates | 61 | td. | Farm grade tree v40: value-tracking reweight. The org letter is now primarily driven by aggregate risk-adjuste... |
| model_updates | 57 | td. | The org promotion multipliers left the served ETA: in the keep-or-remove gate (list vintage 2024) the two arms... |
| model_updates | 53 | td. | eFV v1's guarded blend left the active board when eFV V2 began serving. It ranked on a mix of the consensus WA... |
| model_updates | 53 | td. | Consensus source weighting REVERTED to equal. The June accuracy weights (Pipeline 1.06 / FanGraphs 0.94) faile... |
| model_updates | 51 | td. | eFV v1's displayed grade left the per side quantile map, a rank map onto the consensus distribution, and moved... |
| model_updates | 48 | td. | eFV v1's board overlays left the active board when eFV V2 began serving: injury, prospect age, stale list cove... |
| model_updates | 48 | td. | Consensus FV moved to ACCURACY-WEIGHTED source blending after a vintage-disciplined A/B measured it above equa... |
| model_updates | 47 | td. | Cross-source scale normalization: each source's grades are quantile-mapped onto the FanGraphs scale over the p... |
| model_updates | 41 | p.mu-intro | One row per served model, the scored ones first. A lead prints only when the interval clears zero, a one-sided... |
| model_updates | 41 | td. | eFV V2 serves the board (owner decision DS-02): consensus percentile plus admitted skill and timing drivers wi... |
| models | 101 | li. | data/xfv_disagreements_eval.json · July 24, 2026 NO SHIP. The biggest-miss gap is irreducible variance on the ... |
| models | 91 | li. | data/riv_plus_eval.json · August 30, 2026 SUPERSEDED 2026-09-18. The claim this artifact carried, that RIV+ tr... |
| models | 82 | summary.acct-sum | etool_ebat PROVISIONAL The shown tool grade (marked e, to the nearest whole grade) on PROSPX cards, list rows,... |
| models | 82 | summary.acct-sum | etool_ecmd PROVISIONAL The shown tool grade (marked e, to the nearest whole grade) on PROSPX cards, list rows,... |
| models | 82 | summary.acct-sum | etool_efb PROVISIONAL The shown tool grade (marked e, to the nearest whole grade) on PROSPX cards, list rows, ... |
| models | 82 | summary.acct-sum | etool_ehit PROVISIONAL The shown tool grade (marked e, to the nearest whole grade) on PROSPX cards, list rows,... |
| models | 82 | summary.acct-sum | etool_epow PROVISIONAL The shown tool grade (marked e, to the nearest whole grade) on PROSPX cards, list rows,... |
| models | 82 | summary.acct-sum | etool_esel PROVISIONAL The shown tool grade (marked e, to the nearest whole grade) on PROSPX cards, list rows,... |
| models | 71 | summary.acct-sum | etool_composite UNVALIDATED Every PROSPX surface that prints or sorts on the Tool composite: the card chips (w... |
| models | 57 | summary.acct-sum | playoff_odds_sim PROVISIONAL /projections/ Team Outlook and the /betting/ Futures tab. /standings/ ODDS group ... |
| models | 44 | summary.acct-sum | tool_tables_rederived PROVISIONAL /scouting/ tool tiers (TL_23_SCOUTING_PAGE_FLIP, 2026-10-15): a cell that re... |
| models | 44 | summary.acct-sum | postseason_bracket_sim UNVALIDATED /betting/ Futures Pennant and World Series columns and postseason table, Fr... |
| models | 43 | summary.acct-sum | tool_source_accuracy PROVISIONAL Served since 2026-10-14: the Source Accuracy Tools tab on /glossary/ prints l... |
| models | 42 | summary.acct-sum | etools_plus PROVISIONAL PROSPX: the eT+ chip on the list row's tool strip (tooltip: each tool's weight, grade ... |
| models | 42 | summary.acct-sum | proj_components PROVISIONAL the component lines of the /projections/ player Projection tab: rates, batting, ba... |
| models | 42 | summary.acct-sum | tool_implied_production PROVISIONAL Served since 2026-10-14: the Source Accuracy Tools tab on /glossary/ print... |
| models | 41 | summary.acct-sum | trade_partner_screen UNVALIDATED Trade Machine partner screen (/trademachine/, under the deal builder): for a ... |
| pal | 53 | span.section-sub | Role and position conversions. SP to RP passed its gate, though a sort on high pre-season ERA ranks the same e... |
| scouting | 53 | p. | For hit, game power, pitch selection, bat control, fastball and command, PROSPX shows the eTool: the consensus... |
| scouting | 51 | p.sc-callout | 'If he arrives' is WAR for a player who reaches his projected role; 'Expected, bust-inclusive' averages every ... |
| scouting | 49 | p.sc-note | 45 and up: the 2014-2020 average (3,463 players), blended half and half with the public Edwards scale, more pu... |
| scouting | 42 | p.sc-note | Our prime-season table gives WAR in a full prime season for a player who sticks, from FV 35 up. The FanGraphs ... |
| scouting | 42 | p.sc-note | This column is the table our valuations use today. Its registered calibration test, the Prospect Anchor gate, ... |
| sources | 101 | p. | PROSPX grades are a consensus of seven industry sources. A player's card shows each source's FV grade beside t... |

## 8. LLM and evaluative wording

The rendered pass found no phrase from the COPY_STYLE.md section 4 hallmark list outside the third-party article. Remaining hits are baseball terms: 'best of 7', 'high-leverage', the 'elite' outcome bucket, 'Perfect Game Field' (a venue). Two registry notes on /models/ said 'honestly' and 'flagship'; both are rewritten (F7).

## 9. Tests

Relevant files only, `-p no:cacheprovider`. New failures: none. Failures present at HEAD 8a5a43da before any change of this pass (checked by running them on a clean stash): test_scores_render chart crosshair; test_standings_render budgets (standings.js 47,972 bytes over 46,080); test_sources_attribution baseballprospectus.com host; test_claims_freshness war_pa_plus numbers; test_awards_copy glossary drafts; test_model_registry unregistered eval artifacts and STALE_DAYS; test_report_excerpt glossary.js limit phrase; test_prospx_card_one_consensus (3, eyebrow format); test_mlbstats_windows columns; test_ledger_export two trade-value lags; test_prospect_anchor_gate flag site; test_franchise_export eWAR; test_methodology_freshness mappings.

