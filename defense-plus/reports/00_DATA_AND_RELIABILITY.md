# Defense+ — Spike 0: Data Availability & Metric Reliability
Date: 2026-06-16 · Machine: willcahoon · pybaseball 2.2.7 @ Python 3.13 framework build

## 1. Reachability verdict (the binding constraint)

| Source | Metrics | Status | How |
|---|---|---|---|
| **FanGraphs — legacy scrape** | (any) | **BLOCKED (403)** | `pb.fielding_stats`, `pb.team_fielding` hit `leaders-legacy.aspx` → 403 |
| **FanGraphs — modern JSON API** | Def, UZR, UZR/150, DRS, RngR, ARM, DPR, ErrR + 8 DRS components, FG-hosted OAA/FRP/CFraming, **Inn by position**, pos adj | **OK** ✅ | `/api/leaders/major-league/data?stats=fld&type=8&season=Y&season1=Y` with browser UA — same mechanism playing-time used for `/api/projections`. ~2,200 player-position rows/yr |
| **Baseball Savant — IF OAA** | OAA, Fielding Runs Prevented, directional (in/lateral/behind), RHH/LHH splits, success-rate vs expected | **OK** | CSV `/leaderboard/outs_above_average?pos=if&year=…` |
| **Savant — OF OAA** | OAA + position labels (CF/LF/RF), directional slices, catch prob by bucket | **OK** | same leaderboard `pos=of`; + `outfield_directional_oaa`, `outfielder_jump`, `outfield_catch_prob` |
| **Savant — Catcher framing** | Framing RV (rv_tot), strike rate (pct_tot), per-zone (rv_11…rv_19), pitches | **OK (workaround)** | embedded `data=[…]` JSON on `/catcher_framing?year=` page; the clean CSV path silently ignores year |
| **Savant — Catcher poptime** | pop 2B/3B, exchange, max-eff arm, CS/SB counts | **OK** | `/leaderboard/poptime?year=` |
| **Savant — Arm strength** | per-position arm (mph), max, overall, throw counts | **OK** | `/leaderboard/arm-strength?type=player&year=` (param is **`year`**, not `season`) |
| **Savant — Fielding Run Value (unified)** | FRV | partial | dedicated FRV CSV path 404/HTML; IF leaderboard already carries `fielding_runs_prevented`; revisit for OF/C unified FRV |
| **MLB Stats API** | innings/games-started/PO/A/E/DP **by position**, every level (MLB + MiLB) | **OK** | `/people/{id}/stats?group=fielding&season=&sportId=` (1=MLB, 11=AAA, 12=AA, 13=A+, 14=A) |
| **BRef team fielding** | team-level | **FLAKY** | `team_fielding_bref` scrape currently breaks (`NoneType.find`); not core |

**Two year-param traps caught** (same family as the Steamer "season ignored" trap): arm-strength ignores `season=` → use `year=`; catcher-framing CSV ignores year entirely → must parse the page JSON.

**Implication for the program (CORRECTED):** Defense+ has the **full public suite** at MLB level — FG (UZR/DRS/Def + components, Inn-by-position) *and* Savant (OAA, arm strength, framing, pop time). The Part 2 latent-talent model gets genuinely multiple indicators. MiLB defense = innings-by-position + counting proxies from statsapi (no tracking), exactly as the prompt assumed. Only the legacy FG scrape (pybaseball.fielding_stats) is blocked — use the modern JSON API instead.

## 2. Year-to-year reliability (t → t+1, 2021–2025, qualified both years)

| Metric | Pos | n pairs | **r (yoy)** | low-sample r | high-sample r |
|---|---|--:|--:|--:|--:|
| Arm strength | SS | 118 | **0.84** | 0.85 | 0.83 |
| Arm strength | RF | 88 | **0.86** | 0.84 | 0.88 |
| Arm strength | 3B | 122 | **0.84** | 0.84 | 0.83 |
| Arm strength | CF | 138 | **0.76** | 0.66 | 0.84 |
| Arm strength | 2B | 109 | **0.74** | 0.77 | 0.71 |
| Arm strength | 1B | 103 | **0.72** | 0.62 | 0.82 |
| Pop time | C | 247 | **0.74** | 0.69 | 0.79 |
| Framing RV | C | 177 | **0.62** | 0.59 | 0.63 |
| OAA | LF | 63 | 0.57 | – | – |
| OAA | 2B | 106 | 0.52 | – | – |
| OAA | 3B | 94 | 0.48 | – | – |
| OAA | CF | 95 | 0.48 | – | – |
| OAA | SS | 99 | 0.42 | – | – |
| OAA | RF | 61 | 0.35 | – | – |
| OAA | 1B | 74 | 0.32 | – | – |
| FRP | (≈OAA, all pos) | – | 0.33–0.58 | – | – |

