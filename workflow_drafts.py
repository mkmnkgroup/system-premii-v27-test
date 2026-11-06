"""Period-scoped draft persistence for a dedicated test database only.

Do not point this module at the production database. The caller must supply
an isolated TEST_DATABASE_URL secret and provision the test-only schema.
"""
from db_storage import read_versioned, write_item


ALLOWED_STAGES = frozenset({"schedule", "attendance", "production", "weights", "bonuses", "approval"})


def draft_key(period, stage):
    if not isinstance(period, str) or len(period) != 7 or period[4] != "-":
        raise ValueError("Nieprawidlowy okres. Oczekiwano RRRR-MM.")
    year, month = period.split("-")
    if not year.isdigit() or not month.isdigit() or not (1 <= int(month) <= 12):
        raise ValueError("Nieprawidlowy okres.")
    if stage not in ALLOWED_STAGES:
        raise ValueError("Nieznany etap procesu.")
    return f"draft_v27:{period}:{stage}"


def load_draft(database_url, period, stage):
    return read_versioned(database_url, draft_key(period, stage))


def save_draft(database_url, period, stage, payload, expected_revision):
    return write_item(database_url, draft_key(period, stage), payload,
                      expected_revision=expected_revision)
