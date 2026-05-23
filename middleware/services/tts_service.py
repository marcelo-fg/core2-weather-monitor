"""
Google Cloud Text-to-Speech service.
Returns a base64-encoded WAV audio payload that the M5Stack can play.
"""
import base64
import logging
from google.cloud import texttospeech
from config import TTS_LANGUAGE_CODE, TTS_VOICE_NAME

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        _client = texttospeech.TextToSpeechClient()
    return _client


def synthesize(text: str) -> bytes | None:
    """
    Convert text to speech and return raw LINEAR16 audio bytes (WAV).
    Returns None on failure.
    """
    if not text:
        return None

    client = _get_client()

    synthesis_input = texttospeech.SynthesisInput(text=text[:500])  # cap length

    voice = texttospeech.VoiceSelectionParams(
        language_code=TTS_LANGUAGE_CODE,
        name=TTS_VOICE_NAME,
    )

    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=8000,
    )

    try:
        response = client.synthesize_speech(
            input=synthesis_input,
            voice=voice,
            audio_config=audio_config,
        )
        return response.audio_content
    except Exception as e:
        logger.error(f"TTS error: {e}")
        return None


def synthesize_b64(text: str) -> str | None:
    """Return TTS audio as base64 string (for JSON transport)."""
    audio = synthesize(text)
    if audio is None:
        return None
    return base64.b64encode(audio).decode("utf-8")
