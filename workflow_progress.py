"""Read-only, month-scoped progress ribbon for the warehouse payroll workflow.

Statuses are evidence-based and do not interpret an uploaded Excel file, an
automatically generated schedule, or an archive as publication to employees.
"""
from html import escape


def _saved_revision(state, year, month, stage):
    key = f"_test_saved_draft_revision_draft_v27_{year:04d}-{month:02d}_{stage}"
    value = state.get(key)
    return type(value) is int and value > 0


def workflow_steps(state, *, year, month, period_label,
                   schedule_loaded, production_loaded, weights_loaded):
    """Describe monthly workflow in the actual business order; no network I/O."""
    year, month = int(year), int(month)
    month_key = f"{year:04d}-{month:02d}-01"
    schedule_saved = _saved_revision(state, year, month, "schedule")
    attendance_saved = _saved_revision(state, year, month, "attendance")
    extras_saved = state.get("_bonus_inputs_confirmed_by_period", {}).get(period_label) is True
    extras_present = period_label in state.get("_bonus_inputs_by_period", {})
    archive = state.get("history_v2", {})
    archived = period_label in archive
    publication_attendance = state.get("_test_attendance_publications", {}).get(month_key) is True
    publication_bonus = state.get("_test_payroll_publications", {}).get(month_key) is True

    if schedule_saved:
        plan = ("Zapisany szkic", "done",
                "Zapis harmonogramu tego miesiąca potwierdzony w bieżącej sesji.")
    elif schedule_loaded:
        plan = ("W przygotowaniu", "working",
                "Harmonogram utworzono lub wczytano lokalnie; zapis w bazie wymaga potwierdzenia.")
    else:
        plan = ("Do zaplanowania", "pending",
                "Można przygotować przed rozpoczęciem miesiąca.")

    if attendance_saved:
        attendance = ("Zapisana ewidencja", "done",
                      "Szkic wejść, wyjść, nieobecności i nadgodzin zapisano; publikacja jest osobna.")
    elif schedule_loaded:
        attendance = ("Do potwierdzenia", "working",
                      "Uzupełnij faktyczne wejścia, wyjścia, nieobecności i nadgodziny.")
    else:
        attendance = ("Oczekuje", "pending", "Najpierw przygotuj harmonogram.")

    if extras_saved:
        extras = ("Dodatki zapisane", "done",
                  "Zatwierdzono dane wózka, palet i premii specjalnych dla tego miesiąca.")
    elif extras_present:
        extras = ("Do zatwierdzenia", "working",
                  "Wartości robocze nie są potwierdzone przyciskiem zapisu dodatków.")
    else:
        extras = ("Do wprowadzenia", "pending",
                  "Wprowadź godziny wózka, liczbę palet i premie specjalne.")

    if archived:
        production = ("Uwzględniono", "done",
                      "W tej sesji istnieje zapisane rozliczenie. Nowy raport wymaga ponownej kontroli.")
    elif production_loaded and weights_loaded:
        production = ("Pliki wgrane", "working",
                      "Wgrano raport i katalog wag; poprawność sprawdza dopiero kalkulator.")
    elif production_loaded or weights_loaded:
        production = ("Niekompletne", "working",
                      "Do obliczeń potrzebny jest raport produkcji i katalog wag.")
    else:
        production = ("Po zamknięciu miesiąca", "pending",
                      "Po zakończeniu miesiąca wgraj raport produkcji oraz katalog wag.")

    payroll = (
        ("Rozliczenie zapisane", "done", "Rozliczenie wyliczono i zapisano do archiwum sesji.")
        if archived else
        ("Do przeliczenia", "pending",
         "Po skompletowaniu ewidencji, dodatków oraz produkcji przelicz premie.")
    )
    stored = (
        ("W archiwum", "done",
         "Zapis archiwalny jest dostępny; nie oznacza publikacji na kontach pracowników.")
        if archived else
        ("Do archiwizacji", "pending",
         "Zapisz i sprawdź rozliczenie przed udostępnieniem pracownikom.")
    )

    if publication_attendance and publication_bonus:
        published = ("Opublikowane", "done",
                     "W tej sesji serwer potwierdził publikację obecności i premii.")
    elif publication_attendance or publication_bonus:
        published = ("Częściowo", "working",
                     "Potwierdzono tylko jeden rodzaj publikacji; sprawdź drugi.")
    else:
        published = ("Do weryfikacji", "pending",
                     "Brak potwierdzonego statusu publikacji w tej sesji. "
                     "Nie oznacza to, że w bazie nie ma publikacji.")

    count = len(archive)
    if count >= 2:
        reports = ("Dostępne", "working",
                   "Analizy i porównania co najmniej dwóch rozliczonych miesięcy są dostępne.")
    elif archived:
        reports = ("Analizy dostępne", "working",
                   "Dla porównań potrzebne są co najmniej dwa zapisane okresy.")
    else:
        reports = ("Na koniec", "pending",
                   "Analizy i porównania wykonuje się po zapisaniu rozliczeń.")

    entries = (
        ("Harmonogram", "Harmonogram", plan),
        ("Ewidencja", "Obecności i nadgodziny", attendance),
        ("Dodatki", "Dodatki premiowe", extras),
        ("Raport i wagi", "Rozliczenie premii", production),
        ("Rozliczenie", "Rozliczenie premii", payroll),
        ("Archiwum", "Archiwum", stored),
        ("Publikacja", "Archiwum", published),
        ("Analizy / porównania", "Analizy", reports),
    )
    return tuple({
        "title": title,
        "module": module,
        "status": status,
        "tone": tone,
        "description": description,
    } for title, module, (status, tone, description) in entries)


def progress_html(steps, period_label):
    """Compact ribbon visible on every module, not interactive or state-changing."""
    if not steps:
        return ""
    parts = []
    for i, step in enumerate(steps, 1):
        title = escape(str(step["title"]), quote=True)
        status = escape(str(step["status"]), quote=True)
        desc = escape(str(step["description"]), quote=True)
        tone = step["tone"]
        if tone not in ("pending", "working", "done"):
            raise ValueError("Nieznany status procesu.")
        marker = "✓" if tone == "done" else "●" if tone == "working" else "○"
        parts.append(
            f'<div class="erp-process-step erp-process-step--{tone}" title="{desc}">'
            f'<div class="erp-process-step-title"><span>{i:02d}</span> {title}</div>'
            f'<div class="erp-process-step-status">'
            f'<span aria-hidden="true">{marker}</span> {status}</div></div>'
        )
    return (
        '<section class="erp-process" aria-label="Postęp rozliczenia wybranego miesiąca">'
        '<div class="erp-process-heading"><strong>ETAPY PRACY</strong>'
        f'<span>{escape(str(period_label), quote=True)}</span></div>'
        '<div class="erp-process-list">' + "".join(parts) + '</div>'
        '<div class="erp-process-note">Zapis szkicu, import plików i publikacja '
        'pracownikom to trzy różne operacje. Statusy odnoszą się do bieżącej sesji.'
        '</div></section>'
    )
