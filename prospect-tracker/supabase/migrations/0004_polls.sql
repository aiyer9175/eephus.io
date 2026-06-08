-- Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
-- eephus.io — Part 7 polls. A poll is defined INLINE in a comment's markdown as
-- `[[poll:Question?|Option A|Option B|...]]` (so it reuses the existing comment
-- sanitization + render path); only the VOTES need storage, keyed by the host
-- comment. One vote per user per poll; changing your vote upserts. Run AFTER
-- 0001. (The `follows` table for the activity feed already ships in 0001.)
begin;

create table if not exists poll_votes (
  comment_id uuid not null references comments(id) on delete cascade,
  user_id    uuid not null references profiles(id) on delete cascade,
  choice     smallint not null check (choice >= 0 and choice < 10),
  created_at timestamptz not null default now(),
  primary key (comment_id, user_id)
);
alter table poll_votes enable row level security;
create policy "poll_votes public read" on poll_votes for select using (true);
create policy "owner writes poll_votes" on poll_votes for all
  using (auth.uid() = user_id) with check (auth.uid() = user_id);

commit;
