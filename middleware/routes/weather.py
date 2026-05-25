"""
Weather route — proxies OpenWeatherMap requests for the M5Stack device.
"""
from flask import Blueprint, request, jsonify
from services.weather_service import get_full_weather, get_current, get_forecast

weather_bp = Blueprint("weather", __name__)


@weather_bp.route("/api/time", methods=["GET"])
def get_time():
    """Return the current UTC timestamp for the device to sync its clock."""
    import time
    return jsonify({"status": "ok", "unixtime": int(time.time())}), 200

@weather_bp.route("/api/weather", methods=["GET"])
def weather():
    """
    Return current weather and 5-day forecast.
    Query param: ?location=Lausanne,CH (optional, defaults to config)
    """
    location = request.args.get("location", None)
    data = get_full_weather(location)

    if data.get("current") is None and not data.get("forecast"):
        return jsonify({
            "status": "error",
            "message": "Unable to fetch weather data"
        }), 503

    return jsonify({"status": "ok", **data}), 200


@weather_bp.route("/api/weather/current", methods=["GET"])
def weather_current():
    """Return only current weather conditions."""
    location = request.args.get("location", None)
    current = get_current(location)
    if current is None:
        return jsonify({"status": "error", "message": "Weather unavailable"}), 503
    return jsonify({"status": "ok", "current": current}), 200


@weather_bp.route("/api/weather/forecast", methods=["GET"])
def weather_forecast():
    """Return only the 5-day forecast."""
    location = request.args.get("location", None)
    forecast = get_forecast(location)
    return jsonify({"status": "ok", "forecast": forecast}), 200
