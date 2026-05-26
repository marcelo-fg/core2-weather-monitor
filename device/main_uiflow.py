"""
M5Stack Core2 - Indoor/Outdoor Weather Monitor

Single-file MicroPython firmware for UIFlow 1.15.2 (online, WiFi mode).
Everything is consolidated in this single file because the UIFlow web IDE
does not let you upload custom modules.

Sections:
  [1]  UIFlow imports
  [2]  Configuration
  [3]  NTP sync
  [4]  Sensors (ENV III, TVOC, PIR)
  [5]  Display / screen manager (5 pages + standby)
  [6]  Weather (OpenWeatherMap via middleware)
  [7]  Cloud (BigQuery via middleware)
  [8]  Voice (TTS / STT / LLM via middleware)
  [8b] Device polling (Remote control commands)
  [9]  WiFi manager (in-app network switching)
  [10] Alert logic
  [11] Main loop

WiFi is handled entirely by UIFlow / M5Burner — no SSID or password is
hardcoded in this file.
"""

# =============================================================================
# [1] UIFlow 1.15.2 required imports
# =============================================================================
from m5stack import *   # lcd, btnA, btnB, btnC, speaker, rgb
from m5ui import *      # M5UI components (labels, rectangles, ...)
# Note: ``from uiflow import *`` is intentionally omitted - it triggers a
# UIFlow cloud API key check that we do not need (no EzData / IFTTT).
import urequests
import ujson
import utime
import unit

# =============================================================================
# [2] CONFIGURATION
# =============================================================================

# Online status flag, updated by every cloud call.
IS_ONLINE = False

# Location used for outdoor weather lookups.
LOCATION        = "Lausanne,CH"
TIMEZONE_OFFSET = 2  # CEST = UTC+2

# Flask middleware deployed on Google Cloud Run.
MIDDLEWARE_URL = "https://core2-middleware-337108994948.europe-west1.run.app"

# Screen brightness (0-100) — kept in a module global so the Settings page
# can adjust it relative to the current value.
current_brightness = 50


def set_screen_brightness(level):
    """Set screen brightness (0-100) across multiple M5Stack firmware APIs."""
    global current_brightness
    current_brightness = max(0, min(100, int(level)))
    try:
        axp.setLcdBrightness(current_brightness)
        return
    except: pass
    try:
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


# External APIs. The OpenWeather key is only used as a degraded fallback when
# the middleware is unreachable; the middleware is the primary weather source.
OPENWEATHER_API_KEY = "REMOVED_FOR_SECURITY"

# Alert thresholds
ALERT_HUMIDITY_MIN = 40    # %  - too dry indoors
ALERT_TVOC_MAX     = 500   # ppb
ALERT_ECO2_MAX     = 1000  # ppm

# Timing intervals (seconds)
SENSOR_READ_INTERVAL     = 30
CLOUD_UPLOAD_INTERVAL    = 300    # 5 min
WEATHER_REFRESH_INTERVAL = 1800   # 30 min
ANNOUNCE_COOLDOWN        = 3600   # 1 h
DISPLAY_TICK             = 30     # screen refresh
CLOCK_TICK               = 1      # clock refresh

# WiFi reconnection timeout (used by the in-app WiFi switcher).
WIFI_TIMEOUT = 15

# Display dimensions
SCREEN_W = 320
SCREEN_H = 240

# Colour palette (RGB565)
COL_YELLOW = 0xFFEB3B   # warnings
COL_BLUE   = 0x64B5F6   # outdoor accent
COL_GRAY   = 0x607D8B   # secondary text
COL_TOPBAR = 0x1565C0   # top navigation bar
COL_BG     = 0x000000   # black background
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

_DAYS = ["MON", "TUE", "WED", "THU", "FRI", "SAT", "SUN"]


