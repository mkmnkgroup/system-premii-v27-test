"""Client category exclusion rules; no source data is modified."""
import pandas as pd

CLIENT_CATEGORY_COLUMN = "Название текущей категории клиента"


def category_options(df, saved_exclusions=()):
    saved = {str(v).strip() for v in saved_exclusions if str(v).strip()}
    if CLIENT_CATEGORY_COLUMN not in df.columns:
        return sorted(saved)
    present = {str(v).strip() for v in df[CLIENT_CATEGORY_COLUMN].dropna() if str(v).strip()}
    return sorted(present | saved)


def exclude_categories(df, exclusions):
    """Return filtered copy and count; fail closed if configured column is absent."""
    exclusions = {str(v).strip() for v in exclusions if str(v).strip()}
    if not exclusions:
        return df.copy(), 0
    if CLIENT_CATEGORY_COLUMN not in df.columns:
        raise ValueError("Brak kolumny aktualnej kategorii klienta w pliku produkcji.")
    mask = df[CLIENT_CATEGORY_COLUMN].fillna("").astype(str).str.strip().isin(exclusions)
    return df.loc[~mask].copy(), int(mask.sum())

