# =========================================================================
# main.py - M5Stack Core2 (UIFlow 1.x) - Moniteur meteo intelligent
# =========================================================================
# Dialogue avec mon API Flask (TTS / STT + LLM Gemini) sur Google Cloud Run.
# MicroPython - commentaires en francais SANS accents (copier-coller sur).
#
# Boutons :  A court = bienvenue   |   A long (>2 s) = afficher le journal
#            B = meteo             |   C = conversation (micro -> /listen)
# Tous les diagnostics sont ecrits dans /flash/debug.log (lisible via A long).
# =========================================================================

from m5stack import *      # lcd (ecran), btnA/btnB/btnC (touches), speaker
from uiflow import *       # wait, wait_ms
import network             # WiFi
import urequests           # HTTP
import ujson               # JSON
import time                # pauses / chrono
from machine import Pin    # broche du capteur PIR

# --- Configuration -------------------------------------------------------
WIFI_SSID = "Sunrise_Wi-Fi_6315482"
WIFI_PASSWORD = "sfk6rtdyTjMv"
API_BASE = "https://tts-module-847024687713.europe-west9.run.app"
PIR_PIN = 36                       # capteur de presence (Port B = GPIO 36)
DUREE_ENREGISTREMENT_S = 5         # duree d'enregistrement de la voix (bouton C)
DELAI_PRESENCE_S = 3600            # 1 bienvenue auto max par heure
FICHIER_VOIX = "/flash/voix.wav"        # voix enregistree
FICHIER_REPONSE = "/flash/reponse.wav"  # WAV recu de l'API (a jouer)
FICHIER_LOG = "/flash/debug.log"        # journal (lisible via appui long sur A)
JSON_HEADERS = {"Content-Type": "application/json"}

# =========================================================================
# JOURNAL + AFFICHAGE
# =========================================================================

def log(message):
    """Affiche dans la console ET ajoute la ligne a /flash/debug.log."""
    print(message)
    try:
        with open(FICHIER_LOG, "a") as f:
            f.write(message + "\n")
    except:
        pass


def afficher(message, couleur=0xFFFFFF):
    """Affiche un message court au centre de l'ecran (gere les retours ligne)."""
    lcd.clear()
    lcd.font(lcd.FONT_DejaVu18)
    y = 90
    for ligne in message.split("\n"):
        lcd.print(ligne, 10, y, couleur)
        y = y + 26


def _police_petite():
    """Selectionne la plus petite police disponible.

    Renvoie (largeur, hauteur) = nb de caracteres par ligne et hauteur de
    ligne en pixels, pour ne JAMAIS deborder de l'ecran (320 x 240).
    """
    for nom, largeur, hauteur in (("FONT_DefaultSmall", 44, 13),
                                  ("FONT_Default", 35, 15),
                                  ("FONT_DejaVu18", 22, 22)):
        police = getattr(lcd, nom, None)
        if police is not None:
            try:
                lcd.font(police)
                return largeur, hauteur
            except:
                pass
    return 22, 22


def _couper(texte, largeur):
    """Coupe un texte (avec retours ligne) en lignes de 'largeur' caracteres max."""
    lignes = []
    for brute in str(texte).split("\n"):
        if brute == "":
            lignes.append("")
        else:
            for i in range(0, len(brute), largeur):
                lignes.append(brute[i:i + largeur])
    return lignes


def afficher_erreur(titre, detail):
    """Affiche une erreur a l'ecran SANS deborder (titre rouge), 8 secondes."""
    log("[ERREUR] " + str(titre) + " | " + str(detail))
    lcd.clear()
    largeur, hauteur = _police_petite()
    lcd.print(str(titre)[:largeur], 4, 2, 0xFF0000)     # titre en rouge
    y = 2 + hauteur
    for ligne in _couper(detail, largeur):
        if y > 240 - hauteur:                           # on s'arrete avant le bas de l'ecran
            break
        lcd.print(ligne, 4, y, 0xFFFFFF)
        y = y + hauteur
    wait(8)


