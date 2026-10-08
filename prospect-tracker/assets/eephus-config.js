// eephus.io - front-end Supabase connection (committed-blank stub).
//
// This file ships BLANK on purpose: every page links it, and shipping the
// stub kills the per-page 404 console error the missing file used to log.
// Blank values keep the account layer fully dormant (logged-out,
// localStorage watchlist) - identical behavior to the file being absent.
//
// ENABLE LIVE: fill in your project's values (Supabase dashboard → Settings
// → API) at deploy time. The anon (public) key is safe to ship in the
// browser - Row-Level Security in the migrations, not this key, is what
// guards your data. NEVER put the service-role key here; that lives only in
// the pipeline's server-side env. See assets/eephus-config.example.js and
// supabase/README.md.
window.EEPHUS_SUPABASE = {
  url:     "",   // e.g. "https://abcd1234.supabase.co"
  anonKey: ""    // the anon / public key
};

// Privacy-light analytics (Plausible-compatible; GoatCounter via the extra
// field). Blank = fully inert: eephus-ui.js injects nothing, no cookies, no
// network traffic. ENABLE LIVE: fill in at deploy time, e.g.
//   src: "https://plausible.io/js/script.js", domain: "eephus.io"
window.EEPHUS_ANALYTICS = {
  src:    "",          // the provider's script URL
  domain: "",          // your site domain as registered with the provider
  goatcounter: ""      // GoatCounter endpoint (only if using GoatCounter)
};

// season-state:begin (season_state.py writes this block every night; do not edit)
window.EEPHUS_SEASON = {"phase": "postseason", "season": 2026, "mlb_regular_end": "2026-09-27", "mlb_postseason_end": "2026-10-31", "milb_last_game": "2026-09-20", "next_opening_day": "2027-03-25", "draft_date": "2026-07-12", "j2_open": "2027-01-15", "posting_window": ["2026-11-01", "2026-12-15"]};
// season-state:end
