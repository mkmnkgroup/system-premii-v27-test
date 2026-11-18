"""Streamlit controls for authorized test-only monthly draft restoration.

Autosave is opt-in per active tab, and never starts before the user explicitly
saves or restores a draft. Only committed bonus inputs are included. The final
autosave pass runs after the active module rendered its edits.
"""
import time

import streamlit as st
from help_ui import help_icon
from workflow_help import DRAFT_HELP

from test_draft_persistence import (
    DraftError, DraftConflict, collect_draft, apply_draft, fingerprint,
    read_draft, save_draft, check_identity,
)


def _context(year, month):
    uid = st.session_state.get("_test_work_user_id")
    token = st.session_state.get("_test_auth_access_token")
    if not uid or not token:
        return None
    period = f"{int(year):04d}-{int(month):02d}-01"
    try:
        check_identity(uid, period)
    except DraftError:
        # No persistence without a real verified Supabase UUID.
        return None
    from app_auth import _config
    url, key = _config()
    return url, key, token, uid, period


def render_draft_controls(year, month, period_key):
    """Show safe save/restore controls, and fetch revision once per period."""
    context = _context(year, month)
    if context is None:
        return
    url, key, token, uid, period = context
    metadata = st.session_state.setdefault("_test_draft_status", {})
    if period not in metadata:
        try:
            remote = read_draft(url, key, token, uid, period)
            metadata[period] = {
                "revision": remote["revision"] if remote else 0,
                "exists": bool(remote),
                "restored": False,
                "autowrite": False,
                "saved_hash": "",
                "checked_at": time.monotonic(),
                "updated_at": remote.get("updated_at") if remote else None,
            }
        except DraftError:
            metadata[period] = {"error": True}
    meta = metadata[period]
    with st.expander("💾 Wersja robocza miesiąca", expanded=False):
        help_icon(DRAFT_HELP)
        if meta.get("error"):
            st.error("Brak łączności z zapisem. Dane pozostają wyłącznie w tej karcie.")
            return
        if meta["exists"] and not meta["restored"]:
            st.info("Znaleziono zapis z poprzedniej sesji. Przywróć go przed edycją.")
        elif meta["exists"]:
            st.caption("Zapisano — wersja " + str(meta["revision"]))
        else:
            st.caption("Nie znaleziono zapisu na serwerze.")
        if meta["updated_at"]:
            st.caption("Ostatni zapis (UTC): " + str(meta["updated_at"])[:19])

        if st.button("Przywróć zapis z bazy", key="draft_restore_" + period,
                     disabled=not meta["exists"], use_container_width=True):
            try:
                row = read_draft(url, key, token, uid, period)
                if not row:
                    raise DraftError("Zapis nie jest już dostępny.")
                apply_draft(st.session_state, row["payload"], period_key)
                meta.update(
                    revision=row["revision"], restored=True, exists=True,
                    autowrite=False, updated_at=row.get("updated_at"),
                    checked_at=time.monotonic(),
                )
                meta["saved_hash"] = fingerprint(collect_draft(st.session_state, period_key))
                st.toast("Wersja robocza została przywrócona.", icon="✅")
                st.rerun()
            except DraftError as exc:
                st.error(str(exc))
        if st.button("Zapisz wersję roboczą", key="draft_save_" + period,
                     disabled=meta["exists"] and not meta["restored"],
                     use_container_width=True, type="primary"):
            try:
                payload = collect_draft(st.session_state, period_key)
                result = save_draft(
                    url, key, token, uid, period, payload, meta["revision"],
                )
                meta.update(
                    revision=result["revision"], restored=True, exists=True,
                    updated_at=result.get("updated_at"), checked_at=time.monotonic(),
                    saved_hash=fingerprint(payload),
                )
                from workflow_status_sync import invalidate_remote_workflow_status
                invalidate_remote_workflow_status(st.session_state, year, month)
                st.toast("Zapisano wersję roboczą.", icon="✅")
                st.rerun()
            except DraftConflict as exc:
                meta.update(error=True)
                st.error(str(exc) + " Odśwież stronę i przywróć najnowszy zapis.")
            except DraftError as exc:
                st.error(str(exc))
        # Manual saving always works; automated saving is optional.
        if meta["exists"] and meta["restored"]:
            meta["autowrite"] = st.checkbox(
                "Autozapis w trakcie pracy", value=meta["autowrite"],
                key="draft_autosave_" + period,
                help="Co najmniej 15 s między zapisami, tylko przy zmianach "
                     "i przy kolejnym przeliczeniu strony.",
            )
        # Instrukcja odzyskiwania pracy jest dostępna przez ⓘ na górze panelu.


def autosave_draft(year, month, period_key):
    """Called after the active module so edits are captured in that rerun."""
    context = _context(year, month)
    if context is None:
        return
    url, key, token, uid, period = context
    meta = st.session_state.get("_test_draft_status", {}).get(period, {})
    if not meta.get("autowrite") or not meta.get("restored") or meta.get("error"):
        return
    if time.monotonic() - meta["checked_at"] < 15:
        return
    try:
        payload = collect_draft(st.session_state, period_key)
        hash_now = fingerprint(payload)
        if hash_now == meta["saved_hash"]:
            meta["checked_at"] = time.monotonic()
            return
        result = save_draft(
            url, key, token, uid, period, payload, meta["revision"],
        )
        meta.update(
            revision=result["revision"], saved_hash=hash_now,
            updated_at=result.get("updated_at"),
            checked_at=time.monotonic(),
        )
        from workflow_status_sync import invalidate_remote_workflow_status
        invalidate_remote_workflow_status(st.session_state, year, month)
    except DraftConflict:
        meta["autowrite"] = False
        meta["error"] = True
        st.error("Automatyczny zapis wstrzymany — wersja robocza została "
                 "zmieniona w innej karcie. Nie nadpisano jej.")
    except DraftError:
        meta["autowrite"] = False
        st.warning("Autozapis nie powiódł się. Użyj ręcznego zapisu "
                   "po przywróceniu połączenia.")
