-- RUN ONLY IN ISOLATED TEST Supabase. All fixtures ROLLBACK.
begin;
do $guard$
begin
  if exists(select 1 from public.v27_test_attendance_publications where period='2099-12-01')
    or exists(select 1 from public.v27_test_workflow_drafts
              where item_key='draft_v27:2099-12:attendance')
  then raise exception 'fixture key already in use, abort'; end if;
end;
$guard$;

update public.app_user_profiles
set employee_id='FIKCYJNY TEST DO WYCOFANIA'
where user_id='fc48a0ab-e4dc-4264-9f99-2d77d61e1bc5';

insert into public.v27_test_workflow_drafts(item_key,payload,revision,updated_by)
values (
'draft_v27:2099-12:attendance',
'{"format_version":1,"period":"2099-12","entries":[
{"employee":"FIKCYJNY TEST DO WYCOFANIA","work_day":"2099-12-01","day_type":"Pracujący","absence":"Brak","time_in":"08:00","time_out":"16:00","overtime_h":1.5},
{"employee":"FIKCYJNY TEST DO WYCOFANIA","work_day":"2099-12-02","day_type":"Pracujący","absence":"Zwolnienie","time_in":"","time_out":"","overtime_h":0},
{"employee":"FIKCYJNY TEST DO WYCOFANIA","work_day":"2099-12-03","day_type":"Pracujący","absence":"Brak","time_in":"","time_out":"","overtime_h":0},
{"employee":"FIKCYJNY TEST DO WYCOFANIA","work_day":"2099-12-04","day_type":"Wolny","absence":"Brak","time_in":"","time_out":"","overtime_h":0}
]}'::jsonb,
1,'fc48a0ab-e4dc-4264-9f99-2d77d61e1bc5'
);

do $test$
declare
  v_result jsonb;
  v_blocked boolean := false;
begin
  -- Wrong revision cannot create a marker or any attendance row.
  begin
    perform public.v27_test_publish_attendance_month(
      'fc48a0ab-e4dc-4264-9f99-2d77d61e1bc5','2099-12-01',2);
  exception when others then v_blocked := true;
  end;
  if not v_blocked or exists (
     select 1 from public.v27_test_attendance_publications where period='2099-12-01'
  ) then raise exception 'STALE_REVISION_NOT_REJECTED'; end if;

  select public.v27_test_publish_attendance_month(
    'fc48a0ab-e4dc-4264-9f99-2d77d61e1bc5','2099-12-01',1)
  into v_result;
  if v_result->>'published' <> 'true' or
     (select count(*) from public.v27_test_attendance
       where work_day between '2099-12-01' and '2099-12-31') <> 4 or
     (select count(*) from public.v27_test_attendance
       where status='present' and work_day='2099-12-01'
       and time_in='08:00' and time_out='16:00'
       and overtime_h=1.5 and worked_hours is null) <> 1 or
     (select count(*) from public.v27_test_attendance
       where status='absent' and work_day='2099-12-02' and absence_label='Zwolnienie') <> 1 or
     (select count(*) from public.v27_test_attendance
       where status='unconfirmed' and work_day='2099-12-03') <> 1 or
     (select count(*) from public.v27_test_attendance
       where status='off' and work_day='2099-12-04') <> 1
  then raise exception 'PUBLISHED_DATA_INCORRECT'; end if;

  v_blocked := false;
  begin
    perform public.v27_test_publish_attendance_month(
      'fc48a0ab-e4dc-4264-9f99-2d77d61e1bc5','2099-12-01',1);
  exception when unique_violation then v_blocked := true;
  end;
  if not v_blocked then raise exception 'DUPLICATE_MONTH_NOT_BLOCKED'; end if;
end;
$test$;
rollback;