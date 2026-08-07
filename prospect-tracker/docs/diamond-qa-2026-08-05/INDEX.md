# Diamond QA record, 2026-08-05 (55 findings)

Copied verbatim 2026-08-07 from the b288db78 session temp scratchpad (the only prior copy,
which lived in OS temp space and was one cleanup away from deletion). This executes the
overdue G1 item from docs/master-plan-2026-08-05-omnibus2.md.

- qa_0.txt: 15 findings (dynasty/redraft), 8 were unfixed at capture
- qa_1.txt: 18 findings (dfs/betting), 5 were unfixed at capture
- qa_2.txt: 22 findings (cards/diamond hub), 7 were unfixed at capture

Total 55 findings, 20 unfixed at capture. Two of the 20 have since RESOLVED (verified
2026-08-07 against current artifacts):

1. Stale callup_watch.fvE vs dynasty efv: 0 of 60 mlbam-joined display mismatches in
   current data/fantasy.json.
2. data/dfs.json missing: now exists AND is git-tracked.

The remaining 18 are scheduled in docs/master-plan-2026-08-07-omnibus3.md (Lane H item H4
and Lane M). Notable still-open items: eephus-gfx.js:228 unclamped board sub-text;
card_market_export.py:500-528 METHOD prose fragments rendered verbatim on /cards/ Method;
per-card GFX ungated on unpriced cards; Method tab missing the gold screen banner; the
My Bets mergeLocalBets orphan (inert until Supabase config; fix with the account-layer
enablement, not before); site.css section-sub mid-word ellipsis at 390px; "Developers"
nav clip at 768/1366.
