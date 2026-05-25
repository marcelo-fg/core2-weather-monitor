"""
tts/stt.py
==========
Rôle du fichier :
C'est le SEUL endroit du projet qui parle à l'API Google Cloud
Speech-to-Text (reconnaissance vocale = transformer de la voix en texte).

Il est utilisé par l'endpoint /listen (mode conversation) : le M5Stack
enregistre la voix de l'utilisateur, l'envoie ici, et on récupère le texte.

Remarque sur le format audio :
On suppose que l'audio reçu est du PCM 16 bits, mono, à 16000 Hz
(c'est ce que le micro du M5Stack Core2 produit). Ces valeurs sont
configurables dans config.py (STT_SAMPLE_RATE_HZ, STT_LANGUAGE_CODE).
"""

import logging

from google.cloud import speech

import config

logger = logging.getLogger(__name__)


# Indices de vocabulaire (speech contexts) : on oriente Google vers le champ
# lexical météo/maison pour améliorer la reconnaissance des questions courantes.
_PHRASES_METEO = [
    "quelle température", "température", "il fait combien", "fait-il chaud", "fait-il froid",
    "humidité", "qualité de l'air", "air intérieur", "air extérieur", "pollution",
    "à l'intérieur", "à l'extérieur", "dehors", "dans la maison",
    "météo", "quel temps", "demain", "aujourd'hui", "cette semaine", "prochains jours",
    "va-t-il pleuvoir", "pluie", "soleil", "nuages", "vent", "prévisions",
    "ouvrir les fenêtres", "aérer", "dois-je", "est-ce que",
]


# Comme pour le TTS, on crée le client Google "paresseusement" (lazy) :
# il n'est créé qu'au premier appel réel, et une seule fois.
# Avantage : l'application démarre même sans credentials, et on renvoie
# une erreur 503 propre lors de la première requête en cas de problème.
_client = None


def _get_client():
    """Crée (si nécessaire) et retourne le client Google Speech-to-Text.

    Le client lit automatiquement la variable d'environnement
    GOOGLE_APPLICATION_CREDENTIALS pour s'authentifier.
    """
    global _client
    if _client is None:
        _client = speech.SpeechClient()
    return _client


def _parse_wav_header(audio_bytes):
    """Lit (fréquence, nb_canaux, bits) dans l'en-tête WAV (sous-bloc "fmt ").

    Offsets dans "fmt " : +10 canaux (2o), +12 fréquence (4o), +22 bits (2o).
    Si l'en-tête est absent/illisible, on retombe sur des valeurs par défaut.
    Le nombre de canaux est CRUCIAL : si le M5 enregistre en stéréo et qu'on
    transcrit en mono, Google lit les échantillons de travers → rien reconnu.
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
    """Position du début des échantillons PCM (après l'en-tête 'data')."""
    i = audio_bytes.find(b"data")
    return i + 8 if i >= 0 else 44


def _max_amp_pcm(pcm):
    """Amplitude max (échantillons 16 bits LE) sur des octets PCM bruts.
    Renvoie 0..32767, ou -1 si illisible. Sert à détecter le silence et à
    localiser le transitoire de début."""
    try:
        n = len(pcm) // 2
        if n == 0:
            return 0
        step = max(1, n // 20000)   # on échantillonne au plus ~20 000 points
        mx = 0
        for k in range(0, n, step):
            s = int.from_bytes(pcm[2 * k:2 * k + 2], "little", signed=True)
            a = s if s >= 0 else -s
            if a > mx:
                mx = a
        return mx
    except Exception:
        return -1


# Conservé pour compatibilité (ancien nom).
def _frequence_wav(audio_bytes):
    return _parse_wav_header(audio_bytes)[0]


def transcribe_wav(audio_bytes):
    """Transcrit un audio (octets) en texte français via Google.

    Paramètre :
        audio_bytes (bytes) : le contenu audio enregistré par le M5Stack
                              (PCM 16 bits, mono, 16000 Hz).

    Retour :
        str : le texte reconnu. Peut être une chaîne VIDE si Google n'a
              rien compris (silence, bruit...).

    Note sur les erreurs :
        Si l'appel à Google échoue (réseau, quota, credentials...), une
        exception est levée. On la laisse remonter jusqu'à la route Flask,
        qui renverra alors un code HTTP 503.
    """
    client = _get_client()

    # 1) On lit le VRAI format dans l'en-tête (fréquence + canaux + bits).
    sr, ch, bits = _parse_wav_header(audio_bytes)
    sample_bytes = ch * (bits // 8) or 2

    # 2) On isole les échantillons PCM (après 'data') et on ROGNE le début :
    #    le micro M5 produit un "clic" transitoire constant au démarrage de
    #    l'enregistrement (amplitude max identique à chaque fois dans les logs).
    #    Ce transitoire perturbe la reconnaissance → on coupe les 0,35 premières
    #    secondes. On envoie ensuite du PCM BRUT (sans en-tête) à Google.
    pcm = audio_bytes[_data_offset(audio_bytes):]
    cut = int(0.35 * sr) * sample_bytes      # 0,35 s alignées sur un échantillon
    amp_start = _max_amp_pcm(pcm[:cut])
    amp_rest  = _max_amp_pcm(pcm[cut:])
    pcm_trim = pcm[cut:] if len(pcm) > cut * 2 else pcm
    logger.info("STT input: bytes=%d sr=%d ch=%d bits=%d amp_start=%d amp_rest=%d",
                len(audio_bytes), sr, ch, bits, amp_start, amp_rest)

    # 3) On envoie le PCM rogné (brut LINEAR16).
    audio = speech.RecognitionAudio(content=pcm_trim)

    # 4) Paramètres communs. On passe la fréquence ET le nombre de canaux lus
    #    dans l'en-tête. enable_automatic_punctuation améliore la lisibilité.
    base_kwargs = dict(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sr,
        audio_channel_count=(ch if ch in (1, 2) else 1),
        language_code=config.STT_LANGUAGE_CODE,
        enable_automatic_punctuation=True,
        speech_contexts=[speech.SpeechContext(phrases=_PHRASES_METEO, boost=15.0)],
    )

    # 5) On essaie d'abord le modèle "latest_short" + enhanced (nettement plus
    #    précis pour des phrases courtes/commandes vocales). S'il n'est pas
    #    disponible, on retombe sur la config simple.
    try:
        rc = speech.RecognitionConfig(model="latest_short", use_enhanced=True, **base_kwargs)
        response = client.recognize(config=rc, audio=audio)
    except Exception as e:
        logger.warning("STT modele enhanced indispo (%s) -> repli config simple", str(e)[:100])
        rc = speech.RecognitionConfig(**base_kwargs)
        response = client.recognize(config=rc, audio=audio)
    logger.info("STT results=%d", len(response.results))

    # 5) Google peut renvoyer PLUSIEURS morceaux de transcription : on les
    #    recolle bout à bout pour obtenir une seule phrase.
    morceaux = []
    for result in response.results:
        # On prend la 1re alternative (la plus probable selon Google).
        if result.alternatives:
            morceaux.append(result.alternatives[0].transcript)

    texte = " ".join(morceaux).strip()
    logger.info("STT transcript: %r", texte)
    return texte
