"""Client-category workload attribution for warehouse analytics.

Excluded client categories are duplicate orders, not separate warehouse work.
All percentages and denominators use eligible positions only. Net EUR sales
is informational and NEVER enters the existing bonus calculation.
"""
from __future__ import annotations

import math

import pandas as pd

from client_categories import CLIENT_CATEGORY_COLUMN, exclude_categories
from production_import import ARTICLE, BRAND, GOODS_VALUE, QTY, normalize


def numeric_series(values):
    """Handle Excel numeric values and European thousands/decimal separators."""
    def parse(v):
        if v is None or (not isinstance(v, str) and pd.isna(v)):
            return float("nan")
        if isinstance(v, (int, float)):
            return float(v)
        s = str(v).strip().replace("\u00a0", "").replace(" ", "")
        if not s:
            return float("nan")
        if "," in s and "." in s:
            if s.rfind(",") > s.rfind("."):
                s = s.replace(".", "").replace(",", ".")
            else:
                s = s.replace(",", "")
        elif "," in s:
            s = s.replace(",", ".")
        try:
            return float(s)
        except ValueError:
            return float("nan")
    return values.map(parse).astype(float)


def _finite_nonnegative(values):
    return values.notna() & values.map(math.isfinite) & (values >= 0)


def group_workload(production, catalog, excluded, *,
                   value_mode=None, workload_weights=(42.86, 28.57, 28.57)):
    """Return JSON-safe, additive group summaries and explicit data quality."""
    required = (CLIENT_CATEGORY_COLUMN, ARTICLE, BRAND, QTY)
    if any(c not in production for c in required):
        raise ValueError("Niekompletny raport produkcji do analizy grup klientów.")
    eligible, excluded_count = exclude_categories(production, excluded)
    if eligible.empty:
        raise ValueError("Po wykluczeniach nie ma pozycji do analizy.")
    work = eligible.copy()
    work["_q"] = numeric_series(work[QTY])
    if not _finite_nonnegative(work["_q"]).all():
        raise ValueError("Niepoprawna liczba sztuk w uwzględnianych grupach klientów.")
    work["_brand"] = work[BRAND].map(normalize)
    work["_article"] = work[ARTICLE].map(normalize)
    weights = catalog.copy()
    if any(c not in weights for c in ("Producent", "Artykuł", "Waga")):
        raise ValueError("Niekompletny katalog wag.")
    weights["_brand"] = weights["Producent"].map(normalize)
    weights["_article"] = weights["Artykuł"].map(normalize)
    weights["_weight"] = numeric_series(weights["Waga"])
    weights = weights[(weights["_brand"] != "") & (weights["_article"] != "")]
    if weights.duplicated(["_brand", "_article"]).any():
        raise ValueError("Zduplikowany producent i artykuł w katalogu wag.")
    work = work.merge(
        weights[["_brand", "_article", "_weight"]],
        how="left", on=["_brand", "_article"], validate="many_to_one",
        sort=False,
    )
    if not _finite_nonnegative(work["_weight"]).all():
        raise ValueError("Niekompletne wagi produktów w uwzględnianych grupach.")
    work["_mass"] = work["_q"] * work["_weight"]
    work["_group"] = (
        work[CLIENT_CATEGORY_COLUMN].fillna("").astype(str).str.strip()
        .replace("", "(bez kategorii)")
    )
    have_value = value_mode in ("position", "unit")
    if value_mode not in (None, "position", "unit"):
        raise ValueError("Nieznany sposób naliczania wartości sprzedaży.")
    invalid_values = 0
    if have_value:
        if GOODS_VALUE not in work:
            raise ValueError("Brak wybranej kolumny sprzedaży netto EUR.")
        amount = numeric_series(work[GOODS_VALUE])
        valid_amount = _finite_nonnegative(amount)
        invalid_values = int((~valid_amount).sum())
        if not invalid_values:
            work["_eur"] = amount * work["_q"] if value_mode == "unit" else amount
    components = ("positions", "pieces", "weight_kg")
    weights_coef = [float(v) for v in workload_weights]
    if len(weights_coef) != 3 or any(not math.isfinite(v) or v < 0 for v in weights_coef) or sum(weights_coef) <= 0:
        raise ValueError("Nieprawidłowe wagi udziału obciążenia.")
    weights_coef = [v / sum(weights_coef) for v in weights_coef]
    totals = {
        "positions": int(len(work)),
        "pieces": float(work["_q"].sum()),
        "weight_kg": float(work["_mass"].sum()),
        "sales_eur_net": float(work["_eur"].sum()) if have_value and not invalid_values else None,
    }
    grouped = []
    for name, frame in work.groupby("_group", sort=True, dropna=False):
        row = {
            "group": str(name),
            "positions": int(len(frame)),
            "pieces": float(frame["_q"].sum()),
            "weight_kg": float(frame["_mass"].sum()),
            "sales_eur_net": float(frame["_eur"].sum()) if totals["sales_eur_net"] is not None else None,
        }
        for key in components:
            row["share_" + key] = (row[key] / totals[key]) if totals[key] > 0 else None
        row["share_sales_eur_net"] = (
            row["sales_eur_net"] / totals["sales_eur_net"]
            if totals["sales_eur_net"] is not None and totals["sales_eur_net"] > 0
            else None
        )
        # Shares in pieces, positions and kg, same three elements as the
        # warehouse production indicator, normalized for allocation only.
        row["workload_share"] = sum(
            (row["share_" + c] or 0) * w
            for c, w in zip(components, weights_coef)
        )
        grouped.append(row)
    return {
        "groups": grouped, "totals": totals,
        "excluded_duplicate_positions": int(excluded_count),
        "value_selected": have_value,
        "value_complete": bool(have_value and invalid_values == 0),
        "invalid_value_positions": invalid_values,
        "value_mode": value_mode,
        "workload_weights": dict(zip(components, weights_coef)),
    }


def estimated_main_bonus_allocation(result, bonus_main_pln):
    """Illustrative distribution of total main bonus, NOT marginal causality."""
    if not isinstance(result, dict) or not result.get("groups"):
        raise ValueError("Nie ma grup klientów do rozdzielenia kosztów.")
    amount = float(bonus_main_pln)
    if not math.isfinite(amount) or amount < 0:
        raise ValueError("Niepoprawna kwota głównej premii.")
    groups = [dict(row) for row in result["groups"]]
    for row in groups:
        row["allocated_main_bonus_pln"] = amount * float(row["workload_share"])
    return groups
