# Diamond QA record, 2026-08-05 (55 findings)

Copied verbatim 2026-08-07 from the b288db78 session temp scratchpad (the only prior copy,
which lived in OS temp space and was one cleanup away from deletion). This executes the
overdue G1 item from docs/master-plan-2026-08-05-omnibus2.md.

- qa_0.txt: 15 findings (dynasty/redraft), 8 were unfixed at capture
- qa_1.txt: 18 findings (dfs/betting), 5 were unfixed at capture
- qa_2.txt: 22 findings (cards/diamond hub), 7 were unfixed at capture

Total 55 findings, 20 unfixed at capture. FIVE of the 20 have since RESOLVED and one was
MIS-STATED. All six re-verified 2026-08-07 in a real browser against the current tree.

1. Stale callup_watch.fvE vs dynasty efv: 0 of 60 mlbam-joined display mismatches in
   current data/fantasy.json.
2. data/dfs.json missing: now exists AND is git-tracked.
3. "eephus-gfx.js:228 unclamped board sub-text" was already fixed when this index was
   written, and the index was wrong to carry it. Commit 21d24e6 put the cell `sub`
   through fitTxt() with a limit taken from the next column origin; 22643b1 then
   re-cut that limit against the PANEL edge rather than the canvas edge, because the
   already-clamped sub still crossed its column by 8px in the two-panel split. The
   current renderer clamps the sub and drops it outright when the track has nothing
   left (assets/eephus-gfx.js, the `cell.sub` branch of renderBoard).
4. "site.css section-sub mid-word ellipsis at 390px" DOES NOT REPRODUCE, and the
   characterisation should not be repeated. Measured 2026-08-07 with the pre-fix
   unconditional clamp re-armed, across 7 surfaces (/cards/, /mlbstats/, /pal/,
   /betting/, /models/, /trademachine/, /projections/) x 8 widths (320-640): the
   clamp cut on a space or a hyphen in 56 of 56 cases, never inside a word. The
   /cards/ case that reads like a mid-word cut, "a derived, grade-", is the hyphen in
   "grade-adjusted", which is a legitimate break opportunity.
   The REAL defect at that spot was a different and worse one: the clamp hid 5 of 7
   lines on /cards/ at 390px (6 of 8 on /mlbstats/, 7 of 9 on /pal/), and the run it
   hid on /cards/ was the "Treat this as a screen, not a forecast" disclaimer, while
   the only mitigation was a `title` attribute - a HOVER tooltip, which does not exist
   on a touch device. Fixed 2026-08-07: the clamp now hangs off [data-sub-collapsed]
   and ships with a Read more / Show less control (assets/site.css + eephus-nav.js),
   and with JS off the subtitle renders in full.
5. `"Developers" nav clip at 768/1366` is HALF resolved and the 1366 half should be
   struck. Measured 2026-08-07 on the current nav: the link strip is 799px and fits
   its 904px track at 1440, 1366 and 1280 with 105px to spare; it stops fitting below
   1190px viewport, so 768 does still amputate the tail (it overflows by 420px there).
   The 1366 clip was cured by moving the nav-control label breakpoint to 1440 (see the
   measured comment above `.eephus-nav .eephus-nav-controls` in site.css). The fit is
   now pinned by test_board_card_typography.py::test_nav_link_strip_fits_without_scrolling.
   STILL OPEN AS AN IA DECISION, not a bug to guess at: 641-1189 is a band where the
   strip silently horizontal-scrolls while the hamburger does not take over until 640.
   A thin scrollbar was added for that band; it did not paint a gutter in headless
   Chromium at any width, so whether it is visible needs a check in a real browser
   before anything else is done to it.

The remaining 14 are scheduled in docs/master-plan-2026-08-07-omnibus3.md (Lane H item H4
and Lane M). Notable still-open items: card_market_export.py:500-528 METHOD prose fragments
rendered verbatim on /cards/ Method; per-card GFX ungated on unpriced cards; Method tab
missing the gold screen banner; the My Bets mergeLocalBets orphan (inert until Supabase
config; fix with the account-layer enablement, not before).
