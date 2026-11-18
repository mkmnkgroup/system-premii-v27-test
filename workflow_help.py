"""Expanded operational help shown only when a user clicks the ⓘ icon.

Keep explanatory copy here rather than cluttering the Streamlit module pages.
Status notices, errors, confirmation dialogs and financial values remain
visible outside these help panes.
"""

MODULE_HELP = {
    "schedule": """
**Kiedy używać:** przed rozpoczęciem miesiąca, nawet kilka tygodni wcześniej.

1. Wybierz miesiąc i sprawdź listę pracowników oraz systemy zmian.
2. Wygeneruj harmonogram albo wczytaj gotowy plik Excel.
3. Sprawdź dni wolne, święta, zmiany i godziny. Dopiero potem zapisz szkic w Supabase.

**Nowy harmonogram a zapis:** wygenerowanie nowego grafiku zmienia dane tylko na ekranie. Zapisanie szkicu utrwala go w bazie, ale nie udostępnia go pracownikom.

**Po wylogowaniu:** wybierz ten sam miesiąc i użyj „Przywróć szkic z Supabase”. Jeśli w bazie jest już harmonogram, nadpisanie wymaga świadomego potwierdzenia.

**Uwaga:** ponowne wygenerowanie może usunąć ręczne poprawki, a nawet wpisy obecności z bieżącej sesji. Przed zastąpieniem eksportuj aktualny grafik jako kopię.
""",
    "attendance": """
**Kiedy używać:** w trakcie miesiąca i podczas jego zamykania.

1. Przywróć właściwy harmonogram miesiąca.
2. Zweryfikuj nieobecności i nanieś je ręcznie albo przez import Excel.
3. Uzupełnij faktyczne wejścia i wyjścia. Opcjonalnie przyjmij planowane godziny dla dni, w których nie ma żadnego wpisu, po świadomym sprawdzeniu nieobecności.
4. Wprowadź **nadgodziny ręcznie** w pierwszej kolumnie tabeli, sprawdzając nazwisko i datę.
5. Skontroluj brakujące godziny i zapisz ewidencję w Supabase.

**Ważne:** opcja „według harmonogramu” nie odczytuje podpisów pracowników, nie zmienia nadgodzin i nie uzupełnia przyszłych dni. Ręcznie wpisanych godzin nie nadpisuje.

**Zapis a publikacja:** zapis szkicu umożliwia kontynuację pracy po ponownym logowaniu. Udostępnienie ewidencji kontom pracowników to osobna, jednorazowa operacja z potwierdzeniem.
""",
    "bonuses": """
**Co tu rozliczasz:** trzy niezależne składniki: godziny pracy wózka, obsługę palet oraz premie specjalne.

1. Wpisz rzeczywistą liczbę godzin wózka dla każdej osoby. Pula dodatku dzieli się proporcjonalnie do wpisanych godzin.
2. Podaj łączną liczbę palet za miesiąc i wskaż osoby uczestniczące w podziale. Pula to liczba palet pomnożona przez stawkę w ustawieniach.
3. Dodaj premie specjalne, wskazując pracownika, kwotę i powód. Jeśli ich nie było, pozostaw sekcję pustą.

**Zatwierdzenie:** kliknij „Zapisz i przelicz dodatki”. Dopiero ten przycisk przenosi wpisane wartości do obliczeń i oznacza etap jako wykonany w bieżącej sesji. Jeśli nic nie wystąpiło, możesz zatwierdzić zera.

**Po wylogowaniu:** aby odtworzyć dodatki, zapisz również „Wersję roboczą miesiąca” w Supabase. Sam przycisk w formularzu nie zastępuje trwałej kopii danych.
""",
    "settlement": """
**Kiedy używać:** gdy masz już dane produkcyjne za cały rozliczany miesiąc i wprowadzone dodatki.

1. W tym module otwórz „Dane źródłowe do rozliczenia” i wgraj **raport produkcji oraz katalog wag razem**.
2. Sprawdź wykluczone kategorie klientów, liczbę pozycji, sztuk i sumę masy.
3. Jeśli brakuje wag, uzupełnij je po weryfikacji. Obliczenia są wstrzymywane, dopóki dane są niekompletne.
4. Wybierz wariant rozliczania nieobecności i przejrzyj indywidualne kwoty: premię główną, nadgodziny, wózek, palety oraz premie specjalne.
5. Po kontroli zapisz rozliczenie w archiwum, a następnie w Supabase.

**Czego to nie robi:** samo przeliczenie nie publikuje żadnych danych pracownikom. Pliki Excel z produkcją i wagami są obecnie przechowywane tylko w sesji i po jej utracie wymagają ponownego wgrania.
""",
    "archive": """
**Do czego służy:** przechowuje zakończone miesięczne rozliczenia, aby można było je przywracać, analizować i porównywać.

**Dwa różne zapisy:**
- Zapis rozliczenia do archiwum sesji umożliwia jego bieżące przeglądanie.
- „Zapisz archiwum w Supabase” utrwala archiwum na czas po wylogowaniu i otwarciu aplikacji ponownie.

**Publikacja to osobny krok.** Dopiero świadome zatwierdzenie publikacji udostępnia premie pracownikom. Przed publikacją sprawdź przypisania kont, składniki premii i nadgodziny. Sam zapis archiwum niczego nie wypłaca ani nie udostępnia.
""",
    "analytics": """
**Do czego służą analizy:** pomagają ocenić zakończony miesiąc, np. rozkład premii pracowników i nadgodzin w zespole.

Najpierw zapisz rozliczenie w archiwum. Jeśli po nowym logowaniu archiwum istnieje w Supabase, ale wykresy są puste, przywróć archiwum w module „Archiwum”.

**Analiza jest dodatkowa:** nie wpływa na naliczane kwoty i nie zastępuje kontroli poprawności danych produkcji oraz obecności.
""",
    "comparisons": """
**Kiedy używać:** po zapisaniu co najmniej dwóch różnych miesięcy.

Wybierz dwa okresy z archiwum. Porównasz wyniki produkcyjne, strukturę dodatków oraz kwoty dla zespołu i poszczególnych pracowników.

**Ważne:** porównania opierają się na archiwalnych wynikach, a nie na aktualnie otwartym arkuszu produkcji. Po ponownym logowaniu przywróć archiwum z Supabase, jeśli nie ma dostępnych zapisanych okresów.

To funkcja analityczna; nie zmienia premii i nie publikuje danych.
""",
    "settings": """
**Co ustawiasz:** listę pracowników i stanowisk, grupy zmianowe, stawki nadgodzin, pulę wózka, stawkę za paletę, podstawę premii, średnie bazowe oraz wagi wskaźników.

**Jak postępować:** sprawdź dane przed rozpoczęciem miesiąca i po każdej zmianie personelu lub stawek. Zmiany zatwierdź przyciskiem zapisu ustawień.

**Średnie bazowe:** ustalone wartości powinny pozostawać stałe do świadomej aktualizacji. Wagi wskaźników „pozycje / sztuki / masa” określają ich udział w obliczaniu premii produkcyjnej.

**Katalog wag produktów** to inna rzecz niż procentowe wagi wskaźników. Plik katalogu wag wgrywasz razem z raportem produkcji, w module „Rozliczenie premii”.
""",
}

