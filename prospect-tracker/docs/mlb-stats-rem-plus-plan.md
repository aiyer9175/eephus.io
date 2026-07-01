# PROMPT — MLB Modules nav group + MLB Stats module + Bullpen Leaderboards (REM+)

Build three things, in order, on `eephus.io` (the `prospect-tracker` repo). Treat this as
best-model-wins, copy-clean, test-green work — the same bar as every other module here. Do
NOT commit or push unless I explicitly ask. Use plan mode and `AskUserQuestion` for the
owner-level decisions flagged at the bottom before writing code for that part.

---

## PART A — "MLB Modules" nav dropdown group

Goal: group **Free Agency** and **MLB Projections** (and the new **MLB Stats** module from
Part B) under one **"MLB Modules"** dropdown in the nav — on both the homepage and the
in-module top bar. PROSPX, CollegeSavant, Articles, Forums, Glossary, Developers stay where
they are (PROSPX/CollegeSavant are MiLB/amateur, not MLB).

Where the nav lives (single source):
- `build_site.py` → `NAV_ITEMS` (the flat `(key, label, href)` registry, ~line 122) is rendered in **two** places you must both update:
  - `_nav(active)` (~line 566) → the top bar (`.eephus-nav` / `.eephus-links`).
  - the homepage sidebar builder (~line 1840) → `.sb-group` / `.sb-nav`, with `sidebar_icons` / `sidebar_labels`.
- CSS for both lives in `assets/site.css` (`.eephus-nav`, `.eephus-links`, `.sb-nav`, `.sb-group`, `.sb-group-label`).
- `PROSPX_SUBNAV` (~line 136) is the existing pattern for a grouped/nested set of links — mirror its shape.

Implementation:
1. Change `NAV_ITEMS` (or add a parallel grouped structure) so a nav entry can be either a
   leaf `(key, label, href)` or a group `{label: "MLB Modules", children: [...]}`. Keep it one
   source so the top bar and the sidebar stay in sync — do not hand-duplicate the grouping.
2. Top bar (`_nav`): render "MLB Modules" as a dropdown (a `<details>`/`<summary>` or a
   button + CSS hover/focus menu — pick the accessible one; the bar is single-line, see the
   `short` map). Keyboard + screen-reader accessible (`aria-expanded`, focus-visible, Esc to
   close). Active-state: highlight "MLB Modules" when the active page is any of its children.
