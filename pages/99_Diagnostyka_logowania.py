"""Temporary, public-safe configuration check for the TEST app only.

No credential value is printed, logged, or returned to the browser.
Remove this page once rollout validation is complete.
"""
import requests
import streamlit as st

st.set_page_config(page_title="Diagnostyka logowania — TEST", page_icon="🔐")
st.title("Diagnostyka logowania — TEST")
st.caption("Wyłącznie środowisko testowe. Ta strona nie wyświetla kluczy ani danych osobowych.")

try:
    test_url = str(st.secrets.get("TEST_SUPABASE_URL", "")).rstrip("/")
    publishable_key = str(st.secrets.get("TEST_SUPABASE_ANON_KEY", ""))
except (FileNotFoundError, KeyError, OSError):
    test_url, publishable_key = "", ""

url_valid = test_url == "https://bzpfukyugfuybqivjyoz.supabase.co"
key_valid = publishable_key.startswith("sb_publishable_") and len(publishable_key) >= 35

st.write("Adres testowego projektu Supabase:", "✅ Poprawny" if url_valid else "❌ Brak lub błędny")
st.write("Publiczny klucz aplikacji:", "✅ Skonfigurowany" if key_valid else "❌ Brak lub błędny")

if url_valid and key_valid:
    try:
        response = requests.get(
            test_url + "/auth/v1/settings",
            headers={"apikey": publishable_key},
            timeout=10,
        )
        st.write("Połączenie z Supabase Auth:",
                 "✅ Działa" if response.status_code == 200 else "❌ Nie odpowiada poprawnie")
    except requests.RequestException:
        st.write("Połączenie z Supabase Auth: ❌ Błąd sieci")
else:
    st.info("Najpierw zapisz dwa ustawienia w Streamlit Cloud → Secrets.")

st.caption("Diagnostyka nie tworzy kont i nie zapisuje haseł.")
