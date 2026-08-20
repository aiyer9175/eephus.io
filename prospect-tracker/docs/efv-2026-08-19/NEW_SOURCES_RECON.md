# New-sources recon, V2 lane (2026-08-19)

Report only. No ingestion, no production code this cycle. All probes run 2026-08-19.
Probe routes: WebFetch (live pages; FanGraphs and live BA block Python and BA 403s
WebFetch too), curl against web.archive.org (WebFetch is blocked on web.archive.org
but curl is not; the archive.org availability API works under WebFetch).

## 1. BA deep history (2017-2022 backfill)

### What the DB holds now

`snapshots` source `baseballamerica`: 4,556 rows, 2023-02-15 to 2026-08-10, four
preseason vintages plus 2026 midseason and two Top-100 pulls. 4,456 rows carry
tools_json with `_extras.ba_risk` and `_extras.ba_raw_grade`; the 100-row
2026-06-03 Top 100 is rank-only. Nothing before 2023.

### Probe results

Three archived BA board URLs were pulled and parsed (via curl through Wayback):

1. `web.archive.org/web/20191207102230/.../2019-top-100-prospects/` (contemporaneous
   2019 capture). Tabs 1-25 / 26-50 / 51-75 / 76-100 are a JS `data-start-page`
   selector; only the first 25 rows exist in the DOM. Those 25 carry per-tool grades
   (`Hit: 70 | Power: 70 | Speed: 50 | Defense: 55 | Arm: 55`), ETA, preseason rank,
   and a BA player id in the anchor (`/players/99322/nate-pearson/`). No overall
   grade, no OFP, no risk label anywhere on the page (0 regex hits).
2. `web.archive.org/web/20180513175746/.../2017-top-100-prospects/` (2018 capture).
   Same shape: 25 player links, tool grades in prose form, no overall grade, no risk.
3. `web.archive.org/web/20251106183819/.../2019-top-100-prospects/0/` (MODERN-site
   capture of the historical list, 2025-11-06). This is the important one: the modern
   BA page embeds the FULL list as JSON in the HTML. Parsed: 100 `"rank"` entries,
   100 names, per-player `"mlbId"` (MLBAM id, e.g. 666215), positions, birth dates,
   debut dates. But `"baGrade": null` and `"rankingRisk": null` on ALL 100 entries.
   Confirmed again on the 2022 list (capture 20240305000607): 200 rank entries
   parsed, 0 non-null baGrade, 0 non-null rankingRisk, 133 mlbIds.

CDX enumeration shows yearly Top-100 pages archived back to 1990, and modern-era
(2023+) captures exist for 2017, 2018, 2020, 2022 base URLs (2021 reachable via
query-variant captures). Org boards pre-2023 are DEAD in the archive: every
`.../minors/<year>-<team>-top-10-prospects/` capture 2015-2017 redirects to
`/account/` (login wall was captured, not content).

### Feasibility estimate

- Rows recoverable: ~100/year rank-only Top 100 for 2017-2022 (~600 rows), each with
  a free MLBAM id from the embedded JSON. Plus ~25/year with per-tool grades from
  contemporaneous captures (no overall grade). Org Top 30s: 0 (login-walled at
  capture time; the grades exist only in the print Prospect Handbook).
- FV-equivalent grades pre-2023: NO. BA's own database serves `baGrade: null` and
  `rankingRisk: null` for every pre-2023 vintage. This matches the Luis Hernandez
  dossier precedent (BA rank-only in those eras). No ingest route can recover a
  number BA never published digitally.
- Identity-resolution cost: near zero. The modern embedded JSON carries `mlbId`
  directly; no name-only matching needed for the Top-100 rows.
- What it buys: 6 extra pairwise-overlap years (BA x FG rank overlap 2017-2022,
  ~100 rows/yr against FG's 2017+ history) for rank-based accuracy legs and the
  era-basis map, plus a longer BA rank series for the B-L6 denoised-baseline
  question. It adds NOTHING to consensus FV (no grades), nothing to the risk
  feature (no risk labels), and nothing to the grade-era map before 2023.

### Verdict

Marginal ingest lane, cheap but thin: ~600 rank-only rows with free ids. Worth doing
ONLY if a rank-based scoring leg or B-L6 explicitly needs pre-2023 BA overlap; not
worth it for consensus, grades, or risk. **Binding constraint: BA published no
overall grades or risk labels before 2023, so the pre-2023 record is rank-only at
the source.** Access and identity are solved problems (Wayback modern captures +
embedded mlbId); the data simply does not exist upstream.

## 2. Other boards

**Baseball Prospectus.** BP is the one outlet with a grade type nobody else
publishes: the OFP / Likely dual grade (a mean AND a mode, i.e. second-moment
information the consensus mean discards), standard on their team lists in the
2014-2019 Jason Parks / Jeffrey Paternostro era and still present in current
scouting reports. Access is the problem: the 2026 Top 101
(`baseballprospectus.com/prospects/article/104472/`) truncates at the paywall header
under WebFetch ("Full access to this article is for Baseball Prospectus
subscribers"); the prospects hub lists rankings but serves no rows. The paywall is
server-side, so Wayback captures inherit the truncation. Identity: names only (BP
ids are internal). Era depth on paper 2014+, era depth in practice = whatever a
subscription or a free-window capture exposes. Real grades, blocked access.

**Keith Law / The Athletic.** Rank-only plus prose; Law publishes no numeric
FV/OFP in his Top 100 or org rankings (tool numbers appear occasionally inside
prose). Hard paywall (Athletic/NYT); second-hand partial leaks via team blogs cover
only each fanbase's handful of players. Identity: names only. Era depth: Athletic
2020+, ESPN Insider before that (also paywalled). As a features source this is a
rank column, and the rank frontier is measured CLOSED; not worth identity cost plus
a paywall for ranks.

**ESPN (Kiley McDaniel).** The best target of the three. McDaniel's Top 100 carries
explicit FV tiers per player (65 FV / 60 FV / 55 FV / 50 FV section headers; probe
of the 2026 Top 100 page loaded the FULL list free under WebFetch, no ESPN+ wall).
The DB already holds 252 espn rows (2025-08-20 to 2026-05-22) with fv populated;
the ingest break is `espn_article_probe: HTTP 403` since 2026-08-04, which is the
direct Python fetch being blocked, NOT the content going paywalled: the same
article family fetches clean via WebFetch today. Era depth: McDaniel-era 2020+
(older years under Insider; africa.espn.com mirrors have historically served
Insider pieces free). Identity: names + team + position (no ids), standard alias
cost. Grades: yes, tier-level FV, exactly the consensus feature shape.

### Ranked recommendation

1. **ESPN repair** (not a new source): route the existing espn ingest through a
   WebFetch-class fetch or equivalent header set. Cheapest action, restores a
   grade-bearing source already wired into consensus, unblocks 2026 vintages
   accruing now. This is an ingest_health fix, not a recon lane.
2. **BA rank-only backfill 2017-2022** via Wayback modern captures: ~600 rows,
   free mlbIds, one-off script. Do it only when a rank-based leg (B-L6, era map)
   asks for it by name; file under that lane, not as a standing source.
3. **BP OFP/Likely**: highest information ceiling (second moment), blocked on
   subscription. If the owner ever holds a BP sub, a 2014-2019 team-list OFP
   backfill becomes the only new GRADE history on the market. Until then: no lane.
4. **Law/Athletic**: no. Ranks only, hard paywall, closed rank frontier.

No registry rows needed this cycle; nothing here ships code or data.
