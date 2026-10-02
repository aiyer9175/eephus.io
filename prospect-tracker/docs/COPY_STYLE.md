# Copy style (2026-10-02)

The register for every sentence a reader sees on eephus.io. Source: the sitepass copy lane (LANE_COPY.md section 1),
landed by COPY_0. The lint that enforces it is `tools/copy_lint.py --served`; section 8 says how it runs.

Owner ask, 2026-10-02, verbatim:

> "While you go through the site for all of this, I'd also like you to look to remove any unnecessary flavor text or unnecessary copy. The copy that you feel is essential should be written in my/a human voice and not have any hallmarks of AI/LLM text and should be as condensed and use mathematical/economical/sabermetric language"

## 1. The voice

The owner's own sentences set the register (`DECISIONS_FOR_OWNER.md`, the verbatim lines):

- "Use whichever model wins"
- "Each index's own history, and create+land the prospect arbitration model"
- "Can't we use our own projected arbitration/pre-arbitration salaries?"
- "Let's skip the benchmark for Steamer/ZiPS projections, our projections shouldn't be influenced by other projection systems"
- "embed the video we arent a commercial site, real sports app uses MLB.com embedded highlights and they're commercialized"
- "give credit to the club that actually develops the player, not just the club that signed/acquired them"
- "eFV has to beat consensus, rewrite the driver system and/or scrap it entirely if we can't find a way for it to beat consensus"

What they share: the subject is a model, a metric or a club, named. The verb is a decision or a fact. The reason, when
there is one, is one clause. No hedge, no warm-up, no adjective doing a number's job. 'Our' means the site's own
models. Site copy is this voice made exact: lead with the quantity, assume a numerate reader, let numbers, units,
sample sizes and metric names carry the sentence.

## 2. Density

1. One idea per sentence. Body sentences 25 words or fewer; tooltips 20; mastheads 12 to 20 words as a noun phrase;
   share cards (meta description, og, twitter) 25.
2. A number beats an adjective. 'Safe, likely to be a real contributor' becomes 'Safe: low P(bust), high P(regular+)'
   with the chip's thresholds. With no number, say what is measured, not how good it is.
3. Define once. The Library entry holds the definition, a row's tooltip holds that row's numbers, a column header holds
   the one-line method. No sentence of 12+ words repeats on more than 20 rows of a page.
4. State the claim, the number and the frame: 'Ties PROSPX consensus: Spearman difference -0.0045, CI95 -0.021 to
   +0.011 (n 828)'. Verdict words come from the registry, never from the prose.
5. Mastheads are noun phrases: 'Five-year eWAR paths for every MLB player · surplus over club control'.
6. Loading, empty, unmeasured and failed states use the four sentences of section 6 and nothing else.

## 3. Vocabulary to prefer

- Sabermetric: WAR, eWAR, fWAR, bWAR, wRC+, wOBA, xwOBA, FIP, K%, BB%, ISO, run value, run expectancy, win expectancy
  (WE), WPA, gmLI, Stuff+, plus indexes ('100 = league average, 10 points = 1 SD' where true), park factor,
  replacement level, aging curve, stabilization point, platoon split, times through the order.
- Statistical: Spearman, MAE, Brier, AUC, ECE, CI95, lo95, MDE95 (the resolvable margin), forward-chained, out of sample,
  vintage-matched, bootstrap, shrunk toward, n.
- Economic: surplus, NPV, $/WAR, AAV, guarantee, control years, arbitration step, dead-band, de-vig, implied
  probability, expected value, CLV, ROI, flat unit.
- Plain verbs: predicts, beats, ties, loses, ranks, prices, excludes, ships, retires.

## 4. Banned: the AI hallmarks

| id | pattern | example served on 2026-10-02 | write instead |
|---|---|---|---|
| V1 | over-length sentence or masthead | a 45-word management masthead in one sentence | split it; one idea each |
| V2 | adjective doing a number's job | 'a real good/star ceiling' | 'P(good or better) >= 10%' |
| V3 | hedges ('may', 'might', 'could', 'likely', 'suggests', 'tends to') with no stated probability | 'may be waiting for his pitch' | 'Low in-zone swing rate.' |
| V4 | throat-clearing and meta: 'This page shows', 'Here', 'Below', 'Every number below is' | 'This page labels the elements you'll see on a player card' | 'Labels for the player card, FV chart and farm page.' |
| V5 | marketing and second-person cheer: 'flagship', 'in one place', 'at a glance', 'explore', 'ready to' | 'ready to set your favorites' | 'you return here signed in' |
| V6 | self-certification: 'honest', 'genuinely', 'transparent', 'nothing cherry-picked', 'not mysterious' | 'scored the honest way' | 'scored leakage-free, forward-chained, vintage-matched' |
| V7 | caps emphasis: 'NOT', 'ONLY', 'SAME', 'EVERY', 'WHOLE', 'ACTUALLY' | 'This is the SAME value' | 'Same value as the Star Odds column.' |
| V8 | internal identifiers in reader copy: script and test names, commit hashes, decision ids, docs paths, internal versions | 'v40 composite grade' | the public /data/ URL, or nothing |
| V9 | rhetorical or framing questions | 'Is eFV still calibrated?' | 'Calibration monitor: eFV reliability by bin' |
| V10 | 'check back' empty states; one state worded five ways | 'Check back shortly.' | section 6 |
| V11 | stale state words: 'newly launched', 'coming soon', 'soon', 'while we build', 'renamed from', 'now inside' | 'More analysis soon' | delete |
| V12 | repeated definitions and duplicate sentences | the eFV method sentence on 1,996 rows | define once (section 2, rule 3) |
| V13 | dash rhythm left by the em-dash strip ('a - b - c' asides) and arrow chains in prose | 'Time-travel the board - view rankings ...' | ';', ':', ',' or two sentences |
| V14 | flavor and idiom: 'narrative', 'journey', 'cratered', 'handy', 'panned out', 'overbought', 'sitting on', 'slam dunk' | 'K-rate has cratered (Bryce Rainer-style)' | 'K% has collapsed past the screen's cut' |

