# EXECUTION 2026-08-04: the eight owner asks

Plan: `docs/master-plan-2026-08-03-eight-asks.md` (written 2026-08-03 from a 10-lane
read-only recon). This is the execution record. Numbers here are the acceptance record: if
a later run disagrees, something regressed.

Session opened by pushing the 23 pending commits (`7626fd0..5325440`), so `origin/main`
was clean before any new work landed.

---

## Owner decision taken during execution

**Hero cards keep their photos; photos come off the LISTS only.** The plan had flagged
this as an open question (plan Lane A2). The owner ruled: "the single-player hero cards
should keep their photos, I just want photos-off for the lists." Lane A was scoped to
exactly that.

---

## Lane A: generateGFX overhaul (commit 406ac05, plus cce3f23)

The owner's ask had four parts: remove player pictures, spend the space on the cramping,
stop the name truncation, and stop using the wrong font.

**Photos off the lists, kept on the cards.** `buildProspectCard`, `buildCompareCard`,
`_gfxMiniCard` and the legacy farm row renderer are untouched, as is the `photos` toggle
that feeds them. The toggle is relabelled "card photos" and now only appears on card
modes, because on a list it would be a control that silently does nothing.

**ROWS (the default board).** Dropping the 30px headshot and its 6px gutter hands 36px per
row straight to the name field, which is where the truncation came from. Measured by
running the shipped geometry functions under node, wide 16:9 at n=100:

| | before | after |
|---|---|---|
| grid | 6x17 | 4x25 |
| column width | 243px | 371px |
| name field | ~140px | ~275px |
| name size | 12.5px | 13px |
| meta size | 9px | 11px |
| empty cells | 2 | 0 |
| vertical fill | - | 97.8% |

The name step went UP even though the rows got denser, and the meta line rose 9px -> 11px,
closing the one place the board still broke the "nothing under 11px" floor the chip work
set. At a 600px-wide timeline render, 9px is 3.4px on screen.

**TILES (was "Chips").** This layout existed to showcase the headshot and its column search
literally maximised photo area. Rebuilt text-first: the search now maximises the NAME
budget, and with the photo well gone the vertical budget buys TWO LINES of name. That is
the actual fix for "missing spaces for prospect names" - the old chip ellipsised past
roughly 14 characters, so hyphenated and double surnames lost their second half on every
board. Names wrap now instead of truncating.

**Everything else in the same complaint family:**

- Card names had no ellipsis, no `min-width:0` and no step-down at 44/40/22/18px, so a long
  name wrapped and shoved the card body down. On the compare card it also broke the three
  columns out of alignment, because each is an independent flex column. Names step down to
  fit (`_gfxFitNamePx`) and the compare name sits in a fixed-height box, so the FV badge row
  is pinned across all three columns.
- **Three SVG helpers carried three DIFFERENT literal font stacks**, so one card could
  render its radar labels, overlay labels and axis labels in three different faces. This is
  the concrete "not using our preferred font" defect. html2canvas serializes inline SVG
  standalone where `var()` cannot resolve, so literals are necessary; there is now ONE,
  mirroring `--font-retro-mono` rung for rung.
- The webfont link pulled SIX families. Five (Inter, JetBrains Mono, Source Serif 4, VT323,
  Press Start 2P) appear in no `font-family` stack anywhere in the tree, verified by grep,
  and were racing `document.fonts.ready` before every capture for nothing.
- `fonts.ready` resolves for faces the document already decided it needs, and every face
  here is `font-display:swap`, so a cold first export could rasterise the fallback. The
  exact weights are now explicitly loaded before capture.
- The asset preloader only scanned INLINE `background-image` - correct for today's markup,
  silently wrong for any future class-based background.
- A board that does not fit its format extended past it in silence, so "Wide 16:9" could
  return a 16:9.4 PNG. The footer now discloses it.
- The card-pack sheet returned a hardcoded width of 1080 while styling itself to the
  selected format's width.
- Renderers handed a raw un-normalized row drew blank cells and threw nothing (escapeHtml
  returns "" for null). That is how the chip board shipped as a grid of logos on
  2026-08-03. It warns now.
- Tile height budget was itemised against the markup after a first pass under-reserved the
  meta line by 4px and forgot the 2px border - a 6px under-reserve that would have clipped
  on a tight canvas, i.e. the exact failure the rewrite exists to remove.
- Default count opens at 100 rather than 50, matching how the row board is actually used.

