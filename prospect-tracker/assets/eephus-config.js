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
