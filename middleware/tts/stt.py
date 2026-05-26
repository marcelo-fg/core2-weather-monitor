"""
Google Cloud Speech-to-Text client.

Used by the /api/voice/listen route: the M5Stack records a voice clip and
POSTs it here, this module returns the transcribed text. The recognizer
runs in English (``en-US``) with Google's enhanced ``latest_short`` model
and a rich weather / indoor-air speech-context bias.
"""

import logging

from google.cloud import speech

import config

logger = logging.getLogger(__name__)

# audioop ships with the Python 3.12 runtime used by the middleware image.
try:
    import audioop
except ImportError:
    audioop = None


# Speech-context phrases — bias the recognizer towards the weather and
# indoor-air vocabulary used by the assistant. Boosts recognition accuracy
# on short commands, on past-tense questions, and on day-of-week mentions.
_WEATHER_PHRASES = [
    # Indoor environment
    "temperature", "indoor temperature", "outdoor temperature",
    "humidity", "indoor humidity", "outdoor humidity",
    "air quality", "indoor air", "outdoor air", "pollution",
    "VOC", "TVOC", "CO2", "eCO2", "carbon dioxide", "ppm", "ppb",
    # Weather conditions
    "weather", "forecast", "rain", "sun", "sunny", "clouds", "cloudy",
    "wind", "windy", "storm", "snow", "fog",
    "is it going to rain", "will it rain", "what's the weather",
    "how hot is it", "how cold is it", "how warm is it",
    # Past
    "yesterday", "last night", "earlier today", "this morning",
    "this afternoon", "this evening", "last week", "last 24 hours",
    "last 7 days", "the past week", "recently", "earlier",
    # Present
    "today", "right now", "currently", "at this moment",
    # Future
    "tomorrow", "this week", "the next few days", "the coming days",
    "Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
    "Saturday", "Sunday",
    # Aggregations / extremes
    "average", "highest", "lowest", "maximum", "minimum",
    "warmest", "coolest", "hottest", "coldest", "peak",
    "what was", "when was", "how often", "how many times",
    "what time", "at what time",
    # Comfort / advice
    "should I open the windows", "ventilate", "do I need to",
    "is it safe", "is it OK", "is it healthy", "fresh air",
    # Locations
    "inside", "outside", "in the house", "at home",
]


# Lazy-initialized Google STT client (created on first request, reused after).
_client = None


def _get_client():
    """Return the Google STT client, creating it lazily on first use."""
    global _client
    if _client is None:
        _client = speech.SpeechClient()
    return _client


def _parse_wav_header(audio_bytes):
    """Return (sample_rate, channels, bits) read from the WAV ``fmt `` chunk.

    Offsets relative to ``fmt ``: +10 channels (2 bytes), +12 sample rate
    (4 bytes), +22 bits per sample (2 bytes). Falls back to defaults if the
    header is unreadable. Channel count is critical: a stereo recording
    interpreted as mono produces garbled audio and an empty transcript.
    """
    sr   = config.STT_SAMPLE_RATE_HZ
    ch   = 1
    bits = 16
    try:
        i = audio_bytes.find(b"fmt ")
        if i >= 0:
            ch   = int.from_bytes(audio_bytes[i + 10:i + 12], "little") or 1
            sr   = int.from_bytes(audio_bytes[i + 12:i + 16], "little") or sr
            bits = int.from_bytes(audio_bytes[i + 22:i + 24], "little") or 16
    except Exception:
        pass
    return sr, ch, bits


def _data_offset(audio_bytes):
    """Return the byte offset of the PCM data (right after the ``data`` chunk header)."""
    i = audio_bytes.find(b"data")
    return i + 8 if i >= 0 else 44


