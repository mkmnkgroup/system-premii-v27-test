"""Build fail-closed publication payloads from the TEST archive.

No guessed account mapping, per-person production counts or missing attendance.
This module does not perform network access or publish anything.
"""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID

import pandas as pd
from attendance_validation import analyze_attendance, AttendanceValidationError

MONTHS = {
    "Styczeń": 1, "Luty": 2, "Marzec": 3, "Kwiecień": 4,
    "Maj": 5, "Czerwiec": 6, "Lipiec": 7, "Sierpień": 8,
    "Wrzesień": 9, "Październik": 10, "Listopad": 11, "Grudzień": 12,
}


class PublicationValidationError(ValueError):
    """Display-safe publication preflight error."""


def canonical_name(raw):
    if not isinstance(raw, str) or not raw.strip():
        raise PublicationValidationError("Brak identyfikatora pracownika.")
    return " ".join(raw.split()).casefold()


def period_date(label):
    try:
        month, year_text = label.split(" ")
        year = int(year_text)
        if month not in MONTHS or not 2000 <= year <= 2100:
            raise ValueError()
        return date(year, MONTHS[month], 1).isoformat()
    except (ValueError, AttributeError, TypeError):
        raise PublicationValidationError("Nieobsługiwany okres archiwum.") from None


def _decimal(value, label, *, nonnegative=True, places=2):
    try:
        if value is None or isinstance(value, bool):
            raise ValueError()
        result = Decimal(str(value))
        if not result.is_finite() or abs(result) > Decimal("1000000000"):
            raise ValueError()
        result = result.quantize(Decimal("0." + "0" * (places - 1) + "1"), rounding=ROUND_HALF_UP)
        if nonnegative and result < 0:
            raise ValueError()
        return result
    except (ValueError, InvalidOperation, TypeError):
        raise PublicationValidationError(f"Nieprawidłowa wartość: {label}.") from None


def _int(value, label, *, maximum=None):
    number = _decimal(value, label, places=0)
    if number != Decimal(str(value)):
        raise PublicationValidationError(f"Niecałkowita wartość: {label}.")
    number = int(number)
    if maximum is not None and number > maximum:
        raise PublicationValidationError(f"Przekroczony zakres: {label}.")
    return number


