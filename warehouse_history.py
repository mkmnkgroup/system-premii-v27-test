"""Warehouse trend metrics and fair client-category cost attribution.

Monthly archive is the sole source. Missing history is never treated as zero.
Client-group allocations are scenario shares, not client-caused payroll costs.
"""
from __future__ import annotations

import calendar
from collections import defaultdict

import pandas as pd

from client_group_analysis import estimated_main_bonus_allocation

MONTHS = {
    name: i for i, name in enumerate((
        "Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec",
        "Lipiec", "Sierpień", "Wrzesień", "Październik", "Listopad", "Grudzień"
    ), 1)
}
MAIN = "Premia (zł)"
TOTAL = "ŁĄCZNA PREMIA / DODATKI (zł)"
OVERTIME = "Nadgodziny (godz.)"


def month_key(period):
    bits = str(period).strip().split()
    if len(bits) != 2 or bits[0] not in MONTHS or not bits[1].isdigit():
        return None
    year = int(bits[1])
    if not 2000 <= year <= 2100:
        return None
    return year, MONTHS[bits[0]]


def _number(value):
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not pd.notna(number) or number == float("inf") or number == float("-inf"):
        return None
    return number


def monthly_history(history):
    """Produce chronological read-only monthly KPI rows from saved archives."""
    output = []
    for label, snapshot in history.items():
        pair = month_key(label)
        if pair is None or not isinstance(snapshot, dict):
            continue
        metrics = snapshot.get("metrics")
        frame = snapshot.get("summary")
        if not isinstance(metrics, dict) or not isinstance(frame, pd.DataFrame):
            continue
        def sum_field(column):
            if column not in frame:
                return None
            series = pd.to_numeric(frame[column], errors="coerce")
            return float(series.sum()) if series.notna().all() else None
        total_cost, main_bonus, overtime = (
            sum_field(TOTAL), sum_field(MAIN), sum_field(OVERTIME)
        )
        sales = _number(metrics.get("sales_eur_net"))
        positions = _number(metrics.get("lines"))
        pieces = _number(metrics.get("pcs"))
        mass = _number(metrics.get("weight"))
        output.append({
            "period": label, "year": pair[0], "month": pair[1],
            "date": f"{pair[0]:04d}-{pair[1]:02d}",
            "positions": positions, "pieces": pieces, "weight_kg": mass,
            "sales_eur_net": sales, "pallets": _number(metrics.get("pallets")),
            "main_bonus_pln": main_bonus, "total_cost_pln": total_cost,
            "overtime_h": overtime,
            "cost_pln_per_1000_positions": (
                1000 * total_cost / positions
                if total_cost is not None and positions and positions > 0 else None
            ),
            "cost_pln_per_1000_eur": (
                1000 * total_cost / sales
                if total_cost is not None and sales and sales > 0 else None
            ),
            "client_groups_available": bool(
                isinstance(metrics.get("client_group_workload"), dict)
                and metrics["client_group_workload"].get("groups")
            ),
        })
    return sorted(output, key=lambda r: (r["year"], r["month"]))


def _bucket(year, month, frequency):
    if frequency == "year":
        return str(year), 12
    if frequency == "half":
        return f"{year} / P{1 if month <= 6 else 2}", 6
    if frequency == "quarter":
        return f"{year} / Q{(month - 1) // 3 + 1}", 3
    raise ValueError("Nieobsługiwany rodzaj okresu.")


def grouped_history(rows, frequency):
    """Aggregations carry coverage; missing values never become artificial 0."""
    groups = defaultdict(list)
    for row in rows:
        name, _ = _bucket(row["year"], row["month"], frequency)
        groups[name].append(row)
    result = []
    for period, subset in sorted(groups.items()):
        needed = _bucket(subset[0]["year"], subset[0]["month"], frequency)[1]
        unique_months = len({(r["year"], r["month"]) for r in subset})
        record = {
            "period": period, "recorded_months": unique_months,
            "expected_months": needed, "complete": unique_months == needed,
        }
        for key in ("positions", "pieces", "weight_kg", "sales_eur_net",
                    "pallets", "main_bonus_pln", "total_cost_pln", "overtime_h"):
            values = [_number(r.get(key)) for r in subset]
            record[key] = sum(values) if all(v is not None for v in values) else None
        positions, total, sales = record["positions"], record["total_cost_pln"], record["sales_eur_net"]
        record["cost_pln_per_1000_positions"] = (
            total / positions * 1000 if total is not None and positions and positions > 0 else None
        )
        record["cost_pln_per_1000_eur"] = (
            total / sales * 1000 if total is not None and sales and sales > 0 else None
        )
        result.append(record)
    return result


def history_client_groups(history, labels):
    """Aggregate eligible group workload across months with source group data."""
    summaries, missing = defaultdict(lambda: defaultdict(float)), []
    sales_ok = True
    tracked_months = 0
    for label in labels:
        snapshot = history.get(label, {})
        metrics = snapshot.get("metrics", {}) if isinstance(snapshot, dict) else {}
        workload = metrics.get("client_group_workload") if isinstance(metrics, dict) else None
        if not isinstance(workload, dict) or not workload.get("groups"):
            missing.append(label)
            continue
        summary = snapshot.get("summary")
        if not isinstance(summary, pd.DataFrame) or MAIN not in summary:
            missing.append(label)
            continue
        monthly_main = pd.to_numeric(summary[MAIN], errors="coerce")
        if monthly_main.isna().any():
            missing.append(label)
            continue
        attributed = estimated_main_bonus_allocation(workload, float(monthly_main.sum()))
        tracked_months += 1
        sales_ok = sales_ok and bool(workload.get("value_complete"))
        for item in attributed:
            name = item["group"]
            output = summaries[name]
            for key in ("positions", "pieces", "weight_kg", "allocated_main_bonus_pln"):
                output[key] += float(item.get(key) or 0)
            if item.get("sales_eur_net") is not None:
                output["sales_eur_net"] += float(item["sales_eur_net"])
    result = []
    totals = {key: sum(g.get(key, 0) for g in summaries.values())
              for key in ("positions", "pieces", "weight_kg", "sales_eur_net", "allocated_main_bonus_pln")}
    for name, record in summaries.items():
        row = {"group": name}
        for key in totals:
            row[key] = record.get(key, 0) if key != "sales_eur_net" or sales_ok else None
            row["share_" + key] = (
                (record.get(key, 0) / totals[key]) if totals[key] > 0
                else None
            ) if key != "sales_eur_net" or sales_ok else None
        result.append(row)
    return {
        "groups": sorted(result, key=lambda x: x["positions"], reverse=True),
        "missing": missing,
        "months_with_groups": tracked_months,
        "sales_complete": sales_ok and bool(tracked_months),
        "totals": totals,
    }
