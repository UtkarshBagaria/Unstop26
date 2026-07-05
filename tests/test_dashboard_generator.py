import importlib.util
import sys
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / 'src' / 'dashboard_generator.py'

spec = importlib.util.spec_from_file_location('dashboard_generator', MODULE_PATH)
dashboard_generator = importlib.util.module_from_spec(spec)
sys.modules['dashboard_generator'] = dashboard_generator
spec.loader.exec_module(dashboard_generator)


class DashboardGeneratorTests(unittest.TestCase):
    def test_build_summary_returns_expected_keys(self):
        data_path = ROOT / 'data' / 'delhi_ncr_aqi_dataset.csv'
        summary = dashboard_generator.build_summary(data_path)

        self.assertIn('ai_summary', summary)
        self.assertIn('alert_headline', summary)
        self.assertIn('delhi_hotspots', summary)
        self.assertIn('source_attribution', summary)
        self.assertIn('traffic_correlation', summary)
        self.assertIn('factory_by_zone', summary)
        self.assertGreater(len(summary['ai_summary']), 50)
        self.assertGreater(len(summary['delhi_hotspots']), 0)
        self.assertGreater(len(summary['source_attribution']), 0)

    def test_build_summary_accepts_selected_datetime(self):
        data_path = ROOT / 'data' / 'delhi_ncr_aqi_dataset.csv'
        summary = dashboard_generator.build_summary(data_path, selected_datetime='2020-01-02 12:00:00')

        self.assertIn('selected_datetime', summary)
        self.assertEqual(summary['selected_datetime'], '2020-01-02 12:00:00')


if __name__ == '__main__':
    unittest.main()
