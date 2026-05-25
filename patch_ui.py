import re

with open('device/main_uiflow.py.bak', 'r') as f:
    orig = f.read()

# Extract parts we keep
parts = re.split(r'# =============================================================================\n# \[5\] DISPLAY / SCREEN MANAGER\n# =============================================================================', orig)
part1 = parts[0]
parts2 = re.split(r'# =============================================================================\n# \[6\] WEATHER \(OpenWeatherMap\)\n# =============================================================================', parts[1])
part3 = parts2[1]
parts3 = re.split(r'# =============================================================================\n# \[11\] MAIN LOOP\n# =============================================================================', part3)
part4 = parts3[0]

# --- NEW SECTION 5 ---
new_section_5 = """
NUM_PAGES = 4  # 0=Home, 1=Forecast, 2=History, 3=Settings

_screen_alerts = []

def _weather_icon_path(condition):
    mapping = {
        "Clear": "clear.jpg", "Clouds": "clouds.jpg", "Rain": "rain.jpg",
        "Drizzle": "rain.jpg", "Thunderstorm": "storm.jpg", "Snow": "snow.jpg",
    }
    return "res/" + mapping.get(condition, "partly.jpg")

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
    # Dessin de la Top Bar type Pilule avec les 4 onglets
    lcd.rect(10, 5, 300, 24, COL_PANEL, COL_WHITE) # Contour blanc, fond panel
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

def _draw_alerts():
    if not _screen_alerts:
        return
    msg = " | ".join(_screen_alerts)
    lcd.rect(0, 222, 320, 18, COL_RED, COL_RED)
    lcd.font(FONT_TINY)
    lcd.print(msg[:52], 4, 225, COL_WHITE)

def _page_home(data, primary_card):
    # primary_card peut être "indoor" ou "outdoor"
    
    # 1. Dessiner la carte en arrière plan (plus petite, couleurs assombries)
    if primary_card == "indoor":
        _draw_outdoor_card(data, bg=True)
        _draw_indoor_card(data, bg=False)
    else:
        _draw_indoor_card(data, bg=True)
        _draw_outdoor_card(data, bg=False)
        
    _draw_alerts()


def _draw_indoor_card(data, bg=False):
    # Si background: dessine à droite, plus bas, plus petit (illusion)
    # Si foreground: dessine à gauche, plus grand
    
    temp = data.get("temperature")
    humi = data.get("humidity")
    eco2 = data.get("eco2")
    aq   = data.get("aq_label", "N/A")
    aq_col = _aq_color(aq)
    
    if bg:
        # Carte fond (droite)
        x, y, w, h = 170, 70, 140, 140
        lcd.rect(x, y, w, h, COL_BG, COL_CYAN) # Contour cyan, fond BG
        lcd.font(FONT_TINY)
        lcd.print("INDOOR", x+10, y+10, COL_CYAN)
        lcd.font(FONT_SMALL)
        lcd.print("{:.1f}C".format(temp) if temp is not None else "--", x+10, y+35, COL_GRAY)
        lcd.print("{:.0f}% hum".format(humi) if humi is not None else "--%", x+10, y+65, COL_GRAY)
        lcd.print("{} ppm CO2".format(eco2) if eco2 is not None else "-- ppm", x+10, y+95, COL_GRAY)
        lcd.print(aq, x+10, y+120, COL_GRAY)
    else:
        # Carte avant (gauche)
        x, y, w, h = 10, 45, 175, 170
        lcd.rect(x, y, w, h, COL_PANEL, COL_CYAN) # Contour cyan, fond PANEL
        lcd.font(FONT_SMALL)
        lcd.print("INDOOR", x+15, y+15, COL_CYAN)
        lcd.font(FONT_LARGE)
        lcd.print("{:.1f}C".format(temp) if temp is not None else "--C", x+15, y+45, COL_AMBER)
        lcd.font(FONT_SMALL)
        lcd.print("{:.0f}% humidity".format(humi) if humi is not None else "--%", x+15, y+95, COL_CYAN)
        lcd.print("{} ppm ECO2".format(eco2) if eco2 is not None else "-- ppm", x+15, y+120, COL_WHITE)
        lcd.print("{} air quality".format(aq), x+15, y+145, aq_col)


def _draw_outdoor_card(data, bg=False):
    weather = data.get("weather", {}).get("current", {})
    icon_path = _weather_icon_path(weather.get("condition", ""))
    temp = weather.get("temp")
    feels = weather.get("feels_like")
    humi = weather.get("humidity")
    wind = weather.get("wind_speed")
    
    if bg:
        # Carte fond (droite)
        x, y, w, h = 170, 70, 140, 140
        lcd.rect(x, y, w, h, COL_BG, COL_AMBER) # Contour orange
        lcd.font(FONT_TINY)
        lcd.print("OUTSIDE", x+10, y+10, COL_AMBER)
        lcd.font(FONT_SMALL)
        lcd.print("{:.0f}C".format(temp) if temp is not None else "--", x+10, y+35, COL_GRAY)
        lcd.print("feels {:.0f}C".format(feels) if feels is not None else "--", x+10, y+65, COL_GRAY)
        lcd.print("{:.0f}% hum".format(humi) if humi is not None else "--", x+10, y+95, COL_GRAY)
        lcd.print("{} m/s".format(wind) if wind is not None else "--", x+10, y+120, COL_GRAY)
        try:
            # Petite image (si supportée en 30x30, sinon on l'affiche juste)
            lcd.image(x+90, y+15, icon_path)
        except: pass
    else:
        # Carte avant (gauche)
        x, y, w, h = 10, 45, 175, 170
        lcd.rect(x, y, w, h, COL_PANEL, COL_AMBER) 
        lcd.font(FONT_SMALL)
        lcd.print("OUTSIDE", x+15, y+15, COL_AMBER)
        lcd.font(FONT_LARGE)
        lcd.print("{:.1f}C".format(temp) if temp is not None else "--C", x+15, y+45, COL_AMBER)
        lcd.font(FONT_SMALL)
        lcd.print("{:.0f}C feels like".format(feels) if feels is not None else "--", x+15, y+95, COL_AMBER)
        lcd.print("{:.0f}% humidity".format(humi) if humi is not None else "--", x+15, y+120, COL_AMBER)
        lcd.print("{} m/s wind".format(wind) if wind is not None else "--", x+15, y+145, COL_AMBER)
        try:
            lcd.image(x+105, y+45, icon_path)
        except: pass


def _page_forecast(data):
    forecast = data.get("weather", {}).get("forecast", [])
    
    # Bloc horaire en haut (simulé par le daily pour l'instant vu qu'OpenWeather donne du 3h)
    lcd.rect(10, 35, 300, 75, COL_PANEL, COL_BLUE)
    
    if not forecast:
        lcd.font(FONT_SMALL)
        lcd.print("No forecast", 100, 60, COL_GRAY)
        return
        
    for i, day in enumerate(forecast[:5]):
        x = 20 + (i * 55)
        lcd.font(FONT_TINY)
        lcd.print(day.get("day_name", "?")[:3].upper(), x, 40, COL_AMBER)
        try:
            lcd.image(x-5, 55, _weather_icon_path(day.get("condition", "")))
        except: pass
        lcd.font(FONT_TINY)
        t_max = day.get("temp_max")
        lcd.print("{}C".format(int(t_max) if t_max is not None else "--"), x, 95, COL_AMBER)
        
    # 5-DAY FORECAST 
    lcd.rect(10, 115, 300, 115, COL_PANEL, COL_BLUE)
    lcd.font(FONT_TINY)
    lcd.print("5-DAY FORECAST", 15, 122, COL_BLUE)
    lcd.line(10, 135, 310, 135, COL_BLUE)
    
    y = 140
    for i, day in enumerate(forecast[:5]):
        lcd.font(FONT_TINY)
        lcd.print(day.get("day_name", "?")[:3], 15, y+2, COL_WHITE)
        try:
            lcd.image(50, y-10, _weather_icon_path(day.get("condition", "")))
        except: pass
        
        t_min = day.get("temp_min", 0)
        t_max = day.get("temp_max", 0)
        lcd.print("{}C".format(int(t_min)), 90, y+2, COL_BLUE)
        
        # Jauge de température
        lcd.rect(120, y+5, 120, 4, COL_BG, COL_BG)
        # On simule un remplissage proportionnel 
        # (ex: 0C = x=120, 30C = x=240)
        fill_x = 120 + int(max(0, t_min)*3)
        fill_w = int(max(1, (t_max - t_min)*3))
        if fill_x + fill_w > 240: fill_w = 240 - fill_x
        lcd.rect(fill_x, y+5, fill_w, 4, COL_AMBER, COL_AMBER)
        
        lcd.print("{}C".format(int(t_max)), 250, y+2, COL_WHITE)
        
        y += 18
        if y > 210: break


def _page_history(data):
    history = data.get("history", [])
    lcd.rect(10, 35, 300, 195, COL_PANEL, COL_BLUE)
    lcd.font(FONT_TINY)
    lcd.print("INDOOR HISTORY", 15, 42, COL_BLUE)
    lcd.line(10, 55, 310, 55, COL_BLUE)
    
    if not history:
        lcd.print("No history data", 100, 100, COL_GRAY)
        return

    y = 65
    for row in history[:8]:
        ts   = row.get("time_label", "--:--")
        temp = row.get("temperature")
        humi = row.get("humidity")
        aq_col = _aq_color(row.get("aq_label", ""))
        lcd.font(FONT_TINY)
        lcd.print(ts, 15, y, COL_WHITE)
        lcd.print("{:.1f}C".format(temp) if temp is not None else "-- C", 80, y, COL_AMBER)
        lcd.print("{:.0f}%".format(humi) if humi is not None else "--%", 150, y, COL_CYAN)
        
        lcd.rect(210, y+2, 80, 8, COL_BG, COL_BG)
        val = min(100, max(0, row.get("tvoc", 0) / 10))
        lcd.rect(210, y+2, int(val*0.8), 8, aq_col, aq_col)
        
        y += 20
        if y > 210: break


def _page_settings(data):
    lcd.rect(10, 35, 300, 195, COL_PANEL, COL_BLUE)
    lcd.font(FONT_TINY)
    lcd.print("SETTINGS & STATUS", 15, 42, COL_BLUE)
    lcd.line(10, 55, 310, 55, COL_BLUE)
    
    lcd.print("WiFi Connected: " + data.get("wifi_ssid", "?"), 15, 65, COL_GREEN)
    lcd.print("Middleware: " + ("OK" if data.get("weather") else "ERROR"), 15, 95, COL_GREEN if data.get("weather") else COL_RED)
    
    lcd.print("[A] Volume-  [B] Mic Test  [C] Volume+", 25, 200, COL_GRAY)

def screen_render(page, data, primary_card="indoor"):
    lcd.clear(COL_BG)
    _draw_nav_bar(page)
    if page == 0:
        _page_home(data, primary_card)
    elif page == 1:
        _page_forecast(data)
    elif page == 2:
        _page_history(data)
    elif page == 3:
        _page_settings(data)

"""

