"""Historical-labels vertical-slice tests (master prompt sections 7, 34, 40, 66).

Prove — with zero network and zero Track B deps (httpx/pydantic absent in the
portable sandbox) — that the historical-labels bridge collector honours every
constraint:

  1. A catalog run stores the verified historical-event SOURCES into
     `historical_sources` with stage='CATALOG_ONLY' and NO event geometry / NO event
     time / NO training label (there is no coordinate, time or numeric-label column
     in the catalog schema — none can appear).
  2. A catalog record NEVER fabricates a confirmed event or a 1/0/-1 label, and
     never leaks into an events/labels or observation table ("do not interpret the
     inventory as a complete nationwide absence/presence census"; "do not convert
     missing observations into negatives").
  3. Unverified source -> refuses to catalog (ERROR), no invented sources.
  4. A successful catalog reports LIVE (verified public source references, no creds).
  5. An optional source-page probe that fails -> honest STALE, but the verified
     catalog rows are still written (the sources are verified static metadata).
  6. The pure-Python registry->catalog mapping keeps stage=CATALOG_ONLY, copies
     hazard/role/url/period/access verbatim, and — unlike LGD/GSI (one shared portal
     URL) — gives each source its OWN source_url (like CWC).
  7. Reingest is idempotent on (source, source_key, source_url).

The collector reads the VENDORED, verified HISTORICAL_SOURCES registry; tests also
inject a tiny explicit registry to keep assertions deterministic.
"""
import unittest
from _util import bootstrap
bootstrap()

from app.database import db, repositories as repo
from app.collectors import historical_mapping as M
from app.collectors.historical_collector import HistoricalCollector


def _sample_registry():
    """A deterministic stand-in mirroring the vendored HISTORICAL_SOURCES shape.
    Each source keeps its OWN url, so source_url keeps rows distinct (like CWC)."""
    return {
        "nrsc_landslide_atlas": {
            "hazard": "LANDSLIDE",
            "url": "https://www.nrsc.gov.in/nrscnew/resources_atlas_landslide.php",
            "period": "1998-2022",
            "role": "historical_landslide_inventory",
        },
        "ndem_historical_disasters": {
            "hazard": "FLOOD_OR_LANDSLIDE",
            "url": "https://ndem.nrsc.gov.in/",
            "period": "1999-present",
            "role": "event_specific_historical_reference",
            "access": "portal/authentication dependent",
        },
    }


class _FakeClientReachable:
    def fetch_source_page(self):
        return "<html>NRSC Landslide Atlas</html>"


class _FakeClientUnreachable:
    def fetch_source_page(self):
        raise ConnectionError("simulated: historical source unreachable")


