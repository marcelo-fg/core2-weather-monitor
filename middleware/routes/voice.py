"""
Voice routes — Google TTS, Google STT, and Gemini LLM Q&A endpoints.
"""
import uuid
from flask import Blueprint, request, jsonify, Response
from services.tts_service import synthesize_b64, synthesize
from services.llm_service import answer, generate_announcement
from services.stt_service import transcribe_audio

voice_bp = Blueprint("voice", __name__)

_audio_cache = {}
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


@voice_bp.route("/api/voice/stt", methods=["POST"])
def speech_to_text():
    """
    Convert raw audio to text using Google Cloud STT, then answer via Gemini.
    Request body: {
        "audio":       "<base64 LINEAR16 PCM>",
        "language":    "fr-FR",         # optional, default fr-FR
        "sample_rate": 16000,           # optional, default 16000
        "context":     {...}            # optional sensor context for LLM
    }
    Response: {
        "status":    "ok",
        "transcript": "<recognised text>",
        "answer":    "<LLM response>",
        "audio_id":  "<cache id for /api/voice/tts.wav?id=..."
    }
    """
    data        = request.get_json(force=True, silent=True) or {}
    audio_b64   = data.get("audio", "").strip()
    language    = data.get("language", "fr-FR")
    sample_rate = int(data.get("sample_rate", 16000))
    context     = data.get("context", {})

    if not audio_b64:
        return jsonify({"status": "error", "message": "No audio data provided"}), 400

    # 1. Speech → Text
    transcript = transcribe_audio(audio_b64, language, sample_rate)
    if not transcript:
        return jsonify({"status": "ok", "transcript": "", "answer": "", "audio_id": None}), 200

    # 2. Text → Gemini LLM
    response_text = answer(transcript, context)
    if response_text is None:
        return jsonify({"status": "error", "message": "LLM unavailable"}), 500

    # 3. Cache TTS audio
    audio_bytes = synthesize(response_text)
    audio_id = None
    if audio_bytes:
        audio_id = str(uuid.uuid4())[:8]
        _audio_cache[audio_id] = audio_bytes

    return jsonify({
        "status":     "ok",
        "transcript": transcript,
        "answer":     response_text,
        "audio_id":   audio_id,
    }), 200

@voice_bp.route("/api/voice/stt_raw", methods=["POST"])
def speech_to_text_raw():
    """
    Convert raw binary audio to text. Avoids JSON encoding on IoT device.
    """
    audio_bytes = request.data
    if not audio_bytes:
        return jsonify({"status": "error", "message": "No audio data provided"}), 400

    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    
    # Check if audio is completely silent (all zeros)
    is_silent = all(b == 0 for b in audio_bytes)
    print(f"[STT_RAW] Received {len(audio_bytes)} bytes. Is silent? {is_silent}")
    
    transcript = transcribe_audio(audio_b64, "fr-FR", 16000)
    print(f"[STT_RAW] Google Speech-to-Text returned: '{transcript}'")
    
    if not transcript:
        return jsonify({"status": "ok", "transcript": "", "answer": "", "audio_id": None}), 200

    # Minimal context for now
    response_text = answer(transcript, {})
    if response_text is None:
        return jsonify({"status": "error", "message": "LLM unavailable"}), 500

    audio_tts_bytes = synthesize(response_text)
    audio_id = None
    if audio_tts_bytes:
        import uuid
        audio_id = str(uuid.uuid4())[:8]
        _audio_cache[audio_id] = audio_tts_bytes

    return jsonify({
        "status":     "ok",
        "transcript": transcript,
        "answer":     response_text,
        "audio_id":   audio_id,
    }), 200


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

@voice_bp.route("/api/voice/stt_only", methods=["POST"])
def stt_only():
    """Reads raw WAV from request, returns only the transcript (for Dashboard 2-step flow)."""
    audio_bytes = request.data
    if not audio_bytes:
        return jsonify({"status": "error", "message": "No audio"}), 400
        
    import base64
    audio_b64 = base64.b64encode(audio_bytes).decode("utf-8")
    
    transcript = transcribe_audio(audio_b64, "fr-FR", 16000)
    return jsonify({"status": "ok", "transcript": transcript or ""}), 200

@voice_bp.route("/api/voice/process_text_to_device", methods=["POST"])
def process_text_to_device():
    """Takes user text, gets LLM response, generates TTS, and queues it for the M5Stack."""
    global _device_command_queue
    data = request.get_json(force=True, silent=True) or {}
    text = data.get("text", "").strip()
    context = data.get("context", {})
    
    if not text:
        return jsonify({"status": "error", "message": "No text"}), 400
        
    response_text = answer(text, context)
    if response_text is None:
        return jsonify({"status": "error", "message": "LLM failed"}), 500
        
    audio_tts_bytes = synthesize(response_text)
    audio_id = None
    if audio_tts_bytes:
        import uuid
        audio_id = str(uuid.uuid4())[:8]
        _audio_cache[audio_id] = audio_tts_bytes
        _device_command_queue.append({"type": "play_audio", "value": response_text})
        print(f"[PROCESS] Queued play_audio for M5Stack.")

    return jsonify({
        "status": "ok",
        "answer": response_text,
        "audio_id": audio_id
    }), 200
