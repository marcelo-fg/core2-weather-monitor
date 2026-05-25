"""
tts/service.py
==============
Rôle du fichier :
C'est le SEUL endroit du projet qui parle directement à l'API
Google Cloud Text-to-Speech.

Deux fonctions importantes :
1. synthesize_to_wav(text) : appelle réellement Google et renvoie du WAV.
2. get_audio(text)         : utilise d'abord le cache, et n'appelle Google
                             que si le texte n'a jamais été synthétisé.

Avantage de tout isoler ici : si un jour on change de fournisseur
(par exemple Amazon Polly), on ne modifie QUE ce fichier.
"""

from google.cloud import texttospeech

import config
from tts import cache


# Le client Google est créé "paresseusement" (lazy) : il n'est créé
# qu'au premier appel réel, et UNE SEULE FOIS (on le réutilise ensuite).
# On stocke ici la référence ; au départ elle vaut None.
_client = None


def _get_client():
    """Crée (si nécessaire) et retourne le client Google Text-to-Speech.

    Pourquoi une création "paresseuse" plutôt qu'au démarrage ?
    - Si les credentials Google sont absents/invalides, l'application Flask
      DÉMARRE quand même. On renverra alors une erreur 503 propre lors de la
      première requête, au lieu de planter au lancement du serveur.
    - Le client lit automatiquement la variable d'environnement
      GOOGLE_APPLICATION_CREDENTIALS pour s'authentifier.
    """
    global _client
    if _client is None:
        _client = texttospeech.TextToSpeechClient()
    return _client


def synthesize_to_wav(text):
    """Transforme un texte français en audio WAV (octets) via Google.

    Paramètre :
        text (str) : le texte à lire à voix haute.

    Retour :
        bytes : le contenu binaire d'un fichier WAV.

    Note sur les erreurs :
        Si l'appel à Google échoue (réseau coupé, quota dépassé, credentials
        invalides...), une exception est levée. On NE l'attrape PAS ici :
        on la laisse remonter jusqu'à la route Flask, qui décidera de
        renvoyer un code HTTP 503. Cela garde ce fichier simple et focalisé.
    """
    client = _get_client()

    # 1) On emballe le texte dans l'objet attendu par l'API.
    synthesis_input = texttospeech.SynthesisInput(text=text)

    # 2) On choisit la voix : code de langue + nom de la voix WaveNet.
    voice = texttospeech.VoiceSelectionParams(
        language_code=config.TTS_LANGUAGE_CODE,
        name=config.TTS_VOICE_NAME,
    )

    # 3) On configure le format de sortie.
    #    LINEAR16 = WAV non compressé (demandé pour le M5Stack Core2).
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.LINEAR16,
        sample_rate_hertz=config.TTS_SAMPLE_RATE_HZ,
        speaking_rate=config.TTS_SPEAKING_RATE,
        pitch=config.TTS_PITCH,
    )

    # 4) Appel réel à l'API Google.
    response = client.synthesize_speech(
        input=synthesis_input,
        voice=voice,
        audio_config=audio_config,
    )

    # 5) response.audio_content contient déjà les octets du fichier WAV.
    return response.audio_content


def get_audio(text):
    """Retourne l'audio WAV d'un texte, en utilisant le cache si possible.

    C'est la fonction "principale" appelée par les routes Flask.

    Étapes :
    1. On regarde si le texte est déjà dans le cache (sur disque).
    2. Si OUI  -> on renvoie directement le fichier (AUCUN appel Google).
    3. Si NON  -> on appelle Google, on sauvegarde le résultat, puis on renvoie.

    Paramètre :
        text (str) : le texte à synthétiser.

    Retour :
        bytes : le contenu WAV.
    """
    # 1) Tentative de lecture depuis le cache.
    audio_en_cache = cache.get_cached_audio(text)
    if audio_en_cache is not None:
        return audio_en_cache

    # 2) Pas en cache : on appelle Google.
    audio_bytes = synthesize_to_wav(text)

    # 3) On sauvegarde pour les prochaines fois, puis on renvoie.
    cache.save_audio(text, audio_bytes)
    return audio_bytes
