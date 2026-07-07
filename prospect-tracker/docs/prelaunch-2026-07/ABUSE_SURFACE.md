# Supabase abuse-surface audit (pre-beta, 2026-07-07)

Scope: the account / forum layer (Supabase Postgres + the client that drives it).
Read in full: supabase/migrations/0001_accounts_forums.sql, 0002_storage_avatars.sql,
0003_moderation.sql, 0004_polls.sql, and the client (assets/eephus-account.js,
assets/eephus-ui.js). Method: enumerate every table's RLS, confirm anon and
cross-user writes are blocked, trace the comment render path for XSS, and check
the client caps / throttle / consent surfaces. Read-only except two trivial
client fixes noted below.

## Verdict

The data layer is in good shape for Beta. RLS is ON for every user-data table,
anon writes are blocked everywhere, and authenticated users can only write their
own rows. The serious anti-abuse controls the 0001 comments say are "deferred"
are in fact IMPLEMENTED in 0003 (ban/suspend, posting + voting rate-limits,
new-account link + downvote karma gates) as SECURITY DEFINER triggers, which are
the authoritative floor under the RLS insert policies. Comment rendering is
XSS-safe by construction (escape-first markdown, scheme-allowlisted links, and
the stored body_html is never rendered - the client re-derives HTML from body_md
at display time).

The residual gaps are moderation completeness (threads cannot be locked, pinned,
or deleted through any policy, and thread creation is not rate-limited) and the
launch-hygiene items (no Terms/Privacy surface; a protocol-relative-link bypass
of the link-gate). None is a data-exposure hole.

## RLS coverage (every table)

| table | RLS on | anon write | cross-user write | notes |
|---|---|---|---|---|
| profiles | yes | denied (no insert policy; created by trigger) | update self only; role/karma pinned by trigger; staff-manage in 0003 | banned_until added in 0003 |
| favorites | yes | denied | owner only | public read |
| watchlist | yes | denied | owner only (also owner-only read) | private |
| badges | yes | denied (seed only) | n/a | public read |
| user_badges | yes | denied | staff grant/revoke only | public read |
| boards | yes | denied (seed only) | n/a | public read |
| threads | yes | denied | insert self-as-creator only | NO update/delete policy (see F1) |
| comments | yes | denied | insert/edit/delete self (or staff) | body_md capped 1..8000; 0003 guard = ban+rate+link gate |
| votes | yes | denied | owner only; no self-vote (trigger) | 0003 guard = ban+rate+downvote gate |
| mentions | yes | denied | insert only on own comment | public read |
| notifications | yes | denied (no insert policy; trigger/service only) | read/update own only | clients cannot fabricate |
| notification_prefs | yes | denied | owner only | - |
| reports | yes | denied | insert self-as-reporter; staff read/update | unique(comment,reporter) bounds spam |
| follows | yes | denied | owner only; no self-follow (check) | public read |
| storage.objects (avatars) | yes (0002) | denied | upload/replace/delete own folder only | public read; size/MIME set on bucket (owner, dashboard) |
| poll_votes (0004) | yes | denied | owner only | public read |

Every `create table` is paired with `enable row level security`; every write
policy keys on `auth.uid() = <owner column>`, so anon (auth.uid() IS NULL) is
denied by construction. No table was found without RLS.

## Findings

| # | area | finding | severity | effort | disposition |
|---|---|---|---|---|---|
| F1 | threads moderation | no UPDATE/DELETE policy on `threads`: staff cannot pin/lock/delete, authors cannot delete their own thread, AND `locked` is never checked on comment insert (locking is decorative). Thread creation has no rate-limit, so board threads can be flooded and then cannot be removed. | Medium | Low | OWNER-ACTION (proposed SQL below, NOT applied) |
| F2 | link gates | a protocol-relative link `//evil.com` renders as a LIVE external link (safeLink treated it as a site-root path) AND bypasses both the client and the 0003 server link-gate, which only match `https?://`. Defeats the primary new-account spam defense. | Medium | Low | Client half FIXED TODAY; server half OWNER-ACTION (proposed SQL below) |
| F3 | consent | signup modal links no Terms of Service / Privacy note, and no ToS/Privacy pages exist anywhere on the site. Public UGC + accounts at launch normally need both. | Medium | Medium | OWNER-ACTION (author the pages, then link) |
| F4 | comment cap | compose + edit textareas had no client length cap while the DB caps body_md at 8000 (a long paste round-trips to a raw check-constraint error). | Low | Trivial | FIXED TODAY (`maxlength="8000"`) |
| F5 | post throttle | no client-side post cooldown; the button disables only during the in-flight request. The authoritative <=6/min floor is enforced server-side in 0003, so this is UX polish, not a hole. | Low | Low | POST-LAUNCH (report only) |
| F6 | body_html trust | the DB stores client-supplied body_html with no server-side sanitization; it is safe ONLY because this client never renders it (display re-derives from body_md via the escape-first renderer). Any future consumer that renders body_html directly would be stored XSS. | Low (latent) | n/a | POST-LAUNCH awareness (keep body_html render-forbidden, or sanitize server-side) |
| F7 | profile fields | avatar_url is free text (rendered only inside an escaped `<img src>`, so no script execution) and bio <=500 (rendered escaped). No live vector today. | Low | n/a | POST-LAUNCH (add a URL/scheme check on avatar_url if ever rendered elsewhere) |
| F8 | rate-limits (misc) | reports / follows / mentions / favorites / poll_votes have no per-minute throttle, but each is bounded by a unique constraint (one report per comment per user, one vote/follow per pair), so blast radius is small. | Low | Low | POST-LAUNCH (add a guard only if abuse appears) |
| F9 | sybil karma | karma is votes-received; alt accounts can upvote a user's own comments (self-vote is blocked, sockpuppets are not). Inherent to email-only signup with no social vouching; the link/downvote karma gates raise the cost. | Low | High | OWNER-AWARENESS (accepted for Beta) |

