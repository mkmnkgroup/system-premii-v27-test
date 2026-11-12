-- TEST ONLY: Supabase project bzpfukyugfuybqivjyoz.
-- Attendance publication is a separate admin-confirmed, immutable monthly action.
-- The verified Edge Function passes its own caller UUID; the database reads
-- saved draft data directly and checks the expected draft revision atomically.
begin;
alter table public.v27_test_attendance
  drop constraint if exists v27_test_attendance_status_check;
alter table public.v27_test_attendance
  add constraint v27_test_attendance_status_check
  check (status in ('present','absent','vacation','sick','off','unconfirmed'));
alter table public.v27_test_attendance
  alter column planned_hours drop not null,
  alter column planned_hours drop default,
  alter column worked_hours drop not null,
  alter column worked_hours drop default;
alter table public.v27_test_attendance
  add column if not exists absence_label text check (length(absence_label) <= 120),
  add column if not exists time_in time,
  add column if not exists time_out time,
  add column if not exists overtime_h numeric(5,2) check (overtime_h between 0 and 24);

create table if not exists public.v27_test_attendance_publications (
  period date primary key check (extract(day from period) = 1),
  published_by uuid not null references auth.users(id),
  published_at timestamptz not null default now(),
  draft_revision bigint not null check (draft_revision >= 1),
  employee_count integer not null check (employee_count between 1 and 50),
  entry_count integer not null check (entry_count between 1 and 1500)
);
alter table public.v27_test_attendance_publications enable row level security;
revoke all on table public.v27_test_attendance_publications from PUBLIC, anon, authenticated;

create or replace function public.v27_test_publish_attendance_month(
  p_actor uuid, p_period date, p_expected_revision bigint
) returns jsonb
language plpgsql security invoker set search_path = ''
as $fn$
declare
  v_payload jsonb;
  v_items jsonb;
  v_entry jsonb;
  v_name text;
  v_user uuid;
  v_matches int;
  v_date_text text;
  v_day date;
  v_day_type text;
  v_absence text;
  v_start text;
  v_end text;
  v_ot_text text;
  v_ot numeric;
  v_status text;
  v_count int := 0;
  v_employee_count int;
