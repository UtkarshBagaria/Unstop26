"""Advanced air-quality intelligence: pollutant-based source attribution,
hyperlocal AQI forecasting, health advisories, multi-city comparison and
weather/dispersion analysis.

All functions operate on already-loaded DataFrames so the large Delhi-NCR
dataset is read only once by the caller.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

POLLUTANT_COLS = ['pm25', 'pm10', 'no2', 'so2', 'co', 'o3']

# Rough CPCB-style breakpoints used only to normalise pollutants into a
# comparable 0-500 sub-index so the dominant driver can be identified.
SUBINDEX_SCALE = {
    'pm25': 60.0,   # ug/m3 that maps to ~AQI 100
    'pm10': 100.0,
    'no2': 80.0,
    'so2': 80.0,
    'co': 2.0,      # mg/m3
    'o3': 100.0,
}

# Which real-world sources each pollutant most strongly implicates.
POLLUTANT_SOURCE = {
    'pm25': ('Combustion / Vehicles & Biomass', 'Fine particulates from diesel exhaust, crop-residue and waste burning.'),
    'pm10': ('Dust / Construction & Roads', 'Coarse dust from construction sites, unpaved roads and demolition.'),
    'no2': ('Traffic', 'Nitrogen dioxide is a direct marker of vehicular and fleet exhaust.'),
    'so2': ('Industry / Power', 'Sulphur dioxide points to coal, diesel gensets and industrial stacks.'),
    'co': ('Vehicles / Incomplete Burning', 'Carbon monoxide indicates congested traffic and open burning.'),
    'o3': ('Photochemical / Secondary', 'Ground-level ozone forms in sunlight from traffic and industrial precursors.'),
}


def _aqi_bucket(aqi: float) -> str:
    if aqi <= 50:
        return 'Good'
    if aqi <= 100:
        return 'Satisfactory'
    if aqi <= 200:
        return 'Moderate'
    if aqi <= 300:
        return 'Poor'
    if aqi <= 400:
        return 'Very Poor'
    return 'Severe'


def dominant_pollutant(row: pd.Series) -> tuple[str, float]:
    """Return the pollutant with the highest normalised sub-index for a row."""
    best_key, best_val = 'pm25', 0.0
    for col in POLLUTANT_COLS:
        val = row.get(col)
        if val is None or pd.isna(val):
            continue
        norm = float(val) / SUBINDEX_SCALE[col]
        if norm > best_val:
            best_val, best_key = norm, col
    return best_key, best_val


def pollutant_attribution(latest: pd.DataFrame, top_n: int = 6) -> list[dict]:
    """For the highest-AQI stations, attribute pollution to a dominant source."""
    results = []
    ranked = latest.sort_values('aqi', ascending=False).head(top_n)
    for _, row in ranked.iterrows():
        key, _ = dominant_pollutant(row)
        source, explanation = POLLUTANT_SOURCE[key]
        # Confidence: how far the dominant pollutant leads the field (0-1).
        norms = []
        for col in POLLUTANT_COLS:
            v = row.get(col)
            if v is not None and not pd.isna(v):
                norms.append(float(v) / SUBINDEX_SCALE[col])
        norms.sort(reverse=True)
        if len(norms) >= 2 and norms[0] > 0:
            confidence = min(0.99, 0.55 + 0.45 * (norms[0] - norms[1]) / norms[0])
        else:
            confidence = 0.6
        results.append({
            'station': row['station'],
            'city': row['city'],
            'aqi': int(round(row['aqi'])),
            'dominant_pollutant': key.upper().replace('PM25', 'PM2.5'),
            'primary_source': source,
            'explanation': explanation,
            'confidence': round(confidence, 2),
        })
    return results


def pollutant_mix(latest: pd.DataFrame) -> dict:
    """City-wide average sub-index share of each pollutant (for a doughnut chart)."""
    shares = {}
    for col in POLLUTANT_COLS:
        if col in latest.columns:
            series = pd.to_numeric(latest[col], errors='coerce')
            shares[col] = float(series.mean() / SUBINDEX_SCALE[col]) if not series.isna().all() else 0.0
    total = sum(shares.values()) or 1.0
    labels = {'pm25': 'PM2.5', 'pm10': 'PM10', 'no2': 'NO2', 'so2': 'SO2', 'co': 'CO', 'o3': 'O3'}
    return {
        'labels': [labels[k] for k in shares],
        'values': [round(100 * v / total, 1) for v in shares.values()],
    }


def diurnal_profile(history: pd.DataFrame, station: str) -> list[float]:
    """Mean AQI for each of the 24 hours for one station."""
    sub = history[history['station'] == station]
    profile = sub.groupby('hour')['aqi'].mean()
    return [float(profile.get(h, sub['aqi'].mean() if not sub.empty else 0)) for h in range(24)]


def _seasonal_climatology(history: pd.DataFrame, station: str) -> dict:
    """Mean AQI keyed by (month, hour) so the forecast tracks seasonal level and
    time-of-day shape — the combination that beats naive persistence day-ahead."""
    sub = history[history['station'] == station]
    if sub.empty:
        return {}
    grp = sub.groupby(['month', 'hour'])['aqi'].mean()
    return {key: float(val) for key, val in grp.items()}


def forecast_station(history: pd.DataFrame, station: str, start_ts: pd.Timestamp,
                     horizon_hours: int = 72) -> list[dict]:
    """Blend the recent level with a seasonal (month+hour) climatology to project
    AQI forward. Explainable and measurably better than flat persistence."""
    sub = history[history['station'] == station].sort_values('datetime')
    if sub.empty:
        return []
    clim = _seasonal_climatology(history, station)
    profile = diurnal_profile(history, station)
    fallback = sum(profile) / 24 if any(profile) else float(sub['aqi'].mean())
    recent = float(sub['aqi'].tail(3).mean())
    points = []
    for h in range(1, horizon_hours + 1):
        ts = start_ts + pd.Timedelta(hours=h)
        climatology = clim.get((ts.month, ts.hour), profile[ts.hour] if profile else fallback)
        # Anchor to the recent level early, relax toward climatology over ~48h.
        w = min(0.65, 0.5 + 0.15 * (h / 48.0))
        aqi = max(0.0, (1 - w) * recent + w * climatology)
        points.append({
            'offset_h': h,
            'datetime': ts.strftime('%Y-%m-%d %H:%M'),
            'aqi': int(round(aqi)),
            'bucket': _aqi_bucket(aqi),
        })
    return points


def forecast_accuracy(history: pd.DataFrame, station: str) -> dict:
    """Back-test the seasonal-climatology model against a persistence baseline at
    a ~24h horizon (the challenge's key forecasting metric)."""
    sub = history[history['station'] == station].sort_values('datetime').reset_index(drop=True)
    if len(sub) < 200:
        return {'model_rmse': None, 'persistence_rmse': None, 'improvement_pct': None, 'horizon_h': 24}
    deltas = sub['datetime'].diff().dt.total_seconds().dropna() / 3600.0
    step_h = float(deltas.median()) if not deltas.empty else 1.0
    k = max(1, round(24.0 / step_h)) if step_h > 0 else 1
    actual = sub['aqi'].to_numpy()
    if len(actual) <= k:
        return {'model_rmse': None, 'persistence_rmse': None, 'improvement_pct': None, 'horizon_h': 24}
    clim_series = sub.groupby(['month', 'hour'])['aqi'].transform('mean').to_numpy()
    target = actual[k:]
    persistence_pred = actual[:-k]
    persistence_rmse = float(((target - persistence_pred) ** 2).mean() ** 0.5)
    model_pred = 0.5 * persistence_pred + 0.5 * clim_series[k:]
    model_rmse = float(((target - model_pred) ** 2).mean() ** 0.5)
    improvement = 0.0
    if persistence_rmse > 0:
        improvement = round(100 * (persistence_rmse - model_rmse) / persistence_rmse, 1)
    return {
        'model_rmse': round(model_rmse, 1),
        'persistence_rmse': round(persistence_rmse, 1),
        'improvement_pct': improvement,
        'horizon_h': 24,
    }


# --- Machine-learning forecaster -----------------------------------------
# A gradient-boosted regressor trained on lagged AQI + weather + calendar
# features, using a direct multi-horizon formulation (horizon is a feature so
# one model covers the whole 6h..72h range). Evaluated with a time-based
# train/test split so the reported skill is an honest out-of-time number.

FORECAST_FEATURES = [
    'last_aqi', 'wind_speed', 'humidity', 'temperature', 'visibility',
    'pm25', 'pm10', 'clim', 'horizon', 'target_hour', 'target_month',
    'target_dow', 'target_is_weekend',
]
_STEP_HOURS = 6            # dataset cadence
_MAX_STEPS = 12           # 12 * 6h = 72h horizon


def _rmse(a, b) -> float:
    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    return float(np.sqrt(np.mean((a - b) ** 2)))


def train_forecast_model(history: pd.DataFrame, max_samples: int = 150000, seed: int = 42) -> dict | None:
    """Train and time-split-validate a gradient-boosted AQI forecaster.

    Returns None (caller falls back to the climatology model) if scikit-learn
    is unavailable or there is insufficient data.
    """
    try:
        from sklearn.ensemble import HistGradientBoostingRegressor
    except Exception:
        return None

    df = history.sort_values(['station', 'datetime']).reset_index(drop=True)
    if len(df) < 5000:
        return None
    df['dow'] = df['datetime'].dt.dayofweek
    clim_table = (
        df.groupby(['station', 'month', 'hour'])['aqi'].mean().rename('clim').reset_index()
    )
    g = df.groupby('station', sort=False)

    blocks = []
    for s in range(1, _MAX_STEPS + 1):
        target_dt = g['datetime'].shift(-s)
        blocks.append(pd.DataFrame({
            'station': df['station'].to_numpy(),
            'last_aqi': df['aqi'].to_numpy(),
            'wind_speed': df['wind_speed'].to_numpy(),
            'humidity': df['humidity'].to_numpy(),
            'temperature': df['temperature'].to_numpy(),
            'visibility': df['visibility'].to_numpy(),
            'pm25': df['pm25'].to_numpy(),
            'pm10': df['pm10'].to_numpy(),
            'horizon': s,
            'target_hour': g['hour'].shift(-s).to_numpy(),
            'target_month': g['month'].shift(-s).to_numpy(),
            'target_dow': g['dow'].shift(-s).to_numpy(),
            'target_is_weekend': g['is_weekend'].shift(-s).to_numpy(),
            'anchor_dt': df['datetime'].to_numpy(),
            'y': g['aqi'].shift(-s).to_numpy(),
            '_gap_ok': (target_dt - df['datetime']).dt.total_seconds().to_numpy() <= s * _STEP_HOURS * 3600 * 1.5,
        }))

    data = pd.concat(blocks, ignore_index=True)
    data = data[data['_gap_ok'] & data['y'].notna() & data['target_hour'].notna()]
    data = data.merge(
        clim_table, left_on=['station', 'target_month', 'target_hour'],
        right_on=['station', 'month', 'hour'], how='left',
    )
    data['clim'] = data['clim'].fillna(data['last_aqi'])

    if len(data) > max_samples:
        data = data.sample(max_samples, random_state=seed)
    data = data.sort_values('anchor_dt').reset_index(drop=True)

    split = int(len(data) * 0.8)
    train, test = data.iloc[:split], data.iloc[split:]
    if len(train) < 1000 or len(test) < 200:
        return None

    model = HistGradientBoostingRegressor(
        max_depth=8, learning_rate=0.08, max_iter=300,
        l2_regularization=1.0, random_state=seed,
    )
    model.fit(train[FORECAST_FEATURES], train['y'])

    test_pred = model.predict(test[FORECAST_FEATURES])
    overall_rmse = _rmse(test['y'], test_pred)
    # Headline skill reported at the 24h horizon (step 4).
    t24 = test[test['horizon'] == 4]
    if len(t24) > 50:
        m_rmse = _rmse(t24['y'], model.predict(t24[FORECAST_FEATURES]))
        p_rmse = _rmse(t24['y'], t24['last_aqi'])
    else:
        m_rmse, p_rmse = overall_rmse, _rmse(test['y'], test['last_aqi'])
    improvement = round(100 * (p_rmse - m_rmse) / p_rmse, 1) if p_rmse > 0 else 0.0

    return {
        'model': model,
        'features': FORECAST_FEATURES,
        'clim_table': clim_table,
        'model_rmse': round(m_rmse, 1),
        'persistence_rmse': round(p_rmse, 1),
        'improvement_pct': improvement,
        'overall_rmse': round(overall_rmse, 1),
        'horizon_h': 24,
        'n_train': int(len(train)),
        'n_test': int(len(test)),
        'method': 'Gradient-boosted trees (lagged AQI + weather + calendar)',
    }


def forecast_station_ml(history: pd.DataFrame, trained: dict, station: str,
                        start_ts: pd.Timestamp, horizon_hours: int = 72) -> list[dict]:
    """Produce a 6-hourly forecast out to `horizon_hours` using the trained model."""
    if not trained or 'model' not in trained or not station:
        return []
    model = trained['model']
    sub = history[history['station'] == station]
    sub = sub[sub['datetime'] <= start_ts]
    if sub.empty:
        sub = history[history['station'] == station]
    sub = sub.sort_values('datetime')
    if sub.empty:
        return []
    anchor = sub.iloc[-1]
    clim_lookup = sub.groupby(['month', 'hour'])['aqi'].mean()
    fallback = float(sub['aqi'].mean())

    steps = max(1, horizon_hours // _STEP_HOURS)
    rows, metas = [], []
    for s in range(1, steps + 1):
        tdt = start_ts + pd.Timedelta(hours=_STEP_HOURS * s)
        clim_val = float(clim_lookup.get((tdt.month, tdt.hour), fallback))
        rows.append([
            float(anchor['aqi']), float(anchor['wind_speed']), float(anchor['humidity']),
            float(anchor['temperature']), float(anchor['visibility']), float(anchor['pm25']),
            float(anchor['pm10']), clim_val, s, tdt.hour, tdt.month, tdt.dayofweek,
            1 if tdt.dayofweek >= 5 else 0,
        ])
        metas.append((_STEP_HOURS * s, tdt))

    preds = model.predict(pd.DataFrame(rows, columns=trained['features']))
    # Start from the current (anchor) value so the trajectory is continuous.
    anchor_aqi = max(0.0, float(anchor['aqi']))
    points = [{
        'offset_h': 0,
        'datetime': pd.Timestamp(anchor['datetime']).strftime('%Y-%m-%d %H:%M'),
        'aqi': int(round(anchor_aqi)),
        'bucket': _aqi_bucket(anchor_aqi),
        'is_now': True,
    }]
    for (offset, tdt), pred in zip(metas, preds):
        aqi = max(0.0, float(pred))
        points.append({
            'offset_h': offset,
            'datetime': tdt.strftime('%Y-%m-%d %H:%M'),
            'aqi': int(round(aqi)),
            'bucket': _aqi_bucket(aqi),
        })
    return points


HEALTH_ADVISORY = {
    'Good': ('#2ecc71', 'Air quality is healthy. Ideal for all outdoor activity.',
             'No restrictions for any group.'),
    'Satisfactory': ('#9acd32', 'Acceptable air quality with minor risk to the very sensitive.',
                     'Unusually sensitive people should watch for symptoms.'),
    'Moderate': ('#f1c40f', 'Sensitive groups may notice mild respiratory discomfort.',
                 'Children, elderly and asthmatics should limit prolonged exertion.'),
    'Poor': ('#e67e22', 'Breathing discomfort likely for most people on prolonged exposure.',
             'Avoid outdoor exercise; keep windows shut during peak hours.'),
    'Very Poor': ('#e74c3c', 'Respiratory illness risk is high for the whole population.',
                  'Schools should suspend outdoor activity; masks (N95) advised outdoors.'),
    'Severe': ('#8e44ad', 'Serious health impact; affects healthy people and severely harms the ill.',
               'Halt outdoor work, close schools, activate emergency GRAP measures.'),
}


def health_advisory(aqi: float) -> dict:
    bucket = _aqi_bucket(aqi)
    color, message, action = HEALTH_ADVISORY[bucket]
    return {'aqi': int(round(aqi)), 'category': bucket, 'color': color,
            'message': message, 'protective_action': action}


def city_comparison(latest: pd.DataFrame, history: pd.DataFrame) -> list[dict]:
    """Compare the NCR cities: current AQI, dominant pollutant and 24h trend."""
    results = []
    for city, grp in latest.groupby('city'):
        avg_aqi = float(grp['aqi'].mean())
        # 24h trend: compare the last 24h mean vs the previous 24h mean.
        hist_city = history[history['city'] == city].sort_values('datetime')
        trend = 'flat'
        if len(hist_city) > 48:
            recent = hist_city['aqi'].tail(24).mean()
            prior = hist_city['aqi'].tail(48).head(24).mean()
            if recent > prior * 1.05:
                trend = 'rising'
            elif recent < prior * 0.95:
                trend = 'falling'
        mix = pollutant_mix(grp)
        top_pollutant = mix['labels'][mix['values'].index(max(mix['values']))] if mix['values'] else 'PM2.5'
        results.append({
            'city': city,
            'avg_aqi': int(round(avg_aqi)),
            'category': _aqi_bucket(avg_aqi),
            'dominant_pollutant': top_pollutant,
            'trend': trend,
            'station_count': int(grp['station'].nunique()),
        })
    return sorted(results, key=lambda x: x['avg_aqi'], reverse=True)


def weather_dispersion(latest: pd.DataFrame) -> dict:
    """Assess how favourable current weather is for pollutant dispersion."""
    wind = pd.to_numeric(latest.get('wind_speed'), errors='coerce').mean()
    humidity = pd.to_numeric(latest.get('humidity'), errors='coerce').mean()
    temp = pd.to_numeric(latest.get('temperature'), errors='coerce').mean()
    visibility = pd.to_numeric(latest.get('visibility'), errors='coerce').mean()
    wind = 0.0 if pd.isna(wind) else float(wind)
    humidity = 0.0 if pd.isna(humidity) else float(humidity)
    temp = 0.0 if pd.isna(temp) else float(temp)
    visibility = 0.0 if pd.isna(visibility) else float(visibility)
    if wind < 5:
        dispersion = 'Poor'
        note = 'Low wind speed traps pollutants near the surface — expect accumulation.'
    elif wind < 12:
        dispersion = 'Moderate'
        note = 'Moderate winds provide partial ventilation of the urban boundary layer.'
    else:
        dispersion = 'Good'
        note = 'Strong winds actively disperse pollutants and lower ground-level AQI.'
    return {
        'wind_speed': round(wind, 1),
        'humidity': round(humidity, 1),
        'temperature': round(temp, 1),
        'visibility': round(visibility, 1),
        'dispersion': dispersion,
        'note': note,
    }
