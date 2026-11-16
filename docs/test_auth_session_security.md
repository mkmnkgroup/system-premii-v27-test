# Test application: authentication and session lifetime

## Current test-only change

- The application uses Supabase Auth and a checked `app_user_profiles` row for authorization.
- An open Streamlit tab retains a server-side access/refresh token pair in `st.session_state`.
- Before token expiry (or after a 401/403), the app exchanges the refresh token for a new pair using the server-side Supabase REST endpoint.
- Refresh tokens are rotated; the old refresh token is replaced. The server verifies the new access token with `/auth/v1/user` and rechecks the active, enabled role before displaying any private page.
- Malformed, revoked, or unavailable refresh responses cause an authenticated workspace to be cleared. Explicit logout revokes the **current** Supabase session.
- Password recovery never imports recovery tokens into normal authenticated sessions.
- Never write Supabase session credentials into URLs, logs, GitHub, localStorage, JavaScript cookies, or public Streamlit components.

**Limitation:** Streamlit's `st.session_state` is attached to the current WebSocket connection. Refreshing the browser tab or starting a separate browser automation session still requires reauthentication. Token rotation does **not** change that, and should never be described as persistent browser login.

## Secure browser-persistent login (not enabled)

To preserve login across browser restarts without weakening authentication, use a real first-party identity cookie managed by Streamlit's supported `st.login` OpenID Connect integration, plus revalidation of application roles and Supabase RLS access.

A potential IdP is Supabase Auth's OAuth 2.1 / OIDC Server, but it requires enabling and configuring OAuth on the **test project**, an authorization UI, an OAuth client, asymmetric JWT keys and credentials stored only in **Streamlit Secrets**. This is a separate migration that must be fully tested before enabling. The old password-based test login remains active until then.

There is intentionally no homemade cookie, hidden login token in query parameters, shared global cache of users, or bypass of role checks.

References:
- https://docs.streamlit.io/develop/api-reference/caching-and-state/st.session_state
- https://docs.streamlit.io/develop/api-reference/user/st.login
- https://supabase.com/docs/guides/auth/sessions
- https://supabase.com/docs/guides/auth/oauth-server/getting-started
