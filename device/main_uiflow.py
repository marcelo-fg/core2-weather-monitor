"""
M5Stack Core2 – Indoor/Outdoor Weather Monitor
Single-file version for UIFlow 1.15.2 (online, WiFi mode).

All modules are consolidated here because UIFlow web IDE does not support
uploading custom .py files — everything must be in the main Python editor.

Sections:
  [1] UIFlow imports
  [2] Configuration (edit these!)
  [3] NTP sync
  [4] Sensors (ENV III, TVOC, PIR)
  [5] Display / Screen manager (4 pages)
  [6] Weather (OpenWeatherMap)
  [7] Cloud (BigQuery via middleware)
  [8] Voice (TTS / STT / LLM Q&A)
  [9] WiFi manager (in-app switching for iot-unil)
  [10] Alert logic
  [11] Main loop
"""

# =============================================================================
# [1] UIFlow 1.15.2 required imports
# =============================================================================
from m5stack import *   # lcd, btnA, btnB, btnC, speaker
from m5ui import *      # M5UI components (labels, rects, etc.)
# Note: 'from uiflow import *' is intentionally omitted — it triggers a
# UIFlow cloud API key check that we don't need (we use no EzData/IFTTT).
import urequests
import ujson
import utime
import unit

# =============================================================================
# [2] CONFIGURATION — edit these values before clicking Run
# =============================================================================

# WiFi (used by in-app switcher — UIFlow handles the initial connection)
WIFI_SSID     = "YOUR_WIFI_SSID"  # change to "iot-unil" for in-class demo
WIFI_PASSWORD = "YOUR_WIFI_PASSWORD"
WIFI_TIMEOUT  = 30  # seconds

# Location
LOCATION        = "Lausanne,CH"
TIMEZONE_OFFSET = 2  # CEST = UTC+2

# Middleware (Flask API on Google Cloud Run — deployed!)
MIDDLEWARE_URL = "https://core2-middleware-337108994948.europe-west1.run.app"


# External APIs
OPENWEATHER_API_KEY = "YOUR_OPENWEATHER_API_KEY_HERE"
# Note: Gemini LLM and Google TTS are handled server-side by the middleware.


# Alert thresholds
ALERT_HUMIDITY_MIN = 40    # % — too dry indoors
ALERT_TVOC_MAX     = 500   # ppb
ALERT_ECO2_MAX     = 1000  # ppm

# Timing intervals (seconds)
SENSOR_READ_INTERVAL     = 30
CLOUD_UPLOAD_INTERVAL    = 300    # 5 min
WEATHER_REFRESH_INTERVAL = 1800   # 30 min
ANNOUNCE_COOLDOWN        = 3600   # 1 h — motion TTS cooldown
DISPLAY_TICK             = 5      # screen refresh

# Display dimensions
SCREEN_W = 320
SCREEN_H = 240

# Colour palette (RGB565)
COL_BG     = 0x0d1b2a   # dark navy background
COL_PANEL  = 0x1b2838   # slightly lighter panel
COL_WHITE  = 0xFFFFFF
COL_AMBER  = 0xFF9F00   # temperature
COL_CYAN   = 0x00D4FF   # humidity
COL_GREEN  = 0x00E676   # good air quality
COL_RED    = 0xFF4444   # alerts / bad AQ
COL_YELLOW = 0xFFEB3B   # warnings
COL_BLUE   = 0x64B5F6   # outdoor accent
COL_GRAY   = 0x607D8B   # secondary text
COL_TOPBAR = 0x1565C0   # top navigation bar

# Fonts
FONT_SMALL  = lcd.FONT_DejaVu18
FONT_MEDIUM = lcd.FONT_DejaVu24
FONT_LARGE  = lcd.FONT_DejaVu40
FONT_TINY   = lcd.FONT_DefaultSmall

