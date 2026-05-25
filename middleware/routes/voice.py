"""
Voice routes — Google TTS, Google STT, and Gemini LLM Q&A endpoints.
Integrates the tts-module-main robust logic.
"""
import uuid
import base64
import traceback
from flask import Blueprint, request, jsonify, Response

# Import the newly copied tts module logic
from tts import service
from tts import announcements
from tts import stt
from tts import llm

voice_bp = Blueprint("voice", __name__)

_device_command_queue = []

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
        audio_bytes = service.get_audio(text)
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
        text = announcements.build_announcement_text(event_type)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400

    try:
        audio_bytes = service.get_audio(text)
    except Exception as e:
        return jsonify({"error": f"Service TTS indisponible: {e}\n\nTRACEBACK:\n{traceback.format_exc()}"}), 503

    announcements.mark_announced(event_type)

    return jsonify({
        "status": "ok",
        "text": text
    }), 200

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
        return jsonify({"error": f"Service de transcription indisponible: {e}\n\nTRACEBACK:\n{traceback.format_exc()}"}), 503

    if not transcription:
        # Fallback if no voice was detected
        reponse_texte = "Desole, je n'ai pas bien compris. Pouvez-vous repeter ?"
        transcription = "..."
    else:
        try:
            reponse_texte = llm.generate_reply(transcription)
        except Exception as e:
            return jsonify({"error": f"Service LLM indisponible: {e}\n\nTRACEBACK:\n{traceback.format_exc()}"}), 503

    try:
        audio_reponse = service.get_audio(reponse_texte)
    except Exception as e:
        return jsonify({"error": f"Service TTS indisponible: {e}\n\nTRACEBACK:\n{traceback.format_exc()}"}), 503

    return jsonify({
        "status": "ok",
        "transcript": transcription,
        "answer": reponse_texte
    }), 200

