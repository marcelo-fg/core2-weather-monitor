# Core2 Weather Monitor

**Team**

- Noah Issah
- Marcelo Ferreira Gonçalves

---

## Project overview

Core2 Weather Monitor is an end-to-end indoor / outdoor weather station built
around an **M5Stack Core2** IoT device. The device measures the indoor
environment, pulls the outdoor weather, persists every reading in the cloud,
and exposes the result through two interfaces — an on-device LCD UI and a web
dashboard — both fed by the same Flask middleware. A voice assistant lets the
user talk to the device in natural language and get spoken answers grounded in
the live sensor and weather data.

The system follows a strict **three-tier architecture**:

```
+--------------------+        REST / JSON       +-------------------------+      Google APIs       +-----------------------+
|  Device tier       | -----------------------> |  Logic tier             | --------------------> |  Data & 3rd-party     |
|  M5Stack Core2     |   /api/sensor            |  Flask middleware on    |   BigQuery             |  Google Cloud         |
|  MicroPython +     |   /api/weather           |  Google Cloud Run        |   Speech-to-Text       |  + OpenWeatherMap     |
|  ENV III / TVOC /  |   /api/voice/*           |  (routes, services,     |   Text-to-Speech       |                       |
|  PIR / mic / HP    |   /api/time              |   tts package)          |   Gemini (LLM)         |                       |
+--------------------+ <----------------------- +-----------+-------------+ <-------------------- +-----------------------+
                                                            |
                                                            | REST / JSON
                                                            v
                                                +-------------------------+
                                                |  Presentation tier      |
                                                |  Streamlit dashboard    |
                                                |  on Google Cloud Run    |
                                                +-------------------------+
```

### End-to-end data flow

1. **Sensing on the device.** Every 30 seconds the Core2 reads the **ENV III**
   sensor (temperature, humidity), the **SGP30 TVOC unit** (TVOC and eCO2), and
   polls the **PIR motion sensor**. The firmware derives a coarse air-quality
   label (`Good` / `Moderate` / `Poor` / `Hazardous`) from the TVOC value.

2. **Boot-time enrichment.** On boot the device fetches the most recent reading
   stored in the cloud (`GET /api/sensor/latest`), the current weather and
   5-day forecast (`GET /api/weather`), the local time (`GET /api/time`,
   Europe/Zurich) and the weather icons (`GET /static/icons/*`) so that the UI
   is fully populated even before any new measurement is taken.

3. **Cloud upload.** Every 5 minutes the device POSTs its latest reading to
   `POST /api/sensor`. The middleware injects the current outdoor weather and
   writes the enriched row to **BigQuery** (`weather_monitor.sensor_readings`,
   partitioned by day on the `timestamp` field).

4. **Voice assistant.** When the user presses the **voice button** on the
   device:
   - The Core2 records 5 seconds of audio with its built-in microphone.
   - The WAV is POSTed to `POST /api/voice/listen`.
   - The middleware trims the loud initialization transient produced by the M5
     microphone, auto-levels the signal, then calls **Google Cloud Speech-to-Text**
     in English (`en-US`) with the `latest_short` enhanced model and a rich
     weather / indoor-air speech-context bias for higher accuracy.
   - It builds a context block from BigQuery (latest reading + 24-hour and
     7-day history summary) and OpenWeatherMap (current weather + 5-day
     forecast), prepends it to the user question,
     and asks **Google Gemini** through a multi-model fallback chain
     (`gemini-2.0-flash` → `gemini-2.5-flash-lite` → `gemini-2.0-flash-lite` →
     `gemini-2.5-flash` → `gemini-flash-latest`). Each model has its own free-
     tier quota and is put in cooldown for 90 s when it returns 429, so the
     assistant stays available throughout the day.
   - The route returns `{ "transcript": ..., "answer": ... }` to the device.
     The Core2 displays the text immediately and concurrently fetches the
     synthesized voice from `GET /api/voice/tts.wav?text=…`, which streams a
     WAV produced by **Google Cloud Text-to-Speech** (voice
     `en-US-Journey-F`, 24 kHz LINEAR16). The device writes the WAV to flash
     in 512-byte chunks to keep RAM usage low and plays it at full volume.

5. **Presence-triggered welcome.** When the PIR detects motion after the
   device has been idle, the firmware calls `GET /api/voice/smart_welcome`.
   The middleware returns a single English sentence — a fixed one when
   everything is in the normal range, or a Gemini-generated alert otherwise
   (extreme indoor temperature, poor air quality, incoming storm…). The
   device then plays the sentence through `/api/voice/tts.wav`.

6. **Dashboard.** The Streamlit dashboard calls the middleware's REST API to
   display real-time telemetry, 24-hour and weekly charts, weather, AI
   insights (`POST /api/voice/query`) and a text chat with the assistant
   (`POST /api/voice/stt_only` for browser audio + `POST /api/voice/query`).
   The Remote page also sends commands to the device via
   `POST /api/device/command`; the device drains the queue every 5 seconds
   with `GET /api/device/sync`.

