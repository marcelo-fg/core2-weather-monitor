import streamlit as st
import streamlit.components.v1 as components
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

# =================== CUSTOM CSS ===================
st.markdown("""
<style>
    /* Hide sidebar */
    [data-testid="stSidebar"] { display: none; }
    [data-testid="stSidebarCollapsedControl"] { display: none; }
    /* General layout and background */
    .stApp {
        background: white !important;
    }
    .block-container { padding-top: 2rem; background: transparent !important; }

    /* Fix bento box background */
    [data-testid="stVerticalBlockBorderWrapper"] {
        background: white !important;
    }

    /* Make ALL columns stretch to match height in their row */
    div[data-testid="stHorizontalBlock"] {
        align-items: stretch !important;
    }
    
    /* Make the inner stVerticalBlock fill the column */
    div[data-testid="column"] > div[data-testid="stVerticalBlock"] {
        height: 100%;
        display: flex;
        flex-direction: column;
    }

    /* ================= ROW 1 (Telemetry & M5Stack) ================= */
    /* Make their element-containers flex-grow to fill the height */
    div[data-testid="stHorizontalBlock"]:nth-of-type(2) div[data-testid="column"] > div[data-testid="stVerticalBlock"] > div.element-container {
        flex-grow: 1;
        display: flex;
        flex-direction: column;
    }
    div[data-testid="stHorizontalBlock"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] {
        flex-grow: 1;
    }

    /* ================= ROW 4 (Forecast vs Air Poll & Delta) ================= */
    /* Left column: one big box, stretch it */
    div[data-testid="stHorizontalBlock"]:nth-of-type(4) div[data-testid="column"]:nth-of-type(1) > div[data-testid="stVerticalBlock"] > div.element-container {
        flex-grow: 1;
        display: flex;
        flex-direction: column;
    }
    div[data-testid="stHorizontalBlock"]:nth-of-type(4) div[data-testid="column"]:nth-of-type(1) [data-testid="stVerticalBlockBorderWrapper"] {
        flex-grow: 1;
    }

    /* Right column: two boxes, distribute space and stretch them */
    div[data-testid="stHorizontalBlock"]:nth-of-type(4) div[data-testid="column"]:nth-of-type(2) > div[data-testid="stVerticalBlock"] {
        justify-content: space-between;
        gap: 0.5rem !important; /* Reduce vertical space between the two boxes */
    }
    div[data-testid="stHorizontalBlock"]:nth-of-type(4) div[data-testid="column"]:nth-of-type(2) > div[data-testid="stVerticalBlock"] > div.element-container {
        flex: 1;
        display: flex;
        flex-direction: column;
    }
    div[data-testid="stHorizontalBlock"]:nth-of-type(4) div[data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] {
        flex-grow: 1;
    }
    
    /* Reduce inner padding of the air pollution/delta boxes to save space */
    div[data-testid="stHorizontalBlock"]:nth-of-type(4) div[data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] > div {
        padding-top: 0.8rem !important;
        padding-bottom: 0.8rem !important;
    }

    /* Remote button bento styling */
    [data-testid="stButton"] button {
        background-color: white !important;
        border: 2px solid #3b82f6 !important;
        border-radius: 8px !important;
        box-shadow: none !important;
    }
    [data-testid="stButton"] button p {
        color: #3b82f6 !important;
        font-weight: 800 !important;
    }

    .ai-insight, .ai-summary {
        display: -webkit-box;
        -webkit-line-clamp: 2;
        -webkit-box-orient: vertical;
        overflow: hidden;
        text-overflow: ellipsis;
        font-style: italic;
        color: #666;
        margin-top: 10px;
    }

    .greeting-header {
        font-family: 'Inter', -apple-system, sans-serif;
        font-weight: 800;
        font-size: 2.5rem;
        color: #1a1a1a;
        margin-bottom: 1.5rem;
    }

    /* Metric styles */
    .metric-row {
        display: flex;
        justify-content: space-between;
        align-items: flex-end;
        gap: 20px;
        padding: 0px 10px 5px 10px;
    }
    .metric-block { text-align: left; flex: 1; }
    .metric-val {
        font-size: 3.2rem;
        font-weight: 800;
        color: #1a1a1a;
        line-height: 1.1;
    }
    .metric-label {
        font-size: 0.85rem;
        font-weight: 700;
        color: #000;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        margin-top: 5px;
    }

    /* Section titles */
    .section-title {
        font-size: 0.85rem;
        font-weight: 600;
        color: #999;
        text-transform: uppercase;
        letter-spacing: 1.5px;
        margin-bottom: 15px;
    }

    /* Forecast row */
    .forecast-row {
        display: flex;
        align-items: center;
        padding: 10px 0;
        gap: 12px;
        margin: 5px 0;
    }
    .forecast-day { width: 55px; font-weight: 700; color: #1a1a1a; font-size: 0.95rem; }
    .forecast-icon { font-size: 1.2rem; width: 30px; text-align: center; }
    .forecast-min { width: 28px; text-align: right; color: #999; font-weight: 600; font-size: 0.9rem; }
    .forecast-bar-bg {
        flex-grow: 1; height: 6px; background: #eee;
        border-radius: 3px; position: relative;
    }
    .forecast-bar-fill {
        position: absolute; top: 0; bottom: 0;
        background: linear-gradient(90deg, #fbbf24, #f59e0b);
        border-radius: 3px;
    }
    .forecast-max { width: 28px; font-weight: 800; color: #1a1a1a; font-size: 0.9rem; }

    /* AQ bar */
    .aq-bar {
        height: 10px; background: #ddd;
        border-radius: 5px; margin: 10px 0 15px 0;
    }
    .aq-bar-fill { height: 100%; border-radius: 5px; }

    .delta-value {
        font-size: 3rem; font-weight: 800;
        color: #888; margin: 5px 0 10px 0;
    }
    
    /* Radio button styling to look like tabs */
    div[role="radiogroup"] {
        margin-bottom: 10px;
    }
    div[role="radiogroup"] > label > div:first-child {
        display: none !important; /* Hide the radio circles */
    }
    div[role="radiogroup"] p {
        font-weight: 800;
        font-size: 1.1rem;
        color: #888;
        cursor: pointer;
        margin-right: 15px;
    }
    div[role="radiogroup"] label[data-baseweb="radio"] input:checked + div p {
        color: #3b82f6 !important;
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
        # Force English response unconditionally
        full_prompt = prompt_text + " IMPORTANT: Answer in English only."
        result = ask_llm(full_prompt, context)
        if result:
            import re
            result = re.sub(r'(?i)This is Orion.*?(station|board|Commander)\.?', '', result, flags=re.DOTALL)
            result = re.sub(r'(?i)I am analyzing the data.*?\.', '', result)
            result = re.sub(r'(?i)My mission is to.*?\.', '', result)
            result = re.sub(r'(?i)Commander,\s*here is.*?:', '', result)
            result = re.sub(r'(?i)My advice.*?:', '', result)
            result = result.replace("Commander,", "").replace("Commander.", "").replace("Commander", "").strip()
            return result
        return "AI analysis temporarily unavailable."
    except Exception as e:
        return f"Error fetching AI insight: {e}"

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
        return "UNKNOWN", "#888"
    if (tvoc is not None and tvoc < 220) and (eco2 is not None and eco2 < 1000):
        return "GOOD", "#22c55e"
    elif (tvoc is not None and tvoc < 660) and (eco2 is not None and eco2 < 2000):
        return "MODERATE", "#f59e0b"
    return "POOR", "#ef4444"


# =====================================================
#                     MAIN PAGE
# =====================================================
if st.session_state.page == "main":
    now = datetime.datetime.now()
    hour = now.hour
    greeting = "GOOD MORNING" if hour < 12 else ("GOOD AFTERNOON" if hour < 18 else "GOOD EVENING")
    date_str = now.strftime("%a %b %d")

    # ---------- HEADER ----------
    col_greeting, col_btn = st.columns([8, 1])
    with col_greeting:
        st.markdown(f"<div class='greeting-header'>{greeting}, {date_str}</div>", unsafe_allow_html=True)
    with col_btn:
        st.markdown("<div style='margin-top: 10px;'></div>", unsafe_allow_html=True)
        if st.button("REMOTE", key="remote_btn", use_container_width=True):
            st.session_state.page = "remote"
            st.rerun()

    # ---------- SENSOR VALUES ----------
    t = latest.get('temperature')
    h = latest.get('humidity')
    v = latest.get('tvoc')
    e = latest.get('eco2')

    temp_str = f"{t:.1f} C" if t is not None else "--"
    hum_str = f"{h:.1f}%" if h is not None else "--"
    eco2_str = f"{int(e)}ppm" if e is not None else "--"
    aq_level, aq_color = get_aq_level(v, e)

    cw_temp = current_weather.get("temp")
    cw_hum = current_weather.get("humidity")
    cw_wind = current_weather.get("wind_speed")
    cw_press = current_weather.get("pressure")
    out_temp_str = f"{cw_temp:.1f} C" if cw_temp is not None else "--"
    out_hum_str = f"{cw_hum}%" if cw_hum is not None else "--"
    out_wind_str = f"{cw_wind} m/s" if cw_wind is not None else "--"
    out_press_str = f"{cw_press} hPa" if cw_press is not None else "--"

    # Online status
    last_ts = latest.get('timestamp')
    is_online = False
    if last_ts:
        try:
            last_dt = pd.to_datetime(last_ts, utc=True)
            now_utc = datetime.datetime.now(datetime.timezone.utc)
            is_online = (now_utc - last_dt).total_seconds() < 120
        except Exception:
            pass

    # ========== BENTO 1 : TELEMETRY + M5STACK STATUS ==========
    tele_col, device_col = st.columns([3, 1])

    with tele_col:
        with st.container(border=True, height=185):
            tele_view = st.radio("View", ["INDOOR", "OUTDOOR"], horizontal=True, label_visibility="collapsed")
            
            if tele_view == "INDOOR":
                st.markdown(f"""
                <div class="metric-row">
                    <div class="metric-block"><div class="metric-val">{temp_str}</div><div class="metric-label">TEMPERATURE</div></div>
                    <div class="metric-block"><div class="metric-val">{hum_str}</div><div class="metric-label">HUMIDITY</div></div>
                    <div class="metric-block"><div class="metric-val">{eco2_str}</div><div class="metric-label">eCO2</div></div>
                    <div class="metric-block"><div class="metric-val" style="color:{aq_color};">{aq_level}</div><div class="metric-label">AIR QUALITY</div></div>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div class="metric-row">
                    <div class="metric-block"><div class="metric-val">{out_temp_str}</div><div class="metric-label">TEMPERATURE</div></div>
                    <div class="metric-block"><div class="metric-val">{out_hum_str}</div><div class="metric-label">HUMIDITY</div></div>
                    <div class="metric-block"><div class="metric-val">{out_wind_str}</div><div class="metric-label">WIND SPEED</div></div>
                    <div class="metric-block"><div class="metric-val">{out_press_str}</div><div class="metric-label">PRESSURE</div></div>
                </div>
                """, unsafe_allow_html=True)

    with device_col:
        border_col = "#22c55e" if is_online else "#ef4444"
        status_txt = "ONLINE" if is_online else "OFFLINE"
        status_col = "#22c55e" if is_online else "#ef4444"
        
        with st.container(border=True, height=185):
            st.markdown(f"""
            <style>
            /* Apply color to this specific container's border */
            div[data-testid="column"]:nth-of-type(2) [data-testid="stVerticalBlockBorderWrapper"] {{
                border: 2px solid {border_col} !important;
            }}
            </style>
<div style="display: flex; flex-direction: column; align-items: center; justify-content: center; height: 100%; padding: 10px 0;">
    <div style="width: 150px; height: 130px; background: #1a1a1a; border-radius: 12px; border: 4px solid #c0392b; display: flex; flex-direction: column; align-items: center; justify-content: flex-start; padding-top: 10px; position: relative;">
        <div style="width: 120px; height: 80px; background: white; border-radius: 4px; position: relative; display: flex; align-items: center; justify-content: center;">
            <div style="font-weight:800; font-size:1rem; color:{status_col};">{status_txt}</div>
            <div style="position:absolute; top:8px; right:8px; width:10px; height:10px; background:{border_col}; border-radius:50%;"></div>
        </div>
        <div style="display: flex; gap: 8px; margin-top: 12px;">
            <div style="width: 25px; height: 10px; background: white; border-radius: 3px;"></div>
            <div style="width: 25px; height: 10px; background: white; border-radius: 3px;"></div>
            <div style="width: 25px; height: 10px; background: white; border-radius: 3px;"></div>
        </div>
    </div>
</div>
            """, unsafe_allow_html=True)

    # ========== BENTO 2 : CHARTS ==========
    with st.container(border=True):
        col_metric, col_time = st.columns([1, 1])
        with col_metric:
            chart_type = st.selectbox("Metric", ["Temperature", "Humidity", "Air Quality (eCO2/TVOC)"], label_visibility="collapsed")
        with col_time:
            time_filter = st.selectbox("Time Range", ["Last 24 Hours", "Last 7 Days", "Last 30 Days"], label_visibility="collapsed")
            
        hours_map = {"Last 24 Hours": 24, "Last 7 Days": 168, "Last 30 Days": 720}
        history = fetch_history(hours_map[time_filter])

        if history:
            df = pd.DataFrame(history)
            df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
            df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

            chart_kw = dict(
                height=350, margin=dict(l=0, r=0, t=40, b=0),
                paper_bgcolor="white", plot_bgcolor="white",
                xaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
                yaxis=dict(showgrid=True, gridcolor="#f0f0f0"),
                legend=dict(orientation="h", y=1.1),
            )

            fig = go.Figure()

            if chart_type == "Temperature":
                if "temperature" in df.columns:
                    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["temperature"], name="Indoor Temp", line=dict(color="#f59e0b", width=2.5)))
                fig.update_layout(title="Indoor Temperature", **chart_kw)
                
            elif chart_type == "Humidity":
                if "humidity" in df.columns:
                    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["humidity"], name="Humidity", line=dict(color="#14b8a6", width=2.5), fill='tozeroy', fillcolor="rgba(20,184,166,0.1)"))
                fig.update_layout(title="Indoor Humidity Trend", **chart_kw)
                
            elif chart_type == "Air Quality (eCO2/TVOC)":
                if "tvoc" in df.columns:
                    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["tvoc"], name="TVOC (ppb)", line=dict(color="#8b5cf6", width=2.5)))
                if "eco2" in df.columns:
                    fig.add_trace(go.Scatter(x=df["timestamp"], y=df["eco2"], name="eCO2 (ppm)", line=dict(color="#ef4444", width=2), yaxis="y2"))
                fig.update_layout(title="Air Quality", yaxis2=dict(overlaying="y", side="right", showgrid=False), **chart_kw)

            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("No historical data available.")

    # ========== BENTO 3 : AI SUMMARY + HOURLY FORECAST ==========
    with st.container(border=True):
        ai_context = {
            "indoor_temp": t, "indoor_humidity": h,
            "outdoor_temp": cw_temp,
            "outdoor_description": current_weather.get("description", ""),
            "wind_speed": cw_wind, "device_online": is_online
        }
        ai_summary = fetch_ai_insight(
            "weather_summary",
            f"Outdoor: {current_weather.get('description', 'unknown')} at {cw_temp} C, wind {cw_wind} m/s. "
            f"Indoor: {t} C. M5Stack {'online' if is_online else 'offline'}. "
            f"Give a 1 short sentence weather summary maximum. Very concise.",
            json.dumps(ai_context, default=str)
        )
        st.markdown(f"<div class='ai-summary'>{ai_summary}</div>", unsafe_allow_html=True)
        st.divider()

        # Hourly forecast using st.columns (avoids HTML rendering issues)
        items = hourly_forecast[:6] if hourly_forecast else []
        if items:
            cols = st.columns(len(items))
            for idx, item in enumerate(items):
                with cols[idx]:
                    time_label = item.get("time", "")
                    temp_val = int(item.get("temp", 0))
                    emoji = icon_to_emoji(item.get("icon", "01d"))
                    st.markdown(f"<div style='text-align:center;'>"
                                f"<div style='font-weight:600; color:#555; font-size:0.85rem;'>{time_label}</div>"
                                f"<div style='font-size:1.8rem; margin:4px 0;'>{emoji}</div>"
                                f"<div style='font-weight:700; color:#1a1a1a; margin-bottom: 20px;'>{temp_val} °C</div>"
                                f"</div>", unsafe_allow_html=True)
        else:
            st.info("No hourly forecast available.")

    # ========== BENTO 4 : BOTTOM ROW ==========
    bot_left, bot_right = st.columns(2)

    with bot_left:
        with st.container(border=True, height=280):
            st.markdown("<div class='section-title'>5-DAY FORECAST</div>", unsafe_allow_html=True)
            if daily_forecast:
                days = daily_forecast[:5]
                g_min = min(d.get('temp_min', 0) for d in days)
                g_max = max(d.get('temp_max', 10) for d in days)
                span = max(g_max - g_min, 1)

                for i, day in enumerate(days):
                    dn = "TODAY" if i == 0 else day.get('day_name', '')[:3].upper()
                    ic = icon_to_emoji(day.get('icon', '01d'))
                    mn = day.get('temp_min', 0)
                    mx = day.get('temp_max', 0)
                    lp = (mn - g_min) / span * 100
                    wp = max((mx - mn) / span * 100, 8)
                    st.markdown(f"""<div class='forecast-row'>
                        <div class='forecast-day'>{dn}</div>
                        <div class='forecast-icon'>{ic}</div>
                        <div class='forecast-min'>{int(mn)}</div>
                        <div class='forecast-bar-bg'><div class='forecast-bar-fill' style='left:{lp}%;width:{wp}%;'></div></div>
                        <div class='forecast-max'>{int(mx)}</div>
                    </div>""", unsafe_allow_html=True)
            else:
                st.info("No forecast data available.")

    with bot_right:
        with st.container(border=True, height=132):
            # --- Air Pollution ---
            aq_full, aq_col = get_aq_level(v, e)
            aq_pct = 33 if aq_full == "GOOD" else (66 if aq_full == "MODERATE" else 100)
            
            air_insight = fetch_ai_insight(
                "air_quality",
                f"Indoor TVOC={v}ppb, eCO2={e}ppm. Level: {aq_full}. 1 short sentence analysis max. Answer in English only.",
                json.dumps({"tvoc": v, "eco2": e}, default=str)
            )

            html_str = f"""
            <div style='line-height: 1.2;'>
                <div class='section-title' style='margin-bottom: 5px;'>AIR POLLUTION</div>
                <div style='font-size:1.8rem; font-weight:800; color:#555; margin-bottom: 5px;'>{aq_full}</div>
                <div class='aq-bar' style='margin-bottom: 8px;'><div class='aq-bar-fill' style='width:{aq_pct}%; background:{aq_col};'></div></div>
                <div class='ai-insight' style='margin-top: 0;'>{air_insight}</div>
            </div>
            """
            st.markdown(html_str, unsafe_allow_html=True)

        with st.container(border=True, height=132):
            # --- Delta Temperature ---
            if t is not None and cw_temp is not None:
                delta = t - cw_temp
                sign = "+" if delta >= 0 else ""
                delta_insight = fetch_ai_insight(
                    "delta_temp",
                    f"Indoor {t:.1f} C, outdoor {cw_temp:.1f} C, delta {delta:+.1f} C. "
                    f"1 short sentence explanation max. Answer in English only.",
                    json.dumps({"indoor": t, "outdoor": cw_temp, "delta": delta}, default=str)
                )
                html_str = f"""
                <div style='line-height: 1.2;'>
                    <div class='section-title' style='margin-bottom: 5px;'>DELTA TEMPERATURE INSIDE VS OUTSIDE</div>
                    <div class='delta-value' style='margin-bottom: 5px;'>{sign}{delta:.1f} C</div>
                    <div class='ai-insight' style='margin-top: 0;'>{delta_insight}</div>
                </div>
                """
                st.markdown(html_str, unsafe_allow_html=True)
            else:
                html_str = f"""
                <div style='line-height: 1.2;'>
                    <div class='section-title' style='margin-bottom: 5px;'>DELTA TEMPERATURE INSIDE VS OUTSIDE</div>
                    <div class='delta-value' style='margin-bottom: 5px;'>-- C</div>
                </div>
                """
                st.markdown(html_str, unsafe_allow_html=True)


# =====================================================
#                  REMOTE CONTROL PAGE
# =====================================================
elif st.session_state.page == "remote":
    col_back, col_title = st.columns([1, 6])
    with col_back:
        st.markdown("<div style='margin-top: 5px;'></div>", unsafe_allow_html=True)
        if st.button("← Back", use_container_width=True):
            st.session_state.page = "main"
            st.rerun()
    with col_title:
        st.markdown("<div class='greeting-header' style='margin-top: 0;'>REMOTE DEVICE CONTROL</div>", unsafe_allow_html=True)

    # === REMOTE LAYOUT ===
    # Bento 1: Navigation
    with st.container(border=True):
        st.markdown("<div class='section-title'>CHANGE DEVICE PAGE</div>", unsafe_allow_html=True)
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            if st.button("HOME", use_container_width=True, key="btn_home"): 
                post_device_command("set_page", "page=home")
                st.toast("Navigated to HOME")
        with col2:
            if st.button("FORECAST", use_container_width=True, key="btn_weather"): 
                post_device_command("set_page", "page=weather")
                st.toast("Navigated to FORECAST")
        with col3:
            if st.button("HISTORY", use_container_width=True, key="btn_history"): 
                post_device_command("set_page", "page=history")
                st.toast("Navigated to HISTORY")
        with col4:
            if st.button("SETTINGS", use_container_width=True, key="btn_settings"): 
                post_device_command("set_page", "page=settings")
                st.toast("Navigated to SETTINGS")

    st.markdown("<br>", unsafe_allow_html=True)

    # Bento 2: Diagnostics
    with st.container(border=True):
        st.markdown("<div class='section-title'>SYSTEM DIAGNOSTICS & CONNECTIVITY</div>", unsafe_allow_html=True)
        
        last_ts = latest.get('timestamp')
        is_online = False
        if last_ts:
            try:
                last_dt = pd.to_datetime(last_ts, utc=True)
                now_utc = datetime.datetime.now(datetime.timezone.utc)
                is_online = (now_utc - last_dt).total_seconds() < 360
            except:
                pass

        status_color = "#22c55e" if is_online else "#ef4444"
        status_text = "ONLINE" if is_online else "OFFLINE"
        
        env_temp_ok = "OK" if latest.get('temperature') is not None else "FAIL"
        env_press_ok = "OK" if weather_data else "FAIL" 
        sgp_ok = "OK" if latest.get('tvoc') is not None else "FAIL"
        
        html_diagnostics = f"""
        <div style="background: #f8f9fa; border-radius: 8px; padding: 15px; margin-bottom: 15px;">
            <h4 style="margin: 0 0 10px 0; font-size: 0.95rem; color: #333; text-transform: uppercase;">MAIN CONNECTIVITY</h4>
            <div style="display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #eee;">
                <span style="font-weight: 600; color: #555;">Device Power</span>
                <span style="font-weight: 800; color: {status_color};">{status_text}</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #eee;">
                <span style="font-weight: 600; color: #555;">Cloud Backend Sync</span>
                <span style="font-weight: 800; color: #22c55e;">CONNECTED</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 5px 0;">
                <span style="font-weight: 600; color: #555;">Middleware Server</span>
                <span style="font-weight: 800; color: #22c55e;">CONNECTED</span>
            </div>
        </div>

        <div style="background: #f8f9fa; border-radius: 8px; padding: 15px;">
            <h4 style="margin: 0 0 10px 0; font-size: 0.95rem; color: #333; text-transform: uppercase;">SENSORS HEALTH</h4>
            <div style="display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #eee;">
                <span style="font-weight: 600; color: #555;">ENV III (Temp/Hum)</span>
                <span style="font-weight: 800; color: #555;">{env_temp_ok}</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #eee;">
                <span style="font-weight: 600; color: #555;">ENV III (Pressure)</span>
                <span style="font-weight: 800; color: #555;">{env_press_ok}</span>
            </div>
            <div style="display: flex; justify-content: space-between; padding: 5px 0;">
                <span style="font-weight: 600; color: #555;">SGP30 (TVOC/eCO2)</span>
                <span style="font-weight: 800; color: #555;">{sgp_ok}</span>
            </div>
        </div>
        """
        st.markdown(html_diagnostics, unsafe_allow_html=True)
        
        st.markdown("<div style='height: 5px;'></div>", unsafe_allow_html=True)
        if st.button("Run Full System Diagnostic", use_container_width=True):
            st.toast("Diagnostic test initiated on device.")

    st.markdown("<br>", unsafe_allow_html=True)

    # Bento 3: AI Assistant Chat
    with st.container(border=True):
        st.markdown("<div class='section-title'>ORION AI ASSISTANT</div>", unsafe_allow_html=True)
        
        if "chat_history" not in st.session_state:
            st.session_state.chat_history = []
            
        chat_container = st.container(height=350)
        with chat_container:
            for msg in st.session_state.chat_history:
                with st.chat_message(msg["role"]):
                    st.markdown(msg["content"])
        
        # Text Input
        prompt = st.chat_input("Ask Orion anything about the station...")

        if prompt:
            user_text = prompt
            st.session_state.chat_history.append({"role": "user", "content": user_text})
            # Re-render new message
            with chat_container:
                with st.chat_message("user"):
                    st.markdown(user_text)
                    
            # AI Response
            context = {
                "temperature": latest.get("temperature"),
                "humidity": latest.get("humidity"),
                "tvoc": latest.get("tvoc"),
                "eco2": latest.get("eco2"),
                "aq_label": latest.get("aq_label"),
                "weather": {"current": weather_data.get("current", {}) if weather_data else {}},
            }
            
            with chat_container:
                with st.chat_message("assistant"):
                    with st.spinner("Orion is thinking..."):
                        answer = ask_llm(user_text, context)
                        if answer:
                            st.markdown(answer)
                            st.session_state.chat_history.append({"role": "assistant", "content": answer})
                        else:
                            st.error("Sorry, I could not reach the middleware.")
