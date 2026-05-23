"""
Main Streamlit dashboard — Core2 Indoor/Outdoor Weather Monitor.
Professional cloud-based monitoring interface with premium UI/UX.
"""
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timezone
import sys, os

sys.path.insert(0, os.path.dirname(__file__))
from services.api_client import get_latest, get_history, get_weather, ask_llm

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Core2 Intelligence",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS & Icons ───────────────────────────────────────────────────────
st.markdown(
    '''
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/regular/style.css" />
    <link rel="stylesheet" type="text/css" href="https://unpkg.com/@phosphor-icons/web@2.1.1/src/fill/style.css" />
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    /* Base Typography */
    html, body, .stApp, .stMarkdown, p, div {
        font-family: 'Outfit', sans-serif !important;
    }
    /* Main App Background */
    .stApp {
        background: radial-gradient(circle at top right, #0f172a, #020617);
        color: #f8fafc;
    }
    /* Hide Streamlit branding */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    /* Metric Cards (Glassmorphism) */
    .metric-card {
        background: rgba(30, 41, 59, 0.4);
        backdrop-filter: blur(12px);
        -webkit-backdrop-filter: blur(12px);
        border: 1px solid rgba(255, 255, 255, 0.05);
        border-top: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 1.2rem;
        text-align: left;
        box-shadow: 0 4px 20px rgba(0, 0, 0, 0.2);
        transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
        position: relative;
        overflow: hidden;
        min-height: 140px;
        display: flex;
        flex-direction: column;
        justify-content: space-between;
    }
    .metric-card:hover {
        transform: translateY(-4px);
        box-shadow: 0 12px 30px rgba(0, 0, 0, 0.4);
        border: 1px solid rgba(255, 255, 255, 0.15);
    }
    /* Metric Card Header (Icon + Title) */
    .metric-card-header {
        display: flex;
        align-items: center;
        gap: 8px;
        margin-bottom: 8px;
        flex-wrap: nowrap;
    }
    .metric-card-header i {
        font-size: 1.2rem;
        color: #94a3b8;
        flex-shrink: 0;
    }
    .metric-card h2 {
        color: #94a3b8;
        font-size: 0.85rem;
        font-weight: 600;
        margin: 0;
        text-transform: uppercase;
        letter-spacing: 0.5px;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    /* Metric Value */
    .metric-card .value {
        font-size: 1.8rem;
        font-weight: 700;
        margin: 0;
        line-height: 1.2;
        color: #f8fafc;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    /* Metric Subtitle/Info */
    .metric-card .sub {
        font-size: 0.75rem;
        color: #64748b;
        margin-top: 6px;
        font-weight: 400;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    /* Alerts/Status Styles inside cards */
    .status-indicator {
        position: absolute;
        top: 0;
        right: 0;
        width: 4px;
        height: 100%;
    }
    .status-good { background: linear-gradient(to bottom, #10b981, #059669); }
    .status-warn { background: linear-gradient(to bottom, #f59e0b, #d97706); }
    .status-bad { background: linear-gradient(to bottom, #ef4444, #dc2626); }
    /* Section Titles */
    .section-title {
        display: flex;
        align-items: center;
        gap: 10px;
        color: #e2e8f0;
        font-size: 1.2rem;
        font-weight: 600;
        border-bottom: 1px solid rgba(255,255,255,0.05);
        padding-bottom: 0.8rem;
        margin-top: 1.5rem;
        margin-bottom: 1rem;
    }
    .section-title i { color: #3b82f6; font-size: 1.4rem; }
    /* Buttons & Inputs */
    .stButton>button {
        border-radius: 8px !important;
        font-weight: 500 !important;
        transition: all 0.2s ease !important;
        background-color: rgba(59, 130, 246, 0.1) !important;
        color: #60a5fa !important;
        border: 1px solid rgba(59, 130, 246, 0.3) !important;
    }
    .stButton>button:hover {
        background-color: #3b82f6 !important;
        color: white !important;
        box-shadow: 0 4px 12px rgba(59, 130, 246, 0.3) !important;
    }
    /* Primary buttons */
    button[kind="primary"] {
        background-color: #3b82f6 !important;
        color: white !important;
        border: none !important;
    }
    button[kind="primary"]:hover {
        background-color: #2563eb !important;
        box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4) !important;
    }
    .stTextInput>div>div>input, .stTextArea>div>div>textarea {
        border-radius: 8px !important;
        background-color: rgba(30, 41, 59, 0.6) !important;
        border: 1px solid rgba(255,255,255,0.1) !important;
        color: #f8fafc !important;
    }
    </style>
    ''',
    unsafe_allow_html=True
)

