import { createClient } from "npm:@supabase/supabase-js@2.58.0";

const PROJECT_URL = "https://bzpfukyugfuybqivjyoz.supabase.co";
const PERIOD = /^20[0-9]{2}-(0[1-9]|1[0-2])-01$/;
const SIZE_LIMIT = 1500;

function response(code: number, data: Record<string, unknown>) {
  return new Response(JSON.stringify(data), {
    status: code,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return response(405, { error: "Niedozwolona metoda." });
  if (req.headers.get("content-type")?.split(";")[0]?.trim() !== "application/json") {
    return response(415, { error: "Wymagany JSON." });
  }
  const url = Deno.env.get("SUPABASE_URL")?.replace(/\/$/, "");
  const anon = Deno.env.get("SUPABASE_ANON_KEY");
  const secret = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  if (url !== PROJECT_URL || !anon || !secret) {
    return response(503, { error: "Brak konfiguracji testowego środowiska." });
  }
  const authorization = req.headers.get("Authorization") ?? "";
  if (!/^Bearer [A-Za-z0-9_\-.]+$/.test(authorization)) {
    return response(401, { error: "Wymagane ponowne logowanie." });
  }
  try {
    const auth = createClient(url, anon, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
    const { data: verified, error: authError } = await auth.auth.getUser(authorization.slice(7));
    if (authError || !verified.user?.id || verified.user.is_anonymous) {
      return response(401, { error: "Niepoprawna lub wygasła sesja." });
    }
    const db = createClient(url, secret, {
      auth: { persistSession: false, autoRefreshToken: false },
    });
    const { data: profile, error: profileError } = await db
      .from("app_user_profiles")
      .select("role,enabled").eq("user_id", verified.user.id).maybeSingle();
    if (profileError || profile?.role !== "admin" || profile.enabled !== true) {
      return response(403, { error: "Operacja wymaga aktywnego administratora." });
    }

    const raw = await req.text();
    if (new TextEncoder().encode(raw).length > SIZE_LIMIT) {
      return response(413, { error: "Zbyt duże żądanie." });
    }
    let body: any;
    try { body = JSON.parse(raw); } catch (_) {
      return response(400, { error: "Niepoprawne dane JSON." });
    }
    if (!body || typeof body !== "object" || Array.isArray(body) ||
        typeof body.period !== "string" || !PERIOD.test(body.period)) {
      return response(400, { error: "Niepoprawny miesiąc." });
    }
    if (body.action === "status") {
      const { data, error } = await db.from("v27_test_attendance_publications")
        .select("period,employee_count,entry_count,published_at,draft_revision")
        .eq("period", body.period).maybeSingle();
      if (error) return response(503, { error: "Nie można pobrać statusu publikacji." });
      return response(200, { published: !!data, publication: data ?? null });
    }
    if (body.action !== "publish" || body.confirm !== "PUBLIKUJ_OBECNOSC" ||
        !Number.isSafeInteger(body.expected_revision) || body.expected_revision < 1) {
      return response(400, { error: "Brak potwierdzenia lub numeru wersji." });
    }
    // The database reads the immutable-by-revision draft itself. The client
    // cannot substitute records or select a different set of employees.
    const { data, error } = await db.rpc("v27_test_publish_attendance_month", {
      p_actor: verified.user.id,
      p_period: body.period,
      p_expected_revision: body.expected_revision,
    });
    if (error) {
      if (error.code === "23505") {
        return response(409, { error: "Ten miesiąc jest już opublikowany." });
      }
      return response(422, { error: "Publikacja odrzucona. Sprawdź wersję szkicu, godziny i przypisania kont." });
    }
    return response(200, { publication: data, message: "Ewidencja obecności została opublikowana." });
  } catch (_) {
    return response(503, { error: "Usługa publikacji obecności jest niedostępna." });
  }
});
