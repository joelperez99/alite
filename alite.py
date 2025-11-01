import os
import time
import json
import math
import requests
import pandas as pd
from datetime import datetime, date
import streamlit as st

# ========= CONFIG BÁSICA =========
# Preferimos Odds Comparison Prematch v2 (pre-match) para estabilidad.
OC_PRODUCT = "oddscomparison-prematch"   # también existen: oddscomparison-liveodds, oddscomparison-regular (v1)
OC_VERSION = "v2"
LANG = "en"   # 'en' o 'es' (docs usan 'en' por defecto)
FMT = "json"  # 'json' o 'xml'
SPORT_TENNIS_ID = "sr:sport:5"  # Tennis en SR IDs.  
- **Rutas y endpoints usados:**
  - **Daily Sport Event Schedules**: lista partidos con odds para un deporte y fecha. :contentReference[oaicite:4]{index=4}
  - **Sport Event Markets**: mercados y cuotas por partido (filtramos “Match Winner”). :contentReference[oaicite:5]{index=5}
  - **ID del deporte (tenis)**: `sr:sport:5`. :contentReference[oaicite:6]{index=6}

¿Quieres que adapte la app para **cuotas en vivo** (Live Odds v2) o que agregue mercados alternos (totales, hándicap, set ganador)? Puedo dejártelo ya integrado.
::contentReference[oaicite:7]{index=7}
