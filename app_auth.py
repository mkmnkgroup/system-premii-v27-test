"""Supabase Auth login gateway for the isolated test application.

Both Streamlit entrypoints enforce this gateway before rendering. Never display
private production data in the public test deployment.
"""
import requests
import streamlit as st
from auth_rules import active_role


def _config():
    try:
        url = str(st.secrets["TEST_SUPABASE_URL"]).rstrip("/")
        key = str(st.secrets["TEST_SUPABASE_ANON_KEY"])
    except (KeyError, FileNotFoundError):
        st.error("Logowanie testowe nie jest jeszcze skonfigurowane.")
        st.stop()
    if url != "https://bzpfukyugfuybqivjyoz.supabase.co" or not key:
        st.error("Błędna konfiguracja izolowanego środowiska testowego.")
        st.stop()
    return url, key


def _request(method, path, *, token=None, data=None):
    url, key = _config()
    headers = {"apikey": key, "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    try:
        response = requests.request(method, url + path, headers=headers,
                                    json=data, timeout=12)
        return response.status_code, response.json()
    except (requests.RequestException, ValueError):
        return 0, {}



def _password_recovery():
    """Exchange only a recovery token; never expose a session in the URL."""
    if st.query_params.get("recovery") == "1":
        recovery_hash = st.query_params.get("token_hash", "")
        st.session_state.pop("_test_recovery_hash", None)
        st.session_state.pop("_test_recovery_token", None)
        st.query_params.clear()
        st.session_state["_test_recovery_open"] = True
        if recovery_hash:
            st.session_state["_test_recovery_hash"] = recovery_hash
        st.rerun()
    if not st.session_state.get("_test_recovery_open"):
        return
    st.subheader("Ustaw nowe hasło")
    if st.button("Wróć do logowania"):
        for key in list(st.session_state):
            if key.startswith("_test_recovery_"):
                del st.session_state[key]
        st.rerun()
    recovery_hash = st.session_state.get("_test_recovery_hash")
    token = st.session_state.get("_test_recovery_token")
    if recovery_hash and not token:
        st.caption("Potwierdź, że chcesz wykorzystać jednorazowy link z wiadomości.")
        if st.button("Potwierdź link odzyskiwania"):
            status, result = _request("POST", "/auth/v1/verify", data={
                "token_hash": recovery_hash, "type": "recovery"})
            st.session_state.pop("_test_recovery_hash", None)
            if status == 200 and result.get("access_token"):
                st.session_state["_test_recovery_token"] = result["access_token"]
                st.session_state.pop("_test_auth_access_token", None)
                st.rerun()
            st.error("Link jest nieprawidłowy lub wygasł. Poproś o nową wiadomość.")
        st.stop()
    if not token:
        st.info("Otwórz najnowszy link odzyskiwania hasła z wiadomości e-mail.")
        st.stop()
    status, user = _request("GET", "/auth/v1/user", token=token)
    if status != 200 or not user.get("id"):
        st.session_state.pop("_test_recovery_token", None)
        st.error("Sesja odzyskiwania wygasła. Poproś o nową wiadomość.")
        st.stop()
    with st.form("_test_recovery_password_form", clear_on_submit=True):
        password = st.text_input("Nowe hasło", type="password", autocomplete="new-password")
        confirmation = st.text_input("Powtórz nowe hasło", type="password", autocomplete="new-password")
        submit = st.form_submit_button("Zapisz nowe hasło")
    if submit:
        if len(password) < 12:
            st.error("Hasło musi mieć co najmniej 12 znaków.")
        elif password != confirmation:
            st.error("Podane hasła różnią się.")
        else:
            status, result = _request("PUT", "/auth/v1/user", token=token,
                                      data={"password": password})
            if status == 200 and result.get("id") == user["id"]:
                _request("POST", "/auth/v1/logout", token=token)
                for key in list(st.session_state):
                    if key.startswith("_test_recovery_"):
                        del st.session_state[key]
                st.session_state["_test_password_changed"] = True
                st.rerun()
            st.error("Nie udało się zapisać hasła. Spróbuj innego hasła lub poproś o nowy link.")
    st.stop()


def login_gate():
    st.set_page_config(page_title="System Premii 2.7 — Logowanie", layout="wide")
    st.title("System Premii 2.7")
    st.caption("Środowisko testowe · Dostęp tylko dla upoważnionych użytkowników")
    _password_recovery()
    if st.session_state.pop("_test_password_changed", False):
        st.success("Hasło zostało zmienione. Zaloguj się nowym hasłem.")
    token = st.session_state.get("_test_auth_access_token")
    if token:
        status, user = _request("GET", "/auth/v1/user", token=token)
        if status == 200 and user.get("id"):
            status, profiles = _request(
                "GET", "/rest/v1/app_user_profiles?select=user_id,role,enabled,employee_id&user_id=eq." + user["id"],
                token=token)
            role = active_role(user, profiles) if status == 200 else None
            if role:
                st.sidebar.write("Zalogowano:", user.get("email", ""))
                st.sidebar.write("Rola:", role)
                if st.sidebar.button("Wyloguj", key="_test_logout"):
                    _request("POST", "/auth/v1/logout", token=token)
                    st.session_state.pop("_test_auth_access_token", None)
                    st.rerun()
                if role != "admin":
                    st.info("Konto aktywne. Panel roli jest przygotowywany; dane innych pracowników są niedostępne.")
                    st.stop()
                # Do not expose the legacy full-access UI until its data storage
                # is migrated to per-user authorization.
                st.info("Zalogowano jako administrator. Trwa przygotowanie bezpiecznego panelu.")
                st.stop()
        st.session_state.pop("_test_auth_access_token", None)
    with st.form("_test_login_form"):
        email = st.text_input("E-mail", autocomplete="email")
        password = st.text_input("Hasło", type="password", autocomplete="current-password")
        submit = st.form_submit_button("Zaloguj się")
    if submit:
        status, data = _request("POST", "/auth/v1/token?grant_type=password",
                                data={"email": email.strip(), "password": password})
        if status == 200 and data.get("access_token"):
            st.session_state["_test_auth_access_token"] = data["access_token"]
            st.rerun()
        else:
            st.error("Nieprawidłowe dane logowania lub konto nie jest aktywne.")
    st.stop()


if __name__ == "__main__":
    login_gate()
