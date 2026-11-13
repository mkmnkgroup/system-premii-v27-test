"""Role-restricted read-only pages backed exclusively by Supabase RLS.

No production data is loaded here. Rows are served only with the signed-in
user's JWT, not the service role. Data are empty until imported securely.
"""
from datetime import date
from urllib.parse import urlencode

import pandas as pd
import requests
import streamlit as st

PROJECT_URL = "https://bzpfukyugfuybqivjyoz.supabase.co"
MONTH_TITLES = {
    1: "Styczeń", 2: "Luty", 3: "Marzec", 4: "Kwiecień",
    5: "Maj", 6: "Czerwiec", 7: "Lipiec", 8: "Sierpień",
    9: "Wrzesień", 10: "Październik", 11: "Listopad", 12: "Grudzień",
}


def role_sections(role):
    """Exposed menu sections: director never gets person-level data."""
    return {
        "admin": ("statystyki", "porownania", "harmonogramy", "premie", "obecnosc"),
        "director": ("statystyki", "porownania"),
        "manager": ("statystyki", "harmonogramy", "premie", "obecnosc"),
        "employee": ("moj_miesiac", "moj_pasek", "moja_obecnosc", "wskazniki"),
    }.get(role, ())


def _get(table, *, filters=None, columns="*", limit=200):
    """Perform a bounded read with user's JWT; RLS still enforces row ownership."""
    token = st.session_state.get("_test_auth_access_token")
    if not isinstance(token, str) or not token:
        return None
    try:
        apikey = str(st.secrets["TEST_SUPABASE_ANON_KEY"])
        query = {"select": columns, "limit": str(limit)}
        if filters:
            query.update(filters)
        response = requests.get(
            PROJECT_URL + "/rest/v1/" + table,
            params=query,
            headers={
                "Authorization": "Bearer " + token,
                "apikey": apikey,
                "Accept": "application/json",
            },
            timeout=12,
        )
        data = response.json()
        if response.status_code != 200 or not isinstance(data, list):
            return None
        return data
    except (requests.RequestException, ValueError, KeyError, FileNotFoundError):
        return None


def _show_table(rows, columns):
    if rows is None:
        st.error("Nie udało się odczytać danych. Odśwież stronę lub zaloguj się ponownie.")
    elif not rows:
        st.info("Brak zatwierdzonych danych dla wybranego okresu.")
    else:
        st.dataframe(pd.DataFrame(rows)[columns], hide_index=True, use_container_width=True)


def _period():
    today = date.today()
    c1, c2 = st.columns(2)
    with c1:
        year = st.selectbox("Rok", list(range(today.year - 2, today.year + 2)),
                            index=2, key="_role_period_year")
    with c2:
        month = st.selectbox("Miesiąc", list(range(1, 13)), index=today.month - 1,
                             format_func=lambda m: MONTH_TITLES[m],
                             key="_role_period_month")
    return "%04d-%02d-01" % (year, month), year, month


