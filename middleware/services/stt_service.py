"""
Speech-to-Text service using Google Cloud STT.
"""
import base64
from google.cloud import speech


def transcribe_audio(audio_b64: str, language_code: str = "fr-FR", sample_rate: int = 16000) -> str:
    """
    Transcribe base64-encoded raw PCM audio using Google Cloud STT.

    Args:
        audio_b64:     Base64-encoded LINEAR16 (16-bit signed PCM) audio data.
        language_code: BCP-47 language tag (default: French).
        sample_rate:   Sampling rate in Hz (default: 16 000 Hz).

    Returns:
        Transcribed text, or empty string if nothing was recognised.
    """
    client = speech.SpeechClient()

    audio_bytes = base64.b64decode(audio_b64)
    audio = speech.RecognitionAudio(content=audio_bytes)

    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sample_rate,
        language_code=language_code,
        enable_automatic_punctuation=True,
    )

    response = client.recognize(config=config, audio=audio)

    if not response.results:
        return ""

    return response.results[0].alternatives[0].transcript
