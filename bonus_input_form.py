"""One-action, period-scoped input form for warehouse bonus additions.

Streamlit forms batch widget edits: expensive production analysis only reruns
after "Zapisz i przelicz dodatki", not after each typed cell.
"""
import pandas as pd
import streamlit as st


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

    st.markdown("---")
    st.subheader("3–5. Dodatki do premii")
    st.info(
        "Uzupełnij wszystkie trzy części formularza. Zmiany nie są liczone "
        "przy każdym wpisanym znaku — użyj przycisku **Zapisz i przelicz dodatki**."
    )
    safe_key = _safe_period_id(period)

    people_df = employees_df[["OSOBA", "UPRAWNIENIA UDT"]].copy()
    editor_source = people_df.merge(
        saved["forklift"], on="OSOBA", how="left"
    ).fillna({"CZAS WÓZKA (godz.)": 0.0})

    with st.form("bonus_additions_form_" + safe_key, clear_on_submit=False):
        with st.expander("1. Wózek widłowy — godziny na pracownika", expanded=True):
            st.caption(
                f"Wpisz faktyczne godziny. Pula {forklift_pool:,.2f} zł "
                "zostanie podzielona proporcjonalnie do sumy godzin zespołu."
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
                use_container_width=True,
                hide_index=True,
                key="forklift_bonus_editor_" + safe_key,
            )

        with st.expander("2. Palety — liczba i uczestnicy podziału", expanded=True):
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
            st.caption(
                "Dodaj wiersz dla każdej nagrody. Pracownik zobaczy kwotę i powód przyznania."
            )
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
                use_container_width=True,
                hide_index=True,
                key="bonus_special_editor_" + safe_key,
            )

        submitted = st.form_submit_button(
            "Zapisz i przelicz dodatki", type="primary", use_container_width=True
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
                st.session_state.pop("_prepared_bonus_slip", None)
                st.toast("Dodatki zapisane i przeliczone.", icon="✅")
                st.rerun()

    forklift_hours = float(
        pd.to_numeric(saved["forklift"]["CZAS WÓZKA (godz.)"], errors="coerce")
        .fillna(0.0).sum()
    )
    pallets = float(saved["pallets"])
    selected = [p for p in saved["selected"] if p in people]
    pool = pallets * float(pallet_rate)
    per_person = pool / len(selected) if selected else 0.0

    st.caption(
        "Obowiązujące w rozliczeniu wartości (po ostatnim zapisaniu formularza):"
    )
    a, b, c = st.columns(3)
    a.metric("Wózek · godziny zespołu", f"{forklift_hours:,.1f} h")
    b.metric("Palety · pula dodatków", f"{pool:,.2f} zł")
    c.metric("Palety · kwota na osobę", f"{per_person:,.2f} zł")
    return pallets, selected, forklift_hours, per_person
