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


def decode_schedule_payload(payload, year, month):
    """Validate saved schedule before replacing the current session."""
    if (not isinstance(payload, dict)
            or payload.get("format_version") != 1
            or payload.get("period") != safe_period(year, month)):
        raise ValueError("Nieobsługiwany format harmonogramu.")
    frame = _decode(payload["schedule"])
    required = {"OSOBA", "DATA", "DZIEŃ PRACUJĄCY/WOLNY", "CZAS ZMIANY"}
    if not isinstance(frame, pd.DataFrame) or not required.issubset(frame.columns):
        raise ValueError("Niekompletny harmonogram.")
    if frame.empty:
        raise ValueError("Pusty harmonogram.")
    dates = pd.to_datetime(frame["DATA"].astype(str), format="%d.%m.%Y", errors="coerce")
    if dates.isna().any() or any(d.strftime("%Y-%m") != safe_period(year, month) for d in dates):
        raise ValueError("Harmonogram zawiera daty z innego miesiąca.")
    return frame


def decode_archive_payload(payload):
    """Reject damaged monthly payroll archives without touching local state."""
    if not isinstance(payload, dict) or payload.get("format_version") != 1:
        raise ValueError("Nieobsługiwany format archiwum.")
    archive = _decode(payload["archive"])
    if not isinstance(archive, dict) or any(
        not isinstance(period, str) or not isinstance(record, dict)
        or not isinstance(record.get("summary"), pd.DataFrame)
        or not isinstance(record.get("schedule"), pd.DataFrame)
        or not isinstance(record.get("metrics"), dict)
        for period, record in archive.items()
    ):
        raise ValueError("Uszkodzony zapis archiwum.")
    return archive


def _save_schedule_snapshot(key, slot, year, month, display_period, expected_revision):
    """Save current screen without publishing; server enforces revision locking."""
    frame = st.session_state.get("current_schedule_df")
    if (not isinstance(frame, pd.DataFrame) or frame.empty
            or st.session_state.get("schedule_period_key") != display_period):
        st.error("Najpierw przygotuj poprawny harmonogram wybranego miesiąca.")
        return False
    payload = {
        "schedule": _encode(frame),
        "period": safe_period(year, month),
        "format_version": 1,
    }
    try:
        # Reject saving a graph for the wrong month or incomplete schedule.
        decode_schedule_payload(payload, year, month)
    except (ValueError, TypeError, KeyError):
        st.error("Nie zapisano: harmonogram jest niekompletny lub zawiera daty z innego miesiąca.")
        return False
    ok, result = _request("write", key, payload=payload,
                          expected_revision=expected_revision)
    if not ok:
        st.error(result.get("error",
                            "Nie zapisano harmonogramu. Sprawdź, czy w bazie nie ma nowszej wersji."))
        return False
    revision = result.get("revision")
    if type(revision) is not int or revision < 1:
        st.error("Serwer nie potwierdził numeru zapisanej wersji. Sprawdź stan bazy.")
        return False
    st.session_state[slot] = revision
    if st.session_state.get("_schedule_local_changes_period") == display_period:
        st.session_state.pop("_schedule_local_changes_period", None)
    st.toast("Zapisano harmonogram w Supabase. Pracownicy nie otrzymali publikacji.", icon="✅")
    return True


@st.dialog("Zastąpić istniejący zapis harmonogramu?")
def _confirm_schedule_draft_overwrite(key, slot, year, month, display_period, expected_revision):
    """Require an informed decision, then re-check revision before writing."""
    st.warning(
        f"W Supabase jest już harmonogram za **{display_period}** "
        f"(wersja {expected_revision}). Zapisanie bieżącego grafiku zastąpi tę wersję."
    )
    st.caption(
        "Jeśli wolisz wcześniejszy grafik, wybierz Anuluj, a następnie "
        "„Przywróć szkic z Supabase”. Stary zapis możesz wcześniej wyeksportować. "
        "Publikacja pracownikom jest oddzielną czynnością."
    )
    left, right = st.columns(2)
    with left:
        if st.button("Anuluj", key="cancel_saved_schedule_overwrite", use_container_width=True):
            st.rerun()
    with right:
        if st.button(
            "Tak, zastąp zapis w bazie", type="primary",
            key="confirm_saved_schedule_overwrite", use_container_width=True,
        ):
            ok, latest = _request("read", key)
            if not ok:
                st.error(latest.get("error", "Nie można sprawdzić aktualnego zapisu."))
                return
            if not latest.get("found") or latest.get("revision") != expected_revision:
                st.error(
                    "W międzyczasie zapis w bazie został zmieniony. "
                    "Nie nadpisano go. Sprawdź najnowszą wersję."
                )
                return
            if _save_schedule_snapshot(
                key, slot, year, month, display_period, expected_revision
            ):
                st.rerun()


