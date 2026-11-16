"""Offline tests for RLS-bound monthly draft snapshots and optimistic concurrency.

All tokens, users and payloads here are synthetic. No live Supabase writes.
"""
import copy
import json
import unittest
from unittest.mock import patch

import pandas as pd
from test_draft_persistence import (
    DraftError, DraftConflict, apply_draft, check_identity, collect_draft,
    fingerprint, read_draft, save_draft, validate_payload,
)

USER = "11111111-1111-4111-8111-111111111111"
OTHER = "22222222-2222-4222-8222-222222222222"
PERIOD = "2026-11-01"
KEY = "Listopad 2026"


def state_fixture():
    return {
        "schedule_period_key": KEY,
        "current_schedule_df": pd.DataFrame([{
            "OSOBA": "PRACOWNIK TESTOWY", "DATA": "02.11.2026",
            "NADGODZINY (godz.)": 2.5,
        }]),
        "employees_df": pd.DataFrame([{"OSOBA": "PRACOWNIK TESTOWY", "STANOWISKO": "MAGAZYNIER"}]),
        "special_bonuses_df": pd.DataFrame([{
            "Pracownik": "PRACOWNIK TESTOWY", "Kwota netto premii": 75.0,
            "Powód przyznania premii": "Test rozładunku", "Kto przyznał": "KIEROWNIK TEST",
        }]),
        "_bonus_inputs_by_period": {
            KEY: {
                "forklift": pd.DataFrame([{"OSOBA": "PRACOWNIK TESTOWY",
                                           "CZAS WÓZKA (godz.)": 3.0}]),
                "specials": pd.DataFrame([{
                    "Pracownik": "PRACOWNIK TESTOWY", "Kwota netto premii": 75.0,
                    "Powód przyznania premii": "Test rozładunku",
                    "Kto przyznał": "KIEROWNIK TEST",
                }]),
                "pallets": 20.0,
                "selected": ["PRACOWNIK TESTOWY"],
            },
        },
        "base_bonus_salary": 4400.0,
        "forklift_pool": 600.0,
        "excluded_client_categories": ["test", "UA-2"],
        "_test_auth_access_token": "SECRET-JWT-NEVER-EXPORT",
        "_test_auth_refresh_token": "SECRET-REFRESH-NEVER-EXPORT",
        "history_v2": {"PUBLISHED": "PRIVATE-ARCHIVE-NEVER-EXPORT"},
        "uploaded_month_file": b"RAW-PRODUCTION-NEVER-EXPORT",
    }


class DraftSnapshotTests(unittest.TestCase):
    def test_snapshot_contains_only_committed_drafts_not_secrets_or_publications(self):
        state = state_fixture()
        payload = collect_draft(state, KEY)
        serialized = validate_payload(payload)
        for secret in ("SECRET-JWT", "SECRET-REFRESH", "PRIVATE-ARCHIVE",
                       "RAW-PRODUCTION", "_test_auth", "history_v2"):
            self.assertNotIn(secret, serialized)
        self.assertEqual(payload["bonus_inputs"]["pallets"], 20.0)
        self.assertEqual(payload["tables"]["current_schedule_df"][0]["OSOBA"], "PRACOWNIK TESTOWY")
        self.assertEqual(payload["settings"]["base_bonus_salary"], 4400.0)

    def test_restore_in_new_session_preserves_auth_and_does_not_publish(self):
        payload = collect_draft(state_fixture(), KEY)
        fresh = {
            "_test_auth_access_token": "NEW-SESSION-SECRET",
            "history_v2": {"published": "UNCHANGED"},
            "current_schedule_df": pd.DataFrame([{"OSOBA": "OLD"}]),
        }
        apply_draft(fresh, payload, KEY)
        self.assertEqual(fresh["_test_auth_access_token"], "NEW-SESSION-SECRET")
        self.assertEqual(fresh["history_v2"], {"published": "UNCHANGED"})
        self.assertEqual(fresh["current_schedule_df"]["OSOBA"].iloc[0], "PRACOWNIK TESTOWY")
        self.assertEqual(fresh["_bonus_inputs_by_period"][KEY]["pallets"], 20.0)
        self.assertEqual(fresh["excluded_client_categories"].count("UA-2"), 1)
        self.assertEqual(fresh["forklift_hours_df"]["CZAS WÓZKA (godz.)"].iloc[0], 3.0)

    def test_draft_rejects_malformed_or_oversized_payload(self):
        valid = collect_draft(state_fixture(), KEY)
        for change in (
            {"version": 9},
            {"unexpected_auth_token": "SECRET"},
            {"settings": {"extra_field": 100}},
            {"bonus_inputs": {"pallets": 10}},
            {"excluded_client_categories": [3]},
        ):
            with self.subTest(change=change), self.assertRaises(DraftError):
                validate_payload({**valid, **change})
        oversized = copy.deepcopy(valid)
        oversized["tables"]["current_schedule_df"] = [
            {"OSOBA": "X" * 2000} for _ in range(1200)
        ]
        with self.assertRaises(DraftError):
            validate_payload(oversized)

    def test_wrong_period_does_not_restore_another_schedule(self):
        valid = collect_draft(state_fixture(), KEY)
        with self.assertRaises(DraftError):
            apply_draft({}, valid, "Grudzień 2026")
        with self.assertRaises(DraftError):
            check_identity("not-an-account", PERIOD)

    def test_restore_preserves_other_month_bonus_inputs(self):
        payload = collect_draft(state_fixture(), KEY)
        state = {"_bonus_inputs_by_period": {"Grudzień 2026": {"pallets": 999}}}
        apply_draft(state, payload, KEY)
        self.assertEqual(state["_bonus_inputs_by_period"]["Grudzień 2026"]["pallets"], 999)
        self.assertEqual(state["_bonus_inputs_by_period"][KEY]["pallets"], 20.0)

    def test_hash_changes_only_when_payroll_draft_changes(self):
        state = state_fixture()
        old = fingerprint(collect_draft(state, KEY))
        state["_test_auth_access_token"] = "CHANGED-BUT-SECRET"
        self.assertEqual(fingerprint(collect_draft(state, KEY)), old)
        state["_bonus_inputs_by_period"][KEY]["pallets"] = 22.0
        self.assertNotEqual(fingerprint(collect_draft(state, KEY)), old)


