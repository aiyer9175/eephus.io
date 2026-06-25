-- Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
-- eephus.io — moderation & anti-abuse (Part 6). The AUTHORITATIVE server-side
-- floor: ban/suspend, posting/voting rate-limits, and new-account reputation
-- gates. The client (eephus-ui.js) mirrors these for instant UX, but these
-- triggers are what actually enforce — RLS lets a row in, these decide if it
-- stays. Run AFTER 0001/0002.
begin;

-- Suspension window. NULL = not banned; future timestamp = suspended until then
-- (use a far-future date for a permanent ban). Set by staff / service role only.
alter table profiles add column if not exists banned_until timestamptz;

-- helpers ---------------------------------------------------------------------
create or replace function eph_karma(uid uuid) returns int language sql stable as $$
  select coalesce((select karma from profiles where id = uid), 0);
$$;
create or replace function eph_is_banned(uid uuid) returns boolean language sql stable as $$
  select exists (select 1 from profiles where id = uid and banned_until is not null and banned_until > now());
$$;

-- Comments: ban check · rate-limit (≤ 6 / minute) · link gate (< 5 karma → no
-- URLs, the primary new-account spam defense given no social-provider vouching).
create or replace function guard_comment_insert()
returns trigger language plpgsql security definer set search_path = public as $$
declare recent int;
begin
  if eph_is_banned(new.author_id) then
    raise exception 'account is suspended';
  end if;
  select count(*) into recent from comments
    where author_id = new.author_id and created_at > now() - interval '1 minute';
  if recent >= 6 then
    raise exception 'posting too fast — wait a moment';
  end if;
  if eph_karma(new.author_id) < 5 and new.body_md ~* 'https?://' then
    raise exception 'new accounts cannot post links until 5 karma';
  end if;
  return new;
end $$;
drop trigger if exists trg_guard_comment on comments;
create trigger trg_guard_comment before insert on comments
  for each row execute function guard_comment_insert();

-- Votes: ban check · rate-limit (≤ 20 / minute) · downvote gate (< 10 karma).
create or replace function guard_vote_insert()
returns trigger language plpgsql security definer set search_path = public as $$
declare recent int;
begin
  if eph_is_banned(new.user_id) then
    raise exception 'account is suspended';
  end if;
  select count(*) into recent from votes
    where user_id = new.user_id and created_at > now() - interval '1 minute';
  if recent >= 20 then
    raise exception 'voting too fast — slow down';
  end if;
  if new.value = -1 and eph_karma(new.user_id) < 10 then
    raise exception 'downvoting unlocks at 10 karma';
  end if;
  return new;
end $$;
drop trigger if exists trg_guard_vote on votes;
create trigger trg_guard_vote before insert on votes
  for each row execute function guard_vote_insert();

-- Staff may update another user's profile (ban/suspend, role grants). Combined
-- OR with the existing "owner updates own profile" policy. The guard trigger
-- from 0001 only pins role/karma on SELF-edits, so staff edits to others pass.
drop policy if exists "staff manages profiles" on profiles;
create policy "staff manages profiles" on profiles for update
  using (is_staff()) with check (is_staff());

commit;
