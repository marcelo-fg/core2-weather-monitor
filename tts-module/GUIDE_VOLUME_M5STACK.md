# Guide — Régler le volume du haut-parleur (M5Stack Core2, UIFlow 1.x)

Ce guide documente **en détail** comment fonctionne le volume du haut-parleur
sur le **M5Stack Core2** en **UIFlow 1.x**, parce que ça nous a posé beaucoup
de difficultés. Il explique ce qui **ne marche pas**, **pourquoi**, et la
solution qui **fonctionne**.

> ### TL;DR (le plus important)
> Sur ce firmware, **`speaker.setVolume(...)` ne fonctionne pas**.
> Le volume doit être passé **directement dans l'appel de lecture** :
> ```python
> speaker.playWAV("/flash/reponse.wav", volume=100)
> ```
> Le code de référence est dans **`main.py`** → fonction **`jouer_wav()`**.

---

## 1. Le symptôme que nous avons eu

- Le son sortait **beaucoup trop faible**, à peine audible.
- On a essayé `speaker.setVolume(8)`, `setVolume(10)`, `speaker.volume(100)`…
  → **aucun effet** sur le volume (ou erreurs silencieuses).
- `from m5stack import axp` → erreur **`can't import name axp`**.

Bref : les méthodes « classiques » de réglage du volume sont **inopérantes**
sur ce firmware pour le Core2.

---

## 2. Pourquoi ça ne marche pas

1. **Firmware UIFlow 1.x.** Les exemples qu'on trouve en ligne
   (`speaker.setVolume`, `Speaker.setVolumePercentage`…) viennent souvent de
   **UIFlow 2.0**, dont l'API est différente. En 1.x, `setVolume` existe parfois
   mais **n'agit pas** sur le volume de lecture des fichiers WAV.

2. **L'ampli audio passe par le PMIC AXP192.** Sur le Core2, le haut-parleur
   est piloté par un circuit de gestion d'énergie (AXP192). Beaucoup de tutos
   disent d'utiliser `axp.setSpkEnable(True)` ou `axp.setLDO...`, mais sur notre
   firmware **`from m5stack import axp` n'existe pas** (d'où l'erreur d'import).

3. **Le volume réel se règle au moment de jouer le son**, pas avant.

---

## 3. LA solution qui fonctionne

On passe le volume **en paramètre** de la méthode de lecture :

```python
speaker.playWAV("/flash/reponse.wav", volume=100)
```

C'est la syntaxe officielle M5Stack (`playWAV(chemin, volume=...)`). Le volume
est appliqué **à cette lecture précise**.

### Subtilité : l'échelle de volume varie selon le firmware
On ne sait pas d'avance si l'échelle va de **0 à 11**, **0 à 100** ou **0 à 10**.
Dans `main.py`, on **essaie plusieurs valeurs** (la première qui passe gagne) et
**deux orthographes** (`playWAV` puis `playWav`), pour être robuste :

```python
for volume in (100, 11, 10):                 # echelles connues
    for nom in ("playWAV", "playWav"):       # orthographe selon firmware
        methode = getattr(speaker, nom, None)
        if methode is None:
            continue
        try:
            methode(chemin, volume=volume)   # <-- LE volume est ici
            return                           # premiere variante qui marche -> on s'arrete
        except Exception as e:
            log("[AUDIO] " + nom + " vol=" + str(volume) + " echec: " + str(e))
```

> Pour mettre le **son au maximum**, garde simplement `100` en premier dans la
> liste (c'est ce qu'on fait). Pour **baisser** le volume, mets une valeur plus
> petite en premier (ex. `(30, 11, 10)`).

---

## 4. Deux pièges annexes (indispensables pour que le son sorte)

### a) Micro et haut-parleur partagent le bus I2S
Sur le Core2, le micro et le HP utilisent le **même bus matériel (I2S)**. Après
un enregistrement (bouton C), le haut-parleur peut rester « bloqué ». Il faut :

```python
time.sleep(0.5)        # laisser le bus se liberer apres le micro
try:
    speaker.begin()    # re-initialiser le haut-parleur (si la methode existe)
except:
    pass
```

C'est exactement ce que fait `jouer_wav()` au début. **Sans ce délai + re-init,
on entendait « rien » après le bouton C** alors que la réponse était bien reçue.

### b) Activer l'ampli via l'objet `power` (au cas où)
`from m5stack import axp` ne marche pas, mais un objet global `power` existe
parfois. On tente d'activer l'ampli sans planter si l'objet est absent :

```python
p = globals().get("power")                   # None si absent -> on ignore
if p is not None:
    for nom in ("setSpkEnable", "setSpeakerEnable"):
        try:
            getattr(p, nom)(True)
            break
        except:
            pass
```

C'est dans la fonction `preparer_audio()` de `main.py`. En pratique, **c'est
surtout `volume=` dans `playWAV` qui fait le travail** ; ce bloc est une sécurité.

---

## 5. Comment diagnostiquer SANS câble USB

Le vrai déblocage est venu du diagnostic. Deux techniques :

1. **Lister les méthodes réellement disponibles** du haut-parleur :
   ```python
   print(dir(speaker))     # affiche playWAV, setVolume, tone, etc.
   ```
   Au démarrage, `main.py` écrit `[DIAG] speaker=[...]` dans le journal.

2. **Lire le journal à l'écran** (le terminal UIFlow nécessite l'USB) :
   - Tout passe par la fonction `log()` → fichier **`/flash/debug.log`**.
   - **Appui long sur le bouton A (≥ 2 s)** affiche ce journal **à l'écran**.
   - C'est comme ça qu'on a vu les lignes `[AUDIO] ... echec:` et compris
     quelle méthode/quel volume fonctionnait.

---

## 6. Récapitulatif (checklist volume)

| À faire | Pourquoi |
| --- | --- |
| Passer `volume=` dans `playWAV(chemin, volume=100)` | `setVolume()` ne marche pas en 1.x |
| Essayer les échelles `100`, `11`, `10` | L'échelle dépend du firmware |
| Essayer `playWAV` **et** `playWav` | L'orthographe dépend du firmware |
| `speaker.end()` avant d'enregistrer (micro) | Micro + HP partagent l'I2S |
| `time.sleep(0.5)` + `speaker.begin()` avant de jouer | Libérer/réinitialiser le bus après le micro |
| Lire `dir(speaker)` + `/flash/debug.log` (appui long A) | Diagnostiquer sans USB |

---

## 7. Où est le code

| Fichier | Fonction | Rôle |
| --- | --- | --- |
| `main.py` | `jouer_wav(chemin)` | Joue un WAV avec le volume en paramètre |
| `main.py` | `preparer_audio()` | Active l'ampli (`power`) avant lecture |
| `main.py` | `log()` / `afficher_log()` | Journal `/flash/debug.log` lisible via appui long A |

Voir aussi **`M5STACK_UIFLOW.md`** pour l'installation du device et
**`GUIDE_ASSISTANT_VOCAL.md`** pour le bouton C (conversation).
