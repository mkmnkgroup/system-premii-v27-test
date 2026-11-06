"""Versioned JSONB storage. Provision schema with sql/001_test_storage.sql."""
from datetime import date, datetime
import json
import math

import pandas as pd
import psycopg
from psycopg.rows import dict_row
from psycopg.conninfo import make_conninfo


class StorageError(Exception):
    """Safe to display; never includes connection details."""


class StorageConflict(StorageError):
    pass


def configured_connection(database_url, password=None):
    """Allow a separate password secret without manual URL encoding."""
    if not database_url or password is None:
        return database_url
    try:
        return make_conninfo(database_url, password=password)
    except Exception:
        raise StorageError("Nieprawidłowa konfiguracja połączenia z bazą.") from None


def _encode(value):
    if isinstance(value, pd.DataFrame):
        return {"__type__": "dataframe", "columns": list(value.columns),
                "rows": json.loads(value.to_json(orient="values", date_format="iso"))}
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(k): _encode(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    if hasattr(value, "item"):
        return _encode(value.item())
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def _decode(value):
    if isinstance(value, dict):
        if value.get("__type__") == "dataframe" and set(value) == {"__type__", "columns", "rows"}:
            return pd.DataFrame(value["rows"], columns=value["columns"])
        return {k: _decode(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_decode(v) for v in value]
    return value


def _connect(database_url):
    # Never forward a psycopg exception to the UI or logging system.
    return psycopg.connect(database_url, sslmode="require", connect_timeout=10,
                           options="-c statement_timeout=15000", prepare_threshold=None)


def read_versioned(database_url, key):
    try:
        with _connect(database_url) as conn:
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT payload, revision FROM app_private.app_store WHERE item_key = %s", (key,))
                row = cur.fetchone()
                return (_decode(row["payload"]), row["revision"]) if row else ({}, None)
    except Exception:
        raise StorageError("Nie można odczytać danych. Sprawdź konfigurację bazy i połączenie.") from None


def write_item(database_url, key, value, *, expected_revision):
    try:
        payload = json.dumps(_encode(value), ensure_ascii=False, allow_nan=False)
        with _connect(database_url) as conn:
            with conn.cursor() as cur:
                if expected_revision is None:
                    cur.execute("""INSERT INTO app_private.app_store (item_key, payload)
                        VALUES (%s, %s::jsonb) ON CONFLICT (item_key) DO NOTHING
                        RETURNING revision""", (key, payload))
                else:
                    cur.execute("""UPDATE app_private.app_store
                        SET payload = %s::jsonb, revision = revision + 1, updated_at = now()
                        WHERE item_key = %s AND revision = %s RETURNING revision""",
                        (payload, key, expected_revision))
                row = cur.fetchone()
                if row is None:
                    raise StorageConflict("Dane zmieniły się w innej sesji. Otwórz aplikację ponownie przed zapisem.")
                return row[0]
    except StorageConflict:
        raise
    except Exception:
        raise StorageError("Nie zapisano danych. Sprawdź konfigurację bazy i połączenie.") from None

