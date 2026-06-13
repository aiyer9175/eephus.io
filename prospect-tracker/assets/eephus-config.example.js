// eephus.io - front-end Supabase connection.
//
// SETUP: copy this file to `assets/eephus-config.js` and fill in your project's
// values (Supabase dashboard → Settings → API). The real eephus-config.js is
// git-ignored; this .example.js is the committed template.
//
// The anon (public) key is SAFE to ship in the browser - Row-Level Security in
// the migrations, not this key, is what guards your data. NEVER put the
// service-role key here; that lives only in the pipeline's server-side env.
//
// If this config is absent or left blank, the site runs exactly as today
// (logged-out, localStorage watchlist) - the account layer simply stays dormant.
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
