"""Regression: logged-out admins see verified Supabase stage status on return.

All external reads are mocked. Tests never upload files, change SQL, publish
attendance or access a real authentication credential.
"""
from unittest import TestCase
from unittest.mock import patch
from pathlib import Path

import pandas as pd
from streamlit.testing.v1 import AppTest

from workflow_progress import workflow_steps, progress_html
from test_draft_persistence import collect_draft, apply_draft, validate_payload

APP = str(Path(__file__).resolve().parents[1] / "app_v2.py")
PERIOD = "Listopad 2026"
UID = "00000000-0000-4000-8000-000000000019"
REMOTE = {
    "schedule": "saved",
    "attendance": "saved",
    "bonuses": "saved",
    "archive": "saved",
    "archived_periods": ("Październik 2026", PERIOD),
    "attendance_publication": "published",
    "payroll_publication": "published",
}


def steps(remote):
    return workflow_steps(
        {}, year=2026, month=11, period_label=PERIOD,
        schedule_loaded=False, production_loaded=False, weights_loaded=False,
        remote_status=remote,
    )


class ReloginWorkflowTests(TestCase):
    def test_all_stages_recover_saved_evidence_without_local_session(self):
        result = steps(REMOTE)
        self.assertEqual(len(result), 7)
        self.assertEqual([step["tone"] for step in result[:5]], ["done"] * 5)
        self.assertEqual(result[0]["status"], "Zapisany w bazie")
        self.assertEqual(result[1]["status"], "Szkic w bazie")
        self.assertEqual(result[2]["status"], "Zapisane w bazie")
        self.assertEqual(result[3]["status"], "Rozliczenie w bazie")
        self.assertEqual(result[4]["status"], "Zapisane w bazie")
        self.assertEqual(result[5]["status"], "W bazie · przywróć")
        self.assertEqual(result[6]["status"], "W bazie · przywróć")
        self.assertIn("opublikowane", result[4]["description"].lower())
        self.assertIn("Przywróć", result[0]["description"])
        html = progress_html(result, PERIOD)
        self.assertIn("Zapisany w bazie", html)
        self.assertNotIn("Do zaplanowania", html)

    def test_bonus_stage_is_done_after_form_save_even_before_cloud_snapshot(self):
        from workflow_progress import workflow_steps
        state = {
            "_bonus_inputs_by_period": {PERIOD: {"pallets": 14}},
            "_bonus_inputs_confirmed_by_period": {PERIOD: True},
        }
        result = workflow_steps(
            state, year=2026, month=11, period_label=PERIOD,
            schedule_loaded=False, production_loaded=False,
            weights_loaded=False, remote_status={},
        )
        self.assertEqual(result[2]["tone"], "done")
        self.assertEqual(result[2]["status"], "Dodatki wprowadzone")
        self.assertIn("Supabase", result[2]["description"])

        not_confirmed = {
            "_bonus_inputs_by_period": {PERIOD: {"pallets": 14}},
        }
        second = workflow_steps(
            not_confirmed, year=2026, month=11, period_label=PERIOD,
            schedule_loaded=False, production_loaded=False,
            weights_loaded=False, remote_status={},
        )
        self.assertNotEqual(second[2]["tone"], "done")

    def test_draft_and_unknown_are_not_false_completed_stages(self):
        remote = {**REMOTE, "schedule": "unknown", "attendance": "unknown",
                  "bonuses": "draft", "archive": "missing",
                  "archived_periods": (), "payroll_publication": "unknown",
                  "attendance_publication": "missing"}
        r = steps(remote)
        self.assertEqual(r[0]["status"], "Status nieznany")
        self.assertEqual(r[0]["tone"], "working")
        self.assertEqual(r[1]["status"], "Status nieznany")
        self.assertEqual(r[2]["status"], "Szkic w bazie")
        self.assertNotEqual(r[2]["tone"], "done")
        self.assertNotEqual(r[4]["tone"], "done")

    def test_archive_network_failure_is_not_interpreted_as_missing_work(self):
        remote = {**REMOTE, "archive": "unknown", "archived_periods": None}
        result = steps(remote)
        self.assertEqual(result[3]["status"], "Status nieznany")
        self.assertEqual(result[4]["status"], "Status nieznany")
        self.assertEqual(result[5]["status"], "Status nieznany")
        self.assertEqual(result[6]["status"], "Status nieznany")
        self.assertTrue(all(result[i]["tone"] != "done" for i in (3, 4, 5, 6)))

    def test_legacy_bonus_draft_remains_valid_but_unconfirmed(self):
        period = PERIOD
        data = {
            "_bonus_inputs_by_period": {
                period: {
                    "forklift": pd.DataFrame([{
                        "OSOBA": "TEST PRACOWNIK",
                        "CZAS WÓZKA (godz.)": 8.0,
                    }]),
                    "specials": pd.DataFrame(columns=[
                        "Pracownik", "Kwota netto premii",
                        "Powód przyznania premii", "Kto przyznał",
                    ]),
                    "pallets": 10.0,
                    "selected": ["TEST PRACOWNIK"],
                }
            },
            "_bonus_inputs_confirmed_by_period": {period: True},
        }
        payload = collect_draft(data, period)
        self.assertIs(payload["bonus_inputs_confirmed"], True)
        legacy = dict(payload)
        legacy.pop("bonus_inputs_confirmed")
        validate_payload(legacy)
        rest = {}
        apply_draft(rest, legacy, period)
        self.assertIs(rest["_bonus_inputs_confirmed_by_period"][period], False)
        rest2 = {}
        apply_draft(rest2, payload, period)
        self.assertIs(rest2["_bonus_inputs_confirmed_by_period"][period], True)

    def test_app_sidebar_and_dashboard_show_server_save_but_prompt_restore(self):
        with patch("app_auth.login_gate", return_value=None), patch(
            "workflow_status_sync.load_remote_workflow_status", return_value=REMOTE
        ):
            # The fake login gate must not display any personal user information.
            app = AppTest.from_file(APP, default_timeout=45).run()
            self.assertEqual(list(app.exception), [])
            # The entrypoint imports status loader, and both sidebar and ribbon
            # derive from verified server evidence, not locally loaded frames.
            self.assertNotIn(
                "Zapisany w bazie",
                [m.value for m in app.markdown],
            ) if app.session_state.erp_period_month != "Listopad" else None
            next(x for x in app.selectbox if x.label == "Miesiąc rozliczenia").set_value("Listopad").run()
            self.assertEqual(list(app.exception), [])
            labels = next(r for r in app.radio if r.label == "Moduł").options
            self.assertTrue(any("✓" in l and "Harmonogram" in l for l in labels))
            self.assertTrue(any("Zapisany w bazie" in m.value for m in app.markdown))
            # A remote status never implies an automatic restore of actual data.
            self.assertNotIn(
                "_test_saved_draft_revision_draft_v27_2026-11_schedule", app.session_state
            )

    def test_authenticated_status_cache_is_scoped_by_month_and_user(self):
        script = """
import streamlit as st
from workflow_status_sync import load_remote_workflow_status
st.session_state["_test_work_user_id"] = st.session_state.get("account", "00000000-0000-4000-8000-000000000019")
st.session_state["_test_auth_access_token"] = "synthetic-token"
month = st.session_state.get("month", 11)
result = load_remote_workflow_status(2026, month, "Listopad 2026" if month == 11 else "Grudzień 2026")
st.write(result["schedule"])
"""
        with patch("workflow_status_sync._draft_status", return_value="saved") as draft, \
             patch("workflow_status_sync._monthly_snapshot_status", return_value="missing"), \
             patch("workflow_status_sync._archive_periods", return_value=()), \
             patch("workflow_status_sync._publication_status", return_value=("missing", "missing")):
            app = AppTest.from_string(script, default_timeout=45).run()
            self.assertEqual(list(app.exception), [])
            self.assertEqual(draft.call_count, 2)
            app.run()
            self.assertEqual(draft.call_count, 2)
            app.session_state["month"] = 12
            app.run()
            self.assertEqual(draft.call_count, 4)
            app.session_state["account"] = "00000000-0000-4000-8000-000000000020"
            app.run()
            self.assertEqual(draft.call_count, 6)

if __name__ == "__main__":
    import unittest
    unittest.main()
