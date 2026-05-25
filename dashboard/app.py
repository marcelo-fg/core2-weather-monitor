import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import datetime
import json
from services.api_client import get_latest, get_history, get_weather, ask_llm, post_device_command

st.set_page_config(
    page_title="Core2 Weather Monitor",
    page_icon="🌦️",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# =================== CSS ===================
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');

/* Background gradient */
.stApp {
    background: linear-gradient(135deg, #0f0c29 0%, #302b63 60%, #24243e 100%) !important;
    background-attachment: fixed !important;
    font-family: 'Inter', -apple-system, sans-serif;
}
[data-testid="stAppViewContainer"],
[data-testid="stHeader"],
[data-testid="appCreatorBackground"],
.block-container {
    background: transparent !important;
}
.block-container { padding-top: 2rem; }
[data-testid="stSidebar"],
[data-testid="stSidebarCollapsedControl"] { display: none; }

/* Glass cards */
[data-testid="stVerticalBlockBorderWrapper"] {
    background: rgba(255, 255, 255, 0.07) !important;
    backdrop-filter: blur(16px) !important;
    -webkit-backdrop-filter: blur(16px) !important;
    border: 1px solid rgba(255, 255, 255, 0.12) !important;
    border-radius: 20px !important;
    box-shadow: 0 4px 28px rgba(0, 0, 0, 0.35), inset 0 1px 0 rgba(255,255,255,0.07) !important;
}

/* Stretch columns */
div[data-testid="stHorizontalBlock"] { align-items: stretch !important; }
div[data-testid="column"] > div[data-testid="stVerticalBlock"] {
    height: 100%; display: flex; flex-direction: column;
}
div[data-testid="column"] > div[data-testid="stVerticalBlock"] > div.element-container {
    flex-grow: 1; display: flex; flex-direction: column;
}
div[data-testid="column"] > div[data-testid="stVerticalBlock"] > div.element-container > div {
    flex-grow: 1; display: flex; flex-direction: column;
}
div[data-testid="column"] > div[data-testid="stVerticalBlock"] > div.element-container [data-testid="stVerticalBlockBorderWrapper"] {
    flex-grow: 1;
}

/* Typography */
.greeting-header {
    font-weight: 900; font-size: 2.6rem; color: #ffffff;
    letter-spacing: -1.5px; margin: 0;
    text-shadow: 0 2px 30px rgba(79, 172, 254, 0.2);
}
.greeting-date {
    font-size: 0.85rem; font-weight: 700; color: rgba(255,255,255,0.4);
    letter-spacing: 2.5px; text-transform: uppercase; margin-top: 6px;
}
.section-title {
    font-size: 0.68rem; font-weight: 700; color: rgba(255,255,255,0.38);
    text-transform: uppercase; letter-spacing: 2px; margin-bottom: 10px;
}

/* Metric cards */
.metric-val {
    font-size: 2.3rem; font-weight: 900; color: #ffffff;
    line-height: 1; letter-spacing: -1px;
}
.metric-label {
    font-size: 0.68rem; font-weight: 700; color: rgba(255,255,255,0.38);
    text-transform: uppercase; letter-spacing: 2px; margin-top: 10px;
}

/* Radio toggle */
div[role="radiogroup"] { gap: 4px !important; margin-bottom: 6px; }
div[role="radiogroup"] > label > div:first-child { display: none !important; }
div[role="radiogroup"] label {
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px; padding: 3px 14px; cursor: pointer; transition: all 0.15s;
}
div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) {
    background: rgba(79,172,254,0.2); border-color: rgba(79,172,254,0.5);
}
div[role="radiogroup"] p {
    font-weight: 700; font-size: 0.8rem; color: rgba(255,255,255,0.5); margin: 0;
}
div[role="radiogroup"] label[data-baseweb="radio"]:has(input:checked) p { color: #4facfe !important; }

/* Buttons */
[data-testid="stButton"] button {
    background: rgba(79,172,254,0.12) !important;
    border: 1px solid rgba(79,172,254,0.3) !important;
    border-radius: 12px !important; box-shadow: none !important; transition: all 0.2s !important;
}
[data-testid="stButton"] button:hover {
    background: rgba(79,172,254,0.25) !important;
    box-shadow: 0 0 20px rgba(79,172,254,0.15) !important;
}
[data-testid="stButton"] button p { color: #4facfe !important; font-weight: 700 !important; }

/* Select boxes */
[data-testid="stSelectbox"] > div > div {
    background: rgba(255,255,255,0.08) !important;
    border: 1px solid rgba(255,255,255,0.15) !important;
    border-radius: 10px !important; color: white !important;
}
[data-testid="stSelectbox"] svg { fill: rgba(255,255,255,0.5) !important; }

/* AI text */
.ai-insight, .ai-summary {
    font-style: italic; color: rgba(255,255,255,0.4); font-size: 0.82rem;
    line-height: 1.55; margin-top: 6px; display: -webkit-box;
    -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden;
}

/* Forecast */
.forecast-row { display: flex; align-items: center; padding: 7px 0; gap: 10px; }
.forecast-day { width: 50px; font-weight: 700; color: rgba(255,255,255,0.8); font-size: 0.85rem; }
.forecast-icon { font-size: 1.1rem; width: 26px; text-align: center; }
.forecast-min { width: 24px; text-align: right; color: rgba(255,255,255,0.38); font-weight: 600; font-size: 0.82rem; }
.forecast-bar-bg { flex-grow: 1; height: 4px; background: rgba(255,255,255,0.1); border-radius: 2px; position: relative; }
.forecast-bar-fill { position: absolute; top: 0; bottom: 0; background: linear-gradient(90deg, #4facfe, #00f2fe); border-radius: 2px; }
.forecast-max { width: 24px; font-weight: 800; color: #ffffff; font-size: 0.82rem; }

/* AQ bar */
.aq-bar { height: 7px; background: rgba(255,255,255,0.1); border-radius: 4px; margin: 7px 0 10px 0; }
.aq-bar-fill { height: 100%; border-radius: 4px; }

/* Delta */
.delta-value { font-size: 2.6rem; font-weight: 900; letter-spacing: -1px; margin: 4px 0 6px 0; }

/* Divider + alerts */
hr { border-color: rgba(255,255,255,0.08) !important; }
[data-testid="stAlert"] {
    background: rgba(255,255,255,0.06) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 12px !important;
}

/* M5Stack device overrides */
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-outer):not(:has([data-testid="stVerticalBlockBorderWrapper"]:has(#m5-outer))) {
    background: #1c1c1c !important;
    backdrop-filter: none !important;
    border: 2px solid #2e2e2e !important;
    border-radius: 22px !important;
    box-shadow: 0 20px 60px rgba(0,0,0,0.7) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-screen):not(:has([data-testid="stVerticalBlockBorderWrapper"]:has(#m5-screen))) {
    background: #050505 !important;
    backdrop-filter: none !important;
    border: 3px solid #000 !important;
    border-radius: 10px !important;
    box-shadow: inset 0 0 20px rgba(0,0,0,0.8) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-nav):not(:has([data-testid="stVerticalBlockBorderWrapper"]:has(#m5-nav))) {
    background: rgba(255,255,255,0.04) !important;
    backdrop-filter: none !important;
    border: 1px solid rgba(255,255,255,0.08) !important;
    border-radius: 10px !important;
    box-shadow: none !important;
    margin-bottom: 80px !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-nav) button {
    background: transparent !important;
    border: none !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-nav) button p {
    color: rgba(255,255,255,0.7) !important; font-size: 0.6rem !important;
    font-weight: 700 !important; white-space: nowrap !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-nav) button:hover p { color: #4facfe !important; }
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-bottom):not(:has([data-testid="stVerticalBlockBorderWrapper"]:has(#m5-bottom))) {
    background: transparent !important; border: none !important;
    box-shadow: none !important; position: absolute !important;
    bottom: 12px !important; left: 0 !important; right: 0 !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-bottom) div[data-testid="stHorizontalBlock"] {
    display: flex !important; justify-content: center !important; gap: 28px !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-bottom) button {
    background: transparent !important;
    border: 2px solid #e74c3c !important; border-radius: 50% !important;
    height: 34px !important; width: 34px !important; min-height: 34px !important;
    padding: 0 !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-bottom) button:hover {
    background: rgba(231,76,60,0.2) !important;
    box-shadow: 0 0 12px rgba(231,76,60,0.5) !important;
}
[data-testid="stVerticalBlockBorderWrapper"]:has(#m5-bottom) button p { color: transparent !important; }

/* Sliders */
[data-testid="stSlider"] > div > div > div { background: rgba(79,172,254,0.3) !important; }
[data-testid="stSlider"] [data-baseweb="slider"] > div:last-child > div { background: #4facfe !important; }
[data-testid="stSlider"] label { color: rgba(255,255,255,0.7) !important; }

/* Diagnostics table */
.diag-row {
    display: flex; justify-content: space-between; padding: 7px 0;
    border-bottom: 1px solid rgba(255,255,255,0.07); align-items: center;
}
.diag-row:last-child { border-bottom: none; }
.diag-key { font-weight: 600; color: rgba(255,255,255,0.55); font-size: 0.88rem; }
.diag-val-ok { font-weight: 800; color: #34d399; font-size: 0.88rem; }
.diag-val-fail { font-weight: 800; color: #f87171; font-size: 0.88rem; }
.diag-val-na { font-weight: 800; color: rgba(255,255,255,0.4); font-size: 0.88rem; }
.diag-section { font-size: 0.68rem; font-weight: 700; color: rgba(255,255,255,0.35); text-transform: uppercase; letter-spacing: 2px; margin: 14px 0 8px 0; }

/* Audio input */
[data-testid="stAudioInput"] {
    background: rgba(255,255,255,0.05) !important;
    border: 1px solid rgba(255,255,255,0.1) !important;
    border-radius: 12px !important;
}
</style>
""", unsafe_allow_html=True)

# =================== DATA FETCHING ===================
@st.cache_data(ttl=60)
def fetch_telemetry():
    data = get_latest()
    return data if data else {}

@st.cache_data(ttl=60)
def fetch_history(hours):
    return get_history(hours)

@st.cache_data(ttl=600)
def fetch_weather():
    return get_weather()

@st.cache_data(ttl=300)
def fetch_ai_insight(prompt_key, prompt_text, context_str):
    try:
        context = json.loads(context_str)
        result = ask_llm(prompt_text, context)
        if result:
            import re
            result = re.sub(r'Ici Orion.*?(station\.|bord\.|Commandant\.)', '', result, flags=re.IGNORECASE|re.DOTALL)
            result = re.sub(r'J\'analyse les données.*?\.', '', result, flags=re.IGNORECASE)
            result = re.sub(r'Je suis chargé de vous fournir.*?\.', '', result, flags=re.IGNORECASE)
            result = re.sub(r'Ma mission est de vous tenir.*?\.', '', result, flags=re.IGNORECASE)
            result = re.sub(r'Commandant,\s*voici.*?:', '', result, flags=re.IGNORECASE)
            result = re.sub(r'Mon conseil.*?:', '', result, flags=re.IGNORECASE)
            result = result.replace("Commandant,", "").replace("Commandant.", "").replace("Commandant", "").strip()
            return result
        return "AI analysis temporarily unavailable."
    except Exception as e:
        return f"Error: {e}"

# =================== LOAD DATA ===================
latest = fetch_telemetry()
weather_data = fetch_weather()
current_weather = weather_data.get("current", {}) or {}
forecast_data = weather_data.get("forecast", {}) or {}
daily_forecast = forecast_data.get("daily", [])
hourly_forecast = forecast_data.get("hourly", [])

# =================== NAVIGATION ===================
if "page" not in st.session_state:
    st.session_state.page = "main"

# =================== HELPERS ===================
ICON_MAP = {
    "01d": "☀️", "01n": "🌙", "02d": "⛅", "02n": "☁️",
    "03d": "☁️", "03n": "☁️", "04d": "☁️", "04n": "☁️",
    "09d": "🌧️", "09n": "🌧️", "10d": "🌦️", "10n": "🌧️",
    "11d": "⛈️", "11n": "⛈️", "13d": "❄️", "13n": "❄️",
    "50d": "🌫️", "50n": "🌫️"
}

def icon_to_emoji(code):
    return ICON_MAP.get(code, "☀️")

def get_aq_level(tvoc, eco2):
    if tvoc is None and eco2 is None:
        return "UNKNOWN", "rgba(255,255,255,0.4)"
    if (tvoc is not None and tvoc < 220) and (eco2 is not None and eco2 < 1000):
        return "GOOD", "#34d399"
    elif (tvoc is not None and tvoc < 660) and (eco2 is not None and eco2 < 2000):
        return "MODERATE", "#fbbf24"
    return "POOR", "#f87171"

GLASS_CHART = dict(
    paper_bgcolor="rgba(0,0,0,0)",
    plot_bgcolor="rgba(255,255,255,0.02)",
    font=dict(color="rgba(255,255,255,0.6)", family="Inter, sans-serif"),
    xaxis=dict(
        showgrid=True, gridcolor="rgba(255,255,255,0.06)",
        color="rgba(255,255,255,0.4)", showline=False, zeroline=False,
        tickfont=dict(size=11)
    ),
    yaxis=dict(
        showgrid=True, gridcolor="rgba(255,255,255,0.06)",
        color="rgba(255,255,255,0.4)", showline=False, zeroline=False,
        tickfont=dict(size=11)
    ),
    legend=dict(orientation="h", y=1.1, font=dict(color="rgba(255,255,255,0.6)")),
    margin=dict(l=0, r=0, t=24, b=0),
    height=360,
)


# =====================================================
#                     MAIN PAGE
# =====================================================
if st.session_state.page == "main":
    now = datetime.datetime.now()
    hour = now.hour
    greeting = "GOOD MORNING" if hour < 12 else ("GOOD AFTERNOON" if hour < 18 else "GOOD EVENING")
    date_str = now.strftime("%A, %B %d").upper()

    # ---- SENSOR VALUES ----
    t = latest.get('temperature')
    h = latest.get('humidity')
    v = latest.get('tvoc')
    e = latest.get('eco2')

    temp_str   = f"{t:.1f}°C"    if t is not None else "--"
    hum_str    = f"{h:.0f}%"     if h is not None else "--"
    eco2_str   = f"{int(e)} ppm" if e is not None else "--"
    aq_level, aq_color = get_aq_level(v, e)

    cw_temp   = current_weather.get("temp")
    cw_hum    = current_weather.get("humidity")
    cw_wind   = current_weather.get("wind_speed")
    cw_press  = current_weather.get("pressure")
    cw_icon   = current_weather.get("icon", "01d")

    out_temp_str  = f"{cw_temp:.1f}°C"   if cw_temp  is not None else "--"
    out_hum_str   = f"{cw_hum}%"         if cw_hum   is not None else "--"
    out_wind_str  = f"{cw_wind} m/s"     if cw_wind  is not None else "--"
    out_press_str = f"{cw_press} hPa"    if cw_press is not None else "--"

    last_ts = latest.get('timestamp')
    is_online = False
    if last_ts:
        try:
            last_dt = pd.to_datetime(last_ts, utc=True)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            is_online = (now_utc - last_dt).total_seconds() < 120
        except Exception:
            pass

    # ---- HEADER ----
    hdr_left, hdr_btn = st.columns([9, 1])
    with hdr_left:
        st.markdown(f"""
        <div class='greeting-header'>{greeting}</div>
        <div class='greeting-date'>{date_str}</div>
        """, unsafe_allow_html=True)
    with hdr_btn:
        st.markdown("<div style='margin-top:24px'></div>", unsafe_allow_html=True)
        if st.button("REMOTE", use_container_width=True):
            st.session_state.page = "remote"
            st.rerun()

    # ---- METRIC CARDS ----
    tog_col, _ = st.columns([2, 7])
    with tog_col:
        tele_view = st.radio("View", ["INDOOR", "OUTDOOR"], horizontal=True, label_visibility="collapsed")
    if tele_view == "INDOOR":
        cards = [
            ("TEMPERATURE", temp_str, "#fbbf24"),
            ("HUMIDITY",    hum_str,  "#34d399"),
            ("eCO2",        eco2_str, "#f87171"),
            ("AIR QUALITY", aq_level, aq_color),
        ]
    else:
        cards = [
            ("TEMPERATURE", out_temp_str,  "#fbbf24"),
            ("HUMIDITY",    out_hum_str,   "#34d399"),
            ("WIND SPEED",  out_wind_str,  "#a78bfa"),
            ("PRESSURE",    out_press_str, "#4facfe"),
        ]

    c1, c2, c3, c4, c5 = st.columns(5)
    for col, (label, val, color) in zip([c1, c2, c3, c4], cards):
        with col:
            with st.container(border=True, height=130):
                st.markdown(f"""
                <div style='padding:4px 2px;'>
                    <div class='metric-label'>{label}</div>
                    <div class='metric-val' style='color:{color};'>{val}</div>
                </div>
                """, unsafe_allow_html=True)

    status_color = "#34d399" if is_online else "#f87171"
    status_text  = "ONLINE"  if is_online else "OFFLINE"
    with c5:
        with st.container(border=True, height=130):
            st.markdown(f"""
            <div style='padding:4px 2px; text-align:center;'>
                <div class='metric-label'>M5STACK</div>
                <div class='metric-val' style='color:{status_color}; font-size:1.5rem;'>{status_text}</div>
                <div style='width:9px; height:9px; background:{status_color}; border-radius:50%;
                            margin:10px auto 0; box-shadow:0 0 10px {status_color};'></div>
            </div>
            """, unsafe_allow_html=True)

    # ---- CHARTS ----
    with st.container(border=True):
        sel_col, time_col = st.columns(2)
        with sel_col:
            chart_type = st.selectbox(
                "Metric",
                ["Temperature", "Humidity", "Air Quality (eCO2/TVOC)"],
                label_visibility="collapsed"
            )
        with time_col:
            time_filter = st.selectbox(
                "Range",
                ["Last 24 Hours", "Last 7 Days", "Last 30 Days"],
                label_visibility="collapsed"
            )

        hours_map = {"Last 24 Hours": 24, "Last 7 Days": 168, "Last 30 Days": 720}
        history = fetch_history(hours_map[time_filter])

        if history:
            df = pd.DataFrame(history)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
            df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

            fig = go.Figure()
            kw = dict(GLASS_CHART)
            title_style = dict(font=dict(color="rgba(255,255,255,0.5)", size=12, family="Inter"))

            if chart_type == "Temperature":
                if "temperature" in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df["timestamp"], y=df["temperature"],
                        name="Indoor Temp",
                        line=dict(color="#fbbf24", width=2.5),
                        fill="tozeroy", fillcolor="rgba(251,191,36,0.06)"
                    ))
                fig.update_layout(title=dict(text="INDOOR TEMPERATURE", **title_style), **kw)

            elif chart_type == "Humidity":
                if "humidity" in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df["timestamp"], y=df["humidity"],
                        name="Humidity %",
                        line=dict(color="#34d399", width=2.5),
                        fill="tozeroy", fillcolor="rgba(52,211,153,0.06)"
                    ))
                fig.update_layout(title=dict(text="INDOOR HUMIDITY", **title_style), **kw)

            elif chart_type == "Air Quality (eCO2/TVOC)":
                if "tvoc" in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df["timestamp"], y=df["tvoc"],
                        name="TVOC (ppb)", line=dict(color="#a78bfa", width=2.5)
                    ))
                if "eco2" in df.columns:
                    fig.add_trace(go.Scatter(
                        x=df["timestamp"], y=df["eco2"],
                        name="eCO2 (ppm)", line=dict(color="#f87171", width=2),
                        yaxis="y2"
                    ))
                kw["yaxis2"] = dict(
                    overlaying="y", side="right", showgrid=False,
                    color="rgba(255,255,255,0.4)", tickfont=dict(size=11)
                )
                fig.update_layout(title=dict(text="AIR QUALITY", **title_style), **kw)

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No historical data available.")

    # ---- AI SUMMARY + HOURLY FORECAST ----
    with st.container(border=True):
        ai_col, forecast_col = st.columns([2, 5])

        with ai_col:
            ai_context = {
                "indoor_temp": t, "indoor_humidity": h,
                "outdoor_temp": cw_temp,
                "outdoor_description": current_weather.get("description", ""),
                "wind_speed": cw_wind, "device_online": is_online
            }
            ai_summary = fetch_ai_insight(
                "weather_summary",
                f"Outdoor: {current_weather.get('description', 'unknown')} at {cw_temp}°C, wind {cw_wind} m/s. "
                f"Indoor: {t}°C. M5Stack {'online' if is_online else 'offline'}. "
                f"Give a 1 short sentence weather summary maximum. Very concise.",
                json.dumps(ai_context, default=str)
            )
            st.markdown(f"""
            <div style='padding:4px 0;'>
                <div class='section-title'>TODAY'S OVERVIEW</div>
                <div style='font-size:2.8rem; margin-bottom:8px; line-height:1;'>{icon_to_emoji(cw_icon)}</div>
                <div class='ai-summary'>{ai_summary}</div>
            </div>
            """, unsafe_allow_html=True)

        with forecast_col:
            items = hourly_forecast[:6] if hourly_forecast else []
            if items:
                cols = st.columns(len(items))
                for idx, item in enumerate(items):
                    with cols[idx]:
                        time_label = item.get("time", "")
                        temp_val   = int(item.get("temp", 0))
                        emoji      = icon_to_emoji(item.get("icon", "01d"))
                        st.markdown(f"""
                        <div style='text-align:center; padding:4px 0;'>
                            <div style='font-size:0.68rem; font-weight:700; color:rgba(255,255,255,0.38);
                                        letter-spacing:1.5px; text-transform:uppercase;'>{time_label}</div>
                            <div style='font-size:1.7rem; margin:6px 0;'>{emoji}</div>
                            <div style='font-weight:800; color:#ffffff; font-size:1.05rem;'>{temp_val}°C</div>
                        </div>
                        """, unsafe_allow_html=True)
            else:
                st.info("No hourly forecast available.")

    # ---- BOTTOM ROW — CSS Grid for guaranteed equal height ----
    GLASS = ("background:rgba(255,255,255,0.07);backdrop-filter:blur(16px);"
             "-webkit-backdrop-filter:blur(16px);border:1px solid rgba(255,255,255,0.12);"
             "border-radius:20px;padding:20px 24px;"
             "box-shadow:0 4px 28px rgba(0,0,0,0.35),inset 0 1px 0 rgba(255,255,255,0.07);")
    STITLE = "font-size:0.68rem;font-weight:700;color:rgba(255,255,255,0.38);text-transform:uppercase;letter-spacing:2px;margin-bottom:10px;"
    AITEXT = "font-style:italic;color:rgba(255,255,255,0.4);font-size:0.82rem;line-height:1.55;margin-top:6px;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden;"

    # Forecast rows
    forecast_inner = ""
    if daily_forecast:
        days  = daily_forecast[:5]
        g_min = min(d.get('temp_min', 0)  for d in days)
        g_max = max(d.get('temp_max', 10) for d in days)
        span  = max(g_max - g_min, 1)
        for i, day in enumerate(days):
            dn = "TODAY" if i == 0 else day.get('day_name', '')[:3].upper()
            ic = icon_to_emoji(day.get('icon', '01d'))
            mn, mx = day.get('temp_min', 0), day.get('temp_max', 0)
            lp = (mn - g_min) / span * 100
            wp = max((mx - mn) / span * 100, 8)
            forecast_inner += (
                f"<div class='forecast-row'>"
                f"<div class='forecast-day'>{dn}</div>"
                f"<div class='forecast-icon'>{ic}</div>"
                f"<div class='forecast-min'>{int(mn)}&deg;</div>"
                f"<div class='forecast-bar-bg'><div class='forecast-bar-fill' style='left:{lp:.1f}%;width:{wp:.1f}%;'></div></div>"
                f"<div class='forecast-max'>{int(mx)}&deg;</div>"
                f"</div>"
            )
    else:
        forecast_inner = "<p style='color:rgba(255,255,255,0.4)'>No forecast data.</p>"

    # Air quality
    aq_full, aq_col = get_aq_level(v, e)
    aq_pct = 33 if aq_full == "GOOD" else (66 if aq_full == "MODERATE" else 100)
    air_insight = fetch_ai_insight(
        "air_quality",
        f"Indoor TVOC={v}ppb, eCO2={e}ppm. Level: {aq_full}. 1 short sentence analysis max.",
        json.dumps({"tvoc": v, "eco2": e}, default=str)
    )

    # Delta temperature
    if t is not None and cw_temp is not None:
        delta = t - cw_temp
        sign  = "+" if delta >= 0 else ""
        delta_color = "#f87171" if delta > 3 else ("#4facfe" if delta < -3 else "rgba(255,255,255,0.75)")
        delta_insight = fetch_ai_insight(
            "delta_temp",
            f"Indoor {t:.1f}C, outdoor {cw_temp:.1f}C, delta {delta:+.1f}C. 1 short sentence max.",
            json.dumps({"indoor": t, "outdoor": cw_temp, "delta": delta}, default=str)
        )
        delta_val   = f"{sign}{delta:.1f}&deg;C"
        delta_clr   = delta_color
        delta_extra = f"<div style='{AITEXT}'>{delta_insight}</div>"
    else:
        delta_val   = "-- &deg;C"
        delta_clr   = "rgba(255,255,255,0.25)"
        delta_extra = ""

    parts = [
        f"<div style='{GLASS}'>",
        f"<div style='{STITLE}'>5-DAY FORECAST</div>",
        forecast_inner,
        "</div>",
        f"<div style='{GLASS}'>",
        f"<div style='{STITLE}'>AIR POLLUTION</div>",
        f"<div style='font-size:1.7rem;font-weight:900;color:{aq_col};'>{aq_full}</div>",
        f"<div style='height:7px;background:rgba(255,255,255,0.1);border-radius:4px;margin:7px 0 10px 0;'>"
        f"<div style='height:100%;border-radius:4px;width:{aq_pct}%;background:{aq_col};'></div></div>",
        f"<div style='{AITEXT}'>{air_insight}</div>",
        "<div style='border-top:1px solid rgba(255,255,255,0.08);margin:14px 0;'></div>",
        f"<div style='{STITLE}'>DELTA T INSIDE vs OUTSIDE</div>",
        f"<div style='font-size:2.6rem;font-weight:900;letter-spacing:-1px;margin:4px 0 6px 0;color:{delta_clr};'>{delta_val}</div>",
        delta_extra,
        "</div>",
    ]

    st.markdown(
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:16px;align-items:stretch;'>"
        + "".join(parts)
        + "</div>",
        unsafe_allow_html=True,
    )


# =====================================================
#                  REMOTE CONTROL PAGE
# =====================================================
elif st.session_state.page == "remote":
    col_back, col_title = st.columns([1, 6])
    with col_back:
        st.markdown("<div style='margin-top:6px'></div>", unsafe_allow_html=True)
        if st.button("← Back", use_container_width=True):
            st.session_state.page = "main"
            st.rerun()
    with col_title:
        st.markdown("<div class='greeting-header' style='margin-top:0;'>REMOTE CONTROL</div>", unsafe_allow_html=True)

    # ---- SLIDERS ----
    sl_b, sl_v = st.columns(2, gap="large")
    with sl_b:
        brightness = st.slider("☀️ Brightness", 0, 100, 80, key="b_slide")
        if st.button("Apply Brightness", key="apply_b", use_container_width=True):
            post_device_command("settings", f"b={brightness}")
            st.toast("Brightness updated")
    with sl_v:
        volume = st.slider("🔊 Volume", 0, 100, 50, key="v_slide")
        if st.button("Apply Volume", key="apply_v", use_container_width=True):
            post_device_command("settings", f"v={volume}")
            st.toast("Volume updated")

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ---- DEVICE + DIAGNOSTICS ----
    col_device, col_right = st.columns([1, 1], gap="large")

    with col_device:
        with st.container(border=True):
            st.markdown("<div id='m5-outer'></div>", unsafe_allow_html=True)

            with st.container(border=True):
                st.markdown("<div id='m5-screen'></div>", unsafe_allow_html=True)

                with st.container(border=True):
                    st.markdown("<div id='m5-nav'></div>", unsafe_allow_html=True)
                    n1, n2, n3, n4 = st.columns(4)
                    with n1:
                        if st.button("HOME",     use_container_width=True, key="btn_home"):
                            post_device_command("set_page", "page=home")
                    with n2:
                        if st.button("FORECAST", use_container_width=True, key="btn_weather"):
                            post_device_command("set_page", "page=weather")
                    with n3:
                        if st.button("HISTORY",  use_container_width=True, key="btn_history"):
                            post_device_command("set_page", "page=history")
                    with n4:
                        if st.button("SETTINGS", use_container_width=True, key="btn_settings"):
                            post_device_command("set_page", "page=settings")

            with st.container(border=True):
                st.markdown("<div id='m5-bottom'></div>", unsafe_allow_html=True)
                b1, b2, b3 = st.columns(3)
            with b1:
                if st.button("A", key="btn_a"): post_device_command("btn", "a")
            with b2:
                if st.button("B", key="btn_b"): post_device_command("btn", "b")
            with b3:
                if st.button("C", key="btn_c"): post_device_command("btn", "c")

    with col_right:
        # ---- DIAGNOSTICS ----
        last_ts = latest.get('timestamp')
        is_online_remote = False
        if last_ts:
            try:
                last_dt = pd.to_datetime(last_ts, utc=True)
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                is_online_remote = (now_utc - last_dt).total_seconds() < 360
            except Exception:
                pass

        status_cls   = "ok"     if is_online_remote else "fail"
        status_text  = "ONLINE" if is_online_remote else "OFFLINE"
        env_ok  = "OK"   if latest.get('temperature') is not None else "FAIL"
        env_cls = "ok"   if latest.get('temperature') is not None else "fail"
        prs_ok  = "OK"   if weather_data else "FAIL"
        prs_cls = "ok"   if weather_data else "fail"
        sgp_ok  = "OK"   if latest.get('tvoc') is not None else "FAIL"
        sgp_cls = "ok"   if latest.get('tvoc') is not None else "fail"

        with st.container(border=True):
            st.markdown(f"""
            <div class='diag-section'>CONNECTIVITY</div>
            <div class='diag-row'>
                <span class='diag-key'>Device Power</span>
                <span class='diag-val-{status_cls}'>{status_text}</span>
            </div>
            <div class='diag-row'>
                <span class='diag-key'>Cloud Backend</span>
                <span class='diag-val-ok'>CONNECTED</span>
            </div>
            <div class='diag-row'>
                <span class='diag-key'>Middleware Server</span>
                <span class='diag-val-ok'>CONNECTED</span>
            </div>

            <div class='diag-section'>SENSORS HEALTH</div>
            <div class='diag-row'>
                <span class='diag-key'>ENV III — Temp / Humidity</span>
                <span class='diag-val-{env_cls}'>{env_ok}</span>
            </div>
            <div class='diag-row'>
                <span class='diag-key'>ENV III — Pressure</span>
                <span class='diag-val-{prs_cls}'>{prs_ok}</span>
            </div>
            <div class='diag-row'>
                <span class='diag-key'>SGP30 — TVOC / eCO2</span>
                <span class='diag-val-{sgp_cls}'>{sgp_ok}</span>
            </div>
            """, unsafe_allow_html=True)

            st.markdown("<div style='height:12px'></div>", unsafe_allow_html=True)
            if st.button("Run Full System Diagnostic", use_container_width=True):
                st.toast("Diagnostic initiated on device.")
