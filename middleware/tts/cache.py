"""
On-disk cache of TTS audio files.

A WAV is identified by the MD5 hash of its source text, so identical texts
map to the same cached file and Google TTS is called only once per text.
"""

import hashlib
import os

import config


def _text_to_filename(text):
    """Return the WAV file path that uniquely corresponds to ``text``."""
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()
    return os.path.join(config.AUDIO_CACHE_DIR, digest + ".wav")


def get_cached_audio(text):
    """Return the cached WAV bytes for ``text``, or ``None`` if not cached."""
    path = _text_to_filename(text)
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None


def save_audio(text, audio_bytes):
    """Persist ``audio_bytes`` to the cache; return the path, or ``None`` on failure.

    The cache is a pure optimization. If the directory is read-only (Cloud Run
    runs as a non-root user and ``/app`` is read-only), we swallow the error
    and return ``None`` — the caller already has the audio bytes.
    """
    try:
        os.makedirs(config.AUDIO_CACHE_DIR, exist_ok=True)
        path = _text_to_filename(text)
        with open(path, "wb") as f:
            f.write(audio_bytes)
        return path
    except Exception:
        return None
