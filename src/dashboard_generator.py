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


def build_summary(path: Path = DELHI_AQI_PATH, selected_datetime: str | None = None) -> dict:
    delhi_df = load_delhi_dataset(path)
    national_df = load_national_dataset()
    traffic_df = load_traffic_dataset()
    factory_entries = load_factory_entries()
    
    enriched_factories = enrich_factory_locations(factory_entries)
    save_factory_locations(enriched_factories)
    
    traffic_correlation = analyze_traffic_pollution_correlation()

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

    ai_prompt = (
        f"You are an expert urban air quality analyst for Delhi-NCR and India. "
        f"Provide a detailed, actionable summary including: "
        f"(1) National picture: top 5 polluted cities are {', '.join([item['city'] for item in india_summary[:5]])}; "
        f"(2) Delhi-NCR hotspots at {selected_datetime or str(selected_ts)}: {', '.join([h['station'] for h in top_hotspots[:3]])} with AQI {', '.join([str(int(h['aqi'])) for h in top_hotspots[:3]])}; "
        f"(3) Traffic correlation: {traffic_correlation['highest_traffic_period']} shows highest congestion, {traffic_correlation['highest_aqi_period']} shows highest pollution; "
        f"(4) {len(enriched_factories)} registered factories across {len(factory_by_zone)} Delhi zones contribute to source emissions; "
        f"(5) Intervention priorities: focus on {top_hotspots[0]['city']} for maximum impact. "
        f"Be concise, cite data, and suggest 2-3 immediate actions."
    )
    ai_summary = _call_ollama(ai_prompt, max_length=1200)
    if not ai_summary:
        ai_summary = (
            f"India faces acute air quality stress: {india_summary[0]['city']} leads with AQI {round(india_summary[0]['avg_aqi'])}. "
            f"Delhi-NCR hotspots ({', '.join([h['station'] for h in top_hotspots[:3]])}) show critical pollution. "
            f"Traffic peaks during {traffic_correlation['highest_traffic_period']} align with pollution spikes. "
            f"{len(enriched_factories)} industrial sources across {len(factory_by_zone)} zones amplify exposure. "
            f"Immediate actions: Deploy enforcement in {top_hotspots[0]['station']}, impose traffic restrictions during {traffic_correlation['highest_aqi_period'].lower()} hours."
        )

    return {
        'ai_summary': ai_summary,
        'alert_headline': alert_headline,
        'city_count': delhi_df['city'].nunique(),
        'station_count': delhi_df['station'].nunique(),
        'selected_datetime': selected_datetime or str(selected_ts),
        'india_summary': india_summary,
        'national_trends': national_trends,
        'delhi_hotspots': top_hotspots,
        'forecast_cards': forecast_cards,
        'source_attribution': source_attribution_enhanced,
        'factory_by_zone': factory_by_zone,
        'factory_count': len(enriched_factories),
        'factory_preview': enriched_factories[:10],
        'traffic_correlation': traffic_correlation,
        'recommendations': recommendations,
        'station_locations': station_locations,
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
