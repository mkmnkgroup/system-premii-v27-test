# System Premii 2.7 – Wersja Testowa

Publiczny podgląd do testów na fikcyjnych danych. Źródło: feature/dark-premium-ui,
commit eb341a552d82cf1ef750cf6ec172406832123e50; osobna historia repozytorium.

Uruchomienie: `pip install -r requirements.txt`, następnie `streamlit run app_v2.py`.
Streamlit Community Cloud: repozytorium mkmnkgroup/system-premii-v27-test,
gałąź main, plik app_v2.py, nazwa system-premii-v27-test. Bez sekretów.

Podgląd nie odczytuje sekretów ani produkcyjnej bazy. Ustawienia i archiwum
są odseparowane dla każdej sesji przeglądarki i nie są trwale przechowywane.
Nowa sesja może zacząć od danych domyślnych. Pobierz wyniki do Excel przed jej końcem.
Testy integracyjne PostgreSQL dotyczą modułu źródłowego, nie zapisu podglądu.

Wbudowana lista zawiera tylko fikcyjnych pracowników. Grupy klientów test,
UA-2, АНД, ОПТ_UA i ФОП_UA są obowiązkowo wyłączone z premii i analiz.
Testy: `python -m unittest discover -s tests -v`.
