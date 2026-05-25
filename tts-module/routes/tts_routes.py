"""
routes/tts_routes.py
====================
Rôle du fichier :
Définit les routes HTTP (les "endpoints") du module TTS, sous forme
d'un Blueprint Flask.

Routes exposées :
- GET  /health   : vérifie que le service tourne.
- POST /speak    : transforme un texte libre en audio WAV.
- POST /announce : transforme un event_type en audio WAV (annonce composée).
- POST /listen   : mode conversation (voix -> texte -> LLM -> voix).

Principe IMPORTANT (issu de la spec) :
On ne laisse JAMAIS Flask planter. En cas de problème (texte manquant,
Google indisponible, event_type inconnu...), on renvoie un JSON propre
avec un code HTTP adapté :
    - 400 = mauvaise requête (entrée invalide).
    - 429 = trop de requêtes (rate-limiting).
    - 503 = service indisponible (Google ou Gemini down).
"""

from flask import Blueprint, request, jsonify, Response

from tts import service
from tts import announcements
from tts import stt
from tts import llm

# Un Blueprint est un "groupe de routes" réutilisable, qu'on branche ensuite
# sur l'application principale (voir app.py).
tts_blueprint = Blueprint("tts", __name__)


@tts_blueprint.route("/health", methods=["GET"])
def health():
    """Route de "santé" : permet de vérifier rapidement que le service répond.

    Très utile pour Google Cloud Run, un load balancer, ou simplement pour
    que mon coéquipier sache si le service tourne.
    """
    return jsonify({"status": "ok"})


@tts_blueprint.route("/speak", methods=["POST"])
def speak():
    """Transforme un texte libre en audio WAV.

    Entrée (JSON) : {"text": "le texte à lire"}
    Sortie (succès) : le fichier WAV binaire (Content-Type: audio/wav).
    Sortie (erreur) : un JSON {"error": "..."} + code HTTP.
    """
    # get_json(silent=True) renvoie None si le corps n'est pas du JSON valide,
    # au lieu de lever une exception : c'est plus sûr et plus simple à gérer.
    data = request.get_json(silent=True)

    # Validation : on vérifie qu'on a bien reçu un texte NON vide.
    if not data or "text" not in data or not str(data["text"]).strip():
        return jsonify({"error": "Le champ 'text' est obligatoire."}), 400

    text = str(data["text"]).strip()

    try:
        # get_audio() gère d'abord le cache, puis appelle Google si nécessaire.
        audio_bytes = service.get_audio(text)
    except Exception as e:
        # Google est peut-être indisponible, ou les credentials sont invalides.
        # On renvoie 503 (Service Unavailable) au lieu de planter.
        return jsonify({"error": "Service TTS indisponible : " + str(e)}), 503

    # Succès : on renvoie directement les octets WAV avec le bon Content-Type.
    return Response(audio_bytes, mimetype="audio/wav")


@tts_blueprint.route("/announce", methods=["POST"])
def announce():
    """Transforme un event_type en audio WAV (texte composé + rate-limiting).

    Entrée (JSON) : {"event_type": "morning_briefing"}
    Sortie (succès) : le fichier WAV binaire.
    Sortie (erreur) : un JSON {"error": "..."} + code HTTP.
    """
    data = request.get_json(silent=True)

    # Validation de l'entrée.
    if not data or "event_type" not in data:
        return jsonify({"error": "Le champ 'event_type' est obligatoire."}), 400

    event_type = str(data["event_type"]).strip()

    # "force": true permet de CONTOURNER le rate-limiting. Le M5Stack l'envoie
    # lors d'un appui bouton manuel (l'utilisateur doit toujours pouvoir
    # rejouer une annonce). Les declencheurs automatiques (PIR) n'envoient pas
    # "force" et restent donc limites a 1 annonce par heure et par type.
    force = bool(data.get("force", False))

    # Rate-limiting : on refuse si la même annonce date de moins d'une heure
    # (sauf si force=true).
    if not force and announcements.is_rate_limited(event_type):
        return jsonify({
            "error": (
                "Annonce '" + event_type + "' déjà émise récemment. "
                "Réessayez plus tard."
            )
        }), 429  # 429 = Too Many Requests

    # Composition du texte selon l'event_type.
    try:
        text = announcements.build_announcement_text(event_type)
    except ValueError as e:
        # event_type inconnu -> mauvaise requête.
        return jsonify({"error": str(e)}), 400

    # Synthèse (avec cache) + gestion d'erreur Google.
    try:
        audio_bytes = service.get_audio(text)
    except Exception as e:
        return jsonify({"error": "Service TTS indisponible : " + str(e)}), 503

    # On note que l'annonce vient d'être émise (pour le rate-limiting).
    # IMPORTANT : on le fait seulement APRÈS un succès complet.
    announcements.mark_announced(event_type)

    return Response(audio_bytes, mimetype="audio/wav")