(arm position codes 3–10 = 1B,2B,3B,SS,LF,CF,RF,util)

### Reads
1. **Tools > outcomes.** Directly-measured physical tools — arm strength (r .72–.86), pop time (.74) — are the most reliable signals on the board, because they're high-N measurements with little opportunity confounding. These should anchor talent estimation.
2. **Framing is a real, stable skill** (r .62) and rests on thousands of pitches/season — high-volume is why it stabilizes despite being a "soft" skill. Strong candidate for a young-stabilizing talent signal.
3. **Range/OAA is moderate-to-noisy and position-dependent** (r .32–.57). Low-opportunity positions (1B .32, RF .35) are noisiest; up-the-middle and 2B/LF are steadier. This is the opportunity/sample problem the prompt anticipated — OAA needs the most shrinkage and the largest samples.
4. **OAA ≈ FRP** (r tracks within ~.02 everywhere). They are one signal scaled by run value — **do not enter both as independent indicators** in the latent model.

### Honest caveats (what this first cut does NOT yet separate)
- Year-to-year r conflates three things: sample noise + true talent change (aging) + measurement reliability. To isolate pure reliability we need **within-season split-half** (odd/even games or 1st/2nd half via date-windowed pulls) — deferred.
- OAA low/high-sample split is blank: the unified OAA leaderboard CSV has no `attempts` column. Sample-dependence for OAA needs attempts joined from the catch-prob/directional leaderboards or innings from statsapi — the obvious next task, since "how much sample does each metric need" is a core Part 1 question.
- Framing RV is a counting stat (scales with pitches); a backup→starter jump shows as "change." The rate version (pct_tot) is the cleaner talent measure to test next.

## 2b. Metric head-to-head (Module 02 — FG suite, common sample, Inn≥200 both yrs)

Year-to-year r on the **identical** player-position-season sample (so OAA/DRS/UZR/Def are directly comparable):

| Pos | OAA | DRS | UZR | Def |
|---|--:|--:|--:|--:|
| C  | –   | .40 | –   | .62 |
| SS | .41 | .32 | .26 | .44 |
| 2B | .42 | .52 | .30 | .45 |
| 3B | .49 | .61 | .43 | .53 |
| CF | .46 | .45 | .46 | .52 |
| LF | .52 | .39 | .28 | .56 |
| RF | .43 | .38 | .34 | .45 |
| 1B | .33 | .37 | .22 | .47 |

