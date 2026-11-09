import { createClient } from "npm:@supabase/supabase-js@2.58.0";

const PROJECT_URL = "https://bzpfukyugfuybqivjyoz.supabase.co";
const INVITE_REDIRECT = "https://system-premii-v27-test.streamlit.app/";
const ROLES = new Set(["admin", "director", "manager", "employee"]);
const ID_RX = /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const EMAIL_RX = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

function answer(status: number, data: Record<string, unknown>) {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}
function limitedText(value: unknown, limit: number): string | null | undefined {
  if (value === null || value === "") return null;
  if (typeof value !== "string") return undefined;
  const v = value.trim();
  return v.length <= limit ? (v || null) : undefined;
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return answer(405, { error: "Niedozwolona metoda." });
  if (req.headers.get("content-type")?.split(";")[0].trim() !== "application/json") {
    return answer(415, { error: "Wymagany JSON." });
  }
  const url = Deno.env.get("SUPABASE_URL")?.replace(/\/$/, "");
  const secret = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const anon = Deno.env.get("SUPABASE_ANON_KEY");
  if (url !== PROJECT_URL || !secret || !anon) {
    return answer(503, { error: "Konfiguracja testowego serwera jest niekompletna." });
  }
  const authorization = req.headers.get("Authorization") ?? "";
  if (!/^Bearer [A-Za-z0-9_\-.]+$/.test(authorization)) {
    return answer(401, { error: "Wymagane logowanie." });
  }
  const jwt = authorization.slice("Bearer ".length);
  try {
    const identityClient = createClient(url, anon, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: identity, error: identityError } = await identityClient.auth.getUser(jwt);
    if (identityError || !identity.user?.id || identity.user.is_anonymous) {
      return answer(401, { error: "Sesja wygasła lub jest nieprawidłowa." });
    }
    const supabase = createClient(url, secret, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: admin, error: roleError } = await supabase
      .from("app_user_profiles").select("user_id,role,enabled")
      .eq("user_id", identity.user.id).maybeSingle();
    if (roleError || !admin || admin.role !== "admin" || admin.enabled !== true) {
      return answer(403, { error: "Tylko aktywny administrator może zarządzać kontami." });
    }
    let body: Record<string, unknown>;
    try {
      body = await req.json();
      if (!body || Array.isArray(body) || typeof body !== "object") {
        return answer(400, { error: "Nieprawidłowe dane." });
      }
    } catch (_) {
      return answer(400, { error: "Nieprawidłowy JSON." });
    }
    if (body.action === "list") {
      const { data, error } = await supabase.from("app_user_profiles")
        .select("user_id,email,display_name,employee_id,role,enabled,created_at")
        .order("email").limit(200);
      if (error) return answer(503, { error: "Nie można odczytać listy użytkowników." });
      return answer(200, { users: data ?? [], caller_id: identity.user.id });
    }
    if (body.action === "invite") {
      const email = typeof body.email === "string" ? body.email.trim().toLowerCase() : "";
      const role = body.role;
      const displayName = limitedText(body.display_name, 120);
      const employeeId = limitedText(body.employee_id, 128);
      if (!EMAIL_RX.test(email) || email.length > 254 || !ROLES.has(String(role))
          || displayName === undefined || employeeId === undefined) {
        return answer(400, { error: "Nieprawidłowy e-mail, rola lub dane pracownika." });
      }
      const { data: invite, error: inviteError } = await supabase.auth.admin.inviteUserByEmail(email, {
        redirectTo: INVITE_REDIRECT,
      });
      if (inviteError || !invite?.user?.id) {
        return answer(409, { error: "Nie udało się wysłać zaproszenia. Sprawdź adres i czy konto już istnieje." });
      }
      const { error: profileError } = await supabase.from("app_user_profiles").insert({
        user_id: invite.user.id,
        email,
        display_name: displayName,
        employee_id: employeeId,
        role,
        enabled: true,
      });
      if (profileError) {
        return answer(503, { error: "Zaproszenie wysłano, ale zapis profilu nie powiódł się. Skontaktuj się z administratorem bazy." });
      }
      return answer(200, { message: "Zaproszenie zostało wysłane.", email });
    }
    if (body.action === "update") {
      const id = body.user_id;
      const role = body.role;
      const enabled = body.enabled;
      const displayName = limitedText(body.display_name, 120);
      const employeeId = limitedText(body.employee_id, 128);
      if (typeof id !== "string" || !ID_RX.test(id) || !ROLES.has(String(role))
        || typeof enabled !== "boolean" || displayName === undefined || employeeId === undefined) {
        return answer(400, { error: "Nieprawidłowe dane użytkownika." });
      }
      const { data: previous, error: previousError } = await supabase.from("app_user_profiles")
        .select("user_id,role,enabled").eq("user_id", id).maybeSingle();
      if (previousError || !previous) return answer(404, { error: "Nie znaleziono konta." });
      // Existing administrators are immutable in this test phase to avoid
      // accidentally removing the last admin or simultaneous demotions.
      if (previous.role === "admin" && (role !== "admin" || enabled !== true)) {
        return answer(409, { error: "Zabezpieczenie: nie można dezaktywować ani zdegradować administratora." });
      }
      if (id === identity.user.id && (role !== "admin" || enabled !== true)) {
        return answer(409, { error: "Nie można zablokować własnego konta administratora." });
      }
      const { data: updated, error } = await supabase.from("app_user_profiles")
        .update({
          role, enabled, display_name: displayName, employee_id: employeeId,
          updated_at: new Date().toISOString(),
        })
        .eq("user_id", id)
        .select("user_id,email,display_name,employee_id,role,enabled").maybeSingle();
      if (error || !updated) return answer(503, { error: "Nie udało się zapisać zmian." });
      return answer(200, { user: updated, message: "Zmiany zapisane." });
    }
    return answer(400, { error: "Nieznana operacja." });
  } catch (_) {
    return answer(503, { error: "Operacja chwilowo niedostępna." });
  }
});
