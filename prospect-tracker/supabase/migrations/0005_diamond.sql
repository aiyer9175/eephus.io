-- Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
-- eephus.io - Diamond entitlement + the personal bet tracker.
--
-- Ships DORMANT. Diamond is not gated at launch (assets/diamond-config.js
-- carries `gating: false`), and nothing here grants itself: `diamond_until`
-- is service-role only, exactly like `role` and `karma`. This migration only
-- makes the columns and tables exist so the front end has something real to
-- talk to when the flag eventually flips.
--
-- Target: Supabase Postgres. Run AFTER 0001 (profiles, badges, the
-- guard_profile_privileged_cols trigger) and 0003 (banned_until). Same
-- conventions as 0001: RLS on every user-data table, IF NOT EXISTS /
-- CREATE OR REPLACE so a re-run is harmless.

begin;

-- ---------------------------------------------------------------------------
-- Bet result enum. `open` is the resting state; `void` covers a push, a
-- cancelled game, or a book voiding the wager.
-- ---------------------------------------------------------------------------
do $$ begin
  create type bet_result as enum ('open', 'won', 'lost', 'void');
exception when duplicate_object then null; end $$;

-- ---------------------------------------------------------------------------
-- bets - the user's OWN bet log, cloned from watchlist's owner-only RLS shape.
--
-- PRIVATE by construction: there is no public-read policy here, unlike
-- favorites/badges. A bet log is financial behavior, not social identity, so
-- the owner is the only reader. The site's PUBLISHED betting record is a
-- separate thing entirely (data/betting_record.json, append-only, written by
-- the pipeline) and never draws from this table.
--
-- `odds` is AMERICAN odds at the moment the bet was placed, stored as an
-- integer (-110, +145). Storing the price at placement rather than deriving
-- it later is what makes closing-line value computable after the fact.
-- `payload` carries whatever the tracker UI wants to keep (book, game id,
-- line, our model probability at post) without a migration per field.
-- ---------------------------------------------------------------------------
create table if not exists bets (
  id          uuid primary key default uuid_generate_v4(),
  user_id     uuid not null references profiles(id) on delete cascade,
  sport       text not null default 'mlb',
  market      text not null,                 -- 'moneyline' | 'runline' | 'total' | 'prop' | 'parlay'
  selection   text not null,                 -- free text: the side actually taken
  odds        integer not null,              -- American odds AT PLACEMENT
  stake       numeric(12,2) not null default 1,
  placed_at   timestamptz not null default now(),
  settled_at  timestamptz,
  result      bet_result not null default 'open',
  payload     jsonb not null default '{}',
  created_at  timestamptz not null default now()
);
create index if not exists bets_user_placed on bets (user_id, placed_at desc);
create index if not exists bets_user_open on bets (user_id) where result = 'open';
alter table bets enable row level security;
create policy "owner reads bets"   on bets for select using (auth.uid() = user_id);
create policy "owner inserts bets" on bets for insert with check (auth.uid() = user_id);
create policy "owner updates bets" on bets for update
  using (auth.uid() = user_id) with check (auth.uid() = user_id);
create policy "owner deletes bets" on bets for delete using (auth.uid() = user_id);

-- ---------------------------------------------------------------------------
-- The Diamond badge. Display already flows through getUserBadges /
-- userFlair (assets/eephus-ui.js), so seeding the row is the whole job;
-- 'manual' kind means a grant is an explicit act, not a scheduled job.
-- ---------------------------------------------------------------------------
insert into badges (slug, name, description, icon, kind) values
  ('diamond', 'Diamond', 'Supports eephus.io with a Diamond membership.', '💎', 'manual')
on conflict (slug) do nothing;

-- ---------------------------------------------------------------------------
-- profiles.diamond_until - the entitlement itself. NULL or past = not a
-- member; a future timestamp = member until then. One nullable timestamptz
-- rather than a boolean, so an expiring membership expires on its own instead
-- of needing a job to switch it off.
-- ---------------------------------------------------------------------------
alter table profiles add column if not exists diamond_until timestamptz;

-- Extend the privileged-column guard from 0001 to cover it. Without this line
-- the "owner updates own profile" policy would let any signed-in user hand
-- themselves a Diamond membership with a single PATCH, because RLS allows the
-- row update and nothing else inspects the columns. Same silent-pin pattern
-- as role/karma: the write succeeds, the value does not change.
create or replace function guard_profile_privileged_cols()
returns trigger language plpgsql as $$
begin
  if auth.uid() = new.id and (new.role is distinct from old.role
       or new.karma is distinct from old.karma
       or new.diamond_until is distinct from old.diamond_until) then
    new.role := old.role;
    new.karma := old.karma;
    new.diamond_until := old.diamond_until;   -- service role only
  end if;
  return new;
end $$;
drop trigger if exists trg_guard_profile on profiles;
create trigger trg_guard_profile before update on profiles
  for each row execute function guard_profile_privileged_cols();

commit;

-- ===========================================================================
-- NOT IN THIS MIGRATION (intentional):
--  * Payment. Stripe is out of scope this pass: it needs an entity and a legal
--    review, and the review is not simple next to betting content. The grant
--    path today is a service-role update to diamond_until.
--  * Gating. Nothing reads diamond_until to withhold content yet. The site is
--    static, so genuinely members-only DATA cannot live in /data/*.json when
--    that day comes; it has to arrive over RLS or an edge function. The
--    modules are built with that seam in mind.
--  * The published betting record. That is a pipeline artifact
--    (data/betting_record.json), append-only, and has nothing to do with the
--    private `bets` table above.
-- ===========================================================================
