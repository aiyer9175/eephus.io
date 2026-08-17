// eephus.io - Diamond section configuration. ONE file, one flag.
// Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
//
// THE GATE SWITCH LIVES HERE AND NOWHERE ELSE. Every Diamond module loads
// this script (build_site.DIAMOND_CONFIG_SCRIPT) before its own app, so the
// flag is readable on first paint. No module may keep a second copy of it.
//
// gating: false is the shipped state and the owner decision behind it is
// recorded: the Diamond section launches fully public with "Diamond preview"
// labeling and no paywall. Flipping this to true does NOT by itself create a
// working paywall. The site is static, so a full payload sitting in
// /data/*.json is readable by anyone who opens the network tab no matter what
// this flag says. A real gate needs the members-only slice to arrive over
// Supabase RLS or an edge function. Treat `gating: true` as "show the upsell
// and hide the premium UI", never as "the data is safe".
//
// Module clients do NOT read this object directly (2026-08-16). The one
// consumer is assets/eephus-diamond.js, which wraps the flag in the account
// layer's answer and hands clients EephusDiamond.gated() / previewRows(mod).
// The old advice here showed clients keying off D.isMember, a key this file
// never defined, and three clients copied it; that ghost read is why the
// helper exists.
//
// price_usd_month  - the list price at gate-on. Also what /diamond/ prints.
// founding_rate_usd - the founding cohort rate, held for twelve months.
// preview_rows     - per-module non-member row caps (2026-08-16). Read ONLY
//                    through EephusDiamond.previewRows(mod) in
//                    assets/eephus-diamond.js; no client reads this map raw.
//                    A module absent from the map previews at 25.
window.EEPHUS_DIAMOND = {
  gating: false,
  price_usd_month: 15,
  founding_rate_usd: 9.99,
  preview_rows: { dynasty: 25, redraft: 25, dfs: 25, cards: 40 }
};
