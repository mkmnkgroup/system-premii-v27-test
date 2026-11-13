"""Printable, single-employee PDF built only from published monthly values."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
import unicodedata

MONTHS = ("", "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
          "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień")
FONTS = Path(__file__).parent / "assets" / "fonts"


def _number(value):
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError("Brak poprawnej kwoty w opublikowanym rozliczeniu.") from None
    if not result.is_finite() or result < 0:
        raise ValueError("Nieprawidłowa kwota w opublikowanym rozliczeniu.")
    return result.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def _pl(value):
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def payslip_filename(period, employee_name):
    slug = unicodedata.normalize("NFKD", employee_name).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^A-Za-z0-9]+", "_", slug).strip("_")[:80] or "pracownik"
    return f"pasek_premiowy_{date.fromisoformat(period):%Y-%m}_{slug}.pdf"


def build_payslip_pdf(period, employee_name, row):
    from fpdf import FPDF

    month = date.fromisoformat(period)
    if month.day != 1 or row.get("period") != period:
        raise ValueError("Nieprawidłowy okres rozliczenia.")
    name = " ".join(str(employee_name or "").split())
    if not name or len(name) > 150:
        raise ValueError("Brak poprawnego identyfikatora pracownika.")
    main, additions, total = [_number(row.get(key)) for key in
                              ("bonus_main_pln", "bonus_additions_pln", "bonus_final_pln")]
    reduction = _number(row.get("absence_reduction_pct"))
    hours = _number(row["overtime_hours"]) if row.get("overtime_hours") is not None else None
    overtime = _number(row["overtime_pay_pln"]) if row.get("overtime_pay_pln") is not None else None
    if (hours is not None and hours > 744 or overtime is not None and overtime > additions
            or hours == 0 and overtime is not None and overtime > 0):
        raise ValueError("Niespójne dane nadgodzin.")
    # Breakdown values are nullable for historical publications. Never
    # turn missing detail into a fabricated zero.
    detail_keys = ("forklift_pay_pln", "pallet_pay_pln", "special_pay_pln")
    detail_amounts = {
        key: _number(row[key]) if row.get(key) is not None else None
        for key in detail_keys
    }
    detailed = overtime is not None and all(
        amount is not None for amount in detail_amounts.values()
    )
    if detailed and abs(overtime + sum(detail_amounts.values()) - additions) > Decimal("0.01"):
        raise ValueError("Rozbicie dodatków nie zgadza się z kwotą łączną.")
    overtime_rate = (
        _number(row["overtime_rate_pln"])
        if row.get("overtime_rate_pln") is not None else None
    )
    if hours is not None and overtime_rate is not None and overtime is not None:
        if abs(hours * overtime_rate - overtime) > Decimal("0.01"):
            raise ValueError("Nieprawidłowe rozliczenie stawki nadgodzin.")
    forklift_hours = (
        _number(row["forklift_hours"])
        if row.get("forklift_hours") is not None else None
    )
    forklift_total = (
        _number(row["forklift_team_hours"])
        if row.get("forklift_team_hours") is not None else None
    )
    pallet_total = (
        _number(row["pallet_team_count"])
        if row.get("pallet_team_count") is not None else None
    )
    pallet_rate = (
        _number(row["pallet_rate_pln"])
        if row.get("pallet_rate_pln") is not None else None
    )
    recipients = row.get("pallet_recipients")
    special_details = row.get("special_details")
    if special_details is not None:
        if not isinstance(special_details, list) or len(special_details) > 12:
            raise ValueError("Nieprawidłowy wykaz premii specjalnych.")
        normalized_specials = []
        for item in special_details:
            if not isinstance(item, dict):
                raise ValueError("Nieprawidłowa pozycja premii specjalnej.")
            amount = _number(item.get("amount_pln"))
            reason = str(item.get("reason") or "").strip()
            author = str(item.get("awarded_by") or "").strip()
            if not reason or len(reason) > 200 or len(author) > 100:
                raise ValueError("Brak uzasadnienia premii specjalnej.")
            normalized_specials.append((amount, reason, author))
        special_details = normalized_specials
        if detailed and abs(
            sum((amount for amount, _, _ in special_details), Decimal("0"))
            - detail_amounts["special_pay_pln"]
        ) > Decimal("0.01"):
            raise ValueError("Kwoty premii specjalnych nie sumują się.")
    if (forklift_hours is not None and forklift_total is not None
            and forklift_hours > forklift_total):
        raise ValueError("Błędny udział pracy wózka.")
    if recipients is not None and (type(recipients) is not int or not 0 <= recipients <= 50):
        raise ValueError("Nieprawidłowy podział premii paletowej.")

    planned, attended = row.get("planned_days"), row.get("attended_days")
    if (type(planned) is not int or type(attended) is not int
            or not 0 <= attended <= planned <= 31 or reduction > 100
            or main + additions != total):
        raise ValueError("Niespójne dane w opublikowanym rozliczeniu.")

    pdf = FPDF(format="A4")
    pdf.add_font("DejaVu", "", str(FONTS / "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", str(FONTS / "DejaVuSans-Bold.ttf"))
    pdf.set_auto_page_break(False)
    pdf.set_margins(20, 20, 20)
    pdf.set_title(f"Pasek premiowy - {MONTHS[month.month]} {month.year} - {name}")
    pdf.set_author("System Premii 2.7")
    pdf.add_page()
    navy, muted, teal = (24, 43, 61), (94, 110, 123), (14, 110, 99)

    def text(x, y, value, size=10, bold=False, color=navy, width=170, align="L"):
        pdf.set_xy(x, y)
        pdf.set_font("DejaVu", "B" if bold else "", size)
        pdf.set_text_color(*color)
        pdf.cell(width, 8, value, align=align)

    pdf.set_fill_color(*teal)
    pdf.rect(20, 20, 12, 2, style="F")
    text(20, 27, "SYSTEM PREMII 2.7", 10, True, teal)
    text(20, 40, "Pasek premiowy", 27, True)
    text(20, 54, f"{MONTHS[month.month]} {month.year}  |  Rozliczenie miesięczne", 11, color=muted)
    text(20, 75, "PRACOWNIK", 9, True, muted)
    pdf.set_xy(20, 87)
    pdf.set_font("DejaVu", "B", 11 if len(name) > 80 else 15)
    pdf.set_text_color(*navy)
    pdf.multi_cell(170, 7, name)
    y = max(110, pdf.get_y() + 10)

    pdf.set_fill_color(243, 247, 248)
    pdf.rect(20, y, 170, 28, style="F")
    for x, label, value in [(25, "Dni planowane", planned),
                             (81, "Dni obecności", attended),
                             (137, "Dni nieobecności", planned - attended)]:
        text(x, y + 2, label, 9, color=muted, width=50)
        text(x, y + 13, str(value), 16, True, width=50)
    y += 36
    text(20, y, "SKŁADNIKI PREMII", 9, True, muted)
    y += 11
    overtime_label = "Nadgodziny" + (f" ({_pl(hours)} h)" if hours is not None else " (brak liczby godzin)")
    components = [("Premia po uwzględnieniu obecności", main),
                  (overtime_label, overtime)]
    if detailed:
        components.extend([
            ("Dodatek za wózek widłowy", detail_amounts["forklift_pay_pln"]),
            ("Dodatek za palety", detail_amounts["pallet_pay_pln"]),
            ("Premie specjalne", detail_amounts["special_pay_pln"]),
        ])
    else:
        components.append(("Pozostałe dodatki" if overtime is not None
                           else "Dodatki łącznie",
                           additions - overtime if overtime is not None else additions))
    for label, value in components:
        text(20, y, label, 9.5)
        text(130, y, _pl(value) + " zł" if value is not None else "Brak danych",
             11, True, width=60, align="R")
        pdf.set_draw_color(223, 230, 234)
        pdf.line(20, y + 10, 190, y + 10)
        y += 11
    text(20, y, "Potrącenie za nieobecności", 9, color=muted)
    text(130, y, _pl(reduction) + "%", 10, width=60, align="R")
    text(20, y + 8, "Potrącenie jest już uwzględnione w premii głównej.", 7.5, color=muted)
    y += 19
    pdf.set_fill_color(*teal)
    pdf.rect(20, y, 170, 27, style="F")
    text(26, y + 9, "DO WYPŁATY", 11, True, (255, 255, 255), width=65)
    text(100, y + 9, _pl(total) + " zł netto", 20, True,
         (255, 255, 255), width=84, align="R")

    def footer():
        pdf.set_draw_color(223, 230, 234)
        pdf.line(20, 282, 190, 282)
        text(20, 285, "WERSJA TESTOWA  |  Dokument informacyjny - nie stanowi dokumentu płacowego.",
             8, color=muted)

    footer()
    extra = detailed and any(v is not None for v in (
        overtime_rate, forklift_hours, forklift_total, pallet_total,
        pallet_rate, recipients, special_details,
    ))
    if extra:
        # A separate, readable breakdown page prevents clipped explanations
        # and does not conflate a team-level pallet count with individual work.
        pdf.add_page()
        text(20, 24, "SYSTEM PREMII 2.7", 10, True, teal)
        text(20, 39, "Szczegóły dodatków", 22, True)
        text(20, 52, f"{MONTHS[month.month]} {month.year} · {name[:58]}", 9, color=muted)
        cursor = 70

        def explanation(label, description):
            nonlocal cursor
            if cursor > 252:
                footer()
                pdf.add_page()
                cursor = 27
            text(20, cursor, label, 10, True)
            cursor += 8
            pdf.set_xy(20, cursor)
            pdf.set_font("DejaVu", "", 9)
            pdf.set_text_color(*muted)
            pdf.multi_cell(170, 6, description)
            cursor = pdf.get_y() + 10

        if overtime_rate is not None:
            explanation("Nadgodziny", f"Stawka: {_pl(overtime_rate)} zł za godzinę; "
                        f"czas: {_pl(hours) if hours is not None else 'brak danych'} h; "
                        f"kwota: {_pl(overtime)} zł.")
        if forklift_hours is not None:
            explanation("Wózek widłowy", f"Czas pracownika: {_pl(forklift_hours)} h"
                        + (f"; zespół: {_pl(forklift_total)} h" if forklift_total is not None else "")
                        + f"; przyznany dodatek: {_pl(detail_amounts['forklift_pay_pln'])} zł.")
        if pallet_total is not None or pallet_rate is not None:
            details = []
            if pallet_total is not None:
                details.append(f"Palety rozliczone przez zespół: {_pl(pallet_total)}")
            if pallet_rate is not None:
                details.append(f"Stawka: {_pl(pallet_rate)} zł/paleta")
            if recipients is not None:
                details.append(f"Podział puli na {recipients} osób")
            details.append(f"Udział pracownika: {_pl(detail_amounts['pallet_pay_pln'])} zł")
            explanation("Palety - wspólna pula", "; ".join(details)
                        + ". Liczba palet zespołu nie jest liczbą palet obsłużonych indywidualnie.")
        if special_details is not None:
            if special_details:
                for idx, (amount, reason, author) in enumerate(special_details, 1):
                    explanation(f"Premia specjalna {idx}: {_pl(amount)} zł",
                                reason + (f" (przyznał: {author})" if author else ""))
            else:
                explanation("Premie specjalne", "Brak dodatkowych premii za ten miesiąc.")
        text(20, 273, "Szczegóły odpowiadają wyłącznie opublikowanemu rozliczeniu pracownika.",
             8, color=muted)

    if extra:
        footer()
    return bytes(pdf.output())
