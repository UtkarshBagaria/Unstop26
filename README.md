# AirIntel — Urban Air Quality Intelligence Platform

**An AI-powered platform for geospatial pollution source attribution, machine-learning AQI forecasting, and evidence-based enforcement intelligence across Indian urban centers — with a hyperlocal focus on Delhi-NCR.**

---

## Executive Summary

AirIntel fuses monitoring-station data, traffic mobility, an industrial registry, and meteorology to move urban air-quality management from **reactive dashboarding** to **proactive, geospatially-attributed intervention intelligence**.

### Problem Addressed
- **1.67M premature deaths annually** from air pollution in India (Lancet Planetary Health)
- **Only 31% of monitored cities** have actionable multi-agency response protocols (CAG audit, 2024)
- The data exists; the **intelligence layer to act on it does not**

### What the platform delivers
- ✅ **Source attribution** — identifies the dominant pollutant per hotspot and maps it to a likely emission source with a confidence score
- ✅ **ML forecasting** — 24–72h hyperlocal AQI forecasts that **beat a persistence baseline by ~31% RMSE** on a time-based holdout
- ✅ **Enforcement prioritisation** — ranked, evidence-backed recommendations
- ✅ **Public-health advisories** — CPCB-category guidance for vulnerable groups
- ✅ **Multi-city comparison** — the five NCR cities with 24h trend direction
- ✅ **Live alerting** — a running ticker that fires when stations cross Very-Poor / Severe thresholds

---

## Key Capabilities

### 1. Machine-Learning AQI Forecasting (`src/air_intelligence.py`)
- **Model:** gradient-boosted trees (`HistGradientBoostingRegressor`, scikit-learn)
- **Features (13):** last-known AQI (lag), wind speed, humidity, temperature, visibility, PM2.5, PM10, a station month×hour climatology term, forecast horizon, and target-time calendar features (hour, month, day-of-week, is-weekend)
- **Direct multi-horizon design** — horizon is a feature, so one model forecasts the whole 6h→72h range
- **Honest evaluation** — a **time-based train/test split** (earliest 80% train, latest 20% test); the headline skill is measured at the 24h horizon and reported alongside the raw model vs. persistence RMSE
- **Trained once and cached**; automatically **falls back** to a seasonal-climatology model if scikit-learn is unavailable

### 2. Pollutant-Based Source Attribution
Normalises PM2.5 / PM10 / NO2 / SO2 / CO / O3 into comparable sub-indices, identifies the **dominant driver** per hotspot, and maps it to a real-world source (traffic, dust/construction, industry, biomass) with a **confidence score** derived from how far the lead pollutant separates from the rest.

### 3. Multi-Layer Data Fusion
- **National** daily AQI across 50 cities (`city_day.csv`)
- **Delhi-NCR** 6-hourly readings — **5 cities, 23 stations, 2020–2025**, full pollutant + weather breakdown (`delhi_ncr_aqi_dataset.csv`)
- **Traffic** congestion & speed by time-of-day (`delhi_traffic_features.csv`)
- **Industrial registry** — factories extracted from PDF and enriched with Delhi zone + category

### 4. Health, Weather & Comparative Intelligence
- **Health advisories** — colour-coded CPCB category, message, and protective action per hotspot
- **Weather dispersion** — wind/humidity/visibility → dispersion rating explaining pollutant accumulation
- **Multi-city NCR comparison** — current AQI, dominant pollutant, and rising/falling 24h trend

### 5. Interactive Geospatial Dashboard (`index.html`)
- **Dark glassmorphism UI** with sticky header and a **running alert ticker**
- **KPI cards** that recolour by severity (avg/peak AQI, forecast skill, dispersion, stations, factories)
- **Live Leaflet map** — AQI-coloured, size-scaled station markers; **click a marker to forecast that station**
- **Chart.js visualisations** — colour-segmented 72h forecast (with a "Now" anchor point), national trend, pollutant-mix doughnut, and city-comparison bars, all with rich hover tooltips
- **Forecast station selector** + **click-to-focus** from hotspots, source-attribution rows, and map markers
- **Date/time simulator** to replay any moment from 2020–2025

---

## Quick Start

### Prerequisites
- Python 3.10+
- ~1 GB free disk / RAM (model training is in-memory)
- Internet connection for the map tiles & chart CDN (graceful fallback if offline)
- *(Optional)* Ollama running `llama3.2` for a generative AI narrative

### Install & Run
```bash
# 1. Navigate to the project
cd Unstop26

# 2. Install dependencies
pip install pandas pypdf numpy scikit-learn

# 3. (Optional) start Ollama for the generative narrative
ollama run llama3.2

# 4. Start the server (trains & caches the forecast model on first run, ~15s)
python api/dashboard.py

# 5. Open the dashboard
#    http://127.0.0.1:8000
```

