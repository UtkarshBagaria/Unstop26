# AirIntel — Deployment Guide

## Prerequisites
- Python 3.10+
- pip
- Windows / Linux / macOS
- Internet access for map tiles (Leaflet/CARTO) and Chart.js CDN — the UI degrades gracefully offline
- *(Optional)* Ollama running `llama3.2` for the generative AI narrative

## Installation

1. **Navigate to the project directory**
   ```bash
   cd Unstop26
   ```

2. **Install dependencies**
   ```bash
   pip install pandas pypdf numpy scikit-learn
   ```
   > `scikit-learn` powers the ML forecaster. If it is not installed, the platform automatically falls back to a statistical seasonal-climatology model.

3. **Verify the data files** exist in `data/`:
   - `delhi_ncr_aqi_dataset.csv` — Delhi-NCR 6-hourly AQI + weather (2020–2025, 5 cities, 23 stations)
   - `city_day.csv` — national daily AQI
   - `delhi_traffic_features.csv` — traffic density & speed by period
   - `07-list_of_registered_working_factories.pdf` — factory registry
   - `delhi_building_footprints.geojson` — (large, optional; not loaded at runtime)

4. **(Optional) Start Ollama**
   ```bash
   ollama run llama3.2
   ```
   Expected endpoint: `http://127.0.0.1:11434/api/generate`. Without it, a rich expert fallback narrative is generated from the computed metrics.

## Running the Platform

```bash
python api/dashboard.py
```

Open: **http://127.0.0.1:8000**

On the **first run** the server:
- Loads and caches the datasets and the factory registry (parsed from PDF)
- **Trains and caches the gradient-boosted forecast model (~15 s)**
- Writes a snapshot to `public/dashboard.json`

Subsequent requests are served from cache in ~2 s.

> The dashboard opens on a varied demo date (**2023-09-28**) so the map shows a spread of AQI colours. Winter dates (e.g. **2023-11-08**) are genuinely Severe across the NCR in the data — use them to demo the crisis view and live alerts.

## File Structure
```
Unstop26/
├── api/
│   └── dashboard.py           # HTTP server (port 8000), parses selected_datetime + station
├── src/
│   ├── dashboard_generator.py # Orchestration, caching, AI narrative
│   ├── air_intelligence.py    # ML forecaster, attribution, health, weather, comparison
│   ├── factory_locations.py   # Zone/category enrichment
│   └── traffic_pollution.py   # Traffic ↔ pollution correlation
├── data/                      # Datasets (see above)
├── public/
│   └── dashboard.json         # Cached analysis snapshot
├── tests/
│   └── test_dashboard_generator.py
├── index.html                 # Interactive dashboard UI
├── README.md
└── DEPLOYMENT.md
```

## Running Tests
```bash
python -m pytest tests/ -v
```

## Using the Dashboard
1. **Select date/time** in the header and click **Run Analysis** to replay any moment (2020–2025).
2. **Read the Executive AI Summary** for a data-cited narrative.
3. **Explore the map** — click any station marker (or a hotspot / source-attribution row) to **forecast that station**; the map flies to it.
4. **Switch forecast stations** via the dropdown in the forecast card.
5. **Hover charts** for exact values; the forecast tooltip shows the timestamp and AQI category.
6. **Export JSON** at `http://127.0.0.1:8000/api/dashboard?selected_datetime=...&station=...`

## API
`GET /api/dashboard`

| Parameter | Example | Description |
|-----------|---------|-------------|
| `selected_datetime` | `2023-09-28T09:00` | Moment to analyse (optional) |
| `station` | `Wazirpur, Delhi` | Station to forecast (optional; defaults to worst hotspot) |

## Customization

**Forecast model** — `src/air_intelligence.py`, `train_forecast_model()`:
- Tune `max_samples`, or the `HistGradientBoostingRegressor` hyperparameters (`max_depth`, `learning_rate`, `max_iter`).
- Adjust the feature set in `FORECAST_FEATURES`.

**AI narrative** — `src/dashboard_generator.py`, `build_summary()`:
- Edit the `ai_prompt` string, or the expert fallback below it.

**Alert thresholds** — `build_summary()` builds `alert_ticker` from Very-Poor (≥300) and Severe (≥400) stations; edit those cut-offs.

**Map view** — `index.html`, `renderMap()`:
- Change the initial `setView([28.61, 77.20], 10)` centre/zoom or the tile layer.

**Caching** — `src/dashboard_generator.py` uses a module-level `_CACHE`. Restart the server to invalidate (e.g. after swapping a dataset).

## Performance
| Metric | Value |
|--------|-------|
| Forecast model training (once, at startup) | ~15 s |
| Cached request (analysis + forecast) | ~2 s |
| 24h forecast skill vs persistence | ~31% lower RMSE (time-split holdout) |
| Dashboard render | <1 s |

## Troubleshooting

**Slow first request / startup**
- Expected — the forecast model trains once (~15 s) then caches. Later requests are fast.

**Forecast shows "statistical fallback" instead of gradient boosting**
- `scikit-learn` is not installed: `pip install scikit-learn`, then restart.

**Map or charts blank**
- Offline / CDN blocked. The map and charts load Leaflet & Chart.js from CDNs; connect to the internet or self-host those assets. Panels show a graceful fallback message.

**"No data" in a panel**
- Confirm the `data/` files exist and are UTF-8. Run `pytest tests/ -v`.

**Ollama timeout / no AI narrative**
- Optional feature. Install Ollama and pull `llama3.2`, or ignore — the expert fallback is used automatically.

**Port already in use**
- Edit the port in `api/dashboard.py`: `HTTPServer(('127.0.0.1', 8000), Handler)`.

**PDF parsing issues**
- The factory list is parsed from the registry PDF (capped for the prototype). Regenerate with `python src/dashboard_generator.py`; ensure the PDF has a text layer.

## Architecture
```
┌──────────────────────────────────────────────┐
│  Browser (index.html)                        │
│  Leaflet map · Chart.js · KPI cards · ticker │
│  station selector · click-to-focus           │
└───────────────┬──────────────────────────────┘
                │ GET /api/dashboard?selected_datetime&station
┌───────────────▼──────────────────────────────┐
│  API server (api/dashboard.py)               │
└───────────────┬──────────────────────────────┘
                │ build_summary()  (cached)
┌───────────────▼──────────────────────────────┐
│  Orchestration (dashboard_generator.py)      │
│  hotspots · enforcement · AI narrative       │
├───────────────┬───────────────┬──────────────┤
│ air_intelligence.py           │ factory_locations.py │
│ • ML forecaster (GBT)         │ traffic_pollution.py │
│ • pollutant attribution       │ • zone/category      │
│ • health / weather / cities   │ • period correlation │
└───────────────────────────────┴──────────────────────┘
                │ JSON
┌───────────────▼──────────────────────────────┐
│  Output: ai_summary, alert_ticker,           │
│  aqi_forecast + forecast_meta,               │
│  pollutant_attribution, pollutant_mix,       │
│  city_comparison, weather, health,           │
│  delhi_hotspots, factory_by_zone,            │
│  station_locations, KPIs                     │
└──────────────────────────────────────────────┘
```

## Support
See `README.md` and inline source comments for details.
