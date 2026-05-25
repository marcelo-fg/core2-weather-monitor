# Guide — L'assistant vocal (bouton C : voix → réponse intelligente)

Ce guide documente **en détail** le mode conversation déclenché par le
**bouton C** du M5Stack, parce que c'est la partie qui nous a donné le plus de
fil à retordre (surtout la connexion à **Gemini**). Il explique chaque étape,
les **erreurs** rencontrées, **pourquoi**, et la **solution** retenue.

> ### TL;DR (les 3 pièges qui nous ont bloqués)
> 1. **Micro** : l'objet `MIC` (UIFlow 1.x) n'a qu'une méthode → `record2file(duree, fichier)`.
> 2. **STT** : il faut lire la **fréquence dans l'en-tête du WAV** (sinon « bad encoding »).
> 3. **Gemini** : utiliser une **clé API** (pas le compte de service) **et** le
>    modèle **`gemini-2.5-flash`** (le `1.5` a été retiré par Google).

---

## 1. Vue d'ensemble du flux

Quand on appuie sur **C** :

```
[M5Stack]                              [Serveur Flask /listen]
 micro -> record2file -> voix.wav  ──►  Google Speech-to-Text  (voix -> texte)
                                          │
                                          ▼
                                        Google Gemini          (texte -> reponse)
                                          │
                                          ▼
 haut-parleur  ◄── reponse.wav  ◄──     Google Text-to-Speech  (reponse -> voix)
```

- Côté **device** : fonction `mode_conversation()` dans `main.py`.
- Côté **serveur** : endpoint `POST /listen` dans `routes/tts_routes.py`,
  qui appelle `tts/stt.py` (STT), `tts/llm.py` (Gemini) et `tts/service.py` (TTS).

---

## 2. Étape 1 — Enregistrer la voix (le piège du micro)

### Ce qu'on a découvert
- En UIFlow 1.x sur Core2, il existe un objet **`MIC`** (majuscule).
- **MAIS** il n'a **pas** les méthodes de la doc UIFlow 2.0 (`begin`, `record`,
  `isRecording`). Erreur typique :
  `AttributeError: 'MIC' object has no attribute 'begin'`.
- En affichant `dir(Mic)`, on a vu **une seule méthode utile : `record2file`**.

### La signature (déduite des erreurs, puis confirmée)
`record2file` prend **2 arguments**, et le **2ᵉ doit être une chaîne** (le nom
de fichier). La forme qui marche :

```python
mic.record2file(5, "/flash/voix.wav")   # (duree_en_secondes, chemin_du_wav)
```

`record2file` écrit **directement un fichier WAV** (avec en-tête) et est
**bloquant** : au retour, le fichier est complet. Code dans `main.py` :

```python
def enregistrer_voix(chemin):
    mic = globals().get("Mic") or globals().get("mic")
    if mic is None:
        import mic
    try:
        speaker.end()                      # liberer l'I2S (partage micro/HP)
    except:
        pass
    mic.record2file(DUREE_ENREGISTREMENT_S, chemin)   # (duree_s, fichier)
```

> ⚠️ La **fréquence** d'enregistrement est choisie par le firmware (on ne la
> contrôle pas). Pas grave : le serveur la lira dans l'en-tête du WAV (étape 3).

---

## 3. Étape 2 — Envoyer l'audio à `/listen`

Le M5Stack envoie le WAV **brut** dans le corps de la requête (le plus simple
avec `urequests`) :

```python
with open("/flash/voix.wav", "rb") as f:
    audio = f.read()
urequests.post(API_BASE + "/listen", data=audio,
               headers={"Content-Type": "audio/wav"})
```

Côté serveur, `/listen` accepte le corps binaire **ou** un envoi `multipart`
(pratique pour tester avec `curl -F`).

---

## 4. Étape 3 — Speech-to-Text (le piège « bad encoding »)

### L'erreur
En laissant Google **deviner** le format (encodage non précisé), on obtenait :
`400 Invalid recognition 'config': bad encoding.`