def afficher_log():
    """Affiche les dernieres lignes de /flash/debug.log, sans deborder (appui long A)."""
    try:
        with open(FICHIER_LOG) as f:
            contenu = f.read()
    except Exception as e:
        afficher_erreur("LOG introuvable", e)
        return
    lcd.clear()
    largeur, hauteur = _police_petite()
    nb_max = 240 // hauteur                              # nb de lignes qui tiennent a l'ecran
    for i, ligne in enumerate(_couper(contenu, largeur)[-nb_max:]):
        lcd.print(ligne, 4, 2 + i * hauteur, 0xFFFFFF)
    wait(12)


# =========================================================================
# WIFI
# =========================================================================

def connecter_wifi():
    """Connecte au WiFi (timeout ~10 s). Renvoie True si OK, False sinon."""
    afficher("Connexion WiFi...")
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        wlan.connect(WIFI_SSID, WIFI_PASSWORD)
        essais = 0
        while not wlan.isconnected() and essais < 20:
            time.sleep(0.5)
            essais = essais + 1
    if wlan.isconnected():
        log("[WIFI] OK " + str(wlan.ifconfig()))
        afficher("WiFi OK !", 0x00FF00)
        time.sleep(1)
        return True
    log("[WIFI] echec de connexion")
    return False


# =========================================================================
# AUDIO : ampli/volume, lecture WAV, ecriture WAV
# =========================================================================

def preparer_audio():
    """Active l'ampli du speaker (via l'objet 'power' si dispo) et met le volume au max."""
    p = globals().get("power")                 # objet d'alimentation (AXP192) du Core2
    if p is not None:
        for nom in ("setSpkEnable", "setSpeakerEnable"):
            try:
                getattr(p, nom)(True)          # active l'amplificateur audio
                break
            except:
                pass
    for v in (11, 100, 10, 8):                 # echelles de volume selon firmware
        try:
            speaker.setVolume(v)
            break
        except:
            pass
    try:
        speaker.setVolumePercentage(100)
    except:
        pass


def jouer_wav(chemin):
    """Joue un fichier WAV ; le volume est passe DIRECTEMENT dans playWAV."""
    time.sleep(0.5)                            # liberer le bus I2S apres le micro
    try:
        speaker.begin()                        # re-init du HP si la methode existe
    except:
        pass
    preparer_audio()
    for volume in (100, 11, 10):               # echelles de volume connues
        for nom in ("playWAV", "playWav"):     # orthographe selon firmware
            methode = getattr(speaker, nom, None)
            if methode is None:
                continue
            try:
                methode(chemin, volume=volume)
                afficher("Son OK", 0x00FF00)
                return
            except Exception as e:
                log("[AUDIO] " + nom + " vol=" + str(volume) + " echec: " + str(e))
    afficher_erreur("SON ECHEC", "playWAV/playWav KO - voir log (A long)")


# =========================================================================
# MICRO : objet MIC de UIFlow 1.x -> methode record2file (ecrit un WAV)
# =========================================================================

def enregistrer_voix(chemin):
    """Enregistre la voix dans un fichier WAV via mic.record2file.

    Sur ce firmware (UIFlow 1.x, Core2), l'objet MIC ecrit directement le WAV :
        record2file(duree_en_secondes, chemin_du_fichier)
    (signature confirmee sur le device). L'appel est BLOQUANT : au retour, le
    fichier WAV est complet. La frequence est choisie par le firmware ; le
    serveur la lira dans l'en-tete du WAV.
    """
    mic = globals().get("Mic") or globals().get("mic")
    if mic is None:
        import mic                             # leve ImportError si le micro est absent
    try:
        speaker.end()                          # liberer le bus I2S (partage avec le micro)
    except:
        pass
    mic.record2file(DUREE_ENREGISTREMENT_S, chemin)   # (duree_s, fichier)
    log("[MIC] enregistrement OK -> " + chemin)


# =========================================================================
# RESEAU : POST puis lecture du WAV recu
# =========================================================================

def envoyer(url, data, etiquette, headers=JSON_HEADERS):
    """POST 'data' vers 'url'. Si 200 : sauvegarde + joue le WAV.

    Renvoie (status, apercu_contenu), ou (None, None) si erreur reseau.
    """
    try:
        r = urequests.post(url, data=data, headers=headers)
    except Exception as e:
        afficher_erreur(etiquette + " reseau", e)
        return None, None
    try:
        code = r.status_code
        apercu = r.content[:120]
        log("[" + etiquette + "] status=" + str(code) + " taille=" + str(len(r.content)))
        if code == 200:
            with open(FICHIER_REPONSE, "wb") as f:
                f.write(r.content)
            jouer_wav(FICHIER_REPONSE)
        return code, apercu
    finally:
        r.close()