class HistoricalSliceTest(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)

    # ---- 1 + 2: catalog stores sources, never events/geometry/labels ----
    def test_catalog_stores_sources_and_never_events_or_labels(self):
        c = HistoricalCollector(verified=True, registry=_sample_registry())
        res = c.run()
        self.assertEqual(res.stored, 2, "expected 2 catalog records")

        rows = repo.historical_sources_recent()
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")
            self.assertEqual(r["source"], "historical")
            self.assertTrue(r["source_url"], "source_url must be present")
            self.assertTrue(r["source_key"], "source_key must be present")
            self.assertIn(r["hazard"],
                          {"FLOOD", "LANDSLIDE", "FLOOD_OR_LANDSLIDE"})
            # honesty: the catalog schema has NO event/label column at all.
            self.assertNotIn("latitude", r)
            self.assertNotIn("longitude", r)
            self.assertNotIn("geometry", r)
            self.assertNotIn("event_time", r)
            self.assertNotIn("target", r)
            self.assertNotIn("label", r)

    # ---- 3: unverified source refuses to catalog (honest ERROR) ----
    def test_unverified_source_refuses_and_reports_error(self):
        c = HistoricalCollector(verified=False, registry=_sample_registry())
        with self.assertRaises(RuntimeError):
            c.run()
        health = repo.get_source_health("historical")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "ERROR")
        self.assertEqual(len(repo.historical_sources_recent()), 0)

    # ---- 4: successful catalog reports LIVE (verified sources, no creds) ----
    def test_successful_catalog_reports_live(self):
        c = HistoricalCollector(verified=True, registry=_sample_registry())
        c.run()
        health = repo.get_source_health("historical")
        self.assertEqual(health["status"], "LIVE")
        self.assertIsNotNone(health["last_success_at"])
        self.assertTrue(any("catalog-only" in n for n in c._stage_notes),
                        f"expected a catalog-only parse note; got {c._stage_notes}")

    # ---- 4b: pure catalog with no probe also LIVE and reads vendored registry ----
    def test_pure_catalog_uses_vendored_registry(self):
        c = HistoricalCollector(verified=True)  # no override -> vendored
        res = c.run()
        self.assertGreater(res.stored, 0,
                           "vendored HISTORICAL_SOURCES should yield catalog rows")
        self.assertEqual(repo.get_source_health("historical")["status"], "LIVE")
        rows = repo.historical_sources_recent(limit=100)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")
            # every source_url must be a real verified reference (nrsc/ndem host).
            self.assertTrue(
                ("nrsc.gov.in" in (r["source_url"] or "")),
                f"unexpected source_url {r['source_url']!r}")

    # ---- 5a: reachable probe keeps LIVE ----
    def test_reachable_probe_keeps_live(self):
        c = HistoricalCollector(verified=True, registry=_sample_registry(),
                                client=_FakeClientReachable())
        res = c.run()
        self.assertEqual(res.stored, 2)
        self.assertEqual(repo.get_source_health("historical")["status"], "LIVE")
        self.assertTrue(any("reachable" in n for n in c._stage_notes))

    # ---- 5b: failed probe -> STALE, but verified catalog rows still written ----
    def test_unreachable_probe_is_stale_but_catalog_written(self):
        c = HistoricalCollector(verified=True, registry=_sample_registry(),
                                client=_FakeClientUnreachable())
        res = c.run()
        self.assertEqual(res.stored, 2,
                         "verified catalog rows are written even if probe fails")
        health = repo.get_source_health("historical")
        self.assertEqual(health["status"], "STALE")
        self.assertIsNone(health["last_success_at"],
                          "STALE (unreachable) is not a full success")
        self.assertTrue(any("unreachable" in n for n in c._stage_notes))

    # ---- 6: mapping keeps CATALOG_ONLY, copies fields verbatim, own url ----
    def test_mapping_copies_fields_and_catalog_only(self):
        rec = M.registry_entry_to_catalog_record(
            "ndem_historical_disasters",
            _sample_registry()["ndem_historical_disasters"],
            retrieved_at="2026-09-06T00:00:00Z")
        self.assertEqual(rec["stage"], M.CATALOG_ONLY)
        self.assertEqual(rec["source_key"], "ndem_historical_disasters")
        self.assertEqual(rec["hazard"], "FLOOD_OR_LANDSLIDE")
        self.assertEqual(rec["role"], "event_specific_historical_reference")
        self.assertEqual(rec["source_url"], "https://ndem.nrsc.gov.in/")
        self.assertEqual(rec["period"], "1999-present")
        self.assertEqual(rec["access_note"], "portal/authentication dependent")
        # honesty: mapping never emits an event geometry, event time or a label.
        self.assertNotIn("latitude", rec)
        self.assertNotIn("geometry", rec)
        self.assertNotIn("event_time", rec)
        self.assertNotIn("target", rec)

    def test_mapping_gives_each_source_its_own_url(self):
        recs = M.registry_to_catalog_records(_sample_registry())
        self.assertEqual(len(recs), 2)
        urls = {r["source_url"] for r in recs}
        # Unlike LGD/GSI (one shared portal URL), each historical source keeps its
        # own official url — like CWC, source_url differs per row.
        self.assertEqual(len(urls), 2)
        self.assertEqual({r["source_key"] for r in recs},
                         {"nrsc_landslide_atlas", "ndem_historical_disasters"})

    # ---- 7: reingest is idempotent on (source, source_key, source_url) ----
    def test_reingest_is_idempotent(self):
        reg = _sample_registry()
        HistoricalCollector(verified=True, registry=reg).run()
        HistoricalCollector(verified=True, registry=reg).run()
        self.assertEqual(len(repo.historical_sources_recent()), 2,
                         "re-cataloging the same sources must not duplicate rows")


if __name__ == "__main__":
    unittest.main()
