"""Test-only administrator view; all permissions are enforced again by Supabase Edge Function.

The browser never receives a service-role key. Calls use the verified user's
short-lived Supabase Auth access token and cannot bypass server-side rules.
"""
import requests
from datetime import datetime

import pandas as pd
import streamlit as st

from employee_account_links import (
    analyze_account_links, names_from_attendance_draft, normalized_employees,
    validate_quick_link,
)

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


MONTH_LABELS = (
    "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
    "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień",
)


def _source_employees(year, month):
    """Use the stored month being published, never an assumed default roster."""
    from test_schedule_drafts import (
        _request as draft_api, draft_item_key, decode_schedule_payload,
    )

    ok, attendance = draft_api("read", draft_item_key(year, month, "attendance"))
    if not ok:
        return None, None, "Nie można odczytać ewidencji z Supabase. Sprawdź połączenie."
    if attendance.get("found"):
        try:
            names = names_from_attendance_draft(
                attendance.get("payload"), year, month
            )
        except (ValueError, TypeError, KeyError):
            return None, None, "Zapisana ewidencja jest uszkodzona; nie można bezpiecznie ocenić przypisań."
        return names, "zapisana ewidencja obecności", None

    ok, draft = draft_api("read", draft_item_key(year, month))
    if not ok:
        return None, None, "Nie można odczytać harmonogramu z Supabase."
    if draft.get("found"):
        try:
            schedule = decode_schedule_payload(draft.get("payload"), year, month)
            names = normalized_employees(schedule["OSOBA"].tolist())
        except (ValueError, KeyError, TypeError):
            return None, None, "Zapisany harmonogram jest uszkodzony."
        return names, "zapisany harmonogram", None

    # Fallback is explicitly marked as local, never a stored record.
    period_label = f"{MONTH_LABELS[month - 1]} {year}"
    frame = st.session_state.get("current_schedule_df")
    if (isinstance(frame, pd.DataFrame) and not frame.empty
            and st.session_state.get("schedule_period_key") == period_label
            and "OSOBA" in frame.columns):
        return normalized_employees(frame["OSOBA"].tolist()), "harmonogram w tej sesji (niezapisany)", None
    employees = st.session_state.get("employees_df")
    if isinstance(employees, pd.DataFrame) and "OSOBA" in employees.columns:
        return normalized_employees(employees["OSOBA"].tolist()), "lista pracowników w tej sesji (niezapisana)", None
    return None, None, (
        "Nie ma zapisanego harmonogramu ani ewidencji za wybrany miesiąc. "
        "Przygotuj i zapisz harmonogram, aby sprawdzić powiązania."
    )


def render_employee_links(users):
    """Admin-only preflight with a strictly explicit safe assignment action."""
    st.subheader("Powiązania pracowników z kontami")
    st.caption(
        "Sprawdź przypisania przed publikacją. Weryfikacja dotyczy konkretnego miesiąca "
        "i nie publikuje ani nie zmienia danych automatycznie."
    )
    left, right = st.columns([2, 1])
    default_month = st.session_state.get("erp_period_month")
    index = MONTH_LABELS.index(default_month) if default_month in MONTH_LABELS else datetime.now().month - 1
    with left:
        month_name = st.selectbox(
            "Miesiąc kontroli", list(MONTH_LABELS), index=index, key="_admin_link_month",
        )
    with right:
        year = int(st.number_input(
            "Rok kontroli", min_value=2020, max_value=2100,
            value=int(st.session_state.get("erp_period_year", datetime.now().year)),
            step=1, key="_admin_link_year",
        ))
    month = MONTH_LABELS.index(month_name) + 1
    names, source, error = _source_employees(year, month)
    if error:
        st.warning(error)
        return
    if not names:
        st.info("Nie znaleziono pracowników do sprawdzenia w wybranym miesiącu.")
        return

    rows, counts, unassigned_accounts = analyze_account_links(names, users)
    st.caption(f"Podstawa kontroli: {source} · {month_name} {year}")
    a, b, c = st.columns(3)
    a.metric("Pracownicy", counts["total"])
    b.metric("Powiązani", counts["linked"])
    c.metric("Wymagają poprawy", counts["issues"])

    st.dataframe(
        pd.DataFrame(rows), hide_index=True, use_container_width=True,
        column_config={
            "Pracownik": st.column_config.TextColumn("Pracownik"),
            "Status": st.column_config.TextColumn("Stan powiązania"),
            "Konto": st.column_config.TextColumn("Konto e-mail"),
            "Rola": st.column_config.TextColumn("Rola"),
        },
    )
    if counts["issues"] == 0:
        st.success("Wszyscy pracownicy mają po jednym aktywnym, poprawnie przypisanym koncie.")
        return
    st.warning(
        f"{counts['issues']} z {counts['total']} pracowników wymaga poprawienia powiązania "
        "przed publikacją. Zablokowane, niewłaściwe lub zdublowane konta można "
        "naprawić w sekcji „Konta użytkowników” poniżej."
    )
    missing = [r["Pracownik"] for r in rows if r["Status"] == "Brak przypisania"]
    if not missing or not unassigned_accounts:
        st.caption(
            "Jeśli nie ma wolnego konta, użyj formularza zaproszenia na dole strony "
            "albo popraw identyfikator pracownika w istniejącym koncie."
        )
        return

    st.markdown("#### Szybkie przypisanie wolnego konta")
    st.caption(
        "Pokazywane są wyłącznie aktywne konta bez przypisanego pracownika. "
        "Nie zmieniamy automatycznie kont już powiązanych z inną osobą."
    )
    employee = st.selectbox(
        "Pracownik bez konta", missing, key="_admin_link_employee",
    )
    account_options = {str(u["user_id"]): u for u in unassigned_accounts}
    account_id = st.selectbox(
        "Wolne aktywne konto", list(account_options),
        format_func=lambda uid: str(account_options[uid].get("email") or "Konto bez e-mail"),
        key="_admin_link_account",
    )
    if st.button("Przypisz wybrane konto", key="_admin_link_save", type="primary"):
        # Re-fetch immediately before assignment to avoid overwriting a mapping
        # already created in a different admin session.
        ok, fresh = api("list")
        if not ok or not isinstance(fresh.get("users"), list):
            st.error("Nie można ponownie zweryfikować listy kont. Nie zapisano zmian.")
            return
        try:
            account = validate_quick_link(employee, account_id, names, fresh["users"])
        except ValueError as exc:
            st.error(str(exc))
            return
        success, result = api(
            "update", user_id=str(account["user_id"]),
            role=account["role"], enabled=True,
            display_name=str(account.get("display_name") or ""),
            employee_id=employee,
        )
        if success:
            st.success("Powiązanie zostało zapisane. Odświeżam listę.")
            st.rerun()
        else:
            st.error(result.get("error", "Nie udało się zapisać powiązania."))


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
    render_employee_links(users)
    st.divider()
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
