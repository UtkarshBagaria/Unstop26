import pandas as pd
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TRAFFIC_PATH = ROOT / 'data' / 'delhi_traffic_features.csv'
DELHI_AQI_PATH = ROOT / 'data' / 'delhi_ncr_aqi_dataset.csv'


def load_traffic_data(path: Path = TRAFFIC_PATH) -> pd.DataFrame:
    return pd.read_csv(path)


def load_aqi_data(path: Path = DELHI_AQI_PATH) -> pd.DataFrame:
    df = pd.read_csv(path, parse_dates=['datetime'])
    return df


def analyze_traffic_pollution_correlation() -> dict:
    traffic_df = load_traffic_data()
    aqi_df = load_aqi_data()
    
    traffic_by_hour = traffic_df.groupby('time_of_day').agg(
        avg_traffic_density=('traffic_density_level', lambda x: (x == 'Heavy').sum()),
        avg_speed=('average_speed_kmph', 'mean'),
        trip_count=('Trip_ID', 'count')
    ).reset_index()
    
    aqi_df['hour'] = aqi_df['datetime'].dt.hour
    aqi_by_hour = aqi_df.groupby('hour').agg(
        avg_aqi=('aqi', 'mean'),
        pollution_count=('aqi', 'count')
    ).reset_index()
    
    time_mapping = {
        'Morning': list(range(6, 12)),
        'Afternoon': list(range(12, 17)),
        'Evening': list(range(17, 21)),
        'Night': list(range(21, 24)) + list(range(0, 6)),
    }
    
    correlation_results = []
    for period, hours in time_mapping.items():
        traffic_row = traffic_by_hour[traffic_by_hour['time_of_day'] == period]
        if traffic_row.empty:
            continue
        
        period_aqi = aqi_by_hour[aqi_by_hour['hour'].isin(hours)]
        if period_aqi.empty:
            continue
        
        avg_aqi = period_aqi['avg_aqi'].mean()
        avg_traffic = traffic_row['avg_traffic_density'].values[0]
        avg_speed = traffic_row['avg_speed'].values[0] or 0
        
        correlation_results.append({
            'period': period,
            'hours': hours,
            'avg_aqi': round(avg_aqi, 1),
            'traffic_congestion_score': round(avg_traffic, 1),
            'avg_speed_kmph': round(avg_speed, 1),
            'correlation_insight': (
                f'Peak congestion during {period.lower()} correlates with elevated AQI of {round(avg_aqi, 0)}'
                if avg_traffic > 50 else f'{period} shows moderate traffic and stable AQI conditions.'
            ),
        })
    
    return {
        'by_period': correlation_results,
        'highest_aqi_period': max(correlation_results, key=lambda x: x['avg_aqi'], default={}).get('period', 'N/A'),
        'highest_traffic_period': max(correlation_results, key=lambda x: x['traffic_congestion_score'], default={}).get('period', 'N/A'),
    }
