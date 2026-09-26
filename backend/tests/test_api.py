"""Portable HTTP API surface (master prompt section 23).

Boots the real stdlib ThreadingHTTPServer on an ephemeral port against an
isolated temp DB, seeds + replays, then exercises the route surface the
dashboard consumes. Uses only urllib (no external HTTP client)."""
import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from _util import bootstrap
bootstrap()

import os
from app.services import seed
from app.services import replay_driver
from app.portable.api import Handler

def _resolve_dataset() -> str:
    env = os.environ.get("REPLAY_DATASET")
    if env and Path(env).exists():
        return env
    for p in (Path(__file__).resolve().parents[1] / "data" / "replay" / "uttarakhand_flash_flood_event.json",
              Path(__file__).resolve().parents[2] / "data" / "replay" / "uttarakhand_flash_flood_event.json"):
        if p.exists():
            return str(p)
    return str(Path(__file__).resolve().parents[2] / "data" / "replay" / "uttarakhand_flash_flood_event.json")

DATASET = _resolve_dataset()


def _get(base, path):
    with urllib.request.urlopen(base + path, timeout=10) as r:
        return r.status, json.loads(r.read().decode())


def _post(base, path, payload):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data,
                                 headers={"Content-Type": "application/json"},
                                 method="POST")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.status, json.loads(r.read().decode())


class TestAPI(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        seed.run(reset=True)
        replay_driver.run_replay(DATASET, reseed=False)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.port = cls.httpd.server_address[1]
        cls.base = f"http://127.0.0.1:{cls.port}"
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def test_health(self):
        code, body = _get(self.base, "/health")
        self.assertEqual(code, 200)
        self.assertEqual(body["status"], "ok")

    def test_system_status_has_disclaimer(self):
        code, body = _get(self.base, "/system/status")
        self.assertEqual(code, 200)
        self.assertIn("DEMO MODEL", body["model_disclaimer"])
        self.assertGreaterEqual(body["villages"], 4)

    def test_locations_villages(self):
        code, body = _get(self.base, "/locations?level=village")
        self.assertEqual(code, 200)
        self.assertEqual(len(body["locations"]), 4)

    def test_risk_all(self):
        code, body = _get(self.base, "/risk")
        self.assertEqual(code, 200)
        self.assertTrue(body["risks"])
        for r in body["risks"]:
            self.assertIn(r["risk_level"], ("LOW", "MODERATE", "HIGH", "CRITICAL"))
            self.assertTrue(r["is_synthetic"])  # honesty: demo data labelled

    def test_risk_map_is_geojson(self):
        code, body = _get(self.base, "/risk/map")
        self.assertEqual(code, 200)
        self.assertEqual(body["type"], "FeatureCollection")
        self.assertIn("model_disclaimer", body["meta"])
        self.assertTrue(body["features"])
        self.assertEqual(body["features"][0]["type"], "Feature")

    def test_risk_single_and_factors(self):
        _, all_risk = _get(self.base, "/risk")
        lid = all_risk["risks"][0]["location_id"]
        code, body = _get(self.base, f"/risk/{lid}")
        self.assertEqual(code, 200)
        self.assertEqual(body["location_id"], lid)
        self.assertIsInstance(body["top_factors"], list)

    def test_prediction_history(self):
        _, all_risk = _get(self.base, "/risk")
        lid = all_risk["risks"][0]["location_id"]
        code, body = _get(self.base, f"/predictions/history?location_id={lid}")
        self.assertEqual(code, 200)
        self.assertTrue(body["history"])

    def test_alerts(self):
        code, body = _get(self.base, "/alerts")
        self.assertEqual(code, 200)
        self.assertIn("alerts", body)

    def test_data_source_status(self):
        code, body = _get(self.base, "/data-sources/status")
        self.assertEqual(code, 200)
        self.assertTrue(any(s["source"] == "replay" for s in body["sources"]))

    def test_model_info_default_demo(self):
        code, body = _get(self.base, "/model/info")
        self.assertEqual(code, 200)
        self.assertIn("flood", body["hazards"])
        self.assertIn("landslide", body["hazards"])
        # default path uses demo scorers -> honesty flags must say so
        for hazard in ("flood", "landslide"):
            entry = body["hazards"][hazard]
            self.assertFalse(entry["validated"])
            self.assertTrue(entry["is_demo"])

    def test_model_feature_importance_surface(self):
        code, body = _get(self.base, "/model/feature-importance")
        self.assertEqual(code, 200)
        self.assertIn("flood", body)
        self.assertIn("landslide", body)

    def test_model_status_surface(self):
        code, body = _get(self.base, "/model/status")
        self.assertEqual(code, 200)
        self.assertIn("models", body)
        self.assertIn("status", body)
        self.assertIn("disclaimer", body)
        self.assertFalse(body["models"]["flood"]["validated"])
        self.assertEqual(body["models"]["flood"]["status"], "NOT VALIDATED")

    def test_model_metrics_surface(self):
        code, body = _get(self.base, "/model/metrics")
        self.assertEqual(code, 200)
        self.assertIn("flood", body)
        self.assertIn("landslide", body)
        for h in ("flood", "landslide"):
            self.assertIn("test_metrics", body[h])
            self.assertIn("validation_metrics", body[h])
            self.assertIn("samples", body[h])

    def test_model_explain_surface(self):
        _, all_risk = _get(self.base, "/risk")
        lid = all_risk["risks"][0]["location_id"]
        code, body = _get(self.base, f"/model/explain/{lid}")
        self.assertEqual(code, 200)
        self.assertEqual(body["location_id"], lid)
        self.assertIn("flood", body)
        self.assertIn("landslide", body)
        self.assertIn("combined", body)
        self.assertIn("drivers", body["combined"])

    def test_unknown_route_404(self):
        try:
            _get(self.base, "/nope")
            self.fail("expected HTTPError")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 404)

    def test_post_prediction_run(self):
        _, all_risk = _get(self.base, "/risk")
        lid = all_risk["risks"][0]["location_id"]
        code, body = _post(self.base, "/prediction/run",
                           {"location_id": lid, "as_of": "2024-08-01T10:00:00Z",
                            "mode": "replay"})
        self.assertEqual(code, 200)
        self.assertIn("risk_level", body)

    def test_post_iot_observation(self):
        code, body = _post(self.base, "/iot/observations",
                           {"sensor_id": "test-sensor-1",
                            "ts": "2024-08-01T10:00:00Z",
                            "latitude": 30.05, "longitude": 78.05,
                            "rainfall_mm": 3.0, "soil_moisture": 40.0})
        self.assertEqual(code, 201)
        self.assertTrue(body["stored"])

    def test_post_iot_validation_rejects_bad(self):
        try:
            _post(self.base, "/iot/observations",
                  {"ts": "2024-08-01T10:00:00Z", "latitude": 30.05,
                   "longitude": 78.05})  # missing sensor_id => BAD
            self.fail("expected HTTPError 400")
        except urllib.error.HTTPError as e:
            self.assertEqual(e.code, 400)


if __name__ == "__main__":
    unittest.main()
