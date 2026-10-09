# Trade partner screen: notes for the flip (W08_2_PARTNER_SCREEN_FLIP)

Prepared by W08_1_PARTNER_SCREEN_V1_DARK on 2026-10-09. Nothing below is
applied at that commit: the glossary has no entry, the registry row is the one
the registration (805290bd) wrote, and `TRADE_PARTNER_SCREEN_LIVE` is False.
The gate is `TRADE_PARTNER_SCREEN_GATE.md` in this folder.

## 1. What W08_1 built (dark)

- `trade_partner_screen.py` (module root): `TRADE_PARTNER_SCREEN_LIVE = False`,
  the one definition of the flag; `build_slice` (the slim slice); the Python
  twin of the rule (`rank_screen`, between the partner_v1 markers);
  `players` (the Trade Machine's priced pools); `build_entry`, `write_day`,
  `replay`, `load_chain` (the frozen record, gate section 3); `run` (the
  nightly entry point).
- `assets/trademachine.js`: `_tmPartnerScreen` and its helpers between
  `// ---- Trade partner screen rule partner_v1 (begin)` and `(end)` (the
  text `rule_sha256` hashes), and the panel (`_tmPartnerHtml`,
  `_tmPaintPartner`), drawn only when the module root carries
  `data-tm-partner="live"`.
- `assets/trademachine.css`: the `.tm-partner*` block.
- `build_site._tm_partner_attr()`: writes `data-tm-partner="live"` on
  `#proj-view-trademachine` only while the flag is True.
- `run_monthly._export_trade_partner_screen(log)`, called by
  `_export_franchise_board` right after the board and its club files are
  written (nightly step 6b7d and the rebuild-only tail), so the slice is
  always beside the board it was cut from and the CBT sidecar of d10e.
- `test_trade_partner_screen.py`.

While the flag is False the nightly writes, under
`.cache/trade_partner_screen/preview/`: `trade_partner_slice.json` (29,455
bytes on the 2026-10-09 inputs), `<YYYY-MM-DD>.json.gz` (about 420 KB a day:
6,162 players, 9.3 MB uncompressed), `chain.json` and its public copy
`trade_partner_screen_chain.json`. Preview files are never scored.

## 2. The flip commit (one commit)

1. `trade_partner_screen.TRADE_PARTNER_SCREEN_LIVE = True`.
2. The served files it then writes: `data/trade_partner_slice.json` (beside
   `data/franchise_board.json`; tracked like the board, or gitignored and
   published, the flip's choice) and `data/trade_partner_screen_chain.json`
   (gitignored and published with the nightly, gate 3.2): add the chain to
   `.gitignore` and both files to `deploy/publish_paths.txt` and the rsync
   list, with a pinning test like `test_franchise_clubs_ship_in_both_deploy_consumers`.
3. The record lives at `.cache/trade_partner_screen/record/`: add it to the
   box's backup list (a deploy step: write it to `docs/DEPLOY_PENDING.md`
   while deploys are deferred). It must never be pruned before 365 days after
   the look (gate 3.2).
4. `run_monthly`: add `"trade_partner_screen"` to `SCHEDULED_EXPORTS` (below
   the rows `test_mgmt_export` pins) and file `_record_ingest` from
   `_export_trade_partner_screen` (True with the player count, False on a
   refusal or a raise). The dark helper files nothing on purpose.
5. Rebuild `/trademachine/` (`python -c "import build_site as B;
   B._write('trademachine/index.html', B.build_trademachine())"`): the shell
   gains `data-tm-partner="live"` and nothing else.
6. Optionally one line in the page's "How this works" list (suggested text:
   "<strong>Partner screen.</strong> For a player on the builder, the 29
   other clubs ordered by a published rule with every factor printed; a
   screen, not a rumor board.").
7. The glossary entry and the registry row update below, by an idempotent
   script that keeps each file's line endings and indent; regenerate
   `MODEL_REGISTRY.md` with `tools/gen_audit_docs.py`.
8. Name in the commit message every new key, file and row count.

The first frozen day is the first nightly after the flip: the record writer
refuses a later rule text under `partner_v1` (gate 3.3), so the JS rule region
and the Python twin must not change after that day without a dated
re-registration in the gate.

## 3. Glossary entry (data/glossary.json), prepared text

```json
{
 "id": "trade_partner_screen",
 "term": "Trade partner screen",
 "category": "site-feature",
 "section": "Value & Contracts",
 "module": ["trademachine"],
 "aliases": ["partner screen", "partner_v1"],
 "priority": 40,
 "definition": "For one player on the Trade Machine builder, the 29 clubs other than his own ordered by a published rule with every factor printed: need at his slot, contention, the marginal tax his CBT charge carries, and farm surplus as the ability to pay in prospects. A screen, not a rumor board: it makes no claim about any trade.",
 "methodology": "Rule partner_v1 (docs/trademachine-2026-10/TRADE_PARTNER_SCREEN_GATE.md): each factor ranks the 29 clubs, ties at their average rank, and scores (29 - rank) / 28; an input not on file scores 0.5. Need is the starter's HEM+ at the position with team DEM+ for a fielder, Offense+ for a designated hitter, Rotation+ for a starter and Bullpen+ for a reliever, lower counting as more need. Contention is Team Outlook's 2027 wins on the served frame before the first regular-season game and playoff odds after. Tax is the marginal tax of the player's CBT charge at the club's payor tier on the Club Ledger's schedule, printed as tax payroll before and after, threshold, bracket and payor tier, never as room under a line. Ability to pay is farm surplus. The Score adds the four with equal weight, 0 to 4. The org trade profile is shown with weight 0. Read from trade_partner_slice.json, a slim slice of the Franchise board and the CBT sidecar; the daily output is frozen and hashed for one registered read after the 2027 deadline.",
 "example": "",
 "formula": "Score = Need + Contention + Tax + Ability to pay, each (29 - rank) / 28",
 "seeAlso": ["trade_machine", "cbt_payroll", "payor_tier", "surplus_value", "farm_report_card"],
 "shelf": "ark",
 "origin": "eephus wiring W08, owner answer W-OQ4 (a), 2026-10-01"
}
```

Check the `category`, `section`, `shelf` and `seeAlso` values against the
glossary's enums and existing ids at flip time (on 2026-10-09 every `seeAlso`
id exists, `site-feature` is a category and `ark` a shelf).

