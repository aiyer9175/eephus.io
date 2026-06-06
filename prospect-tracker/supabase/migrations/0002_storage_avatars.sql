-- Avatar storage bucket + RLS. Run AFTER 0001. Avatars render circular in the
-- UI (the one sanctioned exception to rectangular photos). Public-read so they
-- show on profiles/comments; write restricted to the owner's own folder.
begin;

insert into storage.buckets (id, name, public)
values ('avatars', 'avatars', true)
on conflict (id) do nothing;

-- File-size / MIME limits are also set on the bucket in the dashboard
-- (2 MB; image/png, image/jpeg, image/webp). These policies key uploads to a
-- per-user folder: avatars/<auth.uid()>/<filename>.
create policy "avatars public read"
  on storage.objects for select
  using (bucket_id = 'avatars');

create policy "users upload own avatar"
  on storage.objects for insert to authenticated
  with check (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "users replace own avatar"
  on storage.objects for update to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);

create policy "users delete own avatar"
  on storage.objects for delete to authenticated
  using (bucket_id = 'avatars' and (storage.foldername(name))[1] = auth.uid()::text);

commit;
