"""Safe preparation of production KPIs from a current monthly export and weight catalog."""
import io
import re
import pandas as pd
from client_categories import CLIENT_CATEGORY_COLUMN, exclude_categories

BRAND = "Наименование ТМ запчасти"
ARTICLE = "Каталожный номер отформатированный"
QTY = "Количество штук в строке заказа"
DATE = "Дата перехода в искомое состояние"


def parse_production_dates(values):
    """Preserve ISO year-month-day order while accepting local day-first dates."""
    def parse(value):
        iso = isinstance(value, str) and bool(re.match(r'^\s*\d{4}-\d{2}-\d{2}(?:[ T]|$)', value))
        return pd.to_datetime(value, dayfirst=not iso, errors="coerce")
    return values.map(parse)


def normalize(value):
    return str(value).strip().casefold() if pd.notna(value) else ""


def read_production(file_bytes):
    """Read only required fields, supporting metadata rows in supplier exports."""
    from openpyxl import load_workbook
    columns = (CLIENT_CATEGORY_COLUMN, BRAND, ARTICLE, QTY, DATE)
    book = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    try:
        sheet = book.active
        rows = sheet.iter_rows(values_only=True)
        header = None
        for index, row in enumerate(rows):
            if index >= 12:
                break
            candidate = {str(value).strip(): pos for pos, value in enumerate(row) if value is not None}
            if all(name in candidate for name in columns):
                header = [candidate[name] for name in columns]
                break
        if header is None:
            raise ValueError("Nie znaleziono wymaganych kolumn raportu produkcji.")
        values = ([row[i] if i < len(row) else None for i in header] for row in rows)
        return pd.DataFrame.from_records(values, columns=columns)
    finally:
        book.close()


def read_weights(file_bytes):
    """Read only relevant catalog columns using pandas' optimized Excel parser."""
    data = io.BytesIO(file_bytes)
    return pd.read_excel(data, usecols=["Producent", "Artykuł", "Waga"], engine="openpyxl")


def prepare_production(production, weights, excluded=()):
    required = (CLIENT_CATEGORY_COLUMN, BRAND, ARTICLE, QTY)
    missing = [c for c in required if c not in production.columns]
    if missing:
        raise ValueError("Brak kolumn w raporcie produkcji: " + ", ".join(missing))
    missing_weights = [c for c in ("Producent", "Artykuł", "Waga") if c not in weights.columns]
    if missing_weights:
        raise ValueError("Brak kolumn w bazie wag: " + ", ".join(missing_weights))
    filtered, excluded_count = exclude_categories(production, excluded)
    source = filtered.copy()
    source["_brand"] = source[BRAND].map(normalize)
    source["_article"] = source[ARTICLE].map(normalize)
    source["_qty"] = pd.to_numeric(source[QTY].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    catalog = weights.copy()
    catalog["_brand"] = catalog["Producent"].map(normalize)
    catalog["_article"] = catalog["Artykuł"].map(normalize)
    catalog["_weight"] = pd.to_numeric(catalog["Waga"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    catalog = catalog[(catalog["_brand"] != "") & (catalog["_article"] != "")]
    duplicates = catalog.duplicated(["_brand", "_article"], keep=False)
    if duplicates.any():
        raise ValueError("Baza wag zawiera powtarzające się klucze producent + artykuł.")
    source = source.merge(catalog[["_brand", "_article", "_weight"]], on=["_brand", "_article"], how="left", validate="many_to_one", sort=False)
    valid = source["_weight"].notna() & (source["_weight"] >= 0) & source["_qty"].notna() & (source["_qty"] >= 0)
    missing = source.loc[~valid, [BRAND, ARTICLE, QTY]].copy()
    missing.columns = ["Producent", "Artykuł", "Liczba sztuk"]
    missing = missing.drop_duplicates()
    return {
        "positions": len(source),
        "pieces": float(source["_qty"].sum()) if source["_qty"].notna().all() else None,
        "weight_kg": float((source["_qty"] * source["_weight"]).sum()) if valid.all() else None,
        "excluded_positions": excluded_count,
        "matched_positions": int(valid.sum()),
        "missing_positions": int((~valid).sum()),
        "missing_items": missing,
    }

