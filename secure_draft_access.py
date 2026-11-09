"""Fail-closed authorization for test-only draft storage.

This module is deliberately NOT wired into the public Streamlit preview until
OIDC authentication and TEST_DATABASE_URL are configured. Never use the
production DATABASE_URL for test drafts.
"""


class DraftAccessDenied(PermissionError):
    pass


def authorized_identity(user, allowed_emails):
    """Return normalized verified OIDC email or deny access.

    The caller must supply claims from Streamlit's server-validated st.user,
    not user-entered text or arbitrary request headers.
    """
    if not getattr(user, "is_logged_in", False):
        raise DraftAccessDenied("Zaloguj się, aby korzystać z zapisu danych.")
    email = str(getattr(user, "email", "") or "").strip().casefold()
    allowed = {str(item).strip().casefold() for item in allowed_emails if str(item).strip()}
    if not email or not allowed or email not in allowed:
        raise DraftAccessDenied("Brak uprawnień do danych testowych.")
    return email


def isolated_test_connection(test_database_url, expected_project_ref="bzpfukyugfuybqivjyoz"):
    """Reject absent/misconfigured connections before a database operation.

    For URL-style PostgreSQL DSNs, validate the Supabase hostname. For libpq
    key/value DSNs, require an explicit project-specific host as well.
    """
    from psycopg.conninfo import conninfo_to_dict
    if not test_database_url:
        raise DraftAccessDenied("Brak konfiguracji testowej bazy danych.")
    try:
        info = conninfo_to_dict(test_database_url)
    except Exception:
        raise DraftAccessDenied("Nieprawidłowa konfiguracja testowej bazy danych.") from None
    host = str(info.get("host", "")).lower()
    user = str(info.get("user", ""))
    if expected_project_ref not in host or not host.endswith(".supabase.co") or user in {"postgres", "supabase_admin", "service_role"}:
        raise DraftAccessDenied("Połączenie nie wskazuje na wydzieloną bazę testową z ograniczoną rolą.")
    return test_database_url
