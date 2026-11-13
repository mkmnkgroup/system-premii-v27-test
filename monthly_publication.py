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





def snapshot_bonus_breakdowns(summary, details_map):
    """Freeze a complete, verified, JSON-safe bonus breakdown alongside the archive.

    This must run on calculator results BEFORE the monthly archive is saved.
    Values come from the existing calculator, never from a second calculation.
    """
    from bonus_components import parse_bonus_breakdown

    if not isinstance(summary, pd.DataFrame) or summary.empty or not isinstance(details_map, dict):
        raise PublicationValidationError("Brak szczegółów naliczonych premii.")

    names = {}
    for key, details in details_map.items():
        canonical = canonical_name(key)
        if canonical in names or not isinstance(details, dict):
            raise PublicationValidationError("Powtórzone lub niekompletne szczegóły pracowników.")
        names[canonical] = details

    snapshots = {}
    seen = set()
    for _, row in summary.iterrows():
        name = str(row["Pracownik"]).strip()
        canonical = canonical_name(name)
        if canonical in seen or canonical not in names:
            raise PublicationValidationError("Brak jednoznacznych szczegółów rozliczenia dla pracownika.")
        seen.add(canonical)
        details = names[canonical]

        def money(value, field):
            return str(_decimal(value, field))

        special_items = details.get("spec_bonus_items")
        if not isinstance(special_items, list):
            raise PublicationValidationError("Brak wykazu premii specjalnych w kalkulatorze.")
        bonuses = []
        for item in special_items:
            if not isinstance(item, dict):
                raise PublicationValidationError("Nieprawidłowy wpis premii specjalnej.")
            reason = str(item.get("reason") or "").strip()
            approver = str(item.get("approved_by") or "").strip()
            if not reason or len(reason) > 180 or len(approver) > 100:
                raise PublicationValidationError("Każda premia specjalna musi mieć krótki opis.")
            bonuses.append({
                "amount_pln": money(item.get("amount"), "premia specjalna"),
                "reason": reason,
                "approved_by": approver,
            })

        detail = {
            "base_bonus_pln": money(details.get("base_emp_bonus"), "premia bazowa"),
            "overtime_rate_pln": money(details.get("ot_rate"), "stawka nadgodzin"),
            "forklift_pay_pln": money(details.get("forklift_pay"), "dodatek wózek"),
            "forklift_hours": money(details.get("emp_forklift_hours"), "godziny wózka"),
            "forklift_team_hours": money(details.get("total_forklift_hours"), "godziny wózka zespołu"),
            "forklift_pool_pln": money(details.get("forklift_pool"), "pula wózka"),
            "pallet_pay_pln": money(details.get("pallet_pay"), "dodatek palety"),
            "pallet_count": money(details.get("pallet_count"), "liczba palet"),
            "pallet_rate_pln": money(details.get("pallet_rate"), "stawka za paletę"),
            "pallet_recipients": _int(details.get("pallet_recipients"), "liczba odbiorców", maximum=50),
            "special_bonuses": bonuses,
        }
        validation_row = {
            "overtime_pay_pln": money(row["Nadgodziny (zł)"], "nadgodziny"),
            "overtime_hours": money(row["Nadgodziny (godz.)"], "godziny nadliczbowe"),
            "bonus_additions_pln": str(sum(
                (_decimal(row[field], field) for field in (
                    "Nadgodziny (zł)", "Dodatek Wózek (zł)",
                    "Dodatek Palety (zł)", "Premia Specjalna (zł)",
                )), Decimal("0.00")
            )),
            "bonus_breakdown": detail,
        }
        try:
            parsed = parse_bonus_breakdown(validation_row)
        except ValueError:
            raise PublicationValidationError(
                f"Kwoty lub dane dodatków pracownika „{name}” nie są spójne."
            ) from None

        for calc_value, field in [
            (parsed["forklift_pay"], "Dodatek Wózek (zł)"),
            (parsed["pallet_pay"], "Dodatek Palety (zł)"),
            (parsed["special_total"], "Premia Specjalna (zł)"),
        ]:
            if abs(calc_value - _decimal(row[field], field)) > Decimal("0.01"):
                raise PublicationValidationError(f"Dodatki pracownika „{name}” różnią się od kalkulatora.")

        main = _decimal(row["Premia (zł)"], "premia główna")
        base = _decimal(detail["base_bonus_pln"], "premia bazowa")
        if base + Decimal("0.01") < main:
            raise PublicationValidationError(f"Premia bazowa pracownika „{name}” jest niższa od należnej.")
        if abs(_decimal(details.get("calculated_bonus"), "naliczona premia") - main) > Decimal("0.01"):
            raise PublicationValidationError(f"Premia główna pracownika „{name}” różni się od kalkulatora.")

        snapshots[name] = detail

    if len(seen) != len(names):
        raise PublicationValidationError("Szczegóły rozliczenia zawierają obcych pracowników.")
    return snapshots