## 4. Registry row update (data/model_registry.json, row trade_partner_screen)

Keep `verdict` `unvalidated`, `registration_status` "registered, not read" and
`eval_artifact` null (gate section 9). Change:

- `surface`: "Trade Machine partner screen (/trademachine/, under the deal
  builder): for a player on the builder, the 29 other clubs ordered by
  partner_v1 with every factor printed; a descriptive screen, never a price, a
  grade or a trade value"
- `notes`: append "FLIP <date>: TRADE_PARTNER_SCREEN_LIVE True; served
  data/trade_partner_slice.json and data/trade_partner_screen_chain.json; the
  first frozen day is <date> (box), rule_sha256 <hash>, rule_py_sha256
  <hash>." Fill the hashes from `trade_partner_screen.rule_sha256()` and
  `rule_py_sha256()` on the flip commit.
- `last_checked`: the flip date.

## 5. Recorded defaults (open owner question)

partner_v1's slot mapping follows the Trade Machine's own position buckets:
C, 1B, 2B, 3B, SS, LF, CF, RF at the position; DH; SP from SP, RHP, LHP, P; RP
from RP, CL, SIRP, MIRP and CP. A primary position of OF, INF or TWP has no
slot, so the player gets no screen output and the record counts him under
`skipped_players.no_slot_by_position` (151 players on the 2026-10-09 inputs:
OF 132, INF 8, INF/OF 1, TWP 7, none 3). The gate's missing-input rule is read
literally: the candidates that carry a value are ranked among themselves and
scored (29 - rank) / 28, and a candidate with no value scores 0.5. Any change
to either must be registered in the gate before the first frozen day.
