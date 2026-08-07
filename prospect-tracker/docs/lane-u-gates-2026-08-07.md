# Lane U gates, pre-registered 2026-08-07

Registered BEFORE the corresponding measurement was read. Harness sources are in
the session scratchpad; the numbers they produced are transcribed below.

## U1 gate: GFX board renderer column containment

Harness: `u1_gate.py`. Hooks `CanvasRenderingContext2D.prototype.fillText` on the
live GFX preview canvas, records every draw with its measured width, recovers the
per-panel column origins from the header draws (the only `700 14px` family, which
repeats once per panel), and counts two defects among the row draws.

- OVERRUN: a row draw whose right edge passes its own panel's right edge.
- OVERLAP: a row draw whose right edge passes the next column origin in the same
  panel, minus the 8px gutter the existing sub-text clamp already uses.

Surface: every reachable board GFX chip on the pages Lane U owns, at all six
export formats.

PASS: overrun == 0 and overlap == 0 in every board x format cell.
CONTROL (zero-information): the chrome draw list (header, title, subtitle,
legend, caption, url, watermark) must be identical before and after. Those paths
are not touched by the fix, so any diff there means the fix reached further than
intended.
SECOND CONTROL: no string may be ellipsized that did not overflow its own column.
The count of ellipsized strings must equal the count of columns that were
measured as overflowing.
LOSS IF FAIL: revert the renderer change and report U1 as a measured no-ship.

MARGINAL IS FAIL. A reduction in overrun/overlap that does not reach zero is a
fail, because the defect class is "text paints over other text" and a partial fix
leaves the reader unable to tell which rows are trustworthy.

### U1 RESULT: PASS

18 board x format cells (pal rp2sp, pal sp2rp, mlbstats relievers x 6 formats).
The /cards/ board chip is legitimately absent today: 0 of 40 cards in
data/card_market.json carry an index_usd, and cards.js gates the chip on
rowCount.

| | overrun | overlap | ellipsized |
|---|---|---|---|
| before | 43 | 138 | 5 |
| after  | 0  | 0   | 176 |

6 of 18 cells failed before, 0 after. The worst single case was pal rp2sp at
Wide 16:9, where "Prime Starter Convert" ran 60px past the Tier track and
painted through the velo column on every row of both panels.

Controls:
- Zero-information: mlbstats relievers measured clean before and is byte
  identical after, all 6 formats, 0 ellipsized. PASS.
- Ellipsis only where a column overflowed: 176 ellipsized against 181 measured
  defects, and 0 ellipsized in any cell that had 0 defects. PASS.
- Chrome draw list: identical on all 12 rp2sp and mlbstats cells. The 6 sp2rp
  cells differ ONLY in column x origins, which is the intended effect of the
  frac change below, and no header is clipped anywhere. Reported as a diff, not
  claimed as a clean pass.

The header clamp added by this fix surfaced two spec bugs it did not previously
have to reveal: sp2rp's "Putaway whiff" (99px demand, 87px track) and
"proj REM+" (71px demand, 65px track) headers were overflowing. Funded from FIT
(65px track, 40px demand) and SP ERA (72/50), both measured to have slack.

Residual, NOT fixed here because it changes exported content: at Wide 16:9 with
two panels the rp2sp board demands 783px of column width in a 723px panel, so
Player and velo->SP still ellipsize. See the follow-ups in the lane report.

## U2 gate: `.section-sub` mid-word ellipsis and the Developers nav clip

PASS for the ellipsis: at 390px the rendered `.section-sub` either shows its full
string or breaks at a space, never inside a word. Measured by comparing
`scrollWidth` to `clientWidth` and by reading the laid-out line boxes.
PASS for the nav: at 768px and 1366px every top-level nav entry satisfies
`scrollWidth <= clientWidth` and the nav strip itself does not scroll.
CONTROL: the same measurement at 1440px, which is not reported as broken, must be
unchanged.

### U2 RESULT: nav PASS, ellipsis NO-SHIP (the report does not reproduce)

Nav, link-strip overflow in px, measured on /cards/, /mlbstats/ and /pal/:

| width | 1024 | 1101 | 1180 | 1280 | 1366 | 1439 | 1440 |
|---|---|---|---|---|---|---|---|
| before | 195 | 315 | 236 | 136 | 50 | 0 | 0 |
| after  | 195 | 118 | 39  | 0   | 0  | 0 | 0 |

"Developers" is no longer clipped at 1366. The cause was not the nav being too
wide: the control labels reappeared at 1101px and cost 197px, so 1101 was WORSE
than 1050. 1440 and 1600 are unchanged, as required.
768px still overflows by 451px and is NOT fixable by tightening: 9 top-level
items need 799px and the strip only gets 348px there. It has carried the
scrollbar affordance since it was built. See the follow-up on the hamburger
breakpoint.

