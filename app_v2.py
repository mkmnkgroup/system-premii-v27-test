import calendar
from datetime import datetime
import io
import json
import re
import google.generativeai as genai
import holidays
import pandas as pd
import PIL.Image
import plotly.express as px
import streamlit as st

# ==========================================
# KONFIGURACJA I STYLIZACJA CSS
# ==========================================
st.set_page_config(
    page_title="System Premii 2.7 – Wersja Testowa",
    layout="wide",
    page_icon="📈",
)

from premium_theme import apply_theme, hero
from employee_excel import read_employees_excel, write_employees_excel

if "premium_ui_mode" not in st.session_state:
  st.session_state.premium_ui_mode = "Jasny"

with st.sidebar:
  st.segmented_control(
      "Wygląd aplikacji",
      options=["Ciemny", "Jasny"],
      key="premium_ui_mode",
  )
apply_theme(st.session_state.premium_ui_mode)
hero()

# ==========================================
# DANE PUBLICZNEGO PODGLĄDU — ODDZIELNIE DLA KAŻDEJ SESJI
# ==========================================
from preview_storage import load_item, save_item


def _load_database_item(key):
  return load_item(st.session_state, key)


def _save_database_item(key, value):
  save_item(st.session_state, key, value)
  return True


def load_archive():
  return _load_database_item("archive_v27")


def save_archive(archive_data):
  return _save_database_item("archive_v27", archive_data)


def load_persistent_settings():
  return _load_database_item("settings_v27")


def save_persistent_settings(settings_dict):
  return _save_database_item("settings_v27", settings_dict)


def normalize_name(name):
  if pd.isna(name) or not str(name).strip():
    return ""
  words = str(name).strip().upper().split()
  words.sort()
  return " ".join(words)


def get_col_sum_flexible(df, possible_names):
  if df.empty:
    return 0.0
  low_possible = [p.lower() for p in possible_names]
  for col in df.columns:
    if str(col).strip().lower() in low_possible:
      return float(pd.to_numeric(df[col], errors="coerce").fillna(0).sum())
  return 0.0


@st.cache_data(show_spinner=False)
def load_excel_cached(file_bytes, filename):
  ext = filename.split(".")[-1].lower()
  return pd.read_excel(
      io.BytesIO(file_bytes), engine="xlrd" if ext == "xls" else "openpyxl"
  )


@st.cache_data(show_spinner=False)
def parse_daily_production_cached(prod_df, year, month_idx):
  days_in_month = calendar.monthrange(year, month_idx)[1]
  daily_map = {
      day: {"pcs": 0.0, "lines": 0.0, "weight": 0.0}
      for day in range(1, days_in_month + 1)
  }

  if not prod_df.empty:
    date_col, pcs_col, lines_col, weight_col = None, None, None, None

    for col in prod_df.columns:
      c_low = str(col).strip().lower()
      if not date_col and c_low in [
          "data",
          "date",
          "dzień",
          "dzien",
          "data przyjęcia",
          "data przyjecia",
      ]:
        date_col = col
      if not pcs_col and c_low in [
          "sztuki",
          "sztuka",
          "pcs",
          "ilość sztuk",
          "ilosc sztuk",
      ]:
        pcs_col = col
      if not lines_col and c_low in [
          "pozycje",
          "pozycja",
          "lines",
          "ilość pozycji",
          "ilosc pozycji",
      ]:
        lines_col = col
      if not weight_col and c_low in [
          "waga",
          "waga łączna",
          "waga laczna",
          "weight",
          "kg",
      ]:
        weight_col = col

    if date_col:
      for _, row in prod_df.iterrows():
        raw_date = row[date_col]
        if pd.isna(raw_date):
          continue
        try:
          dt = pd.to_datetime(raw_date, dayfirst=True, errors="coerce")
          if pd.notna(dt) and dt.year == year and dt.month == month_idx:
            d = dt.day
            p = (
                float(pd.to_numeric(row[pcs_col], errors="coerce"))
                if pcs_col and pd.notna(row[pcs_col])
                else 0.0
            )
            l = (
                float(pd.to_numeric(row[lines_col], errors="coerce"))
                if lines_col and pd.notna(row[lines_col])
                else 0.0
            )
            w = (
                float(pd.to_numeric(row[weight_col], errors="coerce"))
                if weight_col and pd.notna(row[weight_col])
                else 0.0
            )

            if d in daily_map:
              daily_map[d]["pcs"] += max(0.0, p)
              daily_map[d]["lines"] += max(0.0, l)
              daily_map[d]["weight"] += max(0.0, w)
        except Exception:
          pass

  return daily_map


def process_attendance_photo(image_file, api_key):
  try:
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")
    img = PIL.Image.open(image_file)

    prompt = """
        Przeanalizuj podane zdjęcie ręcznie wypisanej listy obecności.
        Zlokalizuj w tabeli dane:
        1. Datę dzienną (DD.MM.YYYY).
        2. Imię i Nazwisko pracownika.
        3. Faktyczną godzinę wejścia.
        4. Faktyczną godzinę wyjścia.
        5. Wartość z kolumny nadgodzin.

        Zwróć wynik WYŁĄCZNIE jako poprawny kod JSON (tablica obiektów):
        [
          {
            "data": "DD.MM.YYYY",
            "osoba": "IMIE NAZWISKO",
            "wejscie": "HH:MM",
            "wyjscie": "HH:MM",
            "nadgodziny": 0.0
          }
        ]
        """
    response = model.generate_content([img, prompt])
    raw_text = response.text.strip()

    match = re.search(r"\[.*\]", raw_text, re.DOTALL)
    if match:
      raw_text = match.group(0)

    return json.loads(raw_text)
  except Exception as e:
    st.error(f"Błąd analizy obrazu AI ({image_file.name}): {e}")
    return []


# ==========================================
# DOMYŚLNE DANE SYSTEMOWE I WCZYTANIE ZAPISANYCH
# ==========================================
st.warning("WERSJA TESTOWA — używaj wyłącznie fikcyjnych danych. "
           "Dane są dostępne tylko w bieżącej sesji i mogą zniknąć po jej zakończeniu. "
           "Listę pracowników i rozliczenia możesz pobrać do Excel.")
if "loaded_settings_v27" not in st.session_state:
  st.session_state.loaded_settings_v27 = load_persistent_settings()
saved_settings = st.session_state.loaded_settings_v27

from client_categories import CLIENT_CATEGORY_COLUMN, category_options, exclude_categories
from production_import import read_production, read_weights, prepare_production
from weight_research import product_search_url, validate_weight

@st.cache_data(show_spinner="Odczytywanie raportu produkcji...", max_entries=3)
def cached_read_production_v2(file_bytes):
  return read_production(file_bytes)

@st.cache_data(show_spinner="Odczytywanie bazy wag...", max_entries=3)
def cached_read_weights(file_bytes):
  return read_weights(file_bytes)

if "excluded_client_categories" not in st.session_state:
  st.session_state.excluded_client_categories = list(
      sorted(set(saved_settings.get("excluded_client_categories", [])) | {"test", "UA-2", "АНД", "ОПТ_UA", "ФОП_UA"}))


DEFAULT_ABSENCE_CODES = [
    {"Oznaczenie": "Brak", "Rodzaj nieobecności": "Brak"},
    {"Oznaczenie": "Z", "Rodzaj nieobecności": "URLOP NA ŻĄDANIE"},
    {
        "Oznaczenie": "W",
        "Rodzaj nieobecności": "URLOP WYPOCZYNKOWY WYKORZYSTANY",
    },
    {"Oznaczenie": "NO", "Rodzaj nieobecności": "NIEOBECNY"},
    {"Oznaczenie": "B", "Rodzaj nieobecności": "URLOP BEZPŁATNY"},
    {"Oznaczenie": "1", "Rodzaj nieobecności": "AKTUALNIE POTWIERDZONY"},
    {"Oznaczenie": "N", "Rodzaj nieobecności": "NIEOBECNOŚĆ NIEUSPRAWIEDLIWIONA"},
    {"Oznaczenie": "H", "Rodzaj nieobecności": "CHOROBOWE"},
    {"Oznaczenie": "K", "Rodzaj nieobecności": "KRWIODAWSTWO"},
    {"Oznaczenie": "SW", "Rodzaj nieobecności": "SIŁA WYŻSZA"},
    {"Oznaczenie": "NU", "Rodzaj nieobecności": "NIEOBECNOŚĆ USPRAWIEDLIWIONA"},
    {"Oznaczenie": "OŚ", "Rodzaj nieobecności": "ODEBRANE ZA ŚWIĘTO"},
]

DEFAULT_GROUPS = [
    {"Nazwa grupy": "GRUPA 1", "Czas pracy": "06:00-14:00"},
    {"Nazwa grupy": "GRUPA 2", "Czas pracy": "08:00-16:00"},
    {"Nazwa grupy": "GRUPA 3", "Czas pracy": "11:00-19:00"},
    {"Nazwa grupy": "GRUPA 4", "Czas pracy": "08:00-16:00"},
    {"Nazwa grupy": "GRUPA 5", "Czas pracy": "08:00-16:00"},
    {"Nazwa grupy": "GRUPA 6", "Czas pracy": "11:00-19:00"},
    {"Nazwa grupy": "GRUPA 7", "Czas pracy": "08:00-17:00"},
]

DEFAULT_EMPLOYEES = [
    {"OSOBA": "TEST PRACOWNIK 01", "GRUPA": "GRUPA 1",
     "SYSTEM": "PONIEDZIAŁEK-PIĄTEK", "STANOWISKO": "MAGAZYNIER",
     "FUNKCJA": "1 SKANOWANIE", "UPRAWNIENIA UDT": True},
    {"OSOBA": "TEST PRACOWNIK 02", "GRUPA": "GRUPA 2",
     "SYSTEM": "WTOREK-SOBOTA", "STANOWISKO": "BRYGADZISTA",
     "FUNKCJA": "2 SKANOWANIE", "UPRAWNIENIA UDT": False},
    {"OSOBA": "TEST PRACOWNIK 03", "GRUPA": "GRUPA 7",
     "SYSTEM": "PONIEDZIAŁEK-PIĄTEK", "STANOWISKO": "KIEROWNIK",
     "FUNKCJA": "KIEROWNIK", "UPRAWNIENIA UDT": False},
]

PL_DAYS = {
    0: "poniedziałek",
    1: "wtorek",
    2: "środa",
    3: "czwartek",
    4: "piątek",
    5: "sobota",
    6: "niedziela",
}

# Inicjalizacja Stanu Sesji (z uwzględnieniem zapisanych ustawień)
if "history_v2" not in st.session_state:
  st.session_state.history_v2 = load_archive()
if "current_schedule_df" not in st.session_state:
  st.session_state.current_schedule_df = pd.DataFrame()
if "absence_codes_df" not in st.session_state:
  st.session_state.absence_codes_df = pd.DataFrame(DEFAULT_ABSENCE_CODES)
if "groups_df" not in st.session_state:
  st.session_state.groups_df = pd.DataFrame(DEFAULT_GROUPS)