# =============================================================================
# [3] NTP SYNC
# =============================================================================
_DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def ntp_sync():
    """
    Sync device clock. All methods store UTC in RTC.
    ntp_now() always adds TIMEZONE_OFFSET for local display.
    Shows status on screen during boot.
    """
    from machine import RTC

    lcd.clear(COL_BG)
    lcd.font(FONT_SMALL)
    lcd.print("Syncing clock...", lcd.CENTER, 80, COL_CYAN)

    # ── Already synced? ───────────────────────────────────────────────────────
    if utime.localtime()[0] > 2020:
        lcd.font(FONT_TINY)
        lcd.print("Clock already OK", lcd.CENTER, 110, COL_GREEN)
        utime.sleep(1)
        return True

    # ── Method 1: UIFlow native ntp (targeted import, no API key issue) ───────
    lcd.font(FONT_TINY)
    lcd.print("1) UIFlow NTP...", lcd.CENTER, 110, COL_GRAY)
    try:
        from uiflow import ntp as _ntp
        _ntp.setTime('pool.ntp.org', 0)   # UTC offset = 0; we add it in ntp_now()
        utime.sleep(3)
        if utime.localtime()[0] > 2020:
            lcd.print("UIFlow NTP OK!", lcd.CENTER, 125, COL_GREEN)
            utime.sleep(1)
            return True
        lcd.print("UIFlow NTP: wrong year", lcd.CENTER, 125, COL_YELLOW)
    except Exception as e:
        lcd.print("UIFlow NTP err: " + str(e)[:22], lcd.CENTER, 125, COL_RED)

    # ── Method 2: worldtimeapi.org via HTTP (bypass SSL issues) ───────────
    lcd.print("2) worldtimeapi.org...", lcd.CENTER, 140, COL_GRAY)
    try:
        r    = urequests.get("http://worldtimeapi.org/api/timezone/Europe/Zurich")
        data = ujson.loads(r.content)
        r.close()
        unix_t = data.get("unixtime", 0)
        if unix_t > 946684800:   # sanity: must be after 2000-01-01
            mp_t = unix_t - 946684800       # Unix → MicroPython epoch
            t    = utime.localtime(mp_t)    # gmtime() not in all MicroPython ports
            try:
                import machine
                machine.RTC().datetime((t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))
            except Exception:
                from m5stack import rtc
                rtc.datetime((t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))
            utime.sleep_ms(300)
            if utime.localtime()[0] > 2020:
                lcd.print("worldtimeapi OK!", lcd.CENTER, 155, COL_GREEN)
                utime.sleep(1)
                return True
        lcd.print("worldtimeapi: bad data", lcd.CENTER, 155, COL_YELLOW)
    except Exception as e:
        lcd.print("worldtimeapi: " + str(e)[:24], lcd.CENTER, 155, COL_RED)

    # ── Method 3: ntptime UDP (may be blocked by router) ─────────────────────
    lcd.print("3) NTP UDP pool.ntp.org...", lcd.CENTER, 170, COL_GRAY)
    try:
        import ntptime
        ntptime.settime()   # sets UTC in RTC
        if utime.localtime()[0] > 2020:
            lcd.print("ntptime OK!", lcd.CENTER, 185, COL_GREEN)
            utime.sleep(1)
            return True
    except Exception as e:
        lcd.print("ntptime: " + str(e)[:29], lcd.CENTER, 185, COL_RED)

    # ── Method 4: OpenWeatherMap (bulletproof HTTP fallback) ─────────────────
    lcd.print("4) OpenWeatherMap API...", lcd.CENTER, 200, COL_GRAY)
    try:
        # Re-use the existing HTTP OWM call, grab the 'dt' field
        url = "http://api.openweathermap.org/data/2.5/weather?q={}&appid={}".format(LOCATION, OPENWEATHER_API_KEY)
        r = urequests.get(url)
        data = ujson.loads(r.content)
        r.close()
        unix_t = data.get("dt", 0)
        if unix_t > 1600000000:
            mp_t = unix_t - 946684800
            t = utime.localtime(mp_t)
            try:
                import machine
                machine.RTC().datetime((t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))
            except Exception:
                from m5stack import rtc
                rtc.datetime((t[0], t[1], t[2], t[6], t[3], t[4], t[5], 0))
            utime.sleep_ms(300)
            if utime.localtime()[0] > 2020:
                lcd.print("OWM Time OK!", lcd.CENTER, 215, COL_GREEN)
                utime.sleep(1)
                return True
        lcd.print("OWM Time: bad data", lcd.CENTER, 215, COL_YELLOW)
    except Exception as e:
        lcd.print("OWM err: " + str(e)[:24], lcd.CENTER, 215, COL_RED)

    utime.sleep(2)
    return False


def ntp_now():
    """Return local time dict. RTC stores UTC; we add TIMEZONE_OFFSET here."""
    t = utime.localtime(utime.time() + TIMEZONE_OFFSET * 3600)
    return {
        "yy":  t[0], "mo": t[1], "dd": t[2],
        "h":   t[3], "m":  t[4], "s":  t[5],
        "day": _DAYS[t[6] % 7],   # % 7 safety guard against out-of-range
    }


