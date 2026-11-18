"""Accept verified absences and use scheduled hours for otherwise unrecorded days.

This is a user-confirmed *assumption*, not evidence of signatures or clock
scans. Only past working days with both actual clocks empty are filled. Actual
hours, partial records, absences, overtime and days off remain untouched.
"""
from datetime import date, datetime
import re

import pandas as pd

from attendance_validation import has_absence

BASIS_COLUMN = "PODSTAWA EWIDENCJI"
PLANNED_BASIS = "Przyjęto według planu"
MANUAL_BASIS = "Zmieniono ręcznie"
SHIFT_RE = re.compile(
    r"^\s*([01]?\d|2[0-3]):([0-5]\d)\s*[-–]\s*([01]?\d|2[0-3]):([0-5]\d)\s*$"
)


def _blank(value):
    if value is None:
        return True
    try:
        if bool(pd.isna(value)):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip() == ""


def _parse_shift(value):
    match = SHIFT_RE.fullmatch(str(value))
    if match is None:
        return None
    a, b, c, d = match.groups()
    return f"{int(a):02d}:{b}", f"{int(c):02d}:{d}"


def _parse_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value).strip(), "%d.%m.%Y").date()
    except (TypeError, ValueError):
        return None


def fill_according_to_plan(schedule, *, through):
    """Return (new_dataframe, statistics); do not mutate the original frame."""
    if not isinstance(schedule, pd.DataFrame) or schedule.empty:
        raise ValueError("Brak harmonogramu do uzupełnienia.")
    required = {
        "DATA", "OSOBA", "DZIEŃ PRACUJĄCY/WOLNY", "NIEOBECNOŚĆ",
        "CZAS ZMIANY", "FAKTYCZNIE WEJŚCIE", "FAKTYCZNIE WYJŚCIE",
    }
    if not required.issubset(schedule.columns):
        raise ValueError("Harmonogram nie zawiera wymaganych kolumn.")
    if not isinstance(through, date):
        raise ValueError("Nieprawidłowa data końcowa.")
    if through > date.today():
        raise ValueError("Nie można przyjmować obecności za przyszłe dni.")

    result = schedule.copy(deep=True)
    if BASIS_COLUMN not in result.columns:
        result[BASIS_COLUMN] = ""
    stats = {
        "filled": 0, "absences": 0, "free": 0, "existing": 0,
        "partial": 0, "future": 0, "invalid_shift": 0, "invalid_date": 0,
    }
    for index, row in result.iterrows():
        day = _parse_date(row["DATA"])
        if day is None:
            stats["invalid_date"] += 1
            continue
        if day > through:
            stats["future"] += 1
            continue
        if str(row["DZIEŃ PRACUJĄCY/WOLNY"]).strip() != "Pracujący":
            stats["free"] += 1
            continue
        if has_absence(row["NIEOBECNOŚĆ"]):
            stats["absences"] += 1
            continue

        missing_in = _blank(row["FAKTYCZNIE WEJŚCIE"])
        missing_out = _blank(row["FAKTYCZNIE WYJŚCIE"])
        if not (missing_in and missing_out):
            stats["partial" if missing_in != missing_out else "existing"] += 1
            continue

        shift = _parse_shift(row["CZAS ZMIANY"])
        if shift is None:
            stats["invalid_shift"] += 1
            continue
        result.at[index, "FAKTYCZNIE WEJŚCIE"] = shift[0]
        result.at[index, "FAKTYCZNIE WYJŚCIE"] = shift[1]
        result.at[index, BASIS_COLUMN] = PLANNED_BASIS
        stats["filled"] += 1
    return result, stats


def reconcile_attendance_basis(frame):
    """Never retain a planned-hours label after the user edits those hours."""
    if BASIS_COLUMN not in frame.columns:
        return frame
    result = frame.copy(deep=True)
    for index, row in result.iterrows():
        if row[BASIS_COLUMN] != PLANNED_BASIS:
            continue
        planned = _parse_shift(row.get("CZAS ZMIANY"))
        recorded = (str(row.get("FAKTYCZNIE WEJŚCIE", "")).strip(),
                    str(row.get("FAKTYCZNIE WYJŚCIE", "")).strip())
        if planned != recorded or has_absence(row.get("NIEOBECNOŚĆ")):
            result.at[index, BASIS_COLUMN] = MANUAL_BASIS
    return result


def reconcile_verified_absences(old_frame, new_frame):
    """Remove only previously ASSUMED clock times when absence is newly marked.

    Never clear manually entered timestamps or overtime.
    """
    if BASIS_COLUMN not in old_frame.columns:
        return new_frame
    result = new_frame.copy(deep=True)
    for index in result.index.intersection(old_frame.index):
        if (old_frame.at[index, BASIS_COLUMN] == PLANNED_BASIS
                and has_absence(result.at[index, "NIEOBECNOŚĆ"])):
            result.at[index, "FAKTYCZNIE WEJŚCIE"] = ""
            result.at[index, "FAKTYCZNIE WYJŚCIE"] = ""
            result.at[index, BASIS_COLUMN] = ""
    return result


def attendance_editor_column_order(frame):
    """Prioritize overtime, worker and day; make position the final column."""
    first = ["NADGODZINY (godz.)", "OSOBA", "DATA"]
    last = ["STANOWISKO"]
    keys = list(frame.columns)
    return (
        [key for key in first if key in keys]
        + [key for key in keys if key not in first and key not in last]
        + [key for key in last if key in keys]
    )