if "employees_df" not in st.session_state:
  if "employees_df" in saved_settings:
    st.session_state.employees_df = pd.DataFrame(saved_settings["employees_df"])
  else:
    st.session_state.employees_df = pd.DataFrame(DEFAULT_EMPLOYEES)

if "special_bonuses_df" not in st.session_state:
  st.session_state.special_bonuses_df = pd.DataFrame(
      columns=[
          "Pracownik",
          "Kwota netto premii",
          "Powód przyznania premii",
          "Kto przyznał",
      ]
  )
if "forklift_hours_df" not in st.session_state:
  current_emps_list = st.session_state.employees_df["OSOBA"].tolist()
  st.session_state.forklift_hours_df = pd.DataFrame(
      [{"OSOBA": name, "CZAS WÓZKA (godz.)": 0.0} for name in current_emps_list]
  )
if "imported_absences_df" not in st.session_state:
  st.session_state.imported_absences_df = pd.DataFrame()
if "gemini_api_key" not in st.session_state:
  st.session_state.gemini_api_key = ""

# Parametry z zapisanych ustawień lub domyślne
if "base_bonus_salary" not in st.session_state:
  st.session_state.base_bonus_salary = saved_settings.get(
      "base_bonus_salary", 4300.0
  )
if "kierownik_bonus_multiplier" not in st.session_state:
  st.session_state.kierownik_bonus_multiplier = saved_settings.get(
      "kierownik_bonus_multiplier", 1.35
  )
if "forklift_pool" not in st.session_state:
  st.session_state.forklift_pool = saved_settings.get("forklift_pool", 600.0)
if "rate_pallet" not in st.session_state:
  st.session_state.rate_pallet = saved_settings.get("rate_pallet", 10.0)

if "avg_lines_12m" not in st.session_state:
  st.session_state.avg_lines_12m = saved_settings.get(
      "avg_lines_12m", 17322.50
  )
if "w_lines" not in st.session_state:
  st.session_state.w_lines = saved_settings.get("w_lines", 42.86)
if "avg_pcs_12m" not in st.session_state:
  st.session_state.avg_pcs_12m = saved_settings.get("avg_pcs_12m", 58710.75)
if "w_pcs" not in st.session_state:
  st.session_state.w_pcs = saved_settings.get("w_pcs", 28.57)
if "avg_weight_12m" not in st.session_state:
  st.session_state.avg_weight_12m = saved_settings.get(
      "avg_weight_12m", 26417.42
  )
if "w_weight" not in st.session_state:
  st.session_state.w_weight = saved_settings.get("w_weight", 28.57)

if "ot_kierownik" not in st.session_state:
  st.session_state.ot_kierownik = saved_settings.get("ot_kierownik", 35.0)
if "ot_brygadzista" not in st.session_state:
  st.session_state.ot_brygadzista = saved_settings.get("ot_brygadzista", 30.0)
if "ot_magazynier" not in st.session_state:
  st.session_state.ot_magazynier = saved_settings.get("ot_magazynier", 25.0)


# ==========================================
# GENEROWANIE HARMONOGRAMU
# ==========================================
# Cache disabled: arguments contain dictionaries, which Streamlit cannot hash reliably.
def generate_schedule_cached(year, month_idx, emp_tuples, groups_tuples):
  days_in_month = calendar.monthrange(year, month_idx)[1]
  pl_holidays = holidays.Poland(years=year)

  maciej_early_days = set()
  maciej_emp = None

  for emp in emp_tuples:
    norm_emp_name = normalize_name(emp.get("OSOBA", ""))
    if "BORZECKI" in norm_emp_name or "MACIEJ" in norm_emp_name:
      maciej_emp = emp
      break

  if maciej_emp is not None:
    for day in range(1, days_in_month + 1):
      date_obj = datetime(year, month_idx, day)
      day_name = PL_DAYS[date_obj.weekday()]
      week_num = date_obj.isocalendar()[1]
      is_holiday = date_obj in pl_holidays

      is_working_day = True
      sys_val = str(maciej_emp.get("SYSTEM", ""))
      if "PONIEDZIAŁEK" in sys_val.upper() and day_name in [
          "sobota",
          "niedziela",
      ]:
        is_working_day = False
      elif "WTOREK" in sys_val.upper() and day_name in [
          "niedziela",
          "poniedziałek",
      ]:
        is_working_day = False
      if is_holiday:
        is_working_day = False

      if is_working_day:
        try:
          g_num = int(
              str(maciej_emp.get("GRUPA", "")).replace("GRUPA", "").strip()
          )
        except Exception:
          g_num = 1
        shift_rotation = ((week_num - 1 + (g_num - 1)) % 3) + 1
        if shift_rotation == 1:
          maciej_early_days.add(date_obj.strftime("%d.%m.%Y"))

  schedule_rows = []

  for day in range(1, days_in_month + 1):
    date_obj = datetime(year, month_idx, day)
    date_str = date_obj.strftime("%d.%m.%Y")
    day_name = PL_DAYS[date_obj.weekday()]
    week_num = date_obj.isocalendar()[1]
    is_holiday = date_obj in pl_holidays

    for emp in emp_tuples:
      is_working_day = True
      sys_val = str(emp.get("SYSTEM", ""))

      if "PONIEDZIAŁEK" in sys_val.upper() and day_name in [
          "sobota",
          "niedziela",
      ]:
        is_working_day = False
      elif "WTOREK" in sys_val.upper() and day_name in [
          "niedziela",
          "poniedziałek",
      ]:
        is_working_day = False
      if is_holiday:
        is_working_day = False

      status_dzien = (
          "Święto"
          if is_holiday
          else ("Pracujący" if is_working_day else "Wolny")
      )

      if not is_working_day:
        czas_zmiany = "Wolne"
        shift_val = "Wolne"
        default_start_end = "Wolne"
      else:
        default_start_end = ""
        g_str = str(emp.get("GRUPA", ""))
        try:
          g_num = int(g_str.replace("GRUPA", "").strip())
        except Exception:
          g_num = 1

        default_group_time = "08:00-16:00"
        for g_row in groups_tuples:
          if (
              str(g_row.get("Nazwa grupy", "")).strip().upper()
              == g_str.strip().upper()
          ):
            default_group_time = str(g_row.get("Czas pracy", "08:00-16:00"))
            break

        if g_num in [1, 2, 3]:
          shift_rotation = ((week_num - 1 + (g_num - 1)) % 3) + 1
          shift_val = shift_rotation
          if shift_rotation == 1:
            czas_zmiany = "06:00-14:00"
          elif shift_rotation == 2:
            czas_zmiany = "08:00-16:00"
          else:
            czas_zmiany = "11:00-19:00"
        else:
          czas_zmiany = default_group_time
          shift_val = g_num

        if g_num == 8:
          if date_str in maciej_early_days:
            czas_zmiany = "06:00-14:00"
            shift_val = 1
          else:
            czas_zmiany = "07:30-15:30"
            shift_val = 8

        if day_name == "poniedziałek":
          czas_zmiany = "08:00-17:00"
        elif day_name == "sobota":
          czas_zmiany = "08:00-16:00"

      schedule_rows.append({
          "DATA": date_str,
          "DZIEŃ TYGODNIA": day_name,
          "OSOBA": emp.get("OSOBA", ""),
          "STANOWISKO": emp.get("STANOWISKO", ""),
          "ZMIANA": shift_val if not is_holiday else "Święto",
          "CZAS ZMIANY": czas_zmiany,
          "DZIEŃ PRACUJĄCY/WOLNY": status_dzien,
          "GODZINA ROZPOCZĘCIA": default_start_end,
          "GODZINA ZAKOŃCZENIA": default_start_end,
          "FAKTYCZNIE WEJŚCIE": "",
          "FAKTYCZNIE WYJŚCIE": "",
          "NIEOBECNOŚĆ": "Brak",
          "NADGODZINY (godz.)": 0.0,
      })

  return pd.DataFrame(schedule_rows)


def generate_schedule(year, month_idx):
  emp_tuples = tuple(st.session_state.employees_df.to_dict("records"))
  groups_tuples = tuple(st.session_state.groups_df.to_dict("records"))
  return generate_schedule_cached(year, month_idx, emp_tuples, groups_tuples)


