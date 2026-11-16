"""Simulated-user checks for the batched warehouse bonus editor.

AppTest deliberately does not use a real Supabase account. It exercises the
real Streamlit form and verifies that inputs are committed only on submit.
"""
import time
import unittest

from streamlit.testing.v1 import AppTest

PERIOD = "Listopad 2026"
EDITOR_KEY = "forklift_bonus_editor_Listopad_2026"
PALLET_KEY = "bonus_pallet_total_Listopad_2026"
FIRST = "TEST PRACOWNIK 01"
SECOND = "TEST PRACOWNIK 02"

APP = """
import pandas as pd
import streamlit as st
from bonus_input_form import render_bonus_inputs

people = pd.DataFrame([
    {"OSOBA": "TEST PRACOWNIK 01", "UPRAWNIENIA UDT": True},
    {"OSOBA": "TEST PRACOWNIK 02", "UPRAWNIENIA UDT": True},
])
pallets, selected, hours, per_person = render_bonus_inputs(
    people, "Listopad 2026", 0.0, 600.0, 10.0
)
st.session_state["test_observed_form"] = (
    pallets, selected, hours, per_person
)
"""


class BonusFormInteractionTests(unittest.TestCase):
    def setUp(self):
        start = time.perf_counter()
        self.app = AppTest.from_string(APP, default_timeout=35).run()
        self.initial_seconds = time.perf_counter() - start
        self.assertFalse(list(self.app.exception))
        self.assertEqual(
            self.app.session_state["test_observed_form"],
            (0.0, [FIRST, SECOND], 0.0, 0.0),
        )

    def test_pallets_do_not_apply_until_submit(self):
        # A browser form intentionally does NOT rerun when a field is edited.
        # Test the staged change before submitting, without forcing an
        # artificial AppTest rerun that would discard unsent form edits.
        self.app.number_input(key=PALLET_KEY).set_value(20.0)
        self.assertEqual(
            self.app.session_state["test_observed_form"][0], 0.0
        )
        self.assertEqual(
            self.app.session_state["_bonus_inputs_by_period"][PERIOD]["pallets"],
            0.0,
        )
        start = time.perf_counter()
        next(b for b in self.app.button if b.label == "Zapisz i przelicz dodatki").click().run()
        rerun_seconds = time.perf_counter() - start
        self.assertFalse(list(self.app.exception))
        self.assertEqual(
            self.app.session_state["_bonus_inputs_by_period"][PERIOD]["pallets"],
            20.0,
        )
        self.assertEqual(
            self.app.session_state["test_observed_form"][0], 20.0
        )
        self.assertAlmostEqual(
            self.app.session_state["test_observed_form"][3], 100.0
        )
        print(
            f"BONUS_FORM_TIMING initial={self.initial_seconds:.3f}s "
            f"post_submit={rerun_seconds:.3f}s (CI simulator, not browser latency)"
        )

    def test_forklift_editor_hours_commit_with_submit(self):
        # This is Streamlit's documented AppTest data-editor edit-state shape.
        self.app.session_state[EDITOR_KEY] = {
            "edited_rows": {"0": {"CZAS WÓZKA (godz.)": 5.0}},
            "added_rows": [], "deleted_rows": [],
        }
        self.app.number_input(key=PALLET_KEY).set_value(10.0)
        next(b for b in self.app.button if b.label == "Zapisz i przelicz dodatki").click().run()
        self.assertFalse(list(self.app.exception))
        observed = self.app.session_state["test_observed_form"]
        self.assertEqual(observed[2], 5.0)
        self.assertEqual(observed[0], 10.0)
        current = self.app.session_state["_bonus_inputs_by_period"][PERIOD]["forklift"]
        self.assertEqual(
            float(current.loc[current["OSOBA"] == FIRST, "CZAS WÓZKA (godz.)"].iloc[0]),
            5.0,
        )


if __name__ == "__main__":
    unittest.main()
