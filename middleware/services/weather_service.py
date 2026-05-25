"""
OpenWeatherMap service — fetches current weather and 5-day forecast.
"""
import logging
import requests
from config import OPENWEATHER_API_KEY, DEFAULT_LOCATION

logger = logging.getLogger(__name__)

OWM_BASE = "https://api.openweathermap.org/data/2.5"


def _get(endpoint: str, params: dict) -> dict | None:
    params["appid"] = OPENWEATHER_API_KEY
    params["units"] = "metric"
    try:
        r = requests.get(f"{OWM_BASE}/{endpoint}", params=params, timeout=10)
        data = r.json()
        if str(data.get("cod", 200)) not in ("200", "0", 200):
            logger.error(f"OWM error [{endpoint}]: {data.get('message')}")
            return None
        return data
    except Exception as e:
        logger.error(f"OWM request failed [{endpoint}]: {e}")
        return None


def get_current(location: str = None) -> dict | None:
    """Return current weather for a location."""
    loc = location or DEFAULT_LOCATION
    data = _get("weather", {"q": loc})
    if data is None:
        return None
    try:
        return {
            "temp":        data["main"]["temp"],
            "feels_like":  data["main"]["feels_like"],
            "humidity":    data["main"]["humidity"],
            "pressure":    data["main"]["pressure"],
            "description": data["weather"][0]["description"].capitalize(),
            "condition":   data["weather"][0]["main"],
            "wind_speed":  data["wind"]["speed"],
            "icon":        data["weather"][0]["icon"],
            "location":    loc,
        }
    except (KeyError, IndexError) as e:
        logger.error(f"OWM parse error: {e}")
        return None


def get_forecast(location: str = None) -> dict:
    """Return 5-day daily forecast and next 5 3-hour blocks."""
    loc = location or DEFAULT_LOCATION
    data = _get("forecast", {"q": loc, "cnt": 40})
    if data is None:
        return {"daily": [], "hourly": []}

    DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
    
    # 1. Hourly (NOW + next 5 blocks)
    hourly = []
    
    # First block is NOW
    current = get_current(loc)
    if current:
        hourly.append({
            "time": "NOW",
            "temp": current["temp"],
            "condition": current["condition"],
            "icon": current["icon"]
        })
    else:
        # Fallback if current fails but forecast works
        hourly.append({
            "time": "NOW",
            "temp": 0,
            "condition": "Unknown",
            "icon": "01d"
        })
        
    import datetime
    from config import TIMEZONE_OFFSET
    now_utc = datetime.datetime.utcnow().timestamp()
    
    # Filter out blocks that are in the past
    future_blocks = [item for item in data.get("list", []) if item["dt"] > now_utc]
    
    for item in future_blocks[:5]:
        dt = datetime.datetime.utcfromtimestamp(item["dt"]) + datetime.timedelta(hours=TIMEZONE_OFFSET)
        hourly.append({
            "time": dt.strftime("%H:%M"),
            "temp": item["main"]["temp"],
            "condition": item["weather"][0]["main"],
            "icon": item["weather"][0]["icon"]
        })

    # 2. Daily
    days: dict = {}
    for item in data.get("list", []):
        dt = datetime.datetime.utcfromtimestamp(item["dt"]) + datetime.timedelta(hours=TIMEZONE_OFFSET)
        label = dt.strftime("%d/%m")
        dow = DAYS[dt.weekday()]
        if label not in days:
            days[label] = {
                "day_name": dow,
                "date": label,
                "temps": [],
                "condition": item["weather"][0]["main"],
                "icon": item["weather"][0]["icon"],
                "rain_list": [],
            }
        days[label]["temps"].append(item["main"]["temp"])
        days[label]["rain_list"].append(item.get("pop", 0))

    result = []
    for label, d in days.items():
        result.append({
            "day_name":  d["day_name"],
            "date":      d["date"],
            "temp_max":  max(d["temps"]),
            "temp_min":  min(d["temps"]),
            "condition": d["condition"],
            "icon":      d["icon"],
            "rain_prob": max(d["rain_list"]) if d["rain_list"] else 0,
        })
        if len(result) >= 8:
            break
            
    return {"daily": result, "hourly": hourly}


def get_full_weather(location: str = None) -> dict:
    """Return combined current + forecast."""
    return {
        "current":  get_current(location),
        "forecast": get_forecast(location),
    }