### External services & APIs

| Service | Role |
| --- | --- |
| **OpenWeatherMap** | Provides the current outdoor weather and 5-day / 3-hour forecast for the configured location. Called from `middleware/services/weather_service.py` and cached in memory for 5 minutes. |
| **Google Cloud BigQuery** | Stores every sensor reading in `weather_monitor.sensor_readings`, partitioned by day on `timestamp`. Used by the dashboard and the device to retrieve historical data. |
| **Google Cloud Speech-to-Text** | Transcribes the user's voice on `/api/voice/listen`. English-only (`en-US`), `latest_short` enhanced model, an extensive weather and indoor-air speech-context bias, and automatic punctuation. The middleware also auto-levels quiet recordings before sending them for higher accuracy. |
| **Google Cloud Text-to-Speech** | Synthesizes the assistant's spoken answers and announcements. Default voice `en-US-Journey-F`, LINEAR16 WAV at 24 kHz. Output is cached on disk (`/tmp/tts_cache` on Cloud Run) keyed by an MD5 hash of the cleaned text. |
| **Google Gemini** (via `google-generativeai`) | Generates natural-language answers grounded in the live context. The middleware tries a chain of models in order, applies a 15-second per-call timeout, and cools any model that returns 429 for 90 seconds. |
| **Google Cloud Run** (region `europe-west1`) | Hosts both the middleware (`core2-middleware`) and the dashboard (`core2-dashboard`) as autoscaling HTTPS services. |
| **Google Cloud Build** | Builds the container images automatically when `gcloud run deploy --source ...` is invoked. |
| **M5Stack UIFlow 1.x** | MicroPython runtime that executes `device/main_uiflow.py` on the Core2 and handles WiFi connection at boot. |

### The two user interfaces

- **On-device LCD UI** — Five touch-navigable pages plus a standby clock:
  - **Home** — INDOOR / OUTDOOR cards with current measurements.
  - **Forecast** — Next-hours strip + 5-day proportional gauges.
  - **History** — Recent readings table + weekly humidity ring + weekly eCO2 average.
  - **Settings** — Middleware status, sensor status, WiFi networks (selectable), brightness +/– touch buttons.
  - **Voice** — Press the bottom-center virtual button (or hardware button B) to talk; the page shows the transcript and the assistant's answer.

- **Streamlit dashboard** — Two pages:
  - **Home** — telemetry tiles, 24-hour temperature / humidity / air-quality
    charts, current weather, AI weather summary, air-pollution insight,
    delta-temperature insight (indoor vs outdoor).
  - **Remote** — visual replica of the M5 Core2 with clickable HOME /
    FORECAST / HISTORY / SETTINGS buttons, brightness and volume sliders, an
    AI text chat, and a device-status panel. Commands are dispatched to the
    device through the middleware queue.

---

## Repository structure

```
core2-weather-monitor/
├── README.md
├── .gitignore
├── device/
│   └── main_uiflow.py             ← M5Stack Core2 firmware (UIFlow 1.x, MicroPython)
├── middleware/
│   ├── Dockerfile                 ← Cloud Run image (Gunicorn, non-root user)
│   ├── .dockerignore
│   ├── .env.example               ← copy to .env for local development
│   ├── requirements.txt
│   ├── app.py                     ← Flask entrypoint, blueprint registration, /health
│   ├── config.py                  ← env-var loader (no hardcoded values)
│   ├── routes/
│   │   ├── sensor.py              ← /api/sensor*, /api/time
│   │   ├── voice.py               ← /api/voice/*, /api/device/sync, /api/device/command
│   │   └── weather.py             ← /api/weather*
│   ├── services/
│   │   ├── bigquery_service.py    ← BigQuery client + dataset/table bootstrap + 30 s cache
│   │   └── weather_service.py     ← OpenWeatherMap client + 5-minute TTL cache
│   ├── tts/
│   │   ├── announcements.py       ← pre-canned announcement templates + rate limiting
│   │   ├── cache.py               ← MD5-keyed on-disk WAV cache
│   │   ├── llm.py                 ← Gemini client (multi-model fallback + cooldown + timeout)
│   │   ├── service.py             ← Google Cloud TTS client (synthesis + cleaning)
│   │   └── stt.py                 ← Google Cloud STT client (header parse + transient trim + auto-level + speech-context bias)
│   └── static/
│       └── icons/                 ← weather icons served to the device
└── dashboard/
    ├── Dockerfile                 ← Cloud Run image (Streamlit, non-root user)
    ├── env-vars.yaml              ← MIDDLEWARE_URL for the deployed dashboard
    ├── requirements.txt
    ├── app.py                     ← Streamlit entrypoint (Home + Remote pages)
    ├── assets/
    │   └── bg.png
    └── services/
        └── api_client.py          ← HTTP client wrapping every middleware endpoint
```

The following are intentionally **not** in the repository (see `.gitignore`):
device WiFi credentials (`device/wifi_creds.json`), local credentials
(`device/config.py`, `*.env`, `application_default_credentials.json`,
`*-service-account*.json`), the runtime TTS audio cache
(`middleware/static/audio/`), virtualenvs, and dev-tool config (`.claude/`).

