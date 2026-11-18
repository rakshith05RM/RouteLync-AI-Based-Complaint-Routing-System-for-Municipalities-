"""A local STAND-IN for the Photon geocoder (same JSON shape). Used only to test RouteLync's own code in a browser."""
import json, sys, urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer

COUNTS = {}
PLACES = [
    ("Kempegowda Bus Station", "Kempegowda Road", "Gandhinagar", 12.9767, 77.5726, 4455),
    ("Jayanagar 4th Block", "11th Main Road", "Jayanagar", 12.9250, 77.5838, 5566),
    ("Indiranagar Metro Station", "100 Feet Road", "Indiranagar", 12.9784, 77.6408, 6677),
]

def feature(name, street, district, lat, lng, osm_id):
    return {"type": "Feature", "geometry": {"type": "Point", "coordinates": [lng, lat]},
            "properties": {"osm_id": osm_id, "osm_type": "W", "name": name, "street": street, "district": district, "city": "Bengaluru", "state": "Karnataka"}}

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass
    def send(self, code, body):
        data = json.dumps(body).encode()
        self.send_response(code); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(data))); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        url = urllib.parse.urlparse(self.path); q = urllib.parse.parse_qs(url.query)
        if url.path == "/__count":
            return self.send(200, COUNTS)
        COUNTS[url.path] = COUNTS.get(url.path, 0) + 1
        if url.path == "/api/":
            text = q.get("q", [""])[0].lower()
            if "fail503" in text: return self.send(503, {"error": "down"})
            if "fail429" in text: return self.send(429, {"error": "slow down"})
            if "zzzzzzz" in text: return self.send(200, {"type": "FeatureCollection", "features": []})
            return self.send(200, {"type": "FeatureCollection", "features": [feature(*p) for p in PLACES]})
        if url.path == "/reverse":
            return self.send(200, {"type": "FeatureCollection", "features": [feature("", "Kempegowda Road", "Jayanagar", float(q["lat"][0]), float(q["lon"][0]), 9001)]})
        self.send(404, {})

HTTPServer(("127.0.0.1", int(sys.argv[1])), Handler).serve_forever()
