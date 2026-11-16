"""Server-side Supabase Auth token rotation for an *open* Streamlit test session.

Never put access/refresh tokens in URLs, localStorage, or JavaScript cookies.
Streamlit session_state is WebSocket-scoped and does not survive a tab reload.
A separate OIDC flow is required for browser-persistent authentication.
"""
import time

TOKEN_KEYS = (
    "_test_auth_access_token",
    "_test_auth_refresh_token",
    "_test_auth_expires_at",
)


def clear_auth_tokens(state):
    for key in TOKEN_KEYS:
        state.pop(key, None)


def store_auth_tokens(state, response, *, now=None):
    """Validate a complete refreshed Supabase token pair before replacing it."""
    if not isinstance(response, dict):
        return False
    access = response.get("access_token")
    refresh = response.get("refresh_token")
    ttl = response.get("expires_in")
    if (
        not isinstance(access, str) or not 20 <= len(access) <= 16384
        or not isinstance(refresh, str) or not 10 <= len(refresh) <= 4096
        or type(ttl) is not int or not 60 <= ttl <= 86400
    ):
        return False
    expires_at = (time.time() if now is None else now) + ttl
    state["_test_auth_access_token"] = access
    state["_test_auth_refresh_token"] = refresh
    state["_test_auth_expires_at"] = expires_at
    return True


def session_needs_refresh(state, *, now=None, margin_seconds=90):
    """Use current token until nearly expired. Old access-only sessions still work."""
    expiry = state.get("_test_auth_expires_at")
    if isinstance(expiry, (int, float)) and not isinstance(expiry, bool):
        current = time.time() if now is None else now
        return current >= expiry - margin_seconds
    return False


def refresh_auth_tokens(state, requester, *, now=None):
    """Rotate single-use refresh token. Fail closed when Supabase refuses it.

    Requester is a *server-side* Supabase API wrapper; never pass tokens to a
    browser component. Authorization still requires a fresh /user and role
    verification after successful rotation.
    """
    refresh = state.get("_test_auth_refresh_token")
    if not isinstance(refresh, str) or not refresh:
        clear_auth_tokens(state)
        return False
    status, payload = requester(
        "POST", "/auth/v1/token?grant_type=refresh_token",
        data={"refresh_token": refresh},
    )
    if status != 200 or not store_auth_tokens(state, payload, now=now):
        clear_auth_tokens(state)
        return False
    return True
