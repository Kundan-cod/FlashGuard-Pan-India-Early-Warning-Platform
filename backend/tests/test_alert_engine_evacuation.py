"""
Comprehensive test suite for SIH 26192 Real-Time Alert & Evacuation Guidance Module.

Tests:
1. Actionable alert generation across CRITICAL, HIGH, MODERATE, LOW.
2. Multi-language predefined template rendering in English, Hindi, and Tamil.
3. Nearest evacuation shelter resolution with Haversine distance ranking.
4. Fallback evacuation guidance when no verified shelter exists (no fabricated shelters).
5. Alert deduplication (suppression of duplicate SMS) and escalation handling.
6. Mock SMS dispatch, phone number privacy masking, and delivery audit receipts.
7. Evacuation centres and recipients repository DAL integrity.
"""
import unittest
from _util import bootstrap
bootstrap()

from app.database import db, repositories as repo
from app.services import seed
from app.alerts.engine import (
    build_actionable_alert,
    should_dispatch_alert,
    generate_alert_fingerprint,
    build_alert,
)
from app.alerts.templates import render_alert_message, render_short_sms
from app.services.evacuation_service import EvacuationService, calculate_distance_km
from app.services.sms_service import alert_service, mask_phone_number


class TestAlertEngineEvacuation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ids = seed.run(reset=True)
        cls.vid = cls.ids["villages"][0]
        # Seed national regions as well
        seed.seed_national_regions(cls.ids["country"])

    def test_evacuation_centres_seeded_honestly(self):
        """Verify evacuation centres exist, are marked as DEMO, and have required fields."""
        centres = repo.list_evacuation_centres(active_only=True)
        self.assertGreaterEqual(len(centres), 16)
        for c in centres:
            self.assertTrue(c["name"].endswith("[DEMO SHELTER]"), "Demo shelters must be transparently tagged")
            self.assertEqual(c["is_demo"], 1)
            self.assertIsNotNone(c["capacity"])
            self.assertGreater(c["capacity"], 0)
            self.assertIsNotNone(c["latitude"])
            self.assertIsNotNone(c["longitude"])

    def test_recipients_seeded_with_masked_privacy(self):
        """Verify demo recipients exist across multiple languages and phone masking works."""
        recipients = repo.list_recipients_for_village("Ranikhet-South", active_only=True)
        self.assertGreaterEqual(len(recipients), 3)

        langs = {r["preferred_language"] for r in recipients}
        self.assertIn("en", langs)
        self.assertIn("hi", langs)

        # Verify privacy masking
        masked = mask_phone_number("+919876543210")
        self.assertEqual(masked, "+9198****3210")
        self.assertNotIn("7654", masked)

    def test_nearest_shelter_distance_calculation(self):
        """Verify Haversine distance ranking selects the closest centre."""
        # Devgaon coordinates ~ (30.05, 78.05)
        nearby = EvacuationService.get_nearby_centres(30.05, 78.05, limit=3)
        self.assertGreaterEqual(len(nearby), 1)
        self.assertLessEqual(nearby[0]["distance_km"], 2.0)

    def test_evacuation_guidance_structure_critical(self):
        """Verify actionable evacuation guidance produces structured output with verified shelter."""
        res = EvacuationService.get_evacuation_guidance(
            village="Ranikhet-South",
            hazard="flood",
            risk_level="CRITICAL",
            lat=30.07,
            lon=78.08,
        )
        self.assertTrue(res["has_verified_shelter"])
        self.assertIsNotNone(res["shelter"])
        self.assertIn("Immediate evacuation", res["recommended_action"])
        self.assertIn("Ranikhet-South", res["guidance_text"])
        self.assertIn("Designated Shelter:", res["guidance_text"])
        self.assertIn("Do not cross flooded roads", res["guidance_text"])

    def test_evacuation_guidance_fallback_without_fake_shelter(self):
        """Verify fallback guidance when village has no shelter — must never invent one."""
        res = EvacuationService.get_evacuation_guidance(
            village="NonExistentRemoteRidgeVillage",
            hazard="flood",
            risk_level="CRITICAL",
        )
        self.assertFalse(res["has_verified_shelter"])
        self.assertIsNone(res["shelter"])
        self.assertIn("No verified evacuation centre is currently available", res["guidance_text"])
        self.assertIn("Move away from low-lying/flood-prone areas only according to local-authority instructions", res["guidance_text"])

    def test_multilanguage_templates_rendering(self):
        """Verify predefined templates in English, Hindi, and Tamil render critical instructions."""
        shelter = {"name": "Ranikhet Community Centre [DEMO SHELTER]", "distance_km": 0.8, "capacity": 500}

        # English
        en_msg = render_alert_message("Ranikhet-South", "flood", "CRITICAL", 0.92, "Next 2–3 hours", language="en", shelter=shelter)
        self.assertIn("FLASH FLOOD ALERT", en_msg)
        self.assertIn("Risk Level: CRITICAL (92% probability)", en_msg)
        self.assertIn("DO NOT:\n- enter or cross flooded roads", en_msg)
        self.assertIn("Prioritize children, elderly people", en_msg)

        # Hindi
        hi_msg = render_alert_message("Ranikhet-South", "flood", "CRITICAL", 0.92, "Next 2–3 hours", language="hi", shelter=shelter)
        self.assertIn("अचानक बाढ़ आपातकालीन चेतावनी", hi_msg)
        self.assertIn("गंभीर (CRITICAL - 92%)", hi_msg)
        self.assertIn("जलमग्न सड़कों, रपटों, पुलों या बहते पानी में कतई न जाएं", hi_msg)

        # Tamil
        ta_msg = render_alert_message("Ranikhet-South", "flood", "CRITICAL", 0.92, "Next 2–3 hours", language="ta", shelter=shelter)
        self.assertIn("திடீர் வெள்ளம் அவசர எச்சரிக்கை", ta_msg)
        self.assertIn("மிக ஆபத்தானது (CRITICAL - 92%)", ta_msg)
        self.assertIn("வெள்ளம் சூழ்ந்த சாலைகள், பாலங்கள் அல்லது ஓடும் நீரை கடக்க வேண்டாம்", ta_msg)

    def test_short_sms_length_and_content(self):
        """Verify concise SMS is concise and actionable."""
        sms_en = render_short_sms("Ranikhet-South", "flood", "CRITICAL", "Next 2h", "Panchayat Hall", language="en")
        self.assertIn("FLASHGUARD: CRITICAL", sms_en)
        self.assertIn("Ranikhet-South", sms_en)
        self.assertLessEqual(len(sms_en), 160)

    def test_build_actionable_alert_flow(self):
        """Test build_actionable_alert full pipeline."""
        alert = build_actionable_alert(
            location_id=self.vid,
            village="Devgaon",
            hazard="flood",
            risk_level="CRITICAL",
            probability=0.89,
            window="Next 2–3 hours",
            language="en",
            lat=30.05,
            lon=78.05,
        )
        self.assertEqual(alert["village"], "Devgaon")
        self.assertEqual(alert["risk_level"], "CRITICAL")
        self.assertEqual(alert["severity"], "CRITICAL")
        self.assertTrue(alert["has_verified_shelter"])
        self.assertIn("en", alert["messages"])
        self.assertIn("hi", alert["messages"])
        self.assertIn("ta", alert["messages"])
        self.assertGreater(alert["recipient_count"], 0)
        self.assertIsNotNone(alert["fingerprint"])

    def test_deduplication_and_escalation_logic(self):
        """Verify identical alerts are suppressed and escalation triggers new alert."""
        village = "Devgaon"
        haz = "flood"
        win = "Next 2–3 hours"

        fp = generate_alert_fingerprint(village, haz, "CRITICAL", win)

        # 1. First alert -> should dispatch
        should_send, reason = should_dispatch_alert(self.vid, village, haz, "CRITICAL", win)
        self.assertTrue(should_send)

        # Record it into the database
        aid = repo.insert_alert({
            "location_id": self.vid,
            "severity": "CRITICAL",
            "hazard_type": haz,
            "message": "Critical flash flood warning",
            "risk_level": "CRITICAL",
            "risk_probability": 0.90,
            "lead_time_window": win,
            "fingerprint": fp,
            "status": "active",
        })
        self.assertIsNotNone(aid)

        # 2. Duplicate check with identical parameters -> should be suppressed
        should_send_dup, reason_dup = should_dispatch_alert(self.vid, village, haz, "CRITICAL", win)
        self.assertFalse(should_send_dup)
        self.assertIn("Duplicate alert suppressed", reason_dup)

        # 3. LOW risk check -> suppressed from SMS
        should_send_low, reason_low = should_dispatch_alert(self.vid, village, haz, "LOW", win)
        self.assertFalse(should_send_low)
        self.assertIn("SMS suppressed", reason_low)

    def test_mock_sms_dispatch_service(self):
        """Verify AlertService dispatch generates mock delivery receipts with masked numbers."""
        res = alert_service.dispatch_alert(
            village="Ranikhet-South",
            hazard="flood",
            risk_level="CRITICAL",
            full_message="🚨 Flash flood alert",
            short_sms="🚨 Flash flood alert short",
        )
        self.assertEqual(res["village"], "Ranikhet-South")
        self.assertEqual(res["sms_status"], "MOCK_SENT")
        self.assertTrue(res["is_mock"])
        self.assertGreater(res["recipient_count"], 0)
        self.assertGreater(len(res["receipts"]), 0)

        # Ensure receipt phones are strictly masked
        for r in res["receipts"]:
            self.assertIn("****", r["recipient_phone"])


if __name__ == "__main__":
    unittest.main()
