# Trade Machine partner screen gate (registered 2026-10-08, NOT READ)

Status: **registered, not read.** Model id `trade_partner_screen`, rule version
`partner_v1`. Build task W08_1_PARTNER_SCREEN_V1_DARK (dark, behind
`TRADE_PARTNER_SCREEN_LIVE = False`), flip task W08_2_PARTNER_SCREEN_FLIP. At
this commit no partner screen code, slice, payload, glossary entry or frozen
record exists, and no screen output has been computed: no club ranking, no
factor value for a 2027 trade, no hit count and no share. Every rule below was
written before any such number existed, so none of it was chosen after seeing
one.

**The one look is on 2027-08-05** (section 7). The frozen record lives at
`.cache/trade_partner_screen/record/` (section 3).

## 1. Why

Owner answer **W-OQ4 (a) 'Build and register'**, 2026-10-01, recorded in
`_audit_2026-09-09/DECISIONS_FOR_OWNER.md` under 'early answers for the wiring
lanes and deploy': a labelled rule-based screen behind its own flag, plus a
registered read at the 2027 deadline from daily frozen outputs. The plan is
Part 8 section 8.F 'The lanes', P8.6 'Wiring', the W08 row of 'The eight
BUILD items' and the paragraph 'W08, ready to queue once W-OQ4 is answered
(a) or (b)' of `docs/master-plan-2026-09-24-final-pass.md`, and wiring W08 of
`part8/wiring_ideas.md`.

The screen itself is descriptive: a stated rule over numbers the site already
serves, with no claim that it predicts trades. This file registers the one
test of whether it does. The 2026 deadline cannot be scored honestly:
`franchise_export.py` first shipped on 2026-09-23 and `mlb_projections.json`
is gitignored, so the as-of inputs for July 2026 do not exist. The test is
therefore forward only, on the 2027 deadline, from outputs frozen daily before
each trade happens.

## 2. The candidate: the published rule `partner_v1`

### 2.1 What the screen is

For one selected player, the screen lists the 30 clubs. The player's own club
(his club on the as-of date) is shown first, marked as his club, and is never
ranked. The other 29 clubs are the **candidates**, ranked by the rule below.
Every factor is printed beside the ranking for every club: the raw value, its
source, and the factor score the rule uses. The page calls it a screen, never
a rumor board, and prints no verdict word (section 8).

### 2.2 Inputs, all already served

Per club, read from one slim slice of `data/franchise_board.json` and its club
shards (`data/franchise_clubs/<CODE>.json`, club sections `roster`, `outlook`,
`fin`, `farm`, `odds`), written beside the board by W08_1, plus the Club
Ledger's CBT sidecar that the Trade Machine's CBT block (owner answer M27-4,
the M27 form) already reads:

| Factor | Source | Orientation |
|---|---|---|
| Need, hitter at position P (C, 1B, 2B, 3B, SS, LF, CF, RF) | Franchise ROSTER: the HEM+ of the club's starter at P (the `alignment` starter joined to his `lineup` HEM+) and the club's team DEM+ (`team_dem_plus`) | lower is more need |
| Need, designated hitter | Franchise ROSTER: the club's Offense+ (`offense_plus`) | lower is more need |
| Need, starting pitcher | Franchise ROSTER: Rotation+ (`rotation_plus`) | lower is more need |
| Need, relief pitcher | Franchise ROSTER: Bullpen+ (`bullpen_plus`) | lower is more need |
| Contention | from the first 2027 regular-season game on: ODDS `playoff_pct`; before it: OUTLOOK 2027 wins on the frame the OUTLOOK answer serves (the as-of-signings frame of owner answer OUTLOOK (a), Q9_03, when that frame is live; the served frame otherwise) | higher is more contention |
| Tax | the M27 form: the club's tax payroll for the current tax year (the full 2027 season before Opening Day, the prorated 2027 remainder after it) against the threshold, at the club's payor tier, with the player's CBT charge added (`_tmCbtCharge`), priced by the arithmetic of `_tmCbtBill` and `ledger_export.computed_cbt_bill`; the factor value is the marginal tax that charge carries | lower is better |
| Ability to pay in prospects | Franchise FARM: farm surplus (`farm_surplus_mm`) | higher is better |

