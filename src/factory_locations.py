import json
from pathlib import Path
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
FACTORY_LOCATIONS_PATH = ROOT / 'data' / 'factory_locations.json'


DELHI_ZONES = {
    'North': ['Rohini', 'Bawana', 'Narela', 'Jahangirpuri', 'Wazirpur'],
    'South': ['RK Puram', 'Okhla', 'Kalkaji', 'Sangam Vihar', 'Greater Kailash'],
    'East': ['Anand Vihar', 'Ghazipur', 'Patparganj', 'Shahdara', 'East Delhi'],
    'West': ['Shadipur', 'Kirti Nagar', 'Punjabi Bagh', 'Dwarka', 'Paschim Vihar'],
    'Central': ['ITO', 'Connaught Place', 'New Delhi', 'Chandni Chowk', 'Mandir Marg'],
}

FACTORY_KEYWORDS = {
    'steel': 'Industrial', 'iron': 'Industrial', 'brass': 'Industrial', 'metal': 'Industrial',
    'press': 'Printing', 'printing': 'Printing', 'factory': 'Manufacturing',
    'mill': 'Manufacturing', 'workshop': 'Manufacturing', 'works': 'Industrial',
    'ice': 'Cold Storage', 'cold storage': 'Cold Storage', 'refrig': 'Cold Storage',
    'power': 'Energy', 'coal': 'Energy', 'electric': 'Energy',
    'waste': 'Waste Management', 'disposal': 'Waste Management', 'sewage': 'Waste Management',
}


def infer_factory_zone(factory_name: str) -> tuple[str, str]:
    name_lower = factory_name.lower()
    
    sector_num = None
    for part in factory_name.split():
        if part.isdigit() and len(part) <= 3:
            sector_num = int(part)
            break
    
    if sector_num:
        if 1 <= sector_num <= 8:
            zone = 'North'
        elif 9 <= sector_num <= 15:
            zone = 'Central'
        elif 16 <= sector_num <= 25:
            zone = 'South'
        elif 26 <= sector_num <= 40:
            zone = 'West'
        else:
            zone = 'East'
    else:
        zone = None
        for z, keywords in DELHI_ZONES.items():
            if any(kw.lower() in name_lower for kw in keywords):
                zone = z
                break
        zone = zone or 'Central'
    
    category = 'Manufacturing'
    for keyword, cat in FACTORY_KEYWORDS.items():
        if keyword in name_lower:
            category = cat
            break
    
    return zone, category


def enrich_factory_locations(factory_entries: list[dict]) -> list[dict]:
    enriched = []
    for entry in factory_entries:
        zone, category = infer_factory_zone(entry['name'])
        enriched.append({
            **entry,
            'inferred_zone': zone,
            'category': category,
        })
    return enriched


def save_factory_locations(factory_entries: list[dict]) -> Path:
    enriched = enrich_factory_locations(factory_entries)
    FACTORY_LOCATIONS_PATH.write_text(json.dumps(enriched, indent=2), encoding='utf-8')
    return FACTORY_LOCATIONS_PATH


def load_factory_locations() -> list[dict]:
    if FACTORY_LOCATIONS_PATH.exists():
        return json.loads(FACTORY_LOCATIONS_PATH.read_text(encoding='utf-8'))
    return []
