"""Generate individual PDF bonus slips using amounts from the existing calculator."""

import math
from pathlib import Path
from fpdf import FPDF

FONT_PATHS = (
    Path(__file__).resolve().parent / "assets" / "fonts" / "DejaVuSans.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/local/share/fonts/DejaVuSans.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"),
)
BOLD_FONT_PATHS = (
    Path(__file__).resolve().parent / "assets" / "fonts" / "DejaVuSans-Bold.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/local/share/fonts/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"),
)


def _font_file(candidates):
    for path in candidates:
        if path.is_file():
            return str(path)
    raise RuntimeError("Brak czcionki Unicode do przygotowania PDF. Skontaktuj się z administratorem.")


def _clean(value):
    text = str(value if value is not None else "")
    return "".join(
        ch if ch in "\n\t" or (32 <= ord(ch) <= 0xFFFF and ch not in "\u200b\ufeff") else " "
        for ch in text
    ).strip()


def _number(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else 0.0
    except (ValueError, TypeError):
        return 0.0


def _pl_number(value, digits=2):
    return f"{_number(value):,.{digits}f}".replace(",", "\x01").replace(".", ",").replace("\x01", " ")


def _pl_money(value):
    return f"{_pl_number(value)} zł"


class _Slip(FPDF):
    def header(self):
        self.set_fill_color(25, 49, 83)
        self.rect(0, 0, 210, 26, style="F")
        self.set_xy(15, 7)
        self.set_font("Premium", "B", 12)
        self.set_text_color(255, 255, 255)
        self.cell(0, 8, "SYSTEM PREMII 2.7", new_x="LMARGIN", new_y="NEXT")
        self.set_font("Premium", "", 8)
        self.set_x(15)
        self.set_text_color(207, 222, 239)
        self.cell(0, 5, "Indywidualne rozliczenie premii i dodatków", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(31, 41, 55)
        self.set_y(33)

    def footer(self):
        self.set_y(-14)
        self.set_draw_color(222, 229, 237)
        self.line(15, self.get_y(), 195, self.get_y())
        self.set_y(-12)
        self.set_font("Premium", "", 7)
        self.set_text_color(100, 116, 139)
        self.cell(150, 6, "Zestawienie informacyjne - nie jest paskiem wynagrodzenia zasadniczego.")
        self.cell(30, 6, f"Strona {self.page_no()}/{{nb}}", align="R")

    def section(self, label):
        self.ln(3)
        self.set_fill_color(236, 242, 248)
        self.set_text_color(25, 49, 83)
        self.set_font("Premium", "B", 10)
        self.cell(0, 8, _clean(label), fill=True, new_x="LMARGIN", new_y="NEXT")
        self.ln(1)
        self.set_text_color(31, 41, 55)

    def note(self, text):
        self.set_font("Premium", "", 8)
        self.set_text_color(84, 99, 117)
        self.multi_cell(0, 5, _clean(text), align="L", new_x="LMARGIN", new_y="NEXT")
        self.set_text_color(31, 41, 55)

    def money_row(self, label, amount, description=None):
        if self.will_page_break(18):
            self.add_page()
        self.set_font("Premium", "", 9)
        start_y = self.get_y()
        self.multi_cell(135, 6, _clean(label), new_x="LMARGIN", new_y="NEXT")
        after_y = self.get_y()
        self.set_xy(151, start_y)
        self.set_font("Premium", "B", 9)
        self.cell(44, 6, _pl_money(amount), align="R")
        self.set_y(max(after_y, start_y + 6))
        if description:
            self.note(description)
        self.ln(1)


def generate_bonus_slip_pdf(employee, period, details, absence_mode=False):
    """Return PDF bytes; never fetch or recalculate payroll values."""
    pdf = _Slip(orientation="P", unit="mm", format="A4")
    pdf.add_font("Premium", "", _font_file(FONT_PATHS))
    pdf.add_font("Premium", "B", _font_file(BOLD_FONT_PATHS))
    pdf.set_margins(15, 32, 15)
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.alias_nb_pages()
    pdf.add_page()

    pdf.set_font("Premium", "B", 17)
    pdf.set_text_color(25, 49, 83)
    pdf.multi_cell(0, 10, "Pasek premiowy", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Premium", "", 10)
    pdf.set_text_color(84, 99, 117)
    pdf.multi_cell(0, 7, f"Okres rozliczenia: {_clean(period)}", new_x="LMARGIN", new_y="NEXT")
    pdf.ln(3)
    pdf.set_font("Premium", "B", 12)
    pdf.set_text_color(31, 41, 55)
    pdf.multi_cell(0, 7, _clean(employee), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font("Premium", "", 9)
    pdf.multi_cell(0, 6, f'Stanowisko: {_clean(details.get("position", "—"))}', new_x="LMARGIN", new_y="NEXT")

    pdf.section("01  PREMIA PODSTAWOWA")
    base = _number(details.get("base_emp_bonus"))
    final_bonus = _number(details.get("calculated_bonus"))
    deduction_pct = _number(details.get("deduction_pct")) if absence_mode else 0.0
    pdf.money_row("Premia bazowa", base)
    pdf.money_row(f"Potrącenie za nieobecności ({_pl_number(deduction_pct)}%)", -max(0.0, base - final_bonus))
    pdf.money_row("Premia po uwzględnieniu obecności", final_bonus)
    pdf.note("Wariant: z potrąceniami według udziału pracy w dniach nieobecności." if absence_mode
             else "Wariant: bez potrąceń za nieobecności.")

    pdf.section("02  CZAS PRACY")
    pdf.note("Dni zaplanowane: {scheduled}   |   Dni potwierdzone: {worked}   |   Dni nieobecności: {absent}".format(
        scheduled=int(_number(details.get("scheduled_days"))),
        worked=int(_number(details.get("days_worked"))),
        absent=int(_number(details.get("absent_days"))),
    ))
    hours = _number(details.get("total_ot"))
    rate = details.get("ot_rate")
    rate_label = f"{_pl_number(hours, 1)} h × {_pl_money(rate)}/h" if rate is not None else f"{_pl_number(hours, 1)} h (stawka nieudostępniona)"
    pdf.money_row("Nadgodziny", details.get("ot_pay"), rate_label)

    pdf.section("03  DODATKI")
    emp_fk = _number(details.get("emp_forklift_hours"))
    fk_pct = _number(details.get("emp_forklift_pct"))
    pool = details.get("forklift_pool")
    total_fk = details.get("total_forklift_hours")
    fork_note = f"{_pl_number(emp_fk, 1)} h / {_pl_number(total_fk, 1)} h zespołu = {_pl_number(fk_pct)}% udziału" if total_fk is not None else f"{_pl_number(emp_fk, 1)} h; udział {_pl_number(fk_pct)}%"
    if pool is not None:
        fork_note += f"; pula do podziału: {_pl_money(pool)}"
    pdf.money_row("Dodatek za obsługę wózka widłowego", details.get("forklift_pay"), fork_note)
    pallet_count = details.get("pallet_count")
    pallet_rate = details.get("pallet_rate")
    pallet_recipients = details.get("pallet_recipients")
    if pallet_count is not None and pallet_rate is not None and pallet_recipients:
        pallet_note = (f"{_pl_number(pallet_count, 0)} palet × {_pl_money(pallet_rate)}/paletę "
                       f"/ {int(pallet_recipients)} osób")
    else:
        pallet_note = ("Pracownik nie został uwzględniony w podziale puli za palety."
                       if _number(details.get("pallet_pay")) == 0 and _number(pallet_count) > 0
                       else "Dodatek przydzielony w kalkulatorze; szczegóły podziału nieudostępnione.")
    pdf.money_row("Dodatek za rozładunki i załadunki palet", details.get("pallet_pay"), pallet_note)

    pdf.section("04  PREMIE SPECJALNE I UZNANIOWE")
    items = details.get("spec_bonus_items") or []
    if items:
        for item in items:
            reason = _clean(item.get("reason") or "Premia specjalna")
            approver = _clean(item.get("approved_by"))
            pdf.money_row(reason, item.get("amount"), f"Przyznał: {approver}" if approver else None)
    else:
        pdf.note("Brak dodatkowych premii specjalnych w tym okresie.")
    pdf.money_row("Razem premie specjalne", details.get("spec_bonus_val"))

    pdf.section("05  NIEOBECNOŚCI")
    absence_table = details.get("absences_table")
    if absence_table is not None and not absence_table.empty:
        for row in absence_table.to_dict("records"):
            day = _clean(row.get("Data", ""))
            absence_type = _clean(row.get("Rodzaj nieobecności", ""))
            daily_pct = _pl_number(row.get("Udział pracy w miesiącu (%)"))
            pdf.note(f"{day}  |  {absence_type}  |  Udział pracy dnia: {daily_pct}%")
    else:
        pdf.note("Brak zarejestrowanych nieobecności w tym okresie.")

    if pdf.will_page_break(34):
        pdf.add_page()
    pdf.ln(5)
    pdf.set_fill_color(25, 49, 83)
    y = pdf.get_y()
    pdf.rect(15, y, 180, 14, style="F")
    pdf.set_xy(19, y + 2)
    pdf.set_text_color(255, 255, 255)
    pdf.set_font("Premium", "B", 10)
    pdf.cell(110, 10, "ŁĄCZNA KWOTA PREMII I DODATKÓW")
    pdf.cell(62, 10, _pl_money(details.get("total_payout")), align="R")
    pdf.set_y(y + 14)
    pdf.set_text_color(84, 99, 117)
    pdf.ln(2)
    pdf.note("Kwoty zgodne z kalkulatorem Systemu Premii 2.7, prezentowane z dokładnością do 0,01 zł. "
             "Suma nie obejmuje wynagrodzenia zasadniczego ani innych świadczeń spoza kalkulatora.")

    return bytes(pdf.output())