The lint's HALLMARK list (rule L6, with the BAN list the older gate already enforces): `ensure(s/d)`, `streamline`,
`empower`, `insight(s)`, `actionable`, `at a glance`, `in one place`, `one-stop`, `go-to`, `deep dive`, `unparalleled`,
`world-class`, `best-in-class`, `state-of-the-art`, `effortless(ly)`, `intuitive(ly)`, `holistic(ally)`, `nuanced`,
`pivotal`, `paramount`, `vital`, `indispensable`, `truly`, `incredibly`, `extremely`, `absolutely`, `literally`,
`remarkably`, `genuinely`, `undeniably`, `needless to say`, `in short`, `in summary`, `at the end of the day`,
`simply put`, `when it comes to`, `a wide range of`, `a variety of`, `a wealth of`, `plays a key role`, `serves as`,
`stands as`, `ever-evolving`, `fast-paced`, `rest assured`, `feel free`, `imagine`, `think of it as`, `journey`,
`landscape`, `ecosystem`, `realm`, `crafted`, `bespoke`, `boasts`, `foster`, `bolster`, `embark`, `coming soon`,
`stay tuned`, `check back`, `honest(ly)`, `dishonest`, `flagship`, `game-changer`, `here's the thing`, `the upshot`,
and `!` at a sentence end.

Advisory, legitimate in context: `curated` (hand-entered data is curated; prefer 'hand-entered'), `leverage` (Leverage
Index), `showcase` (the amateur showcase circuit), `real` (the real conversions a backtest scored), `actually` (once,
in a formula gloss: 'the WE that actually resulted').

## 5. Exceptions: kept verbatim, lint-exempt

Each exception is an entry in `tools/copy_registered.json` with its class.