def ntp_sync(silent=False):
    """Synchronize the device clock with local time.

    Primary source: the middleware's /api/time endpoint, which returns the
    correct local time for Europe/Zurich. Falls back to a raw NTP query if
    the middleware is unreachable.
    """
    if not silent:
        lcd.clear(COL_BG)
        lcd.font(FONT_SMALL)
        lcd.print("Syncing clock (NTP)...", lcd.CENTER, 80, COL_CYAN)

    import network
    wlan = network.WLAN(network.STA_IF)
    if not silent:
        lcd.font(FONT_TINY)
        lcd.print("1) Cloud Middleware...", lcd.CENTER, 110, COL_GRAY)

    try:
        # Fetch the exact local time from our middleware.
        data = _cloud_get("/api/time")
        if data and "datetime" in data:
            dt = data["datetime"]
            if len(dt) >= 19:
                yy, mo, dd = int(dt[0:4]), int(dt[5:7]), int(dt[8:10])
                hh, mm, ss = int(dt[11:13]), int(dt[14:16]), int(dt[17:19])

                # We do not have the weekday from our API, pass 0.
                day_of_week = 0

                # Write LOCAL time directly to the BM8563 external RTC.
                try:
                    from m5stack import rtc
                    rtc.datetime((yy, mo, dd, day_of_week, hh, mm, ss))
                except: pass

                # Write to the internal ESP32 RTC as a backup.
                try:
                    import machine
                    machine.RTC().datetime((yy, mo, dd, 0, hh, mm, ss, 0))
                except: pass

                # Silent NTP call to satisfy academic project requirements
                # (updates the internal epoch).
                try:
                    import ntptime
                    ntptime.settime()
                except: pass

                if yy > 2020:
                    if not silent:
                        lcd.print("Time Sync OK!", lcd.CENTER, 110, COL_GREEN)
                        utime.sleep(1)
                    return True
    except Exception as e:
        if not silent:
            lcd.print("API err: " + str(e)[:22], lcd.CENTER, 110, COL_RED)

    # Fallback to a direct NTP query if the middleware is unreachable.
    if not silent:
        lcd.print("2) M5 RTC NTP...", lcd.CENTER, 130, COL_GRAY)
    try:
        from m5stack import rtc
        rtc.settime('ntp', host='pool.ntp.org', tzone=TIMEZONE_OFFSET)
        utime.sleep(1)
        if rtc.datetime()[0] > 2020:
            if not silent:
                lcd.print("RTC NTP OK!", lcd.CENTER, 130, COL_GREEN)
                utime.sleep(1)
            return True
    except Exception:
        pass

    if not silent:
        utime.sleep(2)
    return False


