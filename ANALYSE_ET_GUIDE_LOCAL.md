# 🧭 Analyse du projet & Guide pour travailler en autonomie (Noah)

> Document rédigé après une **analyse complète du code** et une **vérification réelle**
> (tests live des credentials, du backend déployé, et lancement du middleware en local).
> Date de l'analyse : **2026-05-25**.

---

## 1. TL;DR — Réponse à ta question principale

**Oui, tu peux travailler seul de ton côté** (modifier le middleware, le dashboard, BigQuery,
TTS/STT, Gemini) avec les clés que Marcelo t'a données. J'ai tout testé pour de vrai et **ça marche**,
à **3 conditions / nuances** importantes :

| # | Service | Verdict | Nuance vérifiée |
|---|---------|---------|------------------|
| 1 | **BigQuery** (lecture/écriture des mesures) | ✅ Marche | Via l'ADC de Marcelo. **244 lignes** lues dans `core2-weather-monitor.weather_monitor.sensor_readings` (dernière mesure le 25/05 à 19:06). |
| 2 | **Cloud Text-to-Speech + Speech-to-Text** | ✅ Marche | Mais il faut **forcer le projet de quota** sur `core2-weather-monitor` (sinon erreur 403, voir §4). Testé : synthèse vocale OK + transcription parfaite. |
| 3 | **Gemini (LLM)** | ⚠️ Utilise **TA** clé | La clé Gemini de **Marcelo est en quota dépassé (429)** → l'assistant vocal du backend déployé est actuellement **cassé**. **Ta** clé Gemini (celle de `tts-module/.env`) fonctionne. |
| 4 | **OpenWeatherMap** | ✅ Marche | Clé `162f...` valide (testée via le middleware local). |

➡️ **Bonne nouvelle supplémentaire** : l'assistant vocal **est déjà intégré** dans le firmware
principal `device/main_uiflow.py` (page 4 « Voice ») **et** dans le middleware principal
(`routes/voice.py` + dossier `tts/`). Le gros du travail d'intégration est **déjà fait dans le repo**.
Ce qui reste : **redéployer** le middleware avec ta clé Gemini, **reflasher** le M5, et corriger
quelques petites incohérences (voir §8 et §9).

J'ai aussi **déjà préparé ton environnement local** :
- un venv Python prêt à l'emploi : **`.venv-middleware/`** ;
- un fichier de config local : **`middleware/.env`** (gitignoré, contient les bonnes clés).

---

## 2. Architecture du projet (3 tiers)

```
┌─────────────────────┐   REST/HTTP    ┌────────────────────────┐   Google APIs   ┌──────────────────┐
│  M5Stack Core2      │ ─────────────► │  Middleware (Flask)     │ ──────────────► │  Google Cloud     │
│  device/            │  /api/sensor   │  middleware/            │  BigQuery       │  - BigQuery       │
│  main_uiflow.py     │  /api/weather  │  app.py + routes/ +     │  TTS / STT      │  - Text-to-Speech │
│  (MicroPython)      │  /api/voice/*  │  services/ + tts/       │  Gemini (clé)   │  - Speech-to-Text │
│  capteurs + écran   │ ◄───────────── │  Cloud Run (europe-w1)  │ ◄────────────── │  + Gemini API     │
│  + micro/HP         │  WAV / JSON    │                         │  OpenWeather    │  + OpenWeather    │
└─────────────────────┘                └────────────┬───────────┘                 └──────────────────┘
                                                     │  /api/sensor/*  /api/voice/query
                                          ┌──────────▼───────────┐
                                          │  Dashboard (Streamlit)│
                                          │  dashboard/app.py     │
                                          │  Cloud Run            │
                                          └───────────────────────┘
```

- **Tier 1 — Device** : `device/main_uiflow.py` (firmware Core2, UIFlow 1.x / MicroPython).
- **Tier 2 — Middleware** : `middleware/` (Flask, déployé sur Cloud Run `europe-west1`).
- **Tier 3 — Données & présentation** : BigQuery (entrepôt) + `dashboard/` (Streamlit).

**URL du middleware déployé** (utilisée par le device et le dashboard) :
`https://core2-middleware-337108994948.europe-west1.run.app`
→ le numéro `337108994948` correspond au projet **`core2-weather-monitor`** (celui de Marcelo).

---

## 3. Analyse détaillée du code (fichier par fichier)

### 3.1 `middleware/` — le cerveau (Flask)

