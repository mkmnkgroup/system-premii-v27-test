"""Build fail-closed publication payloads from the TEST archive.

No guessed account mapping, per-person production counts or missing attendance.
This module does not perform network access or publish anything.
"""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID

import pandas as pd

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
        planned = int((own_schedule["DZIEŃ PRACUJĄCY/WOLNY"] == "Pracujący").sum())
        if planned > 31 or worked > planned:
            raise PublicationValidationError(f"Nieprawidłowa obecność pracownika „{name}”.")
        rows.append({
            "user_id": uid,
            "employee_name": name,
            "planned_days": planned,
            "attended_days": worked,
            "bonus_main_pln": str(main),
            "bonus_additions_pln": str(additions),
            "bonus_final_pln": str(total),
            "absence_reduction_pct": str(deduction),
        })
    return period, kpis, rows