# ==========================================
# GŁÓWNA LOGIKA KALKULATORA WYNAGRODZEŃ
# ==========================================
def calculate_payroll(
    df_sched,
    employees_df,
    max_bonus_per_emp,
    forklift_hours_df,
    total_forklift_hours,
    pallet_pay_per_selected_emp,
    selected_pallet_emps,
    daily_work_pct_map,
    special_bonuses_df,
    include_absence_deduction=False,
):
  emp_summary = []
  emp_details_map = {}
  unique_emps = employees_df["OSOBA"].dropna().unique().tolist()

  fk_dict = dict(
      zip(
          forklift_hours_df["OSOBA"],
          pd.to_numeric(
              forklift_hours_df["CZAS WÓZKA (godz.)"], errors="coerce"
          ).fillna(0.0),
      )
  )

  for emp_name in unique_emps:
    emp_df = df_sched[
        df_sched["OSOBA"].str.strip().str.upper()
        == str(emp_name).strip().upper()
    ]
    emp_info_matches = employees_df[employees_df["OSOBA"] == emp_name]
    emp_info = emp_info_matches.iloc[0] if not emp_info_matches.empty else {}

    position = emp_info.get("STANOWISKO", "MAGAZYNIER")
    func = emp_info.get("FUNKCJA", "")
    emp_forklift_hours = float(fk_dict.get(emp_name, 0.0))

    days_worked = len(
        emp_df[
            (emp_df["DZIEŃ PRACUJĄCY/WOLNY"] == "Pracujący")
            & (emp_df["NIEOBECNOŚĆ"].isin(["Brak", "", "None"]))
        ]
    )
    absent_rows = emp_df[~emp_df["NIEOBECNOŚĆ"].isin(["Brak", "", "None"])]
    absent_days = len(absent_rows)
    total_ot = emp_df["NADGODZINY (godz.)"].sum()

    ot_rate = st.session_state.ot_magazynier
    if "KIEROWNIK" in str(position).upper():
      ot_rate = st.session_state.ot_kierownik
    elif "BRYGADZISTA" in str(position).upper():
      ot_rate = st.session_state.ot_brygadzista

    ot_pay = total_ot * ot_rate
    scheduled_work_days = len(
        emp_df[emp_df["DZIEŃ PRACUJĄCY/WOLNY"] == "Pracujący"]
    )
    attendance_ratio = (
        (days_worked / scheduled_work_days) if scheduled_work_days > 0 else 0.0
    )

    if include_absence_deduction:
      # Deduct only the production share of scheduled working days missed.
      # A day is counted once, even if multiple absence entries exist.
      absent_work_days = {
          int(str(row["DATA"]).split(".")[0])
          for _, row in absent_rows.iterrows()
          if row["DZIEŃ PRACUJĄCY/WOLNY"] == "Pracujący"
      }
      deduction_pct = min(
          100.0,
          max(0.0, sum(daily_work_pct_map.get(day, 0.0)
                       for day in absent_work_days)),
      )
      effective_ratio = 1.0 - deduction_pct / 100.0
    else:
      deduction_pct = 0.0
      effective_ratio = 1.0

    base_emp_bonus = max_bonus_per_emp
    if "KIEROWNIK" in str(position).upper() or "KIEROWNIK" in str(func).upper():
      base_emp_bonus *= st.session_state.kierownik_bonus_multiplier

    calculated_bonus = base_emp_bonus * effective_ratio

    emp_forklift_pct = (
        (emp_forklift_hours / total_forklift_hours * 100.0)
        if total_forklift_hours > 0
        else 0.0
    )
    forklift_pay = (
        (st.session_state.forklift_pool * (emp_forklift_pct / 100.0))
        if total_forklift_hours > 0
        else 0.0
    )
    pallet_pay = (
        pallet_pay_per_selected_emp if emp_name in selected_pallet_emps else 0.0
    )

    spec_bonus_val = 0.0
    spec_reasons_list = []
    if (
        not special_bonuses_df.empty
        and "Pracownik" in special_bonuses_df.columns
    ):
      spec_df = special_bonuses_df.copy()
      spec_df["Kwota netto premii"] = pd.to_numeric(
          spec_df["Kwota netto premii"], errors="coerce"
      ).fillna(0.0)
      matched_spec = spec_df[
          spec_df["Pracownik"].apply(normalize_name) == normalize_name(emp_name)
      ]
      spec_bonus_val = matched_spec["Kwota netto premii"].sum()
      for _, s_row in matched_spec.iterrows():
        r_txt = str(s_row.get("Powód przyznania premii", "")).strip()
        k_txt = str(s_row.get("Kto przyznał", "")).strip()
        q_val = float(s_row.get("Kwota netto premii", 0.0))
        if q_val > 0:
          spec_reasons_list.append(
              f"{q_val:,.2f} zł — {r_txt}"
              + (f" (przyznał: {k_txt})" if k_txt else "")
          )

    total_payout = (
        calculated_bonus + ot_pay + spec_bonus_val + forklift_pay + pallet_pay
    )

    absences_list = []
    for _, abs_r in absent_rows.iterrows():
      try:
        day_n = int(str(abs_r["DATA"]).split(".")[0])
      except Exception:
        day_n = 1
      day_work_pct = daily_work_pct_map.get(day_n, 0.0)

      absences_list.append({
          "Data": abs_r["DATA"],
          "Dzień tygodnia": abs_r["DZIEŃ TYGODNIA"],
          "Rodzaj nieobecności": abs_r["NIEOBECNOŚĆ"],
          "Udział pracy w miesiącu (%)": day_work_pct,
      })

    emp_summary.append({
        "Pracownik": emp_name,
        "Stanowisko": position,
        "Dni przepracowane": days_worked,
        "Dni nieobecności": absent_days,
        "% Potrącenia": deduction_pct,
        "Czas wózka (h)": emp_forklift_hours,
        "% Udział wózek": emp_forklift_pct,
        "Dodatek Wózek (zł)": forklift_pay,
        "Dodatek Palety (zł)": pallet_pay,
        "Nadgodziny (godz.)": total_ot,
        "Nadgodziny (zł)": ot_pay,
        "Premia (zł)": calculated_bonus,
        "Premia Specjalna (zł)": spec_bonus_val,
        "ŁĄCZNA PREMIA / DODATKI (zł)": total_payout,
    })

    emp_details_map[emp_name] = {
        "position": position,
        "emp_forklift_hours": emp_forklift_hours,
        "emp_forklift_pct": emp_forklift_pct,
        "forklift_pay": forklift_pay,
        "pallet_pay": pallet_pay,
        "days_worked": days_worked,
        "scheduled_days": scheduled_work_days,
        "absent_days": absent_days,
        "deduction_pct": deduction_pct,
        "base_emp_bonus": base_emp_bonus,
        "calculated_bonus": calculated_bonus,
        "total_ot": total_ot,
        "ot_pay": ot_pay,
        "spec_bonus_val": spec_bonus_val,
        "spec_reasons_list": spec_reasons_list,
        "total_payout": total_payout,
        "absences_table": pd.DataFrame(absences_list),
    }

  return pd.DataFrame(emp_summary), emp_details_map


# ==========================================
# PASEK BOCZNY
# ==========================================
st.sidebar.markdown("#### ◈ System Premii 2.7")
st.sidebar.caption("CENTRUM OPERACYJNE · WERSJA TESTOWA")
st.sidebar.markdown("**OKRES PRACY**")
months_list = [
    "Styczeń",
    "Luty",
    "Marzec",
    "Kwiecień",
    "Maj",
    "Czerwiec",
    "Lipiec",
    "Sierpień",
    "Wrzesień",
    "Październik",
    "Listopad",
    "Grudzień",
]
gen_month_name = st.sidebar.selectbox(
    "Miesiąc:", months_list, index=datetime.now().month - 1
)
gen_month_idx = months_list.index(gen_month_name) + 1
gen_year = st.sidebar.number_input("Rok:", value=datetime.now().year, step=1)
period_key = f"{gen_month_name} {gen_year}"

if st.sidebar.button("🚀 Wygeneruj Harmonogram", type="primary"):
  st.session_state.current_schedule_df = generate_schedule(
      gen_year, gen_month_idx
  )
  st.sidebar.success(f"Wygenerowano na {period_key}!")

st.sidebar.markdown("---")
st.sidebar.markdown("**PLIKI DO ROZLICZENIA**")
uploaded_month_file = st.sidebar.file_uploader(
    "Wgraj raport produkcji (Excel):", type=["xlsx", "xls"]
)

# Odczyt kategorii tylko z przeslanego pliku; nie zapisujemy danych klientow.
client_categories_in_file = []
if uploaded_month_file is not None:
  try:
    _production_preview = cached_read_production_v2(uploaded_month_file.getvalue())
    client_categories_in_file = category_options(_production_preview)
  except (ValueError, OSError, ImportError) as exc:
    st.sidebar.warning("Nie mozna odczytac kategorii klientow z pliku.")

uploaded_weights_file = st.sidebar.file_uploader(
    "Aktualna baza wag (Excel .xlsx):", type=["xlsx"], key="current_weights_file"
)

# Initialize the first period before computing its readiness.
if "schedule_period_key" not in st.session_state:
  st.session_state.schedule_period_key = period_key if not st.session_state.current_schedule_df.empty else None
if st.session_state.current_schedule_df.empty and st.session_state.schedule_period_key is None:
  st.session_state.current_schedule_df = generate_schedule(gen_year, gen_month_idx)
  st.session_state.schedule_period_key = period_key
_schedule_matches_period = (
    not st.session_state.current_schedule_df.empty
    and st.session_state.schedule_period_key == period_key
)

# ==========================================
# PANEL PROCESU - planowanie jest dostępne przed rozpoczęciem miesiąca.
# ==========================================
# Power Apps-inspired command bar and compact record header.
# Compact warehouse operations overview, without fabricated production KPIs.
st.markdown(
    '<div class="work-commandbar">'
    '<span class="work-commandbar-brand">PANEL OPERACYJNY</span>'
    '<span>Harmonogram</span><span class="work-commandbar-arrow">›</span>'
    '<span>Produkcja</span><span class="work-commandbar-arrow">›</span>'
    '<span>Premie</span><span class="work-commandbar-arrow">›</span>'
    '<span>Analizy i archiwum</span>'
    '</div>',
    unsafe_allow_html=True,
)
st.markdown(
    f'<div class="work-record-header"><div>'
    f'<div class="work-record-kicker">PODSUMOWANIE OKRESU · WERSJA TESTOWA</div>'
    f'<h2>{period_key}</h2>'
    f'<p>Najpierw zaplanuj harmonogram, następnie rozlicz produkcję i premie.</p>'
    f'</div><span class="work-record-state">● Panel roboczy</span></div>',
    unsafe_allow_html=True,
)
_step_plan = _schedule_matches_period
_step_production = uploaded_month_file is not None
_step_weights = uploaded_weights_file is not None
st.markdown('<div class="erp-dashboard-heading">GOTOWOŚĆ DO ROZLICZENIA</div>', unsafe_allow_html=True)
_overview_cols = st.columns(4)
_overview_cols[0].metric("01 · Harmonogram", "Gotowy" if _step_plan else "Brak")
_overview_cols[1].metric("02 · Raport produkcji", "Wgrany" if _step_production else "Brak")
_overview_cols[2].metric("03 · Katalog wag", "Wgrany" if _step_weights else "Brak")
_overview_cols[3].metric("Etapy przygotowane", f"{sum((_step_plan, _step_production, _step_weights))} / 3")
st.markdown('<div class="erp-dashboard-heading">CENTRUM PRACY</div>', unsafe_allow_html=True)
_work_left, _work_right = st.columns([1.5, 1])
with _work_left:
  with st.container(border=True):
    st.markdown("**Planowanie i harmonogram**")
    st.caption("Harmonogram można przygotować przed rozpoczęciem miesiąca.")
    if _step_plan:
      st.success("Harmonogram przypisany do wybranego okresu.")
    else:
      st.warning("Przygotuj harmonogram dla tego miesiąca.")
    st.markdown("**Rozliczenie produkcji**")
    if not _step_production:
      st.info("Oczekiwanie na raport produkcji.")
    elif not _step_weights:
      st.warning("Raport wgrany — uzupełnij katalog wag.")
    else:
      st.success("Pliki wgrane — sprawdź poprawność danych w kalkulatorze.")
with _work_right:
  with st.container(border=True):
    st.markdown("**Kolejne czynności**")
    st.checkbox("Harmonogram dla okresu", value=_step_plan, disabled=True, key="overview_schedule")
    st.checkbox("Raport produkcji", value=_step_production, disabled=True, key="overview_production")
    st.checkbox("Katalog wag", value=_step_weights, disabled=True, key="overview_weights")
    st.caption("Wgranie plików nie oznacza jeszcze zatwierdzenia obliczeń.")
st.markdown('<div class="erp-module-note">Przejdź do modułu poniżej, aby wykonać szczegółowe czynności. Dane testowe pozostają w bieżącej sesji.</div>', unsafe_allow_html=True)

# ==========================================
# ZAKŁADKI
# ==========================================
tab_gen, tab_calc, tab_dash, tab_history, tab_comp, tab_settings = st.tabs([
    "1. Planowanie i Obecności",
    "2. Rozliczenie i Paski",
    "3. Analizy",
    "4. Archiwum",
    "5. Porównania",
    "⚙️ Ustawienia",
])

