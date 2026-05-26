"""
tts/announcements.py
====================
Rôle du fichier :
Contient la "logique métier" des annonces vocales.

Deux responsabilités :
1. Composer le bon TEXTE français selon le type d'événement (event_type).
2. Appliquer un "rate-limiting" : refuser de rejouer la MÊME annonce si
   elle a déjà été émise il y a moins d'une heure (pour ne pas spammer
   l'utilisateur ni l'API Google).

À propos des données météo :
Pour l'instant on utilise des données FICTIVES (placeholder).
Mon coéquipier branchera OpenWeatherMap plus tard, en remplaçant
simplement le contenu de FAKE_WEATHER_DATA (ou en passant ses propres
données via le paramètre `data`).
"""

import time

import config


# Données météo / capteurs FICTIVES (placeholder).
# Plus tard : remplacé par un vrai appel OpenWeatherMap + capteurs M5Stack.
FAKE_WEATHER_DATA = {
    "temp": 18,        # température extérieure en °C
    "rain": True,      # de la pluie est-elle prévue aujourd'hui ?
    "humidity": 35,    # humidité intérieure en %
}


# Mémoire du rate-limiting.
# Pour chaque event_type, on stocke le timestamp (en secondes) de sa
# DERNIÈRE émission. C'est un simple dictionnaire en mémoire, comme demandé
# dans la spec (pas de base de données).
# Attention : ce dictionnaire est remis à zéro si on redémarre le serveur.
_last_announced = {}


def build_announcement_text(event_type, data=None):
    """Construit le texte français correspondant à un type d'événement.

    Paramètres :
        event_type (str) : le type d'annonce. Valeurs supportées :
            - "morning_briefing"  : résumé matinal (+ parapluie si pluie).
            - "humidity_alert"    : alerte humidité intérieure trop basse.
            - "air_quality_alert" : alerte qualité d'air mauvaise.
            - "welcome"           : message de bienvenue (détection présence).
            - "weather_update"    : annonce de la météo actuelle.
        data (dict) : données météo/capteurs. Si None, on utilise les
                      données fictives FAKE_WEATHER_DATA.

    Retour :
        str : le texte à synthétiser.

    Lève :
        ValueError : si l'event_type n'est pas reconnu.
    """
    # Si l'appelant ne fournit pas de données, on prend les données fictives.
    if data is None:
        data = FAKE_WEATHER_DATA

    # --- Morning briefing -----------------------------------------------------
    if event_type == "morning_briefing":
        texte = (
            "Good morning! Here is your daily briefing. "
            "The outdoor temperature is {temp} degrees."
        ).format(temp=data.get("temp", "unknown"))

        # Umbrella reminder ONLY if rain is predicted.
        if data.get("rain"):
            texte += (
                " Rain is expected today, "
                "don't forget to take an umbrella."
            )
        return texte

    # --- Indoor humidity alert ----------------------------------------
    if event_type == "humidity_alert":
        humidite = data.get("humidity", "unknown")
        return (
            "Warning, indoor humidity is low, "
            "at only {h} percent. "
            "Consider ventilating or using a humidifier."
        ).format(h=humidite)

    # --- Air quality alert -------------------------------------------
    if event_type == "air_quality_alert":
        return (
            "Warning, indoor air quality is poor. "
            "It is recommended to open the windows to ventilate the room."
        )

    # --- Welcome message ----------------------------------------------
    if event_type == "welcome":
        return "Welcome home! Nice to see you again."

    # --- Current weather ----------------------------------------------------
    if event_type == "weather_update":
        return (
            "Current weather: it is {temp} degrees outside."
        ).format(temp=data.get("temp", "unknown"))

    # Si on arrive ici, c'est que l'event_type n'est pas dans la liste.
    raise ValueError("Type d'événement inconnu : " + str(event_type))


def is_rate_limited(event_type):
    """Indique si l'event_type a été émis trop récemment (< 1 heure).

    Paramètre :
        event_type (str) : le type d'annonce à vérifier.

    Retour :
        True  -> il faut REFUSER l'annonce (émise trop récemment).
        False -> on peut émettre l'annonce.
    """
    derniere_emission = _last_announced.get(event_type)

    # Jamais émis auparavant -> jamais rate-limité.
    if derniere_emission is None:
        return False

    # Combien de secondes se sont écoulées depuis la dernière émission ?
    secondes_ecoulees = time.time() - derniere_emission

    # Si c'est inférieur au seuil (1 heure par défaut), on bloque.
    return secondes_ecoulees < config.RATE_LIMIT_SECONDS


def mark_announced(event_type):
    """Mémorise que l'event_type vient d'être émis (timestamp = maintenant).

    À appeler APRÈS avoir émis l'annonce avec succès.
    """
    _last_announced[event_type] = time.time()
