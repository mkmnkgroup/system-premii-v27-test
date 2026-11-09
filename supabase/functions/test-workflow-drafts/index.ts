import { createClient } from "npm:@supabase/supabase-js@2.58.0";

const PROJECT_URL = "https://bzpfukyugfuybqivjyoz.supabase.co";
const KEY = /^(settings_v27|archive_v27|draft_v27:[0-9]{4}-(0[1-9]|1[0-2]):(schedule|attendance|production|weights|bonuses|approval))$/;
const MAX_BODY_BYTES = 1600000;

function result(status: number, data: Record<string, unknown>) {
  return new Response(JSON.stringify(data), {
    status, headers: { "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

Deno.serve(async (req: Request) => {
  if (req.method !== "POST") return result(405, { error: "Niedozwolona metoda." });
  if (req.headers.get("content-type")?.split(";")[0]?.trim() !== "application/json") {
    return result(415, { error: "Oczekiwano JSON." });
  }
  const url = Deno.env.get("SUPABASE_URL")?.replace(/\/$/, "");
  const secret = Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
  const anon = Deno.env.get("SUPABASE_ANON_KEY");
  if (url !== PROJECT_URL || !secret || !anon) {
    return result(503, { error: "Niekompletna konfiguracja testowej bazy." });
  }
  const auth = req.headers.get("Authorization") ?? "";
  if (!/^Bearer [A-Za-z0-9_\-.]+$/.test(auth)) return result(401, { error: "Brak poprawnej sesji." });
  const token = auth.slice(7);
  try {
    const identityClient = createClient(url, anon, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: identity, error: identityError } = await identityClient.auth.getUser(token);
    if (identityError || !identity.user?.id || identity.user.is_anonymous) {
      return result(401, { error: "Sesja wygasła." });
    }
    const db = createClient(url, secret, { auth: { persistSession: false, autoRefreshToken: false } });
    const { data: profile, error: profileError } = await db.from("app_user_profiles")
      .select("role,enabled").eq("user_id", identity.user.id).maybeSingle();
    // The legacy Streamlit workspace is restricted to admin. Other roles
    // cannot import, publish or alter these drafts during this phase.
    if (profileError || !profile || profile.enabled !== true || profile.role !== "admin") {
      return result(403, { error: "Brak uprawnień do zapisu roboczego." });
    }
    const bodyText = await req.text();
    if (new TextEncoder().encode(bodyText).length > MAX_BODY_BYTES) {
      return result(413, { error: "Zbyt duża paczka danych roboczych." });
    }
    let body: any;
    try { body = JSON.parse(bodyText); } catch (_) { return result(400, { error: "Nieprawidłowe dane JSON." }); }
    if (!body || typeof body !== "object" || Array.isArray(body) || !KEY.test(body.item_key)) {
      return result(400, { error: "Nieprawidłowy klucz danych." });
    }
    if (body.action === "read") {
      const { data, error } = await db.from("v27_test_workflow_drafts")
        .select("payload,revision,updated_at").eq("item_key", body.item_key).maybeSingle();
      if (error) return result(503, { error: "Nie można odczytać zapisanej wersji." });
      return result(200, { found: !!data, revision: data?.revision ?? null,
                           payload: data?.payload ?? null, updated_at: data?.updated_at ?? null });
    }
    if (body.action !== "write") return result(400, { error: "Nieznana operacja." });
    if (!body.payload || typeof body.payload !== "object" || Array.isArray(body.payload)) {
      return result(400, { error: "Dane do zapisu muszą być obiektem." });
    }
    const revision = body.expected_revision;
    if (revision !== null && (!Number.isSafeInteger(revision) || revision < 1)) {
      return result(400, { error: "Błędna rewizja danych." });
    }
    if (revision === null) {
      const { data, error } = await db.from("v27_test_workflow_drafts").insert({
        item_key: body.item_key, payload: body.payload, revision: 1,
        updated_by: identity.user.id,
      }).select("revision").maybeSingle();
      if (error) {
        return error.code === "23505"
          ? result(409, { error: "Dane zmieniły się w innej sesji — najpierw odczytaj aktualną wersję." })
          : result(503, { error: "Nie można zapisać danych." });
      }
      return result(200, { revision: data?.revision ?? 1, message: "Zapisano szkic." });
    }
    const { data, error } = await db.from("v27_test_workflow_drafts")
      .update({ payload: body.payload, revision: revision + 1,
        updated_by: identity.user.id, updated_at: new Date().toISOString() })
      .eq("item_key", body.item_key).eq("revision", revision)
      .select("revision").maybeSingle();
    if (error) return result(503, { error: "Nie można zapisać danych." });
    if (!data) return result(409, { error: "Ktoś zmienił dane. Odczytaj aktualną wersję przed ponownym zapisem." });
    return result(200, { revision: data.revision, message: "Zapisano szkic." });
  } catch (_) {
    return result(503, { error: "Testowa usługa zapisu jest chwilowo niedostępna." });
  }
});
