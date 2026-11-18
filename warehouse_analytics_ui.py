"""Optional historical warehouse dashboard based only on restored archives.

Private admin/director workspace. Uses read-only data and never publishes or
updates a payroll month. Charts distinguish missing history and non-comparable
partial years/halves. Customer cost shares are explicitly only estimates.
"""
import pandas as pd
import streamlit as st

from warehouse_history import grouped_history, history_client_groups, monthly_history


MEASURES = {
    "Pozycje": ("positions", "pozycji"),
    "Sztuki": ("pieces", "szt."),
    "Masa towaru (kg)": ("weight_kg", "kg"),
    "Wartość sprzedaży netto (EUR)": ("sales_eur_net", "EUR netto"),
    "Palety": ("pallets", "palet"),
    "Premia główna (PLN)": ("main_bonus_pln", "PLN"),
    "Wszystkie premie i dodatki (PLN)": ("total_cost_pln", "PLN"),
    "Nadgodziny (h)": ("overtime_h", "h"),
    "Koszt premii na 1 000 pozycji": ("cost_pln_per_1000_positions", "PLN / 1 000 pozycji"),
    "Koszt premii na 1 000 EUR sprzedaży": ("cost_pln_per_1000_eur", "PLN / 1 000 EUR"),
}


def _plot_line(df, key, title, unit):
    import plotly.express as px
    if df.empty or df[key].notna().sum() < 2:
        st.info("Za mało danych dla wykresu. Brakujące wartości nie są traktowane jak zera.")
        return
    fig = px.line(df, x="date", y=key, markers=True, title=title)
    fig.update_xaxes(type="category", title_text="Miesiąc")
    fig.update_yaxes(title_text=unit)
    st.plotly_chart(fig, use_container_width=True)


