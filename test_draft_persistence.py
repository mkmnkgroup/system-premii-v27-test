"""Owner-scoped server-side monthly drafts for the isolated test Streamlit app.

Only a verified admin's JWT is used for PostgREST. The database enforces
row ownership with RLS. No source production files, passwords, tokens, or
published awards are included in the draft payload.
"""
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from urllib.parse import urlencode

import pandas as pd
import requests

MAX_BYTES = 2_097_152
MAX_ROWS = 1700
TABLE_FIELDS = {
    "current_schedule_df", "employees_df", "imported_absences_df",
    "absence_codes_df", "groups_df", "forklift_hours_df", "special_bonuses_df",
}
# Empty DataFrames must retain the columns used by the calculator after restore.
# The JSON rows representation cannot otherwise preserve empty-table schemas.
EMPTY_COLUMNS = {
    "employees_df": [
        "OSOBA", "GRUPA", "SYSTEM", "STANOWISKO", "FUNKCJA", "UPRAWNIENIA UDT",
    ],
    "groups_df": ["Nazwa grupy", "Czas pracy"],
    "absence_codes_df": ["Oznaczenie", "Rodzaj nieobecności"],
    "forklift_hours_df": ["OSOBA", "CZAS WÓZKA (godz.)"],
    "special_bonuses_df": [
        "Pracownik", "Kwota netto premii", "Powód przyznania premii", "Kto przyznał",
    ],
}

SCALARS = (
    "base_bonus_salary", "kierownik_bonus_multiplier", "forklift_pool",
    "rate_pallet", "avg_lines_12m", "w_lines", "avg_pcs_12m", "w_pcs",
    "avg_weight_12m", "w_weight", "ot_kierownik", "ot_brygadzista",
    "ot_magazynier",
)
PAYLOAD_KEYS = {"version", "schedule_period_key", "tables", "settings",
                "excluded_client_categories", "bonus_inputs"}
UUID_PATTERN = re.compile(
    r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
)
PERIOD_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])-01$")


class DraftError(ValueError):
    pass


class DraftConflict(DraftError):
    pass


def check_identity(user_id, period):
    if not isinstance(user_id, str) or not UUID_PATTERN.fullmatch(user_id):
        raise DraftError("Nieprawidłowa tożsamość użytkownika.")
    if not isinstance(period, str) or not PERIOD_PATTERN.fullmatch(period):
        raise DraftError("Nieprawidłowy okres wersji roboczej.")
    return user_id, period


def _records(df):
    if not isinstance(df, pd.DataFrame):
        return []
    if len(df) > MAX_ROWS or len(df.columns) > 80:
        raise DraftError("Zbyt duża tabela w wersji roboczej.")
    if not all(isinstance(x, str) and len(x) <= 180 for x in df.columns):
        raise DraftError("Nieprawidłowe kolumny wersji roboczej.")
    return json.loads(df.to_json(orient="records", date_format="iso", force_ascii=False))


def collect_draft(state, period_key):
    """Snapshot only known payroll *draft* inputs, never published or uploaded data."""
    tables = {field: _records(state.get(field)) for field in sorted(TABLE_FIELDS)}
    saved_bonuses = state.get("_bonus_inputs_by_period", {}).get(period_key)
    bonus_inputs = None
    if isinstance(saved_bonuses, dict):
        bonus_inputs = {
            "forklift": _records(saved_bonuses.get("forklift")),
            "specials": _records(saved_bonuses.get("specials")),
            "pallets": float(saved_bonuses.get("pallets", 0)),
            "selected": list(saved_bonuses.get("selected", [])),
        }
    snapshot = {
        "version": 1,
        "schedule_period_key": period_key if state.get("schedule_period_key") == period_key else None,
        "tables": tables,
        "settings": {key: float(state[key]) for key in SCALARS if key in state},
        "excluded_client_categories": list(state.get("excluded_client_categories", [])),
        "bonus_inputs": bonus_inputs,
    }
    validate_payload(snapshot)
    return snapshot