def _kpi_block(period, *, employee=False):
    rows = _get("v27_test_monthly_kpis", filters={"period": "eq." + period})
    if rows is None:
        st.error("Nie można pobrać wskaźników.")
        return
    if not rows:
        st.info("Brak zatwierdzonych wskaźników dla wybranego miesiąca.")
        return
    row = rows[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Pozycje zespołu", row.get("positions", "—"))
    c2.metric("Sztuki zespołu", row.get("pieces", "—"))
    c3.metric("Masa towaru (kg)", row.get("weight_kg", "—"))
    st.caption("Zbiorcze parametry miesięczne. Nie zawierają danych innych pracowników.")
    if row.get("performance_pct") is not None:
        st.metric("Wynik głównej premii (%)", row["performance_pct"])
    targets = [
        ("Cel pozycji", row.get("target_positions")),
        ("Cel sztuk", row.get("target_pieces")),
        ("Cel masy (kg)", row.get("target_weight_kg")),
    ]
    visible = [f"{label}: {value}" for label, value in targets if value is not None]
    if visible:
        st.caption(" · ".join(visible))


def _my_month(period, user_id):
    rows = _get("v27_test_employee_monthly",
                filters={"period": "eq." + period, "user_id": "eq." + user_id})
    if rows is None:
        st.error("Nie można pobrać miesięcznego podsumowania.")
        return None
    if not rows:
        st.info("Nie opublikowano jeszcze Twojego miesięcznego podsumowania.")
        return None
    row = rows[0]
    c1, c2, c3 = st.columns(3)
    c1.metric("Moje pozycje", row.get("positions") if row.get("positions") is not None else "Brak danych")
    c2.metric("Moje sztuki", row.get("pieces") if row.get("pieces") is not None else "Brak danych")
    c3.metric("Moja masa towaru (kg)", row.get("weight_kg") if row.get("weight_kg") is not None else "Brak danych")
    a, b = st.columns(2)
    a.metric("Dni zaplanowane", row.get("planned_days", "—"))
    b.metric("Dni obecności", row.get("attended_days", "—"))
    _overtime_metrics(row)
    return row


def _overtime_metrics(row):
    hours, pay = row.get("overtime_hours"), row.get("overtime_pay_pln")
    a, b = st.columns(2)
    a.metric("Nadgodziny (h)", hours if hours is not None else "Brak danych")
    b.metric("Za nadgodziny (PLN)", pay if pay is not None else "Brak danych")
    st.caption("Kwota za nadgodziny jest częścią dodatków i kwoty do wypłaty.")


def _my_payslip(period, user_id):
    rows = _get("v27_test_employee_monthly",
                filters={"period": "eq." + period, "user_id": "eq." + user_id})
    if rows is None:
        st.error("Nie można pobrać paska premiowego.")
    elif not rows:
        st.info("Twój pasek premiowy za ten okres nie został jeszcze opublikowany.")
    else:
        row = rows[0]
        if row.get("user_id") != user_id:
            st.error("Nie można potwierdzić właściciela rozliczenia.")
            return
        c1, c2 = st.columns(2)
        c1.metric("Premia główna (PLN)", row.get("bonus_main_pln", "—"))
        c2.metric("Dodatki (PLN)", row.get("bonus_additions_pln", "—"))
        st.metric("Premia końcowa (PLN)", row.get("bonus_final_pln", "—"))
        st.caption("Potrącenie za nieobecności: " + str(row.get("absence_reduction_pct", "—")) + "%")
        st.caption("System Premii 2.7 TEST · Dokument informacyjny, nie stanowi dokumentu płacowego.")
        _overtime_metrics(row)
        from bonus_components import parse_bonus_breakdown
        try:
            breakdown = parse_bonus_breakdown(row)
        except ValueError:
            st.error("Opublikowane szczegóły dodatków są niespójne. Skontaktuj się z administratorem.")
            return
        if breakdown is None:
            st.info("Szczegółowy podział dodatków nie został jeszcze opublikowany dla tego miesiąca. PDF pokazuje dostępne kwoty zbiorcze.")
        else:
            st.markdown("#### Szczegółowe składniki dodatków")
            entries = [
                {"Składnik": "Nadgodziny", "Kwota (zł)": float(breakdown["overtime_pay"])},
                {"Składnik": "Wózek widłowy", "Kwota (zł)": float(breakdown["forklift_pay"])},
                {"Składnik": "Rozładunki i załadunki palet", "Kwota (zł)": float(breakdown["pallet_pay"])},
            ]
            for item in breakdown["special_bonuses"]:
                entries.append({
                    "Składnik": "Premia specjalna: " + item["reason"],
                    "Kwota (zł)": float(item["amount"]),
                })
            st.dataframe(pd.DataFrame(entries), hide_index=True, use_container_width=True)
            st.caption("Suma powyższych składników: " + str(breakdown["additions_total"]) + " zł. Kwoty są już ujęte w łącznej premii.")
            st.caption("Wygenerowany PDF zawiera również dostępne stawki, godziny i zasady podziału dodatków.")
        profiles = _get("app_user_profiles", filters={"user_id": "eq." + user_id},
                        columns="user_id,employee_id,display_name", limit=1)
        if (not profiles or len(profiles) != 1
                or profiles[0].get("user_id") != user_id or row.get("user_id") != user_id):
            st.warning("Nie można potwierdzić danych pracownika do pobrania PDF.")
            return
        name = profiles[0].get("employee_id") or profiles[0].get("display_name")
        from payslip_pdf import build_payslip_pdf, payslip_filename
        try:
            slip = build_payslip_pdf(period, name, row)
            filename = payslip_filename(period, name)
        except (ValueError, OSError):
            st.error("Nie można przygotować PDF. Sprawdź opublikowane rozliczenie.")
            return
        st.download_button(
            "Pobierz mój pasek (PDF)", slip,
            file_name=filename, mime="application/pdf",
            key="_employee_slip_download")


def _my_attendance(year, month, user_id):
    prefix = "%04d-%02d-" % (year, month)
    rows = _get(
        "v27_test_attendance",
        filters={"user_id": "eq." + user_id,
                 "work_day": "gte." + prefix + "01"},
        columns="work_day,status,absence_label,time_in,time_out,overtime_h",
        limit=40,
    )
    if rows is not None:
        rows = [r for r in rows if str(r.get("work_day", "")).startswith(prefix)]
    _show_table(rows, ["work_day", "status", "absence_label", "time_in", "time_out", "overtime_h"])


def _director_comparison(year, month):
    periods = ["%04d-%02d-01" % (year, m) for m in range(1, month + 1)]
    rows = _get("v27_test_monthly_kpis", filters={"period": "gte." + periods[0]},
                columns="period,positions,pieces,weight_kg,performance_pct",
                limit=60)
    if rows is not None:
        rows = [r for r in rows if r.get("period") in periods]
    _show_table(rows, ["period", "positions", "pieces", "weight_kg", "performance_pct"])


def render_role_dashboard(role, user_id):
    """Only run after app_auth verifies the identity and active role."""
    available = role_sections(role)
    if not available:
        st.error("Brak uprawnień do tej sekcji.")
        st.stop()

    labels = {
        "statystyki": "Statystyki",
        "porownania": "Porównania",
        "harmonogramy": "Harmonogramy",
        "premie": "Premie",
        "obecnosc": "Obecność",
        "moj_miesiac": "Moje podsumowanie",
        "moj_pasek": "Mój pasek",
        "moja_obecnosc": "Moja obecność",
        "wskazniki": "Wskaźniki premii",
    }
    headings = {
        "director": "Panel dyrektora · Statystyki i porównania",
        "manager": "Panel kierownika",
        "employee": "Mój panel miesięczny",
        "admin": "Panel raportowy administratora",
    }
    st.title(headings.get(role, "Panel"))
    st.caption("Środowisko testowe · Odczyt danych zgodny z uprawnieniami użytkownika")
    period, year, month = _period()
    tabs = st.tabs([labels[section] for section in available])
    for section, tab in zip(available, tabs):
        with tab:
            if section in ("statystyki", "wskazniki"):
                _kpi_block(period, employee=section == "wskazniki")
            elif section == "porownania":
                _director_comparison(year, month)
            elif section == "moj_miesiac":
                _my_month(period, user_id)
            elif section == "moj_pasek":
                _my_payslip(period, user_id)
            elif section == "moja_obecnosc":
                _my_attendance(year, month, user_id)
            elif section == "harmonogramy":
                rows = _get("v27_test_schedule",
                            filters={"work_day": "gte.%04d-%02d-01" % (year, month)},
                            columns="user_id,work_day,shift_label,starts_at,ends_at")
                if rows is not None:
                    rows = [r for r in rows if str(r.get("work_day", "")).startswith("%04d-%02d-" % (year, month))]
                _show_table(rows, ["user_id", "work_day", "shift_label", "starts_at", "ends_at"])
            elif section == "premie":
                rows = _get("v27_test_employee_monthly", filters={"period": "eq." + period},
                            columns="user_id,period,bonus_final_pln,absence_reduction_pct")
                _show_table(rows, ["user_id", "period", "bonus_final_pln", "absence_reduction_pct"])
            elif section == "obecnosc":
                rows = _get("v27_test_attendance", filters={"work_day": "gte.%04d-%02d-01" % (year, month)},
                            columns="user_id,work_day,status,absence_label,time_in,time_out,overtime_h")
                if rows is not None:
                    rows = [r for r in rows if str(r.get("work_day", "")).startswith("%04d-%02d-" % (year, month))]
                _show_table(rows, ["user_id", "work_day", "status", "absence_label", "time_in", "time_out", "overtime_h"])
    st.stop()
