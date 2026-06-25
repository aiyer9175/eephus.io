# Front-end integration blueprint (Parts 1–7)

How the account/social layer hooks into the existing **static** front-end without
breaking the logged-out experience. The site keeps working with no account; the
account layer is additive and degrades gracefully when `EEPHUS_SUPABASE` is unset.

## Shared client (loaded once)
- Add the Supabase JS SDK (`@supabase/supabase-js` via CDN `<script>`) + load
  `assets/eephus-config.js` in `prospx/index.html` and the `build_site.py`
  editorial templates.
- A small `assets/eephus-account.js` module exposes `EephusAccount`:
  `session()`, `signUp/signIn/signOut`, `profile()`, `onAuthChange(cb)`,
  and data helpers (favorites, watchlist, comments, votes, notifications).
  If config is absent every method is a safe no-op → site behaves exactly as today.

## Part 1 — Auth + account basics
- Nav/sidebar account entry point (on-theme): "Sign in" → modal (email + password,
  magic-link option). When signed in → avatar (circular) + menu (Profile,
  Settings, Sign out).
- Onboarding after first sign-up: prompt for #1 favorite team + #1 favorite
  prospect (writes `favorites` with `is_number_one`). Settings page edits
  username/avatar/favorites/notification prefs + delete account.

## Part 2 — Profiles, favorites, badges, circular avatars
- `/u/[username]` route. On the static editorial site this is a generated shell
  page (`build_site.py` emits `/u/index.html`) that reads `?u=` / path and
  hydrates from Supabase; PROSPX (`#u=username` hash) renders inline.
- `userFlair(profile)` helper → circular avatar + username + #1-team clean logo
  + #1-prospect chip + badges. Used everywhere a user appears (comments, forums,
  nav). **Circular avatars are the only round images; everything else stays
  sharp / rectangular.**

## Part 3 — Watchlist (the lowest-risk first real wiring)
- Today: `watchlistLoad/Has/Toggle` + `FARM_*` read/write `localStorage`.
- Change: make those funcs `async`-aware via an adapter:
  - logged-out → localStorage (unchanged).
  - logged-in → `watchlist` table (cached in memory; star reflects account state).
- On sign-in, if localStorage watchlist is non-empty → **merge prompt** (union
  into account, then clear local). Never silent.
- Favorites (showcase) are separate; favoriting offers "also track on watchlist?".

## Part 4 — Forums / comments
- `EephusComments(scope, entity_key)` web component rendered in a "Forums" tab on
  prospect + farm detail pages (and article pages — Part 7). Fetches/creates the
  canonical thread, lists comments (Top/Recent/Active sort), compose box.
- Markdown: render with `marked` (or `markdown-it`) → **DOMPurify sanitize**
  (allowlist: b/i/em/strong/a/ul/ol/li/blockquote/code/pre/p/br). Store the
  sanitized HTML in `comments.body_html`; re-sanitize on render (defense in depth).
- @mentions: textarea autocomplete against `profiles.username`; on submit, resolve
  to user ids → `mentions` rows → notifications.
- Embeds: a `[[prospect:key]]` / `[[fv:key]]` / `[[scatter:...]]` syntax (and a
  picker button) renders compact, on-theme cards from the existing PROSPX JSON +
  chart builders (`makeBigLineChart`, the GFX card builders). Pasting an internal
  `/prospx/#player=...` link auto-previews.
- Homepage Forums module + `/forums` index: query `threads order by last_activity_at`
  (bump) with a "Hot" toggle (`hot_score`). Shows title, last commenter, count, ts.

## Part 5 — Notifications
- Bell in nav with unread count (`notifications where read=false`). Realtime
  subscription for reply/mention; FV-change rows are inserted by the monthly
  pipeline (service role) after grades update — see runbook env vars.

## Part 6 — Moderation (built alongside Part 4)
- Report button on comments → `reports`. Rate limiting + new-account gates (no
  downvotes/links until karma ≥ N) in `EephusAccount` + a Supabase Edge Function
  fronting inserts. Admin/mod view (`/admin`, role-gated) for reports/users/badges.

## Part 7 — Extras
Build: general boards (schema ready), article comments (same component), follow +
feed, polls, share-to-X (reuses the GFX engine). Report for approval:
community-consensus rankings, prediction/accuracy system (need their own tables).
