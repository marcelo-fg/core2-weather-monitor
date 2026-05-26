"""
Sensor routes — handles all /api/sensor/* endpoints.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
from services.bigquery_service import insert_reading, get_latest_reading, get_history
from services.weather_service import get_full_weather

sensor_bp = Blueprint("sensor", __name__)


@sensor_bp.route("/api/sensor", methods=["POST"])
def post_sensor():
    """Receive a sensor reading from the M5Stack and store it in BigQuery."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    # Always inject server UTC timestamp (M5Stack caches the old one on boot)
    data["timestamp"] = datetime.now(timezone.utc).isoformat()

    try:
        w = get_full_weather("Lausanne,CH")
        c = w.get("current", {})
        # get_current() renvoie la clé "temp" (pas "temperature") -> bug corrigé.
        data["outdoor_temp"] = c.get("temp")
        data["outdoor_humidity"] = c.get("humidity")
        data["outdoor_wind"] = c.get("wind_speed")
        data["outdoor_desc"] = c.get("condition")
        data["outdoor_condition"] = c.get("icon")
    except Exception:
        pass

    ok = insert_reading(data)
    if ok:
        return jsonify({"status": "ok"}), 200
    else:
        return jsonify({"status": "error", "message": "BigQuery insert failed"}), 500


@sensor_bp.route("/api/sensor/latest", methods=["GET"])
def get_latest():
    """Return the most recent sensor reading from BigQuery."""
    row = get_latest_reading()
    if row is None:
        return jsonify({"status": "ok", "data": None}), 200

    # Convert BigQuery Timestamps to ISO strings
    for k, v in row.items():
        if hasattr(v, "isoformat"):
            row[k] = v.isoformat()

    return jsonify({"status": "ok", "data": row}), 200


@sensor_bp.route("/api/sensor/history", methods=["GET"])
def get_sensor_history():
    """Return sensor history for the last N hours (default: 24)."""
    try:
        hours = int(request.args.get("hours", 24))
        hours = min(max(hours, 1), 744)  # clamp 1h–31days
    except ValueError:
        hours = 24

    rows = get_history(hours)

    # Downsample by grouping into hourly buckets
    buckets = {}
    for row in rows:
        ts = row.get("timestamp")
        if not ts: continue
        # Truncate to hour
        try:
            hour_key = ts.replace(minute=0, second=0, microsecond=0)
            if hour_key not in buckets:
                buckets[hour_key] = {"temp": [], "out_temp": [], "hum": [], "tvoc": [], "eco2": []}
            
            t = row.get("temperature")
            if t is not None: buckets[hour_key]["temp"].append(t)
            ot = row.get("outdoor_temp")
            if ot is not None: buckets[hour_key]["out_temp"].append(ot)
            h = row.get("humidity")
            if h is not None: buckets[hour_key]["hum"].append(h)
            v = row.get("tvoc")
            if v is not None: buckets[hour_key]["tvoc"].append(v)
            e = row.get("eco2")
            if e is not None: buckets[hour_key]["eco2"].append(e)
        except Exception:
            pass

    formatted = []
    for hk in sorted(buckets.keys()):
        b = buckets[hk]
        avg_temp = sum(b["temp"]) / len(b["temp"]) if b["temp"] else None
        avg_out = sum(b["out_temp"]) / len(b["out_temp"]) if b["out_temp"] else None
        avg_hum = sum(b["hum"]) / len(b["hum"]) if b["hum"] else None
        avg_tvoc = sum(b["tvoc"]) / len(b["tvoc"]) if b["tvoc"] else None
        avg_eco2 = sum(b["eco2"]) / len(b["eco2"]) if b["eco2"] else None
        formatted.append({
            "timestamp": hk.isoformat(),
            "time_label": f"{hk.hour:02d}:00",
            "temperature": avg_temp,
            "outdoor_temp": avg_out,
            "humidity": avg_hum,
            "tvoc": avg_tvoc,
            "eco2": avg_eco2
        })

    return jsonify({"status": "ok", "data": formatted}), 200


@sensor_bp.route("/api/sensor/history_weekly", methods=["GET"])
def get_sensor_history_weekly():
    """Return aggregated weekly data for the complex Dashboard."""
    rows = get_history(168)  # 7 days

    day_buckets = {i: {"in": [], "out": []} for i in range(7)}
    humidity_list = []
    eco2_list = []
    
    for row in rows:
        ts = row.get("timestamp")
        if not ts: continue
        
        try:
            dow = ts.weekday()
            
            t = row.get("temperature")
            if t is not None: day_buckets[dow]["in"].append(t)
            
            ot = row.get("outdoor_temp")
            if ot is not None: day_buckets[dow]["out"].append(ot)
            
            h = row.get("humidity")
            if h is not None: humidity_list.append(h)
            
            e = row.get("eco2")
            if e is not None: eco2_list.append(e)
                
        except Exception:
            pass

    weekly_bars = []
    days_names = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]

    # Données RÉELLES uniquement. Les jours sans mesure sont à 0 (le firmware
    # affiche alors une barre minimale) — pas de données fabriquées.
    for i in range(7):
        b = day_buckets[i]
        avg_in  = sum(b["in"])  / len(b["in"])  if b["in"]  else 0
        avg_out = sum(b["out"]) / len(b["out"]) if b["out"] else 0
        weekly_bars.append({
            "day": days_names[i],
            "in": avg_in,
            "out": avg_out
        })

    avg_humidity = sum(humidity_list) / len(humidity_list) if humidity_list else 0
    avg_eco2 = sum(eco2_list) / len(eco2_list) if eco2_list else 0

    data = {
        "bars": weekly_bars,
        "humidity": int(avg_humidity),
        "eco2": int(avg_eco2)
    }

    return jsonify({"status": "ok", "data": data}), 200

@sensor_bp.route("/api/time", methods=["GET"])
def get_time():
    """Returns the exact local time in Switzerland to fix M5Stack timezone bugs."""
    try:
        from zoneinfo import ZoneInfo
        tz = ZoneInfo("Europe/Zurich")
    except ImportError:
        tz = timezone.utc
    
    now = datetime.now(tz)
    return jsonify({
        "status": "ok", 
        "datetime": now.isoformat()
    }), 200