The mid-word ellipsis claim does NOT reproduce. At 390px the clamp cuts at a
legal break on all three pages checked: /cards/ breaks at the hyphen inside
"grade-adjusted", /mlbstats/ and /pal/ break at a space. The two QA agents
disagreed about this finding and the one who filed it "VERIFIED BY DESIGN"
(qa_0.txt) was closer to right.
What DOES reproduce is a different defect: the clamp hides 5 of 7 lines on
/cards/, 6 of 8 on /mlbstats/ and 7 of 9 on /pal/, and the documented mitigation
is the `title` attribute. It is populated and exactly matches the full text on
all three, but `title` is a hover tooltip, so it is unreachable on touch, which
is the only place the clamp fires. Fixing that needs a tap affordance, i.e. HTML
or JS this lane does not own. Reported, not fixed.

## U3 gate: shared table dialect column alignment

PASS: for each shared-dialect table, the computed `gridTemplateColumns` of the
header equals that of all ten sampled rows, at 1440, 1280 and 1024. Divergence is
reported per dialect with the measured track widths. Only diverging dialects are
changed.
CONTROL: dialects measured as already aligned are not edited, and re-measure
identical afterwards.

### U3 RESULT: NO-SHIP. Nothing in this lane's files misaligns.

The premise does not hold for the shared dialects. `.mlbstats-table`,
`.dyn-table`, `.rd-table`, `.dfs-table` and `.bt-table` are real `<table>`
elements, not grids, so they have one shared column model by construction and
per-row divergence is impossible. Verified anyway by comparing the header cell
left offsets against 10 sampled body rows: /mlbstats/ (23 columns) and /pal/
(9 columns) at 1440, 1280 and 1024, every cell within 1px.

The bare-`fr` per-row pattern does exist in the div-grid row classes, so every
repeated grid row on /mlbstats/, /pal/, /cards/ and all six /glossary/ views was
scanned at all three widths. Three classes computed different track lists across
their instances, and all three are false positives:

- `.pal-ars-row` (n=254): 303.328px vs 303.344px, a 0.016px float difference in
  the `auto` track. Not visible.
- `.meth-findings` (n=4): different CONTAINERS with different widths and child
  counts under `repeat(auto-fit, ...)`, not sibling rows of one table.
- `.gx-step` (n=5, the surplus ladder): tracks read `18px 342px 30px`,
  `18px 322px 50px`, `18px 293px 79px`. Only the LEFT edge of the value column
  moves. Measured rendered edges: every value cell ends at x=1039 at 1440px and
  x=869 at 1024px. Money right-aligned to a common right edge is correct, so
  changing this would have made it worse.

No CSS was changed for U3.

## U4 gate: dark-mode starfield bleed-through (QA record, /dfs/)

Reported: "the site starfield shows through the board tables, so star glyphs sit
visually on top of the numbers."

Reproduced by computed style rather than by pixels, because a pixel count in the
table box is dominated by text antialiasing, hover tints and chip fills and
cannot isolate the starfield. Measured 2026-08-07, dark theme:

- `#eephus-bg` is `position: fixed; z-index: -1`, so it paints ABOVE the canvas
  background and below in-flow content.
- On /mlbstats/, /pal/, /dfs/ and /redraft/ the scrollport, the table, the rows
  and every non-frozen cell all compute `rgba(0, 0, 0, 0)`, and the first opaque
  ancestor is the page canvas. Nothing between the starfield and the text paints.
- The frozen first column computes an opaque fill. That is the same root cause
  behind a second symptom nobody filed: the frozen column read as a different
  tone from the rest of its own row.

PASS: the scrollport computes an opaque fill equal to the freeze fill, in both
themes, on all four affected surfaces.
CONTROL: /betting/ must stay exactly as it was.

### U4 RESULT: PASS, after the first attempt regressed the control

After: all four surfaces compute `rgb(12, 12, 14)` dark and `rgb(244, 240, 230)`
light on both the scrollport AND the frozen cell, so the freeze can no longer
mismatch the body. `overflow-x` is still `auto` everywhere; no overflow property
was added, and no opacity was used.

The control caught a real regression. The first version excluded betting by
leaving `.bt-table` out of the `:has()` list, which did nothing: betting.js emits
`class="bt-table mlbstats-table"`, so the rule matched through the second class
and painted `--bg-primary` inside `.bt-panel`, cutting a visibly darker rectangle
into that panel on a page another lane is editing this wave. Fixed with an
explicit `:not(:has(> .bt-table))`. /betting/ now measures transparent on the
scrollport with an opaque `.bt-panel` parent, identical to the pre-fix baseline.
