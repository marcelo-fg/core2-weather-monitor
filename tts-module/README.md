# Module Text-to-Speech (TTS) — Moniteur météo IoT

Module **Text-to-Speech** du projet de cours *Cloud and Advanced Analytics*
(HEC Lausanne, Master en Systèmes d'Information).

Ce module transforme du **texte français en audio WAV** grâce à l'API
**Google Cloud Text-to-Speech** (voix WaveNet naturelle), et expose ses
fonctionnalités via une **API HTTP Flask**. Il est conçu pour être branché
facilement au reste du projet (device M5Stack Core2, middleware Flask,
BigQuery, dashboard Streamlit) géré par mon coéquipier.

> Project Google Cloud : `weather-tts-noah`

---

## 1. Que fait ce module ?

- Convertit n'importe quel texte français en **fichier WAV** (format choisi
  car le M5Stack Core2 le lit mieux que le MP3).
- Compose automatiquement des **annonces vocales** selon un type d'événement
  (résumé matinal, alerte humidité, qualité d'air, bienvenue, météo).
- Offre un **mode conversation** (`/listen`) : reçoit la voix du M5Stack, la
  transcrit avec **Google Speech-to-Text**, génère une réponse intelligente
  avec **Google Gemini**, et la renvoie en **audio**.
- Met en **cache** les audios déjà générés (hash MD5 du texte → fichier WAV)
  pour ne pas rappeler Google inutilement.
- Applique un **rate-limiting** : refuse une annonce du même type si la
  dernière date de moins d'une heure.
- **Ne plante jamais** : en cas d'erreur, renvoie un JSON d'erreur avec un
  code HTTP adapté (400, 429, 503).

---

## 2. Structure du projet

```
tts-module/
├── README.md              ← ce fichier (serveur Flask)
├── M5STACK_UIFLOW.md      ← guide du device M5Stack (renvoie vers main.py)
├── GUIDE_VOLUME_M5STACK.md   ← régler le volume du HP (pièges + solution)
├── GUIDE_ASSISTANT_VOCAL.md  ← bouton C : micro → STT → Gemini → voix
├── main.py                ← code MicroPython du M5Stack Core2 (UIFlow 1.x)
├── requirements.txt       ← dépendances Python
├── .env.example           ← exemple de configuration
├── .gitignore / .dockerignore
├── Dockerfile             ← pour déployer sur Cloud Run
├── config.py              ← TOUTE la configuration (variables d'env)
├── app.py                 ← point d'entrée Flask
├── tts/
│   ├── service.py         ← Google Text-to-Speech (texte → WAV) + cache
│   ├── cache.py           ← cache des fichiers WAV (hash MD5)
│   ├── announcements.py   ← textes des annonces + rate-limiting
│   ├── stt.py             ← Google Speech-to-Text (voix → texte)
│   └── llm.py             ← Google Gemini (réponse intelligente)
├── routes/
│   └── tts_routes.py      ← routes Flask (/health, /speak, /announce, /listen)
├── static/
│   └── audio/             ← fichiers WAV générés (cache)
└── tests/
    └── test_tts.py        ← tests automatiques (pytest)
```

---

## 3. Prérequis

- **Python 3.11** (ou 3.10+).
- Un **compte de service Google Cloud** avec sa **clé JSON** (`gcp-credentials.json`),
  et les APIs **Text-to-Speech** + **Speech-to-Text** activées :
  ```bash
  gcloud services enable texttospeech.googleapis.com speech.googleapis.com --project weather-tts-noah
  ```
- Une **clé API Gemini** gratuite (pour le mode conversation `/listen`) créée
  sur [Google AI Studio](https://aistudio.google.com/apikey).

---

## 4. Installation

```bash
# 1. Se placer dans le dossier du projet
cd tts-module

# 2. (Recommandé) Créer un environnement virtuel Python
python3 -m venv .venv
source .venv/bin/activate        # sous Windows : .venv\Scripts\activate

# 3. Installer les dépendances
pip install -r requirements.txt
```

---

## 5. Configuration des variables d'environnement

Toute la configuration se fait via des variables d'environnement, lues dans
`config.py`. En local, le plus simple est d'utiliser un fichier `.env`.

```bash
# Copier l'exemple fourni puis l'adapter
cp .env.example .env
```

Variables principales (toutes ont une valeur par défaut) :

| Variable | Défaut | Description |
|---|---|---|
| `GOOGLE_APPLICATION_CREDENTIALS` | `gcp-credentials.json` | Chemin vers la clé JSON Google (TTS + STT) |
| `TTS_LANGUAGE_CODE` | `fr-FR` | Langue de la voix |
| `TTS_VOICE_NAME` | `fr-FR-Wavenet-C` | Voix WaveNet (féminine, naturelle) |
| `TTS_SPEAKING_RATE` | `1.0` | Vitesse de lecture |
| `TTS_PITCH` | `0.0` | Tonalité |
| `TTS_SAMPLE_RATE_HZ` | `24000` | Fréquence d'échantillonnage du WAV |
| `AUDIO_CACHE_DIR` | `static/audio` | Dossier du cache audio |
| `RATE_LIMIT_SECONDS` | `3600` | Délai min. entre 2 annonces identiques (1h) |
| `STT_LANGUAGE_CODE` | `fr-FR` | Langue de la reconnaissance vocale (`/listen`) |
| `STT_SAMPLE_RATE_HZ` | `8000` | Fréquence STT par défaut (le serveur lit sinon l'en-tête du WAV reçu) |
| `GEMINI_API_KEY` | *(vide)* | Clé API Gemini (gratuite, [AI Studio](https://aistudio.google.com/apikey)) pour `/listen` |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Modèle LLM Google Gemini utilisé par `/listen` |
| `PORT` | `8080` | Port du serveur Flask |
| `FLASK_DEBUG` | `false` | Mode debug (jamais en production) |

> **Credentials Google** : place le fichier `gcp-credentials.json` à la racine
> du projet. La librairie Google lit automatiquement la variable
> `GOOGLE_APPLICATION_CREDENTIALS` pour s'authentifier.

---

## 6. Lancer le service en local

```bash
# Avec l'environnement virtuel activé et le .env configuré :
python app.py
```

Le service démarre sur `http://localhost:8080`.

> Note : si les credentials Google sont absents, le serveur **démarre quand
> même** ; il renverra une erreur `503` propre lors du premier appel à
> `/speak` ou `/announce` (le `/health` continue de fonctionner).

---

## 7. Tester les endpoints (exemples curl)

### `GET /health` — vérifier que le service tourne
```bash
curl http://localhost:8080/health
# Réponse : {"status":"ok"}
```

### `POST /speak` — convertir un texte libre en WAV
```bash
curl -X POST http://localhost:8080/speak \
  -H "Content-Type: application/json" \
  -d '{"text": "Bonjour, ceci est un test du module de synthèse vocale."}' \
  --output test.wav

# On peut ensuite écouter le résultat :
#   macOS  : afplay test.wav
#   Linux  : aplay test.wav
```

### `POST /announce` — générer une annonce selon un événement
```bash
curl -X POST http://localhost:8080/announce \
  -H "Content-Type: application/json" \
  -d '{"event_type": "morning_briefing"}' \
  --output annonce.wav
```

Types d'événements (`event_type`) disponibles :

| event_type | Contenu de l'annonce |
|---|---|
| `morning_briefing` | Résumé matinal + rappel parapluie si pluie prévue |
| `humidity_alert` | Alerte humidité intérieure faible (< 40 %) |
| `air_quality_alert` | Alerte qualité d'air mauvaise |
| `welcome` | Message de bienvenue (détection de présence) |
| `weather_update` | Annonce de la météo actuelle |

### `POST /listen` — mode conversation (voix → texte → LLM → voix)

Cet endpoint reçoit un fichier audio (la voix enregistrée par le M5Stack),
le transcrit avec **Google Speech-to-Text**, génère une réponse avec
**Google Gemini (gemini-2.5-flash)**, puis renvoie cette réponse en **WAV**.

```bash
# On envoie un fichier WAV (corps binaire brut, comme le fait le M5Stack) :
curl -X POST http://localhost:8080/listen \
  --data-binary @question.wav \
  -H "Content-Type: audio/wav" \
  --output reponse.wav

# Variante multipart (pratique pour tester à la main) :
curl -X POST http://localhost:8080/listen -F "audio=@question.wav" --output reponse.wav
```

> Nécessite : des **credentials Google valides** (Speech-to-Text activé) **et**
> une **clé API Gemini** (`GEMINI_API_KEY`, gratuite via
> [AI Studio](https://aistudio.google.com/apikey)). L'API Gemini Developer
> n'accepte pas de façon fiable le compte de service (erreur de scope OAuth),
> d'où la clé d'API dédiée pour le LLM. Sinon → `503`. L'audio envoyé est un
> fichier WAV (le serveur détecte le format depuis l'en-tête). Voir
> **`M5STACK_UIFLOW.md`** pour le code du device.

### Exemples d'erreurs (le service ne plante jamais)
```bash
# Champ manquant -> 400
curl -X POST http://localhost:8080/speak -H "Content-Type: application/json" -d '{}'
# {"error":"Le champ 'text' est obligatoire."}

# event_type inconnu -> 400
curl -X POST http://localhost:8080/announce -H "Content-Type: application/json" -d '{"event_type":"xxx"}'

# Même annonce deux fois en moins d'1h -> 429 (rate-limiting)

# /listen sans audio -> 400 ; Google STT ou Gemini indisponible -> 503
```

> **Activer Speech-to-Text** sur le projet (une seule fois) :
> ```bash
> gcloud services enable speech.googleapis.com --project weather-tts-noah
> ```
> Pour Gemini, pas besoin d'activer d'API via gcloud : la **clé `GEMINI_API_KEY`**
> (créée sur [AI Studio](https://aistudio.google.com/apikey)) suffit.

---

## 8. Lancer les tests

Les tests **n'appellent pas la vraie API Google** (elle est "mockée"), donc
ils sont rapides, gratuits et fonctionnent sans credentials.

```bash
pytest
```

---

## 9. Déploiement sur Google Cloud Run

> Cloud Run construit l'image depuis les sources (`--source .`) et fournit
> automatiquement la variable `PORT`. Pour Google (TTS/STT), il utilise le
> **compte de service** attaché au service (pas besoin de `gcp-credentials.json`).
> Pour Gemini, il faut passer la **clé API** en variable d'environnement.

```bash
# 0. Se connecter et sélectionner le projet
gcloud auth login
gcloud config set project weather-tts-noah

# 1. Activer les APIs nécessaires (une seule fois)
gcloud services enable texttospeech.googleapis.com speech.googleapis.com run.googleapis.com cloudbuild.googleapis.com

# 2. Construire + déployer en une commande, en passant la clé Gemini
gcloud run deploy tts-module \
  --source . \
  --region europe-west9 \
  --allow-unauthenticated \
  --set-env-vars GEMINI_API_KEY=AIza_ta_cle_gemini
```

À la fin, `gcloud` affiche l'URL publique du service. On peut alors tester :
```bash
curl https://<URL-CLOUD-RUN>/health
```

> ⚠️ Le `.env` n'est **pas** envoyé à Cloud Run (il est ignoré). La clé Gemini
> doit donc être fournie via `--set-env-vars` (ou `--update-env-vars` pour ne
> pas écraser les autres variables). Le compte de service Cloud Run doit avoir
> accès à Text-to-Speech et Speech-to-Text.

---

## 10. Intégration avec le reste du projet

On appelle simplement les endpoints HTTP (depuis le M5Stack ou un middleware) :

- Faire parler un texte libre : `POST /speak` avec `{"text": "..."}`.
- Annonce automatique : `POST /announce` avec `{"event_type": "..."}`.
- Conversation : `POST /listen` avec l'audio WAV → réponse vocale (WAV).

Le code du **device M5Stack** qui utilise ces endpoints est dans **`main.py`** ;
son installation est expliquée dans **`M5STACK_UIFLOW.md`**.

Les données météo des annonces sont pour l'instant **fictives**
(`FAKE_WEATHER_DATA` dans `tts/announcements.py`). Il suffira de les
remplacer par les vraies données OpenWeatherMap / capteurs, soit en
modifiant ce dictionnaire, soit en passant un `data` personnalisé à la
fonction `build_announcement_text`.