Per player: his slot (hitter at his primary position, designated hitter,
starting pitcher or relief pitcher, as the Trade Machine classifies him), his
club on the as-of date, and his CBT charge for the tax year above.

The tax factor is never shown or stored as room, space or capacity under a
line. It is printed in the M27 form only: "tax payroll $X to $Y; threshold $T;
bracket: A to B; marginal tax $M; payor tier K". No cell is a cap-space cell
(the Ledger NEVER list, `ledger_export.py` module docstring, 'A colour on a
salary, a club surplus total or a cap-space cell').

### 2.3 The scoring

1. **Factor score.** For each factor, rank the 29 candidates from best to
   worst in the factor's orientation, ties taking the average rank, and set
   the factor score to (29 - rank) / 28, so the best candidate scores 1 and
   the worst 0.
2. **Need for a fielder** at C, 1B, 2B, 3B, SS, LF, CF or RF is the mean of
   two factor scores: the starter's HEM+ at P and team DEM+. Need for a
   designated hitter, a starter or a reliever is the one factor score in the
   table.
3. **Missing input.** A club with no value for a factor takes 0.5 on that
   factor; its cell prints a dash and the words "not on file", and the day's
   record logs it.
4. **Score** = Need + Contention + Tax + Ability to pay, equal weights, from 0
   to 4.
5. **Order.** Candidates sort by Score, highest first; ties break on Need,
   then Contention, then Ability to pay, then the club code in alphabetical
   order. The **top five** are the first five candidates in that order.

No weight, cut or orientation in 2.2 or 2.3 was fitted to, tuned on or checked
against any real trade, of any season. The weights are equal by construction.

### 2.4 The org trade profile (after M8-3)

The org trade profile (farm Tendencies, owner answer M8-3, 'Feed + inferred
moves with an A->B->A round-trip filter') is not in `partner_v1`. When M8-3
lands, the screen may print it as a visible column with zero weight. It may
enter the Score only as a new rule version (section 3.4).

### 2.5 Players the screen answers for

Every player the Trade Machine prices: MLB assets (Trade Machine item kind
other than `prospect`, scope `mlb`) and prospects (kind `prospect`, scope
`prospect`). A player with no slot (no position and no pitching role on file)
gets no screen output and no record entry.

## 3. The frozen record

### 3.1 What is frozen, and when

From the build date of the flip (W08_2, the first nightly with
`TRADE_PARTNER_SCREEN_LIVE = True`), one entry per as-of date, written by the
nightly pipeline after the Franchise board and the Club Ledger's CBT sidecar
are written. The as-of date is the America/New_York calendar date of the run.
An entry holds:

- a header: `as_of`, `generated_at`, `machine` (`box` or `local`),
  `rule_version` (`partner_v1`), `rule_sha256` (SHA-256 of the rule function's
  source text between its begin and end markers in `assets/trademachine.js`,
  line endings normalised to LF; when the record writer runs a Python twin of
  the rule, that twin's source hash too), `slice_sha256` (SHA-256 of the slim
  slice file's bytes), the contender threshold flag of each club (section
  5.1), and the club factor table: for each of the 30 clubs every raw input of
  section 2.2 and its source key;
- one row per player of section 2.5: player id (MLBAM id where known, else
  the board key), name, scope, slot, club on the as-of date, CBT charge, the
  29 candidates in rule order with each one's four factor scores and Score,
  and the top five.

Recomputing any stored entry from its own stored inputs must reproduce its
rankings byte for byte (the replay test, which W08_1 writes).

### 3.2 Where it lives, and the hash rule

- **Path.** `.cache/trade_partner_screen/record/<YYYY-MM-DD>.json.gz`, one
  file per as-of date, gzip with header mtime 0 so equal content gives equal
  bytes, and the chain index `.cache/trade_partner_screen/record/chain.json`.
  `.cache/` is the source of truth for the reason `proj_export.py` gives for
  the futures ledger: the box's nightly runs `git checkout -- .` before every
  pipeline, so an accruing tracked file under `data/` is reverted every night,
  while `.cache/` escapes the checkout and is on the backup list. While the
  flag is off, the build writes the same files under
  `.cache/trade_partner_screen/preview/`; preview files are never scored.
- **Hash rule.** The day's content hash is the SHA-256 of the canonical bytes
  of the uncompressed entry: `json.dumps(entry, sort_keys=True,
  separators=(",", ":"), ensure_ascii=False).encode("utf-8")`. The chain index
  appends one row per day: `as_of`, `machine`, `rule_version`, `rule_sha256`,
  the content hash, the previous row's `row_hash`, and `row_hash` (SHA-256 of
  the canonical bytes of the row without `row_hash`). Each run also
  re-renders the chain index, hashes only and no ranking, to
  `data/trade_partner_screen_chain.json` (gitignored, published with the
  nightly), so each day's hash is public the morning it is frozen and anyone
  holding an earlier copy can check the chain.
- **First write wins.** A same-day re-run writes nothing. A missed date stays
  missing; no entry is ever written later for an earlier date, and no entry is
  edited or deleted. The box's entries are the record; an entry a local run
  wrote on a date with no box entry is kept and labelled `local`, and the
  scorer reads the box entry when one exists, else the local one, and says
  which.
- **Retention.** Every day file and the chain index are kept, never pruned,
  from the first frozen day until at least 365 days after the look's commit.
  At the look the scorer commits, under `docs/trademachine-2027-08/`, the
  chain index verified end to end and an extract: for every scored unit, its
  player's row from the as-of day's entry, verbatim, with that day's content
  hash.

### 3.3 What may change, and what may not

Inputs move every day; that is what the record freezes. The **rule** may not
change between the first frozen day and the read without a dated
re-registration. The rule is everything in sections 2.2 to 2.5: the factors,
their sources and orientations, the slot mapping, the factor score, the
missing-input value, the weights, the tie breaks, the candidate set and the
top-five cut, and the contender threshold of section 5.1. A change of an
upstream model (HEM+, DEM+, Rotation+, Bullpen+, the season simulator, farm
surplus, the CBT inputs) is an input change, not a rule change; the read lists
every such change that the model registry dates inside the frame.

The record writer refuses to write an entry whose `rule_sha256` differs from
the chain's first `partner_v1` entry unless the entry carries a new
`rule_version` and this file carries a dated amendment naming that version
and its hash.

### 3.4 Re-registration

A new rule version is registered by a dated amendment to this file, committed
before the version's first frozen day, naming the change, the version and its
`rule_sha256`. The pass rule (section 6) reads `partner_v1` entries only,
except that an amendment committed before the 2027 season's first game may
name its version as the scored one in place of `partner_v1`, since no trade in
the frame has happened by then. Entries under any other version are reported
beside the scored ones and never pooled with them.

## 4. The frame

- **The window.** Every trade dated from the officialDate of the 2027 season's
  first regular-season game (gameType R) through the 2027 trade deadline (the
  date MLB publishes), both included.
- **The deals.** The Trade Audit's trade table names the deals: the
  prospects.db `trades` table (source `mlb_api`, one row per tracked player
  moved, its StatsAPI description naming every party) and the league-wide
  StatsAPI transaction log it is built from (typeCode `TR`,
  `.cache/mlb_transactions/tx_2027_MM.json.gz`), so a deal that moves no
  tracked prospect is in the frame too. Deals are grouped as
  `build_site._group_deals` groups them. Every `mlb_api` row of the `trades`
  table in the window must match a `TR` record; any that does not is reported.
- **The unit.** One per traded player per trade: a player moved in the deal
  whose screen output was frozen on the as-of date that is the day before the
  trade's date. His **acquirer** is the club that received him (the `toTeam`
  resolved to its parent club through `trades.canonical_org_from_id`; in a
  deal of three or more clubs, each player's own receiving club). Cash,
  players to be named later until named, waiver claims and releases are not
  units.
- **Scorable.** A unit is scorable when (a) the as-of day has an admissible
  entry (`partner_v1` or the version an amendment named under 3.4, not a
  preview file) and (b) the player's club in that entry is the club that
  traded him. A unit failing either is listed with its reason and counted,
  never scored. No earlier day stands in for a missing day.
- **The scored set** is the scorable units of scope `mlb`. Units of scope
  `prospect` (mostly prospects sent to the selling club, where a screen of
  need and contention is not built to point) are reported in a separate line
  and never enter the test.

## 5. The statistic and the two baselines

### 5.1 The statistic

**The share of real acquirers inside the top five of the frozen screen per
traded player**: over the N scored units, H / N, where a unit is a hit when
its acquirer is among the top five of the player's frozen screen on the as-of
date.

### 5.2 Baseline R: random among the 29 clubs

A uniformly random five of the 29 candidates. Each unit is a hit with
probability 5/29, so under this baseline H follows Binomial(N, 5/29), with
expectation 5N/29. The read reports the exact distribution: the probability
of every count from 0 to N.

### 5.3 Baseline C: contenders-only

A contender is a candidate whose frozen `playoff_pct` on the unit's as-of date
is **at least 0.25**, read from the same entry the screen used. With K_i
contenders among unit i's 29 candidates, the baseline's top five is a
uniformly random five of the contenders when K_i is at least 5, and every
contender plus a uniformly random (5 - K_i) of the other candidates when K_i
is below 5. Its hit probability for unit i is:

- acquirer a contender: 5 / K_i when K_i is at least 5, else 1;
- acquirer not a contender: 0 when K_i is at least 5, else (5 - K_i) / (29 - K_i).

Under this baseline H follows the Poisson-binomial distribution with these
probabilities, computed exactly by convolution, and the read reports it in
full. Since the baseline uses the screen's own frozen odds, beating it
measures what need, tax and ability to pay add beyond contention.

## 6. The pass rule

- **Tests.** For each baseline, the one-sided exact p-value P(H' >= H) where
  H' follows that baseline's distribution (5.2 or 5.3), with no normal
  approximation and no simulation. The two p-values are adjusted by Holm with
  m = 2 at family alpha 0.05: the smaller is compared with 0.025; only if it
  clears, the larger is compared with 0.05.
- **Minimum count.** The read is reported **not resolvable** when N, the
  scored units, is below **30**. It then reports N, H, the share and both
  exact distributions, and no p-value and no outcome. The floor is design
  arithmetic on the random baseline alone, done before any screen output
  existed: at N = 30, a count of 10 or more has probability 0.0246 under
  Binomial(30, 5/29), inside Holm's first step, and a screen whose true hit
  rate were 0.40 would reach it with probability 0.824.
- **Outcomes.** 'clears both baselines', 'clears baseline R only', 'clears
  baseline C only', 'clears neither', or 'not resolvable'. Daily screens of a
  player traded twice and players moved together in one deal are not
  independent draws; the read says so beside the result and adds, as
  description only with no test, the share counted once per (deal, acquirer)
  pair, led by the player with the largest CBT charge.
- **What a result does.** Whatever the outcome, the registry row's verdict
  moves from unvalidated to provisional with the eval artifact linked, and the
  screen stays a descriptive screen. A page may quote the result only from the
  artifact, with its N and the baseline it cleared; no copy says the screen
  predicts trades unless it cleared both baselines, and even then it quotes
  the 2027 numbers and nothing more.

## 7. The one look

- **Date.** **2027-08-05**, after the 2027 deadline. If MLB sets the 2027
  deadline later than 2027-08-02, the look moves to the first date at least
  three days after the deadline. In either case, if the date is a registered
  look date of any `docs/*GATE*.md` (floating looks included, such as
  `docs/BETTING_DUGOUT_GATE.md`'s, if taken that day) or of the orchestrator's
  calendar, the look moves to the next date that is not.
- **Before it.** The scorer (`tools/trade_partner_screen_read.py`, built and
  committed by a later task before 2027-07-01) refuses any date before the
  look and refuses a second run (its one-run sentinel is written when scoring
  begins). It dry-runs the whole reporting path on
  fixtures with nulls before the look. On a date after the deadline and before
  the look that is not a look date, the 2027 transaction months are fetched
  (`tools/backfill_mlb_transactions.py`, March to August 2027) and the files'
  SHA-256 written to the dry-run report; the look reads those files only.
- **The run.** One read. Its stdout and stderr are teed to the output
  directory before anything else runs. A crash before scoring begins is fixed
  and the look runs again that day. A crash after scoring began is reported as
  it stands, never rerun: the scorer stops and writes `OWNER_QUESTION.md`.
- **Output.** `data/trade_partner_screen_eval.json` (N, H, the share, both
  exact distributions, both p-values, the Holm outcome, every unit with its
  reason when unscorable, the scope `prospect` line, the per-deal line, the
  upstream changes of 3.3) and the evidence of 3.2 under
  `docs/trademachine-2027-08/`, in one commit with the registry row update.
- **No early look.** Before the look nobody computes, prints or commits, on
  any page, commit message, report or note, a hit count, a share, an
  acquirer's rank in a frozen screen or any comparison of frozen screens with
  real trades. The page and the record state counts only (days frozen, players
  per day). An early look disqualifies the read: the registry row then reads
  'disqualified, early look' and no result is quoted anywhere.

## 8. Bans

- Nothing is priced, graded or recorded from the screen: no dollar figure, no
  grade or letter, no star, no record, ledger, shadow or paper row of any kind
  is derived from a ranking or a Score.
- The screen never enters a Trade Machine value, its trade verdict, its CBT
  block or any other model's input; no number of the screen feeds eFV,
  surplus, FA fit, betting or Franchise grades.
- No rumor language anywhere the screen appears: never "rumor", "suitor",
  "interested", "in talks", "linked", "frontrunner", "favorite", "likely
  landing spot", "best fit" or "target". No verdict word and no forecast word
  on a factor or a Score.
- No space, room or capacity cell (2.2), no single projected payroll, no club
  surplus total and no colour on a salary (the Ledger NEVER list).
- The rule is never tuned on any real trade (2.3), and no 2026 trade is ever
  scored against it.

## 9. Registry row

`trade_partner_screen` in `data/model_registry.json`, rendered in
`MODEL_REGISTRY.md`: verdict `unvalidated` (the predictive claim has no
measurement yet; the verdict enum has no word for registered, so
`registration_status` carries **'registered, not read'**, as
`postseason_bracket_sim` carries its own), `eval_artifact` null until the look,
and this file named as its gate.

## 10. Read to write this

Read to write this file, and nothing else of the kind:

- the task specification W08_0_PARTNER_SCREEN_READ_REGISTRATION and its
  family preamble;
- `docs/master-plan-2026-09-24-final-pass.md`, the W08 rows of the wiring
  ranking and 'The eight BUILD items' and the paragraph 'W08, ready to queue
  once W-OQ4 is answered (a) or (b)';
- `part8/wiring_ideas.md`, section 3 (the ranked list) and section 4 'W08.
  Trade partner screen in the Trade Machine';
- `_audit_2026-09-09/DECISIONS_FOR_OWNER.md`, the rows W-OQ4, OUTLOOK and
  M8-3;
- the queue entries for W08_1_PARTNER_SCREEN_V1_DARK and
  W08_2_PARTNER_SCREEN_FLIP;
- `docs/betting-2026-10/BRACKET_SIM_GATE.md` as the form of a forward-record
  registration;
- `data/franchise_board.json` (top-level keys, `shards`, `sections_status`,
  the first `board` row) and `data/franchise_clubs/LAD.json` sections
  `roster`, `outlook`, `fin`, `farm` and `odds`, and the `payor_2027` values of
  every club shard, to learn the key paths in 2.2; the values seen are 2026
  values and no 2027 trade exists;
- `data/trade_cbt.json` (keys, rates, brackets, LAD's blocks) and
  `assets/trademachine.js` CBT context (`_tmCbtBill`, `_tmCbtCharge`,
  `_tmCbtLines`), for the M27 form; no partner code exists there at this
  commit;
- `ledger_export.py` (module docstring NEVER list, `computed_cbt_bill`,
  `FORBIDDEN_KEY_FRAGMENTS`), `franchise_export.py` `FORBIDDEN_KEYS`;
- `storage.py` (the `trades` table schema), `build_site._group_deals`,
  `test_trade_audit_basis.py` (docstring), `trades.canonical_org_from_id`;
- `model_registry.py` (`validate`, the verdict enum, `registration_status`
  precedent rows) and `test_model_registry.py`;
- every `docs/*GATE*.md` searched for registered dates in July and August
  2027, and `docs/efv-2026-09-17/FWAR_LABEL_EPOCH_GATE.md` part 9 for the step
  Z entry (2026-10-03).

No trade was related to any club factor, no screen was computed and no 2027
data exists. The only number computed for this file is the binomial design
arithmetic of section 6, from the random baseline alone.
