"""Explicit, admin-only versioned schedule draft saving for the test application.

The old Streamlit UI still calculates and edits schedules in memory. Nothing
is published to employee-visible data; saving a draft is a separate action.
"""
import pandas as pd
import requests
import streamlit as st

from db_storage import _encode, _decode


PROJECT_URL = "https://bzpfukyugfuybqivjyoz.supabase.co"
ENDPOINT = PROJECT_URL + "/functions/v1/test-workflow-drafts"


def safe_period(year, month):
    year = int(year)
    month = int(month)
    if not 2000 <= year <= 2100 or not 1 <= month <= 12:
        raise ValueError("Nieprawidłowy miesiąc.")
    return f"{year:04d}-{month:02d}"


def draft_item_key(year, month, stage="schedule"):
    if stage not in ("schedule", "attendance", "bonuses", "approval"):
        raise ValueError("Nieprawidłowy etap procesu.")
    return f"draft_v27:{safe_period(year, month)}:{stage}"


def _request(action, key, *, payload=None, expected_revision=None):
    token = st.session_state.get("_test_auth_access_token")
    if not isinstance(token, str) or not token:
        return False, {"error": "Zaloguj się ponownie."}
    body = {"action": action, "item_key": key}
    if action == "write":
        body.update(payload=payload, expected_revision=expected_revision)
    try:
        public_key = str(st.secrets["TEST_SUPABASE_ANON_KEY"])
        result = requests.post(
            ENDPOINT,
            headers={
                "Authorization": "Bearer " + token,
                "apikey": public_key,
                "Content-Type": "application/json",
            },
            json=body,
            timeout=20,
        )
        data = result.json()
        if not isinstance(data, dict):
            return False, {"error": "Nieprawidłowa odpowiedź serwera."}
        return result.status_code == 200, data
    except (requests.RequestException, ValueError, KeyError, FileNotFoundError):
        return False, {"error": "Nie udało się nawiązać połączenia z testową bazą."}


def _slot(key):
    # Revision is bound both to the current logged-in identity and period.
    return "_test_saved_draft_revision_" + key.replace(":", "_")


def render_schedule_draft(year, month, display_period):
    """Save or explicitly restore one month's schedule. Never auto-publish."""
    key = draft_item_key(year, month)
    slot = _slot(key)
    st.divider()
    st.markdown("#### Trwały szkic harmonogramu · Supabase TEST")
    st.caption(
        "Zapis jest oddzielny od publikacji dla pracowników. "
        "W bazie przechowywany jest wyłącznie szkic wybranego miesiąca."
    )
    col_save, col_load = st.columns(2)
    with col_save:
        save = st.button("💾 Zapisz szkic w Supabase", key="_save_" + key)
    with col_load:
        restore = st.button("📂 Przywróć szkic z Supabase", key="_restore_" + key)

    if save:
        frame = st.session_state.get("current_schedule_df")
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            st.warning("Najpierw przygotuj harmonogram.")
            return
        existing_revision = st.session_state.get(slot)
        if existing_revision is None:
            ok, existing = _request("read", key)
            if not ok:
                st.error(existing.get("error", "Nie można sprawdzić wcześniejszego zapisu."))
                return
            if existing.get("found"):
                st.warning(
                    "W bazie istnieje już szkic za ten miesiąc. "
                    "Użyj „Przywróć szkic”, aby najpierw odczytać najnowszą wersję."
                )
                return
        payload = {
            "schedule": _encode(frame),
            "period": safe_period(year, month),
            "format_version": 1,
        }
        ok, result = _request("write", key, payload=payload,
                              expected_revision=existing_revision)
        if ok:
            st.session_state[slot] = result["revision"]
            st.success("Szkic harmonogramu zapisano w testowej bazie Supabase.")
        else:
            st.error(result.get("error", "Nie zapisano szkicu."))

    if restore:
        ok, result = _request("read", key)
        if not ok:
            st.error(result.get("error", "Nie można odczytać szkicu."))
            return
        if not result.get("found"):
            st.info("Brak zapisanego szkicu za ten miesiąc.")
            return
        payload = result.get("payload") or {}
        if (not isinstance(payload, dict)
                or payload.get("format_version") != 1
                or payload.get("period") != safe_period(year, month)):
            st.error("Zapisany szkic ma nieobsługiwany format.")
            return
        try:
            frame = _decode(payload["schedule"])
        except (KeyError, ValueError, TypeError):
            st.error("Nie można odtworzyć harmonogramu.")
            return
        required = {"OSOBA", "DATA", "DZIEŃ PRACUJĄCY/WOLNY", "CZAS ZMIANY"}
        if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns):
            st.error("Niekompletny zapis harmonogramu.")
            return
        st.session_state.current_schedule_df = frame
        st.session_state.schedule_period_key = display_period
        st.session_state[slot] = result["revision"]
        st.success("Przywrócono zapisany harmonogram. Zmiany nie zostały opublikowane pracownikom.")
        st.rerun()

def render_archive_draft():
    """Persist all locally archived TEST monthly payroll results as a private draft.

    This does not make bonuses visible in the employee portal.
    """
    key = "archive_v27"
    slot = _slot(key)
    st.divider()
    st.markdown("#### Trwały szkic archiwum · Supabase TEST")
    st.caption(
        "Archiwum robocze może zawierać dane premiowe. "
        "Jest dostępne tylko administratorowi. Zapis nie publikuje pasków premiowych."
    )
    col_save, col_load = st.columns(2)
    with col_save:
        save = st.button("💾 Zapisz archiwum w Supabase", key="_save_archive_db")
    with col_load:
        restore = st.button("📂 Przywróć archiwum z Supabase", key="_restore_archive_db")
    if save:
        archive = st.session_state.get("history_v2")
        if not isinstance(archive, dict) or not archive:
            st.info("Nie ma jeszcze archiwalnych rozliczeń do zapisania.")
            return
        revision = st.session_state.get(slot)
        if revision is None:
            ok, existing = _request("read", key)
            if not ok:
                st.error(existing.get("error", "Nie można odczytać wersji archiwum."))
                return
            if existing.get("found"):
                st.warning(
                    "Zapisane archiwum już istnieje. Najpierw przywróć najnowszą wersję."
                )
                return
        payload = {"format_version": 1, "archive": _encode(archive)}
        ok, result = _request("write", key, payload=payload,
                              expected_revision=revision)
        if ok:
            st.session_state[slot] = result["revision"]
            st.success("Archiwum robocze zapisano. Paski pracowników nie zostały opublikowane.")
        else:
            st.error(result.get("error", "Nie udało się zapisać archiwum."))
    if restore:
        ok, result = _request("read", key)
        if not ok:
            st.error(result.get("error", "Nie można przywrócić archiwum."))
            return
        if not result.get("found"):
            st.info("W Supabase nie ma jeszcze zapisanego archiwum.")
            return
        payload = result.get("payload")
        if not isinstance(payload, dict) or payload.get("format_version") != 1:
            st.error("Nieobsługiwany format zapisanego archiwum.")
            return
        archive = _decode(payload.get("archive"))
        if not isinstance(archive, dict):
            st.error("Zapisane archiwum jest nieprawidłowe.")
            return
        st.session_state.history_v2 = archive
        st.session_state[slot] = result["revision"]
        st.success("Przywrócono archiwum robocze.")
        st.rerun()