# --- NEW SECTION 11 ---
new_section_11 = """
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
    ai_context = {
        "temperature": indoor.get("temperature"),
        "time": time_now,
        "outdoor_temp": weather.get("temp")
    }
    voice_listen_and_ask(ai_context)


def main():
    # ── Init ────────────────────────────────────────────────────────────────
    lcd.clear(COL_BG)
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
    for ico in ['clear.jpg', 'partly.jpg', 'clouds.jpg', 'rain.jpg', 'storm.jpg', 'snow.jpg']:
        path = 'res/' + ico
        try:
            os.stat(path)
        except OSError:
            screen_show_loading("Downloading " + ico)
            try:
                r = urequests.get(MIDDLEWARE_URL + "/static/icons/" + ico)
                with open(path, 'wb') as f:
                    f.write(r.content)
                r.close()
            except Exception as e:
                print("Failed to dl", ico, e)

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
    screen_render(page, data, home_primary)

    # ── Main loop ────────────────────────────────────────────────────────────
    import touch
    
    while True:
        now = utime.time()

        # Touch handling
        if touch.status():
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
                screen_render(page, data, home_primary)
                utime.sleep_ms(300)
            
            # Home page card swapping
            elif page == 0:
                # Clic sur la carte en arrière-plan à droite
                if tx > 170 and ty > 70 and ty < 210:
                    home_primary = "outdoor" if home_primary == "indoor" else "indoor"
                    data = build_display_data(indoor, weather, history, ntp_now())
                    screen_render(page, data, home_primary)
                    utime.sleep_ms(300)
                    
            utime.sleep_ms(50) # debounce

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
        if now - last_display >= DISPLAY_TICK:
            time_now = ntp_now()
            data = build_display_data(indoor, weather, history, time_now)
            screen_render(page, data, home_primary)
            last_display = now
            
        # Poll dashboard commands every 2 seconds
        if now - last_poll >= 2:
            cmds = device_poll_sync()
            for cmd in cmds:
                action = cmd.get("action")
                payload = cmd.get("payload", {})
                if action == "set_page":
                    p = payload.get("page", 0)
                    if 0 <= p < NUM_PAGES:
                        page = p
                        screen_render(page, build_display_data(indoor, weather, history, ntp_now()), home_primary)
                elif action == "brightness":
                    try:
                        import axp
                        axp.setLcdBrightness(payload.get("level", 50))
                    except: pass
                elif action == "volume":
                    try:
                        import machine
                        speaker.setVolume(payload.get("level", 50))
                    except: pass
                elif action == "play_audio":
                    voice_speak(payload.get("text", ""))
            last_poll = now

        utime.sleep_ms(20)

if __name__ == "__main__":
    try:
        import machine
        machine.freq(240000000)
    except: pass
    main()
"""

# Assemble final
final_code = part1 + "\\n# =============================================================================\\n# [5] DISPLAY / SCREEN MANAGER\\n# =============================================================================\\n" + new_section_5 + "\\n# =============================================================================\\n# [6] WEATHER (OpenWeatherMap)\\n# =============================================================================\\n" + part3 + "\\n" + new_section_11

with open('device/main_uiflow.py', 'w') as f:
    f.write(final_code)
print("Patch applied successfully.")
