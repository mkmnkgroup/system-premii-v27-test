"""Small, click-to-open contextual help for the TEST Streamlit workspace.

Keep errors, validation warnings and save/publication confirmations visible.
Use these helpers only for explanatory copy and optional operator advice.
"""
import streamlit as st


def help_icon(message, *, label="ⓘ"):
    """Render contextual guidance only after clicking the small info symbol."""
    with st.popover(label, help="Kliknij, aby wyświetlić opis lub wskazówkę"):
        st.markdown(message)


def help_heading(title, message, *, level=4):
    """Show a section title and its optional explanation in a single row."""
    left, right = st.columns([18, 1], gap="small", vertical_alignment="center")
    with left:
        st.markdown("#" * int(level) + " " + title)
    with right:
        help_icon(message)
