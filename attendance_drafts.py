"""Persistent TEST attendance drafts stored separately from monthly work schedules.

These records are administrator-only DRAFTS and are never published to the
employee portal. An empty actual entry/exit is not proof of attendance.
"""
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re

import pandas as pd
import streamlit as st

from test_schedule_drafts import _request, _slot, draft_item_key, safe_period


ATTENDANCE_FIELDS = (
    "NIEOBECNOŚĆ", "FAKTYCZNIE WEJŚCIE", "FAKTYCZNIE WYJŚCIE",
    "NADGODZINY (godz.)",
)
REQUIRED_FIELDS = {"OSOBA", "DATA", "DZIEŃ PRACUJĄCY/WOLNY"}
VALID_DAY_TYPES = {"Pracujący", "Wolny", "Święto"}
TIME_FORMAT = re.compile(r"^([01][0-9]|2[0-3]):[0-5][0-9]$")


class AttendanceDraftError(ValueError):
    """Data are incomplete or cannot be safely matched to the local schedule."""


def _name(value):
    if not isinstance(value, str) or not value.strip():
        raise AttendanceDraftError("Brak nazwy pracownika.")
    text = " ".join(value.strip().split())
    if len(text) > 150:
        raise AttendanceDraftError("Za długa nazwa pracownika.")
    return text


def _day(value, period):
    try:
        if isinstance(value, datetime):
            day = value.date()
        elif isinstance(value, date):
            day = value
        elif isinstance(value, str):
            raw = value.strip()
            day = datetime.strptime(raw, "%d.%m.%Y").date() if "." in raw else date.fromisoformat(raw)
        else:
            raise ValueError()
    except (ValueError, TypeError):
        raise AttendanceDraftError("Błędna data w ewidencji obecności.") from None
    if day.strftime("%Y-%m") != period:
        raise AttendanceDraftError("Ewidencja zawiera dni z innego miesiąca.")
    return day.isoformat()


def _optional_text(value, label, max_length=120):
    if value is None:
        return ""
    if isinstance(value, str):
        text = value.strip()
    elif isinstance(value, (float, int)) and pd.isna(value):
        text = ""
    elif value is pd.NA or value is pd.NaT:
        text = ""
    else:
        raise AttendanceDraftError(f"Nieprawidłowe pole: {label}.")
    if len(text) > max_length:
        raise AttendanceDraftError(f"Za długie pole: {label}.")
    return text


def _time(value, label):
    if isinstance(value, datetime):
        value = value.time()
    if hasattr(value, "strftime") and not isinstance(value, str):
        value = value.strftime("%H:%M")
    text = _optional_text(value, label, 12)
    if not text:
        return ""
    if re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d:00", text):
        text = text[:5]
    if not TIME_FORMAT.fullmatch(text):
        raise AttendanceDraftError(f"Błędna godzina w polu: {label}. Wpisz GG:MM lub pozostaw puste.")
    return text


def _hours(value):
    try:
        if value is None or value is pd.NA or isinstance(value, bool):
            raise ValueError()
        amount = Decimal(str(value).replace(",", "."))
        if not amount.is_finite() or not 0 <= amount <= 24:
            raise ValueError()
        if amount.as_tuple().exponent < -2:
            raise ValueError()
        return float(amount)
    except (TypeError, ValueError, InvalidOperation):
        raise AttendanceDraftError("Nadgodziny muszą być liczbą od 0 do 24.") from None