def is_morning():
    """True between 06:00 and 10:00 local time."""
    return 6 <= ntp_now()["h"] < 10



# =============================================================================
# [4] SENSORS (ENV III + TVOC + PIR)
# =============================================================================

_env3 = None
_tvoc = None
_pir  = None


def sensors_init():
    global _env3, _tvoc, _pir
    for name, sensor_type, port in [
        ("ENV3", unit.ENV3, unit.PORTA),   # Temp + Humidity
        ("TVOC", unit.TVOC, unit.PORTC),   # Air quality → PORT C
        ("PIR",  unit.PIR,  unit.PORTB),   # Motion sensor → PORT B
    ]:
        try:
            s = unit.get(sensor_type, port)
            print("[sensors] {} OK".format(name))
            if name == "ENV3": _env3 = s
            elif name == "TVOC": _tvoc = s
            elif name == "PIR":  _pir  = s
        except Exception as e:
            print("[sensors] {} not found: {}".format(name, e))


def _aq_label(tvoc):
    if tvoc is None:   return "Unknown"
    if tvoc < 220:     return "Good"
    if tvoc < 660:     return "Moderate"
    if tvoc < 2200:    return "Poor"
    return "Hazardous"


def sensors_read():
    """Return dict with temperature, humidity, tvoc, eco2, aq_label."""
    temp, humi, tvoc, eco2 = None, None, None, None
    if _env3:
        try:
            temp = round(_env3.temperature, 1)
            humi = round(_env3.humidity, 1)
        except Exception:
            pass
    if _tvoc:
        try:
            tvoc = _tvoc.TVOC
            eco2 = _tvoc.eCO2
        except Exception:
            pass
    return {
        "temperature": temp,
        "humidity":    humi,
        "tvoc":        tvoc,
        "eco2":        eco2,
        "aq_label":    _aq_label(tvoc),
    }


def motion_detected():
    if not _pir:
        return False
    try:
        return _pir.state == 1
    except Exception:
        return False


# =============================================================================
# [5] DISPLAY / SCREEN MANAGER
# =============================================================================

NUM_PAGES = 4  # 0=Home, 1=Forecast, 2=History, 3=WiFi

_WEATHER_ICONS = {
    "Clear": "* ", "Clouds": "~ ", "Rain": "/ ",
    "Drizzle": "/ ", "Thunderstorm": "! ", "Snow": "+ ",
    "Mist": "_ ", "Fog": "_ ",
}

_screen_alerts = []


def _weather_icon(condition):
    return _WEATHER_ICONS.get(condition, "? ")


def _aq_color(label):
    return {
        "Good": COL_GREEN, "Moderate": COL_YELLOW,
        "Poor": COL_AMBER, "Hazardous": COL_RED,
    }.get(label, COL_GRAY)


def screen_set_alerts(alerts):
    global _screen_alerts
    _screen_alerts = alerts


def screen_show_loading(msg="Loading..."):
    lcd.clear(COL_BG)
    lcd.font(FONT_MEDIUM)
    lcd.print(msg, lcd.CENTER, 100, COL_CYAN)


def screen_show_error(msg):
    lcd.font(FONT_SMALL)
    lcd.print(msg[:40], 5, 220, COL_RED)


def _draw_nav_bar(page):
    lcd.rect(0, 0, 320, 28, COL_TOPBAR, COL_TOPBAR)
    labels = ["Home", "Forecast", "History", "WiFi"]
    x = 4
    for i, label in enumerate(labels):
        col = COL_WHITE if i == page else COL_GRAY
        lcd.font(FONT_TINY)
        lcd.print(label, x, 7, col)
        x += 80
    lcd.font(FONT_TINY)
    lcd.print("[A]<  [B]Voice  >[C]", 60, 228, COL_GRAY)


def _draw_alerts():
    if not _screen_alerts:
        return
    msg = "  |  ".join(_screen_alerts)
    lcd.rect(0, 210, 320, 18, COL_RED, COL_RED)
    lcd.font(FONT_TINY)
    lcd.print(msg[:52], 4, 213, COL_WHITE)


