"""Test-only administrator view; all permissions are enforced again by Supabase Edge Function.

The browser never receives a service-role key. Calls use the verified user's
short-lived Supabase Auth access token and cannot bypass server-side rules.
"""
import requests
import streamlit as st

PROJECT_URL = "https://bzpfukyugfuybqivjyoz.supabase.co"
FUNCTION_URL = PROJECT_URL + "/functions/v1/test-user-admin"
ROLE_NAMES = {
    "admin": "Administrator",
    "director": "Dyrektor",
    "manager": "Kierownik",
    "employee": "Pracownik",
}


def api(action, **payload):
    """Call admin-only Edge Function without logging credentials or responses."""
    token = st.session_state.get("_test_auth_access_token")
    if not isinstance(token, str) or not token:
        return False, {"error": "Zaloguj się ponownie."}
    try:
        public_key = st.secrets["TEST_SUPABASE_ANON_KEY"]
        response = requests.post(
            FUNCTION_URL,
            headers={
                "Authorization": "Bearer " + token,
                "apikey": str(public_key),
                "Content-Type": "application/json",
            },
            json={"action": action, **payload},
            timeout=18,
        )
        result = response.json()
        if not isinstance(result, dict):
            return False, {"error": "Nieprawidłowa odpowiedź serwera."}
        return response.status_code == 200, result
    except (requests.RequestException, ValueError, KeyError, FileNotFoundError):
        return False, {"error": "Nie można połączyć się z serwerem administracyjnym."}


def render_admin_panel():
    st.title("Administracja · Użytkownicy")
    st.caption("System Premii 2.7 — odizolowane środowisko testowe")
    if st.button("← Wróć do aplikacji", key="_admin_back"):
        st.session_state["_test_admin_panel"] = False
        st.rerun()
    ok, response = api("list")
    if not ok:
        st.error(response.get("error", "Nie udało się pobrać listy użytkowników."))
        st.stop()
    users = response.get("users")
    if not isinstance(users, list):
        st.error("Nieprawidłowa lista użytkowników.")
        st.stop()
    st.subheader("Konta użytkowników")
    for item in users:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("user_id", ""))
        if not uid:
            continue
        with st.expander(f"{item.get('email', 'Brak e-mail')} · {ROLE_NAMES.get(item.get('role'), 'Nieznana rola')}" +
                         (" · Aktywny" if item.get("enabled") else " · Zablokowany")):
            with st.form("edit_user_" + uid):
                current_role = item.get("role", "employee")
                if current_role not in ROLE_NAMES:
                    current_role = "employee"
                role = st.selectbox("Rola", list(ROLE_NAMES),
                                    index=list(ROLE_NAMES).index(current_role),
                                    format_func=lambda value: ROLE_NAMES[value])
                display_name = st.text_input("Nazwa wyświetlana", value=item.get("display_name") or "")
                employee_id = st.text_input("Identyfikator pracownika", value=item.get("employee_id") or "",
                                            help="W wersji testowej wpisz dokładnie nazwę z kolumny OSOBA rozliczenia. To przypisanie będzie weryfikowane przed publikacją.")
                enabled = st.checkbox("Konto aktywne", value=item.get("enabled") is True)
                submitted = st.form_submit_button("Zapisz zmiany")
            if submitted:
                success, result = api("update", user_id=uid, role=role,
                                      enabled=enabled, display_name=display_name,
                                      employee_id=employee_id)
                if success:
                    st.success("Zapisano.")
                    st.rerun()
                else:
                    st.error(result.get("error", "Nie zapisano zmian."))
    st.divider()
    st.subheader("Zaproś nowego użytkownika")
    st.caption("Użytkownik otrzyma wiadomość umożliwiającą ustawienie własnego hasła.")
    with st.form("_test_invite_form", clear_on_submit=True):
        email = st.text_input("E-mail nowego użytkownika")
        display_name = st.text_input("Imię i nazwisko (opcjonalnie)")
        employee_id = st.text_input("Identyfikator pracownika (opcjonalnie)", help="Wpisz dokładnie wartość z kolumny OSOBA rozliczenia testowego.")
        role = st.selectbox("Rola nowego użytkownika", list(ROLE_NAMES), index=3,
                            format_func=lambda value: ROLE_NAMES[value])
        invite = st.form_submit_button("Wyślij zaproszenie", type="primary")
    if invite:
        success, result = api("invite", email=email.strip(), role=role,
                              display_name=display_name, employee_id=employee_id)
        if success:
            st.success("Zaproszenie zostało wysłane.")
            st.rerun()
        else:
            st.error(result.get("error", "Nie udało się wysłać zaproszenia."))
    st.stop()