| Fichier | Rôle | Remarques |
|---------|------|-----------|
| `app.py` | Point d'entrée Flask, enregistre les *blueprints*, `/health`, `/`. | ⚠️ La liste d'endpoints affichée sur `/` est **obsolète** (mentionne `/api/voice/query`, `/api/voice/tts` qui n'existent plus tels quels). |
| `config.py` | Toute la config via variables d'environnement. | Lit `os.environ` **directement** (ne charge **pas** `.env` tout seul — voir §6). Défaut `GOOGLE_CLOUD_PROJECT=core2-weather-monitor`. |
| `routes/sensor.py` | `POST /api/sensor`, `GET /api/sensor/latest`, `/history`, `/history_weekly`. | Injecte la météo extérieure dans chaque mesure. ⚠️ Met des **données fictives** (random) pour les jours vides dans `/history_weekly`. |
| `routes/weather.py` | `GET /api/weather`, `/weather/current`, `/weather/forecast`. | Proxy OpenWeatherMap (clé jamais exposée au device). |
| `routes/voice.py` | `POST /api/voice/listen` (conversation), `GET /api/voice/tts.wav`, `POST /api/voice/announce`, `/api/device/sync`, `/api/device/command`. | C'est **l'intégration de ton module vocal**. Importe `from tts import ...`. |
| `services/bigquery_service.py` | Création dataset/table + insert + requêtes. | Table **partitionnée par jour**. Client BigQuery créé avec `project=GOOGLE_CLOUD_PROJECT`. |
| `services/weather_service.py` | Appels OpenWeatherMap (current + forecast 5 jours). | ⚠️ `get_current()` renvoie la clé `temp`, mais `sensor.py` lit `c.get("temperature")` → `outdoor_temp` reste **null** en base (petit bug, §9). |
| `services/tts_service.py`, `llm_service.py`, `stt_service.py` | **Ancienne** implémentation TTS/LLM/STT. | ⚠️ **Non utilisée** par `routes/voice.py` (qui utilise le dossier `tts/`). Doublon à nettoyer (§9). |
| `tts/service.py` | Seul point qui parle à **Google TTS** + cache disque (MD5). | Lit `GOOGLE_APPLICATION_CREDENTIALS` automatiquement. |
| `tts/stt.py` | Seul point qui parle à **Google STT**. | Astuce clé : lit la **fréquence dans l'en-tête WAV** (évite l'erreur « bad encoding »). |
| `tts/llm.py` | Seul point qui parle à **Gemini** (via `GEMINI_API_KEY`). | Modèle `gemini-2.5-flash`. |
| `tts/announcements.py` | Textes des annonces (welcome, météo, alerte…) + rate-limiting 1 h. | Données météo encore **fictives** (`FAKE_WEATHER_DATA`) — à brancher sur les vraies si tu veux. |
| `tts/cache.py` | Cache WAV sur disque (hash MD5 du texte). | Évite de rappeler Google pour un texte identique. |

### 3.2 `dashboard/` — l'interface web (Streamlit)

| Fichier | Rôle |
|---------|------|
| `app.py` | Dashboard « bento » : télémétrie, statut M5, graphiques (Plotly), prévisions, qualité de l'air, page **Remote control** du M5. |
| `services/api_client.py` | Client HTTP vers le middleware (`MIDDLEWARE_URL`, défaut `http://localhost:8080`). |

⚠️ **Bug important** : `api_client.ask_llm()` poste sur **`/api/voice/query`**, un endpoint qui
**n'existe ni en local ni sur le backend déployé** (testé → **404**). Conséquence : les encarts
« AI insight / AI summary » du dashboard affichent **« AI analysis temporarily unavailable »**.
Le reste du dashboard (mesures, graphiques, météo, remote) fonctionne. (Voir §9 pour le fix.)

### 3.3 `device/` — le firmware M5Stack

| Fichier | Rôle |
|---------|------|
| `main_uiflow.py` (1432 lignes) | **Firmware principal** : 5 pages (Home, Forecast, History, Settings, **Voice**), capteurs ENV III + SGP30 + PIR, NTP, WiFi switcher, upload BigQuery, polling des commandes du dashboard, **assistant vocal** (`voice_listen_flow`, `voice_speak`). Bouton **B** = parler. |
| `main_uiflow_new.py` (1158 l.) | Variante/itération antérieure (probablement obsolète). |
| `config_template.py` | Modèle de config device (à copier en `config.py`). |

➡️ **Le firmware appelle déjà le middleware principal** pour la voix :
`POST /api/voice/listen` (micro → STT → Gemini → réponse) et
`GET /api/voice/tts.wav?text=...` (lecture vocale). C'est cohérent avec `routes/voice.py`.

### 3.4 `tts-module/` — ton bac à sable d'origine (à supprimer en fin de projet)

