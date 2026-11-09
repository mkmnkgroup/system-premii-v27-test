-- TEST PROJECT ONLY: bzpfukyugfuybqivjyoz.
-- Published results are separate from admin-only session/draft storage.
-- Entire publication is atomic and append-only by period.
begin;

-- The existing production import has team-level positions/pieces/weight,
-- not per-person counts. Unknown person-level counts must never appear as zero.
alter table public.v27_test_employee_monthly
  alter column positions drop not null,
  alter column positions drop default,
  alter column pieces drop not null,
  alter column pieces drop default,
  alter column weight_kg drop not null,
  alter column weight_kg drop default;
alter table public.v27_test_employee_monthly
  add column if not exists bonus_main_pln numeric(12,2) not null default 0
    check (bonus_main_pln >= 0),
  add column if not exists bonus_additions_pln numeric(12,2) not null default 0
    check (bonus_additions_pln >= 0);

-- The performance indicator can legitimately be negative when below baseline.
alter table public.v27_test_monthly_kpis
  drop constraint if exists v27_test_monthly_kpis_performance_pct_check;
alter table public.v27_test_monthly_kpis
  add constraint v27_test_monthly_kpis_performance_pct_check
  check (performance_pct between -10000 and 10000);

create table if not exists public.v27_test_publications (
  period date primary key check (extract(day from period)=1),
  published_by uuid not null references auth.users(id),
  published_at timestamptz not null default now(),
  employee_count smallint not null check (employee_count between 1 and 50)
);
alter table public.v27_test_publications enable row level security;
revoke all on table public.v27_test_publications from public, anon, authenticated;

-- This function is called ONLY with service-role credentials by a separate
-- Edge Function that first verifies the user's JWT and active admin profile.
-- It remains executable by service_role only, never by regular authenticated users.
create or replace function public.v27_test_publish_month(
  p_actor uuid, p_period date, p_kpis jsonb, p_employees jsonb
) returns jsonb
language plpgsql security definer set search_path = ''
as $fn$
declare
  row_data jsonb;
  v_user_id uuid;
  v_employee_name text;
  v_total numeric;
  v_main numeric;
  v_additions numeric;
  v_count integer;
begin
  if p_actor is null or p_period is null or extract(day from p_period) <> 1 then
    raise exception 'INVALID_PERIOD_OR_ACTOR';
  end if;
  if not exists (
    select 1 from public.app_user_profiles p
    where p.user_id = p_actor and p.role = 'admin' and p.enabled = true
  ) then
    raise exception 'ADMIN_REQUIRED';
  end if;
  if jsonb_typeof(p_kpis) <> 'object' or
      jsonb_typeof(p_employees) <> 'array' then
    raise exception 'INVALID_PAYLOAD';
  end if;
  v_count := jsonb_array_length(p_employees);
  if v_count < 1 or v_count > 50 then
    raise exception 'INVALID_EMPLOYEE_COUNT';
  end if;

  -- Unique publication marker prevents races and accidental double release.
  -- Later corrections must have a separate, explicit audited workflow.
  insert into public.v27_test_publications
    (period, published_by, employee_count)
  values (p_period,p_actor,v_count);

  insert into public.v27_test_monthly_kpis
    (period,positions,pieces,weight_kg,performance_pct)
  values (
    p_period,
    (p_kpis->>'positions')::bigint,
    (p_kpis->>'pieces')::bigint,
    (p_kpis->>'weight_kg')::numeric,
    (p_kpis->>'performance_pct')::numeric
  );

  for row_data in select value from jsonb_array_elements(p_employees)
  loop
    if jsonb_typeof(row_data) <> 'object' then
      raise exception 'INVALID_EMPLOYEE_ROW';
    end if;
    v_user_id := (row_data->>'user_id')::uuid;
    v_employee_name := btrim(row_data->>'employee_name');
    if v_employee_name is null or length(v_employee_name) < 3 then
      raise exception 'MISSING_EMPLOYEE_NAME';
    end if;
    -- A named employee must be explicitly linked in Admin > Users first.
    -- No guessed name/email matching and no reassignment to arbitrary accounts.
    if not exists (
      select 1 from public.app_user_profiles p
      where p.user_id = v_user_id and p.enabled = true
        and p.role in ('admin','manager','employee')
        and p.employee_id is not null
        and upper(btrim(p.employee_id)) = upper(v_employee_name)
    ) then
      raise exception 'EMPLOYEE_ACCOUNT_LINK_MISMATCH';
    end if;

    v_main := (row_data->>'bonus_main_pln')::numeric;
    v_additions := (row_data->>'bonus_additions_pln')::numeric;
    v_total := (row_data->>'bonus_final_pln')::numeric;
    if v_main is null or v_additions is null or v_total is null
      or abs(v_total-v_main-v_additions) > 0.01 then
      raise exception 'INVALID_BONUS_TOTAL';
    end if;

    insert into public.v27_test_employee_monthly
      (user_id,period,positions,pieces,weight_kg,planned_days,attended_days,
       bonus_base_pln,bonus_main_pln,bonus_additions_pln,
       absence_reduction_pct,bonus_final_pln)
    values (
      v_user_id,p_period,null,null,null,
      (row_data->>'planned_days')::integer,
      (row_data->>'attended_days')::integer,
      0,v_main,v_additions,
      (row_data->>'absence_reduction_pct')::numeric,
      v_total
    );
  end loop;

  return jsonb_build_object(
    'period',to_char(p_period,'YYYY-MM'),
    'employee_count',v_count,
    'published',true
  );
end;
$fn$;
revoke all on function public.v27_test_publish_month(uuid,date,jsonb,jsonb)
  from PUBLIC, anon, authenticated;
grant execute on function public.v27_test_publish_month(uuid,date,jsonb,jsonb)
  to service_role;
commit;