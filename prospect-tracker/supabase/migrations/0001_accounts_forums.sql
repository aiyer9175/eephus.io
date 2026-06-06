-- Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
-- eephus.io — accounts, profiles, favorites, watchlist, badges/roles, forums
-- (threads/comments/votes/mentions), notifications, moderation, follows.
--
-- Target: Supabase Postgres. Auth is handled by Supabase Auth (auth.users);
-- this migration owns the application/user-generated-content layer only.
-- Run via the Supabase SQL editor or `supabase db push`. Idempotent-ish:
-- uses IF NOT EXISTS / CREATE OR REPLACE where practical.
--
-- Security model: Row-Level Security is ON for every user-data table. The
-- anon/public key is safe to embed in the static front-end BECAUSE these
-- policies — not the key — enforce access. Passwords are never stored here;
-- Supabase Auth manages credentials, sessions, and resets.

begin;

create extension if not exists "uuid-ossp";
create extension if not exists "citext";   -- case-insensitive usernames

-- ---------------------------------------------------------------------------
-- Roles enum (admin/moderator/member) — drives badge granting + moderation.
-- ---------------------------------------------------------------------------
do $$ begin
  create type user_role as enum ('member', 'moderator', 'admin');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- profiles — one row per auth user (PK = auth.users.id). Public-readable
