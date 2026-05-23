"""
Voice routes — Google TTS and Gemini LLM Q&A endpoints.
"""
import uuid
from flask import Blueprint, request, jsonify, Response
from services.tts_service import synthesize_b64, synthesize
from services.llm_service import answer, generate_announcement

voice_bp = Blueprint("voice", __name__)

_audio_cache = {}

@voice_bp.route("/api/voice/tts.wav", methods=["GET"])
def tts_wav():
    """Stream raw WAV audio for the M5Stack playCloudWAV function."""
    audio_id = request.args.get("id")
    if audio_id and audio_id in _audio_cache:
        return Response(_audio_cache[audio_id], mimetype="audio/wav")
        
    text = request.args.get("text", "").strip()
    if not text:
        return "No text or id", 400
        
    audio_bytes = synthesize(text)
    if not audio_bytes:
        return "TTS failed", 500
        
    return Response(audio_bytes, mimetype="audio/wav")


@voice_bp.route("/api/voice/tts", methods=["POST"])
def tts():
    """
    Convert text to speech using Google Cloud TTS.
    Request body: {"text": "Hello world"}
    Response: {"status": "ok", "audio_b64": "<base64 WAV>"}
    """
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text", "").strip()

    if not text:
        return jsonify({"status": "error", "message": "No text provided"}), 400

    audio_b64 = synthesize_b64(text)
    if audio_b64 is None:
        return jsonify({"status": "error", "message": "TTS failed"}), 500

    return jsonify({"status": "ok", "audio_b64": audio_b64}), 200


@voice_bp.route("/api/voice/query", methods=["POST"])
def voice_query():
    """
    Answer a natural language question using Gemini with sensor context.
    Request body: {"query": "What is the temperature?", "context": {...}}
    Response: {"status": "ok", "answer": "The temperature is 22.5°C.", "audio_id": "..."}
    """
    data = request.get_json(force=True, silent=True) or {}
    query   = data.get("query", "").strip()
    context = data.get("context", {})

    if not query:
        response_text = generate_announcement(context)
    else:
        response_text = answer(query, context)

    if response_text is None:
        return jsonify({"status": "error", "message": "LLM unavailable"}), 500

    # Cache audio to avoid URL length limits on the ESP32
    audio_bytes = synthesize(response_text)
    audio_id = None
    if audio_bytes:
        audio_id = str(uuid.uuid4())[:8]
        _audio_cache[audio_id] = audio_bytes

    return jsonify({"status": "ok", "answer": response_text, "audio_id": audio_id}), 200


@voice_bp.route("/api/voice/announce", methods=["POST"])
def announce():
    """
    Generate a proactive announcement (used on motion detection).
    Request body: {"context": {...}}
    Response: {"status": "ok", "text": "...", "audio_b64": "..."}
    The device can optionally use audio_b64 or generate its own TTS from the text.
    """
    data    = request.get_json(force=True, silent=True) or {}
    context = data.get("context", {})

    text = generate_announcement(context)

    # Optionally include TTS audio
    include_audio = data.get("include_audio", False)
    audio_b64 = None
    if include_audio:
        audio_b64 = synthesize_b64(text)

    result = {"status": "ok", "text": text}
    if audio_b64:
        result["audio_b64"] = audio_b64

    return jsonify(result), 200