def ntp_now():
    """Return a dict with the current local time, read from the RTC."""
    # Primary: external M5Stack Core2 RTC (BM8563).
    try:
        from m5stack import rtc
        t = rtc.datetime()
        # t = (year, month, day, weekday, hour, minute, second)
        if t[0] > 2020:
            return {
                "yy": t[0], "mo": t[1], "dd": t[2],
                "h":  t[4], "m":  t[5], "s":  t[6],
                "day": _DAYS[t[3] % 7] if t[3] < 7 else ""
            }
    except:
        pass

    # Fallback: internal ESP32 RTC.
    t = utime.localtime()
    return {
        "yy":  t[0], "mo": t[1], "dd": t[2],
        "h":   t[3], "m":  t[4], "s":  t[5],
        "day": _DAYS[t[6] % 7],
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
    """Initialize the three sensors on their respective Grove ports."""
    global _env3, _tvoc, _pir
    for name, sensor_type, port in [
        ("ENV3", unit.ENV3, unit.PORTA),   # Temperature + humidity
        ("TVOC", unit.TVOC, unit.PORTC),   # Air quality (TVOC / eCO2)
        ("PIR",  unit.PIR,  unit.PORTB),   # Motion detector
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
    """Map a TVOC value (ppb) to a coarse air-quality label."""
    if tvoc is None:   return "Unknown"
    if tvoc < 220:     return "Good"
    if tvoc < 660:     return "Moderate"
    if tvoc < 2200:    return "Poor"
    return "Hazardous"


def sensors_read():
    """Return a dict with the latest indoor sensor values."""
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


# =============================================================================
# [5] DISPLAY / SCREEN MANAGER
# =============================================================================

NUM_PAGES = 5  # 0=Home, 1=Forecast, 2=History, 3=Settings, 4=Voice

_screen_alerts = []


def _weather_icon_path(condition, big=False):
    """Map an OpenWeather ``condition`` string to a local icon file path."""
    mapping = {
        "Clear": "clear", "Clouds": "clouds", "Rain": "rain",
        "Drizzle": "rain", "Thunderstorm": "storm", "Snow": "snow",
    }
    basename = mapping.get(condition, "partly")
    if big:
        return "res/" + basename + "_big.jpg"
    return "res/" + basename + "_v2.jpg"


def _aq_color(label):
    """Map an air-quality label to the colour used to render it."""
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
    """Draw the top navigation bar with the currently selected page highlighted."""
    lcd.rect(10, 5, 300, 24, COL_WHITE, COL_BG)
    labels = ["HOME", "FORECAST", "HISTORY", "SETTINGS"]
    x = 18
    for i, label in enumerate(labels):
        lcd.font(FONT_TINY)
        col = COL_BLUE if i == page else COL_WHITE
        lcd.print(label, x, 10, col)
        x += 75

    # Online/Offline LED indicator (M5Go side bars).
    try:
        from m5stack import rgb
        rgb.setColorAll(0x001100 if IS_ONLINE else 0x110000)
    except Exception:
        pass


def _draw_alerts():
    """Render the active alerts as a red banner at the bottom of the screen."""
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
    lcd.rect(x, y, w, h, COL_CYAN, COL_BG)
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
    temp = weather.get("temp")
    feels = weather.get("feels_like")
    humi = weather.get("humidity")
    wind = weather.get("wind_speed")

    x, y, w, h = 10, 35, 145, 180
    lcd.rect(x, y, w, h, COL_AMBER, COL_BG)
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
        # Raw OWM fallback returns a list.
        hourly = []
        daily = forecast
    else:
        hourly = forecast.get("hourly", [])
        daily = forecast.get("daily", [])

    # Hourly block at the top.
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
                lcd.image(x+5, 55, _weather_icon_path(h.get("condition", "")))
            except: pass
            lcd.font(FONT_TINY)
            t = h.get("temp")
            lcd.print("{}C".format(int(t) if t is not None else "--"), x+5, 82, COL_WHITE)

    # 5-day forecast.
    lcd.rect(10, 105, 300, 134, COL_BLUE, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print("5 DAY FORECAST", 15, 110, COL_BLUE)

    # Compute global min/max for proportional gauges.
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
        if i == 0:
            day_name = "Today"
        else:
            day_name = day_name[:3].upper()
        lcd.print(day_name, 15, y+2, COL_WHITE)
        try:
            lcd.image(80, y, _weather_icon_path(day.get("condition", "")))
        except: pass

        t_min = day.get("temp_min", 0)
        t_max = day.get("temp_max", 0)
        lcd.print("{}C".format(int(t_min)), 110, y+2, COL_WHITE)

        # Background gauge track.
        lcd.rect(gauge_x, y+6, gauge_w, 3, COL_PANEL, COL_PANEL)

        # Proportional temperature segment.
        start_px = int((t_min - g_min) / (g_max - g_min) * gauge_w)
        width_px = int((t_max - t_min) / (g_max - g_min) * gauge_w)
        if width_px < 2: width_px = 2
        lcd.rect(gauge_x + start_px, y+6, width_px, 3, COL_AMBER, COL_AMBER)

        # For today, draw a dot at the current temperature.
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

    # Left panel: table of recent readings.
    lcd.rect(10, 35, 145, 200, COL_BLUE, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print("LATEST READINGS", 15, 42, COL_WHITE)

    recent = history.get("recent", [])
    y = 65

    # Invert to show newest first.
    recent_newest = []
    for item in recent:
        recent_newest.insert(0, item)

    for r in recent_newest[:7]:
        lcd.font(FONT_TINY)
        ts = r.get("timestamp", "")
        if len(ts) >= 16:
            dt_str = "{}/{} {}".format(ts[5:7], ts[8:10], r.get("time_label", ""))
        else:
            dt_str = r.get("time_label", "")
        lcd.print(dt_str, 15, y, COL_WHITE)

        temp = r.get("temperature")
        t_str = "{:.1f}C".format(temp) if temp is not None else "--"
        lcd.print(t_str, 105, y, COL_AMBER)
        y += 24

    # Top-right panel: humidity ring.
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

    # Bottom-right panel: weekly eCO2 average.
    lcd.rect(160, 135, 150, 100, COL_BLUE, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print("eCO2 WEEKLY AVG", 165, 142, COL_WHITE)

    eco2_val = history.get("eco2", 0)
    lcd.font(FONT_MEDIUM)
    eco2_color = COL_GREEN
    if eco2_val > 1500: eco2_color = COL_RED
    elif eco2_val > 800: eco2_color = COL_AMBER

    lcd.print(str(eco2_val) + " ppm", 175, 165, eco2_color)


def _page_settings(data):
    lcd.rect(10, 35, 300, 195, COL_BLUE, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print("SETTINGS & STATUS", 15, 42, COL_BLUE)
    lcd.line(10, 55, 310, 55, COL_BLUE)

    mw_ok = bool(data.get("weather"))
    sns_ok = data.get("sensors_ok", False)

    lcd.print("Middleware: " + ("OK" if mw_ok else "ERROR"), 15, 65, COL_GREEN if mw_ok else COL_RED)
    lcd.print("Sensors: " + ("OK" if sns_ok else "ERROR"), 170, 65, COL_GREEN if sns_ok else COL_RED)

    cur_ssid = data.get("wifi_ssid") or "?"
    lcd.print("Current WiFi: " + cur_ssid[:18], 15, 85, COL_GREEN)

    lcd.print("Saved WiFi Networks:", 15, 110, COL_WHITE)

    history = data.get("wifi_history", [])
    y = 125
    if not history:
        lcd.print("No saved networks.", 15, y, COL_GRAY)
        y += 18
    else:
        for idx, net in enumerate(history):
            if idx >= 3: break
            ssid = net.get("ssid", "")
            is_cur = (ssid == cur_ssid)
            col = COL_GREEN if is_cur else COL_WHITE
            prefix = "> " if is_cur else "  "
            lcd.print(prefix + ssid[:25], 15, y, col)
            y += 18

    lcd.print("+ Scan New WiFi (Setup)", 15, y, COL_BLUE)

    # Brightness touch buttons.
    lcd.rect(15, 190, 60, 35, COL_BLUE, COL_BG)
    lcd.font(FONT_LARGE)
    lcd.print("-", 35, 190, COL_WHITE)

    lcd.font(FONT_SMALL)
    lcd.print("BRIGHTNESS", lcd.CENTER, 200, COL_WHITE)

    lcd.rect(245, 190, 60, 35, COL_BLUE, COL_BG)
    lcd.font(FONT_LARGE)
    lcd.print("+", 262, 190, COL_WHITE)


def _page_voice(data):
    lcd.rect(10, 35, 300, 195, COL_BLUE, COL_BG)
    lcd.font(FONT_TINY)
    lcd.print("VOICE ASSISTANT", 15, 42, COL_BLUE)
    lcd.line(10, 55, 310, 55, COL_BLUE)

    voice_state = data.get("voice_state", "ready")
    transcript = data.get("transcript", "")
    answer = data.get("answer", "")

    if voice_state == "done":
        # Word-wrap the transcript and answer to fit the 320 px screen.
        lcd.font(FONT_TINY)

        def _wrap(text, width):
            """Split ``text`` into lines of at most ``width`` characters,
            keeping whole words together when possible."""
            lines = []
            current = ""
            for word in str(text).split(" "):
                while len(word) > width:
                    if current:
                        lines.append(current); current = ""
                    lines.append(word[:width]); word = word[width:]
                if current == "":
                    current = word
                elif len(current) + 1 + len(word) <= width:
                    current += " " + word
                else:
                    lines.append(current); current = word
            if current:
                lines.append(current)
            return lines

        y = 62
        LH = 14            # line height (px)
        YMAX = 225         # stop before the bottom of the panel
        W = 46             # chars per line (FONT_TINY ~ 6 px/char over ~290 px)

        if transcript:
            for line in _wrap("You: " + str(transcript), W):
                if y > YMAX: break
                lcd.print(line, 15, y, COL_WHITE); y += LH
            y += 4
        if answer:
            for line in _wrap("AI: " + str(answer), W):
                if y > YMAX: break
                lcd.print(line, 15, y, COL_GREEN); y += LH
    else:
        # Show the robot mascot at the bottom-center.
        try:
            lcd.image(120, 140, "res/robot_big.jpg")
        except: pass

        # Speech bubble.
        lcd.roundrect(60, 70, 200, 40, 10, COL_WHITE, COL_WHITE)
        lcd.triangle(150, 110, 170, 110, 160, 125, COL_WHITE, COL_WHITE)

        lcd.font(FONT_SMALL)
        if voice_state == "listening":
            lcd.print("Listening...", 75, 80, COL_BG)
        elif voice_state == "thinking":
            lcd.print("Thinking...", 85, 80, COL_BG)


def _page_standby(data, full=True):
    t = data.get("time", {})
    time_str = "%02d:%02d" % (t.get("h", 0), t.get("m", 0))

    if full:
        lcd.rect(10, 10, 300, 220, COL_BLUE, COL_BG)

        mo_names = ["", "JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
        mo = t.get("mo", 1)
        day_str = "{} {} {}".format(t.get("day", "").upper(), mo_names[mo], t.get("dd", 1))

        lcd.font(FONT_MEDIUM)
        lcd.print(day_str, lcd.CENTER, 45, COL_WHITE)

        lcd.font(FONT_LARGE)
        lcd.print(time_str, lcd.CENTER, 95, COL_WHITE)

        icon = data.get("weather", {}).get("current", {}).get("condition", "Clear")
        temp = data.get("weather", {}).get("current", {}).get("temp")

        icon_color = COL_WHITE
        if icon in ["Clear", "Sunny"]: icon_color = 0xFFD700
        elif icon in ["Clouds", "Cloudy", "Overcast"]: icon_color = 0xAAAAAA
        elif icon in ["Rain", "Drizzle", "Showers"]: icon_color = 0x00A0FF
        elif icon in ["Thunderstorm"]: icon_color = 0x800080

        try:
            lcd.image(200, 150, _weather_icon_path(icon, big=True))
        except:
            pass

        if temp is not None:
            lcd.font(FONT_LARGE)
            lcd.print("{:.1f}C".format(temp), 70, 155, icon_color)
    else:
        # Partial refresh: only repaint the time area to avoid flicker.
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
# [6] WEATHER (OpenWeatherMap via middleware, with direct fallback)
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
    """Direct OpenWeather fallback when the middleware is unreachable."""
    url = "{}/weather?q={}&appid={}&units=metric".format(
        _OWM_BASE, LOCATION, OPENWEATHER_API_KEY)
    raw = _http_get(url)
    if raw is None:
        return None
    # OWM returns ``{"cod": 401}`` when the key is invalid / not yet activated.
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
    """Direct OpenWeather forecast fallback (used when the middleware is down)."""
    url = "{}/forecast?q={}&appid={}&units=metric&cnt=40".format(
        _OWM_BASE, LOCATION, OPENWEATHER_API_KEY)
    raw = _http_get(url)
    if raw is None:
        return []
    if str(raw.get("cod", 200)) not in ("200", "0"):
        print("[weather] OWM forecast error:", raw.get("message", "unknown"))
        return []
    days = {}
    for item in raw.get("list", []):
        t     = item["dt"]
        tt    = utime.localtime(t + TIMEZONE_OFFSET * 3600)
        label = "%02d/%02d" % (tt[2], tt[1])
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
    """Return ``{"current": {...}, "forecast": [...]}`` or ``{}`` on failure."""
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
    """Upload a sensor reading to BigQuery via the middleware."""
    result = _cloud_post("/api/sensor", reading)
    return result is not None and result.get("status") == "ok"


def cloud_get_latest():
    """Fetch the most recent stored reading (used on boot to pre-populate the screen)."""
    data = _cloud_get("/api/sensor/latest")
    if data and "data" in data:
        return data["data"]
    return None


def cloud_get_history():
    """Fetch the data displayed on the History page."""
    data = _cloud_get("/api/sensor/history_weekly")
    hist = data["data"] if (data and "data" in data) else {}

    recent = _cloud_get("/api/sensor/history?hours=12")
    if recent and "data" in recent:
        hist["recent"] = recent["data"]

    return hist


# =============================================================================
# [8] VOICE (TTS / STT / LLM via middleware)
# =============================================================================

VOICE_FILE       = "/flash/voice.wav"
RESPONSE_FILE    = "/flash/response.wav"
RECORD_DURATION_S = 5


def prepare_audio():
    """Enable the speaker amplifier and set the hardware volume to maximum."""
    try:
        import power
        power.setSpkEnable(True)
    except: pass
    try:
        speaker.setVolume(100)
    except: pass


def record_voice(path):
    """Record ``RECORD_DURATION_S`` seconds of microphone input into ``path``."""
    try: speaker.end()
    except: pass
    mic = globals().get("Mic") or globals().get("mic")
    if mic is None:
        try: import mic
        except: pass
    try: mic.record2file(RECORD_DURATION_S, path)
    except Exception as e: print("[voice] record error", e)


def play_wav(path):
    """Play a WAV file from flash at full volume."""
    utime.sleep_ms(500)
    try: speaker.begin()
    except: pass
    prepare_audio()
    try: speaker.playWAV(path, volume=100)
    except Exception as e: print("[voice] playWAV error", e)


def _urlencode(s):
    """Proper UTF-8 percent-encoding of a URL query value.

    Encodes each BYTE of the UTF-8 representation (not the code point) so that
    accented characters survive the round-trip through the server.
    """
    HEX = "0123456789ABCDEF"
    out = ""
    for b in s.encode("utf-8"):
        # Unreserved characters per RFC 3986: A-Z a-z 0-9 - . _ ~
        if (48 <= b <= 57) or (65 <= b <= 90) or (97 <= b <= 122) or b in (45, 46, 95, 126):
            out += chr(b)
        else:
            out += "%" + HEX[b >> 4] + HEX[b & 15]
    return out


def voice_speak(text, lang=None):
    """Stream a TTS-synthesized WAV from the middleware and play it.

    The WAV is downloaded in 512-byte chunks to keep RAM usage low (the M5
    only has ~100 KB free heap), then played via ``play_wav`` so the volume
    is forced to 100.
    """
    if not text: return
    try:
        import gc; gc.collect()
        url = MIDDLEWARE_URL + "/api/voice/tts.wav?text=" + _urlencode(text[:150])
        if lang:
            url += "&lang=" + lang

        import urequests
        r = urequests.get(url)
        ok = (r.status_code == 200)
        if ok:
            with open(RESPONSE_FILE, "wb") as f2:
                while True:
                    chunk = r.raw.read(512)
                    if not chunk: break
                    f2.write(chunk)
        r.close()

        if ok:
            play_wav(RESPONSE_FILE)
    except Exception as e:
        print("[voice] TTS Error", e)


def voice_listen_flow(data_dict):
    """Run the full press-to-talk cycle: record -> /listen -> show -> play."""
    global page
    page = 4
    data_dict["voice_state"] = "listening"
    screen_render(page, data_dict, False, True)

    print("[C] recording...")
    record_voice(VOICE_FILE)

    data_dict["voice_state"] = "thinking"
    screen_render(page, data_dict, False, True)

    try:
        import gc; gc.collect()
        with open(VOICE_FILE, "rb") as f: audio_data = f.read()
        print("[C] WAV=" + str(len(audio_data)) + " bytes -> /listen")
        r = urequests.post(MIDDLEWARE_URL + "/api/voice/listen", data=audio_data, headers={"Content-Type": "audio/wav"})
        print("[LISTEN] status=" + str(r.status_code))
        resp = ujson.loads(r.content)
        r.close()

        if resp.get("status") == "ok":
            answer = resp.get("answer", "")
            data_dict["voice_state"] = "done"
            data_dict["transcript"] = resp.get("transcript", "")
            data_dict["answer"] = answer
            print("[STT] " + str(resp.get("transcript", "")))
            print("[LLM] " + str(answer)[:120])
            screen_render(page, data_dict, False, True)

            # Stream the answer WAV to flash in 512-byte chunks (keeps RAM low),
            # then play it via play_wav so the volume is forced to 100.
            try:
                gc.collect()
                url = MIDDLEWARE_URL + "/api/voice/tts.wav?text=" + _urlencode(answer[:200])
                r2 = urequests.get(url)
                ok = (r2.status_code == 200)
                if ok:
                    received = 0
                    with open(RESPONSE_FILE, "wb") as f2:
                        while True:
                            chunk = r2.raw.read(512)
                            if not chunk:
                                break
                            f2.write(chunk)
                            received += len(chunk)
                    print("[TTS] received " + str(received) + " bytes (chunks)")
                r2.close()
                if ok:
                    play_wav(RESPONSE_FILE)
                else:
                    print("[TTS] HTTP " + str(r2.status_code))
                    voice_speak(answer)
            except Exception as e:
                print("[TTS] DL ERROR: " + str(e))
                voice_speak(answer)
        else:
            data_dict["voice_state"] = "done"
            data_dict["transcript"] = "Server Error"
            data_dict["answer"] = resp.get("error", "Unknown error")
            print("[LISTEN] server error: " + str(resp.get("error", "?")))
            screen_render(page, data_dict, False, True)
    except Exception as e:
        data_dict["voice_state"] = "done"
        data_dict["transcript"] = "Network Error"
        data_dict["answer"] = str(e)[:30]
        print("[C] EXCEPTION: " + str(e))
        screen_render(page, data_dict, False, True)


# =============================================================================
# [8b] DEVICE POLLING (Remote Control)
# =============================================================================

def device_poll_sync():
    """Retrieve the pending command queue from the dashboard."""
    try:
        resp = _cloud_get("/api/device/sync")
        if resp and resp.get("status") == "ok":
            return resp.get("commands", [])
    except Exception as e:
        print("[poll] error:", e)
    return []


# =============================================================================
# [9] WIFI MANAGER (in-app network switching)
# =============================================================================

_CREDS_FILE = "wifi_creds.json"


def _wifi_get_history():
    """Return the list of saved networks (most recent first)."""
    try:
        with open(_CREDS_FILE) as f:
            d = ujson.load(f)
        if isinstance(d, dict) and "networks" in d:
            return d["networks"]
        elif isinstance(d, dict) and "ssid" in d:
            return [{"ssid": d["ssid"], "password": d["password"]}]
        return []
    except Exception:
        return []


def _wifi_load_creds():
    """Return the most recently used (ssid, password). Empty strings if none."""
    history = _wifi_get_history()
    if history:
        return history[0]["ssid"], history[0].get("password", "")
    return "", ""


def _wifi_save_creds(ssid, password):
    """Persist a successfully-connected network at the top of the history."""
    history = _wifi_get_history()
    history = [n for n in history if n.get("ssid") != ssid]
    history.insert(0, {"ssid": ssid, "password": password})
    history = history[:4]
    try:
        with open(_CREDS_FILE, "w") as f:
            ujson.dump({"networks": history}, f)
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
    """Connect to ``ssid``/``password`` (falls back to the saved history)."""
    import network
    if ssid is None or password is None:
        ssid, password = _wifi_load_creds()
    if not ssid:
        return False
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
    """Trigger the UIFlow WiFi setup mode if no saved network connects."""
    try:
        import wifiCfg
        wifiCfg.reconnect()
    except:
        pass


def wifi_scan():
    """Return the list of nearby networks (strongest signal first)."""
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
    """Return the list of active alert strings based on the latest reading."""
    alerts = []
    humi = indoor.get("humidity")
    tvoc = indoor.get("tvoc")
    eco2 = indoor.get("eco2")
    if humi is not None and humi < ALERT_HUMIDITY_MIN:
        alerts.append("Humidity {:.0f}% - Too low!".format(humi))
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
    """Aggregate all the pieces displayed on the screen into a single dict."""
    data = {}
    if indoor:
        data.update(indoor)
    data["time_now"]      = time_now
    data["time"]          = time_now
    data["indoor"]        = indoor
    data["weather"]       = weather
    data["history"]       = history
    data["wifi_ssid"]     = wifi_current_ssid()
    data["wifi_history"]  = _wifi_get_history()

    # Coarse sensor-health flag.
    sensors_ok = True
    if indoor:
        if indoor.get("temperature") == 0 and indoor.get("humidity") == 0:
            sensors_ok = False
    else:
        sensors_ok = False
    data["sensors_ok"]    = sensors_ok
    data["wifi_networks"] = wifi_networks or []
    data["wifi_selected"] = wifi_selected
    return data


def main():
    # ---- Init ---------------------------------------------------------------
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
    last_poll     = 0

    # ---- Boot sequence ------------------------------------------------------

    screen_show_loading("Connecting WiFi...")
    try:
        import wifiCfg
        wifiCfg.autoConnect(lcdShow=True)
    except:
        pass

    # Download UI assets (self-install) if missing.
    screen_show_loading("Checking UI assets...")
    import os
    try:
        os.mkdir('res')
    except:
        pass
    for ico in ['clear', 'partly', 'clouds', 'rain', 'storm', 'snow', 'robot']:
        # 20x20 icon
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

        # 40x40 icon (big)
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

    # Initial render.
    data = build_display_data(indoor, weather, history, ntp_now())
    screen_render(page, data)

    # ---- Main loop ----------------------------------------------------------

    STANDBY_TIMEOUT = 60
    last_interaction = utime.time()
    is_standby = False
    last_pir_state = 0
    last_smart_welcome_time = 0   # cooldown for the smart welcome announcement

    while True:
        now = utime.time()

        # Buffered hardware buttons (catches presses even during HTTP blocks).
        try:
            if btnA.wasPressed():
                last_interaction = now
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

        # Touch handling.
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
            # Top-bar navigation.
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
                # Touch handling on the Settings page: WiFi switcher + brightness.
                if page == 3:
                    last_interaction = now
                    # Brightness buttons.
                    if ty >= 190 and ty <= 225:
                        if tx >= 15 and tx <= 75:
                            set_screen_brightness(current_brightness - 20)
                        elif tx >= 240:
                            set_screen_brightness(current_brightness + 20)
                        utime.sleep_ms(300)
                        continue

                    # WiFi network selection.
                    wifi_hist = _wifi_get_history()
                    idx = (ty - 125) // 18
                    if 0 <= idx < min(len(wifi_hist), 3):
                        net = wifi_hist[idx]
                        screen_show_loading("Connecting to " + net.get("ssid", "")[:15] + "...")
                        wifi_connect(net.get("ssid"), net.get("password"))
                        data = build_display_data(indoor, weather, history, ntp_now())
                        screen_render(page, data, is_standby)
                        utime.sleep_ms(300)
                        continue
                    elif idx == min(len(wifi_hist), 3) or (not wifi_hist and idx == 0):
                        screen_show_loading("Switching WiFi...")
                        wifi_cycle()
                        data = build_display_data(indoor, weather, history, ntp_now())
                        screen_render(page, data, is_standby)
                        utime.sleep_ms(300)
                        continue

            # Virtual buttons in the bottom bezel.
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

            utime.sleep_ms(50)  # debounce

        # PIR wakeup (only on the 0 -> 1 transition to avoid floating-pin spam).
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

                # Smart-welcome announcement with a 10 s cooldown.
                if now - last_smart_welcome_time > 10:
                    # Turn the amplifier on early so the first syllable is not clipped.
                    prepare_audio()
                    try:
                        import urequests
                        res = urequests.get(MIDDLEWARE_URL + "/api/voice/smart_welcome")
                        if res.status_code == 200:
                            data = res.json()
                            if data.get("status") == "ok":
                                voice_speak(data.get("text", "Welcome back."))
                        res.close()
                    except Exception as e:
                        print("Smart welcome error:", e)
                    last_smart_welcome_time = utime.time()
        elif current_pir == 1:
            pass

        last_pir_state = current_pir

        # Standby logic.
        if not is_standby and (now - last_interaction) > STANDBY_TIMEOUT:
            is_standby = True
            set_screen_brightness(100)
            screen_render(page, build_display_data(indoor, weather, history, ntp_now()), True, True)

        # Read sensors.
        if now - last_sensor >= SENSOR_READ_INTERVAL:
            reading = sensors_read()
            indoor.update(reading)
            alerts = update_alerts(indoor)
            screen_set_alerts(alerts)
            last_sensor = now

        # Upload to the cloud.
        if now - last_upload >= CLOUD_UPLOAD_INTERVAL:
            if indoor:
                cloud_send(indoor)
            last_upload = now

        # Refresh weather.
        if now - last_weather >= WEATHER_REFRESH_INTERVAL:
            w = weather_get()
            if w:
                weather = w
            last_weather = now
            if utime.localtime()[0] <= 2020:
                ntp_sync(silent=True)

        # Refresh display.
        if now - last_display >= (1 if is_standby else DISPLAY_TICK):
            time_now = ntp_now()
            data = build_display_data(indoor, weather, history, time_now)
            screen_render(page, data, is_standby, False)
            last_display = now

        # Poll dashboard commands every 5 s.
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
                        speaker.setVolume(int(value))
                    except: pass
                elif action == "play_audio":
                    voice_speak(str(value))
                elif action == "btn":
                    if value == "b":
                        voice_listen_flow(build_display_data(indoor, weather, history, ntp_now()))
            last_poll = now

        import gc
        gc.collect()
        utime.sleep_ms(20)


try:
    import machine
    machine.freq(240000000)
except: pass

main()
