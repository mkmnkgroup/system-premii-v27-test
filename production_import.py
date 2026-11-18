"""Safe preparation of production KPIs from a current monthly export and weight catalog."""
import io
import pandas as pd
from client_categories import CLIENT_CATEGORY_COLUMN, exclude_categories

BRAND = "Наименование ТМ запчасти"
ARTICLE = "Каталожный номер отформатированный"
QTY = "Количество штук в строке заказа"
DATE = "Дата перехода в искомое состояние"

# Selected source column is retained as an explicit value field; do not infer
# price, currency or invoice totals from an arbitrary numeric source column.
GOODS_VALUE = "_goods_value_source"
VALUE_HINTS = ("стоим", "сумма", "вартіст", "вартос", "warto", "value", "amount")


def _production_header(file_bytes):
    from openpyxl import load_workbook
    book = load_workbook(io.BytesIO(file_bytes), read_only=True, data_only=True)
    try:
        rows = book.active.iter_rows(values_only=True)
        for index, row in enumerate(rows):
            if index >= 12:
                break
            named = {str(value).strip(): i for i, value in enumerate(row)
                     if value is not None and str(value).strip()}
            if all(name in named for name in
                   (CLIENT_CATEGORY_COLUMN, BRAND, ARTICLE, QTY, DATE)):
                return named, rows, book
        raise ValueError("Nie znaleziono wymaganych kolumn raportu produkcji.")
    except Exception:
        book.close()
        raise


def production_value_candidates(file_bytes):
    """List *all* optional headers, with likely value fields first.

    The operator must identify net EUR sales explicitly. A missing hint is
    never grounds for silently substituting a different source field.
    """
    named, _, book = _production_header(file_bytes)
    try:
        options = [name for name in named if name not in
                   (CLIENT_CATEGORY_COLUMN, BRAND, ARTICLE, QTY, DATE)]
        return sorted(options, key=lambda name: (
            not any(hint in name.casefold() for hint in VALUE_HINTS),
            name.casefold(),
        ))
    finally:
        book.close()



def parse_production_dates(values):
    """Vectorized mixed-date parser with explicit ISO vs local date order.

    Supplier files mix ISO strings, Polish day-first strings, datetime cells,
    and blanks. Batch conversion avoids thousands of per-row calls to
    pd.to_datetime while preserving the original day/month interpretation.
    """
    if not isinstance(values, pd.Series):
        values = pd.Series(values)
    iso = values.astype("string").str.match(
        r"^\s*\d{4}-\d{2}-\d{2}(?:[ T]|$)", na=False,
    )
    parsed = pd.Series(pd.NaT, index=values.index, dtype="datetime64[ns]")
    if iso.any():
        parsed.loc[iso] = pd.to_datetime(
            values.loc[iso], format="mixed", dayfirst=False, errors="coerce",
        )
    local = ~iso
    if local.any():
        parsed.loc[local] = pd.to_datetime(
            values.loc[local], format="mixed", dayfirst=True, errors="coerce",
        )
    return parsed


def normalize(value):
    return str(value).strip().casefold() if pd.notna(value) else ""


def read_production(file_bytes, value_column=None):
    """Read source work fields plus the *explicitly selected* merchandise value."""
    named, rows, book = _production_header(file_bytes)
    columns = [CLIENT_CATEGORY_COLUMN, BRAND, ARTICLE, QTY, DATE]
    if value_column is not None:
        if value_column not in named or value_column in columns:
            book.close()
            raise ValueError("Nie znaleziono wybranej kolumny wartości w raporcie.")
        columns.append(value_column)
    indices = [named[key] for key in columns]
    output = columns[:-1] + [GOODS_VALUE] if value_column else columns
    try:
        values = ([row[i] if i < len(row) else None for i in indices]
                  for row in rows)
        return pd.DataFrame.from_records(values, columns=output)
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

