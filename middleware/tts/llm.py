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

import config


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


def generate_reply(user_text):
    """Génère une réponse intelligente (texte) à partir du texte utilisateur.

    Paramètre :
        user_text (str) : la phrase de l'utilisateur (déjà transcrite).

    Retour :
        str : la réponse générée par Gemini, en français.

    Note sur les erreurs :
        Si l'appel à Gemini échoue (credentials invalides, réseau, quota...),
        une exception est levée. On la laisse remonter jusqu'à la route Flask,
        qui renverra alors un code HTTP 503.
    """
    model = _get_model()

    # On envoie le texte de l'utilisateur au modèle. Le "contexte" (message
    # système) a déjà été donné à la création du modèle (system_instruction).
    response = model.generate_content(user_text)

    # response.text contient la réponse générée. On enlève les espaces inutiles.
    return response.text.strip()