# ── Helpers ──────────────────────────────────────────────────────────────────

WEATHER_ICONS = {
    "Clear": "ph-sun", "Clouds": "ph-cloud", "Rain": "ph-cloud-rain",
    "Drizzle": "ph-cloud-snow", "Thunderstorm": "ph-cloud-lightning", "Snow": "ph-snowflake",
    "Mist": "ph-waves", "Fog": "ph-cloud-fog",
}

def get_status_class(metric_type: str, value: float) -> str:
    if value is None: return ""
    if metric_type == "humidity":
        return "status-warn" if value < 40 else "status-good"
    if metric_type == "tvoc":
        return "status-bad" if value > 500 else "status-good"
    if metric_type == "eco2":
        return "status-bad" if value > 1000 else "status-good"
    if metric_type == "aq":
        if value in ("Poor", "Hazardous"): return "status-bad"
        if value == "Moderate": return "status-warn"
        return "status-good"
    return "status-good"

def metric_card(icon_class: str, title: str, value: str, sub: str = "", status_class: str = "") -> str:
    return f"""
    <div class="metric-card">
        <div class="status-indicator {status_class}"></div>
        <div class="metric-card-header">
            <i class="ph {icon_class}"></i>
            <h2>{title}</h2>
        </div>
        <div class="value">{value}</div>
        <div class="sub">{sub}</div>
    </div>"""