### Positive findings (verified, no action)

- RLS on every table; anon and cross-user writes blocked (table above).
- 0003 moderation floor is real and authoritative: `banned_until` + `eph_is_banned`
  checks, comments <=6/min, votes <=20/min, link gate (<5 karma -> no URLs),
  downvote gate (<10 karma), and a staff-manages-profiles policy for bans/roles.
- XSS: `renderMarkdownSafe` escapes ALL text first (esc: & < > " '), applies
  markdown on the escaped string, routes every link through `safeLink` (rejects
  javascript:/data:/mailto:), and the mask/embed placeholders are inert. Verified
  no code path renders the stored body_html.
- notifications insert is locked (no client insert policy); clients cannot
  fabricate reply/mention/fv_change/badge notifications.
- Avatars (0002) and poll_votes (0004) are owner-scoped with public read.

## Fixed today (code-side, client only)

Both in assets/eephus-ui.js, both trivial and non-breaking:

1. F4 - added `maxlength="8000"` to the comment compose textarea and the inline
   edit textarea, matching the DB `body_md` check (1..8000): instant UX, no wasted
   round-trip into a raw constraint error.
2. F2 (client half) - `safeLink` now rejects protocol-relative `//host` via a
   `^/(?!/)` lookahead, so a `[text](//evil.com)` no longer renders as a live
   external link. Verified: `/prospx/...` and `/` still pass; `//evil.com`,
   `///a`, `javascript:`, `data:`, `mailto:` all reject.

## Owner-action SQL (PROPOSED, NOT APPLIED - review before running)

Deliberately NOT dropped into supabase/migrations/ as a runnable file: a file
there is auto-applied by the next `supabase db push`, and these want owner review
first. Lift into `supabase/migrations/0005_thread_moderation.sql` when approved.
Do NOT modify 0001-0004.

```sql
-- 0005_thread_moderation.sql (PROPOSED - review before applying)
begin;

-- F1: let authors delete their own thread and staff pin/lock/delete + edit.
create policy "author deletes own thread" on threads for delete
  using (auth.uid() = created_by);
create policy "staff manages threads" on threads for update
  using (is_staff()) with check (is_staff());
create policy "staff deletes threads" on threads for delete
  using (is_staff());

-- F1: make `locked` actually stop comments (it is currently decorative). Extend
-- the 0003 comment guard rather than add a second trigger. Also closes F2's
-- server half by widening the link pattern to protocol-relative + bare-domain.
create or replace function guard_comment_insert()
returns trigger language plpgsql security definer set search_path = public as $$
declare recent int; is_locked boolean;
begin
  if eph_is_banned(new.author_id) then
    raise exception 'account is suspended';
  end if;
  select locked into is_locked from threads where id = new.thread_id;
  if coalesce(is_locked, false) then
    raise exception 'thread is locked';
  end if;
  select count(*) into recent from comments
    where author_id = new.author_id and created_at > now() - interval '1 minute';
  if recent >= 6 then
    raise exception 'posting too fast - wait a moment';
  end if;
  -- widened: catch https?://, protocol-relative //host, and bare www. domains
  if eph_karma(new.author_id) < 5
     and new.body_md ~* '(https?://|//[a-z0-9]|\mwww\.[a-z0-9])' then
    raise exception 'new accounts cannot post links until 5 karma';
  end if;
  return new;
end $$;

-- F1: rate-limit thread creation (mirror the comment cap; board-thread flooding).
create or replace function guard_thread_insert()
returns trigger language plpgsql security definer set search_path = public as $$
declare recent int;
begin
  if eph_is_banned(new.created_by) then
    raise exception 'account is suspended';
  end if;
  select count(*) into recent from threads
    where created_by = new.created_by and created_at > now() - interval '10 minutes';
  if recent >= 5 then
    raise exception 'creating threads too fast - wait a moment';
  end if;
  return new;
end $$;
drop trigger if exists trg_guard_thread on threads;
create trigger trg_guard_thread before insert on threads
  for each row execute function guard_thread_insert();

commit;
```

## Owner-action, non-SQL

- F3: author a Terms of Service + Privacy Policy page (build_site static routes,
  e.g. /terms/ + /privacy/), then add a one-line consent note + links under the
  signup submit button in assets/eephus-ui.js (`authBodyHTML`). Not code-cheap
  because the legal content must exist first.
- 0002 note: confirm the avatars bucket has the file-size (<=2MB) + MIME
  (png/jpeg/webp) limits set in the Supabase dashboard; the migration comment
  says they are set there, not in SQL.
