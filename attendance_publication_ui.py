"""TEST attendance publication: administrator preview and explicit confirmation."""
import requests
import pandas as pd
import streamlit as st

from admin_users import api as user_api
from attendance_publication import prepare_attendance_preview, AttendancePublicationError
from test_schedule_drafts import _request as draft_api, draft_item_key, safe_period

ENDPOINT = "https://bzpfukyugfuybqivjyoz.supabase.co/functions/v1/test-attendance-publish"


def publication_api(action, period, **extra):
    token = st.session_state.get("_test_auth_access_token")
    if not isinstance(token, str) or not token:
        return False, {"error": "Zaloguj się ponownie."}
    try:
        anon = str(st.secrets["TEST_SUPABASE_ANON_KEY"])
        response = requests.post(
            ENDPOINT,
            headers={"Authorization": "Bearer " + token, "apikey": anon,
                     "Content-Type": "application/json"},
            json={"action": action, "period": period, **extra},
            timeout=25,
        )
        payload = response.json()
        if not isinstance(payload, dict):
            return False, {"error": "Nieprawidłowa odpowiedź serwera."}
        return response.status_code == 200, payload
    except (requests.RequestException, ValueError, KeyError, FileNotFoundError):
        return False, {"error": "Nie udało się połączyć z usługą publikacji."}


def render_attendance_publication(year, month):
    """Read only the SAVED draft, not potentially unsaved local cell edits."""
    st.divider()
    with st.expander("Publikacja ewidencji obecności pracownikom · TEST"):
        st.caption(
            "Ta czynność jest oddzielna od zapisywania szkicu. "
            "Pracownik zobaczy tylko swoje dni. Dyrektor nie zobaczy danych osobowych. "
            "Opublikowanego miesiąca nie da się nadpisać."
        )
        period = safe_period(year, month) + "-01"
        ok, status = publication_api("status", period)
        if not ok:
            st.error(status.get("error", "Nie można pobrać statusu publikacji."))
            return
        if status.get("published"):
            data = status.get("publication") or {}
            st.success(
                "Ewidencja już opublikowana: "
                + str(data.get("entry_count", "?"))
                + " wpisów, "
                + str(data.get("employee_count", "?"))
                + " pracowników. Powtórna publikacja zablokowana."
            )
            return

        key = draft_item_key(year, month, "attendance")
        ok, saved = draft_api("read", key)
        if not ok:
            st.error(saved.get("error", "Nie można wczytać szkicu."))
            return
        if not saved.get("found"):
            st.info("Najpierw zapisz ewidencję obecności w Supabase.")
            return
        revision = saved.get("revision")
        if not isinstance(revision, int) or revision < 1:
            st.error("Nieprawidłowy numer wersji szkicu.")
            return
        ok, users = user_api("list")
        if not ok or not isinstance(users.get("users"), list):
            st.error("Nie można pobrać przypisań pracowników do kont.")
            return

        try:
            table, counts, n_users = prepare_attendance_preview(
                period, saved.get("payload"), users["users"]
            )
        except AttendancePublicationError as exc:
            st.warning(str(exc))
            st.info(
                "Przypisz pracowników do aktywnych kont w panelu Administracja · "
                "Użytkownicy. Identyfikator musi odpowiadać kolumnie OSOBA."
            )
            return

        st.markdown(f"**Zapisana wersja: {revision} · Wpisy: {len(table)} · Konta: {n_users}**")
        cols = st.columns(4)
        for c, label in zip(cols, (
            "Potwierdzona obecność", "Nieobecność", "Niepotwierdzony", "Wolne"
        )):
            c.metric(label, counts.get(label, 0))
        st.dataframe(pd.DataFrame(table), hide_index=True, use_container_width=True)
        st.warning(
            "Niepotwierdzony dzień pozostanie niepotwierdzony. "
            "Z godzin wejścia i wyjścia nie wyliczamy czasu pracy bez danych o przerwach. "
            "Dni bez zatwierdzenia również mogą zostać opublikowane jako niepotwierdzone."
        )
        approved = st.checkbox(
            "Sprawdziłem przypisania kont, dni, godziny i oznaczenia nieobecności. "
            "Zatwierdzam jednorazową publikację TEJ ZAPISANEJ wersji.",
            key="_test_attendance_approve_" + period + "_" + str(revision),
        )
        if st.button(
            "Opublikuj obecność pracownikom",
            disabled=not approved,
            type="primary",
            key="_test_attendance_publish_" + period + "_" + str(revision),
        ):
            result_ok, result = publication_api(
                "publish", period,
                confirm="PUBLIKUJ_OBECNOSC",
                expected_revision=revision,
            )
            if result_ok:
                st.success("Ewidencja została opublikowana pracownikom.")
                st.rerun()
            else:
                st.error(result.get("error", "Publikacja nie powiodła się."))
