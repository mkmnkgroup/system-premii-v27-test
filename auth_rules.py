"""Pure authorization rules for the isolated test login screen.

All input to these functions must come from server-verified Supabase Auth
responses, never from user-provided form fields or editable user metadata.
"""
ALLOWED_ROLES = frozenset({"admin", "director", "manager", "employee"})


def active_role(user, profiles):
    """Return role only for exactly one enabled, matching profile."""
    if not isinstance(user, dict) or not isinstance(profiles, list):
        return None
    uid = user.get("id")
    if not isinstance(uid, str) or not uid or len(profiles) != 1:
        return None
    profile = profiles[0]
    if not isinstance(profile, dict):
        return None
    if profile.get("user_id") != uid:
        return None
    if profile.get("enabled") is not True:
        return None
    role = profile.get("role")
    return role if role in ALLOWED_ROLES else None


def allowed_module(role, module):
    """Fail closed. All legacy employee/payroll features remain inaccessible."""
    return role == "admin" and module == "test_auth_status"
