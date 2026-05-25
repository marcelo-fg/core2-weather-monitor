"""Mock API client for local preview — returns realistic dummy data."""
import datetime

def get_latest():
    return {
        "temperature": 22.4,
        "humidity": 58.0,
        "tvoc": 142,
        "eco2": 720,
        "aq_label": "GOOD",
        "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }

def get_history(hours=24):
    import random
    now = datetime.datetime.now(datetime.timezone.utc)
    rows = []
    for i in range(hours):
        ts = now - datetime.timedelta(hours=hours - i)
        rows.append({
            "timestamp": ts.isoformat(),
            "temperature": round(20 + 4 * (0.5 - random.random()), 1),
            "humidity": round(55 + 10 * (0.5 - random.random()), 1),
            "tvoc": int(100 + 100 * random.random()),
            "eco2": int(600 + 300 * random.random()),
        })
    return rows

def get_weather():
    now = datetime.datetime.now(datetime.timezone.utc)
    hourly = []
    for i in range(6):
        h = (now + datetime.timedelta(hours=i + 1))
        hourly.append({
            "time": h.strftime("%Hh"),
            "temp": round(14 + i * 0.5, 1),
            "icon": ["01d", "02d", "03d", "10d", "01d", "02d"][i],
        })
    daily = [
        {"day_name": (now + datetime.timedelta(days=i)).strftime("%A"), "icon": "01d", "temp_min": 10 + i, "temp_max": 20 + i}
        for i in range(5)
    ]
    return {
        "current": {
            "temp": 14.2,
            "humidity": 72,
            "wind_speed": 3.5,
            "pressure": 1015,
            "description": "partly cloudy",
            "icon": "02d",
        },
        "forecast": {
            "hourly": hourly,
            "daily": daily,
        },
    }

def ask_llm(query, context):
    return "Conditions agréables avec un ciel partiellement nuageux — une légère veste suffira."

def post_device_command(cmd_type, cmd_value):
    return True

def post_stt_only(audio_bytes):
    return {"status": "ok", "transcript": "Quelle est la météo aujourd'hui ?"}

def post_process_text_to_device(text, context):
    return {"status": "ok"}