BONUS_HELP = {
    "forklift": """
**Jak rozliczamy wózek:** dla każdej osoby wpisz liczbę godzin pracy wózka w wybranym miesiącu. System sumuje godziny i rozdziela miesięczną pulę między osoby proporcjonalnie do ich udziału.

**Przykład:** jeśli jedna osoba ma 5 godzin, a druga 15 godzin, dzielą pulę w proporcji 25% do 75%.

**Kiedy zostawić zero:** gdy dana osoba nie pracowała na wózku. Nie wpisuj planowanego czasu zamiast rzeczywistego. Zapisz formularz po zakończeniu wprowadzania.
""",
    "pallets": """
**Jak rozliczamy palety:** wpisz łączną liczbę palet rozładowanych i załadowanych w miesiącu. Stawkę za paletę ustalasz w „Ustawieniach”.

**Podział:** system mnoży liczbę palet przez stawkę, po czym dzieli pulę po równo między pracowników zaznaczonych poniżej. Jeśli było 20 palet po 10 zł i dwie wybrane osoby, każda otrzyma po 100 zł.

**Ważne:** sprawdź zaznaczone osoby przed zapisem. Przy dodatniej liczbie palet przynajmniej jedna osoba musi być wybrana.
""",
    "specials": """
**Kiedy używać:** gdy chcesz przyznać jednorazowy dodatkowy składnik premii, np. za szczególne zadanie lub pracę wymagającą dodatkowego zaangażowania.

Dla każdej nagrody dodaj osobny wiersz: pracownik, kwota, powód i osoba przyznająca. Jeden pracownik może mieć kilka takich wpisów w tym samym miesiącu.

**Jeśli nie ma premii specjalnych:** pozostaw tabelę pustą. Każda zatwierdzona premia specjalna zostanie pokazana w szczegółowym rozliczeniu pracownika.
""",
}

