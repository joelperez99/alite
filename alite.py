import os
import json
import time
import requests
import pandas as pd
from datetime import date
import streamlit as st

# =============================
# Helpers
# =============================

def get_api_key():
    return st.secrets.get("SPORTDB_API_KEY", os.getenv("SPORTDB_API_KEY", ""))

def safe_get(url, headers=None, params=None, timeout=30, tries=3, sleep=0.6):
    last = None
    for _ in range(tries):
        try:
            r = requests.get(url, headers=headers, params=params, timeout=timeout)
            if r.status_code == 200:
                try:
                    return r.json()
                except Exception:
                    return {"_raw_text": r.text}
            else:
                return {
                    "_http_error": True,
                    "status": r.status_code,
                    "reason": r.reason,
                    "body": r.text[:1200] + ("... [truncated]" if len(r.text) > 1200 else "")
                }
        except Exception as e:
            last = str(e)
            time.sleep(sleep)
    return {"_exception": True, "error": last or "unknown"}

def normalize_any(json_obj):
    """Convierte un JSON arbitrario de odds a DataFrame plano.
       Busca keys típicas como events, fixtures, matches, markets, outcomes, prices, odds."""
    if json_obj is None:
        return pd.DataFrame()

    # Si ya es lista de eventos:
    if isinstance(json_obj, list):
        return pd.json_normalize(json_obj, max_level=1)

    # Si viene envuelto:
    for top_key in ["events", "fixtures", "matches", "data", "result", "items", "odds"]:
        if top_key in json_obj and isinstance(json_obj[top_key], list):
            return pd.json_normalize(json_obj[top_key], max_level=2)

    # Como fallback, normaliza todo el objeto
    try:
        return pd.json_normalize(json_obj, max_level=2)
    except Exception:
        return pd.DataFrame([json_obj])

def filter_by_bookmaker(df, book_substr):
    if df.empty or not book_substr:
        return df
    cols = [c for c in df.columns if "book" in c.lower() or "bookmaker" in c.lower() or "house" in c.lower()]
    if not cols:
        # intenta detectar en columnas anidadas
        return df
    mask = False
    for c in cols:
        mask = mask | df[c].astype(str).str.contains(book_substr, case=False, na=False)
    return df[mask]

def filter_tennis(df):
    if df.empty:
        return df
    # intenta ubicar columnas con "sport"
    sport_cols = [c for c in df.columns if "sport" in c.lower() or "category" in c.lower() or "league.sport" in c.lower()]
    if not sport_cols:
        return df
    mask = False
    for c in sport_cols:
        mask = mask | df[c].astype(str).str.contains("tennis", case=False, na=False)
    return df[mask]

# =============================
# Streamlit UI
# =============================
st.set_page_config(page_title="Tenis — Momios (SportDB.dev)", page_icon="🎾", layout="wide")
st.title("🎾 Tenis — Momios de Caliente (vía SportDB.dev)")

with st.sidebar:
    st.subheader("Conexión")
    base_url = st.text_input(
        "Base URL",
        value=os.getenv("SPORTDB_BASE_URL", "https://dashboard.sportdb.dev"),
        help="Ej.: https://dashboard.sportdb.dev o el host de tu tenant"
    )
    endpoint_path = st.text_input(
        "Ruta del endpoint de odds",
        value=os.getenv("SPORTDB_ODDS_ENDPOINT", "/api/odds"),
        help="Ejemplos comunes: /api/odds, /api/tennis/odds, /api/events/odds"
    )
    api_key = st.text_input("API Key (SportDB)", value=get_api_key(), type="password")
    fecha = st.date_input("Fecha", value=date.today())
    casa = st.text_input("Bookmaker (contiene…)", value="Caliente", help="Filtro por nombre; p. ej. Caliente, bet365…")
    run = st.button("Consultar")

st.caption("Tip: guarda tu API key en *Secrets* como `SPORTDB_API_KEY`.")

if not run:
    st.info("Completa los datos y pulsa **Consultar**.")
    st.stop()

if not api_key:
    st.error("Falta tu API key.")
    st.stop()

# =============================
# Llamada al endpoint
# Convención por defecto: GET {base_url}{endpoint}?sport=tennis&date=YYYY-MM-DD
# Si tu cuenta usa otros nombres de parámetros (ej. day, from/to), modifica `params` abajo.
# =============================
params = {
    "sport": "tennis",
    "date": fecha.strftime("%Y-%m-%d"),
}
headers = {
    "Authorization": f"Bearer {api_key}"
}

# Unifica la URL
endpoint_path = "/" + endpoint_path.lstrip("/")
url = base_url.rstrip("/") + endpoint_path

with st.spinner(f"Llamando {url} …"):
    data = safe_get(url, headers=headers, params=params)

# =============================
# Manejo de errores
# =============================
if data.get("_http_error") or data.get("_exception"):
    st.error("No fue posible obtener datos del endpoint.")
    st.code(json.dumps(data, indent=2, ensure_ascii=False))
    st.stop()

# =============================
# Normalización y filtros
# =============================
df = normalize_any(data)

# Si el endpoint devuelve múltiples deportes, filtramos tenis:
df = filter_tennis(df)

# Filtra por casa: busca columnas típicas (book/bookmaker/house)
df = filter_by_bookmaker(df, casa)

# Ordena si hay hora/fecha disponibles
for col in ["start_time", "kickoff", "commence_time", "event_time", "time", "start"]:
    if col in df.columns:
        try:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True).dt.tz_localize(None)
            df = df.sort_values(col)
            break
        except Exception:
            pass

st.subheader("Resultados")
if df.empty:
    st.warning("No se encontraron cuotas con los filtros (revisa endpoint, permisos o el nombre de la casa).")
else:
    st.dataframe(df, use_container_width=True)
    # Descarga
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button("⬇️ Descargar CSV", data=csv, file_name=f"tennis_odds_{casa}_{fecha.isoformat()}.csv")

# Muestra el JSON bruto opcionalmente
with st.expander("Ver JSON (debug)"):
    st.code(json.dumps(data, indent=2, ensure_ascii=False))