def _page_home(data):
    # Clock strip
    t = data.get("time", {})
    clock_str = "{:02d}:{:02d}".format(t.get("h", 0), t.get("m", 0))
    date_str  = "{} {:02d}/{:02d}/{:04d}".format(
        t.get("day", ""), t.get("dd", 0), t.get("mo", 0), t.get("yy", 0))
    lcd.rect(0, 30, 320, 28, COL_PANEL, COL_PANEL)
    lcd.font(FONT_MEDIUM)
    lcd.print(clock_str, 8, 33, COL_AMBER)
    lcd.font(FONT_SMALL)
    lcd.print(date_str, 100, 38, COL_GRAY)

    # Divider lines
    lcd.line(0, 60, 320, 60, COL_GRAY)
    lcd.line(160, 60, 160, 208, COL_GRAY)

    # Outdoor panel (left)
    weather = data.get("weather", {}).get("current", {})
    icon    = _weather_icon(weather.get("condition", ""))
    lcd.font(FONT_TINY)
    lcd.print("OUTDOOR", 10, 64, COL_BLUE)
    lcd.font(FONT_LARGE)
    out_temp = weather.get("temp")
    lcd.print("{:.0f}C".format(out_temp) if out_temp is not None else "--C",
              10, 82, COL_AMBER)
    lcd.font(FONT_SMALL)
    lcd.print(icon + weather.get("description", "N/A")[:14], 10, 128, COL_WHITE)
    lcd.font(FONT_TINY)
    feels = weather.get("feels_like")
    lcd.print("Feels: {}C".format(int(feels) if feels else "--"), 10, 152, COL_GRAY)
    wind = weather.get("wind_speed")
    lcd.print("Wind: {} m/s".format(wind if wind else "--"), 10, 167, COL_GRAY)

    # Indoor panel (right)
    temp = data.get("temperature")
    humi = data.get("humidity")
    tvoc = data.get("tvoc")
    aq   = data.get("aq_label", "N/A")
    eco2 = data.get("eco2")

    lcd.font(FONT_TINY)
    lcd.print("INDOOR", 170, 64, COL_CYAN)
    lcd.font(FONT_MEDIUM)
    lcd.print("{:.1f}C".format(temp) if temp is not None else "--C",
              170, 82, COL_AMBER)
    lcd.font(FONT_SMALL)
    lcd.print("~  {:.0f}%".format(humi) if humi is not None else "~  --%",
              170, 116, COL_CYAN)
    aq_col = _aq_color(aq)
    lcd.print("Air: " + aq, 170, 142, aq_col)
    lcd.font(FONT_TINY)
    if eco2 is not None:
        lcd.print("CO2: {} ppm".format(eco2), 170, 165, COL_GRAY)
    if tvoc is not None:
        lcd.print("TVOC: {} ppb".format(tvoc), 170, 180, COL_GRAY)

    _draw_alerts()


def _page_forecast(data):
    forecast = data.get("weather", {}).get("forecast", [])
    lcd.font(FONT_SMALL)
    lcd.print("5-Day Forecast", lcd.CENTER, 34, COL_WHITE)
    lcd.line(0, 56, 320, 56, COL_GRAY)

    if not forecast:
        lcd.font(FONT_SMALL)
        lcd.print("No forecast data", lcd.CENTER, 120, COL_GRAY)
        return

    col_w = 320 // min(5, len(forecast))
    for i, day in enumerate(forecast[:5]):
        x = i * col_w + 4
        lcd.font(FONT_TINY)
        lcd.print(day.get("day_name", "?")[:3].upper(), x, 62, COL_GRAY)
        lcd.font(FONT_SMALL)
        lcd.print(_weather_icon(day.get("condition", "")), x, 80, COL_WHITE)
        lcd.font(FONT_TINY)
        t_max = day.get("temp_max")
        lcd.print("{}C".format(int(t_max) if t_max is not None else "--"), x, 108, COL_AMBER)
        t_min = day.get("temp_min")
        lcd.print("{}C".format(int(t_min) if t_min is not None else "--"), x, 124, COL_BLUE)
        rain = day.get("rain_prob", 0)
        if rain:
            lcd.print("{}%".format(int(rain * 100)), x, 140, COL_CYAN)
        if i < 4:
            lcd.line(x + col_w - 2, 56, x + col_w - 2, 160, COL_PANEL)


