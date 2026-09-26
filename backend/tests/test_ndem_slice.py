"""NDEM vertical-slice tests (master prompt sections 7, 24, 32, 40, 66).

Prove — with zero network and zero Track B deps (httpx/pydantic absent in the
portable sandbox) — that the NDEM bridge collector honours every constraint:

  1. A catalog run stores the verified NDEM CAPABILITIES into `ndem_capabilities`
     with stage='CATALOG_ONLY' and NO measurement / NO geometry / NO event / NO risk
     score (there is no coordinate, value, event or risk column in the catalog schema
     — none can appear).
  2. A catalog record NEVER fabricates a measurement or a risk score, and the access
     level (PUBLIC | AUTHORIZED | AUTHORIZED_OR_PRODUCT_SPECIFIC) is preserved
     verbatim as metadata, stored separately from any risk score. Protected products
     are never bypassed.
  3. Unverified source -> refuses to catalog (ERROR), no invented capabilities.
  4. A successful catalog reports LIVE (verified public portal, no creds).
  5. An optional public-portal probe that fails -> honest STALE, but the verified
     catalog rows are still written (the capabilities are verified static metadata).
  6. The pure-Python registry->catalog mapping keeps stage=CATALOG_ONLY, copies
     access/role/source_url verbatim, and — like GSI/LGD (one shared portal URL) —
     gives every capability the SAME source_url so capability_key keeps rows distinct.
  7. Reingest is idempotent on (source, capability_key, source_url).

The collector reads the VENDORED, verified NDEM_CAPABILITIES registry; tests also
inject a tiny explicit registry to keep assertions deterministic.
"""
import unittest
from _util import bootstrap
bootstrap()

from app.database import db, repositories as repo
from app.collectors import ndem_mapping as M
from app.collectors.ndem_collector import NdemCollector


def _sample_registry():
    """A deterministic stand-in mirroring the vendored NDEM_CAPABILITIES shape.
    Every capability shares the SAME public portal URL (like GSI/LGD), so
    capability_key keeps rows distinct."""
    return {
        "public_base_layers": {
            "access": "PUBLIC",
            "role": "base/context layers",
            "source_url": "https://ndem.nrsc.gov.in",
        },
        "near_real_time_flood": {
            "access": "AUTHORIZED",
            "role": "near-real-time flood products",
            "source_url": "https://ndem.nrsc.gov.in",
        },
        "historical_flood_data": {
            "access": "AUTHORIZED_OR_PRODUCT_SPECIFIC",
            "role": "historical flood reference",
            "source_url": "https://ndem.nrsc.gov.in",
        },
    }


class _FakeClientReachable:
    def check_public_portal(self):
        return "<html>NDEM</html>"


class _FakeClientUnreachable:
    def check_public_portal(self):
        raise ConnectionError("simulated: NDEM public portal unreachable")