@tts_blueprint.route("/listen", methods=["POST"])
def listen():
    """Mode conversation : reçoit de la voix, renvoie une réponse vocale.

    C'est l'endpoint le plus complet. Il enchaîne 3 services :
        1. Speech-to-Text (Google) : transforme la VOIX reçue en TEXTE.
        2. LLM (Google Gemini)     : génère une RÉPONSE intelligente.
        3. Text-to-Speech (Google) : transforme la réponse en VOIX (WAV).

    Entrée :
        Le corps de la requête contient l'audio enregistré par le M5Stack.
        Deux formats sont acceptés :
          - corps binaire brut (Content-Type: audio/wav)  <- utilisé par le M5Stack
          - fichier "audio" en multipart/form-data         <- pratique pour curl
    Sortie (succès) : le fichier WAV de la réponse (Content-Type: audio/wav).
    Sortie (erreur) : un JSON {"error": "..."} + code HTTP.
    """
    # --- 1) Récupérer les octets audio envoyés par le device -----------------
    if "audio" in request.files:
        # Cas multipart (ex. curl -F "audio=@voix.wav").
        audio_bytes = request.files["audio"].read()
    else:
        # Cas corps binaire brut (ce que fait le M5Stack avec urequests).
        audio_bytes = request.get_data()

    # Validation : on refuse une requête sans audio.
    if not audio_bytes:
        return jsonify({"error": "Aucun audio reçu."}), 400

    # --- 2) Transcription : voix -> texte (Google Speech-to-Text) ------------
    try:
        transcription = stt.transcribe_wav(audio_bytes)
    except Exception as e:
        return jsonify({"error": "Service de transcription indisponible : " + str(e)}), 503

    # Si Google n'a rien compris (silence, bruit...), on renvoie quand même
    # une réponse vocale polie, pour que le device ait quelque chose à jouer.
    if not transcription:
        try:
            audio_reponse = service.get_audio(
                "Désolé, je n'ai pas bien compris. Pouvez-vous répéter ?"
            )
        except Exception as e:
            return jsonify({"error": "Service TTS indisponible : " + str(e)}), 503
        return Response(audio_reponse, mimetype="audio/wav")

    # Trace utile dans les logs (visible dans Cloud Run) pour le débogage.
    print("Transcription reçue :", transcription)

    # --- 3) Génération de la réponse par le LLM (Google Gemini) --------------
    try:
        reponse_texte = llm.generate_reply(transcription)
    except Exception as e:
        return jsonify({"error": "Service LLM indisponible : " + str(e)}), 503

    print("Réponse du LLM :", reponse_texte)

    # --- 4) Synthèse vocale de la réponse : texte -> voix (Google TTS) -------
    try:
        audio_reponse = service.get_audio(reponse_texte)
    except Exception as e:
        return jsonify({"error": "Service TTS indisponible : " + str(e)}), 503

    # On renvoie le WAV de la réponse au M5Stack, qui le jouera.
    return Response(audio_reponse, mimetype="audio/wav")
