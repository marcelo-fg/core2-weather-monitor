"""
config.py
=========
Rôle du fichier :
Ce fichier centralise TOUTE la configuration du module Text-to-Speech.

Idée principale :
Chaque paramètre est lu depuis une variable d'environnement, avec une
valeur par défaut raisonnable si la variable n'est pas définie.

Pourquoi tout centraliser ici ?
- On évite les "valeurs magiques" éparpillées dans le code.
- Mon coéquipier (ou le correcteur) peut tout changer SANS toucher au code,
  simplement en modifiant des variables d'environnement (fichier .env).
- C'est plus facile à défendre à l'oral : "toute la config est à un seul endroit".
"""

import os

# On charge automatiquement le fichier .env s'il existe (pratique en local).
# En production (Google Cloud Run), les variables sont fournies autrement,
# mais ce chargement ne pose aucun problème.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    # python-dotenv n'est pas installé : ce n'est pas grave, on continue.
    # Les variables d'environnement "système" sont quand même lues plus bas.
    pass


# ---------------------------------------------------------------------------
# Credentials Google
# ---------------------------------------------------------------------------
# Pas de variable Python ici : les librairies Google (Text-to-Speech,
# Speech-to-Text) lisent AUTOMATIQUEMENT la variable d'environnement
# GOOGLE_APPLICATION_CREDENTIALS (définie dans le .env, ou fournie par le
# compte de service sur Cloud Run). Rien d'autre à faire de notre côté.


# ---------------------------------------------------------------------------
# Paramètres de la voix
# ---------------------------------------------------------------------------

# Langue utilisée pour la synthèse vocale.
TTS_LANGUAGE_CODE = os.environ.get("TTS_LANGUAGE_CODE", "fr-FR")

# Nom de la voix WaveNet par défaut (féminine, naturelle).
TTS_VOICE_NAME = os.environ.get("TTS_VOICE_NAME", "fr-FR-Wavenet-C")

# Vitesse de lecture (1.0 = vitesse normale, 0.5 = lent, 2.0 = rapide).
TTS_SPEAKING_RATE = float(os.environ.get("TTS_SPEAKING_RATE", "1.0"))

# Tonalité (pitch) de la voix. 0.0 = tonalité normale.
TTS_PITCH = float(os.environ.get("TTS_PITCH", "0.0"))


# ---------------------------------------------------------------------------
# Format audio
# ---------------------------------------------------------------------------

# On force le format WAV (encodage LINEAR16) car le M5Stack Core2
# lit mieux le WAV que le MP3.
# Fréquence d'échantillonnage en Hz. 24000 est un bon compromis qualité / taille.
TTS_SAMPLE_RATE_HZ = int(os.environ.get("TTS_SAMPLE_RATE_HZ", "24000"))


# ---------------------------------------------------------------------------
# Cache des fichiers audio
# ---------------------------------------------------------------------------

# Dossier où l'on stocke les fichiers WAV déjà générés (pour éviter de
# rappeler Google inutilement).
AUDIO_CACHE_DIR = os.environ.get("AUDIO_CACHE_DIR", "static/audio")


# ---------------------------------------------------------------------------
# Rate-limiting (limitation de fréquence des annonces)
# ---------------------------------------------------------------------------

# Durée minimale (en secondes) entre deux annonces du MÊME event_type.
# Par défaut 3600 secondes = 1 heure (comme demandé dans la spec).
RATE_LIMIT_SECONDS = int(os.environ.get("RATE_LIMIT_SECONDS", "3600"))


# ---------------------------------------------------------------------------
# Speech-to-Text (reconnaissance vocale) — utilisé par l'endpoint /listen
# ---------------------------------------------------------------------------

# Langue attendue pour la transcription de la voix de l'utilisateur.
STT_LANGUAGE_CODE = os.environ.get("STT_LANGUAGE_CODE", "fr-FR")

# Fréquence d'échantillonnage de l'audio enregistré PAR LE M5STACK.
# Le micro du Core2 (API officielle UIFlow 1.x) enregistre en 16 bits, mono,
# à 8000 Hz : on aligne donc la reconnaissance vocale sur cette valeur. Si tu
# changes la fréquence d'enregistrement côté M5Stack, change-la aussi ici.
STT_SAMPLE_RATE_HZ = int(os.environ.get("STT_SAMPLE_RATE_HZ", "8000"))


# ---------------------------------------------------------------------------
# LLM (Google Gemini) — utilisé par l'endpoint /listen (mode conversation)
# ---------------------------------------------------------------------------

# Modèle Gemini utilisé. "gemini-2.5-flash" est rapide et eligible au quota gratuit.
# (gemini-1.5-flash a été retiré par Google : on utilise la version 2.5.)
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

# Clé d'API Gemini, à créer (gratuitement) sur https://aistudio.google.com/apikey
# Pourquoi une clé d'API et non le compte de service ? L'API Gemini "Developer"
# n'accepte pas de façon fiable les credentials de compte de service (erreur
# "ACCESS_TOKEN_SCOPE_INSUFFICIENT"). La clé d'API est la méthode standard.
# À mettre dans le fichier .env (jamais en dur dans le code !).
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# "Contexte" donné au LLM (message système). Il définit la personnalité et les
# règles de l'assistant. On peut le surcharger via la variable d'environnement.
LLM_SYSTEM_PROMPT = os.environ.get(
    "LLM_SYSTEM_PROMPT",
    "Tu es un assistant météo intelligent installé dans une maison. "
    "Tu as accès aux données de température, humidité et qualité de l'air. "
    "Réponds en français, de façon concise (2-3 phrases max).",
)


# ---------------------------------------------------------------------------
# Serveur Flask
# ---------------------------------------------------------------------------

# Adresse d'écoute. "0.0.0.0" = accessible depuis l'extérieur (nécessaire
# dans un conteneur Docker / Cloud Run).
FLASK_HOST = os.environ.get("FLASK_HOST", "0.0.0.0")

# Port d'écoute. Google Cloud Run impose d'utiliser la variable PORT.
FLASK_PORT = int(os.environ.get("PORT", "8080"))

# Mode debug (à ne JAMAIS activer en production). "true"/"false".
FLASK_DEBUG = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
