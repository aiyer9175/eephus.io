// eephus.io — front-end Supabase connection.
//
// SETUP: copy this file to `assets/eephus-config.js` and fill in your project's
// values (Supabase dashboard → Settings → API). The real eephus-config.js is
// git-ignored; this .example.js is the committed template.
//
// The anon (public) key is SAFE to ship in the browser — Row-Level Security in
// the migrations, not this key, is what guards your data. NEVER put the
// service-role key here; that lives only in the pipeline's server-side env.
//
// If this config is absent or left blank, the site runs exactly as today
// (logged-out, localStorage watchlist) — the account layer simply stays dormant.
window.EEPHUS_SUPABASE = {
  url:     "",   // e.g. "https://abcd1234.supabase.co"
  anonKey: ""    // the anon / public key
};
