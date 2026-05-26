"""
Voice-assistant HTTP routes.

Endpoints:
- GET  /api/device/sync         : the device pulls queued remote commands.
- POST /api/device/command      : the dashboard enqueues a command for the device.
- GET  /api/voice/tts.wav       : Google TTS — text -> WAV stream.
- POST /api/voice/announce      : pre-canned announcements (rate-limited).
- GET  /api/voice/smart_welcome : 1-sentence context-aware greeting.
- POST /api/voice/query         : text Q&A (used by the dashboard).
- POST /api/voice/listen        : full conversation (audio -> STT -> Gemini -> JSON).
"""

import logging
import time

from flask import Blueprint, request, jsonify, Response

import config
from tts import service
from tts import announcements
from tts import stt
from tts import llm

# Live data sources so the assistant answers with REAL sensor + weather values.
from services.bigquery_service import get_latest_reading, get_history_summary
from services.weather_service import get_current, get_forecast

logger = logging.getLogger(__name__)

voice_bp = Blueprint("voice", __name__)

# In-memory queue of pending commands for the device. The dashboard POSTs into
# it via /api/device/command; the device drains it via /api/device/sync.
_device_command_queue = []


def _build_live_context():
    """Return a context dict with the latest BigQuery reading + current weather
    + 3-day forecast. Resilient: returns whatever could be fetched."""
    ctx = {}
    try:
        latest = get_latest_reading() or {}
        ctx["temperature"] = latest.get("temperature")
        ctx["humidity"]    = latest.get("humidity")
        ctx["tvoc"]        = latest.get("tvoc")
        ctx["eco2"]        = latest.get("eco2")
        ctx["aq_label"]    = latest.get("aq_label")
    except Exception:
        pass
    try:
        cur = get_current() or {}
        ctx["outdoor_temp"]     = cur.get("temp")
        ctx["outdoor_desc"]     = cur.get("description")
        ctx["outdoor_humidity"] = cur.get("humidity")
        ctx["wind_speed"]       = cur.get("wind_speed")
    except Exception:
        pass
    try:
        daily = (get_forecast() or {}).get("daily", [])[:5]
        if daily:
            ctx["forecast"] = [
                {"day_name":  d.get("day_name"),
                 "date":      d.get("date"),
                 "temp_min":  d.get("temp_min"),
                 "temp_max":  d.get("temp_max"),
                 "condition": d.get("condition"),
                 "rain_prob": d.get("rain_prob")}
                for d in daily
            ]
    except Exception:
        pass
    # Aggregated indoor history (last 24 h + last 7 days) so the assistant can
    # answer questions about past data. Disable via env var LLM_INCLUDE_HISTORY.
    if config.LLM_INCLUDE_HISTORY:
        try:
            summary = get_history_summary()
            if summary:
                ctx["history"] = summary
        except Exception:
            pass
    return ctx


def _build_announce_data():
    """Return the real values used by announcement templates (outdoor temperature,
    indoor humidity). Falls back to ``None`` if nothing could be fetched, in
    which case the announcement module uses its placeholders."""
    d = {}
    try:
        cur = get_current() or {}
        if cur.get("temp") is not None:
            d["temp"] = round(cur["temp"])
    except Exception:
        pass
    try:
        latest = get_latest_reading() or {}
        if latest.get("humidity") is not None:
            d["humidity"] = round(latest["humidity"])
    except Exception:
        pass
    return d or None


@voice_bp.route("/api/device/sync", methods=["GET"])
def device_sync():
    global _device_command_queue
    commands = list(_device_command_queue)
    _device_command_queue.clear()
    return jsonify({"status": "ok", "commands": commands})


@voice_bp.route("/api/device/command", methods=["POST"])
def device_command():
    global _device_command_queue
    data = request.get_json(force=True, silent=True) or {}
    cmd_type = data.get("type")
    cmd_value = data.get("value")
    if cmd_type:
        _device_command_queue.append({"type": cmd_type, "value": cmd_value})
        logger.info("Device command queued: %s -> %s", cmd_type, cmd_value)
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "Missing type"}), 400


