"""
Flask middleware application — main entry point.
Exposes all REST API endpoints for the M5Stack device and Streamlit dashboard.
"""
import logging
import os
from flask import Flask, jsonify
from flask_cors import CORS

# Import blueprints
from routes.sensor  import sensor_bp
from routes.weather import weather_bp
from routes.voice   import voice_bp

# Import BigQuery initializer
from services.bigquery_service import ensure_dataset_and_table

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# App factory
# ---------------------------------------------------------------------------

def create_app() -> Flask:
    app = Flask(__name__)
    CORS(app)  # Allow Streamlit dashboard cross-origin requests

    # Register blueprints
    app.register_blueprint(sensor_bp)
    app.register_blueprint(weather_bp)
    app.register_blueprint(voice_bp)

    # Health check endpoint (used by Cloud Run)
    @app.route("/health", methods=["GET"])
    def health():
        return jsonify({"status": "ok", "service": "core2-middleware"}), 200

    @app.route("/", methods=["GET"])
    def index():
        return jsonify({
            "service": "Core2 Weather Monitor — Middleware",
            "version": "1.0.0",
            "endpoints": [
                "POST /api/sensor",
                "GET  /api/sensor/latest",
                "GET  /api/sensor/history?hours=24",
                "GET  /api/sensor/history_weekly",
                "GET  /api/time",
                "GET  /api/weather?location=Lausanne,CH",
                "GET  /api/weather/current",
                "GET  /api/weather/forecast",
                "GET  /api/voice/tts.wav?text=...",
                "POST /api/voice/query",
                "POST /api/voice/listen",
                "POST /api/voice/announce",
                "GET  /api/voice/smart_welcome",
                "GET  /api/device/sync",
                "POST /api/device/command",
            ],
        }), 200

    return app


# ---------------------------------------------------------------------------
# Bootstrap
# ---------------------------------------------------------------------------
app = create_app()

if __name__ == "__main__":
    # Ensure BigQuery dataset and table exist on startup
    try:
        ensure_dataset_and_table()
        logger.info("BigQuery dataset and table verified.")
    except Exception as e:
        logger.warning(f"BigQuery setup warning (will retry on first request): {e}")

    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)
