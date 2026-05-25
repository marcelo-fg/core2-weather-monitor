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
TTS_LANGUAGE_CODE    = os.environ.get("TTS_LANGUAGE_CODE", "fr-FR")
TTS_VOICE_NAME       = os.environ.get("TTS_VOICE_NAME", "fr-FR-Wavenet-C")
TTS_SPEAKING_RATE    = float(os.environ.get("TTS_SPEAKING_RATE", "1.0"))
TTS_PITCH            = float(os.environ.get("TTS_PITCH", "0.0"))
TTS_SAMPLE_RATE_HZ   = int(os.environ.get("TTS_SAMPLE_RATE_HZ", "24000"))
AUDIO_CACHE_DIR      = os.environ.get("AUDIO_CACHE_DIR", "static/audio")
RATE_LIMIT_SECONDS   = int(os.environ.get("RATE_LIMIT_SECONDS", "3600"))

# STT
STT_LANGUAGE_CODE    = os.environ.get("STT_LANGUAGE_CODE", "fr-FR")
STT_SAMPLE_RATE_HZ   = int(os.environ.get("STT_SAMPLE_RATE_HZ", "8000"))

# LLM
GEMINI_MODEL         = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
LLM_SYSTEM_PROMPT    = os.environ.get("LLM_SYSTEM_PROMPT", "Tu es un assistant météo intelligent installé dans une maison. Tu as accès aux données de température, humidité et qualité de l'air. Réponds en français, de façon concise (2-3 phrases max).")
