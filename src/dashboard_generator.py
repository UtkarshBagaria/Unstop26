import json
from pathlib import Path
import urllib.request
import urllib.parse
import pandas as pd
from pypdf import PdfReader
import sys
import numpy as np

sys.path.insert(0, str(Path(__file__).parent))
from factory_locations import enrich_factory_locations, save_factory_locations
from traffic_pollution import analyze_traffic_pollution_correlation
from air_intelligence import (
    pollutant_attribution,
    pollutant_mix,
    forecast_station,
    forecast_accuracy,
    forecast_station_ml,
    train_forecast_model,
    diurnal_profile,
    health_advisory,
    city_comparison,
    weather_dispersion,
)


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        return super().default(obj)


ROOT = Path(__file__).resolve().parents[1]
DELHI_AQI_PATH = ROOT / 'data' / 'delhi_ncr_aqi_dataset.csv'
NATIONAL_AQI_PATH = ROOT / 'data' / 'city_day.csv'
TRAFFIC_PATH = ROOT / 'data' / 'delhi_traffic_features.csv'
FACTORY_PDF_PATH = ROOT / 'data' / '07-list_of_registered_working_factories.pdf'


def load_delhi_dataset(path: Path = DELHI_AQI_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['datetime', 'date'])
    df = df.sort_values(['city', 'station', 'datetime']).reset_index(drop=True)
    return df


def load_national_dataset(path: Path = NATIONAL_AQI_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['Date'])
    df = df.rename(columns={'Date': 'date', 'City': 'city', 'AQI': 'aqi', 'AQI_Bucket': 'aqi_bucket'})
    df = df[['city', 'date', 'aqi', 'aqi_bucket']].copy()
    df = df.dropna(subset=['aqi'])
    return df