3. Homepage sidebar: render the group as a labeled sub-block under "Modules" (the
   `.sb-group` / `.sb-group-label` pattern already exists — reuse it; sidebar can stay
   expanded rather than a dropdown since it's a vertical rail).
4. Keep `MODULE_STAGE` (~line 244) and the cross-module hub strip
   (`assets/eephus-hub.js` → `MODULES`, ~line 45) consistent — add the MLB Stats surface to
   the hub strip if/when a player has a page there (Part D), otherwise leave it.

Decisions to confirm with me first (defaults in parens): dropdown interaction = click vs
hover (click), group label = "MLB Modules" (yes), whether the group also appears as a
homepage module **card** or only in the nav rail.

---

## PART B — New "MLB Stats" module scaffold

A new top-level module, added to the "MLB Modules" group from Part A. First (and for now,
only) section is **Bullpen Leaderboards** (Parts C+D). Scaffold it to grow — other MLB stat
sections will come later.

- New page surface: `/mlbstats/` (new dir + `mlbstats/index.html` + `assets/mlbstats.js`),
  modeled on the Projections module: `projections/index.html` + `assets/projections.js` +
  `proj_export.py`. Match the on-theme shell (THEME_INIT, FAVICON_LINKS, `_nav`, `_footer`,
  `CREATED_BY_BANNER`, the `.build-banner`/masthead, social meta) the other build_site pages emit.
- Register the route in `build_site.py` (NAV_ITEMS group from Part A; add to `MODULE_STAGE`
  as `("α", ...)` — newly launched) and wherever sitemap/routes are enumerated.
- Lifecycle sigil = α on the module masthead only (per the no-sigils-in-nav rule).
- Section nav inside the module (like `PROSPX_SUBNAV`): "Bullpen Leaderboards" first, leave
  room for future sections.

---

## PART C — REM+ model (Reliever Evaluation Metric +)

Build a new, validated, rate-based reliever rating: **REM+**, on a **ratio-to-league scale**
(100 = average reliever, 110 = 10% better than average, like ERA+/OPS+/wRC+ — NOT a z-score
scale). Higher = better. This is the headline number on the Bullpen Leaderboards.

### C0. Research first (read before designing)
Fully read and extract methodology from all of these. Prefer the more recent / more rigorous
when they conflict, and where they genuinely disagree, **resolve it empirically** in the
backtest (C4) rather than by assertion:
- https://tht.fangraphs.com/win-probability-added-above-replacement/  (WPA-above-replacement; WPA, WPA/LI, gmLI, leverage-weighting — the core reliever-value framing)
- https://blogs.fangraphs.com/can-wpa-explain-how-teams-buy-relievers/  (does WPA explain the market — your secondary validation target)
- https://blogs.fangraphs.com/what-determines-reliever-leverage/  (leverage is MANAGER-ASSIGNED, partly a trust signal not earned skill — the key caution against over-rewarding gmLI)
- https://blogs.fangraphs.com/reliever-contracts-make-plenty-of-sense/  (market rationality for relievers)
- https://blogs.fangraphs.com/relief-pitching-in-context/  (small samples, sequencing, which rate stats stabilize — what to trust vs discount)
- https://pitcherlist.com/fantasy-reliever-rankings-closers-holds-solds-6-23/  (practical role taxonomy — closer/setup/holds — feeds the Part D depth charts)
Use `WebFetch`. You may add sources, but only sabermetrically grounded, validated ones
(FanGraphs, Baseball Prospectus, THT, PitcherList, MLB.com, Tango/Book-blog). Write a short
"what each source argues + where they conflict + how I'll settle it" note before coding.

### C1. Reliever population ("true relievers" only)
REM+ is computed only over a reliever pool, re-normalized to that pool's mean (so 100 = the
average **reliever**, not the average pitcher). Define the filter and document it:
- `GS = 0` (or `GS/G ≤ ~0.10` to keep occasional spot-starters), AND a relief-IP / relief-
  appearance minimum (full-season default ~`≥20 IP` and `≥20 G`, pro-rated for partial
  seasons), AND exclude **openers** (filter on first-inning/high-entry-leverage short stints)
  and bulk/swing arms (relief-share + entry-inning test).
- Two tiers: **qualified** (meets the IP/TBF minimum → shown on the leaderboard) vs
  **provisional** (below threshold → shown but flagged, like the rest of the site's
  provisional handling). Pick the qualifying TBF from the stabilization analysis in C4.