The dashboard opens on a varied demo date (**2023-09-28**) so the map shows a spread of AQI colours. Pick a winter date (e.g. **2023-11-08**) to see the pollution crisis and live alerts — those dates are genuinely Severe across the NCR in the data.

---

## Project Structure

```
Unstop26/
├── api/
│   └── dashboard.py                 # HTTP server: serves dashboard + JSON API
├── src/
│   ├── dashboard_generator.py       # Orchestration, caching, AI narrative
│   ├── air_intelligence.py          # ML forecaster, attribution, health, weather, comparison
│   ├── factory_locations.py         # Factory zone/category enrichment
│   └── traffic_pollution.py         # Time-based traffic ↔ pollution correlation
├── data/
│   ├── delhi_ncr_aqi_dataset.csv    # Delhi-NCR 6-hourly AQI + weather (2020–2025)
│   ├── city_day.csv                 # National daily AQI
│   ├── delhi_traffic_features.csv   # Traffic density & speed by period
│   ├── delhi_building_footprints.geojson
│   └── 07-list_of_registered_working_factories.pdf
├── public/
│   └── dashboard.json               # Cached analysis snapshot
├── tests/
│   └── test_dashboard_generator.py  # Regression tests
├── index.html                       # Interactive dashboard UI
├── DEPLOYMENT.md
└── README.md
```

---

## How It Works

```
Data Sources → Load & Cache → Analytics Layers → ML Forecast → JSON API → Interactive Dashboard
```

1. **Load & cache** — datasets, the factory PDF, and the traffic correlation are parsed once and memoised; the forecast model is trained once at startup.
2. **Analytics** — hotspot ranking, pollutant attribution, health advisories, weather dispersion, multi-city comparison, traffic correlation, and enforcement priorities.
3. **ML forecast** — the trained model projects the selected (or worst) station 72h ahead, anchored to its current reading.
4. **AI narrative** — Ollama (if running) writes a data-cited summary; otherwise a rich expert fallback is generated from the computed metrics.
5. **API + UI** — the browser renders the map, charts, KPIs, and interactive panels from a single JSON payload.

---

## API Reference

### `GET /api/dashboard`

**Query parameters**

| Parameter | Example | Description |
|-----------|---------|-------------|
| `selected_datetime` | `2023-09-28T09:00` | ISO moment to analyse (2020–2025). Optional; defaults to the latest reading. |
| `station` | `Wazirpur, Delhi` | Station to forecast. Optional; defaults to the worst hotspot. |

**Selected response fields**
```json
{
  "ai_summary": "…",
  "alert_ticker": ["▲ VERY POOR: … deploy inspectors …"],
  "avg_aqi": 92,
  "max_aqi": 147,
  "delhi_hotspots": [ { "station": "…", "city": "…", "aqi": 133 } ],
  "pollutant_attribution": [
    { "station": "…", "dominant_pollutant": "PM10",
      "primary_source": "Dust / Construction & Roads", "confidence": 0.72 }
  ],
  "pollutant_mix": { "labels": ["PM2.5","PM10","NO2","SO2","CO","O3"], "values": [34.1, …] },
  "aqi_forecast": [ { "offset_h": 0, "aqi": 133, "bucket": "Moderate", "is_now": true } ],
  "forecast_meta": {
    "method": "Gradient-boosted trees (lagged AQI + weather + calendar)",
    "model_rmse": 29.0, "persistence_rmse": 42.2, "improvement_pct": 31.2, "horizon_h": 24
  },
  "forecast_station": "Bawana, Delhi",
  "forecast_station_options": ["Anand Vihar, Delhi", "…"],
  "city_comparison": [ { "city": "Ghaziabad", "avg_aqi": 127, "trend": "rising" } ],
  "weather": { "wind_speed": 3.3, "dispersion": "Poor", "note": "…" },
  "overall_health": { "category": "Moderate", "color": "#f1c40f", "protective_action": "…" },
  "factory_by_zone": { "Central": [ { "name": "…", "category": "Industrial" } ] },
  "station_locations": [ { "station": "…", "latitude": 28.6, "longitude": 77.3, "aqi": 133 } ],
  "generated_at": "2026-07-19 09:00:00 IST"
}
```

**Examples**
```bash
curl "http://127.0.0.1:8000/api/dashboard?selected_datetime=2023-11-08T09:00"
curl "http://127.0.0.1:8000/api/dashboard?selected_datetime=2023-09-28T09:00&station=Wazirpur,%20Delhi"
```

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│                   Browser Dashboard (index.html)         │
│  Leaflet map · Chart.js · KPI cards · alert ticker       │
│  Interactivity: station selector, click-to-focus         │
└────────────────────────┬─────────────────────────────────┘
                         │ GET /api/dashboard?selected_datetime&station