SOURCES_HELP = """
**Dlaczego dwa pliki są razem:** raport produkcyjny i katalog wag są u Ciebie aktualizowane w tym samym cyklu miesięcznym.

- **Raport produkcji** zawiera pozycje, sztuki, daty oraz kategorie klientów.
- **Katalog wag** pozwala przypisać wagę jednej sztuki według producenta i artykułu, a następnie obliczyć całkowitą masę.

Wgraj oba pliki za właściwy miesiąc. System pominie wykluczone grupy klientów i wskaże brakujące dopasowania wag.

**Co ważne:** import jest przypisany do miesiąca w bieżącej sesji. Zmiana zakładki nie usuwa plików, ale zamknięcie sesji może wymagać ponownego importu. Sam import nie zapisuje plików do Supabase ani nie nalicza automatycznie premii bez kontroli.
"""

DRAFT_HELP = """
**Wersja robocza miesiąca** to dodatkowy zapis stanu przygotowywanego rozliczenia, oddzielny od szkiców harmonogramu, ewidencji i archiwum.

**Kiedy używać:** gdy chcesz zachować wpisane ustawienia i dodatki przed przerwaniem pracy. Po ponownym logowaniu wybierz ten sam miesiąc i użyj „Przywróć zapis z bazy”.

**Autozapis:** można go włączyć po początkowym zapisaniu lub przywróceniu wersji roboczej. Działa przy kolejnych przeliczeniach strony z odstępem między zapisami — nie oznacza ciągłego zapisu każdej klawiaturowej zmiany.

**Czego nie zapisuje:** plików źródłowych produkcji i wag ani opublikowanych wyników. Nie zastępuje też zapisania archiwum i osobnej publikacji.
"""

SCHEDULE_DRAFT_HELP = """
**Szkic harmonogramu w Supabase** to trwała kopia zaplanowanego grafiku dla wybranego miesiąca.

- **Zapisz aktualny harmonogram** — zachowuje grafik, który masz na ekranie. Jeśli istnieje wcześniejsza wersja, aplikacja prosi o potwierdzenie zastąpienia.
- **Przywróć szkic z Supabase** — odtwarza wcześniej zapisaną wersję. Uwaga: zastępuje bieżący grafik w sesji.
- **Publikacja** dla pracowników to osobna czynność. Zapis szkicu sam w sobie niczego nie udostępnia.

Po zalogowaniu na nowo status „Zapisany w bazie” oznacza istnienie szkicu, ale żeby edytować jego zawartość, trzeba go przywrócić.
"""

ATTENDANCE_DRAFT_HELP = """
**Szkic ewidencji** utrwala godziny wejścia i wyjścia, nieobecności, nadgodziny oraz informację, które godziny przyjęto zgodnie z grafikiem.

**Kolejność:** przywróć właściwy harmonogram, uzupełnij lub sprawdź ewidencję, wpisz ręcznie nadgodziny i kliknij „Zapisz ewidencję w Supabase”.

**Po ponownym logowaniu:** najpierw przywróć harmonogram, potem ewidencję. Zapis i przywracanie nie publikują danych pracownikom.

**Godziny według planu** są oznaczone jako założone po weryfikacji nieobecności. Nie są równoznaczne z podpisem na fizycznej liście.
"""

ARCHIVE_DRAFT_HELP = """
**Zapis archiwum w Supabase** zachowuje zamknięte rozliczenia na później. Dzięki temu można do nich wrócić po wylogowaniu i korzystać z analiz oraz porównań.

Zapisz najpierw rozliczenie do archiwum sesji, następnie użyj „Zapisz archiwum w Supabase”. Gdy wrócisz po przerwie, możesz wybrać „Przywróć archiwum z Supabase”.

**To nie jest publikacja pracownikom** — paski i premie wymagają osobnego, świadomego zatwierdzenia publikacji.
"""
