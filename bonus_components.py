"""Validated optional itemization of already-approved bonus additions.

The main amount and total always come from the published monthly record.
Legacy records without itemization remain readable.
"""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

CENT = Decimal("0.01")


def _money(value, field):
    try:
        number = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError(f"Nieprawidłowe pole kwotowe: {field}.") from None
    if not number.is_finite() or number < 0 or number > 10000000:
        raise ValueError(f"Nieprawidłowa kwota: {field}.")
    return number.quantize(CENT, rounding=ROUND_HALF_UP)


def _quantity(value, field):
    try:
        number = Decimal(str(value))
    except (ValueError, TypeError, InvalidOperation):
        raise ValueError(f"Nieprawidłowa wartość: {field}.") from None
    if not number.is_finite() or not 0 <= number <= 10000000:
        raise ValueError(f"Nieprawidłowy zakres: {field}.")
    return number


def _optional_quantity(breakdown, key):
    value = breakdown.get(key)
    return _quantity(value, key) if value is not None else None


def _text(value, label, max_length=150, mandatory=False):
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise ValueError(f"Nieprawidłowy opis: {label}.")
    result = " ".join(value.split())
    if len(result) > max_length or (mandatory and not result):
        raise ValueError(f"Brak poprawnego opisu: {label}.")
    return result


def parse_bonus_breakdown(row):
    """Return normalized amounts if detailed breakdown has been published.

    None means an older monthly record without itemization. Never substitute
    a guessed breakdown when the stored amounts are incomplete or inconsistent.
    """
    raw = row.get("bonus_breakdown")
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise ValueError("Niedozwolony format szczegółów rozliczenia.")

    if row.get("overtime_pay_pln") is None:
        raise ValueError("Szczegóły wymagają opublikowanej kwoty nadgodzin.")

    overtime = _money(row["overtime_pay_pln"], "overtime_pay_pln")
    additions = _money(row.get("bonus_additions_pln"), "bonus_additions_pln")
    forklift = _money(raw.get("forklift_pay_pln"), "forklift_pay_pln")
    pallet = _money(raw.get("pallet_pay_pln"), "pallet_pay_pln")

    special_raw = raw.get("special_bonuses")
    if not isinstance(special_raw, list) or len(special_raw) > 30:
        raise ValueError("Nieprawidłowa lista premii specjalnych.")
    special = []
    for index, item in enumerate(special_raw):
        if not isinstance(item, dict):
            raise ValueError("Nieprawidłowa premia specjalna.")
        amount = _money(item.get("amount_pln"), f"special_{index}")
        if amount <= 0:
            raise ValueError("Premia specjalna musi mieć dodatnią kwotę.")
        special.append({
            "amount": amount,
            "reason": _text(item.get("reason"), "powód", 180, mandatory=True),
            "approved_by": _text(item.get("approved_by"), "osoba przyznająca", 100),
        })

    special_total = sum((item["amount"] for item in special), Decimal("0.00"))
    if abs(additions - overtime - forklift - pallet - special_total) > CENT:
        raise ValueError("Kwoty składników nie zgadzają się z sumą dodatków.")

    forklift_hours = _optional_quantity(raw, "forklift_hours")
    team_hours = _optional_quantity(raw, "forklift_team_hours")
    pool = _money(raw["forklift_pool_pln"], "forklift_pool_pln") if raw.get("forklift_pool_pln") is not None else None
    if forklift_hours is not None and team_hours is not None:
        if forklift_hours > team_hours or (team_hours == 0 and forklift_hours > 0):
            raise ValueError("Niespójne godziny pracy wózka.")
    pallet_count = _optional_quantity(raw, "pallet_count")
    pallet_rate = _money(raw["pallet_rate_pln"], "pallet_rate_pln") if raw.get("pallet_rate_pln") is not None else None
    recipients = _optional_quantity(raw, "pallet_recipients")
    if recipients is not None and recipients != int(recipients):
        raise ValueError("Liczba uczestników podziału palet musi być całkowita.")
    if recipients == 0 and pallet > 0:
        raise ValueError("Premia za palety wymaga uczestników podziału.")
    overtime_rate = _money(raw["overtime_rate_pln"], "overtime_rate_pln") if raw.get("overtime_rate_pln") is not None else None
    overtime_hours = _optional_quantity(row, "overtime_hours")
    if overtime_rate is not None and overtime_hours is not None:
        if abs(overtime_hours * overtime_rate - overtime) > Decimal("0.02"):
            raise ValueError("Stawka i godziny nadliczbowe nie zgadzają się z kwotą.")

    return {
        "overtime_pay": overtime,
        "overtime_hours": overtime_hours,
        "overtime_rate": overtime_rate,
        "forklift_pay": forklift,
        "forklift_hours": forklift_hours,
        "forklift_team_hours": team_hours,
        "forklift_pool": pool,
        "pallet_pay": pallet,
        "pallet_count": pallet_count,
        "pallet_rate": pallet_rate,
        "pallet_recipients": int(recipients) if recipients is not None else None,
        "special_bonuses": special,
        "special_total": special_total,
        "additions_total": additions,
    }
