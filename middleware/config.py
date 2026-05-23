"""
Middleware configuration — loaded from environment variables.
Never hardcode secrets in source code!
"""
import os

# Google Cloud
GOOGLE_CLOUD_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "core2-weather-monitor")
BIGQUERY_DATASET     = os.environ.get("BIGQUERY_DATASET", "weather_monitor")
BIGQUERY_TABLE       = os.environ.get("BIGQUERY_TABLE", "sensor_readings")

# External APIs
OPENWEATHER_API_KEY  = os.environ.get("OPENWEATHER_API_KEY", "")
GEMINI_API_KEY       = os.environ.get("GEMINI_API_KEY", "")

# Location defaults
DEFAULT_LOCATION     = os.environ.get("DEFAULT_LOCATION", "Lausanne,CH")
TIMEZONE_OFFSET      = int(os.environ.get("TIMEZONE_OFFSET", "2"))

# Alert thresholds
ALERT_HUMIDITY_MIN   = float(os.environ.get("ALERT_HUMIDITY_MIN", "40"))
ALERT_TVOC_MAX       = int(os.environ.get("ALERT_TVOC_MAX", "500"))
ALERT_ECO2_MAX       = int(os.environ.get("ALERT_ECO2_MAX", "1000"))

# TTS
TTS_LANGUAGE_CODE    = os.environ.get("TTS_LANGUAGE_CODE", "en-US")
TTS_VOICE_NAME       = os.environ.get("TTS_VOICE_NAME", "en-US-Neural2-C")