def _page_history(data):
    history = data.get("history", [])
    lcd.font(FONT_SMALL)
    lcd.print("Indoor History", lcd.CENTER, 34, COL_WHITE)
    lcd.line(0, 56, 320, 56, COL_GRAY)
    lcd.font(FONT_TINY)
    lcd.print("Time      Temp   Hum    AQ", 6, 60, COL_GRAY)
    lcd.line(0, 72, 320, 72, COL_PANEL)

    if not history:
        lcd.font(FONT_SMALL)
        lcd.print("No history data", lcd.CENTER, 120, COL_GRAY)
        return

    y = 76
    for row in history[:8]:
        ts   = row.get("time_label", "--:--")
        temp = row.get("temperature")
        humi = row.get("humidity")
        aq   = row.get("aq_label", "?")[:4]
        aq_col = _aq_color(row.get("aq_label", ""))
        line = "{:<9} {:<7} {:<7}".format(
            ts,
            "{:.1f}C".format(temp) if temp is not None else "-- C",
            "{:.0f}%".format(humi) if humi is not None else "--%",
        )
        lcd.print(line, 6, y, COL_WHITE)
        lcd.print(aq, 268, y, aq_col)
        y += 17
        if y > 200:
            break


def _page_wifi(data):
    lcd.font(FONT_SMALL)
    lcd.print("WiFi Settings", lcd.CENTER, 34, COL_WHITE)
    lcd.line(0, 56, 320, 56, COL_GRAY)
    lcd.font(FONT_TINY)
    lcd.print("Connected: " + data.get("wifi_ssid", WIFI_SSID), 8, 64, COL_GREEN)

    networks = data.get("wifi_networks", [])
    selected = data.get("wifi_selected", 0)
    lcd.print("Available networks:", 8, 86, COL_GRAY)
    lcd.line(0, 98, 320, 98, COL_PANEL)

    if not networks:
        lcd.print("Scanning...", 8, 108, COL_GRAY)
    else:
        y = 104
        for i, net in enumerate(networks[:6]):
            prefix = "> " if i == selected else "  "
            col    = COL_AMBER if i == selected else COL_WHITE
            rssi   = net.get("rssi", 0)
            bars   = "|||" if rssi > -60 else ("||" if rssi > -75 else "|")
            lcd.font(FONT_TINY)
            lcd.print("{}{:<22} {}".format(prefix, net.get("ssid", "?")[:22], bars),
                      8, y, col)
            y += 18

    lcd.font(FONT_TINY)
    lcd.print("[A] Prev  [B] Connect  [C] Next", 8, 194, COL_GRAY)


def screen_render(page, data):
    lcd.clear(COL_BG)
    _draw_nav_bar(page)
    if page == 0:
        _page_home(data)
    elif page == 1:
        _page_forecast(data)
    elif page == 2:
        _page_history(data)
    elif page == 3:
        _page_wifi(data)


# =============================================================================
# [6] WEATHER (OpenWeatherMap)
# =============================================================================

_OWM_BASE = "http://api.openweathermap.org/data/2.5"


def _http_get(url):
    try:
        r    = urequests.get(url)
        data = ujson.loads(r.content)
        r.close()
        return data
    except Exception as e:
        print("[weather] request failed:", e)
        return None


def _fetch_weather_middleware():
    try:
        url  = MIDDLEWARE_URL + "/api/weather?location=" + LOCATION
        r    = urequests.get(url)
        data = ujson.loads(r.content)
        r.close()
        return data
    except Exception as e:
        print("[weather] middleware unavailable:", e)
        return None


def _fetch_current_owm():
    url = "{}/weather?q={}&appid={}&units=metric".format(
        _OWM_BASE, LOCATION, OPENWEATHER_API_KEY)
    raw = _http_get(url)
    if raw is None:
        return None
    # OWM returns {"cod": 401} when the key is invalid/not yet activated
    if str(raw.get("cod", 200)) != "200":
        print("[weather] OWM error:", raw.get("message", "unknown"))
        return None
    try:
        return {
            "temp":        raw["main"]["temp"],
            "feels_like":  raw["main"]["feels_like"],
            "humidity":    raw["main"]["humidity"],
            "pressure":    raw["main"]["pressure"],
            "description": raw["weather"][0]["description"].capitalize(),
            "condition":   raw["weather"][0]["main"],
            "wind_speed":  raw["wind"]["speed"],
            "icon":        raw["weather"][0]["icon"],
        }
    except (KeyError, IndexError) as e:
        print("[weather] parse error:", e)
        return None


