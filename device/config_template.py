# =============================================================================
# config_template.py  –  M5Stack Core2 Weather Station
# =============================================================================
# Copy this file to config.py and fill in your real values.
# config.py is in .gitignore — NEVER commit it with real credentials.
# =============================================================================

# ─── WiFi (in-app WiFi switcher) ─────────────────────────────────────────────
WIFI_SSID     = "YOUR_WIFI_SSID"
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
WIFI_TIMEOUT  = 30  # seconds

# ─── Location ────────────────────────────────────────────────────────────────
LOCATION        = "Lausanne,CH"   # city,country-code  OR  "lat=46.52&lon=6.63"
TIMEZONE_OFFSET = 2               # hours ahead of UTC (CEST = +2)

# ─── Middleware (Flask API) ───────────────────────────────────────────────────
MIDDLEWARE_URL = "http://your-middleware-server.com"

# ─── External APIs ───────────────────────────────────────────────────────────
OPENWEATHER_API_KEY = "your_openweathermap_key"   # https://openweathermap.org
OPENAI_API_KEY      = "your_openai_key"           # https://platform.openai.com

# ─── Alert thresholds ────────────────────────────────────────────────────────
ALERT_HUMIDITY_MIN   = 40    # % – alert when indoor humidity drops below this
ALERT_TVOC_MAX       = 500   # ppb – Total VOC threshold
ALERT_ECO2_MAX       = 1000  # ppm – eCO2 threshold

# ─── Timing intervals (seconds) ──────────────────────────────────────────────
SENSOR_READ_INTERVAL     = 30
CLOUD_UPLOAD_INTERVAL    = 300   # 5 min
WEATHER_REFRESH_INTERVAL = 1800  # 30 min
ANNOUNCE_COOLDOWN        = 3600  # 1 h – motion-triggered TTS cooldown
DISPLAY_TICK             = 5     # display refresh rate

# ─── Display ─────────────────────────────────────────────────────────────────
SCREEN_W = 320
SCREEN_H = 240

# Colour palette (RGB565 hex)
COL_BG       = 0x0d1b2a   # dark navy
COL_PANEL    = 0x1b2838
COL_WHITE    = 0xFFFFFF
COL_AMBER    = 0xFF9F00
COL_CYAN     = 0x00D4FF
COL_GREEN    = 0x00E676
COL_RED      = 0xFF4444
COL_YELLOW   = 0xFFEB3B
COL_BLUE     = 0x64B5F6
COL_GRAY     = 0x607D8B
COL_TOPBAR   = 0x1565C0
