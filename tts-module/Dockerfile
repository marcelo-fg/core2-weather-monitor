# =========================================================================
# Dockerfile
# =========================================================================
# Rôle : construire une image Docker du module TTS, afin de la déployer
# sur Google Cloud Run.
#
# Rappel pour l'oral : un Dockerfile est une "recette" qui décrit, étape
# par étape, comment construire un conteneur autonome contenant notre code
# et toutes ses dépendances.

# Image de base : Python 3.11 en version "slim" (légère, plus rapide à déployer).
FROM python:3.11-slim

# PYTHONUNBUFFERED=1 : Python n'attend pas pour afficher ses logs.
# On voit donc les messages en temps réel dans les logs Cloud Run.
ENV PYTHONUNBUFFERED=1

# Dossier de travail à l'intérieur du conteneur.
WORKDIR /app

# 1) On copie d'abord SEULEMENT requirements.txt, puis on installe.
#    Astuce : tant que requirements.txt ne change pas, Docker réutilise le
#    cache de cette étape -> les reconstructions sont beaucoup plus rapides.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 2) On copie ensuite tout le reste du code du projet.
COPY . .

# Cloud Run fournit le port via la variable d'environnement PORT.
# On expose 8080 par défaut (valeur standard de Cloud Run).
ENV PORT=8080
EXPOSE 8080

# 3) Démarrage en PRODUCTION avec gunicorn (serveur WSGI robuste).
#    - "app:app" = fichier app.py, variable "app".
#    - --workers 1 --threads 8 : suffisant pour ce petit service.
#    - On utilise la forme "exec ... $PORT" pour que la variable PORT
#      soit bien remplacée par sa valeur au démarrage.
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 app:app