- LEGAL: the betting disclaimer ('Informational and entertainment only', 'no affiliate links', 'Sports betting is not
  legal in every state', the 1-800-GAMBLER line) and the logo trademark sentence on /sources/.
- CREDIT: the 'Created by' build banner, source attributions and the Swing+ credit to Will Cahoon.
- IMPLIED_ODDS: the implied-odds labels and the 'never graded on a postseason game' label.
- REGISTERED_CLAIM: claim sentences a test pins as claims (`test_claims_freshness.py`, `test_*_claims.py`,
  `test_smoke_prospx_masthead_count.py`, `test_betting_policy_copy.py`, `test_betting_slot_market_policy.py`). The task
  that changes the claim changes the sentence. Pins that fix wording rather than a claim are updated in the same commit
  as the rewrite.
- THIRD_PARTY: scraped scouting excerpts (FanGraphs, MLB Pipeline, Baseball America, ESPN, Just Baseball) and the
  article bodies in `content/articles`.
- LAB_LOG: the registry's per-row `notes`, em-dash rule only, until each row carries a `summary` and the notes move
  behind a collapsed 'Lab log' (SP-Q4, asked; the recommended answer is built).
- FAQ: FAQ headings ('What happens to the free site?') are questions by format.
- FIELD_NAME: field names in backticks (`honest`, `vintage`), player and venue names.
- OWNER_QUOTE: the owner's verbatim sentences, quoted as above.

## 6. State vocabulary: one sentence per state, every module

| state | sentence | replaces |
|---|---|---|
| loading | 'Loading <board>.' | 'Loading&hellip;', 'Loading free-agency data&hellip;', 'Loading venues...' |
| empty | 'No <rows> match these filters.' | 'No players match.', 'No venue matches that filter.' |
| unmeasured | '<Board> not built yet on this deploy; the nightly build writes it.' Off-season: '<Board> returns with 2027 <input>.' | 'Check back shortly.' (15 strings), 'Newly launched' |
| failed | '<Board> did not load. Retry.' Where true, add 'The nightly build may be writing it.' | 'Data failed to load. Refresh to retry;', 'could not be loaded.' |

## 7. Before and after (served copy, owner voice)

| before | after |
|---|---|
| 'Every public FV grade is an educated opinion about the future. eFV is a model trained on resolved outcomes and scored the honest way: leakage-free, forward-chained, on the same players, the same window AND the same vintage as the sources it is measured against.' | 'Public FV grades are scouting opinions. eFV is fit on resolved outcomes and scored leakage-free and forward-chained, on the same players, window and vintage as each source.' |
| 'A threshold invented to make a pick appear is the single most dishonest number this module could publish.' | 'No edge threshold is set to manufacture a pick; a threshold ships only after it clears its gate.' |
| 'League-average runner: the decision is scored as though the manager had a league-average runner, because the runner's speed is a roster fact and crediting a manager for having a fast team is the confound this module exists to avoid.' | 'Scored with a league-average runner: runner speed is a roster fact, not a manager's decision.' |
| 'Time-travel the board - view rankings & grades as they stood at any past snapshot, or diff two dates for a changelog of risers, fallers, new entries & graduates.' | 'The board at any past snapshot, or a diff of two dates: risers, fallers, adds, graduates.' |
| 'Very-young and young+pedigreed prospects are filtered out unless their K-rate has cratered (Bryce Rainer-style).' | 'Excludes very young and young pedigreed prospects unless K% has collapsed past the screen's cut.' |
| 'Probables are not posted for the streamer window yet - check back once lineups firm up.' | 'No probables posted for this window. Off-season: streamers return with 2027 probables.' |
| 'Registered and serving, with no measurement yet. Its gate has not been run, which is not the same thing as a model that is wrong.' | 'Serving, not yet measured. Unmeasured is not wrong.' |
| 'Statcast+ 112 (>= 110, above pool mean) counters the surface dip - tracked-data signal suggests the slump is BABIP / sequencing noise rather than a real decline.' | 'Statcast+ 112 (above pool mean, >= 110): tracked quality holds; the dip reads as BABIP and sequencing.' |
| 'NO SHIP (2026-07-15). Point estimate +0.0092 (0.5274 vs 0.5182, n_gate 711) but lo95 -0.0014 - knife-edge refused per standing discipline.' | 'No ship: +0.0092 Spearman (0.5274 vs 0.5182, n 711), lo95 -0.0014.' |
| 'The correction is not cosmetic: bias FLIPS SIGN, -4.586 on the raw frame to +2.521 ...' | 'Bias flips sign: -4.586 raw, +2.521 on the served frame; MAE 12.019 to 11.577, Spearman 0.117 to 0.150.' |

Already in the voice, the models for the register:

- 'Arb-1 beats its baseline; arb-2+ is a population multiplier because the model did not.' (/arbitration/ masthead)
- 'Display only: no model reads them.' (park factors masthead)
- 'Identity resolution is the binding constraint on this data, not volume.' (/sources/)
- 'Managers bunt with the batters they least want swinging, so E[WE | bunt] is measured over a weaker population than
  E[WE | swing].' (/management/)
- 'No eFV-move section: grade history is stamped at model re-run dates, not the day a grade changed.' (/history/)

## 8. The lint

`python tools/copy_lint.py --served --check` reads sentences, not lines, over what a reader sees: the built pages
(visible text, attributes, share cards), inline and module scripts (string literals through a prose filter), the
Python producers of served copy by AST (`COPY_PRODUCERS`), `data/glossary.json` and the registry's reader fields.

| rule | check | threshold |
|---|---|---|
| L1 | sentence length | over 60 words fails; over 40 is advisory |
| L2 | attribute text (title, aria-label, data-tip) | over 25 words |
| L3 | share card (meta description, og, twitter) | over 25 words |
| L4 | mean sentence length of a surface | over 20 words |
| L5 | the evaluative lexicon (`honest`, `genuine`, `actually`, `very`, `flagship`, `unique` and the rest in the script) | any hit; surface density over 0.10 per 100 words |
| L6 | the HALLMARK list of section 4 plus BAN | any hit; the advisory words are reported, not failed |
| L7 | caps emphasis: `NOT`, `ONLY`, `NEVER`, `EVERY`, `SAME`, `WHOLE`, `ACTUALLY` outside backticks | any |
| L8 | internal identifiers: script and test names, private function calls, docs paths, decision ids, hex of 8+ characters | any |
| L9 | a sentence ending in a question mark, outside FAQ markup and registered text | any |
| L10 | rhythm: two or more spaced-hyphen asides, or two or more arrows, in one sentence | any |
| L11 | repetition: a 12+ word sentence more than 20 times on one rendered page | a render test (COPY_3), not a static rule |
| L12 | stale state words (section 4, V11) | any |
| coverage | a shipped data file a page fetches, with 8+ word strings, written outside `COPY_PRODUCERS` | any |

Ratchet (SP-D6): `tools/copy_baseline.json` holds the findings of 2026-10-02 as sha1 of the normalised sentence (NFKC,
lower case, digit runs to 0) per rule. New copy that breaks a rule fails the gate. A baseline entry that is no longer a
finding fails too, so the task that fixes a sentence removes its entry in the same commit
(`python tools/copy_lint.py --served --write-baseline`, run only after the fix). This document passes its own rules:
`python tools/copy_lint.py --doc docs/COPY_STYLE.md`.
