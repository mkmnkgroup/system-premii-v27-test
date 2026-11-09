-- TEST PROJECT ONLY: bzpfukyugfuybqivjyoz
-- Supabase Auth owns passwords. Never store passwords in public profiles.
begin;
create table if not exists public.app_user_profiles (
  user_id uuid primary key references auth.users(id) on delete cascade,
  email text not null,
  display_name text,
  employee_id text,
  role text not null default 'employee'
    check (role in ('admin','director','manager','employee')),
  enabled boolean not null default false,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);
alter table public.app_user_profiles enable row level security;
revoke all on public.app_user_profiles from anon;
grant select on public.app_user_profiles to authenticated;
-- Security-definer helper prevents recursive RLS checks; locked search path.
create or replace function public.is_app_admin()
returns boolean language sql stable security definer
set search_path = '' as $$
  select exists (
    select 1 from public.app_user_profiles p
    where p.user_id = (select auth.uid())
      and p.role = 'admin' and p.enabled
  );
$$;
revoke all on function public.is_app_admin() from public, anon;
grant execute on function public.is_app_admin() to authenticated;
drop policy if exists "read_own_enabled_profile" on public.app_user_profiles;
create policy "read_own_enabled_profile" on public.app_user_profiles
  for select to authenticated
  using (user_id = (select auth.uid()) and enabled);
drop policy if exists "admin_read_profiles" on public.app_user_profiles;
create policy "admin_read_profiles" on public.app_user_profiles
  for select to authenticated using ((select public.is_app_admin()));
-- No client INSERT/UPDATE/DELETE policies. Account provisioning and role changes
-- must happen through an audited server-side administrative workflow.
commit;
