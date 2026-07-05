# Urban Air Quality Intelligence Platform - Deployment Guide

## Quick Start

### Prerequisites
- Python 3.10+
- pip package manager
- Windows/Linux/macOS

### Installation

1. **Navigate to project directory**
   ```bash
   cd d:\Hackathon26\Unstop26
   ```

2. **Install dependencies**
   ```bash
   pip install pandas pypdf numpy
   ```

3. **Prepare data files**
   Ensure these files exist in the `data/` directory:
   - `delhi_ncr_aqi_dataset.csv` - Delhi-NCR hourly AQI data
   - `city_day.csv` - National daily AQI data
   - `delhi_traffic_features.csv` - Delhi traffic data
   - `07-list_of_registered_working_factories.pdf` - Factory registry

4. **(Optional) Start Ollama local LLM**
   ```bash
   # Download and run Ollama with llama3.2 model
   ollama run llama3.2
   ```
   Server should run on `http://127.0.0.1:11434/api/generate`

### Running the Platform

**Start the dashboard server:**
```bash
python api/dashboard.py
```

**Access the dashboard:**
Open browser to: `http://127.0.0.1:8000`

The dashboard will:
- Load all national and Delhi-NCR datasets
- Parse factory locations from PDF
- Generate AI insights via Ollama (or fallback summary)
- Display interactive map, hotspots, and correlations

### File Structure
```
Unstop26/
├── api/
│   └── dashboard.py          # HTTP server (port 8000)
├── src/
│   ├── dashboard_generator.py # Core analysis engine
│   ├── factory_locations.py   # Zone/category mapping
│   └── traffic_pollution.py   # Traffic correlation
├── data/
│   ├── delhi_ncr_aqi_dataset.csv
│   ├── city_day.csv
│   ├── delhi_traffic_features.csv
│   └── 07-list_of_registered_working_factories.pdf
├── public/
│   └── dashboard.json         # Generated analysis snapshot
├── tests/
│   └── test_dashboard_generator.py
├── index.html                 # Interactive dashboard UI
└── README.md
```

### Running Tests
```bash
python -m pytest tests/ -v
```

### Using the Dashboard

1. **Select Date/Time**: Use the datetime picker to simulate historical analysis
2. **AI Summary**: Read the top executive summary for key insights
3. **Click Drill-Downs**: Expand sections to see detailed data (India cities, Delhi hotspots, traffic periods, factories)
4. **View Map**: Click "View Hotspots Map" to see geospatial distribution
5. **Export Data**: JSON is available at `http://127.0.0.1:8000/api/dashboard?selected_datetime=...`

### Customization

**Modify Ollama prompt** in `src/dashboard_generator.py`, function `build_summary()`:
- Edit `ai_prompt` variable (line ~200) to change analysis focus

**Add more data sources** in `src/dashboard_generator.py`:
- Add load functions and merge into `build_summary()`

**Change map bounds/zoom** in `index.html`:
- Edit Leaflet map initialization around line 500

### Performance Notes
- First run processes 8,739 factory entries from PDF (~2-3 seconds)
- Ollama inference: ~4-8 seconds per prompt
- Full dashboard generation: ~5-10 seconds

### Troubleshooting

**"No data" in tabs:**
- Check that data files exist in `data/` directory
- Verify CSV encoding is UTF-8
- Run tests: `pytest tests/test_dashboard_generator.py`

**Ollama timeout:**
- Install Ollama and pull `llama3.2` model
- Or disable Ollama; platform uses fallback summary

**Port already in use:**
- Change port in `api/dashboard.py` line 48: `HTTPServer(('127.0.0.1', XXXX), Handler)`

**PDF parsing errors:**
- Try regenerating factory list: `python src/dashboard_generator.py`
- Check PDF is readable and has text layer

### Architecture

```
┌─────────────────────────────────────────┐
│   Browser (index.html)                  │
│  ┌──────────────┐ ┌──────────────┐     │
│  │ AI Summary   │ │ Map View     │     │
│  │ Hotspots     │ │ Drill-downs  │     │
│  │ Drill-downs  │ │ Time Series  │     │
│  └──────────────┘ └──────────────┘     │
└─────────────────────────────────────────┘
         ↓ HTTP GET /api/dashboard
┌─────────────────────────────────────────┐
│   API Server (api/dashboard.py)         │
└─────────────────────────────────────────┘
         ↓ build_summary()
┌─────────────────────────────────────────┐
│   Analysis Engine                       │
│  ┌──────────────────────────────────┐   │
│  │ Load Datasets (pandas)           │   │
│  │ ├─ Delhi AQI hourly             │   │
│  │ ├─ National AQI daily           │   │
│  │ └─ Traffic data                 │   │
│  └──────────────────────────────────┘   │
│  ┌──────────────────────────────────┐   │
│  │ Compute Metrics                  │   │
│  │ ├─ Hotspots (by station)        │   │
│  │ ├─ Factory zones (enriched)     │   │
│  │ ├─ Traffic correlation          │   │
│  │ └─ Source attribution           │   │
│  └──────────────────────────────────┘   │
│  ┌──────────────────────────────────┐   │
│  │ AI Narrative (Ollama)            │   │
│  │ └─ llama3.2 model               │   │
│  └──────────────────────────────────┘   │
└─────────────────────────────────────────┘
         ↓ JSON Response
┌─────────────────────────────────────────┐
│  Data Output                            │
│  ├─ ai_summary (detailed narrative)    │
│  ├─ delhi_hotspots (8 top stations)    │
│  ├─ factory_by_zone (zone→factories)   │
│  ├─ traffic_correlation (by period)    │
│  ├─ source_attribution (priority list) │
│  └─ station_locations (lat/lng)        │
└─────────────────────────────────────────┘
```

### Contact & Support
For questions or issues, refer to project documentation in `README.md` and source code comments.
