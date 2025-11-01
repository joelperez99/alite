import os
import time
import json
import requests
import pandas as pd
from datetime import date
import streamlit as st

# =============================
# CONFIG
# =============================
OC_PRODUCT = "oddscomparison-prematch"   # v2 pre-match
OC_VERSION = "v2"
LANG = "en"
FMT = "json"
SPORT_TENNIS_ID = "sr:sport:5"          # Tennis

# ------- util HTTP con reintentos y errores claros -------
def http_get(url, params, timeout=25, max_tries=3, sleep_sec=0.8):
    last_exc = None
    for i in range(max_tries):
        try:
            r = requests.get(url, params=params, timeout=timeout)
            if r.status_code == 200:
                # intenta JSON, si no, devuelve texto
                try:
                    return r.json()
                except Exception:
                    return {"_raw_text": r.text}
            else:
                # no levantes excepción; regresa dict con error
                payload = r.text
                # truncar para UI
                if payload and len(payload) > 800:
                    payload = payload[:800] + "... [truncated]"
                return {
                    "_http_error": True,
                    "status_code": r.status_code,
                    "reason": r.reason,
                    "body": payload
                }
        except Exception as e:
            last_exc = e
            time.sleep(sleep_sec)
    # si nunca hubo respuesta válida:
    return {"_exception": True, "error": str(last_exc)}

def api_key_from_env_or_secrets():
    return st.secrets.get("SPORTRADAR_API_KEY", os.getenv("SPORTRADAR_API_KEY", ""))

def base_url(access_level):
    return f"https://api.sportradar.com/{OC_PRODUCT}/{access_level}/{OC_VERSION}/{LANG}"

@st.cache_data(ttl=30)
def get_daily_schedule(access_level, api_key, the_date):
    day = the_date.strftime("%Y-%m-%d")
    url = f"{base_url(access_level)}/sports/{SPORT_TENNIS_ID}/schedules/{day}/sport_events.{FMT}"
    return http_get(url, {"api_key": api_key})

@st.cache_data(ttl=30)
def get_sport_event_markets(access_level, api_key, sport_event_id):
    url = f"{base_url(access_level)}/sport_events/{sport_event_id}/sport_event_markets.{FMT}"
    return http_get(url, {"api_key": api_key})

def extract_match_winner_prices(markets_json, book_name_substr=None, book_id=None):
    rows = []
    if markets_json.get("_http_error") or markets_json.get("_exception"):
        return rows  # ya se reportará aparte

    markets = markets_json.get("markets", [])
    target_keys = ("match winner", "match_winner", "moneyline", "2way", "2 way")

    for m in markets:
        mname = (m.get("name") or "").lower()
        if not any(k in mname for k in target_keys):
            continue

        for book in m.get("books", []):
            b_id = book.get("id")
            b_name = book.get("name", "")

            if book_id and b_id != book_id:
                continue
            if book_name_substr and book_name_substr.lower() not in b_name.lower():
                continue

            for out in book.get("outcomes", []):
                dec = (out.get("odds") or {}).get("decimal")
                if dec is None:
                    dec = out.get("decimal")
                am = (out.get("odds") or {}).get("american")
                if am is None:
                    am = out.get("american")
                rows.append({
                    "bookmaker": b_name,
                    "outcome": out.get("name"),
                    "decimal_odds": dec,
                    "american_odds": am,
                })
    return rows

def build_table(schedule_json, access_level, api_key, book_name_substr, book_id=None, max_events=60):
    rows, errors = [], []

    if schedule_json.get("_http_error") or schedule_json.get("_exception"):
        return pd.DataFrame(rows), [("schedule", schedule_json)]

    events = schedule_json.get("sport_events", [])
    for ev in events[:max_events]:
        se = ev.get("sport_event", {})
        match_id = se.get("id")
        comps = se.get("competitors", [])
        p1 = comps[0]["name"] if len(comps) > 0 else ""
        p2 = comps[1]["name"] if len(comps) > 1 else ""
        start_time = se.get("start_time")

        markets = get_sport_event_markets(access_level, api_key, match_id)
        if markets.get("_http_error") or markets.get("_exception"):
            errors.append((match_id, markets))
            continue

        odds = extract_match_winner_prices(markets, book_name_substr=book_name_substr, book_id=book_id)
        if not odds:
            rows.append({
                "match_id": match_id, "start_time": start_time,
                "player1": p1, "player2": p2,
                "bookmaker": book_name_substr, "outcome": "",
                "decimal_odds": "", "american_odds": ""
            })
        else:
            for o in odds:
                rows.append({
                    "match_id": match_id, "start_time": start_time,
                    "player1": p1, "player2": p2,
                    "bookmaker": o["bookmaker"], "outcome": o["outcome"],
                    "decimal_odds": o["decimal_odds"], "american_odds": o["american_odds"]
                })

        time.sleep(0.18)  # conserva margen para el rate limit
    return pd.DataFrame(rows), errors

# =============================
# UI
# =============================
st.set_page_config(page_title="Momios Tenis Caliente", page_icon="🎾", layout="wide")
st.title("🎾 Momios Tenis — Sportradar (filtrado por casa)")

with st.sidebar:
    api_key = st.text_input("Sportradar API Key", api_key_from_env_or_secrets(), type="password")
    access = st.selectbox("Access level", ["trial", "production"])
    fecha = st.date_input("Fecha", date.today())
    book_name = st.text_input("Casa (contiene…)", "Caliente",
                              help="Filtra por coincidencia del nombre. Ej: Caliente, bet365, Pinnacle…")
    run = st.button("Consultar")

if not run:
    st.info("Ingresa tu API key, escribe 'Caliente' y pulsa Consultar.")
    st.stop()

if not api_key:
    st.error("Falta tu API key.")
    st.stop()

with st.spinner(f"Cargando agenda {fecha.isoformat()}…"):
    schedule = get_daily_schedule(access, api_key, fecha)

table, errs = build_table(schedule, access, api_key, book_name_substr=book_name, book_id=None, max_events=80)

st.subheader("Resultados")
if table.empty:
    st.warning("No hay cuotas 'Match Winner' para esa casa o fecha.")
else:
    table = table.sort_values("start_time")
    st.dataframe(table, use_container_width=True)
    csv = table.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV", data=csv, file_name=f"tennis_odds_{book_name}_{fecha.isoformat()}.csv")

# Debug visible y útil
if errs or schedule.get("_http_error") or schedule.get("_exception"):
    st.divider()
    st.markdown("### ⚠️ Detalles técnicos (debug)")
    if schedule.get("_http_error") or schedule.get("_exception"):
        st.write({"schedule_error": schedule})
    for mid, e in errs:
        st.write({"match_id": mid, "error": e})
