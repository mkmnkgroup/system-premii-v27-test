"""Supabase Auth login gateway for the isolated test application.

The Streamlit entrypoint must be app_auth.py, not app_v2.py. Never display
private production data in the public test deployment.
"""
import requests
import streamlit as st


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


def login_gate():
    st.set_page_config(page_title="System Premii 2.7 — Logowanie", layout="wide")
    st.title("System Premii 2.7")
    st.caption("Środowisko testowe · Dostęp tylko dla upoważnionych użytkowników")
    token = st.session_state.get("_test_auth_access_token")
    if token:
        status, user = _request("GET", "/auth/v1/user", token=token)
        if status == 200 and user.get("id"):
            status, profiles = _request(
                "GET", "/rest/v1/app_user_profiles?select=role,enabled,employee_id&user_id=eq." + user["id"],
                token=token)
            if status == 200 and len(profiles) == 1 and profiles[0].get("enabled"):
                role = profiles[0]["role"]
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
