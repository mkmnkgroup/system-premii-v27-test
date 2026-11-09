"""Supabase Auth login gateway for the isolated test application.

Both Streamlit entrypoints enforce this gateway before rendering. Never display
private production data in the public test deployment.
"""
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import streamlit.components.v1 as components
import requests
import streamlit as st
from auth_rules import active_role, allowed_module, bind_user_session, clear_user_session

_recovery_callback = components.declare_component(
    "test_password_recovery", path=str(Path(__file__).parent / "recovery_component"))


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
    callback = _recovery_callback(key="_test_callback_component", default=None)
    if (isinstance(callback, dict) and callback.get("type") in ("recovery", "invite")
            and isinstance(callback.get("access_token"), str)
            and callback.get("transfer_id")
            and callback["transfer_id"] != st.session_state.get("_test_last_recovery_transfer")):
        st.session_state["_test_last_recovery_transfer"] = callback["transfer_id"]
        st.session_state["_test_recovery_token"] = callback["access_token"]
        st.session_state["_test_recovery_open"] = True
        st.session_state.pop("_test_auth_access_token", None)
        st.rerun()
    if not st.session_state.get("_test_recovery_open"):
        return
    _login_header()
    st.subheader("Ustaw hasło do konta")
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
                "token_hash": recovery_hash, "type": st.session_state.get("_test_recovery_kind", "recovery")})
            st.session_state.pop("_test_recovery_hash", None)
            if status == 200 and result.get("access_token"):
                st.session_state["_test_recovery_token"] = result["access_token"]
                st.session_state.pop("_test_auth_access_token", None)
                st.rerun()
            st.error("Link jest nieprawidłowy lub wygasł. Poproś o nową wiadomość.")
        st.stop()
    if not token:
        st.info("Otwórz najnowszy link zaproszenia lub odzyskiwania hasła z wiadomości e-mail. Jeśli automatyczny powrót nie działa, wklej link poniżej.")
        with st.form("_test_recovery_link_form", clear_on_submit=True):
            link = st.text_input("Link odzyskiwania z wiadomości", type="password")
            verify_link = st.form_submit_button("Zweryfikuj link")
        if verify_link:
            parsed = urlparse(link.strip())
            values = parse_qs(parsed.query)
            fragment = parse_qs(parsed.fragment)
            if (parsed.scheme == "https" and parsed.netloc == "bzpfukyugfuybqivjyoz.supabase.co"
                    and parsed.path == "/auth/v1/verify"
                    and values.get("type") in (["recovery"], ["invite"]) and values.get("token")):
                st.session_state["_test_recovery_hash"] = values["token"][0]
                st.session_state["_test_recovery_kind"] = values["type"][0]
                st.rerun()
            elif (parsed.scheme == "https" and parsed.netloc == "system-premii-v27-test.streamlit.app"
                    and fragment.get("type") in (["recovery"], ["invite"]) and fragment.get("access_token")):
                st.session_state["_test_recovery_token"] = fragment["access_token"][0]
                st.rerun()
            else:
                st.error("Wklej link zaproszenia lub odzyskiwania z najnowszej wiadomości dla aplikacji testowej.")
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


def _login_header():
    st.title("System Premii 2.7")
    st.caption("Środowisko testowe · Dostęp tylko dla upoważnionych użytkowników")


def login_gate():
    st.set_page_config(page_title="System Premii 2.7 — Logowanie", layout="wide")
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
                if bind_user_session(st.session_state, user["id"]):
                    st.rerun()
                st.sidebar.write("Zalogowano:", user.get("email", ""))
                st.sidebar.write("Rola:", role)
                if st.sidebar.button("Wyloguj", key="_test_logout"):
                    _request("POST", "/auth/v1/logout", token=token)
                    clear_user_session(st.session_state)
                    st.rerun()
                if allowed_module(role, "test_workspace"):
                    if st.sidebar.button("👥 Administracja · Użytkownicy", key="_test_admin_button"):
                        st.session_state["_test_admin_panel"] = True
                    if st.session_state.get("_test_admin_panel"):
                        from admin_users import render_admin_panel
                        render_admin_panel()
                    return role
                _login_header()
                st.info("Konto aktywne. Panel tej roli jest przygotowywany; dane innych pracowników są niedostępne.")
                st.stop()
        clear_user_session(st.session_state)
    _login_header()
    if st.button("Mam link odzyskiwania hasła"):
        st.session_state["_test_recovery_open"] = True
        st.rerun()
    with st.form("_test_login_form", clear_on_submit=True):
        email = st.text_input("E-mail", autocomplete="email")
        password = st.text_input("Hasło", type="password", autocomplete="current-password")
        submit = st.form_submit_button("Zaloguj się")
    if submit:
        status, data = _request("POST", "/auth/v1/token?grant_type=password",
                                data={"email": email.strip(), "password": password})
        if status == 200 and data.get("access_token"):
            clear_user_session(st.session_state)
            st.session_state["_test_auth_access_token"] = data["access_token"]
            st.rerun()
        else:
            st.error("Nieprawidłowe dane logowania lub konto nie jest aktywne.")
    st.stop()


if __name__ == "__main__":
    login_gate()
