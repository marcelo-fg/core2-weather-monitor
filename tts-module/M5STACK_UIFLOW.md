# M5Stack Core2 — Guide UIFlow (MicroPython)

Ce document explique comment installer la partie **device** du projet sur un
**M5Stack Core2**, via **UIFlow 1.x** ([flow.m5stack.com](https://flow.m5stack.com)).

> **Le code complet du device est dans le fichier [`main.py`](main.py)** à la
> racine du projet. Ce guide explique seulement comment le mettre sur le device
> et comment il fonctionne — on ne recopie pas le code ici pour éviter les
> doublons et les versions qui divergent.

Le device dialogue avec l'API Flask déployée sur Cloud Run :

```
https://tts-module-847024687713.europe-west9.run.app
```

> ⚠️ **UIFlow 1.x** (pas 2.0). C'est important : l'API 1.x utilise
> `from m5stack import *`, `lcd`, `btnA/btnB/btnC`, `speaker`, l'objet `MIC`…
> Le code de `main.py` est écrit pour cette version (si `import M5` plante avec
> « no module named M5 », c'est bien que tu es en 1.x — c'est le cas attendu).

---

## 1. Ce que fait le device

| Bouton (zone tactile en bas de l'écran) | Action |
| --- | --- |
| **A** — appui court | Annonce de **bienvenue** : `POST /announce` (`welcome`) puis joue le WAV |
| **A** — appui long (≥ 2 s) | Affiche le **journal de débogage** (`/flash/debug.log`) à l'écran |
| **B** | Annonce **météo** : `POST /announce` (`weather_update`) puis joue le WAV |
| **C** | **Conversation** : enregistre la voix, l'envoie à `/listen`, joue la réponse |

En plus, un **capteur de présence PIR** déclenche automatiquement l'annonce de
bienvenue (**au maximum 1 fois par heure**).

Flux du **bouton C** (le plus complet) :

```
Voix (micro Core2)  ──►  POST /listen  ──►  [Google Speech-to-Text]
                                              ──►  [Google Gemini 2.5 Flash]
                                              ──►  [Google Text-to-Speech]
Haut-parleur Core2  ◄──  réponse WAV   ◄──────────────────────────────┘
```

---

## 2. Matériel nécessaire

- 1× **M5Stack Core2** (micro, haut-parleur, écran tactile, zones-boutons A/B/C intégrés).
- 1× **M5Stack PIR Unit** (capteur de présence) branché sur le **Port B** (Grove).
- Un réseau **WiFi 2.4 GHz** (le Core2 ne gère pas le 5 GHz).
- Un câble USB-C pour flasher le device.

---

## 3. Préparer UIFlow (une seule fois)

1. **Flasher le firmware UIFlow** avec **M5Burner** :
   - Télécharge M5Burner : <https://docs.m5stack.com/en/download>
   - Choisis un firmware **UIFlow (1.x)** pour **Core2**, branche en USB, clique **Burn**.
   - Pendant le burn, configure ton **WiFi** et note l'**API KEY** affichée au démarrage.
2. **Ouvrir l'éditeur** : <https://flow.m5stack.com>.
3. **Connecter le device** : colle l'**API KEY**, sélectionne **Core2**. Le voyant doit passer au vert.

---

## 4. Installer le code sur le device

UIFlow propose deux vues : **Blockly** (blocs) et **Python**. On utilise Python.

1. En haut à droite de l'éditeur, bascule en mode **Python** (icône `</>`).
2. **Efface** le code par défaut, puis **colle l'intégralité du fichier
   [`main.py`](main.py)** (ouvre-le, sélectionne tout, copie-colle).
3. Clique **Run (▶)** pour tester en mémoire, puis **Download / Run & Save**
   pour l'écrire en flash : il se lancera alors tout seul à chaque démarrage.

> `main.py` est garanti **100 % ASCII** (aucun accent, aucun guillemet
> courbe) pour que le copier-coller dans UIFlow ne casse jamais.

---

## 5. Configuration à adapter (en haut de `main.py`)

```python
WIFI_SSID = "..."        # nom de ton reseau WiFi 2.4 GHz
WIFI_PASSWORD = "..."    # mot de passe
PIR_PIN = 36             # broche du capteur PIR (Port B du Core2)
API_BASE = "https://tts-module-847024687713.europe-west9.run.app"
```

L'URL de l'API est déjà renseignée. Seuls le WiFi (et la broche PIR si tu la
changes) sont à adapter.

---

## 6. Tester + déboguer SANS câble USB

1. **A (court)** → tu dois entendre le message de bienvenue.
2. **B** → message météo.
3. **C** → « Je t'écoute… », parle **distinctement et près du micro**, puis écoute la réponse.
4. **PIR** → passe la main devant : bienvenue automatique (puis silence 1 h).

> **Astuce clé** : tous les diagnostics sont écrits dans `/flash/debug.log`.
> Un **appui long sur A (≥ 2 s)** affiche ce journal directement à l'écran —
> pratique pour lire les erreurs sans brancher l'ordinateur.

---

## 7. Notes techniques (à connaître / défendre à l'oral)

> 📘 Deux points nous ont posé beaucoup de difficultés — chacun a son guide
> dédié à la racine :
> - **[`GUIDE_VOLUME_M5STACK.md`](GUIDE_VOLUME_M5STACK.md)** : régler le volume.
> - **[`GUIDE_ASSISTANT_VOCAL.md`](GUIDE_ASSISTANT_VOCAL.md)** : le bouton C
>   (micro → Speech-to-Text → Gemini → voix), avec tous les pièges.

1. **Micro et haut-parleur partagent le bus I2S** : on coupe le speaker
   (`speaker.end()`) avant d'enregistrer.
2. **Micro = `MIC.record2file(duree_s, fichier)`** : sur ce firmware 1.x,
   l'objet `MIC` n'expose que `record2file`, qui écrit directement un fichier
   WAV (signature confirmée sur le device : durée en secondes, puis chemin).
3. **Haut-parleur = `speaker.playWAV(chemin, volume=…)`** : le volume se passe
   en paramètre (le `setVolume()` classique ne marche pas sur ce firmware).
4. **Fréquence audio** : peu importe la fréquence exacte du micro — le serveur
   la **lit dans l'en-tête du fichier WAV** reçu. Rien à synchroniser.
5. **Broche PIR** : le **Port B** du Core2 = **GPIO 36**. Change `PIR_PIN` si besoin.
6. **WiFi 2.4 GHz uniquement** (le Core2 ne se connecte pas au 5 GHz).

---

## 8. Côté serveur (rappel)

Le device appelle l'API Flask (dossier racine du projet). Pour `/listen`, le
serveur doit avoir **Speech-to-Text activé** et une **clé Gemini** configurée :

```bash
gcloud services enable speech.googleapis.com --project weather-tts-noah
```

> Le LLM est **Google Gemini (`gemini-2.5-flash`)**, authentifié par une **clé
> API** (`GEMINI_API_KEY`, gratuite via [AI Studio](https://aistudio.google.com/apikey)).
> Détails d'installation, des endpoints et du déploiement : voir le **[`README.md`](README.md)**.