# ==========================================
# ZAKŁADKA 1: HARMONOGRAM I SKANER
# ==========================================
with tab_gen:
  st.markdown("#### Harmonogram i rejestracja obecności")
  st.caption("PLANOWANIE MIESIĄCA / Harmonogram · Obecności · Nieobecności")

  if not _schedule_matches_period:
    st.info("Dla wybranego miesiąca nie ma jeszcze aktywnego harmonogramu. Możesz wygenerować nowy lub wgrać wcześniej zapisany.")
  col_action1, col_action2, _ = st.columns([1.5, 1.5, 2])
  with col_action1:
    _confirm_replace = st.checkbox(
        "Potwierdzam zastąpienie obecnego harmonogramu",
        key="confirm_schedule_replace",
    ) if _schedule_matches_period else True
    if st.button("📅 Wygeneruj harmonogram", disabled=not _confirm_replace):
      st.session_state.current_schedule_df = generate_schedule(
          gen_year, gen_month_idx
      )
      st.session_state.schedule_period_key = period_key
      st.success("Wygenerowano harmonogram!")
      st.rerun()

  with col_action2:
    uploaded_schedule_excel = st.file_uploader(
        "Wgraj gotowy plik z Harmonogramem:",
        type=["xlsx", "xls"],
        key="direct_schedule_uploader",
    )
    if uploaded_schedule_excel is not None:
      try:
        loaded_df = load_excel_cached(
            uploaded_schedule_excel.getvalue(), uploaded_schedule_excel.name
        )
        st.session_state.current_schedule_df = loaded_df
        st.session_state.schedule_period_key = period_key
        st.success("Wczytano harmonogram z pliku!")
      except Exception as e:
        st.error(f"Błąd odczytu pliku: {e}")

  st.markdown("---")

  with st.expander("📥 1. Import Nieobecności z pliku Excel"):
    uploaded_absence_file = st.file_uploader(
        "Wgraj plik Excel z nieobecnościami",
        type=["xlsx", "xls"],
        key="absence_file_uploader",
    )
    if uploaded_absence_file is not None:
      try:
        raw_abs_df = load_excel_cached(
            uploaded_absence_file.getvalue(), uploaded_absence_file.name
        )
        if st.button("Zaimportuj nieobecności"):
          imported_records = []
          abs_map = {
              str(row["Oznaczenie"]).strip().upper(): str(
                  row["Rodzaj nieobecności"]
              ).strip()
              for _, row in st.session_state.absence_codes_df.iterrows()
          }

          for r in range(2, len(raw_abs_df)):
            emp_name = raw_abs_df.iloc[r, 0]
            if (
                pd.isna(emp_name)
                or str(emp_name).strip() == ""
                or str(emp_name).strip().lower() == "pracownik"
            ):
              continue
            emp_name_clean = str(emp_name).strip()

            for c in range(1, raw_abs_df.shape[1]):
              cell_val = raw_abs_df.iloc[r, c]
              if pd.notna(cell_val):
                code = str(cell_val).strip().upper()
                if code in abs_map and code != "BRAK":
                  day_val = None
                  for test_r in [1, 2]:
                    header_val = raw_abs_df.iloc[test_r, c]
                    try:
                      if (
                          pd.notna(header_val)
                          and int(float(header_val)) in range(1, 32)
                      ):
                        day_val = int(float(header_val))
                        break
                    except Exception:
                      pass
                  if day_val is None:
                    day_val = c

                  imported_records.append({
                      "Pracownik": emp_name_clean,
                      "Dzień": day_val,
                      "Oznaczenie": code,
                      "Opis": abs_map[code],
                  })

          st.session_state.imported_absences_df = pd.DataFrame(
              imported_records
          )
          st.success(f"Zaimportowano {len(imported_records)} wpisów!")
      except Exception as e:
        st.error(f"Błąd parsowania pliku nieobecności: {e}")

    if not st.session_state.imported_absences_df.empty:
      st.dataframe(
          st.session_state.imported_absences_df, use_container_width=True
      )

  with st.expander(
      "📸 2. Skanowanie List Obecności ze Zdjęć (AI Vision Gemini)"
  ):
    api_key_in = st.text_input(
        "Klucz API Google Gemini:",
        value=st.session_state.gemini_api_key,
        type="password",
    )
    st.session_state.gemini_api_key = api_key_in

    uploaded_photos = st.file_uploader(
        "Wgrywaj zdjęcia list obecności:",
        type=["jpg", "jpeg", "png"],
        accept_multiple_files=True,
    )

    if uploaded_photos and st.button(
        "🔍 Przeanalizuj zdjęcia i zaktualizuj godziny"
    ):
      if not api_key_in:
        st.error("Wprowadź klucz API Google Gemini.")
      else:
        df_temp = st.session_state.current_schedule_df.copy()
        if "FAKTYCZNIE WEJŚCIE" not in df_temp.columns:
          df_temp["FAKTYCZNIE WEJŚCIE"] = ""
        if "FAKTYCZNIE WYJŚCIE" not in df_temp.columns:
          df_temp["FAKTYCZNIE WYJŚCIE"] = ""

        total_extracted = 0
        for photo in uploaded_photos:
          with st.spinner(f"Analizowanie pliku {photo.name}..."):
            records = process_attendance_photo(photo, api_key_in)
            for rec in records:
              p_date = str(rec.get("data", "")).strip()
              p_name_norm = normalize_name(rec.get("osoba", ""))
              t_in = str(rec.get("wejscie", "")).strip()
              t_out = str(rec.get("wyjscie", "")).strip()
              try:
                ot_val = float(rec.get("nadgodziny", 0.0))
              except Exception:
                ot_val = 0.0

              for idx, row in df_temp.iterrows():
                row_name_norm = normalize_name(row["OSOBA"])
                if row["DATA"] == p_date and row_name_norm == p_name_norm:
                  df_temp.at[idx, "FAKTYCZNIE WEJŚCIE"] = t_in
                  df_temp.at[idx, "FAKTYCZNIE WYJŚCIE"] = t_out
                  df_temp.at[idx, "NADGODZINY (godz.)"] = ot_val
                  total_extracted += 1

        st.session_state.current_schedule_df = df_temp
        st.success(f"Dopasowano i zaktualizowano {total_extracted} wpisów!")
        st.rerun()

  st.markdown("---")
  col_b1, col_b2, _ = st.columns([1.5, 1.5, 2])
  with col_b1:
    if st.button("⏱️ Uzupełnij planowane godziny", use_container_width=True):
      df_temp = st.session_state.current_schedule_df.copy()

      if (
          not st.session_state.imported_absences_df.empty
          and "Pracownik" in st.session_state.imported_absences_df.columns
      ):
        abs_lookup = {}
        for _, abs_row in st.session_state.imported_absences_df.iterrows():
          emp_k = normalize_name(abs_row["Pracownik"])
          try:
            day_k = int(abs_row["Dzień"])
          except Exception:
            continue
          abs_lookup[(emp_k, day_k)] = abs_row["Opis"]

        def apply_absences(row):
          try:
            day_num = int(str(row["DATA"]).split(".")[0])
          except Exception:
            day_num = None
          emp_k = normalize_name(row["OSOBA"])
          if (emp_k, day_num) in abs_lookup:
            return abs_lookup[(emp_k, day_num)]
          return row.get("NIEOBECNOŚĆ", "Brak")

        df_temp["NIEOBECNOŚĆ"] = df_temp.apply(apply_absences, axis=1)

      def fill_hours(row):
        absence = str(row.get("NIEOBECNOŚĆ", "Brak")).strip()
        status = str(row.get("DZIEŃ PRACUJĄCY/WOLNY", "")).strip()
        shift_time = str(row.get("CZAS ZMIANY", "")).strip()

        if absence not in ["Brak", "", "None", "nan"]:
          return "NIEOBECNY", "NIEOBECNOŚĆ"
        if status in ["Wolny", "Święto"] or shift_time.lower() == "wolne":
          return "Wolne", "Wolne"
        if "-" in shift_time:
          parts = shift_time.split("-")
          return parts[0].strip(), parts[1].strip()
        return "", ""

      hours_res = df_temp.apply(fill_hours, axis=1)
      df_temp["GODZINA ROZPOCZĘCIA"] = [h[0] for h in hours_res]
      df_temp["GODZINA ZAKOŃCZENIA"] = [h[1] for h in hours_res]

      st.session_state.current_schedule_df = df_temp
      st.success("Naniesiono planowane godziny!")
      st.rerun()

  with col_b2:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
      st.session_state.current_schedule_df.to_excel(
          writer, index=False, sheet_name="Harmonogram"
      )
    buffer.seek(0)
    st.download_button(
        label="📥 Pobierz Harmonogram (Excel)",
        data=buffer,
        file_name=f"Harmonogram_{period_key.replace(' ', '_')}.xlsx",
        mime=(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ),
        use_container_width=True,
    )

  df_curr = st.session_state.current_schedule_df.copy()
  if "FAKTYCZNIE WEJŚCIE" not in df_curr.columns:
    df_curr["FAKTYCZNIE WEJŚCIE"] = ""
  if "FAKTYCZNIE WYJŚCIE" not in df_curr.columns:
    df_curr["FAKTYCZNIE WYJŚCIE"] = ""

  st.markdown("---")
  st.subheader("⚠️ Weryfikacja Obecności i Brakujących Podpisów")

  missing_signatures = df_curr[
      (df_curr["DZIEŃ PRACUJĄCY/WOLNY"] == "Pracujący")
      & (df_curr["NIEOBECNOŚĆ"].isin(["Brak", "", "None"]))
      & (
          (df_curr["FAKTYCZNIE WEJŚCIE"] == "")
          | (df_curr["FAKTYCZNIE WEJŚCIE"].isna())
      )
  ]

  if not missing_signatures.empty:
    st.markdown(
        f'<div class="alert-box"><strong>Wykryto'
        f' {len(missing_signatures)} brakujących podpisów na listach!</strong></div>',
        unsafe_allow_html=True,
    )
    st.dataframe(
        missing_signatures[[
            "DATA",
            "DZIEŃ TYGODNIA",
            "OSOBA",
            "STANOWISKO",
            "CZAS ZMIANY",
            "NIEOBECNOŚĆ",
        ]],
        use_container_width=True,
    )
  else:
    st.markdown(
        '<div class="success-box"><strong>Wszystko w porządku!</strong>'
        " Wszystkie dni robocze mają pokrycie w podpisach.</div>",
        unsafe_allow_html=True,
    )

  st.markdown("---")
  st.subheader(f"📋 Tabela Harmonogramu ({period_key})")

  dynamic_absence_options = (
      st.session_state.absence_codes_df["Rodzaj nieobecności"]
      .dropna()
      .unique()
      .tolist()
  )
  if "Brak" not in dynamic_absence_options:
    dynamic_absence_options = ["Brak"] + dynamic_absence_options

  edited_df = st.data_editor(
      df_curr,
      column_config={
          "NIEOBECNOŚĆ": st.column_config.SelectboxColumn(
              "NIEOBECNOŚĆ",
              options=dynamic_absence_options,
              required=True,
          ),
          "FAKTYCZNIE WEJŚCIE": st.column_config.TextColumn(
              "FAKTYCZNIE WEJŚCIE"
          ),
          "FAKTYCZNIE WYJŚCIE": st.column_config.TextColumn(
              "FAKTYCZNIE WYJŚCIE"
          ),
          "NADGODZINY (godz.)": st.column_config.NumberColumn(
              "NADGODZINY (godz.)", min_value=0.0, max_value=24.0, step=0.5
          ),
      },
      use_container_width=True,
      num_rows="fixed",
      key="main_schedule_table_editor",
  )

  if isinstance(edited_df, pd.DataFrame):
    st.session_state.current_schedule_df = edited_df

