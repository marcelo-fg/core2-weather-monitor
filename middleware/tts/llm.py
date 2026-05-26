"""
Google Gemini client — generates the assistant's natural-language answers.

Highlights:
- Multi-model fallback chain: each Gemini model has its own daily free-tier
  quota, so when one returns 429 we transparently move to the next.
- Per-model cooldown: a 429'd model is skipped for ``_COOLDOWN_S`` seconds to
  avoid wasting time on a model we already know is exhausted.
- Per-call timeout: every Gemini call is capped at ``_CALL_TIMEOUT_S`` seconds
  to prevent the assistant from hanging if Gemini is slow.
"""

import logging
import time

import config

logger = logging.getLogger(__name__)


# Fallback chain — tried in order; each model has its own free-tier quota.
_FALLBACK_MODELS = [
    "gemini-2.0-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-lite",
    "gemini-2.5-flash",
    "gemini-flash-latest",
]

_MODEL_COOLDOWN = {}      # model_name -> timestamp until which to skip the model
_COOLDOWN_S = 90
_CALL_TIMEOUT_S = 15      # max wall time per Gemini call

# Indoor metrics rendered in the history summary block (used by both 24h and 7d).
_HISTORY_METRICS_RENDER = (
    ("temperature", "Indoor temperature", "C"),
    ("humidity",    "Indoor humidity",    "%"),
    ("tvoc",        "VOC (TVOC)",         "ppb"),
    ("eco2",        "eCO2",               "ppm"),
)


def _format_history_block(label, summary):
    """Render a 24h/7d aggregated summary as readable lines for Gemini."""
    if not summary:
        return []
    out = [label + " summary:",
           "- Readings: {}".format(summary.get("readings", 0))]
    for key, name, unit in _HISTORY_METRICS_RENDER:
        if key + "_min" in summary:
            out.append("- {} : min {} {}, max {} {}, avg {} {}".format(
                name,
                summary[key + "_min"], unit,
                summary[key + "_max"], unit,
                summary[key + "_avg"], unit))
    if summary.get("warmest_at"):
        out.append("- Warmest hour today: " + str(summary["warmest_at"]))
    if summary.get("coolest_at"):
        out.append("- Coolest hour today: " + str(summary["coolest_at"]))
    return out


def _format_context(context):
    """Render the live sensor + weather context as a plain-text block for Gemini.

    Returns an empty string if no useful data is available.
    """
    if not context:
        return ""

    lines = []
    t    = context.get("temperature")
    h    = context.get("humidity")
    tvoc = context.get("tvoc")
    eco2 = context.get("eco2")
    aq   = context.get("aq_label")
    if t    is not None: lines.append("- Indoor temperature : {:.1f} C".format(t))
    if h    is not None: lines.append("- Indoor humidity : {:.0f} %".format(h))
    if tvoc is not None: lines.append("- VOC (TVOC) : {} ppb".format(tvoc))
    if eco2 is not None: lines.append("- eCO2 : {} ppm".format(eco2))
    if aq:               lines.append("- Air quality : {}".format(aq))

    ot = context.get("outdoor_temp")
    od = context.get("outdoor_desc")
    oh = context.get("outdoor_humidity")
    ws = context.get("wind_speed")
    if ot is not None: lines.append("- Outdoor temperature : {:.1f} C".format(ot))
    if od:             lines.append("- Outdoor weather : {}".format(od))
    if oh is not None: lines.append("- Outdoor humidity : {} %".format(oh))
    if ws is not None: lines.append("- Wind : {} m/s".format(ws))

    forecast = context.get("forecast")
    if forecast:
        lines.append("Forecast (next few days) :")
        for d in forecast:
            try:
                lines.append("- {} {} : min {:.0f} C, max {:.0f} C, {}, rain {} %".format(
                    d.get("day_name", ""), d.get("date", ""),
                    d.get("temp_min", 0), d.get("temp_max", 0), d.get("condition", ""),
                    int((d.get("rain_prob") or 0) * 100)))
            except Exception:
                pass

    history = context.get("history")
    if history:
        lines.extend(_format_history_block("Last 24 hours", history.get("h24")))
        lines.extend(_format_history_block("Last 7 days",   history.get("h168")))

    if not lines:
        return ""
    return "Current sensor and weather data :\n" + "\n".join(lines)


def generate_reply(user_text, context=None):
    """Return Gemini's English answer to ``user_text``, optionally enriched with ``context``.

    Iterates over the model fallback chain until one succeeds or all fail.
    Models that return 429 (or any other error) are put in cooldown so that
    subsequent requests don't waste time on them.

    Errors are raised and turned into HTTP 503 by the Flask route.
    """
    import google.generativeai as genai
    genai.configure(api_key=config.GEMINI_API_KEY)

    context_block = _format_context(context)
    if context_block:
        prompt = context_block + "\n\nUser question : " + user_text
    else:
        prompt = user_text

    models = [config.GEMINI_MODEL] + [m for m in _FALLBACK_MODELS if m != config.GEMINI_MODEL]
    now = time.time()
    last_error = None
    any_attempt = False

    def _try_model(name):
        model = genai.GenerativeModel(
            model_name=name,
            system_instruction=config.LLM_SYSTEM_PROMPT,
        )
        return model.generate_content(prompt, request_options={"timeout": _CALL_TIMEOUT_S})

    for name in models:
        if _MODEL_COOLDOWN.get(name, 0) > now:
            continue
        any_attempt = True
        try:
            response = _try_model(name)
            logger.info("Gemini OK with model %s", name)
            return response.text.strip()
        except Exception as e:
            last_error = e
            _MODEL_COOLDOWN[name] = time.time() + _COOLDOWN_S
            logger.warning("Gemini model %s unavailable: %s", name, str(e)[:140])
            continue

    # Every model was in cooldown — retry the first one ignoring cooldown so we
    # don't fail outright while quota windows are still open elsewhere.
    if not any_attempt:
        try:
            response = _try_model(models[0])
            return response.text.strip()
        except Exception as e:
            last_error = e

    # Every Gemini model is unavailable (typically: free-tier daily quota
    # exhausted across the entire fallback chain). Instead of returning an
    # error to the caller, synthesize a short reply from the live context so
    # the assistant remains useful.
    logger.warning("All Gemini models unavailable, returning live-data fallback: %s",
                   str(last_error)[:140] if last_error else "no models attempted")
    return _live_data_fallback(context)


def _live_data_fallback(context):
    """Return a short English sentence built directly from live sensor + weather
    data, used when every Gemini model is unavailable."""
    if not context:
        return "The AI service is temporarily unavailable. Please try again later."

    parts = []
    t  = context.get("temperature")
    h  = context.get("humidity")
    aq = context.get("aq_label")
    ot = context.get("outdoor_temp")
    od = context.get("outdoor_desc")

    if t is not None and h is not None:
        parts.append("indoor {:.0f} degrees with {:.0f} percent humidity".format(t, h))
    elif t is not None:
        parts.append("indoor {:.0f} degrees".format(t))
    if aq:
        parts.append("air quality {}".format(str(aq).lower()))
    if ot is not None and od:
        parts.append("outdoor {:.0f} degrees, {}".format(ot, str(od).lower()))
    elif ot is not None:
        parts.append("outdoor {:.0f} degrees".format(ot))

    if not parts:
        return "The AI service is temporarily unavailable. Please try again later."

    return "The AI service is busy. Live data: " + ", ".join(parts) + "."
