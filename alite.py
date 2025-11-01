import os
import time
import requests
import pandas as pd
from datetime import datetime, date
import streamlit as st

# =============================
# CONFIG
# =============================
OC_PRODUCT = "oddscomparison-prematch"
OC_VERSION = "v2"
LANG = "en"
FMT = "json"
SPORT_TENNIS_ID = "sr:sport:5"  # Tennis ID

def api_key_from_env_or_secrets():
    k = st.secrets.get("SPORTRADAR_API_KEY", None)
    if k:
        return k
    return os.getenv("SPORTRADAR_API_KEY", "")

def build_base_url(access_level):
    return f"https://api.sportradar.com/{OC_PRODUCT}/{access_level}/{OC_VERSION}/{LANG}"

@st.cache_data(ttl=60)
def get_books(access_level, api_key):
    url = f"{build_base_url(access_level)}/books.{FMT}"
    r = requests.get(url, params={"api_key": api_key}, timeout=20)
    r.raise_for_status()
    data = r.json()
    books = data.get("books", [])
    return pd.DataFrame(books)

@st.cache_data(ttl=30)
def get_daily_schedule(access_level, api_key, the_date):
    d = the_date.strftime("%Y-%m-%d")
    url = f"{build_base_url(access_level)}/sports/{SPORT_TENNIS_ID}/schedules/{d}/sport_events.{FMT}"
    r = requests.get(url, params={"api_key": api_key}, timeout=30)
    r.raise_for_status()
    return r.json()

@st.cache_data(ttl=30)
def get_sport_event_markets(access_level, api_key, sport_event_id):
    url = f"{build_base_url(access_level)}/sport_events/{sport_event_id}/sport_event_markets.{FMT}"
    r = requests.get(url, params={"api_key": api_key}, timeout=30)
    r.raise_for_status()
    return r.json()

def extract_match_winner_prices(markets_json, book_id=None, book_name=None):
    rows = []
    markets = markets_json.get("markets", [])
    target_keys = ("match winner", "match_winner", "moneyline", "2way", "2 way")

    for m in markets:
        m_name = (m.get("name") or "").lower()
        if not any(k in m_name for k in target_keys):
            continue

        for book in m.get("books", []):
            b_id = book.get("id")
            b_name = book.get("name", "")

            if book_id and b_id != book_id:
                continue
            if book_name and book_name.lower() not in b_name.lower():
                continue

            for out in book.get("outcomes", []):
                rows.append({
                    "bookmaker": b_name,
                    "outcome": out.get("name"),
                    "decimal_odds": out.get("odds", {}).get("decimal") or out.get("decimal"),
                    "american_odds": out.get("odds", {}).get("american") or out.get("american"),
                })
    return rows

def build_table(schedule_json, access_level, api_key, book_id, book_name):
    events = schedule_json.get("sport_events", [])
    rows = []

    for ev in events[:60]:
        se = ev.get("sport_event", {})
        match_id = se.get("id")

        players = se.get("competitors", [])
        p1 = players[0]["name"] if len(players) > 0 else ""
        p2 = players[1]["name"] if len(players) > 1 else ""
        start_time = se.get("start_time")

        try:
            m = get_sport_event_markets(access_level, api_key, match_id)
            odds = extract_match_winner_prices(m, book_id, book_name)
        except:
            odds = []

        if not odds:
            rows.append({
                "match_id": match_id,
                "start_time": start_time,
                "player1": p1,
                "player2": p2,
                "bookmaker": book_name,
                "outcome": "",
                "decimal_odds": "",
                "american_odds": ""
            })
        else:
            for o in odds:
                rows.append({
                    "match_id": match_id,
                    "start_time": start_time,
                    "player1": p1,
                    "player2": p2,
                    "bookmaker": o["bookmaker"],
                    "outcome": o["outcome"],
                    "decimal_odds": o["decimal_odds"],
                    "american_odds": o["american_odds"]
                })

        time.sleep(0.2)

    return pd.DataFrame(rows)

# =============================
# UI
# =============================
st.set_page_config(page_title="Momios Tenis Caliente", page_icon="🎾")
st.title("🎾 Momios Tenis — Casino Caliente (Sportradar Odds)")

with st.sidebar:
    api_key = st.text_input("Sportradar API Key", api_key_from_env_or_secrets(), type="password")
    access = st.selectbox("Tipo de acceso", ["trial", "production"])
    fecha = st.date_input("Fecha", date.today())
    btn = st.button("Consultar")

if not btn:
    st.info("Ingresa tu API Key y da clic en Consultar")
    st.stop()

if not api_key:
    st.error("Necesitas tu API Key de Sportradar.")
    st.stop()

# Cargar casas
books = get_books(access, api_key)
if books.empty:
    st.error("Tu API key no tiene bookmakers disponibles.")
    st.stop()

# Buscar Caliente
idx = 0
if books["name"].str.contains("caliente", case=False, na=False).any():
    idx = books["name"].str.contains("caliente", case=False).idxmax()

pick = st.selectbox("Casa de apuestas", books["name"].tolist(), index=idx)
book_row = books[books["name"] == pick].iloc[0]
book_id = book_row["id"]

sched = get_daily_schedule(access, api_key, fecha)
df = build_table(sched, access, api_key, book_id, pick)

st.subheader("Resultados")
st.dataframe(df)

csv = df.to_csv(index=False).encode("utf-8")
st.download_button("Descargar CSV", data=csv, file_name="tennis_odds.csv")
