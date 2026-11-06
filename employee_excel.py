"""Excel import/export for employee roster, isolated from persistence."""
import io
import pandas as pd

COLUMNS = ("OSOBA", "GRUPA", "SYSTEM", "STANOWISKO", "FUNKCJA", "UPRAWNIENIA UDT")


def validate_employees(frame):
    if not isinstance(frame, pd.DataFrame):
        raise ValueError("Nieprawidłowy arkusz pracowników.")
    frame = frame.copy()
    frame.columns = [str(col).strip().upper() for col in frame.columns]
    missing = [col for col in COLUMNS if col not in frame.columns]
    if missing:
        raise ValueError("Brak wymaganych kolumn: " + ", ".join(missing))
    frame = frame.loc[:, list(COLUMNS)].dropna(how="all")
    if frame.empty:
        raise ValueError("Arkusz nie zawiera pracowników.")
    for col in COLUMNS[:-1]:
        frame[col] = frame[col].fillna("").astype(str).str.strip()
        if frame[col].eq("").any():
            raise ValueError("Puste wartości w kolumnie " + col)
    if frame["OSOBA"].str.casefold().duplicated().any():
        raise ValueError("Powtarzające się nazwiska w kolumnie OSOBA.")
    truthy = {"TAK", "TRUE", "1", "YES", "PRAWDA"}
    falsy = {"NIE", "FALSE", "0", "NO", "FAŁSZ", "FALSZ", ""}
    values = frame["UPRAWNIENIA UDT"].fillna("").astype(str).str.strip().str.upper()
    if (~values.isin(truthy | falsy)).any():
        raise ValueError("UPRAWNIENIA UDT: użyj TAK/NIE lub TRUE/FALSE.")
    frame["UPRAWNIENIA UDT"] = values.isin(truthy)
    return frame.reset_index(drop=True)


def read_employees_excel(file):
    return validate_employees(pd.read_excel(file, sheet_name="Pracownicy", engine="openpyxl"))


def write_employees_excel(frame):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        validate_employees(frame).to_excel(writer, sheet_name="Pracownicy", index=False)
        sheet = writer.sheets["Pracownicy"]
        sheet.freeze_panes = "A2"
        sheet.auto_filter.ref = sheet.dimensions
        for column in sheet.columns:
            letter = column[0].column_letter
            sheet.column_dimensions[letter].width = min(45, max(18, max(len(str(cell.value or "")) for cell in column) + 3))
    return output.getvalue()