class DraftRestApiTests(unittest.TestCase):
    def setUp(self):
        self.payload = collect_draft(state_fixture(), KEY)

    def test_read_filters_on_user_and_period(self):
        with patch("test_draft_persistence._api", return_value=(200, [{
            "payload": self.payload, "revision": 3, "updated_at": "2026-11-16T10:30:00Z"
        }])) as api:
            data = read_draft("https://example.invalid", "anon", "jwt", USER, PERIOD)
        self.assertEqual(data["revision"], 3)
        kwargs = api.call_args.kwargs
        self.assertEqual(kwargs["params"]["user_id"], "eq." + USER)
        self.assertEqual(kwargs["params"]["period"], "eq." + PERIOD)
        self.assertIsNone(read_draft.__defaults__)

    def test_initial_save_does_not_upsert_or_override(self):
        with patch("test_draft_persistence._api", return_value=(201, [{
            "revision": 1, "updated_at": "2026-11-16T10:30:00Z",
        }])) as api:
            saved = save_draft("https://example.invalid", "anon", "jwt",
                               USER, PERIOD, self.payload, 0)
        self.assertEqual(saved["revision"], 1)
        self.assertEqual(api.call_args.args[0], "POST")
        self.assertEqual(api.call_args.kwargs["payload"]["user_id"], USER)
        self.assertEqual(api.call_args.kwargs["payload"]["period"], PERIOD)
        self.assertNotIn("resolution=merge-duplicates", api.call_args.kwargs["prefer"])

    def test_update_requires_exact_revision_and_identity(self):
        with patch("test_draft_persistence._api", return_value=(200, [{
            "revision": 6, "updated_at": "2026-11-16T10:30:00Z",
        }])) as api:
            saved = save_draft("https://example.invalid", "anon", "jwt",
                               USER, PERIOD, self.payload, 5)
        self.assertEqual(saved["revision"], 6)
        self.assertEqual(api.call_args.args[0], "PATCH")
        params = api.call_args.kwargs["params"]
        self.assertEqual(params["revision"], "eq.5")
        self.assertEqual(params["user_id"], "eq." + USER)
        self.assertEqual(params["period"], "eq." + PERIOD)

    def test_concurrent_changes_are_never_silently_overwritten(self):
        for prev, status, rows in ((0, 409, None), (2, 200, [])):
            with patch("test_draft_persistence._api", return_value=(status, rows)):
                with self.assertRaises(DraftConflict):
                    save_draft("https://example.invalid", "anon", "jwt",
                               USER, PERIOD, self.payload, prev)

    def test_http_error_does_not_pretend_save_succeeded(self):
        with patch("test_draft_persistence._api", return_value=(401, None)):
            with self.assertRaises(DraftError):
                save_draft("https://example.invalid", "anon", "jwt",
                           USER, PERIOD, self.payload, 1)
            with self.assertRaises(DraftError):
                read_draft("https://example.invalid", "anon", "jwt", USER, PERIOD)

    def test_per_user_requests_always_use_requested_owner(self):
        with patch("test_draft_persistence._api", return_value=(200, [])) as api:
            read_draft("https://example.invalid", "anon", "jwt", OTHER, PERIOD)
            self.assertEqual(api.call_args.kwargs["params"]["user_id"], "eq." + OTHER)


if __name__ == "__main__":
    unittest.main()