# ── Sidebar ───────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
        <div style="display:flex; align-items:center; gap:12px; margin-bottom: 2rem;">
            <i class="ph-fill ph-cpu" style="font-size:2.5rem; color:#3b82f6;"></i>
            <div>
                <h2 style="margin:0; font-size:1.2rem; font-weight:600;">Core2 Intelligence</h2>
                <div style="color:#64748b; font-size:0.8rem;">Lausanne, CH</div>
            </div>
        </div>
    """, unsafe_allow_html=True)

    st.divider()

    history_hours = st.slider("Data Horizon (hours)", 1, 168, 24)
    location = st.text_input("Forecast Location", value="Lausanne,CH")

    st.divider()

    st.markdown("<div style='color:#94a3b8; font-weight:500; margin-bottom:10px;'>System Thresholds</div>", unsafe_allow_html=True)
    st.markdown("""
        <div style="font-size:0.85rem; color:#64748b; display:flex; flex-direction:column; gap:8px;">
            <div><i class="ph-fill ph-warning-circle" style="color:#f59e0b"></i> Humidity &lt; 40%</div>
            <div><i class="ph-fill ph-warning-octagon" style="color:#ef4444"></i> TVOC &gt; 500 ppb</div>
            <div><i class="ph-fill ph-warning-octagon" style="color:#ef4444"></i> eCO₂ &gt; 1000 ppm</div>
        </div>
    """, unsafe_allow_html=True)

    st.divider()
    
    auto_refresh = st.checkbox("Enable Auto-sync (60s)", value=False)
    if auto_refresh:
        import time
        time.sleep(60)
        st.rerun()

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Synchronizing telemetry..."):
    latest  = get_latest()
    history = get_history(history_hours)
    weather = get_weather(location)

current_weather = weather.get("current", {})
forecast        = weather.get("forecast", [])

# ── Header row ─────────────────────────────────────────────────────────────────
now_str = datetime.now(timezone.utc).strftime("%d %B %Y — %H:%M UTC")
col_title, col_refresh = st.columns([4, 1])
with col_title:
    st.markdown(f"<div style='font-size:1.8rem; font-weight:700; color:#f8fafc; letter-spacing:-0.5px;'>Environment Overview</div>", unsafe_allow_html=True)
    st.markdown(f"<div style='color:#64748b; font-size:0.9rem; margin-top:-5px;'>Last synchronized: {now_str}</div>", unsafe_allow_html=True)
with col_refresh:
    st.write("") # padding
    if st.button("Synchronize Now", type="primary", use_container_width=True):
        st.rerun()

# ── Current conditions ────────────────────────────────────────────────────────
st.markdown('<div class="section-title"><i class="ph-fill ph-activity"></i> Indoor Telemetry</div>', unsafe_allow_html=True)

cols = st.columns(5)
if latest:
    temp  = latest.get("temperature")
    humi  = latest.get("humidity")
    tvoc  = latest.get("tvoc")
    eco2  = latest.get("eco2")
    aq    = latest.get("aq_label", "Unknown")
    ts_str = str(latest.get("timestamp", ""))

    try:
        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
        ts_label = f"Updated at {ts.strftime('%H:%M')}"
    except Exception:
        ts_label = "Update time unknown"

    with cols[0]:
        v = f"{temp:.1f}°C" if temp is not None else "--"
        st.markdown(metric_card("ph-thermometer", "Temperature", v, ts_label, "status-good"), unsafe_allow_html=True)
    with cols[1]:
        v = f"{humi:.0f}%" if humi is not None else "--"
        st.markdown(metric_card("ph-drop", "Humidity", v, "Optimal: 40-60%", get_status_class("humidity", humi)), unsafe_allow_html=True)
    with cols[2]:
        v = f"{tvoc} ppb" if tvoc is not None else "--"
        st.markdown(metric_card("ph-flask", "TVOC", v, "Target: < 220 ppb", get_status_class("tvoc", tvoc)), unsafe_allow_html=True)
    with cols[3]:
        v = f"{eco2} ppm" if eco2 is not None else "--"
        st.markdown(metric_card("ph-wind", "eCO₂", v, "Target: < 1000 ppm", get_status_class("eco2", eco2)), unsafe_allow_html=True)
    with cols[4]:
        st.markdown(metric_card("ph-leaf", "Air Quality", aq, "Overall status", get_status_class("aq", aq)), unsafe_allow_html=True)
else:
    st.info("Waiting for sensor telemetry. Ensure the Core2 device is transmitting.", icon="📡")

# ── Outdoor weather ────────────────────────────────────────────────────────────
st.markdown(f'<div class="section-title"><i class="ph-fill ph-globe-hemisphere-west"></i> Meteorological Data <span style="color:#64748b; font-weight:400; font-size:1rem; margin-left:8px;">({location})</span></div>', unsafe_allow_html=True)

if current_weather:
    cond = current_weather.get("condition", "Clear")
    icon_class = WEATHER_ICONS.get(cond, "ph-thermometer")
    wcols = st.columns(5)
    with wcols[0]:
        v = f"{current_weather.get('temp', 0):.1f}°C"
        desc = current_weather.get("description", "").title()
        st.markdown(metric_card(icon_class, "Outdoor Temp", v, desc), unsafe_allow_html=True)
    with wcols[1]:
        v = f"{current_weather.get('feels_like', 0):.1f}°C"
        st.markdown(metric_card("ph-user", "Feels Like", v), unsafe_allow_html=True)
    with wcols[2]:
        v = f"{current_weather.get('humidity', 0)}%"
        st.markdown(metric_card("ph-drop", "Humidity", v), unsafe_allow_html=True)
    with wcols[3]:
        v = f"{current_weather.get('wind_speed', 0)} m/s"
        st.markdown(metric_card("ph-paper-plane-tilt", "Wind", v), unsafe_allow_html=True)
    with wcols[4]:
        v = f"{current_weather.get('pressure', 0)} hPa"
        st.markdown(metric_card("ph-gauge", "Pressure", v), unsafe_allow_html=True)
else:
    st.info("Meteorological data unavailable. Verifying API connection...", icon="🌐")

# ── 5-day forecast ─────────────────────────────────────────────────────────────
if forecast:
    st.markdown('<div class="section-title"><i class="ph-fill ph-calendar-blank"></i> Extended Forecast</div>', unsafe_allow_html=True)
    fcols = st.columns(len(forecast))
    for i, day in enumerate(forecast):
        with fcols[i]:
            cond = day.get("condition", "")
            icon_class = WEATHER_ICONS.get(cond, "ph-cloud")
            tmax = day.get("temp_max", 0)
            tmin = day.get("temp_min", 0)
            rain = day.get("rain_prob", 0)
            label = f"{day.get('day_name','?')} {day.get('date','')}"
            st.markdown(metric_card(
                icon_class,
                label,
                f"{tmax:.0f}°",
                f"Min: {tmin:.0f}° | Rain: {rain*100:.0f}%",
            ), unsafe_allow_html=True)

# ── Historical charts ──────────────────────────────────────────────────────────
if history:
    df = pd.DataFrame(history)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df = df.dropna(subset=["timestamp"]).sort_values("timestamp")

    st.markdown(f'<div class="section-title"><i class="ph-fill ph-chart-line-up"></i> Analytics & Trends</div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["Climate Overview", "Air Composition", "Differential Analysis"])

    # Shared Chart Layout
    layout_args = dict(
        font=dict(family="Outfit, sans-serif", color="#94a3b8"),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(30,41,59,0.3)",
        margin=dict(l=20, r=20, t=40, b=20),
        height=400,
        hovermode="x unified",
        legend=dict(orientation="h", y=1.1, x=0, font=dict(color="#e2e8f0")),
        xaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=False),
    )

    with tab1:
        fig = go.Figure()
        if "temperature" in df.columns:
            fig.add_trace(go.Scatter(
                x=df["timestamp"], y=df["temperature"],
                name="Indoor Temp (°C)", line=dict(color="#38bdf8", width=3, shape="spline"),
                fill="tozeroy", fillcolor="rgba(56,189,248,0.1)",
                mode="lines"
            ))
        if "outdoor_temp" in df.columns:
            fig.add_trace(go.Scatter(
                x=df["timestamp"], y=df["outdoor_temp"],
                name="Outdoor Temp (°C)", line=dict(color="#94a3b8", width=2, dash="dash", shape="spline"),
                mode="lines"
            ))
        if "humidity" in df.columns:
            fig.add_trace(go.Scatter(
                x=df["timestamp"], y=df["humidity"],
                name="Indoor Humidity (%)", line=dict(color="#818cf8", width=3, shape="spline"),
                yaxis="y2", mode="lines"
            ))
        fig.update_layout(
            **layout_args,
            yaxis=dict(title="Temperature (°C)", showgrid=True, gridcolor="rgba(255,255,255,0.05)", zeroline=False),
            yaxis2=dict(title="Humidity (%)", overlaying="y", side="right", showgrid=False),
        )
        st.plotly_chart(fig, use_container_width=True)

    with tab2:
        fig2 = go.Figure()
        if "tvoc" in df.columns:
            fig2.add_trace(go.Scatter(
                x=df["timestamp"], y=df["tvoc"],
                name="TVOC (ppb)", line=dict(color="#10b981", width=3, shape="spline"),
                fill="tozeroy", fillcolor="rgba(16,185,129,0.1)", mode="lines"
            ))
            fig2.add_hline(y=500, line_color="#ef4444", line_dash="dash", annotation_text="TVOC Warning", annotation_font_color="#ef4444")
        if "eco2" in df.columns:
            fig2.add_trace(go.Scatter(
                x=df["timestamp"], y=df["eco2"],
                name="eCO₂ (ppm)", line=dict(color="#fbbf24", width=3, shape="spline"),
                yaxis="y2", mode="lines"
            ))
            fig2.add_hline(y=1000, line_color="#f59e0b", line_dash="dash", annotation_text="CO₂ Warning", annotation_font_color="#f59e0b")
        fig2.update_layout(
            **layout_args,
            yaxis=dict(title="TVOC (ppb)", showgrid=True, gridcolor="rgba(255,255,255,0.05)"),
            yaxis2=dict(title="eCO₂ (ppm)", overlaying="y", side="right", showgrid=False),
        )
        st.plotly_chart(fig2, use_container_width=True)

    with tab3:
        if "temperature" in df.columns and "outdoor_temp" in df.columns:
            df_clean = df.dropna(subset=["temperature", "outdoor_temp"])
            fig3 = px.scatter(
                df_clean, x="outdoor_temp", y="temperature", color="humidity",
                color_continuous_scale="PuBu",
                labels={"outdoor_temp": "Outdoor Temp (°C)", "temperature": "Indoor Temp (°C)", "humidity": "Humidity %"},
                title="Indoor vs Outdoor Temperature Differential"
            )
            fig3.update_layout(**layout_args)
            fig3.update_traces(marker=dict(size=10, line=dict(width=1, color="rgba(255,255,255,0.5)")))
            st.plotly_chart(fig3, use_container_width=True)

    with st.expander("View Raw Telemetry Log"):
        display_cols = [c for c in ["timestamp", "temperature", "humidity", "tvoc", "eco2", "aq_label", "outdoor_temp"] if c in df.columns]
        st.dataframe(df[display_cols].sort_values("timestamp", ascending=False).head(100), use_container_width=True)

# ── AI Assistant ───────────────────────────────────────────────────────────────
st.markdown('<div class="section-title"><i class="ph-fill ph-sparkle"></i> AI Intelligence Center</div>', unsafe_allow_html=True)

# AI Layout Restructured
query = st.text_area(
    "Query the Environment AI:",
    value=st.session_state.get("ai_query", ""),
    placeholder="e.g., Provide a comprehensive analysis of my indoor climate...",
    key="ai_input",
    height=80
)

st.markdown("<div style='color:#94a3b8; font-size:0.85rem; margin-top:8px; margin-bottom:8px;'>Suggested Queries:</div>", unsafe_allow_html=True)

# Presets as horizontal buttons
pcols = st.columns(4)
presets = [
    "Synthesize air quality",
    "Evaluate comfort",
    "Ventilation advice",
    "Temperature trends"
]
for i, p in enumerate(presets):
    with pcols[i]:
        if st.button(p, key=f"preset_{i}", use_container_width=True):
            st.session_state["ai_query"] = p
            st.rerun()

st.write("") # small spacing
if st.button("Initialize Analysis", type="primary", use_container_width=True) and query:
    context = {
        **(latest or {}),
        "weather": weather,
        "history": history[-5:] if history else [],
    }
    with st.spinner("Analyzing telemetry streams..."):
        response = ask_llm(query, context)
    if response:
        st.markdown(f"""
        <div style="background:rgba(59,130,246,0.1); border-left:4px solid #3b82f6; padding:1.2rem; border-radius:0 8px 8px 0; margin-top:1.5rem; margin-bottom:1rem;">
            <div style="font-weight:600; color:#3b82f6; margin-bottom:0.5rem; display:flex; align-items:center; gap:8px;">
                <i class="ph-fill ph-robot"></i> Analysis Complete
            </div>
            <div style="color:#e2e8f0; line-height:1.6; font-size:0.95rem;">{response}</div>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.error("System unreachable. Verify middleware connection and Gemini API authentication.")

