# 🌦️ Cloud & Advanced Analytics: Core2 Weather Monitor

![Architecture](https://img.shields.io/badge/Architecture-3--Tier-blue.svg)
![Hardware](https://img.shields.io/badge/Hardware-M5Stack_Core2-orange.svg)
![Cloud](https://img.shields.io/badge/Cloud-Google_Cloud_Platform-4285F4.svg)
![Status](https://img.shields.io/badge/Status-Completed-success.svg)

A complete end-to-end IoT and Cloud project fulfilling the requirements for the **Cloud and Advanced Analytics assignment**. This project implements a smart indoor/outdoor weather station using an M5Stack Core2 device, a robust Google Cloud backend, and a modern Streamlit web dashboard.

---

## 👥 Équipe et Contributions

- **Marcelo Ferreira Gonçalves**
- **Noah Issah**

*(Détails des contributions à compléter)*

🎥 **Lien vidéo de présentation :** [À ajouter]

---

## 🏗️ Architecture (3-Tier)

The system strictly adheres to a 3-tier architecture:

1. **Hardware / Device Tier (M5Stack Core2)**
   - Single-file MicroPython implementation (`main_uiflow.py`).
   - Reads data from physical sensors: ENV III (Temp/Humidity), TVOC/eCO2, and PIR (Motion detection).
   - Local UI managed via standard M5Stack display libraries.
   - Synchronizes with the cloud via REST APIs over WiFi.

2. **Middleware / Logic Tier (Google Cloud Run + Flask)**
   - Acts as the central nervous system bridging the hardware and the cloud.
   - Proxies OpenWeatherMap API calls to prevent hardcoding keys on the device.
   - Interfaces with **Google Cloud Text-to-Speech (TTS)** and **Gemini 1.5 Flash (LLM)** to provide voice interactions and intelligent indoor climate analysis.
   - Securely receives and routes sensor telemetry to the database.

3. **Data & Presentation Tier (Google BigQuery & Streamlit)**
   - **BigQuery:** Highly scalable data warehouse storing partitioned historical sensor telemetry.
   - **Streamlit Dashboard (Cloud Run):** A responsive, web-based UI providing historical charts, real-time alerts, and an interactive AI assistant.

---

## 🚀 Features & Academic Requirements Met

- ✅ **> 1000 Lines of Code:** Modularized codebase spanning Python, MicroPython, and SQL schemas.
- ✅ **Secure Configuration:** No API keys are hardcoded in the repository (enforced via `.gitignore` and environment variables).
- ✅ **Cloud Storage:** Sensor data is successfully persisted in a Google BigQuery dataset.
- ✅ **API Integrations:** Seamless integration with OpenWeatherMap (Current + 5-day forecast).
- ✅ **Voice & AI Services:** Implementation of Google Cloud TTS for spoken announcements and Gemini for intelligent user Q&A.
- ✅ **Resilience:** The M5Stack device automatically retrieves its latest known state from BigQuery on boot and handles WiFi network changes gracefully.
- ✅ **Dual UI:** Local LCD display for the physical device + global Streamlit Dashboard for cloud-based monitoring.

---

## 📂 Project Structure

```bash
core2_project/
├── device/
│   ├── main_uiflow.py          # Core2 MicroPython firmware (UIFlow)
│   ├── config_template.py      # Template for device configuration
│   └── wifi_creds.json         # (Ignored) Local WiFi credentials
│
├── middleware/
│   ├── app.py                  # Flask entry point
│   ├── routes/                 # API controllers (Sensor, Weather, Voice)
│   ├── services/               # Integrations (BigQuery, OWM, TTS, Gemini)
│   ├── Dockerfile              # Container definition
│   └── requirements.txt        # Python dependencies
│
├── dashboard/
│   ├── app.py                  # Streamlit Web UI
│   ├── services/api_client.py  # Middleware HTTP client
│   ├── Dockerfile              # Container definition
│   └── requirements.txt        # Python dependencies
│
├── .env                        # (Ignored) Secrets and API Keys
└── .gitignore                  # Security boundaries
```

---

## ⚙️ Setup & Deployment

### 1. Google Cloud Setup
Enable the following APIs on your GCP project:
- Cloud Run API
- BigQuery API
- Cloud Text-to-Speech API
- Generative Language API (Gemini)
- Service Usage API & Cloud Build API

### 2. BigQuery Initialization
Create a dataset named `weather_monitor` and a table named `sensor_readings`. The middleware service account must have `BigQuery Data Editor` permissions.

### 3. Deploying Middleware & Dashboard
Both the Flask Middleware and Streamlit Dashboard are designed to be deployed via Google Cloud Run:

```bash
# Deploy Middleware
gcloud run deploy core2-middleware \
  --source ./middleware \
  --allow-unauthenticated \
  --env-vars-file ./middleware/env-vars.yaml

# Deploy Dashboard
gcloud run deploy core2-dashboard \
  --source ./dashboard \
  --allow-unauthenticated \
  --env-vars-file ./dashboard/env-vars.yaml
```

### 4. Flashing the M5Stack Device
1. Rename `device/config_template.py` to `device/config.py`.
2. Update the `MIDDLEWARE_URL` inside the code with your deployed Cloud Run URL.
3. Flash `main_uiflow.py` and `config.py` to your M5Stack Core2 using the UIFlow IDE.

---

## 🔐 Security Disclaimer
This project uses `.env` files and `config.py` to manage secrets. **Never commit these files to version control.** A `.gitignore` is properly configured to prevent accidental leakage of Google Cloud Service Accounts, Gemini API keys, or WiFi credentials.