**cce3f23 - the OTHER GFX engine never waited for its font.** The site has two: the
DOM/html2canvas one in prospx, and the canvas-native `assets/eephus-gfx.js` that draws the
FA, Projections, MLB Stats and news boards. Canvas text does not wait on webfonts:
`g.font = "700 26px DotGothic16"` silently draws in the next family if the face has not
loaded, and every face is `font-display:swap`. So the FIRST graphic of a session could
rasterise in a different typeface than every later one. Now loads the exact weights once
per session, memoised, failures resolving rather than rejecting, raced against a 4s
timeout.

**Verification.** Extracted the shipped functions and ran them under node: the geometry
acceptance matrix (7 formats x n in 10/25/50/100) passes for both layouts on every check
(no name under 12px, no ragged column, name field >= 140px, tile cell >= its own text
budget); and the rendered HTML for both layouts carries no headshot URL and no photo
background layer while keeping every name. Full inline script syntax-checked with node.

---

## Lane E0: the eFV disagreement instrument, and a delta that pointed at a retired grade (commit 4eecb44)

The owner asked to get eFV "even closer on the biggest disagreements". There was no
committed answer to *where* those are on the live board: the resolved cohort publishes its
biggest movers, but `run_live` only ever emitted a mean and a max, so every discussion
started by rebuilding the list by hand. `run_live` now emits a ranked block, top 25 each
direction, with consensus, eFV, predicted WAR6 and surplus per row. Display only.

Building it surfaced a real doc-drift bug. The two delta fields now mean the OPPOSITE of
what the export comment says. That comment was itself "corrected" on 2026-07-23 to read:
*the realized delta does not track the displayed headline, the headline's delta is the
quantile one.* True then. Then 2026-07-25 flipped `BOARD_GRADE_FIELD` to `xfv_grade` and
retired the quantile map as the served grade, and the note was never revisited. So today:

- `xfv_minus_consensus` = `xfv_grade` minus consensus = **what the site actually shows**
- `xfv_minus_consensus_quantile` = a grade the site stopped serving in July

Anyone reading the comment to find "the headline's delta" was sent to the retired field.
The size of the gap is why this matters, measured on the 2026-08-03 live board:

| basis | mean abs delta | rows >= 5 FV apart |
|---|---|---|
| served (`xfv_minus_consensus`) | **12.47** | **1,597 of 2,015** |
| retired quantile | 0.56 | 18 of 2,015 |

A quantile remap onto the consensus distribution reproduces consensus almost by
construction, so quoting those numbers would say the model barely disagrees with the
industry, which is the reverse of the truth. The new block therefore names its bases
`board` and `legacy_quantile` rather than inheriting the misleading field names.

---

## Identity: `bind_player_ids` guarded the key and let the id be stolen (commit 1169ebf)

Found by the draft-id-seeding lane, fixed at source. A binding is a pair and only one half
was guarded. The docstring promises it skips a key already bound to a different id; that
half worked. An id already bound to a DIFFERENT key was repointed without a word, because
the key-side guard passes for an unseen key and then

    ON CONFLICT(mlbam_id) DO UPDATE SET
      player_key = COALESCE(excluded.player_key, player_photos.player_key)

overwrites the owner - `excluded.player_key` is never null on this path, so the COALESCE
could only ever choose the incoming key. It reads like a defensive merge and behaves like
an unconditional overwrite.

Live example: MLBAM 814385 belongs to `jackson_natili`; the draft feed spells the same pick
`jack_natili`; an unguarded harvest MOVED the id onto the draft slug. Since `player_photos`
is the canonical durable id-to-key table and the export's last-resort id source, that
propagates.

Guarded in both directions and deliberately twice: python skips an id owned by another key
so the skip is observable, and the SQL `DO UPDATE` only fires where `player_key IS NULL` so
a future caller that forgets the python guard still cannot corrupt a binding. Verified by
replaying both statements against a scratch table. Also covers the caller at
`run_monthly.py:2120`, which had the same exposure.

---

## Correction to standing memory: the NPB parser red is NOT red

Memory and the recon both carried "test_overseas_stats NPB failure is PRE-EXISTING /
still RED". Verified by actually running it: `python -m unittest test_overseas_stats`
returns **10/10 OK**, and `scrape_fg_player_stats` returns its 3 NPB rows from the cached
page. The recon's claim was static inference from a cache mtime, not a run. No parser fix
was needed and none was fabricated; the hardening half (making a zero-row parse loud
rather than silent) is the part still worth doing.

---

*(Lane results for the trade machine, homepage, mlbstats, pages, prospx consistency, eWAR,
the eFV gates and the FA/projection gates are appended below as they land.)*