def load_traffic_dataset(path: Path = TRAFFIC_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def load_factory_entries(path: Path = FACTORY_PDF_PATH) -> list[dict]:
    reader = PdfReader(str(path))
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = line.split()
        if len(parts) >= 3 and parts[0].isdigit() and parts[1].isdigit():
            entries.append({'sl_no': parts[0], 'fd_no': parts[1], 'name': ' '.join(parts[2:])})
    return entries[:80]


def _call_ollama(prompt: str, max_length: int = 1000) -> str:
    try:
        payload = json.dumps({'model': 'llama3.2', 'prompt': prompt, 'stream': False}).encode('utf-8')
        req = urllib.request.Request('http://127.0.0.1:11434/api/generate', data=payload, headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=8) as response:
            body = json.loads(response.read().decode('utf-8'))
            response_text = body.get('response', '').strip()
            return response_text[:max_length] if response_text else ''
    except Exception as e:
        return ''


# --- Lightweight caches so static datasets are parsed only once -----------
_CACHE: dict = {}


def _cached_delhi(path: Path = DELHI_AQI_PATH) -> pd.DataFrame:
    if 'delhi' not in _CACHE:
        _CACHE['delhi'] = load_delhi_dataset(path)
    return _CACHE['delhi']


def _cached_national() -> pd.DataFrame:
    if 'national' not in _CACHE:
        _CACHE['national'] = load_national_dataset()
    return _CACHE['national']


def _cached_factories() -> list[dict]:
    if 'factories' not in _CACHE:
        enriched = enrich_factory_locations(load_factory_entries())
        save_factory_locations(load_factory_entries())
        _CACHE['factories'] = enriched
    return _CACHE['factories']


def _cached_traffic_correlation() -> dict:
    if 'traffic_corr' not in _CACHE:
        _CACHE['traffic_corr'] = analyze_traffic_pollution_correlation()
    return _CACHE['traffic_corr']


def _cached_forecast_model(path: Path = DELHI_AQI_PATH):
    if 'forecast_model' not in _CACHE:
        _CACHE['forecast_model'] = train_forecast_model(_cached_delhi(path))
    return _CACHE['forecast_model']


def build_summary(path: Path = DELHI_AQI_PATH, selected_datetime: str | None = None,
                  forecast_station: str | None = None) -> dict:
    delhi_df = _cached_delhi(path)
    national_df = _cached_national()
    traffic_df = load_traffic_dataset()
    enriched_factories = _cached_factories()

    traffic_correlation = _cached_traffic_correlation()

    if selected_datetime:
        selected_ts = pd.to_datetime(selected_datetime)
        selected_df = delhi_df[delhi_df['datetime'] <= selected_ts].copy()
    else:
        selected_ts = delhi_df['datetime'].max()
        selected_df = delhi_df.copy()

    if selected_df.empty:
        selected_df = delhi_df.copy()

    latest = selected_df.sort_values('datetime').groupby('station').tail(1).copy()
    latest['aqi_bucket'] = pd.cut(
        latest['aqi'],
        bins=[0, 50, 100, 200, 300, 500],
        labels=['Good', 'Moderate', 'Poor', 'Very Poor', 'Severe'],
        include_lowest=True,
    )

    top_hotspots = (
        latest.groupby(['station', 'city'])['aqi']
        .mean()
        .reset_index()
        .sort_values('aqi', ascending=False)
        .head(8)
        .to_dict(orient='records')
    )

    station_hourly = selected_df.groupby(['station', 'hour']).agg(avg_aqi=('aqi', 'mean')).reset_index()
    peak_hour = station_hourly.sort_values(['station', 'avg_aqi'], ascending=[True, False]).groupby('station').first().reset_index()[['station', 'hour', 'avg_aqi']]
    peak_hour = peak_hour.rename(columns={'hour': 'peak_hour', 'avg_aqi': 'peak_avg_aqi'})
    latest = latest.merge(peak_hour, on='station', how='left')

    forecast_cards = []
    for _, row in latest.sort_values('aqi', ascending=False).head(5).iterrows():
        forecast_cards.append({
            'station': row['station'],
            'city': row['city'],
            'aqi': int(round(row['aqi'])),
            'aqi_bucket': str(row['aqi_bucket']),
            'peak_hour': int(row['peak_hour']) if pd.notna(row['peak_hour']) else 6,
            'risk_note': 'High congestion and low dispersion are expected to sustain the hotspot.' if row['aqi'] >= 250 else 'Morning and evening traffic peaks may worsen conditions.',
        })

    recommendations = []
    for hotspot in top_hotspots[:5]:
        recommendations.append({
            'station': hotspot['station'],
            'city': hotspot['city'],
            'priority': 'Immediate' if hotspot['aqi'] >= 300 else 'High',
            'action': 'Deploy inspectors for dust-control, idling enforcement, and hotspot-specific compliance checks.',
            'reason': 'Persistent high AQI suggests concentrated emissions and significant public exposure.',
        })

    india_summary = national_df.groupby('city').agg(avg_aqi=('aqi', 'mean'), latest_date=('date', 'max')).reset_index()
    india_summary['latest_date'] = india_summary['latest_date'].dt.strftime('%Y-%m-%d')
    india_summary = india_summary.sort_values('avg_aqi', ascending=False).head(8)
    india_summary = india_summary.to_dict(orient='records')

    national_trends = (
        national_df.groupby('date')['aqi']
        .mean()
        .reset_index()
        .tail(20)
        .assign(avg_aqi=lambda d: d['aqi'].round(1))
        .copy()
    )
    national_trends['date'] = national_trends['date'].dt.strftime('%Y-%m-%d')
    national_trends = national_trends.to_dict(orient='records')

    station_locations = []
    for _, row in latest[['station', 'city', 'latitude', 'longitude', 'aqi']].drop_duplicates().iterrows():
        station_locations.append({
            'station': row['station'],
            'city': row['city'],
            'latitude': float(row['latitude']),
            'longitude': float(row['longitude']),
            'aqi': int(round(row['aqi'])),
        })

    factory_by_zone = {}
    for factory in enriched_factories:
        zone = factory['inferred_zone']
        if zone not in factory_by_zone:
            factory_by_zone[zone] = []
        factory_by_zone[zone].append({
            'name': factory['name'],
            'category': factory['category'],
        })

    source_attribution_enhanced = []
    for hotspot in top_hotspots[:5]:
        traffic_signal = 'High' if hotspot['aqi'] >= 300 else 'Moderate'
        factory_signal = 'High' if len(enriched_factories) > 50 else 'Moderate'
        
        source_attribution_enhanced.append({
            'station': hotspot['station'],
            'city': hotspot['city'],
            'aqi': int(round(hotspot['aqi'])),
            'traffic_signal': traffic_signal,
            'factory_signal': factory_signal,
            'geospatial_note': 'Building-footprint density and nearby industrial clusters correlate with elevated local exposure.',
            'priority': 'Immediate' if hotspot['aqi'] >= 300 else 'High',
        })

    alert_headline = 'ALERT: AQI thresholds exceeded in multiple Delhi hotspots; enforcement escalation advised.' if latest['aqi'].mean() >= 250 else 'Stable conditions with moderate risk during evening traffic peaks.'

    # --- Advanced intelligence layers -------------------------------------
    pollutant_attr = pollutant_attribution(latest, top_n=6)
    # Enrich source attribution with the dominant pollutant + true source.
    attr_by_station = {p['station']: p for p in pollutant_attr}
    for item in source_attribution_enhanced:
        match = attr_by_station.get(item['station'])
        if match:
            item['dominant_pollutant'] = match['dominant_pollutant']
            item['primary_source'] = match['primary_source']
            item['confidence'] = match['confidence']

    mix = pollutant_mix(latest)
    weather = weather_dispersion(latest)
    cities = city_comparison(latest, selected_df)

    # Hyperlocal forecast for the worst hotspot (or a user-selected station).
    available_stations = [h['station'] for h in top_hotspots]
    if forecast_station and forecast_station in set(selected_df['station'].unique()):
        focus_station = forecast_station
    else:
        focus_station = top_hotspots[0]['station'] if top_hotspots else None
    trained = _cached_forecast_model()
    if trained and focus_station:
        aqi_forecast = forecast_station_ml(selected_df, trained, focus_station, selected_ts, horizon_hours=72)
        forecast_meta = {
            'model_rmse': trained['model_rmse'],
            'persistence_rmse': trained['persistence_rmse'],
            'improvement_pct': trained['improvement_pct'],
            'overall_rmse': trained.get('overall_rmse'),
            'horizon_h': trained['horizon_h'],
            'method': trained['method'],
            'n_train': trained.get('n_train'),
            'n_test': trained.get('n_test'),
        }
    else:
        aqi_forecast = forecast_station(selected_df, focus_station, selected_ts, horizon_hours=72) if focus_station else []
        meta = forecast_accuracy(selected_df, focus_station) if focus_station else {}
        meta['method'] = 'Seasonal-climatology blend (statistical fallback)'
        forecast_meta = meta
    diurnal_curve = diurnal_profile(selected_df, focus_station) if focus_station else []

    # Health advisories for the top hotspots.
    health_advisories = []
    for hotspot in top_hotspots[:5]:
        adv = health_advisory(hotspot['aqi'])
        adv['station'] = hotspot['station']
        adv['city'] = hotspot['city']
        health_advisories.append(adv)
    overall_health = health_advisory(latest['aqi'].mean())

    # Running alert ticker: emit a message for every crossed threshold.
    alert_ticker = []
    severe = latest[latest['aqi'] >= 400]
    very_poor = latest[(latest['aqi'] >= 300) & (latest['aqi'] < 400)]
    for _, r in severe.iterrows():
        alert_ticker.append(f"\u26a0 SEVERE: {r['station']} at AQI {int(r['aqi'])} — halt outdoor activity & trigger GRAP.")
    for _, r in very_poor.head(4).iterrows():
        alert_ticker.append(f"\u25b2 VERY POOR: {r['station']} at AQI {int(r['aqi'])} — deploy inspectors, restrict heavy traffic.")
    if weather['dispersion'] == 'Poor':
        alert_ticker.append(f"\U0001f32c Low wind ({weather['wind_speed']} km/h) — pollutants accumulating, worsening likely.")
    if not alert_ticker:
        alert_ticker.append('\u2714 No stations above the Very Poor threshold in the current window.')


    ai_prompt = (
        f"You are an expert urban air quality analyst for Delhi-NCR and India. "
        f"Provide a detailed, actionable summary including: "
        f"(1) National picture: top 5 polluted cities are {', '.join([item['city'] for item in india_summary[:5]])}; "
        f"(2) Delhi-NCR hotspots at {selected_datetime or str(selected_ts)}: {', '.join([h['station'] for h in top_hotspots[:3]])} with AQI {', '.join([str(int(h['aqi'])) for h in top_hotspots[:3]])}; "
        f"(3) Dominant pollutant at the worst hotspot is {pollutant_attr[0]['dominant_pollutant']} pointing to {pollutant_attr[0]['primary_source']} (confidence {pollutant_attr[0]['confidence']}); "
        f"(4) Weather: wind {weather['wind_speed']} km/h giving {weather['dispersion']} dispersion; "
        f"(5) Traffic correlation: {traffic_correlation['highest_traffic_period']} shows highest congestion, {traffic_correlation['highest_aqi_period']} shows highest pollution; "
        f"(6) {len(enriched_factories)} registered factories across {len(factory_by_zone)} Delhi zones contribute to source emissions; "
        f"(7) Intervention priorities: focus on {top_hotspots[0]['city']} for maximum impact. "
        f"Be concise, cite data, and suggest 2-3 immediate actions."
    )
    ai_summary = _call_ollama(ai_prompt, max_length=1200)
    if not ai_summary:
        lead = pollutant_attr[0] if pollutant_attr else {'dominant_pollutant': 'PM2.5', 'primary_source': 'combustion'}
        ai_summary = (
            f"India faces acute air quality stress: {india_summary[0]['city']} leads with AQI {round(india_summary[0]['avg_aqi'])}. "
            f"Across Delhi-NCR the current average AQI is {int(round(latest['aqi'].mean()))} ({overall_health['category']}), peaking at {int(round(latest['aqi'].max()))}. "
            f"The worst hotspot ({top_hotspots[0]['station']}) is driven by {lead['dominant_pollutant']}, implicating {lead['primary_source']}. "
            f"Weather is {weather['dispersion'].lower()} for dispersion (wind {weather['wind_speed']} km/h), so pollutants are "
            f"{'accumulating near the surface' if weather['dispersion'] == 'Poor' else 'partially ventilating'}. "
            f"Traffic peaks during {traffic_correlation['highest_traffic_period']} align with pollution spikes, while "
            f"{len(enriched_factories)} industrial sources across {len(factory_by_zone)} zones amplify exposure. "
            f"Immediate actions: deploy enforcement at {top_hotspots[0]['station']}, restrict heavy traffic during "
            f"{traffic_correlation['highest_aqi_period'].lower()} hours, and issue a {overall_health['category']} health advisory to vulnerable groups."
        )

    return {
        'ai_summary': ai_summary,
        'alert_headline': alert_headline,
        'alert_ticker': alert_ticker,
        'city_count': delhi_df['city'].nunique(),
        'station_count': delhi_df['station'].nunique(),
        'selected_datetime': selected_datetime or str(selected_ts),
        'india_summary': india_summary,
        'national_trends': national_trends,
        'delhi_hotspots': top_hotspots,
        'forecast_cards': forecast_cards,
        'aqi_forecast': aqi_forecast,
        'forecast_meta': forecast_meta,
        'forecast_station': focus_station,
        'forecast_station_options': sorted(selected_df['station'].unique().tolist()),
        'diurnal_curve': diurnal_curve,
        'source_attribution': source_attribution_enhanced,
        'pollutant_attribution': pollutant_attr,
        'pollutant_mix': mix,
        'weather': weather,
        'city_comparison': cities,
        'health_advisories': health_advisories,
        'overall_health': overall_health,
        'factory_by_zone': factory_by_zone,
        'factory_count': len(enriched_factories),
        'factory_preview': enriched_factories[:10],
        'traffic_correlation': traffic_correlation,
        'recommendations': recommendations,
        'station_locations': station_locations,
        'avg_aqi': int(round(latest['aqi'].mean())),
        'max_aqi': int(round(latest['aqi'].max())),
        'generated_at': pd.Timestamp.utcnow().strftime('%Y-%m-%d %H:%M:%S IST'),
    }


def write_dashboard(output_path: Path | None = None) -> Path:
    output_path = output_path or ROOT / 'public' / 'dashboard.json'
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary = build_summary()
    output_path.write_text(json.dumps(summary, indent=2, cls=NumpyEncoder), encoding='utf-8')
    return output_path


if __name__ == '__main__':
    result = write_dashboard()
    print(result)
