import { createClient } from "npm:@supabase/supabase-js@2.58.0";

const PROJECT_URL = "https://bzpfukyugfuybqivjyoz.supabase.co";
const PERIOD = /^20[0-9]{2}-(0[1-9]|1[0-2])-01$/;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const MAX_SIZE = 16000;

function reply(code: number, data: Record<string, unknown>) {
  return new Response(JSON.stringify(data), {
    status: code,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return reply(405, { error: "Niedozwolona metoda." });
  if (req.headers.get("content-type")?.split(";")[0].trim() !== "application/json") {
    return reply(415, { error: "Wymagany JSON." });
  }
  const url = Deno.env.get("SUPABASE_URL")?.replace(/\/$/, "");
  const secret = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const anon = Deno.env.get("SUPABASE_ANON_KEY");
  if (url !== PROJECT_URL || !secret || !anon) {
    return reply(503, { error: "Brak bezpiecznej konfiguracji testowej bazy." });
  }
  const auth = req.headers.get("Authorization") ?? "";
  if (!/^Bearer [A-Za-z0-9_\-.]+$/.test(auth)) {
    return reply(401, { error: "Zaloguj się ponownie." });
  }
  try {
    const authClient = createClient(url, anon, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: verified, error: invalid } = await authClient.auth.getUser(auth.slice(7));
    if (invalid || !verified.user?.id || verified.user.is_anonymous) {
      return reply(401, { error: "Sesja wygasła." });
    }
    const db = createClient(url, secret, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: profile, error: profileError } = await db.from("app_user_profiles")
      .select("role,enabled").eq("user_id", verified.user.id).maybeSingle();
    if (profileError || !profile || profile.role !== "admin" || profile.enabled !== true) {
      return reply(403, { error: "Publikować może wyłącznie aktywny administrator." });
    }
    const text = await req.text();
    if (new TextEncoder().encode(text).length > MAX_SIZE) {
      return reply(413, { error: "Zbyt dużo danych publikacji." });
    }
    let body: any;
    try {
      body = JSON.parse(text);
    } catch (_) {
      return reply(400, { error: "Błędny JSON." });
    }
    if (!body || typeof body !== "object" || Array.isArray(body) || !PERIOD.test(body.period)) {
      return reply(400, { error: "Nieprawidłowy okres publikacji." });
    }
    if (body.action === "status") {
      const { data, error } = await db.from("v27_test_publications")
        .select("period,published_at,employee_count")
        .eq("period", body.period).maybeSingle();
      if (error) return reply(503, { error: "Nie udało się sprawdzić publikacji." });
      return reply(200, { already_published: !!data, publication: data ?? null });
    }
    if (body.action !== "publish") return reply(400, { error: "Nieznana operacja." });
    if (body.confirm !== "PUBLIKUJ" || !Array.isArray(body.employees) ||
      body.employees.length < 1 || body.employees.length > 50 ||
      !body.kpis || typeof body.kpis !== "object" || Array.isArray(body.kpis)) {
      return reply(400, { error: "Brak potwierdzenia lub niekompletne dane." });
    }
    const seen = new Set<string>();
    for (const employee of body.employees) {
      if (!employee || typeof employee !== "object" ||
        typeof employee.user_id !== "string" || !UUID.test(employee.user_id) ||
        typeof employee.employee_name !== "string" ||
        employee.employee_name.length < 3 || employee.employee_name.length > 150 ||
        seen.has(employee.user_id)) {
        return reply(400, { error: "Nieprawidłowe lub powtarzające się przypisania pracowników." });
      }
      seen.add(employee.user_id);
    }
    // A single transactional Postgres function creates the immutable marker,
    // team KPIs and ALL individual slips, or none of them.
    const { data, error } = await db.rpc("v27_test_publish_month", {
      p_actor: verified.user.id,
      p_period: body.period,
      p_kpis: body.kpis,
      p_employees: body.employees,
    });
    if (error) {
      // Do not leak internal database errors, data or employee identifiers.
      if (error.code === "23505") {
        return reply(409, { error: "Ten miesiąc został już opublikowany. Zmiany wymagają osobnej procedury korekty." });
      }
      return reply(422, { error: "Publikacja odrzucona. Sprawdź przypisania kont, kwoty oraz kompletność danych." });
    }
    return reply(200, { message: "Opublikowano zatwierdzone wyniki.", publication: data });
  } catch (_) {
    return reply(503, { error: "Publikowanie jest chwilowo niedostępne." });
  }
});
