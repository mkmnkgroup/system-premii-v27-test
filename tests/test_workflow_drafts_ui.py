"""Unit tests for private, explicit versioned TEST workflow drafts.

No Supabase credentials or real database connection are needed.
"""
import unittest
from unittest.mock import patch

import pandas as pd
from db_storage import _encode, _decode
from test_schedule_drafts import draft_item_key, safe_period, _slot, decode_schedule_payload, decode_archive_payload


class TestDraftKeys(unittest.TestCase):
    def test_period_is_normalized(self):
        self.assertEqual(safe_period(2026, 11), "2026-11")
        self.assertEqual(draft_item_key(2026, 11), "draft_v27:2026-11:schedule")
        self.assertEqual(draft_item_key(2026, 11, "attendance"), "draft_v27:2026-11:attendance")

    def test_period_and_stage_invalid_fail_closed(self):
        for year, month in ((2026, 0), (2026, 13), (1999, 11), (2101, 11)):
            with self.subTest(year=year, month=month):
                with self.assertRaises(ValueError):
                    safe_period(year, month)
        for stage in ("unknown", "settings_v27", "archive_v27", "production"):
            with self.subTest(stage=stage):
                with self.assertRaises(ValueError):
                    draft_item_key(2026, 11, stage)

    def test_revisions_are_period_scoped(self):
        self.assertNotEqual(_slot(draft_item_key(2026, 11)),
                            _slot(draft_item_key(2026, 12)))
        self.assertNotEqual(_slot("archive_v27"), _slot(draft_item_key(2026, 11)))

    def test_excel_schedule_can_be_encoded_and_decoded(self):
        frame = pd.DataFrame([{
            "OSOBA": "FIKCYJNY PRACOWNIK",
            "DATA": "10.11.2026",
            "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący",
            "CZAS ZMIANY": "06:00-14:00",
            "NIEOBECNOŚĆ": "Brak",
        }])
        restored = _decode(_encode(frame))
        pd.testing.assert_frame_equal(restored, frame)

    def test_decode_saved_schedule_for_selected_month(self):
        frame = pd.DataFrame([{
            "OSOBA": "FIKCYJNY", "DATA": "10.11.2026",
            "CZAS ZMIANY": "08:00-16:00", "DZIEŃ PRACUJĄCY/WOLNY": "Pracujący",
        }])
        payload = {"format_version": 1, "period": "2026-11", "schedule": _encode(frame)}
        actual = decode_schedule_payload(payload, 2026, 11)
        pd.testing.assert_frame_equal(actual, frame)
        with self.assertRaises(ValueError):
            decode_schedule_payload(payload, 2026, 12)
        frame.loc[0, "DATA"] = "10.12.2026"
        with self.assertRaises(ValueError):
            decode_schedule_payload(
                {"format_version": 1, "period": "2026-11", "schedule": _encode(frame)},
                2026, 11
            )

    def test_reject_corrupt_archive_without_restoring(self):
        for payload in (
            None,
            {},
            {"format_version": 2, "archive": {}},
            {"format_version": 1, "archive": {"Listopad 2026": {"summary": "not a dataframe"}}},
            {"format_version": 1, "archive": {"Listopad 2026": {"summary": {
                "__type__": "dataframe", "columns": ["Pracownik"], "rows": [1]
            }}}},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises((ValueError, TypeError)):
                    decode_archive_payload(payload)

    def test_decode_archive_retains_dataframes(self):
        value = {
            "Listopad 2026": {
                "summary": pd.DataFrame({"Pracownik": ["FIKCYJNY"], "Premia (zł)": [400.0]}),
                "schedule": pd.DataFrame({"OSOBA": ["FIKCYJNY"], "DATA": ["10.11.2026"]}),
                "metrics": {"pcs": 12, "lines": 4},
            }
        }
        restored = decode_archive_payload({"format_version": 1, "archive": _encode(value)})
        pd.testing.assert_frame_equal(restored["Listopad 2026"]["summary"],
                                      value["Listopad 2026"]["summary"])

    def test_archive_round_trip(self):
        archive = {
            "Listopad 2026": {
                "summary": pd.DataFrame({"Pracownik": ["FIKCYJNY"], "Premia (zł)": [400.0]}),
                "metrics": {"pcs": 12, "lines": 4},
            }
        }
        restored = _decode(_encode(archive))
        self.assertEqual(restored["Listopad 2026"]["metrics"]["pcs"], 12)
        pd.testing.assert_frame_equal(restored["Listopad 2026"]["summary"],
                                      archive["Listopad 2026"]["summary"])


if __name__ == "__main__":
    unittest.main()