def render_warehouse_history(history, *, prefix="warehouse"):
    """Render month/year/half-year trends and client-group analysis."""
    if not isinstance(history, dict) or not history:
        st.info("Brak historii. Przywróć archiwum z Supabase w module Archiwum.")
        return
    rows = monthly_history(history)
    if not rows:
        st.info("Brak poprawnych miesięcy z wynikami produkcji i premiami w archiwum.")
        return
    labels = [r["period"] for r in rows]
    selected = st.multiselect(
        "Analizowane miesiące (możesz wybrać kilka lat)",
        labels, default=labels, key=prefix + "_chosen_periods",
    )
    included = [r for r in rows if r["period"] in selected]
    if not included:
        st.info("Wybierz przynajmniej jeden miesiąc.")
        return
    selected_df = pd.DataFrame(included)
    tab_trend, tab_period, tab_clients = st.tabs([
        "Trendy wielu miesięcy", "Rok / półrocze / kwartał", "Grupy klientów",
    ])
    with tab_trend:
        measure = st.selectbox(
            "Analizowany wskaźnik", list(MEASURES),
            key=prefix + "_trend_measure",
        )
        key, unit = MEASURES[measure]
        known = selected_df[key].dropna()
        if known.empty:
            st.info(
                "Archiwum tych miesięcy nie zawiera tego wskaźnika. "
                "Dla sprzedaży netto EUR zapisz nowe rozliczenie z wybraną "
                "i potwierdzoną kolumną EUR."
            )
        else:
            st.metric(measure + " · dostępne okresy", f"{known.sum():,.2f}" + " " + unit)
            _plot_line(selected_df, key, f"{measure} — przebieg miesięczny", unit)
            missing = selected_df.loc[selected_df[key].isna(), "period"].tolist()
            if missing:
                st.warning("Brak wskaźnika w archiwum: " + ", ".join(missing))
        st.dataframe(selected_df[[
            "period", "positions", "pieces", "weight_kg", "sales_eur_net",
            "main_bonus_pln", "total_cost_pln", "overtime_h",
            "cost_pln_per_1000_positions",
        ]].rename(columns={
            "period": "Okres", "positions": "Pozycje", "pieces": "Sztuki",
            "weight_kg": "Masa (kg)", "sales_eur_net": "Sprzedaż netto EUR",
            "main_bonus_pln": "Premia główna PLN",
            "total_cost_pln": "Premie i dodatki PLN",
            "overtime_h": "Nadgodziny (h)",
            "cost_pln_per_1000_positions": "PLN / 1 000 pozycji",
        }), hide_index=True, use_container_width=True)
        st.caption(
            "Koszt dotyczy wyłącznie premii i dodatków, nie całkowitego kosztu pracy. "
            "Wskaźnik PLN / 1 000 EUR nie przelicza waluty i nie oznacza marży."
        )
    with tab_period:
        frequency = st.radio(
            "Porównaj okresy", ["Kwartał", "Półrocze", "Rok"],
            horizontal=True, key=prefix + "_period_frequency",
        )
        period_type = {"Kwartał": "quarter", "Półrocze": "half", "Rok": "year"}[frequency]
        sums = grouped_history(included, period_type)
        table = pd.DataFrame(sums)
        table["Pokrycie"] = (
            table["recorded_months"].astype(str)
            + " / " + table["expected_months"].astype(str) + " mies."
        )
        st.dataframe(table[[
            "period", "Pokrycie", "positions", "pieces", "weight_kg",
            "sales_eur_net", "main_bonus_pln", "total_cost_pln",
        ]].rename(columns={
            "period": "Okres", "positions": "Pozycje", "pieces": "Sztuki",
            "weight_kg": "Masa (kg)", "sales_eur_net": "Sprzedaż netto EUR",
            "main_bonus_pln": "Premia główna PLN",
            "total_cost_pln": "Premie i dodatki PLN",
        }), hide_index=True, use_container_width=True)
        incomplete = table.loc[~table["complete"], "period"].tolist()
        if incomplete:
            st.warning(
                "Niepełne okresy: " + ", ".join(incomplete) + ". "
                "Nie porównuj ich bezpośrednio z pełnymi latami, półroczami "
                "lub kwartałami."
            )
        complete = table[table["complete"]]
        if len(complete) >= 2:
            import plotly.express as px
            comparison = st.selectbox(
                "Wskaźnik porównywanych pełnych okresów",
                list(MEASURES)[:7], key=prefix + "_period_measure",
            )
            key, unit = MEASURES[comparison]
            subset = complete.dropna(subset=[key])
            if len(subset) >= 2:
                chart = px.bar(subset, x="period", y=key, title=comparison)
                chart.update_yaxes(title_text=unit)
                st.plotly_chart(chart, use_container_width=True)
        else:
            st.caption(
                "Wykres porównawczy wymaga co najmniej dwóch pełnych okresów "
                "zapisanych w archiwum."
            )
    with tab_clients:
        result = history_client_groups(history, selected)
        if not result["months_with_groups"]:
            st.info(
                "Wybrane archiwalne rozliczenia nie mają jeszcze zapisanych "
                "zestawień według grup klientów. Uzupełnij nowy raport produkcji "
                "i zapisz rozliczenie oraz archiwum w Supabase. Nie odtwarzamy "
                "udziałów grup na podstawie zbiorczych miesięcznych sum."
            )
            return
        if result["missing"]:
            st.warning(
                "Brak szczegółowego podziału na grupy dla miesięcy: "
                + ", ".join(result["missing"])
                + ". Poniższe wartości obejmują TYLKO miesiące ze szczegółami."
            )
        shares = pd.DataFrame(result["groups"])
        if not result["sales_complete"]:
            st.caption(
                "Wartość netto EUR nie została potwierdzona we wszystkich "
                "uwzględnionych miesiącach. Nie sumujemy jej częściowo."
            )
        shown = shares[[
            "group", "positions", "share_positions",
            "pieces", "share_pieces", "weight_kg", "share_weight_kg",
            "sales_eur_net", "share_sales_eur_net",
            "allocated_main_bonus_pln", "share_allocated_main_bonus_pln",
        ]].rename(columns={
            "group": "Grupa klientów", "positions": "Pozycje",
            "share_positions": "% pozycji", "pieces": "Sztuki",
            "share_pieces": "% sztuk", "weight_kg": "Masa kg",
            "share_weight_kg": "% masy",
            "sales_eur_net": "Sprzedaż netto EUR",
            "share_sales_eur_net": "% wartości",
            "allocated_main_bonus_pln": "Przypisany udział premii głównej PLN",
            "share_allocated_main_bonus_pln": "% premii głównej",
        })
        for col in ("% pozycji", "% sztuk", "% masy", "% wartości", "% premii głównej"):
            shown[col] = shown[col] * 100
        st.dataframe(shown, hide_index=True, use_container_width=True)
        import plotly.express as px
        metric = st.selectbox(
            "Porównaj obciążenie grup klientów",
            ["Pozycje", "Sztuki", "Masa kg", "Sprzedaż netto EUR",
             "Przypisany udział premii głównej PLN"],
            key=prefix + "_group_metric",
        )
        if shown[metric].notna().sum():
            fig = px.bar(
                shown, x="Grupa klientów", y=metric,
                title="Wkład grup klientów w obciążenie magazynu",
            )
            st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Grupy wykluczone (duplikaty zamówień) są całkowicie usunięte "
            "z obliczeń i wszystkich mianowników. Przypisanie części premii "
            "głównej grupie jest wyłącznie SZACUNKIEM opartym na udziale pracy "
            "w pozycjach, sztukach i masie. Nie dowodzi dodatkowego kosztu "
            "wywołanego konkretną grupą. Wartość sprzedaży EUR nie zmienia "
            "kwoty premii."
        )
