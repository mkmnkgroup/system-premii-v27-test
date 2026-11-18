"""One-action, period-scoped input form for warehouse bonus additions.

Streamlit forms batch widget edits: expensive production analysis only reruns
after "Zapisz i przelicz dodatki", not after each typed cell.
"""
import pandas as pd
import streamlit as st
from help_ui import help_icon
from workflow_help import BONUS_HELP, MODULE_HELP


def _empty_specials():
    return pd.DataFrame(columns=[
        "Pracownik", "Kwota netto premii", "Powód przyznania premii", "Kto przyznał",
    ])


def _initial_snapshot(employees, default_pallets):
    return {
        "forklift": pd.DataFrame([
            {"OSOBA": person, "CZAS WÓZKA (godz.)": 0.0}
            for person in employees
        ]),
        "specials": _empty_specials(),
        "pallets": float(default_pallets),
        "selected": list(employees),
    }


def _safe_period_id(period):
    return "".join(ch if ch.isalnum() else "_" for ch in str(period))


def committed_bonus_inputs(employees_df, period, default_pallets, pallet_rate):
    """Read the last committed month-specific allowances without drawing the form.

    The calculator calls this only after source production validation; the
    form can instead be used earlier, in the separate Dodatki module.
    """
    people = employees_df["OSOBA"].dropna().astype(str).tolist()
    if not people:
        return 0.0, [], 0.0, 0.0
    store = st.session_state.setdefault("_bonus_inputs_by_period", {})
    if period not in store:
        snapshot = _initial_snapshot(people, default_pallets)
        if not store:
            legacy_forklift = st.session_state.get("forklift_hours_df")
            if isinstance(legacy_forklift, pd.DataFrame) and {
                "OSOBA", "CZAS WÓZKA (godz.)"
            }.issubset(legacy_forklift.columns):
                snapshot["forklift"] = legacy_forklift[
                    ["OSOBA", "CZAS WÓZKA (godz.)"]
                ].copy()
            legacy_special = st.session_state.get("special_bonuses_df")
            if isinstance(legacy_special, pd.DataFrame) and set(
                snapshot["specials"].columns
            ).issubset(legacy_special.columns):
                snapshot["specials"] = legacy_special.copy()
        store[period] = snapshot
    saved = store[period]
    st.session_state.forklift_hours_df = saved["forklift"].copy()
    st.session_state.special_bonuses_df = saved["specials"].copy()
    hours = float(pd.to_numeric(
        saved["forklift"]["CZAS WÓZKA (godz.)"], errors="coerce"
    ).fillna(0.0).sum())
    pallets = float(saved["pallets"])
    selected = [person for person in saved["selected"] if person in people]
    pool = pallets * float(pallet_rate)
    return pallets, selected, hours, pool / len(selected) if selected else 0.0