def _fetch_forecast_owm():
    url = "{}/forecast?q={}&appid={}&units=metric&cnt=40".format(
        _OWM_BASE, LOCATION, OPENWEATHER_API_KEY)
    raw = _http_get(url)
    if raw is None:
        return []
    # Handle invalid/not-yet-active API key
    if str(raw.get("cod", 200)) not in ("200", "0"):
        print("[weather] OWM forecast error:", raw.get("message", "unknown"))
        return []
    days = {}
    for item in raw.get("list", []):
        t     = item["dt"]
        tt    = utime.localtime(t + TIMEZONE_OFFSET * 3600)
        label = "{:02d}/{:02d}".format(tt[2], tt[1])
        dow   = _DAYS[tt[6]]
        if label not in days:
            days[label] = {
                "day_name": dow, "date": label,
                "temps": [], "condition": item["weather"][0]["main"],
                "rain_list": [],
            }
        days[label]["temps"].append(item["main"]["temp"])
        days[label]["rain_list"].append(item.get("pop", 0))
    result = []
    for label, d in days.items():
        temps = d["temps"]
        result.append({
            "day_name":  d["day_name"],
            "date":      d["date"],
            "temp_max":  max(temps),
            "temp_min":  min(temps),
            "condition": d["condition"],
            "rain_prob": max(d["rain_list"]) if d["rain_list"] else 0,
        })
        if len(result) >= 5:
            break
    return result


def weather_get():
    """Return {"current": {...}, "forecast": [...]} or {} on failure."""
    data = _fetch_weather_middleware()
    if data:
        return data
    current  = _fetch_current_owm()
    forecast = _fetch_forecast_owm()
    if current is None and not forecast:
        return {}
    return {"current": current or {}, "forecast": forecast or []}


def is_rain_forecast(forecast):
    if not forecast:
        return False
    return forecast[0].get("rain_prob", 0) >= 0.4


# =============================================================================
# [7] CLOUD (BigQuery via middleware)
# =============================================================================

_HEADERS = {"Content-Type": "application/json"}


def _cloud_post(path, payload):
    try:
        url  = MIDDLEWARE_URL + path
        body = ujson.dumps(payload)
        r    = urequests.post(url, data=body, headers=_HEADERS)
        resp = ujson.loads(r.content)
        r.close()
        return resp
    except Exception as e:
        print("[cloud] POST {} failed: {}".format(path, e))
        return None


def _cloud_get(path):
    try:
        url  = MIDDLEWARE_URL + path
        r    = urequests.get(url, headers=_HEADERS)
        resp = ujson.loads(r.content)
        r.close()
        return resp
    except Exception as e:
        print("[cloud] GET {} failed: {}".format(path, e))
        return None


def cloud_send(reading):
    """Upload sensor reading to BigQuery via middleware."""
    result = _cloud_post("/api/sensor", reading)
    return result is not None and result.get("status") == "ok"


def cloud_get_latest():
    """Fetch most recent stored reading (used on boot to pre-populate screen)."""
    data = _cloud_get("/api/sensor/latest")
    if data and "data" in data:
        return data["data"]
    return None


def cloud_get_history(hours=24):
    """Fetch recent readings for the History page."""
    data = _cloud_get("/api/sensor/history?hours={}".format(hours))
    if data and "data" in data:
        return data["data"]
    return []


# =============================================================================
# [8] VOICE (TTS / STT / LLM Q&A via middleware)
# =============================================================================

_HW_AVAILABLE = False
try:
    from m5stack import speaker
    _HW_AVAILABLE = True
except Exception:
    print("[voice] speaker not available")


def _voice_post(path, payload):
    import gc
    gc.collect()
    r = None
    try:
        r = urequests.post(
            MIDDLEWARE_URL + path,
            data=ujson.dumps(payload),
            headers=_HEADERS
        )
        data = ujson.loads(r.content)
        r.close()
        return data
    except Exception as e:
        print("[voice] request failed:", e)
        if r is not None:
            try:
                r.close()
            except: pass
        return None


def _urlencode(s):
    res = ""
    for c in s:
        if c.isalpha() or c.isdigit() or c in "-_.~":
            res += c
        elif c == " ":
            res += "%20"
        else:
            h = hex(ord(c))[2:]
            if len(h) == 1: h = "0" + h
            res += "%" + h.upper()
    return res


