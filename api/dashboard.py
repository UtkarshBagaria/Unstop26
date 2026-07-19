from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import json
from pathlib import Path
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from dashboard_generator import build_summary, write_dashboard


class NumpyEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.int64)):
            return int(obj)
        if isinstance(obj, (np.floating, np.float64)):
            return float(obj)
        return super().default(obj)


class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == '/api/dashboard':
            params = parse_qs(parsed.query)
            selected_datetime = params.get('selected_datetime', [None])[0]
            forecast_station = params.get('station', [None])[0]
            data = build_summary(selected_datetime=selected_datetime, forecast_station=forecast_station)
            body = json.dumps(data, cls=NumpyEncoder).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == '/':
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            html = (ROOT / 'index.html').read_text(encoding='utf-8')
            body = html.encode('utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        self.send_response(404)
        self.end_headers()


if __name__ == '__main__':
    write_dashboard(ROOT / 'public' / 'dashboard.json')
    server = HTTPServer(('127.0.0.1', 8000), Handler)
    print('Serving on http://127.0.0.1:8000')
    server.serve_forever()
