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
WIFI_SSID     = "Sunrise_Wi-Fi_6315482"   # WiFi de la maison (Noah)
WIFI_PASSWORD = "sfk6rtdyTjMv"
WIFI_TIMEOUT  = 30  # seconds
IS_ONLINE     = False
KNOWN_NETWORKS = [
    (WIFI_SSID, WIFI_PASSWORD),
    ("iPhone", "12345678"),
    ("M5-Config", "12345678")
]

# Location
LOCATION        = "Lausanne,CH"
TIMEZONE_OFFSET = 2  # CEST = UTC+2

# Middleware (Flask API on Google Cloud Run — deployed!)
MIDDLEWARE_URL = "https://core2-middleware-337108994948.europe-west1.run.app"

def set_screen_brightness(level):
    """Safely attempts to set screen brightness (0-100) across different M5Stack API versions"""
    try:
        # Core2 axp global object
        axp.setLcdBrightness(level)
        return
    except: pass
    try:
        # Older core M5Stack
        power.setLCDBrightness(level)
        return
    except: pass
    try:
        import axp as _axp
        _axp.setLcdBrightness(level)
        return
    except: pass
    try:
        lcd.setBrightness(int(level * 255 / 100))
        return
    except: pass
    


# External APIs
OPENWEATHER_API_KEY = "REMOVED_FOR_SECURITY"
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
DISPLAY_TICK             = 30     # screen refresh
CLOCK_TICK               = 1      # clock refresh

# Display dimensions
SCREEN_W = 320
SCREEN_H = 240

