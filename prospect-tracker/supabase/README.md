# eephus.io accounts + forums — Supabase setup

This directory holds the backend for user accounts, profiles, favorites, the
account watchlist, forums/comments, notifications, and moderation. The rest of
the site stays **static** (HTML/JS/JSON on a CDN); the browser talks to Supabase
directly and **Row-Level Security** — not the public key — enforces access.

> **Auth method:** first-party email sign-up only — email + password,
> Supabase-managed passwords/sessions (*not* hand-rolled). **No social OAuth of
> any kind** (no Sign in with X, no Sign in with Google) — this is an intentional,
> permanent product guardrail, not a cost decision. The only third-party identity
> reference anywhere is a *self-entered* X handle on profiles, which is
> display/link-out text — not a login and not an integration. Do not enable any
> OAuth provider in Auth settings.

## One-time provisioning (you, the site owner)

1. **Create a Supabase project** at supabase.com → note the **Project URL** and
   the **anon (public) key** (Settings → API).
2. **Run the migrations** (Supabase SQL editor, in order, or `supabase db push`):
   - `migrations/0001_accounts_forums.sql` — schema, RLS, triggers, seed badges/boards.
   - `migrations/0002_storage_avatars.sql` — the `avatars` storage bucket + policies.
3. **Storage bucket limits** (Storage → `avatars` → settings): max file size
   **2 MB**, allowed MIME `image/png, image/jpeg, image/webp`.
4. **Auth settings** (Authentication → Providers/Settings):
   - Enable **Email** (confirm-email on; password min length ≥ 8).
   - Leave **every OAuth/social provider disabled** — first-party email only is a
     product guardrail (see auth-method note above).
   - Set **Site URL** = `https://eephus.io` and add redirect URLs (incl.
     `http://localhost:8000` for local dev).
   - For production, point Auth → SMTP at a dedicated transactional sender
     (**Resend**) so verification/reset mail and the Part 5 digest share one
     sending reputation; set **SPF/DKIM/DMARC** on `eephus.io`. The built-in
     sender is fine for local/dev only.
5. **Make yourself admin** once you've signed up:
   `update profiles set role = 'admin' where username = '<you>';`
6. **Wire the front-end config** (below).

## Front-end config

The static site reads its Supabase connection from a small config object so no
secret is baked into source control. Create `assets/eephus-config.js`
(git-ignored) from the example:

```js
// assets/eephus-config.js  (DO NOT COMMIT real values)
window.EEPHUS_SUPABASE = {
  url:     "https://YOUR-PROJECT.supabase.co",
  anonKey: "YOUR-ANON-PUBLIC-KEY"   // public anon key is safe client-side; RLS guards data
};
```

`build_site.py` and `prospx/index.html` load the Supabase JS SDK + this config;
if the config is absent the account UI degrades gracefully (the site works
logged-out, exactly as today — the localStorage watchlist keeps functioning).

## Env vars (for the pipeline-side notification job)

The monthly pipeline emits FV-change notifications via the **service role** key
(server-side only — never shipped to the browser):

| Var | Where | Purpose |
|---|---|---|
| `SUPABASE_URL` | CI / local env | project URL for `run_monthly.py` notification step |
| `SUPABASE_SERVICE_ROLE_KEY` | CI secret only | insert `fv_change` notifications for watchlisted prospects |

## Data model (what 0001 creates)

`profiles · favorites · watchlist · badges · user_badges · boards · threads ·
comments · votes · mentions · notifications · notification_prefs · reports ·
follows`, all RLS-protected. Roles: `member / moderator / admin`. Triggers keep
`comments.score` + `profiles.karma` in sync with votes, bump threads on new
comments, fan out reply notifications, block self-votes, and auto-create a
profile on sign-up.

## Privacy / account deletion

Email lives in `auth.users` (never in the public `profiles` table). Deleting an
auth user cascades the profile + owned rows; authored comments keep the thread
intact as **[deleted]** (`author_id ON DELETE SET NULL`). Avatars are deleted
from Storage on account removal.

## Deferred (pending approval — separate migration)

Polls, prediction/accuracy tracking, and user-published → community-consensus
rankings (the larger Part 7 items).