def prepare_publication(label, archive, profiles):
    """Return (period, aggregate KPI dict, personal rows) after all checks."""
    period = period_date(label)
    if not isinstance(archive, dict) or not isinstance(profiles, list):
        raise PublicationValidationError("Brak pełnych danych archiwalnych lub kont.")
    summary = archive.get("summary")
    schedule = archive.get("schedule")
    metrics = archive.get("metrics")
    if not isinstance(summary, pd.DataFrame) or summary.empty or len(summary) > 50:
        raise PublicationValidationError("Brak kompletnego rozliczenia pracowników.")
    if not isinstance(schedule, pd.DataFrame) or schedule.empty:
        raise PublicationValidationError("Brak zatwierdzonego harmonogramu w archiwum.")
    if not isinstance(metrics, dict):
        raise PublicationValidationError("Brak zbiorczych parametrów produkcji.")
    breakdowns = archive.get("bonus_breakdowns")
    if breakdowns is not None and not isinstance(breakdowns, dict):
        raise PublicationValidationError("Uszkodzone szczegóły premii w archiwum.")
    normalized_breakdowns = {}
    if breakdowns is not None:
        for key, data in breakdowns.items():
            normalized_key = canonical_name(key)
            if normalized_key in normalized_breakdowns or not isinstance(data, dict):
                raise PublicationValidationError("Powtórzone lub uszkodzone szczegóły premii.")
            normalized_breakdowns[normalized_key] = data

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
        if planned > 31 or worked != attendance["confirmed"]:
            raise PublicationValidationError(
                f"Nieprawidłowa liczba przepracowanych dni pracownika „{name}”: "
                f"potwierdzono {attendance['confirmed']}, w rozliczeniu {worked}."
            )
        published_breakdown = None
        published_base = None
        if breakdowns is not None:
            published_breakdown = normalized_breakdowns.get(normalized)
            if published_breakdown is None:
                raise PublicationValidationError(
                    f"Brakuje szczegółów premii dla pracownika „{name}”."
                )
            from bonus_components import parse_bonus_breakdown
            try:
                verified = parse_bonus_breakdown({
                    "bonus_additions_pln": str(additions),
                    "overtime_hours": str(overtime_hours) if overtime_hours is not None else None,
                    "overtime_pay_pln": str(overtime_pay),
                    "bonus_breakdown": published_breakdown,
                })
                published_base = _decimal(published_breakdown.get("base_bonus_pln"), "premia bazowa")
            except ValueError:
                raise PublicationValidationError(
                    f"Szczegóły premii pracownika „{name}” są niespójne."
                ) from None
            if published_base + Decimal("0.01") < main:
                raise PublicationValidationError(f"Nieprawidłowa premia bazowa pracownika „{name}”.")
            for amount, field in [
                (verified["forklift_pay"], "Dodatek Wózek (zł)"),
                (verified["pallet_pay"], "Dodatek Palety (zł)"),
                (verified["special_total"], "Premia Specjalna (zł)"),
            ]:
                if abs(amount - _decimal(source[field], field)) > Decimal("0.01"):
                    raise PublicationValidationError(
                        f"Szczegóły premii pracownika „{name}” różnią się od archiwum."
                    )
        rows.append({
            "bonus_breakdown": published_breakdown,
            "bonus_base_pln": str(published_base) if published_base is not None else None,
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
        })
    if breakdowns is not None and set(normalized_breakdowns) != seen_names:
        raise PublicationValidationError("Szczegóły premii zawierają osoby spoza rozliczenia.")
    return period, kpis, rows