class NdemSliceTest(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)

    # ---- 1 + 2: catalog stores capabilities, never measurements/geometry/risk ----
    def test_catalog_stores_capabilities_and_never_values_or_risk(self):
        c = NdemCollector(verified=True, registry=_sample_registry())
        res = c.run()
        self.assertEqual(res.stored, 3, "expected 3 catalog records")

        rows = repo.ndem_capabilities_recent()
        self.assertEqual(len(rows), 3)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")
            self.assertEqual(r["source"], "ndem")
            self.assertTrue(r["source_url"], "source_url must be present")
            self.assertTrue(r["capability_key"], "capability_key must be present")
            # access preserved verbatim, stored separately from any risk score.
            self.assertIn(r["access"],
                          {"PUBLIC", "AUTHORIZED", "AUTHORIZED_OR_PRODUCT_SPECIFIC"})
            # honesty: the catalog schema has NO measurement/geometry/event/risk col.
            self.assertNotIn("latitude", r)
            self.assertNotIn("longitude", r)
            self.assertNotIn("geometry", r)
            self.assertNotIn("numeric_value", r)
            self.assertNotIn("risk_score", r)
            self.assertNotIn("event_time", r)

    # ---- 3: unverified source refuses to catalog (honest ERROR) ----
    def test_unverified_source_refuses_and_reports_error(self):
        c = NdemCollector(verified=False, registry=_sample_registry())
        with self.assertRaises(RuntimeError):
            c.run()
        health = repo.get_source_health("ndem")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "ERROR")
        self.assertEqual(len(repo.ndem_capabilities_recent()), 0)

    # ---- 4: successful catalog reports LIVE (verified portal, no creds) ----
    def test_successful_catalog_reports_live(self):
        c = NdemCollector(verified=True, registry=_sample_registry())
        c.run()
        health = repo.get_source_health("ndem")
        self.assertEqual(health["status"], "LIVE")
        self.assertIsNotNone(health["last_success_at"])
        self.assertTrue(any("catalog" in n for n in c._stage_notes),
                        f"expected a catalog parse note; got {c._stage_notes}")
        # honest access-split visibility in the notes (metadata, never auth bypass).
        self.assertTrue(any("PUBLIC" in n and "AUTHORIZED" in n
                            for n in c._stage_notes))

    # ---- 4b: pure catalog with no probe also LIVE and reads vendored registry ----
    def test_pure_catalog_uses_vendored_registry(self):
        c = NdemCollector(verified=True)  # no override -> vendored
        res = c.run()
        self.assertGreater(res.stored, 0,
                           "vendored NDEM_CAPABILITIES should yield catalog rows")
        self.assertEqual(repo.get_source_health("ndem")["status"], "LIVE")
        rows = repo.ndem_capabilities_recent(limit=100)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")
            # every source_url must be the verified NDEM portal host.
            self.assertTrue(
                ("ndem.nrsc.gov.in" in (r["source_url"] or "")),
                f"unexpected source_url {r['source_url']!r}")

    # ---- 5a: reachable probe keeps LIVE ----
    def test_reachable_probe_keeps_live(self):
        c = NdemCollector(verified=True, registry=_sample_registry(),
                          client=_FakeClientReachable())
        res = c.run()
        self.assertEqual(res.stored, 3)
        self.assertEqual(repo.get_source_health("ndem")["status"], "LIVE")
        self.assertTrue(any("reachable" in n for n in c._stage_notes))

    # ---- 5b: failed probe -> STALE, but verified catalog rows still written ----
    def test_unreachable_probe_is_stale_but_catalog_written(self):
        c = NdemCollector(verified=True, registry=_sample_registry(),
                          client=_FakeClientUnreachable())
        res = c.run()
        self.assertEqual(res.stored, 3,
                         "verified catalog rows are written even if probe fails")
        health = repo.get_source_health("ndem")
        self.assertEqual(health["status"], "STALE")
        self.assertIsNone(health["last_success_at"],
                          "STALE (unreachable) is not a full success")
        self.assertTrue(any("unreachable" in n for n in c._stage_notes))

    # ---- 6: mapping keeps CATALOG_ONLY, copies fields verbatim, shared url ----
    def test_mapping_copies_fields_and_catalog_only(self):
        rec = M.registry_entry_to_catalog_record(
            "near_real_time_flood",
            _sample_registry()["near_real_time_flood"],
            retrieved_at="2026-09-06T00:00:00Z")
        self.assertEqual(rec["stage"], M.CATALOG_ONLY)
        self.assertEqual(rec["capability_key"], "near_real_time_flood")
        self.assertEqual(rec["access"], "AUTHORIZED")
        self.assertEqual(rec["role"], "near-real-time flood products")
        self.assertEqual(rec["source_url"], "https://ndem.nrsc.gov.in")
        # honesty: mapping never emits a measurement, geometry, event or risk score.
        self.assertNotIn("latitude", rec)
        self.assertNotIn("geometry", rec)
        self.assertNotIn("numeric_value", rec)
        self.assertNotIn("risk_score", rec)
        self.assertNotIn("event_time", rec)

    def test_mapping_shares_one_portal_url(self):
        recs = M.registry_to_catalog_records(_sample_registry())
        self.assertEqual(len(recs), 3)
        urls = {r["source_url"] for r in recs}
        # Like GSI/LGD (one shared portal URL), every NDEM capability uses the SAME
        # public portal URL — capability_key is what keeps rows distinct.
        self.assertEqual(len(urls), 1)
        self.assertEqual({r["capability_key"] for r in recs},
                         {"public_base_layers", "near_real_time_flood",
                          "historical_flood_data"})

    # ---- 7: reingest is idempotent on (source, capability_key, source_url) ----
    def test_reingest_is_idempotent(self):
        reg = _sample_registry()
        NdemCollector(verified=True, registry=reg).run()
        NdemCollector(verified=True, registry=reg).run()
        self.assertEqual(len(repo.ndem_capabilities_recent()), 3,
                         "re-cataloging the same capabilities must not duplicate rows")


if __name__ == "__main__":
    unittest.main()
