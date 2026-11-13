"""Memoized heavy production calculations for the active bonus month.

Results depend only on production, catalog, exclusions, approved weights and
period, never on manually edited payroll additions.
"""
import calendar

import pandas as pd
import streamlit as st

from client_categories import exclude_categories
from production_import import (
    ARTICLE, BRAND, DATE, QTY,
    normalize, parse_production_dates, prepare_production,
)


@st.cache_data(show_spinner=False, max_entries=5)
def cached_production_totals(production, catalog, excluded):
    """Cache weight matching and monthly aggregates until source data change."""
    return prepare_production(production, catalog, list(excluded))


@st.cache_data(show_spinner=False, max_entries=5)
def cached_daily_totals(production, catalog, excluded, year, month):
    """Cache per-day weight joins; skip on every forklift/pallet/bonus edit."""
    eligible = exclude_categories(production, list(excluded))[0].copy()
    eligible["_brand"] = eligible[BRAND].map(normalize)
    eligible["_article"] = eligible[ARTICLE].map(normalize)
    eligible["_qty"] = pd.to_numeric(
        eligible[QTY].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )

    catalog_map = catalog.copy()
    catalog_map["_brand"] = catalog_map["Producent"].map(normalize)
    catalog_map["_article"] = catalog_map["Artykuł"].map(normalize)
    catalog_map["_weight"] = pd.to_numeric(
        catalog_map["Waga"].astype(str).str.replace(",", ".", regex=False),
        errors="coerce",
    )
    eligible = eligible.merge(
        catalog_map[["_brand", "_article", "_weight"]],
        on=["_brand", "_article"], how="left", validate="many_to_one",
    )
    if DATE not in eligible.columns:
        raise ValueError(
            "W raporcie nie ma wymaganej daty przejścia: " + DATE
        )

    eligible["_date"] = parse_production_dates(eligible[DATE])
    invalid_dates = int(eligible["_date"].isna().sum())
    wrong_period = int((
        eligible["_date"].notna() &
        ((eligible["_date"].dt.year != year) |
         (eligible["_date"].dt.month != month))
    ).sum())

    days = calendar.monthrange(year, month)[1]
    day_map = {
        day: {"pcs": 0.0, "lines": 0.0, "weight": 0.0}
        for day in range(1, days + 1)
    }
    for day, group in eligible.groupby(eligible["_date"].dt.day):
        day_map[int(day)] = {
            "pcs": float(group["_qty"].sum()),
            "lines": float(len(group)),
            "weight": float((group["_qty"] * group["_weight"]).sum()),
        }
    return day_map, invalid_dates, wrong_period