# Colour palette (RGB565)
COL_YELLOW = 0xFFEB3B   # warnings
COL_BLUE   = 0x64B5F6   # outdoor accent
COL_GRAY   = 0x607D8B   # secondary text
COL_TOPBAR = 0x1565C0   # top navigation bar
COL_BG     = 0x000000   # Fond noir
COL_PANEL  = 0x1b263b
COL_WHITE  = 0xffffff
COL_AMBER  = 0xFF9F00   # temperature
COL_CYAN   = 0x00D4FF   # humidity
COL_GREEN  = 0x00E676   # good air quality
COL_RED    = 0xFF4444   # alerts / bad AQ

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

    import network
    if not network.WLAN(network.STA_IF).isconnected():
        lcd.font(FONT_TINY)
        lcd.print("Offline: Skipping time sync", lcd.CENTER, 130, COL_YELLOW)
        utime.sleep(1)
        return False

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
    pir_state = False
    if _pir:
        try:
            pir_state = (_pir.state == 1)
        except Exception:
            pass
    return {
        "temperature": temp,
        "humidity":    humi,
        "tvoc":        tvoc,
        "eco2":        eco2,
        "aq_label":    _aq_label(tvoc),
        "pir":         pir_state,
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

NUM_PAGES = 5  # 0=Home, 1=Forecast, 2=History, 3=Settings, 4=Voice

_screen_alerts = []

def _weather_icon_path(condition, big=False):
    mapping = {
        "Clear": "clear", "Clouds": "clouds", "Rain": "rain",
        "Drizzle": "rain", "Thunderstorm": "storm", "Snow": "snow",
    }
    basename = mapping.get(condition, "partly")
    if big:
        return "res/" + basename + "_big.jpg"
    return "res/" + basename + "_v2.jpg"

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
    # Dessin de la Top Bar
    lcd.rect(10, 5, 300, 24, COL_WHITE, COL_BG) # Contour blanc, fond noir
    labels = ["HOME", "FORECAST", "HISTORY", "SETTINGS"]
    x = 18
    for i, label in enumerate(labels):
        if i == page:
            lcd.font(FONT_TINY)
            lcd.print(label, x, 10, COL_BLUE)
        else:
            lcd.font(FONT_TINY)
            lcd.print(label, x, 10, COL_WHITE)
        x += 75
        
    # Online/Offline LED indicator (M5Go side bars)
    try:
        from m5stack import rgb
        if IS_ONLINE:
            rgb.setColorAll(0x001100) # Dim green
        else:
            rgb.setColorAll(0x110000) # Dim red
    except Exception:
        pass

def _draw_alerts():
    if not _screen_alerts:
        return
    msg = " | ".join(_screen_alerts)
    lcd.rect(0, 222, 320, 18, COL_RED, COL_RED)
    lcd.font(FONT_TINY)
    lcd.print(msg[:52], 4, 225, COL_WHITE)

def _page_home(data):
    _draw_outdoor_card(data)
    _draw_indoor_card(data)
    _draw_alerts()

def _draw_indoor_card(data):
    temp = data.get("temperature")
    humi = data.get("humidity")
    eco2 = data.get("eco2")
    aq   = data.get("aq_label", "N/A")
    aq_col = _aq_color(aq)
    
    x, y, w, h = 165, 35, 145, 180
    lcd.rect(x, y, w, h, COL_CYAN, COL_BG) # Contour cyan, fond noir
    lcd.font(FONT_SMALL)
    lcd.print("INDOOR", x+15, y+15, COL_CYAN)
    lcd.font(FONT_LARGE)
    lcd.print("{:.1f}C".format(temp) if temp is not None else "--C", x+15, y+45, COL_AMBER)
    lcd.font(FONT_SMALL)
    lcd.print("{:.0f}% hum".format(humi) if humi is not None else "--%", x+15, y+95, COL_CYAN)
    lcd.font(FONT_TINY)
    lcd.print("{} ppm CO2".format(eco2) if eco2 is not None else "-- ppm", x+15, y+125, COL_WHITE)
    lcd.print("{} air quality".format(aq), x+15, y+150, aq_col)

def _draw_outdoor_card(data):
    weather = data.get("weather", {}).get("current", {})
    icon_path = _weather_icon_path(weather.get("condition", ""))
    temp = weather.get("temp")
    feels = weather.get("feels_like")
    humi = weather.get("humidity")
    wind = weather.get("wind_speed")
    
    x, y, w, h = 10, 35, 145, 180
    lcd.rect(x, y, w, h, COL_AMBER, COL_BG) # Contour orange, fond noir
    lcd.font(FONT_SMALL)
    lcd.print("OUTDOOR", x+15, y+15, COL_AMBER)
    lcd.font(FONT_LARGE)
    lcd.print("{:.1f}C".format(temp) if temp is not None else "--C", x+15, y+45, COL_AMBER)
    lcd.font(FONT_TINY)
    lcd.print("{:.0f}C feels like".format(feels) if feels is not None else "--", x+15, y+95, COL_AMBER)
    lcd.print("{:.0f}% humidity".format(humi) if humi is not None else "--", x+15, y+120, COL_AMBER)
    lcd.print("{} m/s wind".format(wind) if wind is not None else "--", x+15, y+145, COL_AMBER)


def _page_forecast(data):
    forecast = data.get("weather", {}).get("forecast", {})
    if isinstance(forecast, list):
        # Fallback raw OWM data is a list
        hourly = []
        daily = forecast
    else:
        hourly = forecast.get("hourly", [])
        daily = forecast.get("daily", [])
    
    # Bloc horaire en haut (hauteur réduite)
    lcd.rect(10, 35, 300, 65, COL_BLUE, COL_BG)
    
    if not hourly:
        lcd.font(FONT_SMALL)
        lcd.print("No forecast", 100, 60, COL_GRAY)
    else:
        for i, h in enumerate(hourly[:6]):
            x = 15 + (i * 48)
            lcd.font(FONT_TINY)
            lcd.print(h.get("time", "?"), x, 40, COL_WHITE)
            try:
                # Icon size is 20x20 now
                lcd.image(x+5, 55, _weather_icon_path(h.get("condition", "")))
            except: pass
            lcd.font(FONT_TINY)
            t = h.get("temp")
            lcd.print("{}C".format(int(t) if t is not None else "--"), x+5, 82, COL_WHITE)
        
    # 5-DAY FORECAST 
    lcd.rect(10, 105, 300, 134, COL_BLUE, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print("5 DAY FORECAST", 15, 110, COL_BLUE)
    
    # Calculate global min/max for proportional gauges
    if daily:
        g_min = min([d.get("temp_min", 0) for d in daily[:6]])
        g_max = max([d.get("temp_max", 0) for d in daily[:6]])
        if g_max == g_min: g_max += 1
    else:
        g_min, g_max = 0, 1
        
    gauge_x = 140
    gauge_w = 115
    
    y = 125
    for i, day in enumerate(daily[:6]):
        lcd.font(FONT_TINY)
        day_name = day.get("day_name", "?")
        if i == 0: day_name = "Today"
        lcd.print(day_name, 15, y+2, COL_WHITE)
        try:
            lcd.image(80, y, _weather_icon_path(day.get("condition", "")))
        except: pass
        
        t_min = day.get("temp_min", 0)
        t_max = day.get("temp_max", 0)
        lcd.print("{}C".format(int(t_min)), 110, y+2, COL_WHITE)
        
        # Piste de fond (Gris foncé)
        lcd.rect(gauge_x, y+6, gauge_w, 3, COL_PANEL, COL_PANEL)
        
        # Segment proportionnel
        start_px = int((t_min - g_min) / (g_max - g_min) * gauge_w)
        width_px = int((t_max - t_min) / (g_max - g_min) * gauge_w)
        if width_px < 2: width_px = 2
        lcd.rect(gauge_x + start_px, y+6, width_px, 3, COL_AMBER, COL_AMBER)
        
        # Si c'est aujourd'hui, point de la temp actuelle
        if i == 0:
            curr_t = hourly[0].get("temp", t_min) if hourly else t_min
            curr_t = max(t_min, min(t_max, curr_t))
            dot_px = int((curr_t - g_min) / (g_max - g_min) * gauge_w)
            lcd.circle(gauge_x + dot_px, y+7, 4, COL_WHITE, COL_WHITE)
            
        lcd.print("{}C".format(int(t_max)), 265, y+2, COL_WHITE)
        
        y += 18
        if y > 230: break


def _page_history(data):
    history = data.get("history", {})
    
    # 1. Left Panel (Bar Chart)
    lcd.rect(10, 35, 145, 200, COL_BLUE, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print("INDOOR VS OUTDOOR C", 15, 42, COL_WHITE)
    
    bars = history.get("bars", [])
    y = 62
    max_px = 90
    max_temp = 30.0
    
    for b in bars:
        lcd.font(FONT_TINY)
        lcd.print(b.get("day", "")[:3], 15, y+2, COL_WHITE)
        
        # Indoor (Orange)
        t_in = min(max_temp, max(0, b.get("in", 0)))
        w_in = int((t_in / max_temp) * max_px)
        if w_in < 2: w_in = 2
        lcd.rect(48, y, w_in, 8, COL_AMBER, COL_AMBER)
        
        # Outdoor (Blue)
        t_out = min(max_temp, max(0, b.get("out", 0)))
        w_out = int((t_out / max_temp) * max_px)
        if w_out < 2: w_out = 2
        lcd.rect(48, y+9, w_out, 8, COL_BLUE, COL_BLUE)
        
        y += 22

    # Scale numbers at bottom
    lcd.print("0", 48, 220, COL_GRAY)
    lcd.print("10", 78, 220, COL_GRAY)
    lcd.print("20", 108, 220, COL_GRAY)
    lcd.print("30", 138, 220, COL_GRAY)

    # 2. Top Right Panel (Humidity)
    lcd.rect(160, 35, 150, 95, COL_BLUE, COL_BG)
    lcd.print("HUMIDITY LAST WEEK", 165, 42, COL_WHITE)
    
    humi = history.get("humidity", 0)
    cx, cy, r, thick = 235, 85, 30, 10
    
    import math
    lcd.circle(cx, cy, r, COL_WHITE, COL_WHITE)
    for a in range(0, int((humi / 100) * 360), 2):
        rad = math.radians(a - 90)
        x2 = cx + int(math.cos(rad) * (r - thick/2))
        y2 = cy + int(math.sin(rad) * (r - thick/2))
        lcd.circle(x2, y2, int(thick/2), COL_BLUE, COL_BLUE)
    lcd.circle(cx, cy, r - thick, COL_BG, COL_BG)
    
    lcd.font(FONT_SMALL)
    lcd.print("{}%".format(humi), cx - 18, cy - 8, COL_WHITE)
    
    # 3. Bottom Right Panel (Alerts)
    lcd.rect(160, 135, 150, 100, COL_BLUE, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print("ALERTS LAST WEEK", 165, 142, COL_WHITE)
    
    alerts = history.get("alerts", 0)
    lcd.font(FONT_LARGE)
    lcd.print(str(alerts), 225, 165, COL_AMBER)


def _page_settings(data):
    lcd.rect(10, 35, 300, 195, COL_BLUE, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print("SETTINGS & STATUS", 15, 42, COL_BLUE)
    lcd.line(10, 55, 310, 55, COL_BLUE)
    
    lcd.print("WiFi Connected: " + data.get("wifi_ssid", "?"), 15, 65, COL_GREEN)
    lcd.print("Middleware: " + ("OK" if data.get("weather") else "ERROR"), 15, 95, COL_GREEN if data.get("weather") else COL_RED)
    
    # WiFi Switcher UI
    lcd.rect(50, 130, 220, 40, COL_BLUE, COL_BG)
    lcd.font(FONT_SMALL)
    lcd.print("SWITCH WIFI", 100, 140, COL_WHITE)
    
    lcd.font(FONT_TINY)
    lcd.print("[A] Volume-  [B] Mic Test  [C] Volume+", 25, 200, COL_GRAY)

def _page_voice(data):
    lcd.rect(10, 35, 300, 195, COL_BLUE, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print("VOICE ASSISTANT", 15, 42, COL_BLUE)
    lcd.line(10, 55, 310, 55, COL_BLUE)
    
    voice_state = data.get("voice_state", "ready")
    transcript = data.get("transcript", "")
    answer = data.get("answer", "")
    
    if voice_state == "done":
        # Affichage avec retour a la ligne pour NE PAS deborder de l'ecran (320 px).
        lcd.font(FONT_TINY)            # petite police -> ~46 caracteres par ligne

        def _wrap(texte, largeur):
            """Decoupe 'texte' en lignes de 'largeur' caracteres max, en gardant
            les mots entiers (coupe seulement les mots plus longs que la ligne)."""
            lignes = []
            courante = ""
            for mot in str(texte).split(" "):
                while len(mot) > largeur:           # mot trop long -> coupe brute
                    if courante:
                        lignes.append(courante); courante = ""
                    lignes.append(mot[:largeur]); mot = mot[largeur:]
                if courante == "":
                    courante = mot
                elif len(courante) + 1 + len(mot) <= largeur:
                    courante += " " + mot
                else:
                    lignes.append(courante); courante = mot
            if courante:
                lignes.append(courante)
            return lignes

        y = 62
        LH = 14          # hauteur de ligne (px)
        YMAX = 225       # on s'arrete avant le bas du cadre
        W = 46           # caracteres par ligne (FONT_TINY ~ 6 px/car sur ~290 px)

        if transcript:
            for ligne in _wrap("Vous: " + str(transcript), W):
                if y > YMAX: break
                lcd.print(ligne, 15, y, COL_WHITE); y += LH
            y += 4
        if answer:
            for ligne in _wrap("IA: " + str(answer), W):
                if y > YMAX: break
                lcd.print(ligne, 15, y, COL_GREEN); y += LH
    else:
        # Show robot at the bottom center
        try:
            lcd.image(120, 140, "res/robot_big.jpg")
        except: pass
        
        # Speech bubble
        lcd.roundrect(60, 70, 200, 40, 10, COL_WHITE, COL_WHITE)
        lcd.triangle(150, 110, 170, 110, 160, 125, COL_WHITE, COL_WHITE)
        
        lcd.font(FONT_SMALL)
        if voice_state == "listening":
            lcd.print("Je vous ecoute...", 75, 80, COL_BG)
        elif voice_state == "thinking":
            lcd.print("Je reflechis...", 85, 80, COL_BG)

def _page_standby(data, full=True):
    t = data.get("time", {})
    time_str = "{:02d}:{:02d}".format(t.get("h", 0), t.get("m", 0))
    
    if full:
        # Contour bleu et fond
        lcd.rect(10, 10, 300, 220, COL_BLUE, COL_BG)
        
        mo_names = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        mo = t.get("mo", 1)
        day_str = "{} {} {}".format(t.get("day", "").upper(), mo_names[mo], t.get("dd", 1))
        
        lcd.font(FONT_MEDIUM)
        lcd.print(day_str, lcd.CENTER, 45, COL_WHITE)
        
        lcd.font(FONT_LARGE)
        lcd.print(time_str, lcd.CENTER, 95, COL_WHITE)
        
        icon = data.get("weather", {}).get("current", {}).get("condition", "Clear")
        try:
            # 50x50 icon, center is at X=135 (320/2 - 25)
            lcd.image(135, 155, _weather_icon_path(icon, big=True))
        except:
            pass
    else:
        # Only update the time area to prevent flickering the image/date
        lcd.rect(15, 95, 290, 50, COL_BG, COL_BG)
        lcd.font(FONT_LARGE)
        lcd.print(time_str, lcd.CENTER, 95, COL_WHITE)

def screen_render(page, data, is_standby=False, full_refresh=True):
    if is_standby:
        if full_refresh:
            lcd.clear(COL_BG)
        _page_standby(data, full=full_refresh)
        return

    if full_refresh:
        lcd.clear(COL_BG)
        
    _draw_nav_bar(page)
    if page == 0:
        _page_home(data)
    elif page == 1:
        _page_forecast(data)
    elif page == 2:
        _page_history(data)
    elif page == 3:
        _page_settings(data)
    elif page == 4:
        _page_voice(data)



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
            "description": raw["weather"][0]["description"],
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
    global IS_ONLINE
    import network
    if not network.WLAN(network.STA_IF).isconnected():
        IS_ONLINE = False
        return None
    try:
        url  = MIDDLEWARE_URL + path
        body = ujson.dumps(payload)
        r    = urequests.post(url, data=body, headers=_HEADERS)
        resp = ujson.loads(r.content)
        r.close()
        IS_ONLINE = True
        return resp
    except Exception as e:
        print("[cloud] POST {} failed: {}".format(path, e))
        IS_ONLINE = False
        return None


def _cloud_get(path):
    global IS_ONLINE
    import network
    if not network.WLAN(network.STA_IF).isconnected():
        IS_ONLINE = False
        return None
    try:
        url  = MIDDLEWARE_URL + path
        r    = urequests.get(url, headers=_HEADERS)
        resp = ujson.loads(r.content)
        r.close()
        IS_ONLINE = True
        return resp
    except Exception as e:
        print("[cloud] GET {} failed: {}".format(path, e))
        IS_ONLINE = False
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


def cloud_get_history():
    """Fetch weekly aggregated readings for the History dashboard."""
    data = _cloud_get("/api/sensor/history_weekly")
    if data and "data" in data:
        return data["data"]
    return {}


# =============================================================================
# [8] VOICE (TTS / STT / LLM Q&A via middleware)
# =============================================================================

_HW_AVAILABLE = False
try:
    from m5stack import speaker
    _HW_AVAILABLE = True
except Exception:
    print("[voice] speaker not available")

FICHIER_VOIX = "/flash/voix.wav"
FICHIER_REPONSE = "/flash/reponse.wav"
FICHIER_LOG = "/flash/debug.log"        # journal lisible via appui LONG sur le bouton A
DUREE_ENREGISTREMENT_S = 5

def log(msg):
    """Affiche dans la console ET ajoute la ligne au journal /flash/debug.log.
    Permet de relire les erreurs sur le M5 via un appui LONG sur le bouton A
    (utile car UIFlow n'affiche pas les erreurs runtime une fois le code lance)."""
    print(msg)
    try:
        with open(FICHIER_LOG, "a") as f:
            f.write(str(msg) + "\n")
    except: pass

def preparer_audio():
    try:
        import power
        power.setSpkEnable(True)
    except: pass
    try:
        speaker.setVolume(100)
    except: pass

def enregistrer_voix(chemin):
    try: speaker.end()
    except: pass
    mic = globals().get("Mic") or globals().get("mic")
    if mic is None:
        try: import mic
        except: pass
    try: mic.record2file(DUREE_ENREGISTREMENT_S, chemin)
    except Exception as e: print("[voice] record error", e)

def jouer_wav(chemin):
    utime.sleep_ms(500)
    try: speaker.begin()
    except: pass
    preparer_audio()
    try: speaker.playWAV(chemin, volume=100)
    except Exception as e: print("[voice] playWAV error", e)

def _urlencode(s):
    # Encodage pourcent CORRECT en UTF-8 : on encode chaque OCTET de la
    # representation UTF-8 (et pas le code-point). L'ancienne version cassait
    # les accents (e, e, a, c...) -> le serveur recevait du texte corrompu et
    # la synthese vocale lisait du charabia. "HEX" pour mapper octet -> 2 hex.
    HEX = "0123456789ABCDEF"
    out = ""
    for b in s.encode("utf-8"):
        if (48 <= b <= 57) or (65 <= b <= 90) or (97 <= b <= 122) or b in (45, 46, 95, 126):
            out += chr(b)            # caracteres non reserves : A-Z a-z 0-9 - . _ ~
        else:
            out += "%" + HEX[b >> 4] + HEX[b & 15]
    return out

def voice_speak(text):
    if not text: return
    try:
        preparer_audio()
        import gc; gc.collect()
        url = MIDDLEWARE_URL + "/api/voice/tts.wav?text=" + _urlencode(text[:150])
        speaker.playCloudWAV(url)
        utime.sleep_ms(500)
    except Exception as e:
        print("[voice] TTS Error", e)

def voice_listen_flow(data_dict):
    global page
    page = 4
    data_dict["voice_state"] = "listening"
    screen_render(page, data_dict, False, True)

    log("[C] enregistrement...")
    enregistrer_voix(FICHIER_VOIX)

    data_dict["voice_state"] = "thinking"
    screen_render(page, data_dict, False, True)

    try:
        import gc; gc.collect()
        with open(FICHIER_VOIX, "rb") as f: audio_data = f.read()
        log("[C] WAV=" + str(len(audio_data)) + " octets -> /listen")
        r = urequests.post(MIDDLEWARE_URL + "/api/voice/listen", data=audio_data, headers={"Content-Type": "audio/wav"})
        log("[LISTEN] status=" + str(r.status_code))
        resp = ujson.loads(r.content)
        r.close()

        if resp.get("status") == "ok":
            answer = resp.get("answer", "")
            data_dict["voice_state"] = "done"
            data_dict["transcript"] = resp.get("transcript", "")
            data_dict["answer"] = answer
            log("[STT] " + str(resp.get("transcript", "")))
            log("[LLM] " + str(answer)[:120])
            screen_render(page, data_dict, False, True)

            # Téléchargement en CHUNKS (512 o) vers /flash, puis lecture via
            # jouer_wav (playWAV volume=100 -> son FORT).
            # Pourquoi ce compromis :
            #  - r2.content chargeait TOUT le WAV en RAM -> saturation (latence 2 min).
            #  - playCloudWAV (streaming) règle la RAM MAIS joue au volume par défaut
            #    (trop faible : sur ce firmware setVolume() est inopérant, seul le
            #     parametre volume= de playWAV agit).
            #  -> On lit donc le WAV par petits morceaux (RAM minimale) vers le
            #     fichier, puis on le joue avec volume=100. Rapide ET fort.
            try:
                gc.collect()
                url = MIDDLEWARE_URL + "/api/voice/tts.wav?text=" + _urlencode(answer[:200])
                r2 = urequests.get(url)
                ok = (r2.status_code == 200)
                if ok:
                    recu = 0
                    with open(FICHIER_REPONSE, "wb") as f2:
                        while True:
                            chunk = r2.raw.read(512)   # 512 o a la fois -> RAM minimale
                            if not chunk:
                                break
                            f2.write(chunk)
                            recu += len(chunk)
                    log("[TTS] recu " + str(recu) + " octets (chunks)")
                r2.close()
                if ok:
                    jouer_wav(FICHIER_REPONSE)         # playWAV(volume=100) -> son fort
                else:
                    log("[TTS] HTTP " + str(r2.status_code))
                    voice_speak(answer)
            except Exception as e:
                log("[TTS] ERREUR DL: " + str(e))
                voice_speak(answer)
        else:
            data_dict["voice_state"] = "done"
            data_dict["transcript"] = "Serveur Erreur"
            data_dict["answer"] = resp.get("error", "Erreur inconnue")
            log("[LISTEN] erreur serveur: " + str(resp.get("error", "?")))
            screen_render(page, data_dict, False, True)
    except Exception as e:
        data_dict["voice_state"] = "done"
        data_dict["transcript"] = "Reseau Erreur"
        data_dict["answer"] = str(e)[:30]
        log("[C] EXCEPTION: " + str(e))
        screen_render(page, data_dict, False, True)


def show_debug_log():
    """Affiche les dernieres lignes de /flash/debug.log a l'ecran (appui LONG sur A).
    Le seul moyen de relire les erreurs sur le M5 sans cable USB."""
    try:
        with open(FICHIER_LOG) as f:
            contenu = f.read()
    except Exception as e:
        contenu = "Pas de journal: " + str(e)
    lcd.clear(COL_BG)
    lcd.font(FONT_TINY)
    # Decoupe en lignes de 52 caracteres max (pour ne pas deborder de l'ecran).
    lignes = []
    for brute in contenu.split("\n"):
        if brute == "":
            lignes.append("")
        else:
            for i in range(0, len(brute), 52):
                lignes.append(brute[i:i + 52])
    y = 4
    for ligne in lignes[-18:]:        # les 18 dernieres lignes qui tiennent a l'ecran
        lcd.print(ligne, 4, y, COL_WHITE)
        y += 13
    utime.sleep(10)                   # laisse 10 s pour lire / prendre une photo


# =============================================================================
# [8b] DEVICE POLLING (Remote Control)
# =============================================================================

def device_poll_sync():
    """Récupère la file d'attente des commandes depuis la Remote Streamlit."""
    try:
        resp = _cloud_get("/api/device/sync")
        if resp and resp.get("status") == "ok":
            return resp.get("commands", [])
    except Exception as e:
        print("[poll] error:", e)
    return []


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


def wifi_cycle():
    """Connect to the next network in KNOWN_NETWORKS."""
    import network
    wlan = network.WLAN(network.STA_IF)
    current = wlan.config("essid") if wlan.isconnected() else ""
    idx = 0
    for i, (s, p) in enumerate(KNOWN_NETWORKS):
        if s == current:
            idx = (i + 1) % len(KNOWN_NETWORKS)
            break
    print("Switching WiFi to:", KNOWN_NETWORKS[idx][0])
    wlan.disconnect()
    return wifi_connect(KNOWN_NETWORKS[idx][0], KNOWN_NETWORKS[idx][1])


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

def main():
    # ── Init ────────────────────────────────────────────────────────────────
    lcd.clear(COL_BG)
    # Journal vierge a chaque demarrage (lisible via appui LONG sur A).
    try:
        with open(FICHIER_LOG, "w") as f:
            f.write("=== DEBUG LOG ===\n")
    except: pass
    sensors_init()

    page          = 0
    home_primary  = "indoor"
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
    last_poll     = 0

    # ── Boot sequence ────────────────────────────────────────────────────────
    
    # 0. Download UI assets (self-install)
    screen_show_loading("Checking UI assets...")
    import os
    try:
        os.mkdir('res')
    except:
        pass
    for ico in ['clear', 'partly', 'clouds', 'rain', 'storm', 'snow', 'robot']:
        # Download 20x20 icons
        ico_file = ico + ".jpg"
        path = 'res/' + ico + "_v2.jpg"
        try:
            os.stat(path)
        except OSError:
            screen_show_loading("Downloading " + ico)
            try:
                import network
                if network.WLAN(network.STA_IF).isconnected():
                    r = urequests.get(MIDDLEWARE_URL + "/static/icons/" + ico_file)
                    with open(path, 'wb') as f:
                        f.write(r.content)
                    r.close()
            except: pass
            
        # Download 40x40 icons (big)
        ico_big_file = ico + "_big.jpg"
        path_big = 'res/' + ico + "_big.jpg"
        try:
            os.stat(path_big)
        except OSError:
            screen_show_loading("DL Big " + ico)
            try:
                import network
                if network.WLAN(network.STA_IF).isconnected():
                    r = urequests.get(MIDDLEWARE_URL + "/static/icons/" + ico_big_file)
                    with open(path_big, 'wb') as f:
                        f.write(r.content)
                    r.close()
            except: pass

    screen_show_loading("Fetching last data...")
    last = cloud_get_latest()
    if last:
        indoor.update(last)
        if "timestamp" in indoor:
            del indoor["timestamp"]

    screen_show_loading("Loading weather...")
    weather = weather_get() or {}

    screen_show_loading("Syncing clock...")
    ntp_sync()

    history = cloud_get_history()

    # Initial render
    data = build_display_data(indoor, weather, history, ntp_now())
    screen_render(page, data)

    # ── Main loop ────────────────────────────────────────────────────────────
    
    STANDBY_TIMEOUT = 60
    last_interaction = utime.time()
    is_standby = False
    last_pir_state = 0
    a_press_start = 0     # instant (ticks_ms) du debut d'appui sur A (0 = relache)

    while True:
        now = utime.time()

        # Buffered hardware buttons (catches presses even during HTTP blocks)
        try:
            # Bouton A : appui COURT = page precedente ; appui LONG (>=1.5s) = JOURNAL DEBUG
            if btnA.isPressed():
                if a_press_start == 0:
                    a_press_start = utime.ticks_ms()
            elif a_press_start != 0:
                held = utime.ticks_diff(utime.ticks_ms(), a_press_start)
                a_press_start = 0
                last_interaction = now
                if held >= 1500:
                    show_debug_log()
                else:
                    page = (page - 1) % NUM_PAGES
                screen_render(page, build_display_data(indoor, weather, history, ntp_now()), is_standby)
            elif btnC.wasPressed():
                last_interaction = now
                page = (page + 1) % NUM_PAGES
                screen_render(page, build_display_data(indoor, weather, history, ntp_now()), is_standby)
            elif btnB.wasPressed():
                last_interaction = now
                voice_listen_flow(build_display_data(indoor, weather, history, ntp_now()))
        except: pass

        # Touch handling
        try:
            touch_active = touch.status()
        except:
            touch_active = False
            
        if touch_active:
            last_interaction = now
            if is_standby:
                is_standby = False
                set_screen_brightness(100)
                screen_render(page, build_display_data(indoor, weather, history, ntp_now()), False)
                utime.sleep_ms(300)
                continue

            tx, ty = touch.read()
            # Top bar navigation
            if ty < 35:
                if tx < 80:
                    page = 0
                elif tx < 160:
                    page = 1
                elif tx < 240:
                    page = 2
                else:
                    page = 3
                data = build_display_data(indoor, weather, history, ntp_now())
                screen_render(page, data, is_standby)
                utime.sleep_ms(300)
            
            elif ty >= 35 and ty <= 240:
                # Handle touch in Settings Page to Switch WiFi
                if page == 3 and tx >= 50 and tx <= 270 and ty >= 130 and ty <= 170:
                    last_interaction = now
                    screen_show_loading("Switching WiFi...")
                    wifi_cycle()
                    data = build_display_data(indoor, weather, history, ntp_now())
                    screen_render(page, data, is_standby)
                    utime.sleep_ms(300)
                    continue

            # M5Stack Core2 Virtual Buttons (Bottom bezel)
            elif ty > 240:
                if tx < 106:      # Button A
                    page = (page - 1) % NUM_PAGES
                elif tx > 213:    # Button C
                    page = (page + 1) % NUM_PAGES
                else:             # Button B
                    voice_listen_flow(build_display_data(indoor, weather, history, ntp_now()))
                
                data = build_display_data(indoor, weather, history, ntp_now())
                screen_render(page, data, is_standby)
                utime.sleep_ms(300)
                    
            utime.sleep_ms(50) # debounce

        # PIR wakeup (only on transition from 0 to 1 to avoid floating pin block)
        current_pir = 0
        try:
            if _pir: current_pir = _pir.state
        except:
            pass
            
        if current_pir == 1 and last_pir_state == 0:
            last_interaction = now
            if is_standby:
                is_standby = False
                set_screen_brightness(100)
                screen_render(page, build_display_data(indoor, weather, history, ntp_now()), False, True)
        elif current_pir == 1:
            pass
            
        last_pir_state = current_pir

        # Standby logic
        if not is_standby and (now - last_interaction) > STANDBY_TIMEOUT:
            is_standby = True
            set_screen_brightness(100)  # User requested brightness à fond
            screen_render(page, build_display_data(indoor, weather, history, ntp_now()), True, True)

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

        # Refresh display (meteo)
        if now - last_display >= (1 if is_standby else DISPLAY_TICK):
            time_now = ntp_now()
            data = build_display_data(indoor, weather, history, time_now)
            screen_render(page, data, is_standby, False)
            last_display = now
            
        # Poll dashboard commands every 5 seconds (reduces HTTP blocking to improve UI responsiveness)
        if now - last_poll >= 5:
            cmds = device_poll_sync()
            for cmd in cmds:
                action = cmd.get("type")
                value = cmd.get("value")
                if action == "set_page":
                    try:
                        if isinstance(value, str) and value.startswith("page="):
                            v = value.split("=")[1]
                            p = {"home": 0, "weather": 1, "history": 2, "settings": 3}.get(v, 0)
                        else:
                            p = int(value)
                        if 0 <= p < NUM_PAGES:
                            page = p
                            screen_render(page, build_display_data(indoor, weather, history, ntp_now()), is_standby)
                    except: pass
                elif action == "prev_page":
                    page = (page - 1) % NUM_PAGES
                    screen_render(page, build_display_data(indoor, weather, history, ntp_now()), is_standby)
                elif action == "next_page":
                    page = (page + 1) % NUM_PAGES
                    screen_render(page, build_display_data(indoor, weather, history, ntp_now()), is_standby)
                elif action == "set_brightness":
                    set_screen_brightness(int(value))
                elif action == "set_volume":
                    try:
                        import machine
                        speaker.setVolume(int(value))
                    except: pass
                elif action == "play_audio":
                    voice_speak(str(value))
                elif action == "btn":
                    if value == "b":
                        voice_listen_flow(build_display_data(indoor, weather, history, ntp_now()))
            last_poll = now

        utime.sleep_ms(20)

try:
    import machine
    machine.freq(240000000)
except: pass

main()