def render_schedule_draft(year, month, display_period):
    """Save current month or deliberately restore a saved private schedule."""
    key = draft_item_key(year, month)
    slot = _slot(key)
    st.divider()
    st.markdown("#### Zapis harmonogramu · Supabase TEST")
    st.caption("Szkic jest prywatny. Zapisanie grafiku nie publikuje go pracownikom.")
    if st.session_state.get("_schedule_local_changes_period") == display_period:
        st.info(
            "Masz nowo wygenerowany grafik w tej sesji. "
            "Aby go zachować, wybierz „Zapisz aktualny harmonogram”. "
            "Przywrócenie szkicu pobierze wcześniejszy grafik i zastąpi ten na ekranie."
        )
    col_save, col_load = st.columns(2)
    with col_save:
        save = st.button("💾 Zapisz aktualny harmonogram", key="_save_" + key)
    with col_load:
        restore = st.button("📂 Przywróć szkic z Supabase", key="_restore_" + key)

    if save:
        frame = st.session_state.get("current_schedule_df")
        if not isinstance(frame, pd.DataFrame) or frame.empty:
            st.warning("Najpierw przygotuj harmonogram.")
            return
        existing_revision = st.session_state.get(slot)
        if existing_revision is not None and (
            type(existing_revision) is not int or existing_revision < 1
        ):
            st.error("Nieznana wersja szkicu. Przywróć zapis z bazy.")
            return
        # A newly generated graph requires explicit consent before overwriting
        # an old server draft, even if its revision is already known locally.
        if (existing_revision is None or
                st.session_state.get("_schedule_local_changes_period") == display_period):
            ok, existing = _request("read", key)
            if not ok:
                st.error(existing.get("error", "Nie można sprawdzić zapisu w bazie."))
                return
            if existing.get("found"):
                server_revision = existing.get("revision")
                if type(server_revision) is not int or server_revision < 1:
                    st.error("Nieznana wersja szkicu na serwerze. Nie zapisano zmian.")
                    return
                if existing_revision is not None and server_revision != existing_revision:
                    st.error(
                        "W bazie jest nowszy szkic niż ostatnio używany. "
                        "Nie nadpisano go. Przywróć i porównaj wersje."
                    )
                    return
                _confirm_schedule_draft_overwrite(
                    key, slot, year, month, display_period, server_revision
                )
                return
            if existing_revision is not None:
                st.error("W bazie nie ma już zapisanego szkicu. Odśwież dane przed zapisem.")
                return
        _save_schedule_snapshot(
            key, slot, year, month, display_period, existing_revision
        )

    if restore:
        ok, result = _request("read", key)
        if not ok:
            st.error(result.get("error", "Nie można odczytać szkicu."))
            return
        if not result.get("found"):
            st.info("Brak zapisanego szkicu za ten miesiąc.")
            return
        try:
            frame = decode_schedule_payload(result.get("payload"), year, month)
        except (ValueError, TypeError, KeyError):
            st.error("Nie można odtworzyć harmonogramu. Zapis ma błędny format lub miesiąc.")
            return
        st.session_state.current_schedule_df = frame
        st.session_state["_test_schedule_editor_generation"] = (
            st.session_state.get("_test_schedule_editor_generation", 0) + 1
        )
        st.session_state.schedule_period_key = display_period
        st.session_state[slot] = result["revision"]
        if st.session_state.get("_schedule_local_changes_period") == display_period:
            st.session_state.pop("_schedule_local_changes_period", None)
        st.toast("Przywrócono harmonogram z bazy. Nie opublikowano go pracownikom.", icon="✅")
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
        try:
            archive = decode_archive_payload(result.get("payload"))
        except (TypeError, ValueError, KeyError):
            st.error("Nieprawidłowy zapis archiwum; bieżące dane nie zostały zmienione.")
            return
        st.session_state.history_v2 = archive
        st.session_state[slot] = result["revision"]
        st.success("Przywrócono archiwum robocze.")
        st.rerun()
