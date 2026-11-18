"""Read-only, publication-aligned employee-to-account audit (TEST only).

The same canonical identity, valid roles and active account checks used by the
attendance publication preflight are applied here. This is advisory UI; the
publication endpoint still authorizes and verifies every account server-side.
"""
from uuid import UUID

from monthly_publication import canonical_name

PUBLISH_ROLES = frozenset(("admin", "manager", "employee"))


def normalized_employees(names):
    """Deduplicate a month's schedule rows without inventing employee names."""
    employees = {}
    for raw in names:
        if not isinstance(raw, str) or not raw.strip():
            continue
        name = " ".join(raw.split())
        key = canonical_name(name)
        employees.setdefault(key, name)
    return [employees[key] for key in sorted(employees)]


def _matching_profiles(name, users):
    key = canonical_name(name)
    matched = []
    for item in users:
        if not isinstance(item, dict):
            continue
        value = item.get("employee_id")
        if not isinstance(value, str) or not value.strip():
            continue
        if canonical_name(value) == key:
            matched.append(item)
    return matched


def _valid_uuid(value):
    try:
        UUID(str(value))
        return True
    except (ValueError, TypeError, AttributeError):
        return False


def analyze_account_links(names, users):
    """Return rows, counters, and possible safely-unassigned account choices."""
    if not isinstance(users, list):
        raise ValueError("Lista kont nie jest dostępna.")
    names = normalized_employees(names)
    rows = []
    for name in names:
        candidates = _matching_profiles(name, users)
        active = [
            u for u in candidates
            if u.get("enabled") is True and u.get("role") in PUBLISH_ROLES
        ]
        if len(active) > 1:
            status = "Kilka aktywnych kont"
            linked = None
        elif len(active) == 1 and not _valid_uuid(active[0].get("user_id")):
            status = "Błędne konto"
            linked = None
        elif len(active) == 1:
            status = "Powiązany"
            linked = active[0]
        elif any(u.get("enabled") is not True for u in candidates):
            status = "Konto nieaktywne"
            linked = None
        elif any(u.get("role") not in PUBLISH_ROLES for u in candidates):
            status = "Niedozwolona rola"
            linked = None
        else:
            status = "Brak przypisania"
            linked = None
        rows.append({
            "Pracownik": name,
            "Status": status,
            "Konto": str(linked.get("email") or "") if linked else "—",
            "Rola": str(linked.get("role") or "") if linked else "—",
        })
    available = [
        u for u in users if isinstance(u, dict)
        and u.get("enabled") is True
        and u.get("role") in PUBLISH_ROLES
        and _valid_uuid(u.get("user_id"))
        and (not isinstance(u.get("employee_id"), str)
             or not u["employee_id"].strip())
    ]
    available.sort(key=lambda u: str(u.get("email") or ""))
    total = len(rows)
    linked_count = sum(r["Status"] == "Powiązany" for r in rows)
    return rows, {
        "total": total,
        "linked": linked_count,
        "issues": total - linked_count,
    }, available


def validate_quick_link(name, user_id, names, users):
    """Allow a one-click assignment only to an empty, eligible active account.

    Caller must fetch a fresh admin list immediately before submitting the
    update, never silently overwrite another employee's existing identifier.
    """
    rows, _, available = analyze_account_links(names, users)
    if not any(r["Pracownik"] == name and r["Status"] == "Brak przypisania"
               for r in rows):
        raise ValueError("Przypisanie pracownika uległo zmianie. Odśwież listę.")
    matches = [u for u in available if str(u.get("user_id")) == str(user_id)]
    if len(matches) != 1:
        raise ValueError("Wybrane konto nie jest już wolne i aktywne.")
    return matches[0]

def names_from_attendance_draft(payload, year, month):
    """Get worker identities from the exact saved month to be published."""
    period = f"{int(year):04d}-{int(month):02d}"
    if (not isinstance(payload, dict) or payload.get("format_version") != 1
            or payload.get("period") != period
            or not isinstance(payload.get("entries"), list)
            or not payload["entries"] or len(payload["entries"]) > 1500):
        raise ValueError("Zapisana ewidencja ma nieprawidłowy format.")
    names = []
    for item in payload["entries"]:
        if (not isinstance(item, dict)
                or not isinstance(item.get("employee"), str)
                or not item["employee"].strip()
                or not isinstance(item.get("work_day"), str)
                or len(item["work_day"]) != 10
                or item["work_day"][:7] != period):
            raise ValueError("Nieprawidłowe osoby lub daty w zapisanej ewidencji.")
        names.append(item["employee"])
    return normalized_employees(names)
