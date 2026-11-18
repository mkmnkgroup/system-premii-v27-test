"""Temporary, period-scoped source imports for warehouse bonus settlement.

Report and weight catalog are intentionally imported together in 'Rozliczenie
premii'. No source files are written to Supabase or shared across users.
"""
import hashlib
import io
import streamlit as st
from help_ui import help_icon
from workflow_help import SOURCES_HELP


def _key(period):
    return hashlib.sha256(str(period).encode("utf-8")).hexdigest()[:12]


def sources_for_period(state, period):
    """Return independent readable streams for this month only."""
    sources = state.get("_test_monthly_sources", {}).get(period, {})
    def stream(kind):
        record = sources.get(kind)
        if not isinstance(record, dict) or not isinstance(record.get("data"), bytes):
            return None
        result = io.BytesIO(record["data"])
        result.name = record.get("name", "")
        return result
    return stream("report"), stream("weights")


def record_source(state, period, kind, uploaded):
    """Keep uploaded bytes across module navigation but not across periods."""
    if uploaded is None:
        return False
    if kind not in ("report", "weights"):
        raise ValueError("Unsupported source type.")
    data = uploaded.getvalue()
    name = str(getattr(uploaded, "name", "plik.xlsx"))
    records = state.setdefault("_test_monthly_sources", {})
    month = records.setdefault(period, {})
    if month.get(kind) == {"name": name, "data": data}:
        return False
    month[kind] = {"name": name, "data": data}
    return True


def render_monthly_sources(period):
    """Show the two imports only in monthly settlement, never in attendance."""
    with st.expander("📁 Dane źródłowe do rozliczenia · raport i katalog wag", expanded=False):
        help_icon(SOURCES_HELP)
        st.caption(f"Okres importu: {period}")
        report_col, weights_col = st.columns(2)
        with report_col:
            uploaded_report = st.file_uploader(
                "Wgraj raport produkcji (Excel):",
                type=["xlsx", "xls"],
                key="source_report_" + _key(period),
            )
        with weights_col:
            uploaded_weights = st.file_uploader(
                "Aktualna baza wag (Excel .xlsx):",
                type=["xlsx"],
                key="source_weights_" + _key(period),
            )
        record_source(st.session_state, period, "report", uploaded_report)
        record_source(st.session_state, period, "weights", uploaded_weights)
        items = st.session_state.get("_test_monthly_sources", {}).get(period, {})
        for kind, label in (("report", "Raport produkcji"), ("weights", "Katalog wag")):
            if kind in items:
                st.caption(f"{label}: {items[kind]['name']} — załadowany do sesji")
    return sources_for_period(st.session_state, period)
