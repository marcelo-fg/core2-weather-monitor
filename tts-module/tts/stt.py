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

from google.cloud import speech

import config


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


def _frequence_wav(audio_bytes):
    """Lit la fréquence d'échantillonnage dans l'en-tête d'un fichier WAV.

    On localise le sous-bloc "fmt " et on lit la fréquence (4 octets,
    little-endian) située 12 octets après son début. Si l'en-tête est absent
    ou illisible, on retombe sur la valeur par défaut (config.STT_SAMPLE_RATE_HZ).
    """
    try:
        i = audio_bytes.find(b"fmt ")
        if i >= 0:
            return int.from_bytes(audio_bytes[i + 12:i + 16], "little")
    except Exception:
        pass
    return config.STT_SAMPLE_RATE_HZ


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

    # 1) On emballe les octets audio dans l'objet attendu par l'API.
    audio = speech.RecognitionAudio(content=audio_bytes)

    # 2) On décrit le format. Le M5Stack envoie un VRAI fichier WAV (LINEAR16)
    #    via mic.record2file, mais sa fréquence dépend du firmware. On la LIT
    #    directement dans l'en-tête du WAV (plus fiable que l'auto-détection de
    #    Google, qui renvoie "bad encoding" sur certains fichiers).
    recognition_config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=_frequence_wav(audio_bytes),
        language_code=config.STT_LANGUAGE_CODE,
    )

    # 3) Appel réel à l'API Google.
    response = client.recognize(config=recognition_config, audio=audio)

    # 4) Google peut renvoyer PLUSIEURS morceaux de transcription : on les
    #    recolle bout à bout pour obtenir une seule phrase.
    morceaux = []
    for result in response.results:
        # On prend la 1re alternative (la plus probable selon Google).
        if result.alternatives:
            morceaux.append(result.alternatives[0].transcript)

    # 5) On renvoie le texte recollé, sans espaces inutiles au début/fin.
    return " ".join(morceaux).strip()
