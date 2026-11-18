"""Unobtrusive, modal help for the TEST Streamlit workspace.

The small rounded "i" icon is not an expander and never changes business
values. Explanations open in a separate native Streamlit dialog only on click.
"""
from hashlib import sha256

import streamlit as st


HELP_STYLE = """
<style>
/* Only our small info controls, never ordinary business buttons. */
div[class*="st-key-help_hint_"] button {
    width: 27px !important;
    min-width: 27px !important;
    max-width: 27px !important;
    height: 27px !important;
    min-height: 27px !important;
    padding: 0 !important;
    margin: 0 !important;
    border-radius: 50% !important;
    border: 1px solid rgba(118, 133, 154, 0.48) !important;
    background: transparent !important;
    color: inherit !important;
    opacity: 0.75;
    box-shadow: none !important;
    font-size: 13px !important;
    font-weight: 650 !important;
    line-height: 1 !important;
    transition: opacity .15s ease, background-color .15s ease;
}
div[class*="st-key-help_hint_"] button:hover,
div[class*="st-key-help_hint_"] button:focus-visible {
    opacity: 1;
    border-color: rgba(94, 116, 149, 0.8) !important;
    background: rgba(116, 137, 172, 0.12) !important;
}
div[class*="st-key-help_hint_"] {
    width: max-content !important;
    max-width: 30px !important;
}
</style>
"""


def help_icon(message, *, title="Informacje i wskazówki"):
    """Show a lightweight trigger that opens a dialog, never an inline panel."""
    identity = sha256((title + "\x00" + message).encode("utf-8")).hexdigest()[:16]
    with st.container(key="help_hint_" + identity):
        opened = st.button(
            "i",
            key="help_button_" + identity,
            type="tertiary",
            help="Otwórz pomoc: " + title,
        )

    if opened:
        @st.dialog(title, width="medium")
        def show_help():
            st.markdown(message)
            if st.button("Zamknij", key="help_close_" + identity):
                st.rerun()

        show_help()


def help_heading(title, message, *, level=4):
    """Use one tidy heading row; help is a dialog, not another expander."""
    left, right = st.columns([18, 1], gap="small", vertical_alignment="center")
    with left:
        st.markdown("#" * int(level) + " " + title)
    with right:
        help_icon(message, title=title)