# ── Alerts panel ───────────────────────────────────────────────────────────────
if latest:
    alerts = []
    humi = latest.get("humidity")
    tvoc = latest.get("tvoc")
    eco2 = latest.get("eco2")
    aq   = latest.get("aq_label", "Good")

    if humi is not None and humi < 40:
        alerts.append(("ph-drop", "f59e0b", f"Low indoor humidity ({humi:.0f}%) detected. Consider environmental modification."))
    if tvoc is not None and tvoc > 500:
        alerts.append(("ph-flask", "ef4444", f"Critical TVOC levels ({tvoc} ppb). Immediate ventilation recommended."))
    if eco2 is not None and eco2 > 1000:
        alerts.append(("ph-wind", "ef4444", f"Elevated eCO₂ concentration ({eco2} ppm). Airflow required."))
    if aq in ("Poor", "Hazardous"):
        alerts.append(("ph-warning-octagon", "ef4444", f"System Alert: Air quality assessed as {aq}."))

    if alerts:
        st.markdown('<div class="section-title"><i class="ph-fill ph-bell-ringing"></i> Active System Alerts</div>', unsafe_allow_html=True)
        for icon, color, text in alerts:
            st.markdown(f"""
            <div style="background:rgba({int(color[:2],16)},{int(color[2:4],16)},{int(color[4:],16)},0.1); border:1px solid #{color}; padding:1rem; border-radius:8px; margin-bottom:0.8rem; display:flex; align-items:center; gap:12px;">
                <i class="ph-fill {icon}" style="color:#{color}; font-size:1.5rem;"></i>
                <div style="color:#f8fafc;">{text}</div>
            </div>
            """, unsafe_allow_html=True)

# ── Footer ─────────────────────────────────────────────────────────────────────
st.markdown("""
<div style="margin-top:4rem; text-align:center; color:#475569; font-size:0.85rem; border-top:1px solid rgba(255,255,255,0.05); padding-top:2rem;">
    <strong>Core2 Enterprise Architecture</strong><br>
    M5Stack Core2 | ENV III | TVOC | PIR<br>
    Engineered with Google Cloud Platform & Gemini AI
</div>
""", unsafe_allow_html=True)