@voice_bp.route("/api/voice/tts.wav", methods=["GET"])
def tts_wav():
    """Stream raw WAV audio synthesized from the ``text`` query parameter."""
    text = request.args.get("text", "").strip()
    lang = request.args.get("lang", None)
    if not text:
        return "No text", 400

    try:
        t0 = time.time()
        audio_bytes = service.get_audio(text, lang_code=lang)
        logger.info("TTS.wav: %d bytes in %.2fs (text %d chars)",
                    len(audio_bytes), time.time() - t0, len(text))
        return Response(audio_bytes, mimetype="audio/wav")
    except Exception as e:
        return str(e), 503


@voice_bp.route("/api/voice/announce", methods=["POST"])
def announce():
    """Generate a proactive announcement (welcome, weather update, alert…).

    Rate-limited per event type unless the request sets ``force: true``.
    """
    data = request.get_json(silent=True) or {}
    event_type = data.get("event_type", "welcome")
    force = bool(data.get("force", False))

    if not force and announcements.is_rate_limited(event_type):
        return jsonify({"error": f"Announcement '{event_type}' was emitted recently."}), 429

    try:
        text = announcements.build_announcement_text(event_type, _build_announce_data())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        service.get_audio(text)   # warm the TTS cache; device fetches via /tts.wav
    except Exception as e:
        return jsonify({"error": f"TTS service unavailable: {e}"}), 503

    announcements.mark_announced(event_type)
    return jsonify({"status": "ok", "text": text}), 200


@voice_bp.route("/api/voice/smart_welcome", methods=["GET"])
def smart_welcome():
    """Return a 1-sentence English welcome adapted to the live context.

    Fast-path: if everything is in the normal range, skip Gemini entirely and
    return a fixed sentence (saves ~4 s of latency).
    """
    context = _build_live_context()

    is_normal = True
    if context.get("tvoc", 0) > 500: is_normal = False
    if context.get("eco2", 0) > 1000: is_normal = False
    if context.get("temperature", 20) > 30 or context.get("temperature", 20) < 15: is_normal = False
    desc = (context.get("outdoor_desc") or "").lower()
    if "storm" in desc or "rain" in desc or "snow" in desc: is_normal = False

    if is_normal:
        text = "Welcome back, everything is normal."
    else:
        prompt = (
            "The user just walked into the room. Give a 1-sentence welcome message in English. "
            "Briefly warn about the specific critical value (e.g., extreme heat, incoming storm, "
            "or bad air quality)."
        )
        try:
            text = llm.generate_reply(prompt, context)
        except Exception as e:
            logger.error("LLM smart_welcome error: %s", e)
            text = "Welcome back, everything is normal."

    return jsonify({"status": "ok", "text": text}), 200


@voice_bp.route("/api/voice/query", methods=["POST"])
def query():
    """Text-only Q&A used by the Streamlit dashboard.

    Input  (JSON): ``{"query": "...", "context": {...}}`` (context optional).
    Output (JSON): ``{"status": "ok", "answer": "..."}``.
    """
    data = request.get_json(silent=True) or {}
    user_query = str(data.get("query", "")).strip()
    if not user_query:
        return jsonify({"error": "The 'query' field is required."}), 400

    # Use the caller's context if provided, otherwise build it from live data.
    context = data.get("context") or _build_live_context()

    try:
        answer = llm.generate_reply(user_query, context)
    except Exception as e:
        return jsonify({"error": f"LLM service unavailable: {e}"}), 503

    return jsonify({"status": "ok", "answer": answer}), 200


@voice_bp.route("/api/voice/listen", methods=["POST"])
def listen():
    """Full voice conversation: audio -> STT -> Gemini -> JSON {transcript, answer}.

    The audio playback is intentionally NOT done here. The device fetches the
    audio via GET /api/voice/tts.wav after receiving this JSON, which lets the
    transcript appear on screen as soon as it is ready.
    """
    if "audio" in request.files:
        audio_bytes = request.files["audio"].read()
    else:
        audio_bytes = request.get_data()

    if not audio_bytes:
        return jsonify({"error": "No audio received."}), 400

    try:
        transcription = stt.transcribe_wav(audio_bytes)
    except Exception as e:
        return jsonify({"error": f"STT service unavailable: {e}"}), 503

    if not transcription:
        answer_text = "Sorry, I didn't catch that. Could you repeat?"
        transcription = "..."
    else:
        try:
            answer_text = llm.generate_reply(transcription, _build_live_context())
        except Exception as e:
            return jsonify({"error": f"LLM service unavailable: {e}"}), 503

    return jsonify({
        "status": "ok",
        "transcript": transcription,
        "answer": answer_text,
    }), 200
