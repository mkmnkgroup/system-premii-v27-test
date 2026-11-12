"""Fail-closed preview for attendance release, prior to server-side publication.

This parser is UX-only: the server always uses the saved, revision-locked
draft and enforces mappings/validation again in the transaction.
"""
from collections import Counter
from datetime import date
from uuid import UUID

from attendance_drafts import AttendanceDraftError, _day, _hours, _name, _optional_text, _time
from monthly_publication import canonical_name


class AttendancePublicationError(ValueError):
    pass


def prepare_attendance_preview(period, payload, profiles):
    if not isinstance(period, str) or len(period) != 10 or period[-3:] != "-01":
        raise AttendancePublicationError("Nieprawidłowy okres.")
    try:
        d = date.fromisoformat(period)
    except ValueError:
        raise AttendancePublicationError("Nieprawidłowy okres.") from None
    month = d.strftime("%Y-%m")
    if (not isinstance(payload, dict) or payload.get("period") != month
            or payload.get("format_version") != 1):
        raise AttendancePublicationError("Zapis nie odpowiada wybranemu miesiącowi.")
    entries = payload.get("entries")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 1500:
        raise AttendancePublicationError("Brak poprawnych wpisów obecności.")
    if not isinstance(profiles, list):
        raise AttendancePublicationError("Brak listy kont.")

    mapping = {}
    for profile in profiles:
        if (not isinstance(profile, dict) or profile.get("enabled") is not True
                or profile.get("role") not in ("admin", "manager", "employee")
                or not profile.get("employee_id")):
            continue
        try:
            name = canonical_name(profile["employee_id"])
            UUID(str(profile["user_id"]))
        except (ValueError, KeyError, TypeError):
            raise AttendancePublicationError("Błędne przypisanie użytkownika.") from None
        if name in mapping:
            raise AttendancePublicationError("Pracownik jest przypisany do kilku kont.")
        mapping[name] = profile

    seen = set()
    names = set()
    counts = Counter()
    preview = []
    for item in entries:
        if not isinstance(item, dict):
            raise AttendancePublicationError("Uszkodzony wpis w szkicu.")
        try:
            employee = _name(item["employee"])
            work_day = _day(item["work_day"], month)
            day_type = _optional_text(item["day_type"], "rodzaj dnia", 30)
            absence = _optional_text(item["absence"], "nieobecność", 120) or "Brak"
            start = _time(item["time_in"], "wejście")
            end = _time(item["time_out"], "wyjście")
            overtime = _hours(item["overtime_h"])
        except (AttendanceDraftError, KeyError, TypeError):
            raise AttendancePublicationError("Nieprawidłowe daty, godziny lub nieobecności.") from None

        name_key = canonical_name(employee)
        profile = mapping.get(name_key)
        if profile is None:
            raise AttendancePublicationError(
                f"Brak aktywnego, jednoznacznego konta dla pracownika: {employee}."
            )
        key = (profile["user_id"], work_day)
        if key in seen:
            raise AttendancePublicationError("Powtórzony wpis tego pracownika w tym dniu.")
        seen.add(key)
        names.add(profile["user_id"])
        if day_type not in ("Pracujący", "Wolny", "Święto"):
            raise AttendancePublicationError("Nieznany rodzaj dnia.")
        if day_type != "Pracujący":
            if absence != "Brak" or start or end or overtime:
                raise AttendancePublicationError("Dzień wolny zawiera sprzeczne wpisy.")
            status = "Wolne"
        elif absence != "Brak":
            if start or end or overtime:
                raise AttendancePublicationError("Nieobecność koliduje z godzinami lub nadgodzinami.")
            status = "Nieobecność"
        elif start and end:
            status = "Potwierdzona obecność"
        else:
            if overtime:
                raise AttendancePublicationError("Niepotwierdzony dzień ma nadgodziny.")
            status = "Niepotwierdzony"
        counts[status] += 1
        preview.append({
            "Pracownik": employee,
            "Konto": profile.get("email", ""),
            "Data": work_day,
            "Status": status,
            "Nieobecność": absence if status == "Nieobecność" else "",
            "Wejście": start,
            "Wyjście": end,
            "Nadgodziny": overtime,
        })
    if len(names) > 50:
        raise AttendancePublicationError("Przekroczono liczbę pracowników.")
    return preview, dict(counts), len(names)
