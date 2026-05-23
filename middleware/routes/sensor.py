"""
Sensor routes — handles all /api/sensor/* endpoints.
"""
from flask import Blueprint, request, jsonify
from datetime import datetime, timezone
from services.bigquery_service import insert_reading, get_latest_reading, get_history

sensor_bp = Blueprint("sensor", __name__)


@sensor_bp.route("/api/sensor", methods=["POST"])
def post_sensor():
    """Receive a sensor reading from the M5Stack and store it in BigQuery."""
    data = request.get_json(force=True, silent=True)
    if not data:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    # Inject UTC timestamp if not provided
    if "timestamp" not in data:
        data["timestamp"] = datetime.now(timezone.utc).isoformat()

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
        hours = min(max(hours, 1), 168)  # clamp 1h–1week
    except ValueError:
        hours = 24

    rows = get_history(hours)

    # Convert timestamps and format for device display
    formatted = []
    for row in rows:
        for k, v in row.items():
            if hasattr(v, "isoformat"):
                row[k] = v.isoformat()
        # Add a display label for the History page
        ts_str = row.get("timestamp", "")
        try:
            dt = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
            row["time_label"] = f"{dt.hour:02d}:{dt.minute:02d}"
        except Exception:
            row["time_label"] = "--:--"
        formatted.append(row)

    return jsonify({"status": "ok", "data": formatted}), 200
