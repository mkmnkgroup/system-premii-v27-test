"""A truthful, compact process overview shared by every ERP module.

The strip shows only evidence available in the *current authenticated session*.
It never treats an automatically generated schedule, uploaded source files, or
a saved payroll archive as proof that employee-facing publication occurred.
"""
from html import escape


def _saved_revision(state, year, month, stage):
    key = f"_test_saved_draft_revision_draft_v27_{year:04d}-{month:02d}_{stage}"
    revision = state.get(key)
    return isinstance(revision, int) and not isinstance(revision, bool) and revision > 0


def workflow_steps(state, *, year, month, period_label,
                   schedule_loaded, production_loaded, weights_loaded):
    """Return statuses for the selected month, with no network or database writes."""
    month_key = f"{int(year):04d}-{int(month):02d}-01"
    year, month = int(year), int(month)
    schedule_saved = _saved_revision(state, year, month, "schedule")
    attendance_saved = _saved_revision(state, year, month, "attendance")
    archived = period_label in state.get("history_v2", {})
    attendance_publication = state.get("_test_attendance_publications", {}).get(month_key)
    payroll_publication = state.get("_test_payroll_publications", {}).get(month_key)
    attendance_done = attendance_publication is True
    payroll_done = payroll_publication is True

    if schedule_saved:
        plan = ("Szkic zapisany", "done",
                "Zapis harmonogramu potwierdzony w tej sesji; nie oznacza publikacji.")
    elif schedule_loaded:
        plan = ("Roboczy w sesji", "working",
                "Harmonogram jest w pamięci aplikacji, ale zapis w bazie nie został potwierdzony.")
    else:
        plan = ("Nie wczytano", "pending",
                "W tej sesji nie ma harmonogramu wybranego miesiąca.")

    if attendance_done:
        attendance = ("Opublikowana", "done",
                      "Publikacja ewidencji potwierdzona przez usługę testową.")
    elif attendance_saved:
        attendance = ("Szkic zapisany", "working",
                      "W bazie zapisano szkic ewidencji; nie opublikowano jej w tej sesji.")
    else:
        attendance = ("Do potwierdzenia", "pending",
                      "Sprawdź wejścia, wyjścia i nieobecności; zapisz szkic ewidencji.")

    if production_loaded and weights_loaded:
        production = ("Pliki wgrane", "working",
                      "Raport i katalog wag są w sesji; samo wgranie nie potwierdza poprawności.")
    elif production_loaded or weights_loaded:
        production = ("Niekompletne", "working",
                      "Do rozliczenia potrzebne są zarówno raport produkcji, jak i katalog wag.")
    else:
        production = ("Brak plików", "pending",
                      "W tej sesji nie wgrano raportu produkcji ani katalogu wag.")

    if archived:
        payroll = ("W archiwum", "done",
                   "Rozliczenie zapisano do archiwum sesji; nie jest to publikacja dla pracowników.")
    else:
        payroll = ("Do rozliczenia", "pending",
                   "Brak zapisanego rozliczenia dla wybranego miesiąca w tej sesji.")

    if attendance_done and payroll_done:
        publication = ("Opublikowano", "done",
                       "Usługa testowa potwierdziła publikację ewidencji i premii.")
    elif attendance_done or payroll_done:
        publication = ("Częściowo", "working",
                       "Potwierdzono tylko jeden z dwóch rodzajów publikacji.")
    else:
        publication = ("Do weryfikacji", "pending",
                       "Brak potwierdzenia publikacji w tej sesji; sprawdź szczegóły w modułach.")

    entries = [
        ("Harmonogram", "Harmonogram", plan),
        ("Ewidencja", "Harmonogram", attendance),
        ("Raport i wagi", "Produkcja i premie", production),
        ("Rozliczenie", "Produkcja i premie", payroll),
        ("Publikacja", "Archiwum", publication),
    ]
    return tuple({
        "title": title,
        "module": module,
        "status": status,
        "tone": tone,
        "description": description,
    } for title, module, (status, tone, description) in entries)


def progress_html(steps, period_label):
    """Static process ribbon; changing a module never changes what 'done' means."""
    items = []
    for i, step in enumerate(steps, 1):
        title = escape(step["title"], quote=True)
        status = escape(step["status"], quote=True)
        desc = escape(step["description"], quote=True)
        tone = step["tone"]
        if tone not in ("pending", "working", "done"):
            raise ValueError("Nieznany status procesu.")
        marker = "✓" if tone == "done" else "●" if tone == "working" else "○"
        items.append(
            f'<div class="erp-process-step erp-process-step--{tone}" title="{desc}">'
            f'<div class="erp-process-step-title"><span>{i:02d}</span> {title}</div>'
            f'<div class="erp-process-step-status">'
            f'<span aria-hidden="true">{marker}</span> {status}</div></div>'
        )
    month = escape(str(period_label), quote=True)
    return (
        '<section class="erp-process" aria-label="Postęp rozliczenia wybranego miesiąca">'
        '<div class="erp-process-heading"><strong>Etapy pracy</strong>'
        f'<span>{month}</span></div>'
        '<div class="erp-process-list">' + "".join(items) + '</div>'
        '<div class="erp-process-note">'
        'Statusy wynikają z bieżącej sesji i potwierdzonych operacji. '
        'Szkic i import plików nie oznaczają publikacji.</div></section>'
    )
