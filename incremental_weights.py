"""Incremental, approval-first weight catalog reconciliation."""
import pandas as pd
from production_import import normalize

KEYS = ("_brand", "_article")


def canonicalize(frame):
    required = ("Producent", "Artykuł", "Waga")
    absent = [name for name in required if name not in frame.columns]
    if absent:
        raise ValueError("Brak kolumn: " + ", ".join(absent))
    result = frame.loc[:, list(required)].copy()
    result["_brand"] = result["Producent"].map(normalize)
    result["_article"] = result["Artykuł"].map(normalize)
    result["_weight"] = pd.to_numeric(result["Waga"].astype(str).str.replace(",", ".", regex=False), errors="coerce")
    result = result[(result["_brand"] != "") & (result["_article"] != "")]
    if result.duplicated(list(KEYS)).any():
        raise ValueError("Powtarzające się klucze producent + artykuł.")
    return result


def reconcile_weights(existing, incoming):
    """Never overwrite existing weights. Return new entries and discrepancies for review."""
    old = canonicalize(existing)
    new = canonicalize(incoming)
    if new["_weight"].isna().any() or (new["_weight"] <= 0).any():
        raise ValueError("Nowy katalog zawiera nieprawidłowe wagi.")
    if old["_weight"].isna().any() or (old["_weight"] <= 0).any():
        raise ValueError("Zapisany katalog zawiera nieprawidłowe wagi.")
    joined = new.merge(old[list(KEYS) + ["_weight"]], on=list(KEYS), how="left", suffixes=("_new", "_old"), indicator=True, validate="one_to_one")
    added = joined.loc[joined["_merge"] == "left_only", ["Producent", "Artykuł", "_weight_new"]].copy()
    added.columns = ["Producent", "Artykuł", "Waga"]
    changed = joined.loc[(joined["_merge"] == "both") & ((joined["_weight_new"] - joined["_weight_old"]).abs() > 1e-9), ["Producent", "Artykuł", "_weight_old", "_weight_new"]].copy()
    changed.columns = ["Producent", "Artykuł", "Waga zapisana", "Waga w nowym pliku"]
    return {"new_items": added.reset_index(drop=True), "discrepancies": changed.reset_index(drop=True), "unchanged": int((joined["_merge"] == "both").sum() - len(changed))}