### C2. Components (rate-based, sample-shrunk)
REM+ is built from a small set of **robust, fast-stabilizing rate components**, weighted by
what carries forward (C4), not a kitchen sink. Candidate inputs (all per-TBF / rate, league-
and park-adjusted via the `-` scale where available):
- Skill core: `K%`, `BB%` (or `K-BB%`), `SwStr%`/`CSW%`, `FIP` and/or `xFIP` (HR-normalized),
  GB% / HR-suppression. These stabilize fastest — weight them most (per "Relief Pitching in
  Context").
- Results layer (discounted, noisy in RP samples): `ERA`/`RA9`, strand/BABIP — include only
  if they earn forward signal in C4; expect to down-weight or drop them.
- Context/leverage layer: `gmLI` (entry leverage), `WPA`, `WPA/LI` (context-neutral WPA),
  `Clutch`, Shutdowns/Meltdowns (`SD`/`MD`).
- **Sample shrinkage**: regress each rate toward the reliever-pool mean by sample size — reuse
  the existing shrink-at-source pattern (`RPS+` / `level_norms.py`, K_AB/K_IP style). Small RP
  samples must not produce blow-ups (the explicit lesson from the RPS+ calibration work).

### C3. The leverage question (the central design decision)
The articles pull two directions and you must pick a philosophy and validate it:
- "WPA-above-replacement" / "Can WPA explain how teams buy relievers" → leverage & WPA ARE
  the value; reward them.
- "What Determines Reliever Leverage" → gmLI is **assigned by the manager**, so rewarding it
  blindly double-counts reputation and bakes in usage you can't credit to the pitcher.

Recommended default (validate, don't assume): a **two-number system** —
- **REM+** = a **leverage-aware skill rate** on the 100-ratio scale: a run-prevention estimate
  from the stabilized skill core, with leverage used as a *weighting/precision* signal (high-
  leverage innings count, but the score measures the pitcher's rate, not the role he was
  handed). This keeps REM+ comparable across roles.
- **A companion Impact/Leverage column** (gmLI, WPA, WPA/LI, SD–MD) shown alongside — the
  context the user explicitly wants surfaced, kept separate so role assignment doesn't
  contaminate the talent number.
Also build a third **leverage-weighted REM+** variant (folds a bounded gmLI multiplier into
the score) so C4 can pick the winner. Whatever wins the forward test ships; the losers go in
the loss ledger.

### C4. Validation + backtest (ship gate — REM+ must BEAT naive baselines)
Pull multi-season MLB reliever leaderboards (target ~2015–2025) — see C5 for source. Then:
1. **Reliability / stabilization**: split-half within season (odd/even appearances or 1st/2nd
   half) correlation of each component and of REM+. Report the TBF where REM+ stabilizes →
   sets the C1 qualifying threshold.
2. **Forward predictiveness (the real gate)**: forward-chained, out-of-sample — does REM+ in
   year Y predict the reliever's Y+1 run prevention (RA9/FIP) and WPA **better than** each
   naive baseline: raw ERA-, FIP-, xFIP-, and raw WPA? Report Spearman per baseline across
   seasons. **REM+ must beat the baselines to ship** (best-model-wins, like every other model
   here). If it doesn't, simplify components and re-test; document honestly.
3. **Variant bake-off** (settles C3 and the article conflicts): score the pure-skill, the
   two-number, and the leverage-weighted variants on the same forward test; ship the winner,
   loss-ledger the rest.
4. **Market check (secondary, informative — NOT a ship gate)**: correlate REM+ and leverage-
   weighted REM+ with reliever contract AAV (you already have FA/contract data in
   `fa_*`/`value_framework.py`) — the "Can WPA explain how teams buy relievers" test. Report it.
5. Write `data/rem_plus_eval.json` (follow the existing eval-artifact shape, e.g.
   `data/statcast_plus_eval.json`: seasons, cohort_n, the r/rho vs each baseline, a `verdict`
   block with a plain-English summary). Register REM+ in `data/model_registry.json` (model_id,
   surface `/mlbstats/`, predicts, champion, baseline, metric, eval_artifact, verdict from the
   `validated|provisional|unvalidated|deprecated` enum). Every eval artifact must be
   registered (standing rule).

### C5. Data source
- Primary: `pybaseball.pitching_stats(season, qual=0)` — the FanGraphs reliever leaderboard
  gives FIP, xFIP, K%, BB%, ERA-/FIP-/xFIP-, WPA, WPA/LI, Clutch, gmLI, inLI, SD, MD, GS, IP
  in one pull. pybaseball is already a dependency (`tools/build_def_history.py` uses
  `pyb.bwar_bat`). Verify reachability **early** — memory notes FanGraphs Cloudflare-blocks
  some autonomous scrapes; `pitching_stats` uses a different leaderboard path, but confirm
  before building on it.
- Role/IP/GS cross-check + headshots/ids: StatsAPI via `stats.py` (already pulls
  `inningsPitched`, splits, `check_rookie_threshold`).
- If a source is blocked, fall back to cached `.cache/` + `WebFetch`, and say so — don't fake
  coverage.

---

## PART D — Bullpen Leaderboards UI (two sections + depth charts)

On `/mlbstats/`, the **Bullpen Leaderboards** section has two sub-sections plus depth charts:

### D1. Individual relievers
Sortable, filterable leaderboard of qualified relievers: REM+ (headline, default sort), the
Impact/Leverage companion (gmLI, WPA, WPA/LI, SD–MD), and the underlying rates (K%, BB%,
K-BB%, FIP, xFIP, SwStr%/CSW%, IP). Provisional relievers flagged. Reuse the existing table
sort/filter pattern (`assets/projections.js`, `collegesavant/table_sort.js`) and team logos.

### D2. Team bullpens (holistic)
A team-level rating — propose **Bullpen+** (100 = average bullpen): a **leverage-weighted**
aggregate of its relievers' REM+ (weight by gmLI or by IP-in-leverage — i.e. how good are the
innings the pen actually throws, in the leverage it throws them). Surface alongside it:
bullpen depth (count/share of above-average relievers), a high-leverage-core rating (top
relievers by gmLI), and team bullpen WPA / SD–MD. Validate Bullpen+ the same way (does it
predict the pen's forward run prevention) — at least report it; flag if unvalidated.

### D3. Bullpen depth charts (roles)
Per team, bucket relievers into roles from gmLI + usage (informed by the PitcherList taxonomy):
Closer (top gmLI / saves) → High-leverage/Setup (gmLI ≳ 1.2) → Middle (≈0.8–1.2) →
Low-leverage/Long (< ~0.8 or long-relief by IP/appearance) → Mop-up. Show REM+ per slot so a
reader sees the shape and quality of each pen's leverage ladder.

### D4. Display conventions
- REM+/Bullpen+ display as **nearest-integer** (the convention for +stats — wRC+, Stuff+).
  NOTE: the site-wide "grades round UP" rule is for **FV and 20-80 tool grades only**; it does
  NOT apply to these 100-scale +stats. Confirm with me if unsure.
- Add a GFX/share card if it fits the section (the `EEPHUS_HUB.shareCard` / GFX path), optional
  for v1.

---

## CROSS-CUTTING (applies to all parts)

- **Pipeline**: add a `run_monthly.py` step that pulls the reliever leaderboards, computes
  REM+ + Bullpen+ + roles, and writes `data/bullpen_leaderboards.json` (or similar). Respect
  the committed-artifact / test-isolation guard (conftest `_restore_committed_build_artifacts`)
  — running the suite must not leave the data tree dirty.
- **Glossary**: add entries to `data/glossary.json` (via `build_glossary_data.py`) for
  `rem_plus`, `bullpen_plus`, `gmLI`, `WPA`, `WPA/LI`, `leverage_index`, `shutdowns_meltdowns`,
  and the role definitions, so ⌘K + tooltips work site-wide (`assets/eephus-gl.js`).
- **Tests**: model tests (population filter correctness, 100-anchoring of the ratio scale,
  shrinkage behavior on small samples, leverage handling), a data-contract test for the new
  JSON, and a `py_mini_racer` JS smoke test for `assets/mlbstats.js` (the CollegeSavant
  precedent). Full suite green.
- **Copy**: plain prose, no em-dashes, no LLM-isms. Run `tools/strip_emdashes.py --check` and
  `tools/copy_lint.py` — both green.
- **No silent caps / honest losses**: if a component, variant, or the whole leverage-weighting
  fails to earn OOS signal, drop it and write the loss into `rem_plus_eval.json` + the model
  registry notes. Don't ship an unvalidated headline number as if validated.
- **Don't commit or push** until I ask. When done, summarize: what shipped, the backtest
  numbers (REM+ vs each baseline), which variant won, what got loss-ledgered, and the open
  follow-ups.

## OWNER DECISIONS TO SURFACE (ask via AskUserQuestion before building the relevant part)
1. REM+ philosophy: two-number (skill REM+ + separate Impact column) [recommended] vs single
   leverage-weighted REM+ vs pure context-neutral skill.
2. Reliever qualification thresholds (IP/G/relief-share, opener handling).
3. Nav dropdown interaction (click vs hover) and whether "MLB Modules" also gets a homepage card.
4. Module name ("MLB Stats" vs "MLB Stats Hub") and section name ("Bullpen Leaderboards").
