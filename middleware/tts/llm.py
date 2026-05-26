"""
tts/llm.py
==========
Rôle du fichier :
C'est le SEUL endroit du projet qui parle au LLM (le "cerveau" qui génère
une réponse intelligente à partir du texte de l'utilisateur).

On utilise **Google Gemini** (modèle gemini-2.5-flash, gratuit) via la
librairie google-generativeai.

Authentification :
On réutilise les MÊMES credentials Google Cloud que le reste du projet
(la variable d'environnement GOOGLE_APPLICATION_CREDENTIALS), au lieu d'une
clé API séparée. Avantage : une seule clé de compte de service sert à la fois
pour le Text-to-Speech, le Speech-to-Text ET le LLM. C'est plus simple à gérer
et à défendre à l'oral.
"""

import logging

import config

logger = logging.getLogger(__name__)


# Liste de modèles de REPLI. Chaque modèle a son PROPRE quota journalier gratuit
# (le free tier de gemini-2.5-flash est très bas : ~20 req/jour). Si un modèle
# renvoie 429 (quota dépassé), on essaie le suivant → l'assistant continue de
# répondre au lieu de tomber en panne.
_FALLBACK_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-latest",
]

# Quand un modèle renvoie 429 (quota), on le met en "cooldown" : on le SAUTE
# pendant un moment au lieu de le réessayer à chaque requête. Cela évite de
# perdre du temps sur des modèles épuisés (les requêtes suivantes vont direct
# au premier modèle qui a encore du quota).
_MODEL_COOLDOWN = {}     # nom_modele -> timestamp jusqu'auquel on le saute
_COOLDOWN_S = 90
_CALL_TIMEOUT_S = 15     # plafond de temps par appel Gemini (anti-blocage)


# Le modèle Gemini est créé "paresseusement" (lazy) : une seule fois, au
# premier appel réel. L'application démarre donc même sans credentials valides,
# et on renvoie une erreur 503 propre lors de la première requête en cas de souci.
_model = None


def _get_model():
    """Crée (si nécessaire) et configure le modèle Gemini.

    Authentification : on utilise une CLÉ D'API Gemini (config.GEMINI_API_KEY).
    Pourquoi une clé plutôt que le compte de service ?
    - L'API Gemini "Developer" (generativelanguage.googleapis.com) n'accepte
      pas de façon fiable les credentials de compte de service : on obtient
      l'erreur "ACCESS_TOKEN_SCOPE_INSUFFICIENT".
    - La clé d'API (gratuite, depuis Google AI Studio) est la méthode standard
      et fiable pour gemini-2.5-flash.
    """
    global _model
    if _model is None:
        # On importe ICI (et pas en haut du fichier) pour que l'application
        # démarre même si la librairie manque ou si la clé est absente.
        import google.generativeai as genai

        # 1) On configure la librairie avec la clé d'API.
        genai.configure(api_key=config.GEMINI_API_KEY)

        # 2) On crée le modèle en lui donnant son "contexte" (message système).
        #    system_instruction = la personnalité / les règles de l'assistant.
        _model = genai.GenerativeModel(
            model_name=config.GEMINI_MODEL,
            system_instruction=config.LLM_SYSTEM_PROMPT,
        )
    return _model