def build_attendance_payload(schedule, year, month):
    """Return the full month snapshot, including unconfirmed working days."""
    period = safe_period(year, month)
    if not isinstance(schedule, pd.DataFrame) or schedule.empty:
        raise AttendanceDraftError("Brak harmonogramu do zapisania obecności.")
    if not REQUIRED_FIELDS.issubset(schedule.columns):
        raise AttendanceDraftError("Harmonogram nie zawiera wymaganych kolumn.")
    if len(schedule) > 1500:
        raise AttendanceDraftError("Za dużo wpisów w ewidencji miesiąca.")
    entries = []
    seen = set()
    for _, row in schedule.iterrows():
        name = _name(row["OSOBA"])
        day = _day(row["DATA"], period)
        day_type = _optional_text(row["DZIEŃ PRACUJĄCY/WOLNY"], "rodzaj dnia", 30)
        if day_type not in VALID_DAY_TYPES:
            raise AttendanceDraftError("Nieznany rodzaj dnia w harmonogramie.")
        key = (name.casefold(), day)
        if key in seen:
            raise AttendanceDraftError("Duplikat pracownika i daty w harmonogramie.")
        seen.add(key)
        absence = _optional_text(row.get("NIEOBECNOŚĆ", "Brak"), "nieobecność", 120) or "Brak"
        time_in = _time(row.get("FAKTYCZNIE WEJŚCIE", ""), "faktyczne wejście")
        time_out = _time(row.get("FAKTYCZNIE WYJŚCIE", ""), "faktyczne wyjście")
        overtime = _hours(row.get("NADGODZINY (godz.)", 0.0))
        entries.append({
            "employee": name, "work_day": day, "day_type": day_type,
            "absence": absence, "time_in": time_in, "time_out": time_out,
            "overtime_h": overtime,
        })
    return {"format_version": 1, "period": period, "entries": entries}


def attendance_summary(payload):
    """Only paired actual entry/exit confirms recorded presence."""
    entries = payload["entries"]
    planned = [r for r in entries if r["day_type"] == "Pracujący"]
    confirmed = sum(bool(r["time_in"] and r["time_out"]) for r in planned)
    absence = sum(r["absence"] not in ("Brak", "") for r in planned)
    unconfirmed = sum(
        r["absence"] in ("Brak", "") and not (r["time_in"] and r["time_out"])
        for r in planned
    )
    return {"planned": len(planned), "confirmed": confirmed,
            "absent_entries": absence, "unconfirmed": unconfirmed}


def restore_attendance_payload(schedule, payload, year, month):
    """Return a copy only if all employee/date/day-type identities match."""
    period = safe_period(year, month)
    if not isinstance(payload, dict) or payload.get("format_version") != 1 or payload.get("period") != period:
        raise AttendanceDraftError("Nieprawidłowy okres lub format zapisu obecności.")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not entries or len(entries) > 1500:
        raise AttendanceDraftError("Uszkodzona ewidencja obecności.")
    current = build_attendance_payload(schedule, year, month)
    if len(current["entries"]) != len(entries):
        raise AttendanceDraftError("Skład harmonogramu różni się od zapisanego miesiąca.")
    saved = {}
    for item in entries:
        if not isinstance(item, dict):
            raise AttendanceDraftError("Błędna struktura zapisu obecności.")
        try:
            name = _name(item["employee"])
            day = _day(item["work_day"], period)
            day_type = _optional_text(item["day_type"], "rodzaj dnia", 30)
            absence = _optional_text(item["absence"], "nieobecność", 120) or "Brak"
            time_in = _time(item["time_in"], "faktyczne wejście")
            time_out = _time(item["time_out"], "faktyczne wyjście")
            overtime = _hours(item["overtime_h"])
        except KeyError:
            raise AttendanceDraftError("Niekompletny zapis obecności.") from None
        key = (name.casefold(), day)
        if key in saved:
            raise AttendanceDraftError("Zapis zawiera powtórzone dni.")
        saved[key] = (day_type, absence, time_in, time_out, overtime)

    result = schedule.copy(deep=True)
    for col in ATTENDANCE_FIELDS:
        if col not in result.columns:
            result[col] = "" if col != "NADGODZINY (godz.)" else 0.0
    for index, row in result.iterrows():
        key = (_name(row["OSOBA"]).casefold(), _day(row["DATA"], period))
        if key not in saved:
            raise AttendanceDraftError("Zapis zawiera innego pracownika lub datę.")
        day_type, absence, time_in, time_out, overtime = saved.pop(key)
        if day_type != row["DZIEŃ PRACUJĄCY/WOLNY"]:
            raise AttendanceDraftError("Zmienił się plan pracy. Przywróć najpierw właściwy harmonogram.")
        result.at[index, "NIEOBECNOŚĆ"] = absence
        result.at[index, "FAKTYCZNIE WEJŚCIE"] = time_in
        result.at[index, "FAKTYCZNIE WYJŚCIE"] = time_out
        result.at[index, "NADGODZINY (godz.)"] = overtime
    if saved:
        raise AttendanceDraftError("Zapis zawiera nadmiarowe wpisy.")
    return result