def prepare_publication(label, archive, profiles):
    """Return (period, aggregate KPI dict, personal rows) after all checks."""
    period = period_date(label)
    if not isinstance(archive, dict) or not isinstance(profiles, list):
        raise PublicationValidationError("Brak pełnych danych archiwalnych lub kont.")
    summary = archive.get("summary")
    schedule = archive.get("schedule")
    metrics = archive.get("metrics")
    special_source = archive.get("special_bonuses")
    if special_source is not None and not isinstance(special_source, pd.DataFrame):
        raise PublicationValidationError("Archiwum premii specjalnych jest nieprawidłowe.")
    if not isinstance(summary, pd.DataFrame) or summary.empty or len(summary) > 50:
        raise PublicationValidationError("Brak kompletnego rozliczenia pracowników.")
    if not isinstance(schedule, pd.DataFrame) or schedule.empty:
        raise PublicationValidationError("Brak zatwierdzonego harmonogramu w archiwum.")
    if not isinstance(metrics, dict):
        raise PublicationValidationError("Brak zbiorczych parametrów produkcji.")

    required_summary = {
        "Pracownik", "Premia (zł)", "ŁĄCZNA PREMIA / DODATKI (zł)",
        "% Potrącenia", "Dni przepracowane",
        "Nadgodziny (zł)", "Dodatek Wózek (zł)", "Dodatek Palety (zł)",
        "Premia Specjalna (zł)",
    }
    required_schedule = {"OSOBA", "DATA", "DZIEŃ PRACUJĄCY/WOLNY"}
    if not required_summary.issubset(summary.columns) or not required_schedule.issubset(schedule.columns):
        raise PublicationValidationError("Archiwum nie zawiera wymaganych pól.")
    # Never release attendance/bonus totals under a different calendar month.
    schedule_dates = pd.to_datetime(schedule["DATA"].astype(str), format="%d.%m.%Y", errors="coerce")
    if schedule_dates.isna().any() or any(day.strftime("%Y-%m") != period[:7] for day in schedule_dates):
        raise PublicationValidationError("Harmonogram pochodzi z innego miesiąca lub ma błędne daty.")

    kpis = {
        "positions": _int(metrics.get("lines"), "pozycje"),
        "pieces": _int(metrics.get("pcs"), "sztuki"),
        "weight_kg": str(_decimal(metrics.get("weight"), "masa towaru")),
        "performance_pct": str(_decimal(
            _decimal(metrics.get("indicator"), "wskaźnik wydajności", nonnegative=False, places=6) * 100,
            "wskaźnik wydajności", nonnegative=False,
        )),
    }

    mapping = {}
    for profile in profiles:
        if not isinstance(profile, dict) or not profile.get("enabled"):
            continue
        if profile.get("role") not in ("admin", "manager", "employee") or not profile.get("employee_id"):
            continue
        try:
            name = canonical_name(profile["employee_id"])
            uuid = str(UUID(str(profile["user_id"])))
        except (PublicationValidationError, KeyError, ValueError, TypeError, AttributeError):
            raise PublicationValidationError("Nieprawidłowe przypisanie konta pracownika.") from None
        if name in mapping:
            raise PublicationValidationError("Ten sam pracownik jest przypisany do wielu kont.")
        mapping[name] = uuid

    seen_names = set()
    seen_ids = set()
    rows = []
    for _, source in summary.iterrows():
        name = str(source["Pracownik"]).strip()
        normalized = canonical_name(name)
        if normalized in seen_names:
            raise PublicationValidationError("W archiwum występuje powtórzony pracownik.")
        seen_names.add(normalized)
        uid = mapping.get(normalized)
        if uid is None:
            raise PublicationValidationError(
                f"Pracownik „{name}” nie ma aktywnego konta z przypisanym identyfikatorem."
            )
        if uid in seen_ids:
            raise PublicationValidationError("Nie można przypisać wielu rozliczeń do jednego konta.")
        seen_ids.add(uid)

        main = _decimal(source["Premia (zł)"], "premia główna")
        total = _decimal(source["ŁĄCZNA PREMIA / DODATKI (zł)"], "premia końcowa")
        additions = sum(
            (_decimal(source[k], k) for k in (
                "Nadgodziny (zł)", "Dodatek Wózek (zł)", "Dodatek Palety (zł)",
                "Premia Specjalna (zł)",
            )), Decimal("0.00")
        )
        if abs(main + additions - total) > Decimal("0.01"):
            raise PublicationValidationError(f"Kwota premii pracownika „{name}” się nie sumuje.")
        deduction = _decimal(source["% Potrącenia"], "potrącenie za nieobecności")
        if deduction > 100:
            raise PublicationValidationError("Potrącenie przekracza 100%.")
        worked = _int(source["Dni przepracowane"], "dni obecności", maximum=31)
        own_schedule = schedule.loc[
            schedule["OSOBA"].map(lambda raw: canonical_name(str(raw))) == normalized
        ]
        if own_schedule.empty:
            raise PublicationValidationError(f"Brak harmonogramu dla pracownika „{name}”.")
        try:
            attendance = analyze_attendance(own_schedule, require_complete=True)
        except AttendanceValidationError as exc:
            raise PublicationValidationError(f"Pracownik „{name}”: {exc}") from None
        planned = attendance["planned"]
        overtime_pay = _decimal(source["Nadgodziny (zł)"], "kwota nadgodzin")
        raw_hours = source.get("Nadgodziny (godz.)")
        overtime_hours = None if raw_hours is None or pd.isna(raw_hours) else _decimal(raw_hours, "liczba nadgodzin")
        if overtime_hours is not None:
            if overtime_hours > 744 or (overtime_hours == 0 and overtime_pay > 0):
                raise PublicationValidationError("Niespójne godziny i kwota nadgodzin.")
            if "NADGODZINY (godz.)" in own_schedule.columns:
                confirmed_hours = sum((_decimal(v, "nadgodziny w ewidencji")
                                       for v in own_schedule["NADGODZINY (godz.)"]), Decimal("0"))
                if overtime_hours != confirmed_hours:
                    raise PublicationValidationError("Nadgodziny rozliczenia nie zgadzają się z ewidencją.")
        # Preserve genuine source details. Historic archives lacking them remain
        # marked unknown; no individual pallet count is fabricated.
        overtime_rate = (
            _decimal(source["Nadgodziny (stawka zł/h)"], "stawka nadgodzin")
            if "Nadgodziny (stawka zł/h)" in summary.columns else None
        )
        if overtime_rate is not None and overtime_hours is not None:
            if abs(overtime_hours * overtime_rate - overtime_pay) > Decimal("0.01"):
                raise PublicationValidationError("Niezgodna stawka i kwota nadgodzin.")

        forklift_pay = _decimal(source["Dodatek Wózek (zł)"], "dodatek za wózek")
        forklift_hours = (
            _decimal(source["Czas wózka (h)"], "czas wózka")
            if "Czas wózka (h)" in summary.columns else None
        )
        forklift_team_hours = (
            sum((_decimal(v, "łączny czas wózka") for v in summary["Czas wózka (h)"]),
                Decimal("0.00"))
            if "Czas wózka (h)" in summary.columns else None
        )
        if forklift_hours is not None and forklift_team_hours is not None:
            if forklift_hours > forklift_team_hours or (
                forklift_team_hours == 0 and forklift_pay != 0
            ):
                raise PublicationValidationError("Niespójny udział w pracy wózka.")

        pallet_pay = _decimal(source["Dodatek Palety (zł)"], "dodatek za palety")
        pallet_team_count = (
            _decimal(metrics["pallets"], "liczba palet zespołu")
            if metrics.get("pallets") is not None else None
        )
        pallet_rate = (
            _decimal(metrics["pallet_rate_pln"], "stawka za paletę")
            if metrics.get("pallet_rate_pln") is not None else None
        )
        pallet_recipients = (
            _int(metrics["pallet_recipient_count"], "liczba osób w podziale", maximum=50)
            if metrics.get("pallet_recipient_count") is not None else None
        )
        if (pallet_team_count is not None and pallet_rate is not None
                and pallet_recipients is not None):
            if pallet_recipients == 0:
                if pallet_pay != 0:
                    raise PublicationValidationError("Dodatek paletowy bez osób w podziale.")
            elif pallet_pay > 0:
                expected_pallet_pay = (pallet_team_count * pallet_rate
                                       / Decimal(pallet_recipients))
                if abs(expected_pallet_pay - pallet_pay) > Decimal("0.01"):
                    raise PublicationValidationError("Dodatek paletowy nie odpowiada podziałowi puli.")

        special_pay = _decimal(source["Premia Specjalna (zł)"], "premia specjalna")
        special_details = None
        if special_source is not None:
            required = {"Pracownik", "Kwota netto premii",
                        "Powód przyznania premii", "Kto przyznał"}
            if not required.issubset(special_source.columns):
                raise PublicationValidationError("Brak wymaganych kolumn premii specjalnych.")
            special_details = []
            for _, detail in special_source.iterrows():
                if str(detail["Pracownik"]).strip().casefold() != normalized:
                    continue
                amount = _decimal(detail["Kwota netto premii"], "kwota premii specjalnej")
                if amount == 0:
                    continue
                reason = str(detail["Powód przyznania premii"] or "").strip()
                awarded_by = str(detail["Kto przyznał"] or "").strip()
                if (not reason or reason.casefold() == "nan" or len(reason) > 200
                        or len(awarded_by) > 100 or awarded_by.casefold() == "nan"):
                    raise PublicationValidationError("Uzupełnij uzasadnienie i autora premii specjalnej.")
                special_details.append({
                    "amount_pln": str(amount), "reason": reason,
                    "awarded_by": awarded_by,
                })
                if len(special_details) > 12:
                    raise PublicationValidationError("Zbyt wiele osobnych premii specjalnych.")
            if abs(sum((Decimal(d["amount_pln"]) for d in special_details),
                       Decimal("0.00")) - special_pay) > Decimal("0.01"):
                raise PublicationValidationError(
                    "Wykaz premii specjalnych nie zgadza się z rozliczeniem."
                )

        if planned > 31 or worked != attendance["confirmed"]:
            raise PublicationValidationError(
                f"Nieprawidłowa liczba przepracowanych dni pracownika „{name}”: "
                f"potwierdzono {attendance['confirmed']}, w rozliczeniu {worked}."
            )
        rows.append({
            "user_id": uid,
            "employee_name": name,
            "planned_days": planned,
            "attended_days": worked,
            "bonus_main_pln": str(main),
            "bonus_additions_pln": str(additions),
            "bonus_final_pln": str(total),
            "absence_reduction_pct": str(deduction),
            "overtime_hours": str(overtime_hours) if overtime_hours is not None else None,
            "overtime_pay_pln": str(overtime_pay),
            "overtime_rate_pln": str(overtime_rate) if overtime_rate is not None else None,
            "forklift_hours": str(forklift_hours) if forklift_hours is not None else None,
            "forklift_team_hours": str(forklift_team_hours) if forklift_team_hours is not None else None,
            "forklift_pay_pln": str(forklift_pay),
            "pallet_team_count": str(pallet_team_count) if pallet_team_count is not None else None,
            "pallet_rate_pln": str(pallet_rate) if pallet_rate is not None else None,
            "pallet_recipients": pallet_recipients,
            "pallet_pay_pln": str(pallet_pay),
            "special_pay_pln": str(special_pay),
            "special_details": special_details,
        })
    return period, kpis, rows
