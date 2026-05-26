"""
Announcement text templates + per-event rate limiting.

Each ``event_type`` maps to a short English sentence rendered through TTS by
the ``/api/voice/announce`` route. The same event cannot be announced twice
within ``config.RATE_LIMIT_SECONDS`` (default: 1 hour).
"""

import time

import config


# Placeholder values used when the caller does not pass real sensor/weather data.
FAKE_WEATHER_DATA = {
    "temp": 18,        # outdoor temperature in °C
    "rain": True,      # is rain expected today?
    "humidity": 35,    # indoor humidity in %
}


# In-memory map: event_type -> timestamp of its last successful emission.
# Reset whenever the server restarts (no database needed).
_last_announced = {}


def build_announcement_text(event_type, data=None):
    """Return the English text for ``event_type``.

    Supported events: ``morning_briefing``, ``humidity_alert``,
    ``air_quality_alert``, ``welcome``, ``weather_update``.

    Raises ``ValueError`` if the event type is unknown.
    """
    if data is None:
        data = FAKE_WEATHER_DATA

    if event_type == "morning_briefing":
        text = (
            "Good morning! Here is your daily briefing. "
            "The outdoor temperature is {temp} degrees."
        ).format(temp=data.get("temp", "unknown"))
        if data.get("rain"):
            text += " Rain is expected today, don't forget to take an umbrella."
        return text

    if event_type == "humidity_alert":
        return (
            "Warning, indoor humidity is low, at only {h} percent. "
            "Consider ventilating or using a humidifier."
        ).format(h=data.get("humidity", "unknown"))

    if event_type == "air_quality_alert":
        return (
            "Warning, indoor air quality is poor. "
            "It is recommended to open the windows to ventilate the room."
        )

    if event_type == "welcome":
        return "Welcome home! Nice to see you again."

    if event_type == "weather_update":
        return (
            "Current weather: it is {temp} degrees outside."
        ).format(temp=data.get("temp", "unknown"))

    raise ValueError("Unknown event type: " + str(event_type))


def is_rate_limited(event_type):
    """Return True if ``event_type`` was emitted less than the rate-limit window ago."""
    last = _last_announced.get(event_type)
    if last is None:
        return False
    return (time.time() - last) < config.RATE_LIMIT_SECONDS


def mark_announced(event_type):
    """Record that ``event_type`` was just emitted successfully."""
    _last_announced[event_type] = time.time()
