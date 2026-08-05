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
// Consumers read it defensively, because a module page must still render if
// this file is missing:
//     var D = (window.EEPHUS_DIAMOND || {});
//     if (D.gating && !isMember) { renderPreviewSlice(); }
//
// price_usd_month  - the list price at gate-on. Also what /diamond/ prints.
// founding_rate_usd - the founding cohort rate, held for twelve months.
window.EEPHUS_DIAMOND = {
  gating: false,
  price_usd_month: 15,
  founding_rate_usd: 9.99
};