┌────────────────────────▼─────────────────────────────────┐
│                REST API (api/dashboard.py)               │
└────────────────────────┬─────────────────────────────────┘
                         │ build_summary()  (cached datasets + model)
┌────────────────────────▼─────────────────────────────────┐
│          Orchestration (src/dashboard_generator.py)      │
│  hotspots · enforcement · AI narrative · caching         │
└───────┬───────────────────────────────────┬──────────────┘
        │                                   │
┌───────▼───────────────┐        ┌──────────▼───────────────┐
│ air_intelligence.py   │        │ factory_locations.py     │
│ • ML forecaster       │        │ traffic_pollution.py     │
│ • source attribution  │        │ • zone/category mapping  │
│ • health / weather    │        │ • time-period correlation│
│ • city comparison     │        │                          │
└───────────────────────┘        └──────────────────────────┘
```

---

## Testing
```bash
python -m pytest tests/ -v
# test_build_summary_returns_expected_keys ....... PASSED
# test_build_summary_accepts_selected_datetime ... PASSED
```

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| **Backend** | Python 3.10, pandas, numpy, pypdf |
| **ML** | scikit-learn (`HistGradientBoostingRegressor`) |
| **API** | `http.server` (standard library) |
| **Frontend** | HTML5, CSS3, JavaScript (ES6) |
| **Mapping** | Leaflet.js (CARTO dark tiles) |
| **Charts** | Chart.js 4 |
| **AI narrative** | Ollama (llama3.2) — optional, with expert fallback |

---

## Performance

| Metric | Value |
|--------|-------|
| Forecast model training (once, at startup) | ~15 s |
| Cached request (analysis + forecast) | ~2 s |
| 24h forecast skill vs persistence | **~31% lower RMSE** (time-split holdout) |
| Dashboard render | <1 s |

---

## Limitations & Future Work

### Current Scope
- Demo data (historical 2020-01 snapshot, not real-time)
- Single-city focus (Delhi-NCR) with optional national comparison
- Manual factory category mapping (rule-based, not ML-trained)

### Enhancements
- [ ] Real-time CAAQMS data feed integration
- [ ] Multi-city instance deployment with federation
- [ ] Satellite imagery integration (Sentinel, MODIS)
- [ ] Atmospheric dispersion modeling (CALPUFF, WRF)
- [ ] Predictive ML models for 24-72h AQI forecast
- [ ] Mobile app with location-aware health advisories
- [ ] Enforcement audit trail & compliance tracking
- [ ] Public API for third-party integrations

---

## Key Insights (From Data)

**National Trends (2020-01 sample):**
- Ahmedabad averaged AQI 452 (Severe)
- Delhi averaged AQI 259 (Very Poor)
- Top 8 polluted cities span Tier 1 & Tier 2 urban centers

**Delhi-NCR Hotspots:**
- Anand Vihar shows peak pollution (AQI 500+)
- Evening traffic peak (17:00-21:00) correlates with highest AQI
- Industrial zones (Central, East) contribute significant factory-linked emissions

**Traffic-Pollution Correlation:**
- Night period (21:00-05:00) shows highest AQI despite lower traffic
- Morning rush (06:00-12:00) shows moderate correlation
- Afternoon stable conditions suggest meteorological factors dominate

---

## Datasets

1. [Delhi Weather and AQI](https://www.kaggle.com/datasets/vishardmehta/delhi-pollution-aqi-dataset)
2. [India AQI](https://www.kaggle.com/datasets/rohanrao/air-quality-data-in-india)
3. [Delhi Traffic](https://www.kaggle.com/datasets/vishardmehta/delhi-traffic-travel-time-prediction-dataset)
4. [Delhi Building Geo-Data](https://www.kaggle.com/datasets/sunnysharma432/delhi-building-footprints)
5. [Delhi Factory Names](https://www.kaggle.com/datasets/tanmayikona/delhi-factories)

---

## Contributing

For questions, bug reports, or enhancements:
1. Check [DEPLOYMENT.md](DEPLOYMENT.md) troubleshooting section
2. Review code comments in [src/dashboard_generator.py](src/dashboard_generator.py)
3. Run tests to validate changes: `pytest tests/`

---

## License
Developed for the Unstop Hackathon 2026 (Theme: Smart Cities & Environmental Intelligence).

---

## Judges' Quick Links
🚀 **Run:** `python api/dashboard.py` → http://127.0.0.1:8000
🧪 **Tests:** `pytest tests/ -v`
📋 **Deployment:** see [DEPLOYMENT.md](DEPLOYMENT.md)
