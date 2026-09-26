import json
import unittest

from _util import bootstrap
bootstrap()

from app.llm.service import LLMBriefingService
from app.database import db, repositories as repo
from app.features.engineer import build_features


class TestLLMBriefingService(unittest.TestCase):
    def setUp(self):
        db.init_db()
        self.location = {
            "id": 1,
            "name": "Devgaon",
            "level": "village",
            "district": "Nainital",
            "state": "Uttarakhand",
        }
        self.prediction = {
            "flood_probability": 0.85,
            "landslide_probability": 0.72,
            "risk_level": "CRITICAL",
            "confidence": 0.91,
            "lead_time_min_lo": 15,
            "lead_time_min_hi": 45,
            "top_factors": [
                {"factor": "Rainfall Intensity", "contribution": 0.38},
                {"factor": "Soil Saturation", "contribution": 0.28},
            ],
        }
        self.telemetry = {
            "rainfall": 65.0,
            "soil_moisture": 88.0,
            "river_level": 2.8,
            "slope": 32.0,
        }

    def test_prompt_generation_all_personas(self):
        for persona in ("PUBLIC_ALERT", "PUBLIC_ALERT_HINDI", "NDRF_TACTICAL", "EXECUTIVE_SUMMARY"):
            prompt = LLMBriefingService.build_prompt(
                self.location, self.prediction, self.telemetry, persona=persona
            )
            self.assertIn("Devgaon", prompt)
            self.assertIn("Nainital", prompt)
            self.assertIn("CRITICAL", prompt)
            self.assertTrue(len(prompt) > 100)

    def test_offline_synthesis_public_alert_english(self):
        res = LLMBriefingService.generate_briefing(
            self.location, self.prediction, self.telemetry, persona="PUBLIC_ALERT"
        )
        self.assertEqual(res["persona"], "PUBLIC_ALERT")
        self.assertEqual(res["location_name"], "Devgaon")
        self.assertIn("EMERGENCY ADVISORY", res["briefing"])
        self.assertIn("MOVE TO HIGHER GROUND", res["briefing"])
        self.assertIn("1077", res["briefing"])

    def test_offline_synthesis_public_alert_hindi(self):
        res = LLMBriefingService.generate_briefing(
            self.location, self.prediction, self.telemetry, persona="PUBLIC_ALERT_HINDI"
        )
        self.assertEqual(res["persona"], "PUBLIC_ALERT_HINDI")
        self.assertIn("आपातकालीन जन-चेतावनी", res["briefing"])
        self.assertIn("ऊंचे स्थानों", res["briefing"])
        self.assertIn("112", res["briefing"])

    def test_offline_synthesis_ndrf_tactical(self):
        res = LLMBriefingService.generate_briefing(
            self.location, self.prediction, self.telemetry, persona="NDRF_TACTICAL"
        )
        self.assertEqual(res["persona"], "NDRF_TACTICAL")
        self.assertIn("NDRF TACTICAL OPERATION BRIEFING", res["briefing"])
        self.assertIn("CHOKE POINTS", res["briefing"])
        self.assertIn("QRT", res["briefing"])

    def test_offline_synthesis_dm_executive_summary(self):
        res = LLMBriefingService.generate_briefing(
            self.location, self.prediction, self.telemetry, persona="EXECUTIVE_SUMMARY"
        )
        self.assertEqual(res["persona"], "EXECUTIVE_SUMMARY")
        self.assertIn("DISTRICT MAGISTRATE EXECUTIVE SUMMARY", res["briefing"])
        self.assertIn("INTER-AGENCY MOBILIZATION", res["briefing"])


if __name__ == "__main__":
    unittest.main()