-- (it's the social identity); email lives in auth.users, NOT here, so PII
-- stays out of the public table.
-- ---------------------------------------------------------------------------
create table if not exists profiles (
  id            uuid primary key references auth.users(id) on delete cascade,
  username      citext unique not null,
  avatar_url    text,                 -- Supabase Storage URL (circular in UI)
  bio           text check (char_length(bio) <= 500),
  role          user_role not null default 'member',
  karma         integer not null default 0,   -- derived from votes received
  created_at    timestamptz not null default now(),
  constraint username_format check (username ~ '^[A-Za-z0-9_]{3,20}$')
);
alter table profiles enable row level security;
create policy "profiles are public read"   on profiles for select using (true);
create policy "owner updates own profile"   on profiles for update
  using (auth.uid() = id) with check (auth.uid() = id);
-- role/karma are NOT user-editable; updates to them go through SECURITY DEFINER
-- functions / service role only. Enforce via a trigger that rejects client
-- changes to those columns.
create or replace function guard_profile_privileged_cols()
returns trigger language plpgsql as $$
begin
  if auth.uid() = new.id and (new.role is distinct from old.role
       or new.karma is distinct from old.karma) then
    new.role := old.role; new.karma := old.karma;  -- silently pin; only
  end if;                                            -- service role can change
  return new;
end $$;
drop trigger if exists trg_guard_profile on profiles;
create trigger trg_guard_profile before update on profiles
  for each row execute function guard_profile_privileged_cols();

-- Auto-create a profile when a new auth user signs up. Username defaults from
-- email local-part (sanitized + de-duped); the user can edit it in settings.
create or replace function handle_new_user()
returns trigger language plpgsql security definer set search_path = public as $$
declare base text; cand text; n int := 0;
begin
  base := regexp_replace(split_part(coalesce(new.email,'user'), '@', 1), '[^A-Za-z0-9_]', '', 'g');
  base := left(coalesce(nullif(base,''),'user'), 16);
  if char_length(base) < 3 then base := base || 'fan'; end if;
  cand := base;
  while exists (select 1 from profiles where username = cand) loop
    n := n + 1; cand := left(base, 16) || n::text;
  end loop;
  insert into profiles (id, username) values (new.id, cand);
  return new;
end $$;
drop trigger if exists trg_on_auth_user_created on auth.users;
create trigger trg_on_auth_user_created after insert on auth.users
  for each row execute function handle_new_user();

-- ---------------------------------------------------------------------------
-- favorites — curated SHOWCASE subset (prospects + teams), one #1 per kind.
-- entity_key references the static PROSPX JSON by key (no FK to prospect data,
-- which lives outside Postgres).
-- ---------------------------------------------------------------------------
create table if not exists favorites (
  user_id       uuid not null references profiles(id) on delete cascade,
  kind          text not null check (kind in ('prospect','team')),
  entity_key    text not null,           -- player_key or org code
  is_number_one boolean not null default false,
  created_at    timestamptz not null default now(),
  primary key (user_id, kind, entity_key)
);
-- At most one #1 per (user, kind).
create unique index if not exists favorites_one_number_one
  on favorites (user_id, kind) where is_number_one;
alter table favorites enable row level security;
create policy "favorites public read" on favorites for select using (true);
create policy "owner writes favorites" on favorites for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- watchlist — broad TRACKING set (the ☆ star). Private to the owner; feeds
-- FV-change notifications. entity_type prospect|farm mirrors the two existing
-- localStorage watchlists.
-- ---------------------------------------------------------------------------
create table if not exists watchlist (
  user_id     uuid not null references profiles(id) on delete cascade,
  entity_type text not null check (entity_type in ('prospect','farm')),
  entity_key  text not null,
  created_at  timestamptz not null default now(),
  primary key (user_id, entity_type, entity_key)
);
alter table watchlist enable row level security;
create policy "owner reads watchlist"  on watchlist for select using (auth.uid() = user_id);
create policy "owner writes watchlist" on watchlist for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- badges + user_badges. Seeded with Beta Tester. kind: manual (admin grants)
-- or auto (tenure / contribution milestones, awarded by a scheduled job).
-- ---------------------------------------------------------------------------
create table if not exists badges (
  slug        text primary key,
  name        text not null,
  description text not null,
  icon        text,                       -- emoji or asset ref
  kind        text not null default 'manual' check (kind in ('manual','auto')),
  created_at  timestamptz not null default now()
);
create table if not exists user_badges (
  user_id    uuid not null references profiles(id) on delete cascade,
  badge_slug text not null references badges(slug) on delete cascade,
  awarded_at timestamptz not null default now(),
  awarded_by uuid references profiles(id),
  primary key (user_id, badge_slug)
);
alter table badges enable row level security;
alter table user_badges enable row level security;
create policy "badges public read"      on badges      for select using (true);
create policy "user_badges public read" on user_badges for select using (true);
-- Granting is admin/mod only.
create or replace function is_staff() returns boolean language sql stable as $$
  select exists (select 1 from profiles where id = auth.uid() and role in ('admin','moderator'));
$$;
create policy "staff grant badges" on user_badges for insert with check (is_staff());
create policy "staff revoke badges" on user_badges for delete using (is_staff());
insert into badges (slug, name, description, icon, kind) values
  ('beta_tester', 'Beta Tester', 'Joined during the eephus.io alpha/beta.', '🧪', 'manual'),
  ('tenured_1y',  'Charter Member', 'Account active for one year.', '🎖️', 'auto'),
  ('contributor', 'Contributor', 'Earned 100+ karma from community votes.', '✍️', 'auto')
on conflict (slug) do nothing;

-- ---------------------------------------------------------------------------
-- boards (Part 7 general boards) + threads. A thread is attached to an entity
-- (prospect/farm/article) OR a board (trades/draft/team/general). last_activity_at
-- drives the homepage "bump" ordering; comment_count is denormalized for the index.
-- ---------------------------------------------------------------------------
create table if not exists boards (
  slug        text primary key,
  name        text not null,
  description text,
  sort_order  integer not null default 0
);
alter table boards enable row level security;
create policy "boards public read" on boards for select using (true);
insert into boards (slug, name, description, sort_order) values
  ('general','General','Anything baseball-prospects.',0),
  ('trades','Trades','Trade talk + deadline analysis.',1),
  ('draft','Draft','Amateur draft + IFA.',2),
  ('teams','Team Talk','Org-specific discussion.',3)
on conflict (slug) do nothing;

create table if not exists threads (
  id              uuid primary key default uuid_generate_v4(),
  scope           text not null check (scope in ('prospect','farm','article','board')),
  entity_key      text,                 -- player_key / org / article slug (null for board)
  board_slug      text references boards(slug) on delete set null,
  title           text not null check (char_length(title) <= 200),
  created_by      uuid references profiles(id) on delete set null,
  created_at      timestamptz not null default now(),
  last_activity_at timestamptz not null default now(),
  comment_count   integer not null default 0,
  hot_score       double precision not null default 0,   -- votes + recency
  pinned          boolean not null default false,
  locked          boolean not null default false
);
-- One canonical thread per entity (prospect/farm/article) so per-page comments
-- attach to a single thread; board threads are free-form.
create unique index if not exists threads_entity_unique
  on threads (scope, entity_key) where scope in ('prospect','farm','article');
create index if not exists threads_last_activity on threads (last_activity_at desc);
create index if not exists threads_hot on threads (hot_score desc);
alter table threads enable row level security;
create policy "threads public read" on threads for select using (true);
create policy "authed create threads" on threads for insert
  with check (auth.uid() = created_by);

-- ---------------------------------------------------------------------------
-- comments — threaded one level (parent_id null = top-level). body_md is the
-- raw markdown; body_html is the SANITIZED render (sanitization also enforced
-- client-side before display — defense in depth). score is denormalized from
-- votes. Soft-delete keeps thread structure ([deleted]).
-- ---------------------------------------------------------------------------
create table if not exists comments (
  id          uuid primary key default uuid_generate_v4(),
  thread_id   uuid not null references threads(id) on delete cascade,
  parent_id   uuid references comments(id) on delete cascade,
  author_id   uuid references profiles(id) on delete set null,
  body_md     text not null check (char_length(body_md) between 1 and 8000),
  body_html   text not null,
  score       integer not null default 0,
  created_at  timestamptz not null default now(),
  edited_at   timestamptz,
  deleted     boolean not null default false
);
create index if not exists comments_thread on comments (thread_id, created_at);
alter table comments enable row level security;
create policy "comments public read" on comments for select using (true);
-- New-account reputation gate + not-banned check happen in the insert policy.
create policy "authed insert comments" on comments for insert
  with check (auth.uid() = author_id
              and exists (select 1 from profiles p where p.id = auth.uid()));
create policy "author edits own comment" on comments for update
  using (auth.uid() = author_id or is_staff())
  with check (auth.uid() = author_id or is_staff());
create policy "author or staff deletes" on comments for delete
  using (auth.uid() = author_id or is_staff());

-- ---------------------------------------------------------------------------
-- votes — one row per (user, comment); value +1/-1. No self-votes (trigger).
-- Triggers recompute comments.score and the author's karma.
-- ---------------------------------------------------------------------------
create table if not exists votes (
  user_id    uuid not null references profiles(id) on delete cascade,
  comment_id uuid not null references comments(id) on delete cascade,
  value      smallint not null check (value in (-1, 1)),
  created_at timestamptz not null default now(),
  primary key (user_id, comment_id)
);
alter table votes enable row level security;
create policy "votes public read" on votes for select using (true);
create policy "owner writes votes" on votes for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

create or replace function prevent_self_vote()
returns trigger language plpgsql as $$
begin
  if exists (select 1 from comments c where c.id = new.comment_id and c.author_id = new.user_id) then
    raise exception 'cannot vote on your own comment';
  end if;
  return new;
end $$;
drop trigger if exists trg_no_self_vote on votes;
create trigger trg_no_self_vote before insert or update on votes
  for each row execute function prevent_self_vote();

-- Recompute score + author karma on any vote change.
create or replace function recompute_comment_score()
returns trigger language plpgsql security definer set search_path = public as $$
declare cid uuid; new_score int; aid uuid;
begin
  cid := coalesce(new.comment_id, old.comment_id);
  select coalesce(sum(value),0) into new_score from votes where comment_id = cid;
  update comments set score = new_score where id = cid returning author_id into aid;
  if aid is not null then
    update profiles set karma = (
      select coalesce(sum(v.value),0) from votes v
      join comments c on c.id = v.comment_id where c.author_id = aid
    ) where id = aid;
  end if;
  return null;
end $$;
drop trigger if exists trg_vote_score on votes;
create trigger trg_vote_score after insert or update or delete on votes
  for each row execute function recompute_comment_score();

-- ---------------------------------------------------------------------------
-- mentions — resolved @username links per comment → drives notifications.
-- ---------------------------------------------------------------------------
create table if not exists mentions (
  comment_id        uuid not null references comments(id) on delete cascade,
  mentioned_user_id uuid not null references profiles(id) on delete cascade,
  primary key (comment_id, mentioned_user_id)
);
alter table mentions enable row level security;
create policy "mentions public read" on mentions for select using (true);
create policy "comment author writes mentions" on mentions for insert
  with check (exists (select 1 from comments c where c.id = comment_id and c.author_id = auth.uid()));

-- ---------------------------------------------------------------------------
-- notifications — reply / mention / fv_change. payload jsonb carries context
-- (thread/comment id, prospect key, old/new FV). Owner-only.
-- ---------------------------------------------------------------------------
create table if not exists notifications (
  id         uuid primary key default uuid_generate_v4(),
  user_id    uuid not null references profiles(id) on delete cascade,
  type       text not null check (type in ('reply','mention','fv_change','badge','follow')),
  payload    jsonb not null default '{}',
  read       boolean not null default false,
  created_at timestamptz not null default now()
);
create index if not exists notifications_user on notifications (user_id, read, created_at desc);
alter table notifications enable row level security;
create policy "owner reads notifications"  on notifications for select using (auth.uid() = user_id);
create policy "owner updates notifications" on notifications for update
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- notification_prefs — per-type toggles + email digest opt-in.
create table if not exists notification_prefs (
  user_id      uuid primary key references profiles(id) on delete cascade,
  reply        boolean not null default true,
  mention      boolean not null default true,
  fv_change    boolean not null default true,
  email_digest boolean not null default false
);
alter table notification_prefs enable row level security;
create policy "owner rw prefs" on notification_prefs for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

-- Bump thread + fan out reply/mention notifications when a comment is posted.
create or replace function on_comment_insert()
returns trigger language plpgsql security definer set search_path = public as $$
declare parent_author uuid;
begin
  update threads set comment_count = comment_count + 1, last_activity_at = now()
    where id = new.thread_id;
  -- reply notification to the parent comment's author (not self)
  if new.parent_id is not null then
    select author_id into parent_author from comments where id = new.parent_id;
    if parent_author is not null and parent_author <> new.author_id
       and coalesce((select reply from notification_prefs where user_id = parent_author), true) then
      insert into notifications (user_id, type, payload)
      values (parent_author, 'reply',
              jsonb_build_object('thread_id', new.thread_id, 'comment_id', new.id, 'from', new.author_id));
    end if;
  end if;
  return new;
end $$;
drop trigger if exists trg_on_comment_insert on comments;
create trigger trg_on_comment_insert after insert on comments
  for each row execute function on_comment_insert();

-- ---------------------------------------------------------------------------
-- reports (moderation queue) — flag a comment; staff resolve.
-- ---------------------------------------------------------------------------
create table if not exists reports (
  id          uuid primary key default uuid_generate_v4(),
  comment_id  uuid not null references comments(id) on delete cascade,
  reporter_id uuid references profiles(id) on delete set null,
  reason      text not null check (char_length(reason) <= 500),
  status      text not null default 'open' check (status in ('open','resolved','dismissed')),
  created_at  timestamptz not null default now(),
  unique (comment_id, reporter_id)
);
alter table reports enable row level security;
create policy "authed file report" on reports for insert with check (auth.uid() = reporter_id);
create policy "staff read reports"  on reports for select using (is_staff());
create policy "staff update reports" on reports for update using (is_staff());

-- ---------------------------------------------------------------------------
-- follows — user social graph (Part 7 activity feed).
-- ---------------------------------------------------------------------------
create table if not exists follows (
  follower_id uuid not null references profiles(id) on delete cascade,
  followee_id uuid not null references profiles(id) on delete cascade,
  created_at  timestamptz not null default now(),
  primary key (follower_id, followee_id),
  check (follower_id <> followee_id)
);
alter table follows enable row level security;
create policy "follows public read" on follows for select using (true);
create policy "owner writes follows" on follows for all
  using (auth.uid() = follower_id) with check (auth.uid() = follower_id);

commit;

-- ===========================================================================
-- NOTES / NOT IN THIS MIGRATION (intentional, handled outside SQL):
--  • Markdown sanitization: rendered + sanitized client-side (DOMPurify) AND
--    body_html stored already-sanitized; never trust raw markup. (Part 4/6)
--  • Rate limiting + reputation gates (no downvote / no links until karma ≥ N
--    for new accounts): enforced in the client + a Supabase Edge Function in
--    front of inserts; the RLS insert policies above are the floor, not the
--    whole story. (Part 6)
--  • FV-change notifications: emitted by the monthly pipeline (run_monthly)
--    after grades update — it diffs each watchlisted prospect's FV and inserts
--    'fv_change' notifications via the service role. (Part 5)
--  • Avatar storage: a Supabase Storage bucket 'avatars' (RLS by user_id,
--    ≤2MB, png/jpeg/webp) — created in the Storage UI / a storage policy file.
--  • Account deletion: delete auth.users → cascades profile + owned rows;
--    comments.author_id ON DELETE SET NULL keeps threads intact as [deleted].
--  • Polls / predictions / community-consensus rankings (Part 7 larger items):
--    deferred pending approval — separate migration when greenlit.
-- ===========================================================================