# =========================================================================
# ACTIONS DES BOUTONS
# =========================================================================

def annonce(event_type):
    """Demande une annonce a /announce et la joue.

    On envoie "force": True pour CONTOURNER le rate-limit serveur : un appui
    bouton doit toujours jouer l'annonce demandee (sinon A et B retombaient
    tous les deux sur le meme message generique a cause du code 429).
    """
    afficher("Annonce:\n" + event_type)
    corps = ujson.dumps({"event_type": event_type, "force": True})
    code, apercu = envoyer(API_BASE + "/announce", corps, "ANNONCE")
    if code is not None and code != 200:
        afficher_erreur("ANNONCE " + str(code), apercu)


def mode_conversation():
    """Bouton C : enregistre la voix (-> WAV), l'envoie a /listen, joue la reponse."""
    try:
        afficher("Je t'ecoute...", 0x00AAFF)
        enregistrer_voix(FICHIER_VOIX)         # ecrit directement le fichier WAV
        with open(FICHIER_VOIX, "rb") as f:
            audio = f.read()
        log("[C] WAV=" + str(len(audio)) + " octets")
    except Exception as e:                     # micro indispo / fichier illisible
        afficher_erreur("MIC ECHEC", type(e).__name__ + ": " + str(e))
        return
    afficher("Je reflechis...", 0xFFAA00)
    code, apercu = envoyer(API_BASE + "/listen", audio, "LISTEN",
                           {"Content-Type": "audio/wav"})
    if code is not None and code != 200:
        afficher_erreur("LISTEN " + str(code), apercu)


# =========================================================================
# PRESENCE (PIR) + MENU
# =========================================================================

capteur_pir = Pin(PIR_PIN, Pin.IN)
derniere_bienvenue = -10000

def verifier_presence():
    """Bienvenue auto si le PIR detecte quelqu'un (max 1 fois / heure)."""
    global derniere_bienvenue
    if capteur_pir.value() == 1 and time.time() - derniere_bienvenue > DELAI_PRESENCE_S:
        derniere_bienvenue = time.time()
        annonce("welcome")


def menu():
    """Affiche le menu d'accueil."""
    afficher("Pret !\nA: Bienvenue\nB: Meteo\nC: Parler\n(A long = LOG)")


# =========================================================================
# PROGRAMME PRINCIPAL
# =========================================================================

# Journal vierge a chaque demarrage.
try:
    with open(FICHIER_LOG, "w") as f:
        f.write("=== DEBUG LOG ===\n")
except:
    pass

# Diagnostic dans le journal (lisible via A long) : methodes reellement dispo.
preparer_audio()
log("[DIAG] speaker=" + str(dir(speaker)))
log("[DIAG] power=" + str(dir(globals().get("power"))))
_m = globals().get("Mic") or globals().get("mic")
log("[DIAG] Mic=" + (str(dir(_m)) if _m is not None else "absent"))

if connecter_wifi():
    menu()
    a_depuis = None                            # instant du debut d'appui sur A
    b_prec = False                             # etat precedent de B (detection de front)
    c_prec = False                             # etat precedent de C

    # Boucle principale : on SONDE les 3 boutons de la meme facon (fiable).
    while True:
        # Bouton A : appui court = bienvenue ; appui long (>= 2 s) = journal.
        if btnA.isPressed():
            if a_depuis is None:
                a_depuis = time.time()
        elif a_depuis is not None:
            duree = time.time() - a_depuis
            a_depuis = None
            if duree >= 2:
                afficher_log()
            else:
                annonce("welcome")
            menu()

        # Bouton B : front montant = meteo.
        b = btnB.isPressed()
        if b and not b_prec:
            annonce("weather_update")
            menu()
        b_prec = b

        # Bouton C : front montant = conversation.
        c = btnC.isPressed()
        if c and not c_prec:
            mode_conversation()
            menu()
        c_prec = c

        verifier_presence()
        time.sleep(0.05)
else:
    afficher_erreur("WiFi KO", "Verifie SSID / mot de passe puis redemarre")
