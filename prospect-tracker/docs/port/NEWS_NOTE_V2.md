# The v2.0 news note (owner P-6 and P-7, 2026-10-22; drafted by PORT_FINAL 2026-10-27)

`/news/` is the MLB News wire: every row is a transaction, grade move or signing from the
event pipeline (`build_site._WIRE_TYPES`), and it has no hand-written row type, so a note
cannot sit dark on it. The site's hand-written surface is `/articles/`, built from
`content/articles/*.md` with no draft state. The note therefore ships as a dated article in
the first bundle of cutover day (PORT_RUNBOOK.md step C-6): copy the block below to
`content/articles/eephus-io-v2.md`, set `date:` to cutover day, rebuild, and the homepage
lead and `/articles/` carry it. Nothing below is served until that copy is made.

Every sentence is descriptive. Every moved number is named by its model, and the reader is
sent to `/models/` and the registry for the figures; no figure is quoted here that an
artifact does not carry.

---

```
---
title: eephus.io v2.0: the live site now runs the current models
author: eephus.io
handle: eephus_io
date: CUTOVER-DATE
summary: The public site now serves the same build as the local pipeline. Every model number moved with it; this note lists which, and where each one's record lives.
---

The public site was a July 2026 build served beside a separate backend. From today it
serves the current build, byte for byte, and every model number on it moved. The version
label reads v2.0, the module beta chips are gone, and the Diamond preview chips stay.

What moved, by model:

- **eFV** (v5 COMBINED, on the fWAR label epoch): every eFV grade and eFV WAR on PROSPX,
  the farm boards and every card.
- **eWAR v3** (FanGraphs' published WAR plus the site's ABS part): the WAR series behind
  every player page, leaderboard, ledger and franchise figure, replacing the bWAR frame the
  old site read.
- **xHEM+, park-matched** (EW3-53): the predictive eWAR batting part now counts its park
  effect once. Provisional. With its park effect counted once, xHEM+ improved next-season
  prediction over FanGraphs' batting in the 2021-2024 test (+0.045, range +0.028 to +0.060).
  A 2027 read decides whether it stays.
- **Trade values, xM$ and Fair $**: the Trade Machine, the Club Ledger roster values and
  the Franchise market surplus; prospects show Fair $ only.
- **MLB projections** and their projection WAR.
- **Consensus grades, DEM+, the plus boards (REM+, HEM+, KRP+, RPS+, Swing+, aStuff+),
  CollegeSavant and the arbitration predictor**: each re-exported from the current code
  and the current data day.
- **New pages**: Arbitration, Awards / HoF, Club Ledger, Franchises, In-Game Management,
  Scores / Standings, Sports Betting and Diamond, Library, Models, Scouting and History.

Where each number's record lives: [/models/](/models/) (Model Accountability, one row per
model with its validation and its last check), [/models/updates/](/models/updates/) (what
changed and when), the registry file `/data/model_registry.json`, and the
[glossary](/glossary/) for every term.

Team codes follow the MLB register (ATH, WSN). The forums and account layer is shipped and
inert.
```