# ==========================================
# ZAKŁADKA 2: KALKULATOR PREMII
# ==========================================
def _render_calculator_tab():
  st.header("🧮 Rozliczenie Premiowe i Wynagrodzeń Dodatkowych")

  if st.session_state.current_schedule_df.empty or st.session_state.schedule_period_key != period_key:
    st.warning("Najpierw przygotuj harmonogram dla wybranego miesiąca w pierwszej zakładce.")
  else:
    base_salary = st.session_state.base_bonus_salary
    step_bonus_pct = 0.04

    w_pcs_frac = st.session_state.w_pcs / 100.0
    w_lines_frac = st.session_state.w_lines / 100.0
    w_weight_frac = st.session_state.w_weight / 100.0

    df_sched = st.session_state.current_schedule_df
    cur_pcs, cur_lines, cur_weight, cur_pallets = 0.0, 0.0, 0.0, 0.0
    prod_df = pd.DataFrame()
    if uploaded_month_file is None:
      st.info("Aby rozpocząć rozliczenie, wgraj raport produkcji w panelu bocznym. Harmonogram i ustawienia są dostępne bez raportu.")
      return
    if uploaded_month_file is not None:
      try:
        prod_df = cached_read_production_v2(uploaded_month_file.getvalue())
        if uploaded_weights_file is None:
          st.warning("Wgraj aktualną bazę wag, aby obliczyć premię z raportu produkcji.")
          return
        weights_df = cached_read_weights(uploaded_weights_file.getvalue())
        if "approved_weights" not in st.session_state:
          st.session_state.approved_weights = {}
        import pandas as _pd
        from production_import import normalize as _normalize
        _approved = st.session_state.approved_weights
        _catalog = weights_df.copy()
        _catalog_keys = set(zip(_catalog["Producent"].map(_normalize), _catalog["Artykuł"].map(_normalize)))
        _new_rows = [{"Producent": key[0], "Artykuł": key[1], "Waga": value}
                     for key, value in _approved.items() if key not in _catalog_keys]
        if _new_rows:
          _catalog = _pd.concat([_catalog, _pd.DataFrame(_new_rows)], ignore_index=True)
        kpis = prepare_production(prod_df, _catalog, st.session_state.excluded_client_categories)
        st.subheader("Kontrola danych produkcyjnych")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Pozycje", f"{kpis['positions']:,}".replace(",", " "))
        k2.metric("Sztuki", f"{kpis['pieces']:,.0f}".replace(",", " ") if kpis["pieces"] is not None else "Błąd danych")
        k3.metric("Łączna waga (kg)", f"{kpis['weight_kg']:,.2f}".replace(",", " ") if kpis["weight_kg"] is not None else "Niekompletna")
        k4.metric("Dopasowane wagi", f"{kpis['matched_positions']}/{kpis['positions']}")
        st.caption(f"Wykluczono {kpis['excluded_positions']} pozycji według kategorii klienta.")
        if kpis["missing_positions"]:
          st.error(f"Brakuje poprawnych wag lub ilości dla {kpis['missing_positions']} pozycji. "
                   "Obliczenia premii zostały wstrzymane, aby nie zaniżyć wyniku.")
          st.dataframe(kpis["missing_items"], use_container_width=True, hide_index=True)
          st.markdown("#### Wyszukiwanie i zatwierdzanie wag")
          st.caption("Wyszukiwanie otwiera zewnętrzną wyszukiwarkę. Przekazywane są tylko producent i numer artykułu. Nie zatwierdzamy automatycznie wag znalezionych w sieci.")
          _missing_unique = kpis["missing_items"].drop_duplicates(["Producent", "Artykuł"])
          _options = [(str(r["Producent"]), str(r["Artykuł"])) for _, r in _missing_unique.iterrows()]
          _selected = st.selectbox("Artykuł do uzupełnienia", _options,
                                   format_func=lambda x: f"{x[0]} / {x[1]}")
          if _selected:
            st.link_button("🔎 Wyszukaj wagę produktu w internecie",
                           product_search_url(*_selected))
            with st.form("approve_weight_form"):
              _entered_weight = st.text_input("Zweryfikowana waga jednej sztuki (kg)")
              _source_url = st.text_input("Źródło wagi (opcjonalnie — adres URL lub opis)")
              if st.form_submit_button("Zatwierdź wagę"):
                try:

                  _key = tuple(_normalize(v) for v in _selected)
                  st.session_state.approved_weights[_key] = validate_weight(_entered_weight)
                  st.success("Waga zatwierdzona w bieżącej sesji.")
                  st.rerun()
                except ValueError as exc:
                  st.error(str(exc))
          if st.session_state.approved_weights:
            _approved_export = _pd.DataFrame([
                {"Producent": key[0], "Artykuł": key[1], "Waga": value}
                for key, value in st.session_state.approved_weights.items()])
            st.download_button("Pobierz zatwierdzone wagi (CSV)",
                               _approved_export.to_csv(index=False).encode("utf-8-sig"),
                               file_name="zatwierdzone_wagi.csv", mime="text/csv")
          st.download_button("Pobierz listę brakujących artykułów (CSV)",
                             data=kpis["missing_items"].to_csv(index=False).encode("utf-8-sig"),
                             file_name="brakujace_wagi.csv", mime="text/csv")
          return
        cur_pcs, cur_lines, cur_weight = kpis["pieces"], float(kpis["positions"]), kpis["weight_kg"]
        st.success(f"Łączna waga: {cur_weight:,.2f} kg".replace(",", " "))
      except (ValueError, KeyError, OSError, ImportError) as exc:
        st.error(f"Nie można przygotować danych produkcyjnych: {exc}")
        return

    dev_pcs = (
        (cur_pcs - st.session_state.avg_pcs_12m) / st.session_state.avg_pcs_12m
        if st.session_state.avg_pcs_12m > 0
        else 0.0
    )
    dev_lines = (
        (cur_lines - st.session_state.avg_lines_12m)
        / st.session_state.avg_lines_12m
        if st.session_state.avg_lines_12m > 0
        else 0.0
    )
    dev_weight = (
        (cur_weight - st.session_state.avg_weight_12m)
        / st.session_state.avg_weight_12m
        if st.session_state.avg_weight_12m > 0
        else 0.0
    )

    indicator = (
        dev_pcs * w_pcs_frac
        + dev_lines * w_lines_frac
        + dev_weight * w_weight_frac
    )
    bonus_rate = indicator * (step_bonus_pct / 0.10) if indicator > 0 else 0.0
    max_bonus_per_emp = base_salary * bonus_rate

    st.info(
        f"💡 Podstawa premii: **{base_salary:,.2f} zł netto** | Mnożnik"
        f" Kierownika: **{st.session_state.kierownik_bonus_multiplier:.2f}x**"
        " | Pula na wózki:"
        f" **{st.session_state.forklift_pool:,.2f} zł netto** | Stawka za"
        f" paletę: **{st.session_state.rate_pallet:,.2f} zł netto**"
    )

    st.markdown("---")
    st.subheader("📌 1. Miesięczne Wyniki Produkcyjne i Wskaźnik Wydajności")

    comparison_data = [
        {
            "Parametr produkcyjny": "Pozycje",
            "Wartość w miesiącu": cur_lines,
            "Średnia roczna (baza)": st.session_state.avg_lines_12m,
            "Różnica ilościowa": cur_lines - st.session_state.avg_lines_12m,
            "Odchylenie procentowe (%)": dev_lines * 100,
            "Waga wskaźnika (%)": st.session_state.w_lines,
        },
        {
            "Parametr produkcyjny": "Sztuki",
            "Wartość w miesiącu": cur_pcs,
            "Średnia roczna (baza)": st.session_state.avg_pcs_12m,
            "Różnica ilościowa": cur_pcs - st.session_state.avg_pcs_12m,
            "Odchylenie procentowe (%)": dev_pcs * 100,
            "Waga wskaźnika (%)": st.session_state.w_pcs,
        },
        {
            "Parametr produkcyjny": "Waga towaru (kg)",
            "Wartość w miesiącu": cur_weight,
            "Średnia roczna (baza)": st.session_state.avg_weight_12m,
            "Różnica ilościowa": cur_weight - st.session_state.avg_weight_12m,
            "Odchylenie procentowe (%)": dev_weight * 100,
            "Waga wskaźnika (%)": st.session_state.w_weight,
        },
    ]

    st.dataframe(
        pd.DataFrame(comparison_data),
        column_config={
            "Wartość w miesiącu": st.column_config.NumberColumn(
                format="%.2f"
            ),
            "Średnia roczna (baza)": st.column_config.NumberColumn(
                format="%.2f"
            ),
            "Różnica ilościowa": st.column_config.NumberColumn(format="%+.2f"),
            "Odchylenie procentowe (%)": st.column_config.NumberColumn(
                format="%+.2f %%"
            ),
            "Waga wskaźnika (%)": st.column_config.NumberColumn(
                format="%.2f %%"
            ),
        },
        use_container_width=True,
        hide_index=True,
    )

    col_m1, col_m2, col_m3 = st.columns(3)
    with col_m1:
      st.metric(
          label="Zbiorczy Wskaźnik Wydajności",
          value=f"{indicator * 100:+.2f}%".replace(".", ","),
      )
    with col_m2:
      st.metric(
          label="Należna Stawka Premii (%)",
          value=f"{bonus_rate * 100:.2f}%".replace(".", ","),
      )
    with col_m3:
      st.metric(
          label="Maks. Premia Bazowa (Magazynier)",
          value=f"{max_bonus_per_emp:,.2f} zł".replace(".", ","),
      )

    # DZIENNA ANALIZA
    st.markdown("---")
    st.subheader(
        "📅 2. Dzienna Analiza Przyjęć i Rozkład Pracy (% Miesiąca)"
    )

    # Calculate daily production from the same eligible rows and unit weights as monthly totals.
    from production_import import DATE as _DATE, BRAND as _BRAND, ARTICLE as _ARTICLE, QTY as _QTY
    daily_source = exclude_categories(prod_df, st.session_state.excluded_client_categories)[0].copy()
    daily_source["_brand"] = daily_source[_BRAND].map(_normalize)
    daily_source["_article"] = daily_source[_ARTICLE].map(_normalize)
    daily_source["_qty"] = pd.to_numeric(daily_source[_QTY].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    _daily_weights = _catalog.copy()
    _daily_weights["_brand"] = _daily_weights["Producent"].map(_normalize)
    _daily_weights["_article"] = _daily_weights["Artykuł"].map(_normalize)
    _daily_weights["_weight"] = pd.to_numeric(_daily_weights["Waga"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    daily_source = daily_source.merge(_daily_weights[["_brand", "_article", "_weight"]], on=["_brand", "_article"], how="left", validate="many_to_one")
    if _DATE not in daily_source.columns:
      st.error("W zaimportowanych danych nie ma kolumny daty przejścia. Wgraj raport ponownie; jeśli problem pozostanie, sprawdź nagłówek: " + _DATE)
      return
    daily_source["_date"] = pd.to_datetime(daily_source[_DATE], dayfirst=True, errors="coerce")
    _invalid_dates = int(daily_source["_date"].isna().sum())
    _outside = int((daily_source["_date"].notna() & ((daily_source["_date"].dt.year != gen_year) | (daily_source["_date"].dt.month != gen_month_idx))).sum())
    if _invalid_dates or _outside:
      st.error(f"Nie można obliczyć analizy dziennej: niepoprawna data w {_invalid_dates} pozycjach; poza wybranym miesiącem: {_outside}.")
      return
    daily_map = {day: {"pcs": 0.0, "lines": 0.0, "weight": 0.0} for day in range(1, calendar.monthrange(gen_year, gen_month_idx)[1] + 1)}
    for _day, _group in daily_source.groupby(daily_source["_date"].dt.day):
      daily_map[int(_day)] = {"pcs": float(_group["_qty"].sum()), "lines": float(len(_group)), "weight": float((_group["_qty"] * _group["_weight"]).sum())}
    if abs(sum(v["weight"] for v in daily_map.values()) - cur_weight) > 0.01:
      st.error("Niezgodność sumy wag dziennych i miesięcznych. Sprawdź dane źródłowe.")
      return
    days_in_month = calendar.monthrange(gen_year, gen_month_idx)[1]

    daily_rows = []
    daily_chart_data = []
    daily_work_pct_map = {}

    for day in range(1, days_in_month + 1):
      date_obj = datetime(gen_year, gen_month_idx, day)
      date_str = date_obj.strftime("%d.%m.%Y")
      day_name = PL_DAYS[date_obj.weekday()]

      pcs_d = daily_map[day]["pcs"]
      lines_d = daily_map[day]["lines"]
      weight_d = daily_map[day]["weight"]

      pct_pcs_d = (pcs_d / cur_pcs * 100.0) if cur_pcs > 0 else 0.0
      pct_lines_d = (lines_d / cur_lines * 100.0) if cur_lines > 0 else 0.0
      pct_weight_d = (weight_d / cur_weight * 100.0) if cur_weight > 0 else 0.0

      pct_work_d = (
          (pct_pcs_d * w_pcs_frac)
          + (pct_lines_d * w_lines_frac)
          + (pct_weight_d * w_weight_frac)
      )

      daily_work_pct_map[day] = pct_work_d

      daily_rows.append({
          "Data": date_str,
          "Dzień tygodnia": day_name,
          "Sztuki": pcs_d,
          "Pozycje": lines_d,
          "Waga (kg)": weight_d,
          "% Sztuk": pct_pcs_d,
          "% Pozycji": pct_lines_d,
          "% Wagi": pct_weight_d,
          "% Pracy w miesiącu": pct_work_d,
      })

      daily_chart_data.append({
          "Data": f"{day:02d}.{gen_month_idx:02d}",
          "% Pracy": round(pct_work_d, 2),
      })

    st.dataframe(
        pd.DataFrame(daily_rows),
        column_config={
            "Sztuki": st.column_config.NumberColumn(format="%.0f"),
            "Pozycje": st.column_config.NumberColumn(format="%.0f"),
            "Waga (kg)": st.column_config.NumberColumn(format="%.2f"),
            "% Sztuk": st.column_config.NumberColumn(format="%.2f %%"),
            "% Pozycji": st.column_config.NumberColumn(format="%.2f %%"),
            "% Wagi": st.column_config.NumberColumn(format="%.2f %%"),
            "% Pracy w miesiącu": st.column_config.NumberColumn(
                format="%.2f %%"
            ),
        },
        use_container_width=True,
        hide_index=True,
    )

    if cur_pcs > 0 or cur_lines > 0 or cur_weight > 0:
      fig_daily = px.bar(
          pd.DataFrame(daily_chart_data),
          x="Data",
          y="% Pracy",
          title=(
              "Dzienny rozkład nakładu pracy (% udziału w skali całego"
              " miesiąca)"
          ),
          text_auto=".2f",
          labels={"% Pracy": "% Udział w pracy"},
      )
      fig_daily.update_traces(marker_color="#1e3a8a")
      st.plotly_chart(fig_daily, use_container_width=True)

    # EWIDENCJA WÓZKA
    st.markdown("---")
    with st.container(border=True):
      st.subheader(
          "🚜 3. Ewidencja Czasu Pracy na Wózku Widłowym (z Książki Obsługi)"
      )
      st.markdown(
          "Wpisz poniżej liczbę godzin obsługi wózka dla każdego z pracowników"
          " w tym miesiącu. System automatycznie wyliczy 100% czasu obsługi"
          f" w zespole i podzieli pulę **{st.session_state.forklift_pool:,.2f}"
          " zł netto**."
      )

      emp_list_df = st.session_state.employees_df[
          ["OSOBA", "UPRAWNIENIA UDT"]
      ].copy()
      merged_forklift = pd.merge(
          emp_list_df, st.session_state.forklift_hours_df, on="OSOBA", how="left"
      ).fillna({"CZAS WÓZKA (godz.)": 0.0})

      forklift_editor_df = st.data_editor(
          merged_forklift,
          column_config={
              "OSOBA": st.column_config.TextColumn("Pracownik", disabled=True),
              "UPRAWNIENIA UDT": st.column_config.CheckboxColumn(
                  "Uprawnienia UDT", disabled=True
              ),
              "CZAS WÓZKA (godz.)": st.column_config.NumberColumn(
                  "Liczba godzin na wózku (h)",
                  min_value=0.0,
                  max_value=300.0,
                  step=0.5,
              ),
          },
          use_container_width=True,
          hide_index=True,
          key="forklift_hours_editor",
      )

      if isinstance(forklift_editor_df, pd.DataFrame):
        st.session_state.forklift_hours_df = forklift_editor_df[
            ["OSOBA", "CZAS WÓZKA (godz.)"]
        ]

      total_forklift_hours = pd.to_numeric(
          st.session_state.forklift_hours_df["CZAS WÓZKA (godz.)"],
          errors="coerce",
      ).sum()

      col_fk1, col_fk2 = st.columns(2)
      with col_fk1:
        st.metric(
            label="Łączny Czas Obsługi Wózka w Zespole (100%)",
            value=f"{total_forklift_hours:.1f} godz.",
        )
      with col_fk2:
        st.metric(
            label="Zbiorcza Pula za Wózki do Podziału",
            value=f"{st.session_state.forklift_pool:,.2f} zł netto",
        )

    # PODZIAŁ PALET
    st.markdown("---")
    with st.container(border=True):
      st.subheader("📦 4. Podział Premii za Rozładunki / Załadunki Palet")

      unique_emps = (
          st.session_state.employees_df["OSOBA"].dropna().unique().tolist()
      )

      col_pal1, col_pal2, col_pal3 = st.columns(3)
      with col_pal1:
        manual_pallets = st.number_input(
            "Liczba palet w miesiącu:",
            value=float(cur_pallets),
            min_value=0.0,
            step=1.0,
        )

      total_pallet_pool = manual_pallets * st.session_state.rate_pallet

      with col_pal2:
        st.metric(
            label="Łączna Pula za Palety (netto)",
            value=f"{total_pallet_pool:,.2f} zł",
        )
      with col_pal3:
        st.metric(
            label="Stawka za 1 szt. palety",
            value=f"{st.session_state.rate_pallet:,.2f} zł",
        )

      selected_pallet_emps = st.multiselect(
          "Zaznacz pracowników uwzględnionych w podziale premii za palety:",
          options=unique_emps,
          default=unique_emps,
          key="pallet_emp_multiselect",
      )

      num_selected_pallet_emps = len(selected_pallet_emps)
      pallet_pay_per_selected_emp = (
          (total_pallet_pool / num_selected_pallet_emps)
          if num_selected_pallet_emps > 0
          else 0.0
      )

      if num_selected_pallet_emps > 0:
        st.success(
            f"Pula **{total_pallet_pool:,.2f} zł** dzielona jest na"
            f" **{num_selected_pallet_emps}** wybranych pracowników ("
            f"**{pallet_pay_per_selected_emp:,.2f} zł netto** na osobę)."
        )
      else:
        st.warning(
            "Nie zaznaczono żadnego pracownika do podziału premii za palety."
        )

    # PREMIA SPECJALNA / UZNANIOWA
    st.markdown("---")
    with st.container(border=True):
      st.subheader("⭐ 5. Premie Specjalne i Uznaniowe")
      st.markdown(
          "Wprowadź poniżej ewentualne dodatkowe premie specjalne przyznane"
          " pracownikom w danym miesiącu. Możesz dodawać dowolną liczbę"
          " wierszy."
      )

      edited_spec_bonuses = st.data_editor(
          st.session_state.special_bonuses_df,
          column_config={
              "Pracownik": st.column_config.SelectboxColumn(
                  "Pracownik", options=unique_emps, required=True
              ),
              "Kwota netto premii": st.column_config.NumberColumn(
                  "Kwota netto (zł)",
                  min_value=0.0,
                  step=50.0,
                  format="%.2f zł",
              ),
              "Powód przyznania premii": st.column_config.TextColumn(
                  "Za co przyznana / Powód"
              ),
              "Kto przyznał": st.column_config.TextColumn("Kto przyznał"),
          },
          num_rows="dynamic",
          use_container_width=True,
          hide_index=True,
          key="special_bonuses_editor",
      )

      if isinstance(edited_spec_bonuses, pd.DataFrame):
        st.session_state.special_bonuses_df = edited_spec_bonuses

    # PRZEŁĄCZNIK WARIANTU ROZLICZENIA FREKWENCYJNEGO
    st.markdown("---")
    st.subheader("👥 6. Szczegółowe Rozliczenie Pracowników")

    with st.container(border=True):
      selected_variant = st.radio(
          "⚙️ Wybierz wariant naliczania premii frekwencyjnej:",
          options=[
              "Wersja domyślna (bez potrąceń za nieobecności — 100% premii)",
              "Wersja alternatywna (z potrąceniami za nieobecności)",
          ],
          index=0,
          horizontal=True,
          help=(
              "Wersja domyślna wypłaca pełną kwotę premii wszystkim"
              " pracownikom. Wersja alternatywna obniża wartość premii"
              " o sumę procentowych udziałów produkcji w dniach nieobecności."
          ),
      )

    include_absence_deduction = (
        "z potrąceniami" in str(selected_variant).lower()
    )

    # Production shares must be complete before absence-based deductions.
    if include_absence_deduction:
      production_share = sum(daily_work_pct_map.values())
      if not 99.99 <= production_share <= 100.01:
        st.error(
            "Nie można naliczyć potrąceń za nieobecności: brak kompletnych "
            "danych dziennej produkcji. Wczytaj dane z datami i wartościami "
            "dla wybranego miesiąca."
        )
        return

    # OBLICZENIA I PODSUMOWANIE ZESPOŁU
    summary_df, emp_details_map = calculate_payroll(
        df_sched=df_sched,
        employees_df=st.session_state.employees_df,
        max_bonus_per_emp=max_bonus_per_emp,
        forklift_hours_df=st.session_state.forklift_hours_df,
        total_forklift_hours=total_forklift_hours,
        pallet_pay_per_selected_emp=pallet_pay_per_selected_emp,
        selected_pallet_emps=selected_pallet_emps,
        daily_work_pct_map=daily_work_pct_map,
        special_bonuses_df=st.session_state.special_bonuses_df,
        include_absence_deduction=include_absence_deduction,
    )

    col_tot1, col_tot2, col_tot3 = st.columns(3)
    with col_tot1:
      st.metric(
          label="Łączna Kwota Wypłat i Dodatków",
          value=f"{summary_df['ŁĄCZNA PREMIA / DODATKI (zł)'].sum():,.2f} zł",
      )
    with col_tot2:
      st.metric(
          label="Suma Nadgodzin Zespołu",
          value=f"{summary_df['Nadgodziny (godz.)'].sum():,.1f} h",
      )
    with col_tot3:
      st.metric(
          label="Wykorzystanie Puli Wózków",
          value=f"{summary_df['Dodatek Wózek (zł)'].sum():,.2f} zł",
      )

    st.dataframe(
        summary_df,
        column_config={
            "% Potrącenia": st.column_config.NumberColumn(format="%.2f %%"),
            "% Udział wózek": st.column_config.NumberColumn(format="%.2f %%"),
            "Dodatek Wózek (zł)": st.column_config.NumberColumn(
                format="%.2f zł"
            ),
            "Dodatek Palety (zł)": st.column_config.NumberColumn(
                format="%.2f zł"
            ),
            "Nadgodziny (zł)": st.column_config.NumberColumn(format="%.2f zł"),
            "Premia (zł)": st.column_config.NumberColumn(format="%.2f zł"),
            "Premia Specjalna (zł)": st.column_config.NumberColumn(
                format="%.2f zł"
            ),
            "ŁĄCZNA PREMIA / DODATKI (zł)": st.column_config.NumberColumn(
                format="%.2f zł"
            ),
        },
        use_container_width=True,
        hide_index=True,
    )

    col_save1, col_save2 = st.columns(2)

    with col_save1:
      if st.button(
          "💾 Zapisz rozliczenie w archiwum sesji testowej",
          use_container_width=True,
      ):
        pending_archive = dict(st.session_state.history_v2)
        pending_archive[period_key] = {
            "summary": summary_df,
            "schedule": df_sched,
            "metrics": {
                "pcs": cur_pcs,
                "lines": cur_lines,
                "weight": cur_weight,
                "pallets": manual_pallets,
                "indicator": indicator,
                "bonus_rate": bonus_rate,
                "variant": selected_variant,
            },
        }
        if save_archive(pending_archive):
          st.session_state.history_v2 = pending_archive
          st.success(f"Zarchiwizowano rozliczenie za okres {period_key}!")

    with col_save2:
      hr_buffer = io.BytesIO()
      with pd.ExcelWriter(hr_buffer, engine="openpyxl") as writer:
        summary_df.to_excel(writer, index=False, sheet_name="Rozliczenie_HR")
      hr_buffer.seek(0)

      st.download_button(
          label="📊 Pobierz Rozliczenie dla HR (Excel)",
          data=hr_buffer,
          file_name=f"Rozliczenie_HR_{period_key.replace(' ', '_')}.xlsx",
          mime=(
              "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
          ),
          use_container_width=True,
      )

    # PASKI PREMIOWE DO WYDRUKU
    st.markdown("---")
    st.subheader("🧾 7. Imienne Paski Premiowe do Wydruku")

    st.caption("Wybierz pracownika, aby wyświetlić wyłącznie jego pasek premiowy.")
    col_print_sel, _ = st.columns([3, 1])
    with col_print_sel:
      selected_slip_emp = st.selectbox(
          "Pracownik",
          options=[""] + sorted(unique_emps),
          format_func=lambda name: "— Wybierz pracownika —" if not name else name,
          key="selected_bonus_slip_employee",
      )
    emps_to_render = [selected_slip_emp] if selected_slip_emp else []

    for e_name in emps_to_render:
      e_det = emp_details_map.get(e_name)
      if not e_det:
        continue

      deduction_html_info = (
          f'<p style="margin:3px 0; color:#dc2626;"><strong>Potrącenie za'
          f' nieobecności:</strong> -{e_det["deduction_pct"]:.2f}%</p>'
          if include_absence_deduction
          else '<p style="margin:3px 0; color:#0284c7;"><strong>Wariant'
          " premii:</strong> Bez potrąceń za nieobecności (100%)</p>"
      )

      st.markdown(
          f"""
            <div class="pay-slip">
                <div class="pay-slip-header">
                    <h3 style="margin:0; color:#1e3a8a;">PASEK ROZLICZENIA PREMIOWEGO — {period_key.upper()}</h3>
                    <p style="margin:5px 0 0 0; font-size:16px;"><strong>Pracownik:</strong> {e_name} | <strong>Stanowisko:</strong> {e_det['position']}</p>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 15px;">
                    <div>
                        <p style="margin:3px 0;"><strong>Dni planowane:</strong> {e_det['scheduled_days']}</p>
                        <p style="margin:3px 0;"><strong>Dni przepracowane:</strong> {e_det['days_worked']}</p>
                        <p style="margin:3px 0;"><strong>Dni nieobecności:</strong> {e_det['absent_days']}</p>
                    </div>
                    <div style="text-align: right;">
                        <p style="margin:3px 0;"><strong>Maks. premia bazowa:</strong> {e_det['base_emp_bonus']:,.2f} zł</p>
                        {deduction_html_info}
                        <p style="margin:3px 0; font-size:18px; color:#16a34a;"><strong>Należna premia frekwencyjna:</strong> {e_det['calculated_bonus']:,.2f} zł</p>
                    </div>
                </div>
            """,
          unsafe_allow_html=True,
      )

      st.markdown("**📅 Wykaz Dni Nieobecności:**")
      abs_df_view = e_det["absences_table"]

      if abs_df_view.empty:
        st.success("Brak nieobecności w tym miesiącu — 100% frekwencji!")
      else:
        st.dataframe(
            abs_df_view,
            column_config={
                "Udział pracy w miesiącu (%)": st.column_config.NumberColumn(
                    format="%.2f %%"
                )
            },
            use_container_width=True,
            hide_index=True,
        )

      spec_details_html = ""
      if e_det["spec_reasons_list"]:
        spec_details_html = (
            "<br><small style='color:#475569;'>Wykaz premii"
            " specjalnych:<br>• "
            + "<br>• ".join(e_det["spec_reasons_list"])
            + "</small>"
        )

      st.markdown(
          f"""
                <hr style="border:1px dashed #cbd5e1; margin:15px 0;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <p style="margin:2px 0;"><strong>Wynagrodzenie za nadgodziny:</strong> {e_det['total_ot']} godz. ({e_det['ot_pay']:,.2f} zł)</p>
                        <p style="margin:2px 0;"><strong>Dodatek za wózek widłowy:</strong> {e_det['forklift_pay']:,.2f} zł ({e_det['emp_forklift_hours']} h / {e_det['emp_forklift_pct']:.2f}%)</p>
                        <p style="margin:2px 0;"><strong>Dodatek za rozładunki/załadunki palet:</strong> {e_det['pallet_pay']:,.2f} zł</p>
                        <p style="margin:2px 0;"><strong>Premie specjalne i uznaniowe:</strong> {e_det['spec_bonus_val']:,.2f} zł {spec_details_html}</p>
                    </div>
                    <div style="background-color:#f1f5f9; padding:10px 15px; border-radius:8px; border:1px solid #cbd5e1;">
                        <span style="font-size:16px; font-weight:bold;">DO WYPŁATY 💡: </span>
                        <span style="font-size:22px; font-weight:bold; color:#1e3a8a;">{e_det['total_payout']:,.2f} zł netto</span>
                    </div>
                </div>
            </div>
            """,
          unsafe_allow_html=True,
      )

with tab_calc:
  _render_calculator_tab()

# ==========================================
# ZAKŁADKA 3: DASHBOARD
# ==========================================
with tab_dash:
  st.header("📊 Dashboard Analityczny")
  if period_key in st.session_state.history_v2:
    data_hist = st.session_state.history_v2[period_key]
    sum_df = data_hist["summary"]

    col_d1, col_d2 = st.columns(2)
    with col_d1:
      fig_payout = px.bar(
          sum_df,
          x="Pracownik",
          y="ŁĄCZNA PREMIA / DODATKI (zł)",
          title="Łączne wypłaty dodatkowe wg pracowników",
          color="Stanowisko",
          text_auto=".2f",
      )
      st.plotly_chart(fig_payout, use_container_width=True)

    with col_d2:
      fig_ot = px.pie(
          sum_df,
          names="Pracownik",
          values="Nadgodziny (godz.)",
          title="Udział nadgodzin w zespole",
      )
      st.plotly_chart(fig_ot, use_container_width=True)
  else:
    st.info(
        "Zapisz rozliczenie do archiwum w zakładce Kalkulator Premii, aby"
        " wyświetlić wykresy."
    )

# ==========================================
# ZAKŁADKA 4: ARCHIWUM
# ==========================================
with tab_history:
  st.header("📁 Archiwum Zapisanych Rozliczeń")
  if st.session_state.history_v2:
    selected_period = st.selectbox(
        "Wybierz okres z archiwum:", list(st.session_state.history_v2.keys())
    )
    if selected_period:
      st.subheader(f"Rozliczenie dla: {selected_period}")
      st.dataframe(
          st.session_state.history_v2[selected_period]["summary"],
          use_container_width=True,
      )
  else:
    st.info("Brak zapisanych okresów w archiwum.")

# ==========================================
# ZAKŁADKA 5: PORÓWNANIE
# ==========================================
with tab_comp:
  st.header("📈 Porównanie Okresów Historycznych")
  if len(st.session_state.history_v2) >= 2:
    periods = list(st.session_state.history_v2.keys())
    p1, p2 = st.columns(2)
    with p1:
      period_a = st.selectbox("Wybierz pierwszy okres:", periods, index=0)
    with p2:
      period_b = st.selectbox(
          "Wybierz drugi okres:", periods, index=min(1, len(periods) - 1)
      )

    if period_a and period_b:
      data_a = st.session_state.history_v2[period_a]
      data_b = st.session_state.history_v2[period_b]

      df_a = data_a["summary"]
      df_b = data_b["summary"]
      met_a = data_a.get("metrics", {})
      met_b = data_b.get("metrics", {})

      st.markdown("---")
      st.subheader("📊 1. Porównanie Wyników Produkcyjnych (Miesiąc do Miesiąca)")

      prod_comp_data = [
          {
              "Parametr": "Sztuki (pcs)",
              f"Okres: {period_a}": met_a.get("pcs", 0.0),
              f"Okres: {period_b}": met_b.get("pcs", 0.0),
              "Różnica": met_b.get("pcs", 0.0) - met_a.get("pcs", 0.0),
          },
          {
              "Parametr": "Pozycje (lines)",
              f"Okres: {period_a}": met_a.get("lines", 0.0),
              f"Okres: {period_b}": met_b.get("lines", 0.0),
              "Różnica": met_b.get("lines", 0.0) - met_a.get("lines", 0.0),
          },
          {
              "Parametr": "Waga (kg)",
              f"Okres: {period_a}": met_a.get("weight", 0.0),
              f"Okres: {period_b}": met_b.get("weight", 0.0),
              "Różnica": met_b.get("weight", 0.0) - met_a.get("weight", 0.0),
          },
          {
              "Parametr": "Liczba palet",
              f"Okres: {period_a}": met_a.get("pallets", 0.0),
              f"Okres: {period_b}": met_b.get("pallets", 0.0),
              "Różnica": met_b.get("pallets", 0.0) - met_a.get("pallets", 0.0),
          },
          {
              "Parametr": "Zbiorczy Wskaźnik Wydajności (%)",
              f"Okres: {period_a}": met_a.get("indicator", 0.0) * 100,
              f"Okres: {period_b}": met_b.get("indicator", 0.0) * 100,
              "Różnica": (
                  met_b.get("indicator", 0.0) - met_a.get("indicator", 0.0)
              )
              * 100,
          },
      ]
      st.dataframe(
          pd.DataFrame(prod_comp_data),
          column_config={
              "Różnica": st.column_config.NumberColumn(format="%+.2f"),
          },
          use_container_width=True,
          hide_index=True,
      )

      st.markdown("---")
      st.subheader("💰 2. Porównanie Składowych Premii i Bonusów (Zespół)")

      sum_cols_to_compare = [
          "Premia (zł)",
          "Premia Specjalna (zł)",
          "Dodatek Wózek (zł)",
          "Dodatek Palety (zł)",
          "Nadgodziny (zł)",
          "ŁĄCZNA PREMIA / DODATKI (zł)",
      ]

      totals_a = {
          col: df_a[col].sum() for col in sum_cols_to_compare if col in df_a.columns
      }
      totals_b = {
          col: df_b[col].sum() for col in sum_cols_to_compare if col in df_b.columns
      }

      bonus_comp_rows = []
      for col in sum_cols_to_compare:
        if col in totals_a and col in totals_b:
          val_a = totals_a[col]
          val_b = totals_b[col]
          bonus_comp_rows.append({
              "Składowa wynagrodzenia": col,
              f"Okres: {period_a}": val_a,
              f"Okres: {period_b}": val_b,
              "Różnica (zł)": val_b - val_a,
          })

      st.dataframe(
          pd.DataFrame(bonus_comp_rows),
          column_config={
              f"Okres: {period_a}": st.column_config.NumberColumn(
                  format="%.2f zł"
              ),
              f"Okres: {period_b}": st.column_config.NumberColumn(
                  format="%.2f zł"
              ),
              "Różnica (zł)": st.column_config.NumberColumn(
                  format="%+.2f zł"
              ),
          },
          use_container_width=True,
          hide_index=True,
      )

      st.markdown("---")
      st.subheader("👥 3. Porównanie Łącznych Wypłat per Pracownik")
      comp_df = pd.merge(
          df_a[["Pracownik", "ŁĄCZNA PREMIA / DODATKI (zł)"]],
          df_b[["Pracownik", "ŁĄCZNA PREMIA / DODATKI (zł)"]],
          on="Pracownik",
          suffixes=(f" ({period_a})", f" ({period_b})"),
      )
      st.dataframe(comp_df, use_container_width=True, hide_index=True)
  else:
    st.info("Wymagane są co najmniej 2 zapisane okresy w archiwum.")

# ==========================================
# ZAKŁADKA 6: USTAWIENIA
# ==========================================
with tab_settings:
  st.header("⚙️ Ustawienia Parametrów i Stałych Systemowych")

  col_set1, col_set2 = st.columns(2)

  with col_set1:
    with st.container(border=True):
      st.subheader("💰 Podstawa Premiowa i Dodatki")
      st.session_state.base_bonus_salary = st.number_input(
          "Podstawa premii (zł netto):",
          value=float(st.session_state.base_bonus_salary),
          step=100.0,
      )
      st.session_state.kierownik_bonus_multiplier = st.number_input(
          "Mnożnik premii dla Kierownika:",
          value=float(st.session_state.kierownik_bonus_multiplier),
          step=0.05,
          format="%.2f",
      )
      st.session_state.forklift_pool = st.number_input(
          "Zbiorcza pula dodatku za wózek (zł netto):",
          value=float(st.session_state.forklift_pool),
          step=50.0,
      )
      st.session_state.rate_pallet = st.number_input(
          "Stawka za 1 szt. palety (zł netto):",
          value=float(st.session_state.rate_pallet),
          step=0.5,
          format="%.2f",
      )

    with st.container(border=True):
      st.subheader("⏱️ Stawki za Nadgodziny (zł/h)")
      st.session_state.ot_kierownik = st.number_input(
          "Kierownik:", value=float(st.session_state.ot_kierownik), step=5.0
      )
      st.session_state.ot_brygadzista = st.number_input(
          "Brygadzista:", value=float(st.session_state.ot_brygadzista), step=5.0
      )
      st.session_state.ot_magazynier = st.number_input(
          "Magazynier:", value=float(st.session_state.ot_magazynier), step=5.0
      )

  with col_set2:
    with st.container(border=True):
      st.subheader("📊 Średnie Roczne i Wagi")
      st.session_state.avg_pcs_12m = st.number_input(
          "Średnia roczna - Sztuki:",
          value=float(st.session_state.avg_pcs_12m),
          step=1000.0,
      )
      st.session_state.w_pcs = st.number_input(
          "Waga - Sztuki (%):", value=float(st.session_state.w_pcs), step=1.0
      )

      st.session_state.avg_lines_12m = st.number_input(
          "Średnia roczna - Pozycje:",
          value=float(st.session_state.avg_lines_12m),
          step=500.0,
      )
      st.session_state.w_lines = st.number_input(
          "Waga - Pozycje (%):", value=float(st.session_state.w_lines), step=1.0
      )

      st.session_state.avg_weight_12m = st.number_input(
          "Średnia roczna - Waga (kg):",
          value=float(st.session_state.avg_weight_12m),
          step=1000.0,
      )
      st.session_state.w_weight = st.number_input(
          "Waga - Waga (%):", value=float(st.session_state.w_weight), step=1.0
      )

  st.markdown("---")
  st.subheader("🚫 Wykluczenia grup klientów")
  st.caption("Źródło: Название текущей категории клиента. "
             "Zaznaczone grupy są pomijane w obliczeniach; plik źródłowy pozostaje bez zmian.")
  mandatory_excluded = {"test", "UA-2", "АНД", "ОПТ_UA", "ФОП_UA"}
  st.caption("Stałe wykluczenia: test, UA-2, АНД, ОПТ_UA, ФОП_UA.")
  saved_excluded = st.session_state.excluded_client_categories
  available_categories = sorted(set(client_categories_in_file) | set(saved_excluded))
  if not client_categories_in_file:
    st.info("Wgraj plik produkcji w panelu bocznym, aby zobaczyć grupy klientów. "
            "Zapisane wykluczenia pozostają dostępne do edycji.")
  selected_excluded = st.multiselect(
      "Dodatkowe grupy wykluczone z premii i analiz:",
      options=[x for x in available_categories if x not in mandatory_excluded],
      default=[x for x in saved_excluded if x in available_categories and x not in mandatory_excluded],
      key="excluded_categories_editor",
  )
  st.session_state.excluded_client_categories = sorted(set(selected_excluded) | mandatory_excluded)
  st.caption("Zapisz zmiany przyciskiem «Zapisz ustawienia w sesji testowej» poniżej. "
             "Zmiany działają w bieżącej sesji od razu.")

  st.markdown("---")
  st.subheader("👥 Zespół i Pracownicy")
  col_export, col_import = st.columns(2)
  with col_export:
    try:
      roster_excel = write_employees_excel(st.session_state.employees_df)
      st.download_button(
          "📤 Eksportuj pracowników do Excel",
          data=roster_excel,
          file_name="zespol_i_pracownicy.xlsx",
          mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
          use_container_width=True,
      )
    except ValueError as exc:
      st.warning(f"Nie można wyeksportować listy: {exc}")
  with col_import:
    employee_file = st.file_uploader(
        "📥 Importuj pracowników z Excel (.xlsx)",
        type=["xlsx"],
        key="employee_roster_import",
    )
  if employee_file is not None:
    try:
      imported_employees = read_employees_excel(employee_file)
      st.info(f"Plik zawiera {len(imported_employees)} pracowników. "
              "Import zastąpi bieżącą listę po zatwierdzeniu.")
      if st.button("Zatwierdź import listy pracowników", type="secondary"):
        st.session_state.employees_df = imported_employees
        st.session_state.pop("settings_employees_editor", None)
        st.success("Lista została zaimportowana. Aby zapisać ją w sesji testowej, "
                   "kliknij «Zapisz ustawienia w sesji testowej».")
        st.rerun()
    except (ValueError, KeyError, OSError) as exc:
      st.error(f"Nie udało się zaimportować listy: {exc}")
  edited_employees = st.data_editor(
      st.session_state.employees_df,
      column_config={
          "UPRAWNIENIA UDT": st.column_config.CheckboxColumn("Uprawnienia UDT")
      },
      use_container_width=True,
      num_rows="dynamic",
      key="settings_employees_editor",
  )
  if isinstance(edited_employees, pd.DataFrame):
    st.session_state.employees_df = edited_employees

  st.markdown("---")
  if st.button("💾 Zapisz ustawienia w sesji testowej", type="primary", use_container_width=True):
    current_settings_to_save = {
        "base_bonus_salary": st.session_state.base_bonus_salary,
        "kierownik_bonus_multiplier": st.session_state.kierownik_bonus_multiplier,
        "forklift_pool": st.session_state.forklift_pool,
        "rate_pallet": st.session_state.rate_pallet,
        "ot_kierownik": st.session_state.ot_kierownik,
        "ot_brygadzista": st.session_state.ot_brygadzista,
        "ot_magazynier": st.session_state.ot_magazynier,
        "avg_pcs_12m": st.session_state.avg_pcs_12m,
        "w_pcs": st.session_state.w_pcs,
        "avg_lines_12m": st.session_state.avg_lines_12m,
        "w_lines": st.session_state.w_lines,
        "avg_weight_12m": st.session_state.avg_weight_12m,
        "w_weight": st.session_state.w_weight,
        "employees_df": st.session_state.employees_df.to_dict("records"),
        "excluded_client_categories": st.session_state.excluded_client_categories,
    }
    if save_persistent_settings(current_settings_to_save):
      st.success("Ustawienia i lista pracowników zostały zapisane w bieżącej sesji testowej.")


