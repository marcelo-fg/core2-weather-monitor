"""
API client for the middleware — used by the Streamlit dashboard.
"""
import os
import requests
import logging

logger = logging.getLogger(__name__)

MIDDLEWARE_URL = os.environ.get("MIDDLEWARE_URL", "http://localhost:8080")
TIMEOUT = 10


def _get(path: str, params: dict = None) -> dict | None:
    try:
        r = requests.get(f"{MIDDLEWARE_URL}{path}", params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"API GET {path} failed: {e}")
        return None


def _post(path: str, payload: dict) -> dict | None:
    try:
        r = requests.post(
            f"{MIDDLEWARE_URL}{path}",
            json=payload,
            timeout=TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"API POST {path} failed: {e}")
        return None


# ---------- Sensor ----------

def get_latest() -> dict | None:
    data = _get("/api/sensor/latest")
    return data.get("data") if data else None


def get_history(hours: int = 24) -> list:
    data = _get("/api/sensor/history", {"hours": hours})
    return data.get("data", []) if data else []


def post_sensor(reading: dict) -> bool:
    data = _post("/api/sensor", reading)
    return data is not None and data.get("status") == "ok"


# ---------- Weather ----------

def get_weather(location: str = None) -> dict:
    params = {"location": location} if location else {}
    data = _get("/api/weather", params)
    return data or {}


# ---------- Voice / LLM ----------

def ask_llm(query: str, context: dict) -> str | None:
    data = _post("/api/voice/query", {"query": query, "context": context})
    return data.get("answer") if data else None


def get_announcement(context: dict, include_audio: bool = False) -> dict | None:
    payload = {"context": context, "include_audio": include_audio}
    return _post("/api/voice/announce", payload)

def post_device_command(cmd_type: str, cmd_value) -> bool:
    data = _post("/api/device/command", {"type": cmd_type, "value": cmd_value})
    return data is not None and data.get("status") == "ok"

def post_stt_only(audio_bytes: bytes) -> dict | None:
    try:
        r = requests.post(
            f"{MIDDLEWARE_URL}/api/voice/stt_only",
            data=audio_bytes,
            headers={"Content-Type": "application/octet-stream"},
            timeout=15
        )
        r.raise_for_status()
        return r.json()
    except Exception as e:
        logger.error(f"API POST stt_only failed: {e}")
        return None

def post_process_text_to_device(text: str, context: dict) -> dict | None:
    return _post("/api/voice/process_text_to_device", {"text": text, "context": context})