### La solution
On **lit la fréquence directement dans l'en-tête du WAV** et on la passe
explicitement, en LINEAR16. C'est robuste quelle que soit la fréquence produite
par `record2file`. Dans `tts/stt.py` :

```python
def _frequence_wav(audio_bytes):
    # La frequence est dans le sous-bloc "fmt " du WAV, 12 octets apres son debut.
    i = audio_bytes.find(b"fmt ")
    if i >= 0:
        return int.from_bytes(audio_bytes[i + 12:i + 16], "little")
    return config.STT_SAMPLE_RATE_HZ      # valeur par defaut si en-tete absent

recognition_config = speech.RecognitionConfig(
    encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
    sample_rate_hertz=_frequence_wav(audio_bytes),   # frequence LUE dans l'en-tete
    language_code=config.STT_LANGUAGE_CODE,          # "fr-FR"
)
```

> Si Google ne comprend rien (transcription **vide**), le serveur renvoie quand
> même une réponse vocale polie (« Désolé, je n'ai pas bien compris… »). Dans ce
> cas : **parle plus fort, plus près du micro**.

---

## 5. Étape 4 — Gemini (LE gros morceau)

C'est ici qu'on a perdu le plus de temps. **Deux problèmes distincts.**

### Problème A — Authentification : `403 ACCESS_TOKEN_SCOPE_INSUFFICIENT`
- On voulait au départ utiliser **les mêmes credentials Google** (compte de
  service via `GOOGLE_APPLICATION_CREDENTIALS`) que pour TTS/STT.
- **Ça ne marche pas** avec l'API Gemini « Developer » : elle refuse les jetons
  du compte de service → erreur `403 Request had insufficient authentication
  scopes (ACCESS_TOKEN_SCOPE_INSUFFICIENT)`.

**Solution : utiliser une clé API Gemini (gratuite).**
1. Créer la clé sur **<https://aistudio.google.com/apikey>** (« Create API key »).
2. La mettre dans le `.env` (jamais en dur dans le code) :
   ```
   GEMINI_API_KEY=AIza...
   ```
3. Code dans `tts/llm.py` :
   ```python
   import google.generativeai as genai
   genai.configure(api_key=config.GEMINI_API_KEY)   # <-- cle API, PAS le compte de service
   modele = genai.GenerativeModel(
       model_name=config.GEMINI_MODEL,
       system_instruction=config.LLM_SYSTEM_PROMPT,  # la "personnalite" de l'assistant
   )
   reponse = modele.generate_content(texte_utilisateur)
   print(reponse.text)
   ```

### Problème B — Modèle introuvable : `404 ... is not found`
- Avec `gemini-1.5-flash`, on obtenait :
  `404 models/gemini-1.5-flash is not found for API version v1beta`.
- **Cause** : Google a **retiré** `gemini-1.5-flash`.

**Solution : utiliser `gemini-2.5-flash`** (rapide, gratuit, à jour).
Pour lister les modèles réellement disponibles avec ta clé :
```python
import google.generativeai as genai
genai.configure(api_key="AIza...")
for m in genai.list_models():
    if "generateContent" in m.supported_generation_methods:
        print(m.name)        # ex: models/gemini-2.5-flash, models/gemini-flash-latest...
```
Le modèle est configurable via `GEMINI_MODEL` dans le `.env` (défaut : `gemini-2.5-flash`).

### Problème C — La clé n'arrive pas jusqu'à Cloud Run
- Le fichier `.env` est **ignoré par git** et **n'est PAS envoyé** à Cloud Run.
- Si on déploie sans rien, le serveur n'a pas la clé → erreur 503.

**Solution : passer la clé en variable d'environnement au déploiement :**
```bash
gcloud run deploy tts-module --source . --region europe-west9 \
  --allow-unauthenticated \
  --update-env-vars GEMINI_API_KEY=AIza_ta_cle
```

### Le contexte (personnalité) de l'assistant
Défini dans `config.py` (`LLM_SYSTEM_PROMPT`) — c'est ce qui rend les réponses
courtes et « météo maison » :
> « Tu es un assistant météo intelligent installé dans une maison. Tu as accès
> aux données de température, humidité et qualité de l'air. Réponds en français,
> de façon concise (2-3 phrases max). »

---

## 6. Étape 5 — Lire la réponse (TTS + volume)

Le serveur renvoie un **WAV** ; le M5Stack le sauvegarde sur `/flash` et le joue
avec `jouer_wav()`. Le réglage du **volume** est documenté à part dans
**`GUIDE_VOLUME_M5STACK.md`** (rappel : volume passé dans `playWAV(chemin, volume=...)`).

---

## 7. Tableau de dépannage (symptôme → cause → solution)

| Symptôme (à l'écran ou dans le journal) | Cause | Solution |
| --- | --- | --- |
| `MIC ECHEC ... 'MIC' object has no attribute 'begin'` | API UIFlow 2.0 inexistante en 1.x | Utiliser `record2file(duree, fichier)` |
| `record2file ... can't convert 'int' object to str` | Mauvais ordre/type d'arguments | `record2file(duree_s, "fichier")` (fichier = chaîne, en 2ᵉ) |
| `LISTEN ... 400 bad encoding` | Format audio non précisé au STT | Lire la fréquence dans l'en-tête WAV (`_frequence_wav`) |
| Réponse « je n'ai pas bien compris » | Transcription vide (voix trop faible) | Parler plus fort / plus près du micro |
| `LISTEN 503 ... 403 ACCESS_TOKEN_SCOPE_INSUFFICIENT` | Gemini refuse le compte de service | Utiliser une **clé API** Gemini |
| `LISTEN 503 ... 404 models/gemini-1.5-flash is not found` | Modèle retiré par Google | Passer à **`gemini-2.5-flash`** |
| `LISTEN 503` après déploiement | Clé absente sur Cloud Run | `--update-env-vars GEMINI_API_KEY=...` |
| Réponse reçue mais **pas de son** | Bus I2S non libéré après le micro | `time.sleep(0.5)` + `speaker.begin()` (voir guide volume) |

> Astuce : **appui long sur A (≥ 2 s)** affiche le journal `/flash/debug.log` à
> l'écran (lignes `[MIC]`, `[C]`, `[LISTEN]`, `[ERREUR]`) — indispensable pour
> diagnostiquer sans câble USB.

---

## 8. Où est le code

| Étape | Fichier | Fonction |
| --- | --- | --- |
| Bouton C (orchestration device) | `main.py` | `mode_conversation()` |
| Enregistrement micro | `main.py` | `enregistrer_voix()` |
| Endpoint serveur | `routes/tts_routes.py` | `listen()` |
| Speech-to-Text | `tts/stt.py` | `transcribe_wav()` + `_frequence_wav()` |
| Gemini (LLM) | `tts/llm.py` | `generate_reply()` |
| Text-to-Speech | `tts/service.py` | `synthesize_to_wav()` / `get_audio()` |
| Contexte de l'assistant | `config.py` | `LLM_SYSTEM_PROMPT` |

---

## 9. Tester rapidement la chaîne (sans le M5Stack)

Depuis le dossier du projet, avec le `.env` configuré :
```bash
source .venv/bin/activate
# On genere une voix de test avec /speak, puis on l'envoie a /listen :
python app.py        # dans un 1er terminal
# dans un 2e terminal :
curl -X POST http://localhost:8080/speak -H "Content-Type: application/json" \
  -d '{"text":"Quelle temperature fait-il ?"}' --output /tmp/voix.wav
curl -X POST http://localhost:8080/listen --data-binary @/tmp/voix.wav \
  -H "Content-Type: audio/wav" --output /tmp/reponse.wav && afplay /tmp/reponse.wav
```
Si tu entends une réponse parlée cohérente → **toute la chaîne fonctionne**.