def render_bonus_inputs(employees_df, period, default_pallets, forklift_pool, pallet_rate):
    """Render inputs, keep committed values, return payable allocation variables.

    Values are *not* changed when the user edits a field. They are applied
    atomically to session state only after the submit button is clicked.
    """
    people = employees_df["OSOBA"].dropna().astype(str).tolist()
    if not people:
        st.warning("Najpierw dodaj pracowników w module Zespół i Pracownicy.")
        return 0.0, [], 0.0, 0.0

    store = st.session_state.setdefault("_bonus_inputs_by_period", {})
    if period not in store:
        snapshot = _initial_snapshot(people, default_pallets)
        if not store:
            # Preserve inputs already entered in the earlier unbatched UI
            # when the new form is first deployed during an active session.
            legacy_forklift = st.session_state.get("forklift_hours_df")
            if isinstance(legacy_forklift, pd.DataFrame) and {
                "OSOBA", "CZAS WÓZKA (godz.)"
            }.issubset(legacy_forklift.columns):
                snapshot["forklift"] = legacy_forklift[
                    ["OSOBA", "CZAS WÓZKA (godz.)"]
                ].copy()
            legacy_special = st.session_state.get("special_bonuses_df")
            if isinstance(legacy_special, pd.DataFrame) and set(
                snapshot["specials"].columns
            ).issubset(legacy_special.columns):
                snapshot["specials"] = legacy_special.copy()
        store[period] = snapshot
    saved = store[period]

    # Synchronize the calculator with the selected month's committed inputs.
    st.session_state.forklift_hours_df = saved["forklift"].copy()
    st.session_state.special_bonuses_df = saved["specials"].copy()

    if st.session_state.get("_bonus_inputs_confirmed_by_period", {}).get(period) is True:
        st.success(
            "Dodatki dla tego miesiąca zostały wprowadzone i zatwierdzone "
            "w bieżącej sesji. Aby zachować je po wylogowaniu, zapisz również "
            "„Wersję roboczą miesiąca” w Supabase."
        )
    else:
        help_icon(MODULE_HELP["bonuses"])
    safe_key = _safe_period_id(period)

    people_df = employees_df[["OSOBA", "UPRAWNIENIA UDT"]].copy()
    editor_source = people_df.merge(
        saved["forklift"], on="OSOBA", how="left"
    ).fillna({"CZAS WÓZKA (godz.)": 0.0})

    with st.form("bonus_additions_form_" + safe_key, clear_on_submit=False):
        with st.expander("1. Wózek widłowy — godziny na pracownika", expanded=True):
            help_icon(
                BONUS_HELP["forklift"]
                + f"\n\n**Aktualna pula do podziału:** {forklift_pool:,.2f} zł."
            )
            edited_forklift = st.data_editor(
                editor_source,
                column_config={
                    "OSOBA": st.column_config.TextColumn("Pracownik", disabled=True),
                    "UPRAWNIENIA UDT": st.column_config.CheckboxColumn("Uprawnienia UDT", disabled=True),
                    "CZAS WÓZKA (godz.)": st.column_config.NumberColumn(
                        "Godziny (h)", min_value=0.0, max_value=300.0, step=0.5
                    ),
                },
                width="stretch",
                hide_index=True,
                key="forklift_bonus_editor_" + safe_key,
            )

        with st.expander("2. Palety — liczba i uczestnicy podziału", expanded=True):
            help_icon(BONUS_HELP["pallets"])
            pallet_value = st.number_input(
                "Łączna liczba rozładowanych i załadowanych palet",
                value=float(saved["pallets"]),
                min_value=0.0,
                step=1.0,
                help="Wpisz liczbę palet z całego miesiąca. Stawka za paletę jest w Ustawieniach.",
                key="bonus_pallet_total_" + safe_key,
            )
            chosen_people = st.multiselect(
                "Którym pracownikom podzielić premię za palety?",
                options=people,
                default=[p for p in saved["selected"] if p in people],
                help="Kwota puli za palety zostanie podzielona po równo między wybrane osoby.",
                key="bonus_pallet_people_" + safe_key,
            )
            st.caption(f"Stawka za paletę: {pallet_rate:,.2f} zł.")

        with st.expander("3. Premie specjalne — za co i ile", expanded=False):
            help_icon(BONUS_HELP["specials"])
            edited_specials = st.data_editor(
                saved["specials"],
                column_config={
                    "Pracownik": st.column_config.SelectboxColumn(
                        "Pracownik", options=people, required=True
                    ),
                    "Kwota netto premii": st.column_config.NumberColumn(
                        "Kwota (zł)", min_value=0.0, step=50.0, format="%.2f zł"
                    ),
                    "Powód przyznania premii": st.column_config.TextColumn(
                        "Za co przyznana"
                    ),
                    "Kto przyznał": st.column_config.TextColumn("Kto przyznał"),
                },
                num_rows="dynamic",
                width="stretch",
                hide_index=True,
                key="bonus_special_editor_" + safe_key,
            )

        submitted = st.form_submit_button(
            "Zapisz i przelicz dodatki", type="primary", width="stretch"
        )

    if submitted:
        if pallet_value > 0 and not chosen_people:
            st.error("Wybierz co najmniej jednego pracownika do podziału premii za palety.")
        elif (pd.to_numeric(edited_forklift["CZAS WÓZKA (godz.)"], errors="coerce").isna().any()
              or (pd.to_numeric(edited_forklift["CZAS WÓZKA (godz.)"], errors="coerce") < 0).any()):
            st.error("W ewidencji wózka podaj wyłącznie nieujemne liczby godzin.")
        else:
            specials = edited_specials.copy()
            specials = specials.dropna(how="all")
            amounts = pd.to_numeric(specials.get("Kwota netto premii", pd.Series(dtype=float)), errors="coerce")
            invalid = (
                (not specials.empty and (
                    amounts.isna().any() or (amounts < 0).any()
                    or specials["Pracownik"].isna().any()
                    or not specials["Pracownik"].isin(people).all()
                ))
            )
            if invalid:
                st.error("Uzupełnij poprawnie pracownika i kwotę każdej premii specjalnej.")
            else:
                saved.update({
                    "forklift": edited_forklift[["OSOBA", "CZAS WÓZKA (godz.)"]].copy(),
                    "specials": specials,
                    "pallets": float(pallet_value),
                    "selected": list(chosen_people),
                })
                st.session_state.forklift_hours_df = saved["forklift"].copy()
                st.session_state.special_bonuses_df = specials.copy()
                st.session_state.setdefault("_bonus_inputs_confirmed_by_period", {})[period] = True
                st.session_state.pop("_prepared_bonus_slip", None)
                st.toast("Dodatki wprowadzone i przeliczone w bieżącej sesji.", icon="✅")
                st.rerun()

    forklift_hours = float(
        pd.to_numeric(saved["forklift"]["CZAS WÓZKA (godz.)"], errors="coerce")
        .fillna(0.0).sum()
    )
    pallets = float(saved["pallets"])
    selected = [p for p in saved["selected"] if p in people]
    pool = pallets * float(pallet_rate)
    per_person = pool / len(selected) if selected else 0.0

    help_icon(
        "Wartości poniżej pochodzą z **ostatniego zatwierdzenia formularza**. "
        "Samo wpisywanie w tabeli nie zmienia rozliczenia, dopóki nie klikniesz "
        "„Zapisz i przelicz dodatki”."
    )
    a, b, c = st.columns(3)
    a.metric("Wózek · godziny zespołu", f"{forklift_hours:,.1f} h")
    b.metric("Palety · pula dodatków", f"{pool:,.2f} zł")
    c.metric("Palety · kwota na osobę", f"{per_person:,.2f} zł")
    return pallets, selected, forklift_hours, per_person
