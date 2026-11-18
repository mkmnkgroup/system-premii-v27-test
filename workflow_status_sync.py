"""Read-only server evidence for each TEST monthly workflow stage.

Reconnect-safe status lookup. It does not restore edited tables, publish payroll,
save snapshots, or grant access: all endpoints already enforce their own JWT
authorization. The result is isolated per authenticated admin and month.
"""
import time

import streamlit as st

CACHE_SECONDS = 90


def _draft_status(year, month, stage):
    from test_schedule_drafts import _request, draft_item_key, decode_schedule_payload
    key = draft_item_key(year, month, stage)
    ok, result = _request("read", key)
    if not ok or not isinstance(result, dict):
        return "unknown"
    if not result.get("found"):
        return "missing"
    revision = result.get("revision")
    if type(revision) is not int or revision < 1:
        return "unknown"
    payload = result.get("payload")
    if stage == "schedule":
        try:
            decode_schedule_payload(payload, year, month)
        except (ValueError, TypeError, KeyError):
            return "unknown"
    if stage == "attendance":
        period = f"{int(year):04d}-{int(month):02d}"
        if not isinstance(payload, dict) or payload.get("format_version") != 1:
            return "unknown"
        if payload.get("period") != period or not isinstance(payload.get("entries"), list):
            return "unknown"
        if not payload["entries"]:
            return "unknown"
    return "saved"


def _monthly_snapshot_status(uid, year, month):
    from test_draft_persistence import read_draft, DraftError
    # The auth UI's _config() intentionally calls st.stop() when Secrets are
    # missing. A read-only status probe must never abort the whole workspace.
    try:
        url = str(st.secrets["TEST_SUPABASE_URL"]).rstrip("/")
        anon_key = str(st.secrets["TEST_SUPABASE_ANON_KEY"])
        if url != "https://bzpfukyugfuybqivjyoz.supabase.co" or not anon_key:
            return "unknown"
        token = st.session_state["_test_auth_access_token"]
        period = f"{int(year):04d}-{int(month):02d}-01"
        saved = read_draft(url, anon_key, token, uid, period)
    except (DraftError, ValueError, KeyError, TypeError, FileNotFoundError):
        return "unknown"
    if not saved:
        return "missing"
    payload = saved["payload"]
    bonus = payload.get("bonus_inputs")
    if bonus is None:
        return "missing"
    # Older drafts may contain provisional bonus values but no saved proof of
    # pressing "Zapisz i przelicz dodatki". Never mark them as completed.
    return "saved" if payload.get("bonus_inputs_confirmed") is True else "draft"


def _archive_periods():
    from test_schedule_drafts import _request, decode_archive_payload
    ok, result = _request("read", "archive_v27")
    if not ok or not isinstance(result, dict):
        return None
    if not result.get("found"):
        return ()
    try:
        records = decode_archive_payload(result.get("payload"))
    except (ValueError, TypeError, KeyError):
        return None
    return tuple(str(period) for period in records.keys())


def _publication_status(period):
    from attendance_publication_ui import publication_api as attendance_api
    from month_publication_ui import publication_api as payroll_api
    try:
        a_ok, a = attendance_api("status", period)
        p_ok, p = payroll_api("status", period)
    except (ValueError, TypeError, KeyError, OSError):
        return "unknown", "unknown"
    return (
        ("published" if a.get("published") is True else "missing")
        if a_ok and isinstance(a, dict) else "unknown",
        ("published" if p.get("already_published") is True else "missing")
        if p_ok and isinstance(p, dict) else "unknown",
    )


def load_remote_workflow_status(year, month, display_period, *, refresh=False):
    """Fetch once per short-lived session cache; never infer a missing record on errors."""
    uid = st.session_state.get("_test_work_user_id")
    token = st.session_state.get("_test_auth_access_token")
    if not isinstance(uid, str) or not isinstance(token, str) or not token:
        return None
    from test_draft_persistence import check_identity, DraftError
    period = f"{int(year):04d}-{int(month):02d}-01"
    try:
        check_identity(uid, period)
    except (DraftError, ValueError):
        return None
    cache = st.session_state.setdefault("_workflow_status_cache", {})
    cache_key = uid + "/" + period
    now = time.monotonic()
    cached = cache.get(cache_key)
    if not refresh and cached and now - cached["at"] < CACHE_SECONDS:
        return cached["data"]

    schedule = _draft_status(year, month, "schedule")
    attendance = _draft_status(year, month, "attendance")
    bonuses = _monthly_snapshot_status(uid, year, month)
    periods = _archive_periods()
    attendance_pub, payroll_pub = _publication_status(period)
    result = {
        "schedule": schedule,
        "attendance": attendance,
        "bonuses": bonuses,
        "archive": ("saved" if display_period in periods else "missing")
                   if periods is not None else "unknown",
        "archived_periods": periods,
        "attendance_publication": attendance_pub,
        "payroll_publication": payroll_pub,
    }
    cache[cache_key] = {"at": now, "data": result}
    return result


def invalidate_remote_workflow_status(state, year=None, month=None):
    """Discard cached server evidence; the next rerun fetches a fresh status."""
    cache = state.get("_workflow_status_cache")
    if not isinstance(cache, dict):
        return
    uid = state.get("_test_work_user_id")
    if year is None or month is None:
        cache.clear()
        return
    cache.pop(str(uid) + f"/{int(year):04d}-{int(month):02d}-01", None)