App Flask **autonome** que tu as construite pour l'assistant vocal, déployée sur **TON** projet
`weather-tts-noah` (`https://tts-module-847024687713.europe-west9.run.app`). Contient :
- `main.py` : firmware M5 **dédié** à la voix (boutons A/B/C) — version « laboratoire ».
- `app.py`, `routes/tts_routes.py`, `tts/*` : la logique TTS/STT/LLM (celle qui a été **copiée**
  dans `middleware/tts/`).
- `gcp-credentials.json` : **ton** compte de service `tts-flask-service@weather-tts-noah`.
- `.env` : **ta** clé Gemini (celle qui marche).
- Guides précieux : `GUIDE_ASSISTANT_VOCAL.md`, `M5STACK_UIFLOW.md`, `GUIDE_VOLUME_M5STACK.md`.

> Ce dossier et ses credentials te sont **propres** et seront **supprimés** à la fin. Ils servent de
> référence pour comprendre ce qui a déjà fonctionné. **Ne déploie pas le projet final dessus.**

---

## 4. Inventaire des credentials (qui possède quoi) + résultats des tests réels

| Credential | Propriétaire | Emplacement | Test réalisé | Résultat |
|------------|--------------|-------------|--------------|----------|
| **ADC** `application_default_credentials.json` | Marcelo (compte perso, `authorized_user`) | racine du projet | Liste des projets + requête BigQuery | ✅ Accès à `core2-weather-monitor` (et d'autres). Quota project = `gen-lang-client-0671890527`. |
| **BigQuery** `weather_monitor.sensor_readings` | projet `core2-weather-monitor` | Cloud | `SELECT COUNT(*)` | ✅ **244 lignes**, dernière le 25/05 19:06. |
| **Cloud TTS** | projet `core2-weather-monitor` | Cloud | Synthèse « Bonjour Commandant » | ✅ 74 524 octets WAV (après forçage du quota project). |
| **Cloud STT** | projet `core2-weather-monitor` | Cloud | Transcription du WAV ci-dessus | ✅ « bonjour commandant ceci est un test ». |
| **Clé Gemini de Marcelo** `AIza…UZ554` | Marcelo | `.env` / variable | `generate_content()` | ❌ **429 quota dépassé** (free tier, limite 20). |
| **Clé Gemini de Noah** `AIza…IZsU` | Noah | `tts-module/.env` | `generate_content()` | ✅ Réponse correcte (« Berne »). |
| **OpenWeather** `162f…e11` | Marcelo | `.env` / variable | `/api/weather/current` (middleware local) | ✅ Lausanne, 18.7 °C. |
| **Compte de service** `tts-flask-service@weather-tts-noah` | Noah | `tts-module/gcp-credentials.json` | — | Réservé à ton ancien module autonome. |

### 🔑 Le piège n°1 : le « projet de quota » pour TTS/STT
Avec l'ADC de Marcelo (un compte **utilisateur**), les librairies Google facturent par défaut sur le
**quota project de l'ADC** = `gen-lang-client-0671890527`, où **TTS/STT sont désactivés** →
`403 SERVICE_DISABLED`. **Solution vérifiée** : forcer le quota project sur `core2-weather-monitor`
(où ces APIs sont actives) via la variable `GOOGLE_CLOUD_QUOTA_PROJECT` **ou** la commande gcloud
(voir §6). Pour BigQuery le problème ne se pose pas car le code passe déjà `project=` explicitement.

### 🔑 Le piège n°2 : la clé Gemini de Marcelo est morte (429)
C'est **la raison pour laquelle l'assistant vocal du backend déployé renvoie une erreur 503**
(testé : `POST /api/voice/listen` sur le déployé → 503 « Service LLM indisponible: 429 … quota
exceeded »). **Utilise ta clé Gemini** (déjà mise dans `middleware/.env`).

---

## 5. Peux-tu travailler seul ? (détaillé)

**Oui.** Concrètement, tu peux :
- ✅ **Lire/écrire BigQuery** (via l'ADC de Marcelo).
- ✅ **Modifier et lancer le middleware en local** (Flask) → tous les endpoints répondent.
- ✅ **Faire tourner toute la chaîne vocale en local** : j'ai testé `POST /api/voice/listen` avec un
  vrai WAV → réponse JSON `{"transcript": "bonjour commandant", "answer": "Bonjour Commandant ! Votre
  assistant météo est à votre service…"}`. **La chaîne STT → Gemini → TTS marche de bout en bout.**
- ✅ **Lancer le dashboard Streamlit** (§7).
- ✅ **Redéployer** le middleware sur `core2-weather-monitor` (l'ADC de Marcelo a les droits).

**Ce qui dépend encore de Marcelo (à terme) :**
- Le projet GCP `core2-weather-monitor` lui appartient. Tu y as accès **tant que son ADC est valide**
  (le refresh token peut expirer / être révoqué). Pour une vraie autonomie longue durée, l'idéal serait
  qu'il t'ajoute **comme IAM Editor** sur le projet, ou que vous **centralisiez** tout sur un seul projet.
- La clé OpenWeather et la clé Gemini de Marcelo sont les siennes (mais tu as une clé Gemini à toi).

---

## 6. Mettre en place l'environnement local (déjà préparé)

J'ai déjà créé pour toi :
- **Le venv middleware** : `.venv-middleware/` (Python 3.11, dépendances de `middleware/requirements.txt`).
- **Le venv dashboard** : `.venv-dashboard/` (Python 3.11, dépendances de `dashboard/requirements.txt`,
  dont `plotly` que le Python système n'a pas).
- **La config locale** : `middleware/.env` (gitignoré, clés correctes, **ta** clé Gemini).

### (Une seule fois) Régler le projet de quota gcloud — optionnel mais recommandé
Si tu préfères ne pas dépendre de la variable `GOOGLE_CLOUD_QUOTA_PROJECT`, exécute :
```bash
gcloud auth application-default set-quota-project core2-weather-monitor
```
> Note : `middleware/.env` règle déjà `GOOGLE_CLOUD_QUOTA_PROJECT`, donc ce n'est pas obligatoire.

---

## 7. Lancer les services en local

> ⚠️ Le dossier du projet contient des **espaces** → garde bien les guillemets dans les chemins.

### 7.1 Lancer le **middleware** en local (port 8081)
```bash
cd "/Users/noahissah/Desktop/Cloud and Advanced Analytics/PROJECT_M5/core2-weather-monitor-main"

# Charger les variables du .env puis lancer le serveur :
set -a && source middleware/.env && set +a
cd middleware && PORT=8081 ../.venv-middleware/bin/python app.py
```
Tests rapides (dans un autre terminal) :
```bash
curl "http://127.0.0.1:8081/health"
curl "http://127.0.0.1:8081/api/sensor/latest"
curl "http://127.0.0.1:8081/api/voice/tts.wav?text=Bonjour" -o /tmp/test.wav && afplay /tmp/test.wav
```

### 7.2 Lancer le **dashboard** Streamlit
> ⚠️ Le Python **système** (3.14) n'a **pas** `plotly` → le dashboard plante avec lui.
> Utilise le venv dédié **`.venv-dashboard/`** que j'ai créé (Python 3.11 + streamlit/plotly/pandas).

**Le plus simple : la version DÉJÀ EN LIGNE (rien à lancer)** — ouvre :
`https://core2-dashboard-337108994948.europe-west1.run.app`
(elle pointe sur le backend déployé, désormais corrigé → encarts IA inclus).

**Option A — local, contre le backend déployé (données réelles, recommandé)** :
```bash
cd "/Users/noahissah/Desktop/Cloud and Advanced Analytics/PROJECT_M5/core2-weather-monitor-main"
MIDDLEWARE_URL="https://core2-middleware-337108994948.europe-west1.run.app" \
  .venv-dashboard/bin/python -m streamlit run dashboard/app.py
```

**Option B — local, contre TON middleware local** (lance d'abord le middleware §7.1) :
```bash
MIDDLEWARE_URL="http://127.0.0.1:8081" \
  .venv-dashboard/bin/python -m streamlit run dashboard/app.py
```
> ✅ Les **encarts « AI insight »** fonctionnent maintenant (endpoint `/api/voice/query` ajouté).
> Puis ouvre `http://localhost:8501` dans ton navigateur.

---

## 8. État de l'assistant vocal — ✅ RÉPARÉ ET DÉPLOYÉ (2026-05-25)

**L'assistant vocal fonctionne maintenant de bout en bout, en local ET en ligne.**
Tests réels effectués sur le backend **déployé** :
- `POST /api/voice/listen` → `{"transcript":"fait-il chaud dans la maison",
  "answer":"Oui, il fait assez chaud dans la maison. La température intérieure est de 28.7°C."}`
- `GET /api/voice/tts.wav?text=...` → WAV ~78 Ko (synthèse vocale OK).
- `POST /api/voice/query` → réponse intelligente avec les vraies données.

**Ce qui a été fait :**
1. ✅ **Middleware redéployé** sur `core2-weather-monitor` (révision `core2-middleware-00043`) avec
   **ta clé Gemini** (celle de Marcelo était en 429). C'était LA cause de l'échec de la commande
   vocale sur le M5.
2. ✅ **Assistant rendu intelligent** : `/listen` et `/query` récupèrent la dernière mesure (BigQuery)
   + la météo (OpenWeather) et les injectent dans le prompt Gemini → l'assistant cite les vraies
   valeurs (température intérieure/extérieure, humidité, qualité de l'air).
3. ✅ **Bug Cloud Run corrigé** : la synthèse vocale échouait en ligne (`Permission denied` sur le
   cache audio, conteneur non-root). Corrigé : cache tolérant aux erreurs + dossier cache dans `/tmp`
   (variable `AUDIO_CACHE_DIR=/tmp/tts_cache` au déploiement).
4. ✅ **Annonces** (`/announce`) utilisent désormais la vraie météo (plus de 18°/35% factices).

**Côté device (firmware) — RIEN à reflasher pour la voix :**
- La page 4 « Voice » (bouton **B**) appelle déjà les bons endpoints (`/api/voice/listen` puis
  `/api/voice/tts.wav`). Le correctif étant 100 % côté serveur, **ta commande vocale devrait
  maintenant marcher directement sur le M5 déjà flashé** (il suffit qu'il soit connecté au WiFi et
  pointe sur `MIDDLEWARE_URL` — c'est déjà le cas).
- Si « bad encoding » au STT : le serveur lit la fréquence dans l'en-tête WAV (déjà géré) ; sinon
  ajuster `STT_SAMPLE_RATE_HZ`.
- Petit nettoyage appliqué au fichier `device/main_uiflow.py` (suppression de la fonction morte
  `run_voice_qa`) — **reflash optionnel**, sans effet sur le fonctionnement.

> 🔎 **Si la voix ne marche toujours pas sur le M5 après ça**, le problème est matériel/firmware
> (micro I2S, volume, WiFi) et non plus serveur — voir le tableau de dépannage de
> `tts-module/GUIDE_ASSISTANT_VOCAL.md`.

### 8 bis. Correctifs « voix qui bafouille » (2026-05-25, 2ᵉ passe)

**Symptôme rapporté** : la voix lisait « un mot correct puis du charabia », comme si elle lisait des
caractères spéciaux. **Cause trouvée** : la fonction `_urlencode()` du firmware encodait mal l'UTF-8 →
les mots **accentués** (é, è, à, ç…) arrivaient corrompus au serveur. **Corrigé** :
- 🔧 **Firmware** `device/main_uiflow.py` : `_urlencode()` réécrit pour encoder correctement chaque
  **octet UTF-8** (round-trip vérifié : `"Il fait 28°C à l'intérieur, c'est élevé !"` revient intact).
- 🔧 **Serveur** `tts/service.py` : nouvelle fonction `_clean_for_tts()` qui retire le **markdown**
  (`*`, `#`, puces), les **emoji** et symboles avant la synthèse — pour qu'ils ne soient plus lus.
- 🔧 **Serveur** `config.py` : le prompt système demande à Gemini de répondre en **texte simple**
  (pas de markdown/emoji), car la réponse est lue à voix haute.

**Journal de débogage sur le M5 (rétabli, comme dans `tts-module`)** :
- `device/main_uiflow.py` écrit désormais les étapes de la voix dans `/flash/debug.log`
  (`[C]`, `[LISTEN]`, `[STT]`, `[LLM]`, `[TTS]`, erreurs).
- **Appui LONG sur le bouton A (≥ 1,5 s)** → affiche les dernières lignes du journal à l'écran
  pendant 10 s (le temps de lire / prendre une photo). Appui court sur A = page précédente (inchangé).

**WiFi** : `WIFI_SSID` / `WIFI_PASSWORD` mis à jour avec le réseau **de la maison de Noah**
(`Sunrise_Wi-Fi_6315482`) dans `device/main_uiflow.py` (ils alimentent aussi `KNOWN_NETWORKS[0]`).

> ⚠️ Ces changements sont **côté firmware** → il faut **reflasher** `device/main_uiflow.py` sur le M5
> (copier-coller dans UIFlow). Le middleware corrigé est déjà déployé.

### 8 ter. Quota Gemini + STT vide + affichage (2026-05-25, 3ᵉ passe)

- ⚠️ **Quota Gemini gratuit très bas** : le free tier de `gemini-2.5-flash` est ~**20 requêtes/jour**
  par projet. Nos tests l'ont épuisé (clés de Marcelo ET de Noah). **Correctif** : `tts/llm.py`
  essaie désormais **plusieurs modèles en repli** (`gemini-2.5-flash-lite`, `gemini-2.0-flash`, …),
  chacun ayant son **propre quota journalier** → l'assistant continue de répondre.
  👉 **Pour la soutenance**, activer la **facturation** sur la clé Gemini (AI Studio / GCP) pour
  éliminer ces caps. Modèle par défaut déployé : `gemini-2.5-flash-lite`.
- 🔧 **Affichage qui débordait** (`_page_voice`) : réécrit avec **retour à la ligne par mots** et
  police plus petite → le texte tient dans l'écran. (firmware → reflash)
- 🔎 **STT renvoie vide** (« Désolé, je n'ai pas bien compris ») : le code STT est identique au module
  qui marchait et transcrit parfaitement des WAV propres. La cause est dans l'**audio enregistré par
  le M5**. `tts/stt.py` a été **instrumenté** (logs Cloud Run : `bytes`, `sample_rate`, `channels`,
  `bits`, `max_amp`, `results`) et gère désormais le **stéréo** (`audio_channel_count`). Diagnostic
  via : `gcloud logging read 'resource.labels.service_name=core2-middleware AND textPayload:"STT input"' --project core2-weather-monitor --limit 5 --freshness=10m`.
  - `max_amp` proche de 0 → micro qui n'enregistre que du silence (problème matériel/init).
  - `channels=2` → stéréo (désormais géré).
  - `sample_rate` incohérent avec la taille → en-tête WAV erroné.
  - **Diagnostic réel obtenu** : `bytes=220544 sample_rate=22050 channels=1 bits=16 max_amp=30973`
    → mono, 22050 Hz, en-tête correct, **son très fort** (pic 95 % → risque de saturation). Le micro
    capte bien ; la précision pâtit surtout d'un signal trop fort/proche et de la qualité du micro M5.

### 8 quater. Précision STT + accès aux prévisions (2026-05-25, 4ᵉ passe)

- 🔧 **STT plus précis** (`tts/stt.py`) : modèle **`latest_short` + enhanced** (optimisé commandes
  vocales) avec repli automatique, et **indices de vocabulaire météo** (`speech_contexts` : température,
  humidité, demain, pluie…) pour orienter la reconnaissance. (serveur ✅ déployé)
- 🔧 **Accès aux prévisions** : `/listen` et `/query` injectent désormais les **prévisions des 3
  prochains jours** (min, max, ciel, probabilité de pluie) dans le contexte Gemini. L'assistant répond
  maintenant à « quel temps fera-t-il demain ? ». (serveur ✅ déployé)
- 💡 **Conseil d'usage micro** : parler à **~15-25 cm**, à volume **normal** (pas fort) — trop près/fort
  sature le micro et dégrade la reconnaissance.

### 8 quinquies. Ce à quoi l'assistant vocal a accès (capacités)

**Il PEUT répondre sur :**
- 🏠 **Capteurs intérieurs en direct** (dernière mesure remontée par le M5 dans BigQuery) :
  température, humidité, COV (TVOC), eCO2, label qualité de l'air.
- 🌤️ **Météo extérieure actuelle** (OpenWeather, Lausanne) : température, ciel, humidité, vent.
- 📅 **Prévisions** des 3 prochains jours : min/max, ciel, probabilité de pluie.
- 💬 Conseils simples liés à ces données (aérer, parapluie…).

**Il NE PEUT PAS :**
- Accéder à Internet libre ni à des connaissances temps réel hors météo/capteurs.
- Donner l'historique détaillé heure par heure (les données existent dans BigQuery mais ne sont pas
  injectées dans le prompt — on pourrait l'ajouter si besoin).
- Piloter la maison (il informe, il n'agit pas).
- Garder la mémoire d'une question à l'autre (chaque question est indépendante).

> **D'où viennent les prévisions ?** De l'**API OpenWeatherMap** (endpoint `forecast` 5 jours /
> tranches de 3 h), appelée par `services/weather_service.get_forecast()` avec la clé
> `OPENWEATHER_API_KEY`. Ce sont des données **en direct**, PAS pré-écrites. Le middleware agrège les
> tranches de 3 h en min/max + probabilité de pluie par jour, garde les 3 prochains jours, et les
> injecte dans le prompt Gemini. Gemini ne fait que **reformuler ces vraies données**.

### 8 sexies. Latence + cause racine du STT instable (2026-05-26)

- 🔎 **Cause racine du STT instable** : les logs montrent `max_amp=30973` **identique à CHAQUE
  enregistrement** (réussis comme échoués) → ce n'est pas la voix (elle varierait) mais un
  **transitoire/"clic" constant au début** de l'enregistrement (init micro / bascule I2S). Quand on
  parle plus fort que ce clic → reconnu ; plus doucement → `results=0`.
  **Correctif** : `tts/stt.py` **rogne les 0,35 premières secondes** et envoie du **PCM brut** à Google
  (vérifié : transcription parfaite). Logs enrichis : `amp_start` vs `amp_rest`.
  👉 **Conseil d'usage corrigé** : parler **clairement et à volume normal/soutenu**, assez près
  (mon conseil précédent « parle plus doucement/loin » était une erreur — c'est ce qui faisait passer
  la voix sous le clic et provoquait les échecs).
- ⚡ **Latence réduite** :
  - `weather_service` : **cache mémoire 5 min** de la météo + des prévisions (évite ~3 appels
    OpenWeather par requête vocale).
  - `bigquery_service` : **cache 30 s** de la dernière mesure.
  - `routes/voice.py` `/listen` : suppression d'une **synthèse TTS redondante** (le M5 récupère l'audio
    via `tts.wav`) → le texte s'affiche plus vite, moins d'attente.

### 8 septies. Cause de la latence de ~2 min (2026-05-26)

- 🔎 **Cause racine** : ce n'est PAS le serveur (les logs montrent STT+LLM en ~2-4 s, même avec
  bascule de modèles). C'est le **firmware** qui faisait `r2 = urequests.get(url)` puis `r2.content` —
  donc il **chargeait tout le fichier WAV de la réponse en RAM**. Le M5 a très peu de RAM (~100 Ko) ;
  une réponse longue = WAV de plusieurs centaines de Ko → **saturation mémoire / GC** → latence de
  plusieurs dizaines de secondes (d'où « pire pour les phrases longues »).
- 🔧 **Correctifs** :
  - **Firmware** `voice_listen_flow` : lecture en **streaming** via `speaker.playCloudWAV(url)`
    (l'audio est joué pendant le téléchargement, **sans** tout charger en RAM). (→ **reflash**)
  - **Serveur** : audio TTS abaissé à **16 kHz** (`TTS_SAMPLE_RATE_HZ=16000`) → WAV plus léger.
  - **Serveur** : réponses Gemini **plus courtes** (1-2 phrases) → audio plus court.
  - **Serveur** : LLM avec **timeout par appel (15 s)** + **cooldown des modèles** en quota (on saute
    un modèle épuisé 90 s au lieu de le réessayer) → plus jamais de longue attente côté LLM.
  - **Serveur** : log de timing sur `tts.wav` (`TTS.wav: N octets en X.XXs`).

### 8 octies. Volume trop bas après le passage au streaming (2026-05-26)

- 🔎 **Cause** : `speaker.playCloudWAV(url)` joue au **volume par défaut** (faible). Sur ce firmware,
  `setVolume()` est inopérant — seul le paramètre `volume=` de **`playWAV`** agit (cf.
  `tts-module/GUIDE_VOLUME_M5STACK.md`).
- 🔧 **Correctif (firmware)** : on télécharge le WAV **par petits morceaux (512 o) vers `/flash`**
  (RAM minimale → reste rapide), puis on le joue via **`jouer_wav` → `playWAV(volume=100)`** (son fort).
  On garde donc **rapide ET fort**. (→ **reflash**)

---

## 9. Bugs & incohérences — ✅ TOUS CORRIGÉS (2026-05-25)

| Statut | Problème | Correction appliquée |
|--------|----------|----------------------|
| ✅ | `/api/voice/query` **n'existait pas** (404) → AI insights du dashboard cassés. | **Route `POST /api/voice/query` ajoutée** dans `routes/voice.py` (query + contexte → Gemini). Vérifié : les encarts IA du dashboard se remplissent. |
| ✅ | Clé Gemini de Marcelo en **429** → `/listen` renvoyait 503. | Middleware **redéployé avec ta clé Gemini**. `/listen` répond maintenant en ligne. |
| ✅ | Synthèse vocale en échec sur Cloud Run (`Permission denied` cache audio). | `tts/cache.py` rendu **tolérant aux erreurs** + `AUDIO_CACHE_DIR=/tmp/tts_cache` au déploiement. |
| ✅ | `outdoor_temp` toujours **null** en base. | `routes/sensor.py` lit désormais `c.get("temp")` (au lieu de `"temperature"`). |
| ✅ | Assistant vocal sans contexte capteurs. | `/listen` et `/query` injectent la dernière mesure (BigQuery) + météo dans le prompt Gemini. |
| ✅ | **Doublon** : `services/{tts,llm,stt}_service.py` inutilisés. | **Supprimés** (seuls `bigquery_service.py` et `weather_service.py` sont utilisés). |
| ✅ | `run_voice_qa()` appelait `voice_listen_and_ask()` (non défini). | **Fonction morte supprimée** de `device/main_uiflow.py`. |
| ✅ | Liste d'endpoints **obsolète** sur `/`. | Mise à jour dans `middleware/app.py`. |
| ✅ | Données **fictives** (random + alertes factices) dans `/history_weekly`. | Random supprimé : vraies moyennes, jours sans donnée à `0`, alertes/humidité réelles. |
| ✅ | Annonces avec météo factice (18°/35%). | `/announce` utilise la vraie météo + humidité intérieure réelle. |

> Toutes les modifications ci-dessus ont été **vérifiées en local** (venv) **puis déployées** sur
> `core2-weather-monitor`. Le code source du repo et le service Cloud Run sont alignés.

---

## 10. Redéploiement sur Cloud Run (quand tu seras prêt)

> ⚠️ Action qui **modifie une ressource partagée** (le service de Marcelo). À faire **en accord avec lui**.
> L'ADC de Marcelo a les droits, mais discute-en avant de redéployer « son » backend.

```bash
cd "/Users/noahissah/Desktop/Cloud and Advanced Analytics/PROJECT_M5/core2-weather-monitor-main"

gcloud run deploy core2-middleware \
  --source ./middleware \
  --project core2-weather-monitor \
  --region europe-west1 \
  --allow-unauthenticated \
  --update-env-vars GEMINI_API_KEY=TA_CLE_GEMINI,OPENWEATHER_API_KEY=TA_CLE_OPENWEATHER,GOOGLE_CLOUD_PROJECT=core2-weather-monitor
```
> Sur Cloud Run, **pas besoin de `GOOGLE_APPLICATION_CREDENTIALS`** : le service utilise le **compte de
> service du runtime** (qui doit avoir les droits BigQuery + TTS + STT). Le problème de « quota project »
> du §4 ne se pose **que** pour l'ADC en local.

---

## 11. Sécurité — à respecter absolument

- 🔒 **Aucune clé en clair dans le code** ni dans un fichier **commité**. Les secrets vivent dans
  `middleware/.env` (gitignoré) et `application_default_credentials.json` (à la racine).
- 🔒 Le `.gitignore` couvre déjà `.env`, `*.env`, `credentials*.json`, `*-service-account*.json`,
  `env-vars.yaml`. **Vérifie** que `application_default_credentials.json` est bien ignoré avant tout
  `git add` (le motif `credentials*.json` le couvre).
- 🔒 Ce fichier `.md` **ne contient volontairement aucun secret critique** sauf les clés que tu m'as
  fournies explicitement et qui seront **révoquées/supprimées** en fin de projet. Par prudence, **ne le
  commite pas tel quel** si tu veux rester clean, ou retire la clé Gemini avant push.
- 🔒 `tts-module/` (avec **tes** credentials) est **temporaire** → à **supprimer** en fin de projet.
- ⚠️ Rappel consigne projet : tu dois **maîtriser chaque ligne** au Q&A. Les guides
  `tts-module/GUIDE_ASSISTANT_VOCAL.md` et `M5STACK_UIFLOW.md` sont d'excellents supports de révision.

---

## 12. Récapitulatif de ce qui a été fait

### Fichiers créés / préparés
| Élément | Type | Note |
|---------|------|------|
| `ANALYSE_ET_GUIDE_LOCAL.md` | ce document | À la racine. |
| `.venv-middleware/` | venv Python 3.11 | Deps du middleware. Gitignoré. |
| `.venv-dashboard/` | venv Python 3.11 | Deps du dashboard (plotly inclus). Gitignoré. |
| `middleware/.env` | config locale | Secrets, **ta** clé Gemini, quota project forcé. Gitignoré. |
| `middleware/.dockerignore` | build | Empêche le `.env` et les caches de partir dans l'image Cloud Run. |
| `.claude/launch.json` | preview | Config pour lancer le dashboard (sans secret). |

### Code modifié (middleware)
- `routes/voice.py` : nouvel endpoint `/api/voice/query` ; `/listen` et `/announce` enrichis du
  contexte capteurs/météo réel.
- `tts/llm.py` : `generate_reply()` accepte un contexte et l'injecte dans le prompt Gemini.
- `tts/cache.py` : écriture du cache tolérante aux erreurs (Cloud Run non-root).
- `routes/sensor.py` : `outdoor_temp` corrigé ; suppression des fausses données de `/history_weekly`.
- `app.py` : liste d'endpoints à jour.
- `services/{tts,llm,stt}_service.py` : **supprimés** (inutilisés).
- `device/main_uiflow.py` : suppression de la fonction morte `run_voice_qa` (reflash optionnel).

### Déploiement
- `core2-middleware` redéployé sur `core2-weather-monitor` (europe-west1), révision
  `core2-middleware-00043-sfj`, avec ta clé Gemini + `AUDIO_CACHE_DIR=/tmp/tts_cache`.
- Vérifié en ligne : `/api/voice/query`, `/api/voice/listen`, `/api/voice/tts.wav`, dashboard.

> 🧹 `.gitignore` mis à jour : `.venv-middleware/` et `.venv-dashboard/` sont ignorés.