begin
  if p_actor is null or p_period is null or extract(day from p_period) <> 1
     or p_expected_revision is null or p_expected_revision < 1 then
    raise exception 'INVALID_PARAMETERS';
  end if;
  if not exists (
    select 1 from public.app_user_profiles p
     where p.user_id = p_actor and p.role = 'admin' and p.enabled = true
  ) then
    raise exception 'ADMIN_REQUIRED';
  end if;

  -- Row lock prevents the draft changing between preview verification and release.
  select d.payload into v_payload
  from public.v27_test_workflow_drafts d
  where d.item_key = 'draft_v27:' || to_char(p_period, 'YYYY-MM') || ':attendance'
    and d.revision = p_expected_revision
  for update;
  if v_payload is null or v_payload->>'format_version' <> '1'
     or v_payload->>'period' <> to_char(p_period, 'YYYY-MM')
     or jsonb_typeof(v_payload->'entries') <> 'array' then
    raise exception 'DRAFT_MISSING_OR_STALE';
  end if;
  v_items := v_payload->'entries';
  if jsonb_array_length(v_items) not between 1 and 1500 then
    raise exception 'BAD_ENTRY_COUNT';
  end if;

  -- A unique marker makes a month publishable only once, with no partial rows.
  insert into public.v27_test_attendance_publications
    (period, published_by, draft_revision, employee_count, entry_count)
  values (p_period, p_actor, p_expected_revision, 1, jsonb_array_length(v_items));

  for v_entry in select value from jsonb_array_elements(v_items)
  loop
    if jsonb_typeof(v_entry) <> 'object' then
      raise exception 'BAD_ATTENDANCE_ENTRY';
    end if;
    v_name := nullif(btrim(v_entry->>'employee'), '');
    if v_name is null or length(v_name) > 150 then
      raise exception 'INVALID_EMPLOYEE_NAME';
    end if;
    select count(*), max(p.user_id) into v_matches, v_user
    from public.app_user_profiles p
    where p.enabled = true and p.role in ('admin','manager','employee')
      and p.employee_id is not null
      and upper(regexp_replace(btrim(p.employee_id), '[[:space:]]+', ' ', 'g')) =
          upper(regexp_replace(v_name, '[[:space:]]+', ' ', 'g'));
    if v_matches <> 1 then
      raise exception 'EMPLOYEE_ACCOUNT_LINK_MISMATCH';
    end if;

    v_date_text := v_entry->>'work_day';
    if v_date_text is null or v_date_text !~ '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' then
      raise exception 'INVALID_ATTENDANCE_DATE';
    end if;
    v_day := v_date_text::date;
    if to_char(v_day, 'YYYY-MM-DD') <> v_date_text or
       date_trunc('month', v_day::timestamp)::date <> p_period then
      raise exception 'ATTENDANCE_MONTH_MISMATCH';
    end if;
    v_day_type := v_entry->>'day_type';
    if v_day_type not in ('Pracujący', 'Wolny', 'Święto') or v_day_type is null then
      raise exception 'INVALID_DAY_TYPE';
    end if;
    v_absence := coalesce(nullif(btrim(v_entry->>'absence'), ''), 'Brak');
    if length(v_absence) > 120 then
      raise exception 'INVALID_ABSENCE';
    end if;

    v_start := coalesce(v_entry->>'time_in', '');
    v_end := coalesce(v_entry->>'time_out', '');
    if v_start <> '' and v_start !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' then
      raise exception 'INVALID_START_TIME';
    end if;
    if v_end <> '' and v_end !~ '^([01][0-9]|2[0-3]):[0-5][0-9]$' then
      raise exception 'INVALID_END_TIME';
    end if;
    v_ot_text := v_entry->>'overtime_h';
    if v_ot_text is null or v_ot_text !~ '^[0-9]{1,2}([.][0-9]{1,2})?$' then
      raise exception 'INVALID_OVERTIME';
    end if;
    v_ot := v_ot_text::numeric;
    if v_ot > 24 then
      raise exception 'INVALID_OVERTIME';
    end if;

    if v_day_type in ('Wolny','Święto') then
      if v_start <> '' or v_end <> '' or v_ot <> 0 or v_absence <> 'Brak' then
        raise exception 'OFF_DAY_WITH_ACTIVITY_NEEDS_REVIEW';
      end if;
      v_status := 'off';
    elsif v_absence <> 'Brak' then
      if v_start <> '' or v_end <> '' or v_ot <> 0 then
        raise exception 'ABSENCE_CONFLICTS_WITH_ACTIVITY';
      end if;
      v_status := 'absent';
    elsif v_start <> '' and v_end <> '' then
      v_status := 'present';
    else
      if v_ot <> 0 then
        raise exception 'UNCONFIRMED_OVERTIME';
      end if;
      v_status := 'unconfirmed';
    end if;

    -- Work duration is intentionally NULL: entry/exit alone does not
    -- establish payable hours (breaks have not yet been modeled).
    insert into public.v27_test_attendance
      (user_id, work_day, status, planned_hours, worked_hours,
       absence_label, time_in, time_out, overtime_h)
    values (
      v_user, v_day, v_status, NULL, NULL,
      case when v_status = 'absent' then v_absence else NULL end,
      nullif(v_start,'')::time, nullif(v_end,'')::time, v_ot
    );
    v_count := v_count + 1;
  end loop;
  select count(distinct user_id) into v_employee_count
  from public.v27_test_attendance
  where work_day >= p_period and work_day < (p_period + interval '1 month');
  if v_employee_count not between 1 and 50 then
    raise exception 'BAD_EMPLOYEE_COUNT';
  end if;
  update public.v27_test_attendance_publications
  set employee_count = v_employee_count
  where period = p_period;

  return jsonb_build_object(
    'published', true, 'period', to_char(p_period, 'YYYY-MM'),
    'entry_count', v_count, 'employee_count', v_employee_count,
    'draft_revision', p_expected_revision
  );
end;
$fn$;
revoke all on function public.v27_test_publish_attendance_month(uuid,date,bigint)
  from PUBLIC, anon, authenticated;
grant execute on function public.v27_test_publish_attendance_month(uuid,date,bigint)
  to service_role;
commit;