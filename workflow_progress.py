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
                   schedule_loaded, production_loaded, weights_loaded,
                   remote_status=None):
    """Describe monthly workflow in the actual business order; no network I/O."""
    year, month = int(year), int(month)
    month_key = f"{year:04d}-{month:02d}-01"
    remote = remote_status or {}
    schedule_saved = _saved_revision(state, year, month, "schedule")
    attendance_saved = _saved_revision(state, year, month, "attendance")
    extras_saved = state.get("_bonus_inputs_confirmed_by_period", {}).get(period_label) is True
    extras_present = period_label in state.get("_bonus_inputs_by_period", {})
    archive = state.get("history_v2", {})
    archived = period_label in archive
    remotely_archived = remote.get("archive") == "saved"
    publication_attendance = (state.get("_test_attendance_publications", {}).get(month_key) is True
                              or remote.get("attendance_publication") == "published")
    publication_bonus = (state.get("_test_payroll_publications", {}).get(month_key) is True
                         or remote.get("payroll_publication") == "published")

    if schedule_saved:
        plan = ("Zapisany szkic", "done",
                "Zapis harmonogramu tego miesiąca potwierdzony w bieżącej sesji.")
    elif remote.get("schedule") == "saved":
        plan = ("Zapisany w bazie", "done",
                "Szkic harmonogramu istnieje w Supabase. Przywróć go w module Harmonogram, "
                "aby edytować zapisane dane. Nie został opublikowany pracownikom.")
    elif schedule_loaded:
        plan = ("W przygotowaniu", "working",
                "Harmonogram utworzono lub wczytano lokalnie; zapis w bazie wymaga potwierdzenia.")
    elif remote_status is not None and remote.get("schedule") == "unknown":
        plan = ("Status nieznany", "working",
                "Nie udało się potwierdzić statusu zapisu. Nie oznacza to braku harmonogramu.")
    else:
        plan = ("Do zaplanowania", "pending",
                "Można przygotować przed rozpoczęciem miesiąca.")

    if attendance_saved:
        attendance = ("Zapisana ewidencja", "done",
                      "Szkic wejść, wyjść, nieobecności i nadgodzin zapisano; publikacja jest osobna.")
    elif remote.get("attendance") == "saved":
        attendance = ("Szkic w bazie", "done",
                      "W Supabase zapisano ewidencję. Przywróć harmonogram, a następnie ewidencję. "
                      "Sam szkic nie potwierdza wszystkich wejść i wyjść.")
    elif schedule_loaded:
        attendance = ("Do potwierdzenia", "working",
                      "Uzupełnij faktyczne wejścia, wyjścia, nieobecności i nadgodziny.")
    elif remote_status is not None and remote.get("attendance") == "unknown":
        attendance = ("Status nieznany", "working",
                      "Nie udało się sprawdzić ewidencji w bazie.")
    else:
        attendance = ("Oczekuje", "pending", "Najpierw przygotuj harmonogram.")

    if remote.get("bonuses") == "saved":
        extras = ("Zapisane w bazie", "done",
                  "Zatwierdzone dodatki znajdują się w zapisanej wersji roboczej miesiąca. "
                  "Przywróć ją przed edycją.")
    elif extras_saved:
        extras = ("Zatwierdzone lokalnie", "working",
                  "Dodatki zatwierdzono w formularzu, ale nie potwierdzono ich trwałego "
                  "zapisu. Użyj „Zapisz wersję roboczą miesiąca”.")
    elif remote.get("bonuses") == "draft":
        extras = ("Szkic w bazie", "working",
                  "Dane dodatków zapisano w wersji roboczej, ale brak potwierdzenia "
                  "ostatecznego zatwierdzenia formularza.")
    elif extras_present:
        extras = ("Do zatwierdzenia", "working",
                  "Wartości robocze nie są potwierdzone przyciskiem zapisu dodatków.")
    elif remote_status is not None and remote.get("bonuses") == "unknown":
        extras = ("Status nieznany", "working",
                  "Nie udało się sprawdzić zapisanych dodatków.")
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
        ("Rozliczenie w bazie", "done",
         "Zapisano rozliczenie w archiwum Supabase. Aby przeglądać wyniki, przywróć archiwum.")
        if remotely_archived else
        ("Rozliczenie w sesji", "working",
         "Rozliczenie zapisano lokalnie. Dla trwałości zapisz archiwum w Supabase.")
        if archived else
        ("Do przeliczenia", "pending",
         "Po skompletowaniu ewidencji, dodatków oraz produkcji przelicz premie.")
    )
    stored = (
        ("Zapisane w bazie", "done",
         "Archiwum tego okresu jest zapisane w Supabase. Publikacja pozostaje osobna.")
        if remotely_archived else
        ("W sesji · zapisz", "working",
         "Archiwum znajduje się w tej sesji. Zapisz je osobno w Supabase.")
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

    analyses = (
        ("Dostępne", "working", "Analiza zapisanego rozliczenia wybranego miesiąca.")
        if archived else
        ("W bazie · przywróć", "working",
         "Rozliczenie zapisano w Supabase; przywróć archiwum, by zobaczyć analizy.")
        if remotely_archived else
        ("Po rozliczeniu", "pending", "Najpierw zapisz rozliczenie wybranego miesiąca.")
    )
    saved_periods = remote.get("archived_periods")
    remotely_comparable = (isinstance(saved_periods, (list, tuple))
                           and len(saved_periods) >= 2)
    comparisons = (
        ("Dostępne", "working", "Wybierz dwa różne miesiące do porównania.")
        if len(archive) >= 2 else
        ("W bazie · przywróć", "working",
         "W Supabase zapisano co najmniej dwa miesiące; przywróć archiwum, aby je porównać.")
        if remotely_comparable else
        ("Potrzebne 2 miesiące", "pending", "Zapisz rozliczenia co najmniej dwóch różnych miesięcy.")
    )
    # The same seven stages appear in the sidebar and the ribbon. Source files
    # belong to settlement; publication remains a separate action in Archive.
    settlement = payroll if (archived or remotely_archived) else production
    if not (archived or remotely_archived) and production_loaded and weights_loaded:
        settlement = ("Do sprawdzenia i przeliczenia", "working", production[2] + " " + payroll[2])
    archive_stage = (stored[0], stored[1], stored[2] + " Publikacja: " + published[0].lower() + ". " + published[2])
    entries = (
        ("Harmonogram", "Harmonogram", plan),
        ("Obecności i nadgodziny", "Obecności i nadgodziny", attendance),
        ("Dodatki premiowe", "Dodatki premiowe", extras),
        ("Rozliczenie premii", "Rozliczenie premii", settlement),
        ("Archiwum", "Archiwum", archive_stage),
        ("Analizy", "Analizy", analyses),
        ("Porównania", "Porównania", comparisons),
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
        'pracownikom to trzy różne operacje. Statusy zapisów odnoszą się do Supabase lub sesji; '
        'dane z bazy trzeba przywrócić przed edycją.'
        '</div></section>'
    )
