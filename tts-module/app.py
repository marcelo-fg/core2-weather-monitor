"""
app.py
======
Rôle du fichier :
Point d'entrée de l'application Flask du module Text-to-Speech.

Ce fichier est volontairement COURT : toute la logique se trouve dans les
autres fichiers (tts/ et routes/). Ici, on se contente de :
1. Créer l'application Flask.
2. Y brancher les routes (le Blueprint défini dans routes/tts_routes.py).
3. Lancer le serveur quand on exécute directement "python app.py".

Ce découpage rend le code plus facile à lire et à expliquer à l'oral.
"""

from flask import Flask

import config
from routes.tts_routes import tts_blueprint


def create_app():
    """Crée et configure l'application Flask.

    On utilise une "factory function" (une fonction qui FABRIQUE l'app) :
    c'est une bonne pratique Flask, notamment parce qu'elle facilite les
    tests (on peut créer une app neuve pour chaque test).
    """
    app = Flask(__name__)

    # On branche toutes les routes du module TTS (/health, /speak, /announce).
    app.register_blueprint(tts_blueprint)

    return app


# On crée l'application au niveau du module pour que les serveurs de
# production comme gunicorn (utilisé sur Cloud Run) puissent la trouver
# via la référence "app:app" (fichier app.py, variable app).
app = create_app()


if __name__ == "__main__":
    # Ce bloc ne s'exécute QUE si on lance "python app.py" directement.
    # En production (Cloud Run), c'est gunicorn qui démarre l'app (voir Dockerfile),
    # et ce bloc est ignoré.
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
    )
