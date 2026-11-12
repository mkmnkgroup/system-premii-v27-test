"""Interpret schedule attendance without confusing planned work with recorded work.

Pure validation shared by the bonus calculator and the TEST publication preflight.
Two actual timestamps confirm a presence; an empty absence field never does.
"""
import re
from datetime import datetime, time

import pandas as pd


WORKING = "Pracujący"
DAY_TYPES = {WORKING, "Wolny", "Święto"}
NO_ABSENCE = {"", "brak", "none", "nan"}
CLOCK = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


class AttendanceValidationError(ValueError):
    """A day is inconsistent or lacks confirmation required for settlement."""


def has_absence(value):
    if value is None:
        return False
    try:
        if bool(pd.isna(value)):
            return False
    except (TypeError, ValueError):
        pass
    return str(value).strip().casefold() not in NO_ABSENCE


def actual_clock(value, label):
    if value is None:
        return ""
    try:
        if bool(pd.isna(value)):
            return ""
    except (TypeError, ValueError):
        pass
    if isinstance(value, (datetime, time)):
        text = value.strftime("%H:%M")
    else:
        text = str(value).strip()
    if not text:
        return ""
    if re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d:00", text):
        text = text[:5]
    if not CLOCK.fullmatch(text):
        raise AttendanceValidationError(f"Nieprawidłowa godzina w polu {label}: użyj GG:MM.")
    return text


def analyze_attendance(frame, *, require_complete=False):
    """Return counts and absent row indices for one employee.

    require_complete blocks publishing bonuses with unknown/partly observed days.
    Absence on a free day is not counted as a missed working day.
    """
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        raise AttendanceValidationError("Brak dni harmonogramu pracownika.")
    required = {"DATA", "DZIEŃ PRACUJĄCY/WOLNY", "NIEOBECNOŚĆ"}
    if not required.issubset(frame.columns):
        raise AttendanceValidationError("Harmonogram nie zawiera danych dnia lub nieobecności.")

    confirmed = absent = unconfirmed = planned = 0
    absent_indices = []
    seen_dates = set()
    for index, row in frame.iterrows():
        day = str(row["DATA"]).strip()
        if day in seen_dates:
            raise AttendanceValidationError("Powtórzony dzień w harmonogramie pracownika.")
        seen_dates.add(day)
        kind = str(row["DZIEŃ PRACUJĄCY/WOLNY"]).strip()
        if kind not in DAY_TYPES:
            raise AttendanceValidationError("Nieznany rodzaj dnia w harmonogramie.")
        absence = has_absence(row["NIEOBECNOŚĆ"])
        actual_in = actual_clock(row.get("FAKTYCZNIE WEJŚCIE", ""), "FAKTYCZNIE WEJŚCIE")
        actual_out = actual_clock(row.get("FAKTYCZNIE WYJŚCIE", ""), "FAKTYCZNIE WYJŚCIE")

        if kind != WORKING:
            if require_complete and (absence or actual_in or actual_out):
                raise AttendanceValidationError(
                    "Dzień wolny zawiera obecność lub nieobecność wymagającą ręcznego wyjaśnienia."
                )
            continue

        planned += 1
        if absence:
            if actual_in or actual_out:
                raise AttendanceValidationError(
                    "Jednoczesna nieobecność i faktyczna godzina pracy: popraw harmonogram."
                )
            absent += 1
            absent_indices.append(index)
        elif actual_in and actual_out:
            confirmed += 1
        else:
            unconfirmed += 1

    if require_complete and unconfirmed:
        raise AttendanceValidationError(
            f"Brakuje potwierdzenia wejścia i wyjścia dla {unconfirmed} dni roboczych. "
            "Nie można opublikować pełnego rozliczenia premii."
        )
    return {
        "planned": planned,
        "confirmed": confirmed,
        "absent": absent,
        "unconfirmed": unconfirmed,
        "absent_indices": tuple(absent_indices),
    }
