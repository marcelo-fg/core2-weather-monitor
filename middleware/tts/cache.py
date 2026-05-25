"""
tts/cache.py
============
Rôle du fichier :
Gérer un cache TRÈS SIMPLE sur disque des audios déjà générés.

Pourquoi un cache ?
La synthèse vocale via Google coûte de l'argent ET du temps (appel réseau).
Si on a déjà transformé EXACTEMENT le même texte en WAV, inutile de
rappeler Google : on relit simplement le fichier déjà sauvegardé.

Comment on identifie un texte de façon unique ?
- On calcule le hash MD5 du texte → cela donne une "empreinte" unique.
- Deux textes identiques donnent le même hash → donc le même nom de fichier.
- Exemple : "Bonjour" → "static/audio/<empreinte_md5>.wav"
"""

import hashlib
import os

import config


def _text_to_filename(text):
    """Transforme un texte en chemin de fichier unique grâce à un hash MD5.

    Paramètre :
        text (str) : le texte à transformer.

    Retour :
        str : le chemin complet du fichier WAV correspondant à ce texte.
    """
    # MD5 travaille sur des octets, pas sur du texte : on encode donc en UTF-8.
    empreinte = hashlib.md5(text.encode("utf-8")).hexdigest()

    # On assemble : dossier de cache + empreinte + extension ".wav".
    return os.path.join(config.AUDIO_CACHE_DIR, empreinte + ".wav")


def get_cached_audio(text):
    """Retourne les octets WAV si le texte est déjà en cache, sinon None.

    Paramètre :
        text (str) : le texte recherché.

    Retour :
        bytes : le contenu du fichier WAV si trouvé.
        None  : si aucun fichier n'existe encore pour ce texte.
    """
    chemin = _text_to_filename(text)

    # os.path.exists() vérifie simplement si le fichier est présent sur disque.
    if os.path.exists(chemin):
        with open(chemin, "rb") as f:  # "rb" = lecture binaire (audio)
            return f.read()

    # Pas trouvé : on signale au code appelant qu'il faudra appeler Google.
    return None


def save_audio(text, audio_bytes):
    """Enregistre l'audio WAV sur disque et retourne le chemin du fichier.

    Paramètres :
        text (str)         : le texte d'origine (sert à calculer le nom de fichier).
        audio_bytes (bytes): le contenu binaire du WAV à sauvegarder.

    Retour :
        str : le chemin du fichier créé.
    """
    # On s'assure que le dossier de cache existe (création récursive si besoin).
    # exist_ok=True : pas d'erreur si le dossier existe déjà.
    os.makedirs(config.AUDIO_CACHE_DIR, exist_ok=True)

    chemin = _text_to_filename(text)
    with open(chemin, "wb") as f:  # "wb" = écriture binaire (audio)
        f.write(audio_bytes)

    return chemin
