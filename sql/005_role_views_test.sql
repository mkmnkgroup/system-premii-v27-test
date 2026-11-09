-- TEST ONLY: project bzpfukyugfuybqivjyoz
-- Empty, read-only surfaces. No actual employee/production/payroll data imported.
-- RLS permissions apply to Data API calls; Streamlit also checks roles.
begin;

create table if not exists public.v27_test_schedule (
  user_id uuid not null references auth.users(id) on delete cascade,
  work_day date not null,
  shift_label text not null check (length(shift_label) between 1 and 80),
  starts_at time,
  ends_at time,
  primary key (user_id, work_day)
);
create table if not exists public.v27_test_attendance (
  user_id uuid not null references auth.users(id) on delete cascade,
  work_day date not null,
  status text not null check (status in ('present','absent','vacation','sick','off')),
  planned_hours numeric(5,2) not null default 0 check (planned_hours >= 0 and planned_hours <= 24),
  worked_hours numeric(5,2) not null default 0 check (worked_hours >= 0 and worked_hours <= 24),
  primary key (user_id, work_day)
);
create table if not exists public.v27_test_employee_monthly (
  user_id uuid not null references auth.users(id) on delete cascade,
  period date not null check (extract(day from period) = 1),
  positions bigint not null default 0 check (positions >= 0),
  pieces bigint not null default 0 check (pieces >= 0),
  weight_kg numeric(15,2) not null default 0 check (weight_kg >= 0),
  planned_days integer not null default 0 check (planned_days between 0 and 31),
  attended_days integer not null default 0 check (attended_days between 0 and 31),
  bonus_base_pln numeric(12,2) not null default 0 check (bonus_base_pln >= 0),
  absence_reduction_pct numeric(5,2) not null default 0 check (absence_reduction_pct between 0 and 100),
  bonus_final_pln numeric(12,2) not null default 0 check (bonus_final_pln >= 0),
  primary key (user_id, period)
);
create table if not exists public.v27_test_monthly_kpis (
  period date primary key check (extract(day from period) = 1),
  positions bigint not null default 0 check (positions >= 0),
  pieces bigint not null default 0 check (pieces >= 0),
  weight_kg numeric(15,2) not null default 0 check (weight_kg >= 0),
  performance_pct numeric(7,2) check (performance_pct >= 0),
  target_positions bigint check (target_positions > 0),
  target_pieces bigint check (target_pieces > 0),
  target_weight_kg numeric(15,2) check (target_weight_kg > 0)
);

alter table public.v27_test_schedule enable row level security;
alter table public.v27_test_attendance enable row level security;
alter table public.v27_test_employee_monthly enable row level security;
alter table public.v27_test_monthly_kpis enable row level security;

revoke all on public.v27_test_schedule, public.v27_test_attendance,
  public.v27_test_employee_monthly, public.v27_test_monthly_kpis from PUBLIC, anon, authenticated;
grant select on public.v27_test_schedule, public.v27_test_attendance,
  public.v27_test_employee_monthly, public.v27_test_monthly_kpis to authenticated;

drop policy if exists v27_schedule_verified_role on public.v27_test_schedule;
create policy v27_schedule_verified_role on public.v27_test_schedule
for select to authenticated using (
  exists (
    select 1 from public.app_user_profiles p
    where p.user_id = (select auth.uid()) and p.enabled
      and (
        p.role in ('admin', 'manager')
        or (p.role = 'employee' and v27_test_schedule.user_id = (select auth.uid()))
      )
  )
);

drop policy if exists v27_attendance_verified_role on public.v27_test_attendance;
create policy v27_attendance_verified_role on public.v27_test_attendance
for select to authenticated using (
  exists (
    select 1 from public.app_user_profiles p
    where p.user_id = (select auth.uid()) and p.enabled
      and (
        p.role in ('admin', 'manager')
        or (p.role = 'employee' and v27_test_attendance.user_id = (select auth.uid()))
      )
  )
);

drop policy if exists v27_employee_month_verified_role on public.v27_test_employee_monthly;
create policy v27_employee_month_verified_role on public.v27_test_employee_monthly
for select to authenticated using (
  exists (
    select 1 from public.app_user_profiles p
    where p.user_id = (select auth.uid()) and p.enabled
      and (
        p.role in ('admin', 'manager')
        or (p.role = 'employee' and v27_test_employee_monthly.user_id = (select auth.uid()))
      )
  )
);

drop policy if exists v27_kpis_verified_role on public.v27_test_monthly_kpis;
create policy v27_kpis_verified_role on public.v27_test_monthly_kpis
for select to authenticated using (
  exists (
    select 1 from public.app_user_profiles p
    where p.user_id = (select auth.uid()) and p.enabled
      and p.role in ('admin', 'director', 'manager', 'employee')
  )
);

-- Clients cannot INSERT/UPDATE/DELETE. Future data import must use
-- an audited server-side operation and verify record ownership.
commit;
