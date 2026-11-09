-- Isolated TEST Supabase project: bzpfukyugfuybqivjyoz ONLY.
-- Drafts are NEVER exposed directly to clients.
-- Approved employee-visible data remain in separate RLS tables.
begin;
create table if not exists public.v27_test_workflow_drafts (
  item_key text primary key
    check (item_key ~ '^(settings_v27|archive_v27|draft_v27:[0-9]{4}-(0[1-9]|1[0-2]):(schedule|attendance|bonuses|production|weights|approval))$'),
  payload jsonb not null default '{}'::jsonb,
  revision bigint not null default 1 check (revision >= 1),
  updated_by uuid not null references auth.users(id),
  updated_at timestamptz not null default now()
);
alter table public.v27_test_workflow_drafts enable row level security;
revoke all on public.v27_test_workflow_drafts from public, anon, authenticated;
-- No policies for any Data API user. The verified test-only Edge Function
-- uses service-role rights after checking server-side role on each request.
commit;