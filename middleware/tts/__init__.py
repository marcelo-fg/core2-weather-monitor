"""
tts package — voice subsystem.

Modules:
- service.py       : Google Cloud Text-to-Speech client (synthesis + cache orchestration).
- cache.py         : on-disk cache of already-synthesized WAV files.
- stt.py           : Google Cloud Speech-to-Text client.
- llm.py           : Google Gemini client (multi-model fallback + per-call timeout).
- announcements.py : announcement templates and rate limiting.
"""