def _format_context(context):
    """Met en forme les données capteurs/météo en un bloc lisible pour Gemini.

    Paramètre :
        context (dict | None) : mesures intérieures + météo extérieure.

    Retour :
        str : un bloc de texte (vide si aucune donnée exploitable).
    """
    if not context:
        return ""

    lignes = []
    t    = context.get("temperature")
    h    = context.get("humidity")
    tvoc = context.get("tvoc")
    eco2 = context.get("eco2")
    aq   = context.get("aq_label")
    if t    is not None: lignes.append("- Indoor temperature : {:.1f} C".format(t))
    if h    is not None: lignes.append("- Indoor humidity : {:.0f} %".format(h))
    if tvoc is not None: lignes.append("- VOC (TVOC) : {} ppb".format(tvoc))
    if eco2 is not None: lignes.append("- eCO2 : {} ppm".format(eco2))
    if aq:               lignes.append("- Air quality : {}".format(aq))

    ot = context.get("outdoor_temp")
    od = context.get("outdoor_desc")
    oh = context.get("outdoor_humidity")
    ws = context.get("wind_speed")
    if ot is not None: lignes.append("- Outdoor temperature : {:.1f} C".format(ot))
    if od:             lignes.append("- Outdoor weather : {}".format(od))
    if oh is not None: lignes.append("- Outdoor humidity : {} %".format(oh))
    if ws is not None: lignes.append("- Wind : {} m/s".format(ws))

    # Forecast
    fc = context.get("forecast")
    if fc:
        lignes.append("Forecast (next few days) :")
        for d in fc:
            try:
                lignes.append("- {} {} : min {:.0f} C, max {:.0f} C, {}, rain {} %".format(
                    d.get("jour", ""), d.get("date", ""),
                    d.get("min", 0), d.get("max", 0), d.get("ciel", ""),
                    int((d.get("pluie") or 0) * 100)))
            except Exception:
                pass

    if not lignes:
        return ""
    return "Current sensor and weather data :\n" + "\n".join(lignes)


def generate_reply(user_text, context=None):
    """Génère une réponse intelligente (texte) à partir du texte utilisateur.

    Paramètres :
        user_text (str) : la phrase de l'utilisateur (déjà transcrite).
        context (dict | None) : données capteurs/météo en direct. Si fournies,
            elles sont injectées dans le prompt pour que l'assistant réponde
            avec les vraies valeurs (température, humidité, qualité de l'air...).

    Retour :
        str : la réponse générée par Gemini, en français.

    Note sur les erreurs :
        Si l'appel à Gemini échoue (credentials invalides, réseau, quota...),
        une exception est levée. On la laisse remonter jusqu'à la route Flask,
        qui renverra alors un code HTTP 503.
    """
    import google.generativeai as genai
    genai.configure(api_key=config.GEMINI_API_KEY)

    # On préfixe la question avec le contexte capteurs/météo si disponible.
    bloc_contexte = _format_context(context)
    if bloc_contexte:
        prompt = bloc_contexte + "\n\nUser Question : " + user_text
    else:
        prompt = user_text

    # On essaie le modèle de config en premier, puis les replis (quotas séparés).
    modeles = [config.GEMINI_MODEL] + [m for m in _FALLBACK_MODELS if m != config.GEMINI_MODEL]

    import time
    now = time.time()
    derniere_erreur = None
    un_essai = False

    def _essai(nom):
        modele = genai.GenerativeModel(
            model_name=nom,
            system_instruction=config.LLM_SYSTEM_PROMPT,
        )
        # request_options timeout : plafonne chaque appel pour ne jamais bloquer.
        return modele.generate_content(prompt, request_options={"timeout": _CALL_TIMEOUT_S})

    for nom in modeles:
        if _MODEL_COOLDOWN.get(nom, 0) > now:
            continue                       # modèle en cooldown (quota récent) -> on saute
        un_essai = True
        try:
            response = _essai(nom)
            logger.info("Gemini OK avec le modele %s", nom)
            return response.text.strip()
        except Exception as e:
            derniere_erreur = e
            _MODEL_COOLDOWN[nom] = time.time() + _COOLDOWN_S
            logger.warning("Gemini modele %s indisponible: %s", nom, str(e)[:140])
            continue

    # Si TOUS les modèles étaient en cooldown (aucun essayé), on retente le 1er
    # en ignorant le cooldown — mieux qu'une panne totale.
    if not un_essai:
        try:
            response = _essai(modeles[0])
            return response.text.strip()
        except Exception as e:
            derniere_erreur = e

    # Tous les modèles ont échoué (quota global, réseau...) -> on remonte l'erreur.
    raise derniere_erreur if derniere_erreur else RuntimeError("Aucun modele Gemini disponible")