---

## Step-by-step deployment

### Prerequisites

- A Google Cloud project with billing enabled.
- The `gcloud` CLI installed and authenticated:
  `gcloud auth login` and `gcloud config set project <PROJECT_ID>`.
- An OpenWeatherMap API key (free tier is enough): https://openweathermap.org/api
- A Gemini API key from AI Studio: https://aistudio.google.com/apikey
- An M5Stack Core2 device flashed with UIFlow 1.15.x via M5Burner, plus the
  ENV III, TVOC and PIR Grove units.

### 1. Enable the Google Cloud APIs

```bash
gcloud services enable \
  run.googleapis.com \
  cloudbuild.googleapis.com \
  bigquery.googleapis.com \
  texttospeech.googleapis.com \
  speech.googleapis.com \
  generativelanguage.googleapis.com
```

### 2. Prepare BigQuery

The middleware auto-creates the `sensor_readings` table on first request, but
you must create the dataset and grant the Cloud Run runtime service account
permission to write to it:

```bash
bq --location=EU mk --dataset "${GOOGLE_CLOUD_PROJECT}:weather_monitor"

PROJECT_NUMBER=$(gcloud projects describe "$GOOGLE_CLOUD_PROJECT" --format='value(projectNumber)')
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

gcloud projects add-iam-policy-binding "$GOOGLE_CLOUD_PROJECT" \
  --member="serviceAccount:${RUNTIME_SA}" \
  --role="roles/bigquery.dataEditor"
```

### 3. Deploy the middleware

```bash
gcloud run deploy core2-middleware \
  --source ./middleware \
  --region europe-west1 \
  --allow-unauthenticated \
  --update-env-vars \
GOOGLE_CLOUD_PROJECT=$GOOGLE_CLOUD_PROJECT,\
BIGQUERY_DATASET=weather_monitor,\
BIGQUERY_TABLE=sensor_readings,\
OPENWEATHER_API_KEY=$OPENWEATHER_API_KEY,\
GEMINI_API_KEY=$GEMINI_API_KEY,\
GEMINI_MODEL=gemini-2.5-flash-lite,\
DEFAULT_LOCATION=Lausanne,CH,\
TIMEZONE_OFFSET=2,\
TTS_LANGUAGE_CODE=en-US,\
TTS_VOICE_NAME=en-US-Journey-F,\
TTS_SAMPLE_RATE_HZ=24000,\
STT_LANGUAGE_CODE=en-US,\
AUDIO_CACHE_DIR=/tmp/tts_cache
```

Note the URL printed at the end of the deploy — you will need it for the
dashboard and the device.

### 4. Deploy the dashboard

```bash
gcloud run deploy core2-dashboard \
  --source ./dashboard \
  --region europe-west1 \
  --allow-unauthenticated \
  --update-env-vars MIDDLEWARE_URL=<deployed-middleware-url>
```

### 5. Flash the M5Stack device

1. In `device/main_uiflow.py`, confirm that `MIDDLEWARE_URL` points to your
   deployed middleware and `LOCATION` matches your city.
2. Open https://flow.m5stack.com, switch to **Python mode**, and paste the
   entire content of `device/main_uiflow.py`.
3. Click **Run & Save**. The device will connect to WiFi (configured at
   M5Burner time), download its icon assets from the middleware, sync its
   clock and start showing the Home page.

### Local development (optional)

```bash
# Middleware
python3.11 -m venv .venv-middleware
.venv-middleware/bin/pip install -r middleware/requirements.txt
cp middleware/.env.example middleware/.env   # fill in real values
set -a && source middleware/.env && set +a
cd middleware && python app.py

# Dashboard
python3.11 -m venv .venv-dashboard
.venv-dashboard/bin/pip install -r dashboard/requirements.txt
MIDDLEWARE_URL=http://127.0.0.1:8080 \
  .venv-dashboard/bin/python -m streamlit run dashboard/app.py
```

---

## Team Contributions

We worked closely together throughout the project, and the boundaries between
our contributions were often blurry. We helped each other constantly — whether
it was debugging an issue, reviewing code, or rethinking an approach that
wasn't working. Many of the key decisions, especially around the three-tier
architecture and the API contracts between the device, middleware and
dashboard, were made jointly.

That said, we each naturally gravitated toward certain parts of the system:

| Contributor | Primary focus areas |
| --- | --- |
| **Marcelo Ferreira Gonçalves** | Streamlit dashboard, on-device LCD interface, overall user experience and visual design, BigQuery data layer. |
| **Noah Issah** | Flask middleware, Google Cloud infrastructure and deployment (Cloud Run, Cloud Build), voice assistant pipeline (STT → Gemini → TTS). |

In practice, both of us touched most parts of the codebase at some point, and
neither of us worked in complete isolation on any single feature.

---

## Demo video

[TO BE REPLACED WITH YOUR YOUTUBE LINK]
