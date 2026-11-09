-- Run ONLY on test project bzpfukyugfuybqivjyoz. Every fixture is rolled back.
begin;

insert into auth.users (id, instance_id, aud, role, email, created_at, updated_at)
values
('11111111-1111-4111-8111-111111111111', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'rls-employee-a@example.invalid', now(), now()),
('22222222-2222-4222-8222-222222222222', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'rls-employee-b@example.invalid', now(), now()),
('33333333-3333-4333-8333-333333333333', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'rls-director@example.invalid', now(), now()),
('44444444-4444-4444-8444-444444444444', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'rls-manager@example.invalid', now(), now()),
('55555555-5555-4555-8555-555555555555', '00000000-0000-0000-0000-000000000000', 'authenticated', 'authenticated', 'rls-disabled@example.invalid', now(), now());

insert into public.app_user_profiles (user_id, email, role, enabled)
values
('11111111-1111-4111-8111-111111111111', 'rls-employee-a@example.invalid','employee',true),
('22222222-2222-4222-8222-222222222222', 'rls-employee-b@example.invalid','employee',true),
('33333333-3333-4333-8333-333333333333', 'rls-director@example.invalid','director',true),
('44444444-4444-4444-8444-444444444444', 'rls-manager@example.invalid','manager',true),
('55555555-5555-4555-8555-555555555555', 'rls-disabled@example.invalid','employee',false);

insert into public.v27_test_schedule (user_id,work_day,shift_label)
values
('11111111-1111-4111-8111-111111111111','2026-11-12','Ranna'),
('22222222-2222-4222-8222-222222222222','2026-11-12','Popołudniowa');
insert into public.v27_test_attendance (user_id,work_day,status,planned_hours,worked_hours)
values
('11111111-1111-4111-8111-111111111111','2026-11-12','present',8,8),
('22222222-2222-4222-8222-222222222222','2026-11-12','absent',8,0);
insert into public.v27_test_employee_monthly (user_id,period,positions,pieces,bonus_final_pln)
values
('11111111-1111-4111-8111-111111111111','2026-11-01',100,1000,500),
('22222222-2222-4222-8222-222222222222','2026-11-01',200,2000,600);
insert into public.v27_test_monthly_kpis (period,positions,pieces)
values ('2026-11-01',300,3000);

set local role authenticated;
select set_config('request.jwt.claim.sub','11111111-1111-4111-8111-111111111111',true);
do $$ begin
 if (select count(*) from public.v27_test_schedule) <> 1
 or (select count(*) from public.v27_test_attendance) <> 1
 or (select count(*) from public.v27_test_employee_monthly) <> 1
 or (select count(*) from public.v27_test_monthly_kpis) <> 1
 or (select count(*) from public.v27_test_employee_monthly where bonus_final_pln=600) <> 0
 then raise exception 'RLS employee A: personal data leak'; end if;
end $$;

select set_config('request.jwt.claim.sub','22222222-2222-4222-8222-222222222222',true);
do $$ begin
 if (select count(*) from public.v27_test_schedule) <> 1
 or (select count(*) from public.v27_test_attendance) <> 1
 or (select count(*) from public.v27_test_employee_monthly) <> 1
 or (select count(*) from public.v27_test_monthly_kpis) <> 1
 or (select count(*) from public.v27_test_employee_monthly where bonus_final_pln=500) <> 0
 then raise exception 'RLS employee B: personal data leak'; end if;
end $$;

select set_config('request.jwt.claim.sub','33333333-3333-4333-8333-333333333333',true);
do $$ begin
 if (select count(*) from public.v27_test_schedule) <> 0
 or (select count(*) from public.v27_test_attendance) <> 0
 or (select count(*) from public.v27_test_employee_monthly) <> 0
 or (select count(*) from public.v27_test_monthly_kpis) <> 1
 then raise exception 'RLS director: individual employee records visible'; end if;
end $$;

select set_config('request.jwt.claim.sub','44444444-4444-4444-8444-444444444444',true);
do $$ begin
 if (select count(*) from public.v27_test_schedule) <> 2
 or (select count(*) from public.v27_test_attendance) <> 2
 or (select count(*) from public.v27_test_employee_monthly) <> 2
 or (select count(*) from public.v27_test_monthly_kpis) <> 1
 then raise exception 'RLS manager: expected authorized records missing'; end if;
end $$;

select set_config('request.jwt.claim.sub','55555555-5555-4555-8555-555555555555',true);
do $$ begin
 if (select count(*) from public.v27_test_schedule) <> 0
 or (select count(*) from public.v27_test_attendance) <> 0
 or (select count(*) from public.v27_test_employee_monthly) <> 0
 or (select count(*) from public.v27_test_monthly_kpis) <> 0
 then raise exception 'RLS disabled user: data leak'; end if;
end $$;

select set_config('request.jwt.claim.sub','fc48a0ab-e4dc-4264-9f99-2d77d61e1bc5',true);
do $$ begin
 if (select count(*) from public.v27_test_schedule) <> 2
 or (select count(*) from public.v27_test_attendance) <> 2
 or (select count(*) from public.v27_test_employee_monthly) <> 2
 or (select count(*) from public.v27_test_monthly_kpis) <> 1
 then raise exception 'RLS admin: expected authorized records missing'; end if;
end $$;

reset role;
rollback;