def render_attendance_draft(year, month, display_period):
    """Explicit versioned attendance save/restore; no employee publication."""
    st.divider()
    st.markdown("#### Ewidencja obecności · Trwały szkic Supabase TEST")
    st.caption(
        "Zapisuj faktyczne wejścia, wyjścia, nieobecności i nadgodziny. "
        "Puste godziny pozostają niepotwierdzone. Ten zapis NIE publikuje danych pracownikom."
    )
    if st.session_state.get("schedule_period_key") != display_period:
        st.warning("Najpierw wybierz i przywróć harmonogram właściwego miesiąca.")
        return
    frame = st.session_state.get("current_schedule_df")
    try:
        payload = build_attendance_payload(frame, year, month)
        stats = attendance_summary(payload)
    except AttendanceDraftError as exc:
        st.warning(str(exc))
        return

    a, b, c, d = st.columns(4)
    a.metric("Dni planowane", stats["planned"])
    b.metric("Potwierdzone wejście/wyjście", stats["confirmed"])
    c.metric("Wpisy nieobecności", stats["absent_entries"])
    d.metric("Niepotwierdzone dni", stats["unconfirmed"])
    st.caption("Po imporcie nieobecności użyj „Uzupełnij planowane godziny”, aby nanieść je do tabeli przed zapisem.")

    key = draft_item_key(year, month, "attendance")
    slot = _slot(key)
    save_col, load_col = st.columns(2)
    with save_col:
        save = st.button("💾 Zapisz ewidencję w Supabase", key="_save_" + key)
    with load_col:
        load = st.button("📂 Przywróć ewidencję z Supabase", key="_restore_" + key)

    if save:
        revision = st.session_state.get(slot)
        if revision is None:
            ok, existing = _request("read", key)
            if not ok:
                st.error(existing.get("error", "Nie można sprawdzić wersji ewidencji."))
                return
            if existing.get("found"):
                st.warning(
                    "Ewidencja tego miesiąca jest już zapisana. "
                    "Najpierw ją przywróć, aby nie nadpisać zmian z innej sesji."
                )
                return
        ok, result = _request("write", key, payload=payload, expected_revision=revision)
        if ok:
            st.session_state[slot] = result["revision"]
            st.success("Ewidencja obecności została trwale zapisana (szkic).")
        else:
            st.error(result.get("error", "Nie zapisano ewidencji."))
    if load:
        ok, result = _request("read", key)
        if not ok:
            st.error(result.get("error", "Nie można odczytać ewidencji."))
            return
        if not result.get("found"):
            st.info("Brak zapisanej ewidencji za ten miesiąc.")
            return
        try:
            restored = restore_attendance_payload(frame, result.get("payload"), year, month)
        except (AttendanceDraftError, KeyError, TypeError, ValueError) as exc:
            st.error(str(exc) or "Nie można przywrócić ewidencji.")
            return
        st.session_state.current_schedule_df = restored
        st.session_state["_test_schedule_editor_generation"] = (
            st.session_state.get("_test_schedule_editor_generation", 0) + 1
        )
        st.session_state[slot] = result["revision"]
        st.success("Przywrócono ewidencję obecności. Dane nie zostały opublikowane pracownikom.")
        st.rerun()