def _apply_gain(pcm, target=18000, max_gain=4.0):
    """Auto-level the PCM clip: if the loudest sample is below ``target``,
    scale every 16-bit sample up so Google STT receives a stronger signal.

    Returns ``(boosted_pcm, gain)``. The gain is capped at ``max_gain`` to
    avoid blowing up pure noise. Saturation is handled by ``audioop.mul``.
    """
    if audioop is None or not pcm:
        return pcm, 1.0
    try:
        mx = audioop.max(pcm, 2)
    except Exception:
        return pcm, 1.0
    if mx <= 0 or mx >= target:
        return pcm, 1.0
    gain = min(max_gain, target / mx)
    try:
        return audioop.mul(pcm, 2, gain), gain
    except Exception:
        return pcm, 1.0


def _max_amp_pcm(pcm):
    """Return the maximum absolute amplitude (0..32767) over 16-bit LE samples.

    Used to detect silence (mic recording nothing) and to locate the loud
    transient that the M5 mic emits at the start of every recording.
    """
    try:
        n = len(pcm) // 2
        if n == 0:
            return 0
        step = max(1, n // 20000)
        mx = 0
        for k in range(0, n, step):
            s = int.from_bytes(pcm[2 * k:2 * k + 2], "little", signed=True)
            a = s if s >= 0 else -s
            if a > mx:
                mx = a
        return mx
    except Exception:
        return -1


def transcribe_wav(audio_bytes):
    """Transcribe a WAV recording (bytes) into text via Google Cloud STT.

    Returns the recognized text, possibly an empty string if Google could not
    detect any speech. Network/quota/credential errors propagate as exceptions
    and are turned into HTTP 503 by the Flask route.
    """
    client = _get_client()

    # Read the real audio format from the WAV header.
    sr, ch, bits = _parse_wav_header(audio_bytes)
    sample_bytes = ch * (bits // 8) or 2

    # Extract the PCM body and trim the first 0.35 s. The M5 mic emits a loud
    # initialization "click" at the start of every recording (amplitude ~32767)
    # which confuses the recognizer; trimming it dramatically improves accuracy.
    pcm = audio_bytes[_data_offset(audio_bytes):]
    cut = int(0.35 * sr) * sample_bytes
    amp_start = _max_amp_pcm(pcm[:cut])
    amp_rest  = _max_amp_pcm(pcm[cut:])
    pcm_trim = pcm[cut:] if len(pcm) > cut * 2 else pcm

    # Boost low-amplitude recordings so STT receives a usable signal even when
    # the speaker is quiet or far from the M5 microphone.
    pcm_trim, gain = _apply_gain(pcm_trim)
    logger.info("STT input: bytes=%d sr=%d ch=%d bits=%d amp_start=%d amp_rest=%d gain=%.2f",
                len(audio_bytes), sr, ch, bits, amp_start, amp_rest, gain)

    audio = speech.RecognitionAudio(content=pcm_trim)

    base_kwargs = dict(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sr,
        audio_channel_count=(ch if ch in (1, 2) else 1),
        language_code=config.STT_LANGUAGE_CODE,
        enable_automatic_punctuation=True,
        speech_contexts=[speech.SpeechContext(phrases=_WEATHER_PHRASES, boost=15.0)],
    )

    # Try the enhanced ``latest_short`` model first (much more accurate on
    # short voice commands); fall back to the default model if unavailable.
    try:
        rc = speech.RecognitionConfig(model="latest_short", use_enhanced=True, **base_kwargs)
        response = client.recognize(config=rc, audio=audio)
    except Exception as e:
        logger.warning("STT enhanced model unavailable (%s) -> falling back", str(e)[:100])
        rc = speech.RecognitionConfig(**base_kwargs)
        response = client.recognize(config=rc, audio=audio)
    logger.info("STT results=%d", len(response.results))

    # Concatenate the (possibly multiple) recognized segments into one phrase.
    transcript_parts = []
    for result in response.results:
        if result.alternatives:
            transcript_parts.append(result.alternatives[0].transcript)

    text = " ".join(transcript_parts).strip()
    logger.info("STT transcript: %r", text)
    return text
