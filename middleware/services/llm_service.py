"""
Gemini LLM service — generates contextual answers about weather/indoor data.
Uses google-generativeai (Gemini 1.5 Flash).
"""
import logging
import google.generativeai as genai
from config import GEMINI_API_KEY

logger = logging.getLogger(__name__)

_model = None

SYSTEM_PROMPT = """Tu es une intelligence artificielle sophistiquée nommée "Orion".
Ta mission est de surveiller les conditions de la station (la maison) et de faire un rapport oral au Commandant.
Tu as accès aux données des capteurs en temps réel et à la météo extérieure.
Analyse le contexte et fais un rapport très précis, détaillé et charismatique.
RÈGLES CRITIQUES:
- Parle TOUJOURS en français.
- Présente-toi ("Ici Orion...") et rappelle brièvement ta mission.
- Donne les informations de façon détaillée (températures, humidité, qualité de l'air).
- Finis par un commentaire ou un conseil professionnel pour le Commandant."""


def _get_model():
    global _model
    if _model is None:
        genai.configure(api_key=GEMINI_API_KEY)
        _model = genai.GenerativeModel(
            model_name="gemini-flash-latest",
            system_instruction=SYSTEM_PROMPT,
        )
    return _model


def _build_context(context: dict) -> str:
    """Format sensor/weather context as a readable string for the prompt."""
    lines = ["Current sensor readings:"]

    temp = context.get("temperature")
    humi = context.get("humidity")
    tvoc = context.get("tvoc")
    eco2 = context.get("eco2")
    aq   = context.get("aq_label", "Unknown")

    if temp is not None:
        lines.append(f"  - Indoor temperature: {temp:.1f}°C")
    if humi is not None:
        lines.append(f"  - Indoor humidity: {humi:.0f}%")
    if tvoc is not None:
        lines.append(f"  - TVOC (air quality): {tvoc} ppb")
    if eco2 is not None:
        lines.append(f"  - eCO2: {eco2} ppm")
    lines.append(f"  - Air quality: {aq}")

    weather = context.get("weather", {}).get("current", {})
    if weather:
        lines.append("\nCurrent outdoor weather:")
        if weather.get("temp") is not None:
            lines.append(f"  - Outdoor temperature: {weather['temp']:.1f}°C")
        if weather.get("description"):
            lines.append(f"  - Conditions: {weather['description']}")
        if weather.get("humidity") is not None:
            lines.append(f"  - Outdoor humidity: {weather['humidity']}%")
        if weather.get("wind_speed") is not None:
            lines.append(f"  - Wind speed: {weather['wind_speed']} m/s")

    time_info = context.get("time", {})
    if time_info:
        lines.append(f"\nCurrent time: {time_info.get('h', '?'):02d}:{time_info.get('m', '?'):02d} "
                     f"on {time_info.get('day', '?')} {time_info.get('dd', '?'):02d}/"
                     f"{time_info.get('mo', '?'):02d}/{time_info.get('yy', '?')}")

    # Include recent history summary if available
    history = context.get("history", [])
    if history:
        lines.append(f"\nHistory: {len(history)} readings available for the last 24h.")

    return "\n".join(lines)


_MODEL_NAMES = [
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-lite-latest",
    "gemini-flash-latest"
]

def answer(query: str, context: dict) -> str | None:
    """
    Generate a natural language answer to a question about the current sensor data.
    Returns None on error.
    """
    if not query:
        return None

    genai.configure(api_key=GEMINI_API_KEY)
    ctx_str = _build_context(context)
    full_prompt = f"{ctx_str}\n\nUser question: {query}"

    for model_name in _MODEL_NAMES:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=SYSTEM_PROMPT,
            )
            response = model.generate_content(full_prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini error with {model_name}: {e}")
            continue

    return None


def generate_announcement(context: dict) -> str:
    """
    Generate a proactive announcement when motion is detected.
    """
    genai.configure(api_key=GEMINI_API_KEY)
    ctx_str = _build_context(context)

    prompt = (
        f"{ctx_str}\n\n"
        "Génère ton rapport complet au Commandant selon les règles établies. "
        "Détaille bien toutes les mesures (température, humidité, qualité de l'air) et "
        "ajoute ton analyse ou conseil à la fin."
    )

    for model_name in _MODEL_NAMES:
        try:
            model = genai.GenerativeModel(
                model_name=model_name,
                system_instruction=SYSTEM_PROMPT,
            )
            response = model.generate_content(prompt)
            return response.text.strip()
        except Exception as e:
            logger.error(f"Gemini announcement error with {model_name}: {e}")
            continue

    return "Welcome home! I'm having trouble retrieving the current conditions right now."
