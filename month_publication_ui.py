"""Administrator-only preview and explicit release of completed TEST monthly results.

The archive remains a draft until the admin reviews each account mapping
and confirms publication. Never automatically release an archived period.
"""
import requests
import pandas as pd
import streamlit as st

from admin_users import api as user_api
from monthly_publication import prepare_publication, PublicationValidationError, period_date

ENDPOINT = "https://bzpfukyugfuybqivjyoz.supabase.co/functions/v1/test-month-publish"


def publication_api(action, period, **values):
    token = st.session_state.get("_test_auth_access_token")
    if not isinstance(token, str) or not token:
        return False, {"error": "Zaloguj się ponownie."}
    try:
        apikey = str(st.secrets["TEST_SUPABASE_ANON_KEY"])
        response = requests.post(
            ENDPOINT,
            headers={
                "Authorization": "Bearer " + token,
                "apikey": apikey,
                "Content-Type": "application/json",
            },
            json={"action": action, "period": period, **values},
            timeout=25,
        )
        data = response.json()
        if not isinstance(data, dict):
            return False, {"error": "Nieprawidłowa odpowiedź serwera."}
        return response.status_code == 200, data
    except (requests.RequestException, ValueError, KeyError, FileNotFoundError):
        return False, {"error": "Nie można skontaktować się z usługą publikacji."}


def render_month_publication(label, archived_period):
    st.divider()
    st.subheader("Publikacja zatwierdzonego miesiąca · TEST")
    st.caption(
        "Ta operacja udostępnia pracownikom ich kwoty premiowe, a dyrektorowi wyłącznie "
        "zbiorcze statystyki. Nie można jej cofnąć ani wykonać ponownie dla tego samego miesiąca."
    )
    try:
        period = period_date(label)
    except PublicationValidationError as exc:
        st.error(str(exc))
        return

    status_ok, status = publication_api("status", period)
    if not status_ok:
        st.error(status.get("error", "Nie można zweryfikować stanu publikacji."))
        return
    if status.get("already_published"):
        publication = status.get("publication") or {}
        st.success(
            "Okres już opublikowany. Liczba kont: "
            + str(publication.get("employee_count", "?"))
            + ". Ponowna publikacja jest zablokowana."
        )
        return

    users_ok, listing = user_api("list")
    if not users_ok or not isinstance(listing.get("users"), list):
        st.error("Nie można odczytać aktualnych przypisań kont pracowników.")
        return
    try:
        published_period, kpis, rows = prepare_publication(
            label, archived_period, listing["users"]
        )
    except PublicationValidationError as exc:
        st.warning(str(exc))
        st.info(
            "Najpierw przypisz każdemu pracownikowi osobne, aktywne konto "
            "w „Administracja · Użytkownicy”. W polu „Identyfikator pracownika” "
            "wpisz dokładnie wartość z kolumny „OSOBA” rozliczenia."
        )
        return

    if any(row.get("bonus_breakdown") is None for row in rows):
        st.warning(
            "Ten zapis archiwalny nie zawiera szczegółowych składników premii. "
            "Aby pracownicy mogli zweryfikować wszystkie dodatki, otwórz kalkulator "
            "i zapisz rozliczenie ponownie. Publikacja niepełnego paska została zablokowana."
        )
        return

    st.markdown("**Zbiorcze wskaźniki za okres**")
    c1, c2, c3 = st.columns(3)
    c1.metric("Pozycje", kpis["positions"])
    c2.metric("Sztuki", kpis["pieces"])
    c3.metric("Waga (kg)", kpis["weight_kg"])
    st.caption("Wynik względem średnich: " + kpis["performance_pct"] + "%")

    st.markdown("**Przypisanie indywidualnych pasków**")
    table = pd.DataFrame([{
        "Pracownik": row["employee_name"],
        "Konto użytkownika": next(
            (u.get("email") for u in listing["users"]
             if u.get("user_id") == row["user_id"]), "Nieznane"),
        "Premia główna (zł)": row["bonus_main_pln"],
        "Dodatki (zł)": row["bonus_additions_pln"],
        "Nadgodziny (h)": row["overtime_hours"],
        "Za nadgodziny (zł)": row["overtime_pay_pln"],
        "Wózek (zł)": row["bonus_breakdown"]["forklift_pay_pln"],
        "Palety (zł)": row["bonus_breakdown"]["pallet_pay_pln"],
        "Specjalne (zł)": str(sum(
            (pd.to_numeric(item["amount_pln"]) for item in
             row["bonus_breakdown"]["special_bonuses"]), 0
        )),
        "Premia bazowa (zł)": row["bonus_base_pln"],
        "Łącznie (zł)": row["bonus_final_pln"],
    } for row in rows])
    st.dataframe(table, hide_index=True, width="stretch")
    for row in rows:
        special = row["bonus_breakdown"]["special_bonuses"]
        if special:
            with st.expander("Premie specjalne — " + row["employee_name"]):
                for bonus in special:
                    st.write(
                        f'{bonus["amount_pln"]} zł — {bonus["reason"]}'
                        + (f' (przyznał: {bonus["approved_by"]})' if bonus.get("approved_by") else "")
                    )

    st.caption(
        "Archiwum nie zawiera potwierdzonych indywidualnych wyników "
        "pozycji/sztuk/masy. Nie zostaną one wymyślone ani wpisane jako zero. "
        "Dzienny wykaz obecności również wymaga osobnej publikacji po weryfikacji."
    )

    checkbox = st.checkbox(
        "Sprawdziłem wszystkie kwoty, miesiąc i przypisania kont. "
        "Zatwierdzam nieodwracalną publikację danych testowych.",
        key="_confirm_publish_" + published_period,
    )
    pressed = st.button(
        "Opublikuj wyniki tego miesiąca",
        disabled=not checkbox,
        type="primary",
        key="_publish_" + published_period,
    )
    if pressed:
        success, response = publication_api(
            "publish", published_period, confirm="PUBLIKUJ", kpis=kpis, employees=rows
        )
        if success:
            st.success("Opublikowano miesiąc i indywidualne paski premiowe.")
            st.rerun()
        else:
            st.error(response.get("error", "Serwer nie zaakceptował publikacji."))