### Reads
1. **No single metric dominates — it's position-dependent.** OAA is best at SS/LF; DRS is best at 3B/2B; they genuinely disagree (Witt 2024: OAA **+15** vs DRS **+2** vs UZR **+3.5**). → strong case for the Part 2 latent-talent model: combine indicators, weight by *position-specific* reliability, don't trust any one metric.
2. **UZR is the noisiest public metric** (r .22–.46) — de-emphasize.
3. **OAA and DRS are complementary, not redundant** (they disagree and have different position reliability — DRS carries arm/GDP/good-play components OAA lacks). Real multiple indicators for the latent model. *(Contrast: OAA≈FRP ARE redundant — don't double-count those.)*
4. **Def's higher r is partly an artifact** — it bundles the positional adjustment, which is ~constant per position and sticky, inflating year-to-year r. Don't read "total Defense" as the most reliable *talent* signal.
5. **Sample-dependence is severe** (low vs high innings, ~½-season median split):
   - OAA 2B .12→.53 · OAA LF .22→.58 · OAA SS .17→.48 · DRS 3B .23→.70 · DRS 2B .15→.63 · DRS LF −.01→.50.
   - Below ~½ season these range metrics are near-worthless; trustworthy only at a full season+. SS/2B/LF most sample-hungry.
   - **Exception: catcher D is NOT innings-hungry** (DRS-C .42→.40 flat) — framing is measured every pitch, so it stabilizes fast. Catchers and range fielders need different shrinkage regimes.

## 2c. Reliability vs Stability decomposition (Module 03)

Date-windowed pulls are blocked (FG & Savant ignore `startdate/enddate/month` for fielding — another silent-param trap), so a literal within-season split-half isn't available. Instead we exploit attenuation-by-exposure: observed `r(n) = ρ_true · n/(n+n0)`. Fitting across innings bins (pooled positions, z-scored within position-year) recovers measurement reliability and true stability **separately**:

| Metric | ρ_true (real y2y talent stability) | n0 (inn to Rel=0.5) | Rel @ full season (~1300 inn) |
|---|--:|--:|--:|
| **OAA** | 0.60 | **269** (fast) | **0.83** |
| **DRS** | **0.76** | 527 | 0.71 |
| **UZR** | ~1.0* | **1539** (barely) | **0.46** |

\*UZR is so noise-dominated that ρ is unidentifiable and the fit hits the bound — read as "almost all UZR year-to-year movement is noise," not literal perfect stability. (Predicted full-season pair-r: OAA .50 / DRS .54 / UZR .46 — matches the Module 02 observed table, a good consistency check.)

### The non-obvious result
- **OAA = fast-stabilizing but changeable.** Reaches usable reliability in ~⅕ of a season (n0≈270 inn) and is 83% signal over a full year — the best *current-season* read. But its *true* talent only persists at ρ=0.60 y2y, so a lot of real OAA movement is genuine change → **project it forward with heavy regression.**
- **DRS = slower but stickier.** Needs ~2× the innings to stabilize (noisier per inning) but its underlying talent is more persistent (ρ=0.76) — because it bundles stable tool/skill components (arm, GDP, error-avoidance) that OAA omits. → **lean on DRS components for the persistent / multi-year / aging backbone.**
- **UZR = mostly noise** (46% signal even at a full season). Quantified case to **de-weight or drop UZR** in the latent model.
- **Design takeaway:** OAA and DRS are not interchangeable on the time axis — combine them by *role*: OAA for the current-season point estimate, DRS's sticky components for the projection/career spine. ρ_OAA=0.60 also sets a hard ceiling for Part 4: defensive aging curves will be noisy and sample-hungry.

### Caveats
- Innings is a proxy for true exposure (attempts); absolute n0 blends position-specific opportunity rates (catchers stabilize faster, SS/2B slower — see 2b split). The ordering OAA<DRS<UZR sample-hunger is robust.
- One-parameter reliability form `n/(n+n0)`; exposure = min(Inn) of the pair. A direct attempts-based split-half on raw Statcast would refine n0 but needs the proprietary catch-prob model.

## 3. Files
- `pipeline/00_reachability_probe.py`, `reports/00_reachability.csv`
- `pipeline/01_reliability.py`, `reports/01_reliability.csv` — Savant-only (arm/framing/poptime + OAA)
- `pipeline/02_fg_fielding_reliability.py`, `reports/02_metric_reliability.csv` — FG suite, OAA vs DRS vs UZR vs Def
- `pipeline/03_reliability_vs_stability.py`, `reports/03_reliability_vs_stability.csv` — reliability/stability decomposition
- `data/raw/` — cached per-year leaderboards (oaa_if/of, framing, poptime, arm, **fg_field**), 2021–2025

## 4. PART 1 — STATUS: COMPLETE
Public defensive metrics surveyed, reachability resolved (full FG+Savant suite), reliability characterized two ways (position-specific y2y + reliability/stability decomposition). **Verdict for the indicator set going into Part 2 (latent talent):** anchor on tools (arm strength r.72–.86, pop time .74) + framing (.62, fast-stabilizing); use **OAA for current-season range** (fast, 83% signal) and **DRS components for the persistent backbone** (stickier, ρ=.76); **drop/de-weight UZR** (46% signal); never enter OAA and FRP as separate indicators (redundant). Open follow-ups deferred to later parts: attempts-based n0 refinement, position-specific stabilization table, DRS-component decomposition.