def voice_speak(text, audio_id=None):
    """Call Cloud Run TTS and stream audio via playCloudWAV."""
    if not text:
        return
    print("[voice] TTS:", text[:60])
    
    # Show text on screen to verify what it's saying
    lcd.rect(0, 190, 320, 50, COL_BG, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print(text[:45], 5, 195, COL_CYAN)
    
    if not _HW_AVAILABLE:
        return

    try:
        if audio_id:
            url = MIDDLEWARE_URL + "/api/voice/tts.wav?id=" + audio_id
        else:
            url = MIDDLEWARE_URL + "/api/voice/tts.wav?text=" + _urlencode(text)
        
        try:
            import power
            power.setSpkEnable(True)
        except: pass
        
        try: speaker.setVolume(100)
        except: pass
        
        # Play directly from the cloud
        speaker.playCloudWAV(url)
        
        utime.sleep_ms(500)
    except Exception as e:
        lcd.print("Audio err: " + str(e)[:25], 5, 210, COL_RED)
        utime.sleep(2)
        
    # Clear the text after speaking
    lcd.rect(0, 190, 320, 50, COL_BG, COL_BG)


def voice_ask(query, context):
    """Send a natural language question + context → get LLM answer."""
    resp = _voice_post("/api/voice/query", {"query": query, "context": context})
    return resp


def build_announcement(data, forecast):
    """Build a TTS announcement for when motion is detected."""
    parts = []
    weather = data.get("weather", {}).get("current", {})
    if weather:
        parts.append("Outside it's {} degrees and {}.".format(
            int(weather.get("temp", 0)),
            weather.get("description", "").lower() or "variable",
        ))
    temp = data.get("temperature")
    humi = data.get("humidity")
    if temp is not None:
        parts.append("Inside: {:.1f} degrees.".format(temp))
    if humi is not None:
        parts.append("Humidity: {:.0f} percent.".format(humi))
    if humi is not None and humi < ALERT_HUMIDITY_MIN:
        parts.append(
            "Warning: indoor humidity is very low at {:.0f} percent. "
            "Consider using a humidifier.".format(humi)
        )
    aq = data.get("aq_label", "Good")
    if aq in ("Poor", "Hazardous"):
        parts.append("Air quality is {}. Consider ventilating.".format(aq.lower()))
    if is_morning() and is_rain_forecast(forecast):
        parts.append("Rain is expected today. Don't forget your umbrella!")
    if weather.get("condition") == "Thunderstorm":
        parts.append("There is a thunderstorm outside. Stay safe!")
    return " ".join(parts) if parts else "Everything looks good. Have a great day!"


# =============================================================================
# [9] WIFI MANAGER (in-app network switching)
# =============================================================================

_CREDS_FILE = "wifi_creds.json"


def _wifi_load_creds():
    try:
        with open(_CREDS_FILE) as f:
            d = ujson.load(f)
        return d["ssid"], d["password"]
    except Exception:
        return WIFI_SSID, WIFI_PASSWORD


def _wifi_save_creds(ssid, password):
    try:
        with open(_CREDS_FILE, "w") as f:
            ujson.dump({"ssid": ssid, "password": password}, f)
    except Exception as e:
        print("[wifi] could not save creds:", e)


def wifi_current_ssid():
    import network
    wlan = network.WLAN(network.STA_IF)
    try:
        return wlan.config("essid")
    except Exception:
        return ""


def wifi_connect(ssid=None, password=None):
    import network
    if ssid is None or password is None:
        ssid, password = _wifi_load_creds()
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if wlan.isconnected() and wlan.config("essid") == ssid:
        return True
    wlan.connect(ssid, password)
    deadline = utime.time() + WIFI_TIMEOUT
    while not wlan.isconnected():
        if utime.time() > deadline:
            print("[wifi] timed out")
            return False
        utime.sleep_ms(300)
    print("[wifi] connected:", wlan.ifconfig())
    _wifi_save_creds(ssid, password)
    return True


def wifi_scan():
    import network
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    try:
        results = wlan.scan()
        nets, seen = [], set()
        for r in results:
            ssid = r[0].decode("utf-8", "ignore")
            if ssid and ssid not in seen:
                seen.add(ssid)
                nets.append({"ssid": ssid, "rssi": r[3]})
        nets.sort(key=lambda x: -x["rssi"])
        return nets
    except Exception as e:
        print("[wifi] scan failed:", e)
        return []


# =============================================================================
# [10] ALERT LOGIC
# =============================================================================

def update_alerts(indoor):
    alerts = []
    humi = indoor.get("humidity")
    tvoc = indoor.get("tvoc")
    eco2 = indoor.get("eco2")
    if humi is not None and humi < ALERT_HUMIDITY_MIN:
        alerts.append("Humidity {:.0f}% – Too low!".format(humi))
    if tvoc is not None and tvoc > ALERT_TVOC_MAX:
        alerts.append("Air quality POOR ({} ppb)".format(tvoc))
    if eco2 is not None and eco2 > ALERT_ECO2_MAX:
        alerts.append("CO2 high: {} ppm".format(eco2))
    return alerts


# =============================================================================
# [11] MAIN LOOP
# =============================================================================

def build_display_data(indoor, weather, history, time_now,
                       wifi_networks=None, wifi_selected=0):
    data = {}
    data.update(indoor)
    data["weather"]       = weather
    data["history"]       = history
    data["time"]          = time_now
    data["wifi_ssid"]     = wifi_current_ssid()
    data["wifi_networks"] = wifi_networks or []
    data["wifi_selected"] = wifi_selected
    return data


def run_voice_qa(indoor, weather, history, time_now):
    screen_show_loading("Thinking...")
    # Note: True STT on UIFlow requires native C modules for I2S microphone recording.
    # Here we trigger an intelligent contextual summary using Gemini LLM.
    resp = voice_ask("", build_display_data(indoor, weather, history, time_now))
    if resp:
        ans = resp.get("answer")
        audio_id = resp.get("audio_id")
        if ans:
            screen_show_loading("Speaking...")
            voice_speak(ans, audio_id)
            screen_show_loading("Done")
    else:
        screen_show_error("Could not get an answer.")


def main():
    # ── Init ────────────────────────────────────────────────────────────────
    lcd.clear(COL_BG)
    sensors_init()

    page          = 0
    indoor        = {}
    weather       = {}
    history       = []
    alerts        = []
    wifi_networks = []
    wifi_selected = 0
    time_now      = {}

    last_sensor   = 0
    last_upload   = 0
    last_weather  = 0
    last_display  = 0
    last_announce = utime.ticks_ms()

    # ── Boot sequence ────────────────────────────────────────────────────────
    # 1. Try to load last data from BigQuery (fills screen before sensors read)
    screen_show_loading("Fetching last data...")
    last = cloud_get_latest()
    if last:
        indoor.update(last)

    # 2. Fetch weather (also confirms network is up)
    screen_show_loading("Loading weather...")
    weather = weather_get()

    # 3. NTP sync LAST — network is confirmed up after weather call
    screen_show_loading("Syncing clock...")
    ntp_sync()

    # 4. Load history
    history = cloud_get_history()

    # ── Main loop ────────────────────────────────────────────────────────────
    while True:
        now = utime.time()

        # Read sensors
        if now - last_sensor >= SENSOR_READ_INTERVAL:
            reading = sensors_read()
            indoor.update(reading)
            alerts = update_alerts(indoor)
            screen_set_alerts(alerts)
            last_sensor = now

        # Upload to cloud
        if now - last_upload >= CLOUD_UPLOAD_INTERVAL:
            if indoor:
                cloud_send(indoor)
            last_upload = now

        # Refresh weather
        if now - last_weather >= WEATHER_REFRESH_INTERVAL:
            w = weather_get()
            if w:
                weather = w
            last_weather = now

        # Refresh display
        if now - last_display >= DISPLAY_TICK:
            time_now = ntp_now()
            data = build_display_data(
                indoor, weather, history, time_now,
                wifi_networks, wifi_selected
            )
            screen_render(page, data)
            last_display = now

        # ── Buttons ──────────────────────────────────────────────────────────
        if btnA.wasPressed():
            if page == 3 and wifi_networks:
                wifi_selected = (wifi_selected - 1) % len(wifi_networks)
            elif page > 0:
                page -= 1
                if page == 2:
                    history = cloud_get_history()

        if btnC.wasPressed():
            if page == 3 and wifi_networks:
                wifi_selected = (wifi_selected + 1) % len(wifi_networks)
            elif page < NUM_PAGES - 1:
                page += 1
                if page == 2:
                    history = cloud_get_history()
                if page == 3:
                    wifi_networks = wifi_scan()
                    wifi_selected = 0

        if btnB.wasPressed():
            if page == 3 and wifi_networks:
                net  = wifi_networks[wifi_selected]
                ssid = net["ssid"]
                screen_show_loading("Connecting to {}...".format(ssid[:20]))
                ok = wifi_connect(ssid, "")
                if ok:
                    wifi_networks = []
            else:
                data = build_display_data(
                    indoor, weather, history, time_now,
                    wifi_networks, wifi_selected
                )
                run_voice_qa(indoor, weather, history, time_now)

        utime.sleep_ms(100)


# Entry point
main()