def validate_payload(payload):
    if not isinstance(payload, dict) or set(payload) != PAYLOAD_KEYS:
        raise DraftError("Nieznana struktura danych wersji roboczej.")
    if payload["version"] != 1:
        raise DraftError("Nieobsługiwany format wersji roboczej.")
    if not isinstance(payload["schedule_period_key"], (str, type(None))):
        raise DraftError("Nieprawidłowy okres harmonogramu.")
    tables = payload["tables"]
    if not isinstance(tables, dict) or set(tables) != TABLE_FIELDS:
        raise DraftError("Nieprawidłowa struktura tabel.")
    for name, rows in tables.items():
        if not isinstance(rows, list) or len(rows) > MAX_ROWS:
            raise DraftError("Nieprawidłowa liczba wierszy: " + name)
        if any(not isinstance(row, dict) or len(row) > 80
               or any(not isinstance(col, str) or len(col) > 180 for col in row)
               for row in rows):
            raise DraftError("Nieprawidłowe wiersze: " + name)
    settings = payload["settings"]
    if not isinstance(settings, dict) or not set(settings).issubset(SCALARS):
        raise DraftError("Nieprawidłowe ustawienia.")
    for value in settings.values():
        if type(value) not in (int, float) or not -1e12 < value < 1e12:
            raise DraftError("Nieprawidłowa liczba w ustawieniach.")
    categories = payload["excluded_client_categories"]
    if not isinstance(categories, list) or len(categories) > 200 or any(
        not isinstance(v, str) or len(v) > 180 for v in categories
    ):
        raise DraftError("Nieprawidłowa lista wykluczeń.")
    bonus = payload["bonus_inputs"]
    if bonus is not None:
        if not isinstance(bonus, dict) or set(bonus) != {
            "forklift", "specials", "pallets", "selected"
        }:
            raise DraftError("Nieprawidłowe dane dodatków.")
        if not isinstance(bonus["forklift"], list) or not isinstance(bonus["specials"], list):
            raise DraftError("Nieprawidłowe dane wózka lub nagród.")
        if len(bonus["forklift"]) > MAX_ROWS or len(bonus["specials"]) > MAX_ROWS:
            raise DraftError("Zbyt wiele dodatków.")
        if type(bonus["pallets"]) not in (float, int) or not 0 <= bonus["pallets"] <= 1e8:
            raise DraftError("Nieprawidłowa liczba palet.")
        if not isinstance(bonus["selected"], list) or len(bonus["selected"]) > 100 or any(
            not isinstance(name, str) or len(name) > 180 for name in bonus["selected"]
        ):
            raise DraftError("Nieprawidłowi uczestnicy podziału.")
    encoded = json.dumps(payload, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_BYTES:
        raise DraftError("Wersja robocza przekracza limit 2 MB.")
    return encoded


def fingerprint(payload):
    return hashlib.sha256(validate_payload(payload).encode("utf-8")).hexdigest()


def apply_draft(state, payload, period_key):
    """Replace known draft inputs only; do not modify auth, publications or uploads."""
    validate_payload(payload)
    if payload["schedule_period_key"] not in (None, period_key):
        raise DraftError("Harmonogram wersji roboczej dotyczy innego miesiąca.")
    for key, rows in payload["tables"].items():
        if key == "current_schedule_df" and payload["schedule_period_key"] is None:
            continue
        state[key] = (
            pd.DataFrame(rows) if rows
            else pd.DataFrame(columns=EMPTY_COLUMNS.get(key))
        )
    if payload["schedule_period_key"] == period_key:
        state["schedule_period_key"] = period_key
    for key, value in payload["settings"].items():
        state[key] = value
    mandatory = {"test", "UA-2", "АНД", "ОПТ_UA", "ФОП_UA"}
    state["excluded_client_categories"] = sorted(
        set(payload["excluded_client_categories"]) | mandatory
    )
    bonus = payload["bonus_inputs"]
    if bonus is not None:
        state.setdefault("_bonus_inputs_by_period", {})[period_key] = {
            "forklift": pd.DataFrame(bonus["forklift"], columns=[
                "OSOBA", "CZAS WÓZKA (godz.)"
            ]),
            "specials": pd.DataFrame(bonus["specials"], columns=[
                "Pracownik", "Kwota netto premii", "Powód przyznania premii", "Kto przyznał"
            ]),
            "pallets": float(bonus["pallets"]),
            "selected": list(bonus["selected"]),
        }
        state["forklift_hours_df"] = state["_bonus_inputs_by_period"][period_key]["forklift"].copy()
        state["special_bonuses_df"] = state["_bonus_inputs_by_period"][period_key]["specials"].copy()
    state.pop("_prepared_bonus_slip", None)


def _api(method, url, key, token, *, params, payload=None, prefer=None):
    headers = {"apikey": key, "Authorization": "Bearer " + token,
               "Content-Type": "application/json"}
    if prefer:
        headers["Prefer"] = prefer
    try:
        response = requests.request(
            method, url.rstrip("/") + "/rest/v1/v27_test_user_drafts",
            headers=headers, params=params, json=payload, timeout=12,
        )
        # Never return secrets, raw responses or tracebacks to the user.
        if response.status_code in (200, 201):
            return response.status_code, response.json()
        return response.status_code, None
    except (requests.RequestException, ValueError):
        return 0, None


def read_draft(url, key, token, user_id, period):
    check_identity(user_id, period)
    status, entries = _api(
        "GET", url, key, token,
        params={"user_id": "eq." + user_id, "period": "eq." + period,
                "select": "payload,revision,updated_at"},
    )
    if status != 200 or not isinstance(entries, list):
        raise DraftError("Nie można odczytać wersji roboczej.")
    if not entries:
        return None
    if len(entries) != 1 or not isinstance(entries[0], dict):
        raise DraftError("Nieprawidłowa odpowiedź bazy wersji roboczych.")
    item = entries[0]
    validate_payload(item.get("payload"))
    revision = item.get("revision")
    if type(revision) is not int or revision < 1:
        raise DraftError("Nieprawidłowa wersja zapisu.")
    return item


def save_draft(url, key, token, user_id, period, payload, previous_revision):
    check_identity(user_id, period)
    validate_payload(payload)
    if type(previous_revision) is not int or previous_revision < 0:
        raise DraftError("Nieprawidłowy numer wersji.")
    updated = datetime.now(timezone.utc).isoformat()
    if previous_revision == 0:
        status, entries = _api(
            "POST", url, key, token, params={"select": "revision,updated_at"},
            payload={"user_id": user_id, "period": period, "payload": payload,
                     "revision": 1, "updated_at": updated},
            prefer="return=representation",
        )
        if status == 409:
            raise DraftConflict("Wersja robocza została już zapisana w innej karcie.")
        expected = 1
    else:
        expected = previous_revision + 1
        status, entries = _api(
            "PATCH", url, key, token,
            params={"user_id": "eq." + user_id, "period": "eq." + period,
                    "revision": "eq." + str(previous_revision),
                    "select": "revision,updated_at"},
            payload={"payload": payload, "revision": expected, "updated_at": updated},
            prefer="return=representation",
        )
        if status == 200 and entries == []:
            raise DraftConflict("Wersja robocza została zmieniona w innej karcie.")
    if status not in (200, 201) or not isinstance(entries, list) or len(entries) != 1:
        raise DraftError("Nie udało się bezpiecznie zapisać wersji roboczej.")
    if entries[0].get("revision") != expected:
        raise DraftError("Nie potwierdzono nowej wersji zapisu.")
    return entries[0]
