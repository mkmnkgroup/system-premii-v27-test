"""Printable, single-employee PDF built only from published monthly values."""
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path
import re
import unicodedata

from bonus_components import parse_bonus_breakdown

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


def _add_breakdown_page(pdf, components):
    """Append a verifiable detail page to an already validated payslip."""
    pdf.add_page()
    pdf.set_auto_page_break(True, margin=22)
    navy, muted = (24, 43, 61), (94, 110, 123)

    pdf.set_xy(20, 24)
    pdf.set_font("DejaVu", "B", 17)
    pdf.set_text_color(*navy)
    pdf.multi_cell(170, 9, "Szczegóły naliczenia dodatków")
    pdf.ln(2)
    pdf.set_x(20)
    pdf.set_font("DejaVu", "", 9)
    pdf.set_text_color(*muted)
    pdf.multi_cell(170, 6, "Kwoty z zatwierdzonego rozliczenia. Ta strona nie zwiększa kwoty z podsumowania.")
    pdf.ln(5)

    def item(label, amount, note=None):
        pdf.set_font("DejaVu", "", 9)
        pdf.set_text_color(*navy)
        y = pdf.get_y()
        pdf.set_x(20)
        pdf.multi_cell(112, 6, str(label))
        next_y = pdf.get_y()
        pdf.set_xy(138, y)
        pdf.set_font("DejaVu", "B", 9)
        pdf.cell(52, 6, _pl(amount) + " zł", align="R")
        pdf.set_y(max(next_y, y + 6))
        if note:
            pdf.set_x(20)
            pdf.set_font("DejaVu", "", 8)
            pdf.set_text_color(*muted)
            pdf.multi_cell(170, 5, str(note))
        pdf.ln(3)

    overtime_note = None
    if components["overtime_rate"] is not None and components["overtime_hours"] is not None:
        overtime_note = (
            f'{_pl(components["overtime_hours"])} godz. x '
            f'{_pl(components["overtime_rate"])} zł/godz.'
        )
    item("Nadgodziny", components["overtime_pay"], overtime_note)

    forklift_note = None
    if components["forklift_hours"] is not None and components["forklift_team_hours"] is not None:
        forklift_note = (
            f'{_pl(components["forklift_hours"])} godz. / '
            f'{_pl(components["forklift_team_hours"])} godz. zespołu'
        )
        if components["forklift_pool"] is not None:
            forklift_note += f' | pula {_pl(components["forklift_pool"])} zł'
    item("Dodatek za obsługę wózka widłowego", components["forklift_pay"], forklift_note)

    pallet_note = None
    if (components["pallet_count"] is not None and
            components["pallet_rate"] is not None and components["pallet_recipients"]):
        pallet_note = (
            f'{_pl(components["pallet_count"])} palet x '
            f'{_pl(components["pallet_rate"])} zł / '
            f'{components["pallet_recipients"]} osób'
        )
    item("Dodatek za rozładunek i załadunek palet", components["pallet_pay"], pallet_note)

    for bonus in components["special_bonuses"]:
        note = ("Przyznał: " + bonus["approved_by"]) if bonus["approved_by"] else None
        item("Premia specjalna: " + bonus["reason"], bonus["amount"], note)

    pdf.ln(4)
    pdf.set_x(20)
    pdf.set_font("DejaVu", "B", 11)
    pdf.set_text_color(*navy)
    pdf.cell(110, 8, "Suma dodatków (z nadgodzinami)")
    pdf.cell(60, 8, _pl(components["additions_total"]) + " zł", align="R")


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
    planned, attended = row.get("planned_days"), row.get("attended_days")
    if (type(planned) is not int or type(attended) is not int
            or not 0 <= attended <= planned <= 31 or reduction > 100
            or main + additions != total):
        raise ValueError("Niespójne dane w opublikowanym rozliczeniu.")

    details = parse_bonus_breakdown(row)

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
    y += 42
    text(20, y, "SKŁADNIKI PREMII", 9, True, muted)
    y += 13
    overtime_label = "Nadgodziny" + (f" ({_pl(hours)} h)" if hours is not None else " (brak liczby godzin)")
    components = [("Premia po uwzględnieniu obecności", main),
                  (overtime_label, overtime),
                  ("Pozostałe dodatki (szczegóły na str. 2)" if details is not None else "Pozostałe dodatki" if overtime is not None else "Dodatki łącznie", additions - overtime if overtime is not None else additions)]
    for label, value in components:
        text(20, y, label, 10)
        text(130, y, _pl(value) + " zł" if value is not None else "Brak danych", 12, True, width=60, align="R")
        pdf.set_draw_color(223, 230, 234)
        pdf.line(20, y + 11, 190, y + 11)
        y += 14
    text(20, y, "Potrącenie za nieobecności", 10, color=muted)
    text(130, y, _pl(reduction) + "%", 10, width=60, align="R")
    text(20, y + 9, "Potrącenie jest już uwzględnione w premii powyżej.", 8, color=muted)
    y += 24
    pdf.set_fill_color(*teal)
    pdf.rect(20, y, 170, 28, style="F")
    text(26, y + 9, "DO WYPŁATY", 11, True, (255, 255, 255), width=65)
    text(100, y + 9, _pl(total) + " zł netto", 20, True,
         (255, 255, 255), width=84, align="R")
    pdf.set_draw_color(223, 230, 234)
    pdf.line(20, 282, 190, 282)
    text(20, 285, "WERSJA TESTOWA  |  Dokument informacyjny - nie stanowi dokumentu płacowego.",
         8, color=muted)
    if details is not None:
        _add_breakdown_page(pdf, details)
    return bytes(pdf.output())
