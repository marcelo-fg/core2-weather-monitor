"""
Voice routes — Google TTS, Google STT, and Gemini LLM Q&A endpoints.
Integrates the tts-module-main robust logic.
"""
import logging
import time

from flask import Blueprint, request, jsonify, Response

logger = logging.getLogger(__name__)

# Import the newly copied tts module logic
from tts import service
from tts import announcements
from tts import stt
from tts import llm

# Live data sources, so the assistant answers with the REAL sensor + weather values.
from services.bigquery_service import get_latest_reading
from services.weather_service import get_current, get_forecast

voice_bp = Blueprint("voice", __name__)

_device_command_queue = []


def _build_live_context():
    """Récupère la dernière mesure (BigQuery) + la météo (OpenWeather) pour
    nourrir le LLM avec des données réelles. Tolérant aux pannes (renvoie ce
    qu'il a pu récupérer)."""
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
        # Prévisions des prochains jours (pour répondre à "quel temps demain ?").
        daily = (get_forecast() or {}).get("daily", [])[:3]
        if daily:
            ctx["forecast"] = [
                {"jour": d.get("day_name"), "date": d.get("date"),
                 "min": d.get("temp_min"), "max": d.get("temp_max"),
                 "ciel": d.get("condition"), "pluie": d.get("rain_prob")}
                for d in daily
            ]
    except Exception:
        pass
    return ctx


def _build_announce_data():
    """Données réelles pour les annonces (temp extérieure, humidité intérieure).
    Renvoie None si rien n'a pu être récupéré (announcements retombe alors sur
    ses valeurs par défaut)."""
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
        print(f"[DEVICE CMD] Added: {cmd_type} -> {cmd_value}")
        return jsonify({"status": "ok"})
    return jsonify({"status": "error", "message": "Missing type"}), 400


@voice_bp.route("/api/voice/tts.wav", methods=["GET"])
def tts_wav():
    """Stream raw WAV audio (used by cache or direct text)."""
    text = request.args.get("text", "").strip()
    if not text:
        return "No text", 400
        
    try:
        t0 = time.time()
        audio_bytes = service.get_audio(text)
        logger.info("TTS.wav: %d octets en %.2fs (texte %d car.)",
                    len(audio_bytes), time.time() - t0, len(text))
        return Response(audio_bytes, mimetype="audio/wav")
    except Exception as e:
        return str(e), 503

@voice_bp.route("/api/voice/announce", methods=["POST"])
def announce():
    """
    Generate a proactive announcement.
    If 'force' is False, applies rate-limiting.
    Returns JSON with text and audio_b64.
    """
    data = request.get_json(silent=True) or {}
    event_type = data.get("event_type", "welcome")
    force = bool(data.get("force", False))

    if not force and announcements.is_rate_limited(event_type):
        return jsonify({"error": f"Annonce '{event_type}' déjà émise récemment."}), 429

    try:
        text = announcements.build_announcement_text(event_type, _build_announce_data())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        audio_bytes = service.get_audio(text)
    except Exception as e:
        return jsonify({"error": f"Service TTS indisponible: {e}"}), 503

    announcements.mark_announced(event_type)

    return jsonify({
        "status": "ok",
        "text": text
    }), 200

@voice_bp.route("/api/voice/query", methods=["POST"])
def query():
    """Question/réponse en TEXTE (sans audio) — utilisé par le dashboard Streamlit.

    Entrée (JSON) : {"query": "...", "context": {...}}  (context optionnel)
    Sortie (succès) : {"status": "ok", "answer": "..."}
    """
    data = request.get_json(silent=True) or {}
    user_query = str(data.get("query", "")).strip()
    if not user_query:
        return jsonify({"error": "Le champ 'query' est obligatoire."}), 400

    # Si le dashboard fournit un contexte, on l'utilise ; sinon on récupère les
    # données réelles en direct (BigQuery + météo).
    context = data.get("context") or _build_live_context()

    try:
        answer = llm.generate_reply(user_query, context)
    except Exception as e:
        return jsonify({"error": f"Service LLM indisponible: {e}"}), 503

    return jsonify({"status": "ok", "answer": answer}), 200


@voice_bp.route("/api/voice/listen", methods=["POST"])
def listen():
    """
    Conversation mode: receives audio, returns JSON with transcript, answer, and audio_b64.
    """
    if "audio" in request.files:
        audio_bytes = request.files["audio"].read()
    else:
        audio_bytes = request.get_data()

    if not audio_bytes:
        return jsonify({"error": "Aucun audio reçu."}), 400

    try:
        transcription = stt.transcribe_wav(audio_bytes)
    except Exception as e:
        return jsonify({"error": f"Service de transcription indisponible: {e}"}), 503

    if not transcription:
        # Fallback if no voice was detected
        reponse_texte = "Désolé, je n'ai pas bien compris. Pouvez-vous répéter ?"
        transcription = "..."
    else:
        try:
            # On injecte les vraies données capteurs + météo dans le prompt.
            reponse_texte = llm.generate_reply(transcription, _build_live_context())
        except Exception as e:
            return jsonify({"error": f"Service LLM indisponible: {e}"}), 503

    # NOTE: on ne synthétise PAS l'audio ici. Le M5 récupère l'audio via
    # GET /api/voice/tts.wav après avoir reçu ce JSON → le texte s'affiche
    # immédiatement (latence "réflexion" réduite), puis la voix est jouée.
    return jsonify({
        "status": "ok",
        "transcript": transcription,
        "answer": reponse_texte
    }), 200

@voice_bp.route("/api/voice/stt_only", methods=["POST"])
def stt_only():
    """
    STT mode only: receives audio bytes, returns JSON with transcript.
    Used by Streamlit dashboard audio_input.
    """
    if "audio" in request.files:
        audio_bytes = request.files["audio"].read()
    else:
        audio_bytes = request.get_data()

    if not audio_bytes:
        return jsonify({"error": "Aucun audio reçu."}), 400

    try:
        from google.cloud import speech
        client = speech.SpeechClient()
        
        # Streamlit sends a standard WAV file. Google STT can auto-detect WAV 
        # (with LINEAR16 encoding) if we simply pass the content and language.
        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            language_code="fr-FR",
            enable_automatic_punctuation=True
        )
        
        response = client.recognize(config=config, audio=audio)
        
        morceaux = []
        for result in response.results:
            if result.alternatives:
                morceaux.append(result.alternatives[0].transcript)
        transcription = " ".join(morceaux).strip()
        
        return jsonify({"status": "ok", "text": transcription}), 200
    except Exception as e:
        logger.error(f"STT Error: {e}")
        return jsonify({"error": f"Service de transcription indisponible: {e}"}), 503

