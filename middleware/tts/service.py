"""
Google Cloud Text-to-Speech client (single point of contact with the TTS API).

Public functions:
- synthesize_to_wav(text, lang_code=None) : call Google and return raw WAV bytes.
- get_audio(text, lang_code=None)         : cache-first wrapper around synthesize_to_wav.
"""

import re

from google.cloud import texttospeech

import config
from tts import cache


# Pre-compiled regexes used to strip markdown / emoji before synthesis.
_MD_CHARS = re.compile(r"[*_`#~|>]+")
_BULLETS  = re.compile(r"(?m)^\s*[-•]\s*")
_SPACES   = re.compile(r"\s+")


def _clean_for_tts(text):
    """Strip markdown, emoji and other characters that would be read aloud literally.

    Keeps accented letters and standard punctuation.
    """
    if not text:
        return text
    text = _MD_CHARS.sub(" ", text)
    text = _BULLETS.sub("", text)
    text = (text.replace("…", "...").replace("’", "'")
                .replace("“", '"').replace("”", '"')
                .replace("—", "-").replace("–", "-"))
    # Drop characters outside the standard range (emoji, arrows, …) but keep accents.
    text = "".join(ch for ch in text if ord(ch) < 0x2000)
    text = _SPACES.sub(" ", text).strip()
    return text


# Lazy-initialized Google TTS client (created on first request, reused after).
_client = None


def _get_client():
    """Return the Google TTS client, creating it lazily on first use.

    Lazy init lets the Flask app start even if credentials are missing — the
    first request would then return a 503 instead of crashing at boot.
    """
    global _client
    if _client is None:
        _client = texttospeech.TextToSpeechClient()
    return _client


def synthesize_to_wav(text, lang_code=None):
    """Synthesize ``text`` via Google Cloud TTS and return raw LINEAR16 WAV bytes.

    Errors (network, quota, credentials, …) are raised and handled by the
    Flask route, which converts them into HTTP 503.
    """
    client = _get_client()

    synthesis_input = texttospeech.SynthesisInput(text=text)

    # Pick voice & language. If a non-default ``lang_code`` is provided, fall
    # back to a sensible default voice for that language.
    actual_lang = lang_code if lang_code else config.TTS_LANGUAGE_CODE
    if not lang_code or lang_code == config.TTS_LANGUAGE_CODE:
        actual_voice = config.TTS_VOICE_NAME
    else:
        actual_voice = "en-US-Journey-F" if "en" in lang_code else config.TTS_VOICE_NAME

    voice = texttospeech.VoiceSelectionParams(
        language_code=actual_lang,
        name=actual_voice,
    )

    # LINEAR16 = uncompressed WAV (required by the M5Stack Core2 player).
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=config.TTS_SAMPLE_RATE_HZ,
        speaking_rate=config.TTS_SPEAKING_RATE,
        pitch=config.TTS_PITCH,
    )

    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )
    return response.audio_content


def get_audio(text, lang_code=None):
    """Return WAV bytes for ``text``, using the on-disk cache when possible."""
    text = _clean_for_tts(text)

    cached = cache.get_cached_audio(text)
    if cached is not None:
        return cached

    audio_bytes = synthesize_to_wav(text, lang_code=lang_code)
    cache.save_audio(text, audio_bytes)
    return audio_bytes
