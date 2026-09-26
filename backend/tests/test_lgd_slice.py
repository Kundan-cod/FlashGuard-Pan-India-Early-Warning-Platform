"""LGD vertical-slice tests (master prompt sections 7, 34, 40, 66).

Prove — with zero network and zero Track B deps (httpx absent in the portable
sandbox) — that the LGD bridge collector honours every constraint:

  1. A catalog run stores verified LGD directory datasets into `lgd_directory`
     with stage='CATALOG_ONLY' and NO geometry / NO measurement (there is no
     coordinate or numeric column in the catalog schema — none can appear).
  2. A catalog record NEVER fabricates a boundary polygon or an administrative-unit
     row, and never leaks into an observation table ("do not assume LGD directory
     tables are themselves polygon datasets"; "use LGD codes as stable join keys,
     names are display fields only").
  3. Unverified source -> refuses to catalog (ERROR), no invented endpoints.
  4. A successful catalog reports LIVE (verified public LGD portal, no creds).
  5. An optional download-page probe that fails -> honest STALE, but the verified
     catalog rows are still written (directory datasets are verified static
     metadata).
  6. The pure-Python registry->catalog mapping keeps stage=CATALOG_ONLY, uses the
     verified LGD download-portal URL as directory_url (never a guessed file name
     or geometry URL), and copies level/purpose verbatim.
  7. Reingest is idempotent on (source, dataset_key, directory_url).

Unlike CWC (distinct path per dataset), the LGD registry exposes every directory
through the SAME download portal, so — like GSI — dataset_key is what keeps rows
distinct. The collector reads the VENDORED, verified LGD_DATASETS registry; tests
also inject a tiny explicit registry to keep assertions deterministic.
"""
import unittest
from _util import bootstrap
bootstrap()

from app.database import db, repositories as repo
from app.collectors import lgd_mapping as M
from app.collectors.lgd_collector import LgdCollector


def _sample_registry():
    """A deterministic stand-in mirroring the vendored LGD_DATASETS shape. Every
    dataset shares the SAME download portal, so dataset_key keeps rows distinct."""
    return {
        "districts": {"level": "DISTRICT",
                      "purpose": "district identity and codes"},
        "villages": {"level": "VILLAGE",
                     "purpose": "village identity and codes"},
    }


class _FakeClientReachable:
    def fetch_directory_page(self):
        return "<html>Districts Villages Wards</html>"


class _FakeClientUnreachable:
    def fetch_directory_page(self):
        raise ConnectionError("simulated: LGD portal unreachable")


class LgdSliceTest(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)

    # ---- 1 + 2: catalog stores directory datasets, never geometry/values ----
    def test_catalog_stores_datasets_and_never_geometry(self):
        c = LgdCollector(verified=True, registry=_sample_registry())
        res = c.run()
        self.assertEqual(res.stored, 2, "expected 2 catalog records")

        rows = repo.lgd_directory_recent()
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")
            self.assertEqual(r["source"], "lgd")
            self.assertTrue(r["directory_url"], "directory_url must be present")
            self.assertTrue(r["admin_level"], "admin_level must be present")
            # honesty: the catalog schema has NO geometry / numeric column at all.
            self.assertNotIn("latitude", r)
            self.assertNotIn("longitude", r)
            self.assertNotIn("geometry", r)

    # ---- 3: unverified source refuses to catalog (honest ERROR) ----
    def test_unverified_source_refuses_and_reports_error(self):
        c = LgdCollector(verified=False, registry=_sample_registry())
        with self.assertRaises(RuntimeError):
            c.run()
        health = repo.get_source_health("lgd")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "ERROR")
        self.assertEqual(len(repo.lgd_directory_recent()), 0)

    # ---- 4: successful catalog reports LIVE (verified public portal, no creds) --
    def test_successful_catalog_reports_live(self):
        c = LgdCollector(verified=True, registry=_sample_registry())
        c.run()
        health = repo.get_source_health("lgd")
        self.assertEqual(health["status"], "LIVE")
        self.assertIsNotNone(health["last_success_at"])
        self.assertTrue(any("catalog-only" in n for n in c._stage_notes),
                        f"expected a catalog-only parse note; got {c._stage_notes}")

    # ---- 4b: pure catalog with no probe also LIVE and reads vendored registry ----
    def test_pure_catalog_uses_vendored_registry(self):
        c = LgdCollector(verified=True)  # no registry override -> vendored
        res = c.run()
        self.assertGreater(res.stored, 0,
                           "vendored LGD_DATASETS should yield catalog rows")
        self.assertEqual(repo.get_source_health("lgd")["status"], "LIVE")
        rows = repo.lgd_directory_recent(limit=100)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")
            # every directory_url must be a verified lgdirectory.gov.in host.
            self.assertIn("lgdirectory.gov.in", r["directory_url"])

    # ---- 5a: reachable probe keeps LIVE ----
    def test_reachable_probe_keeps_live(self):
        c = LgdCollector(verified=True, registry=_sample_registry(),
                         client=_FakeClientReachable())
        res = c.run()
        self.assertEqual(res.stored, 2)
        self.assertEqual(repo.get_source_health("lgd")["status"], "LIVE")
        self.assertTrue(any("reachable" in n for n in c._stage_notes))

    # ---- 5b: failed probe -> STALE, but verified catalog rows still written ----
    def test_unreachable_probe_is_stale_but_catalog_written(self):
        c = LgdCollector(verified=True, registry=_sample_registry(),
                         client=_FakeClientUnreachable())
        res = c.run()
        self.assertEqual(res.stored, 2,
                         "verified catalog rows are written even if probe fails")
        health = repo.get_source_health("lgd")
        self.assertEqual(health["status"], "STALE")
        self.assertIsNone(health["last_success_at"],
                          "STALE (unreachable) is not a full success")
        self.assertTrue(any("unreachable" in n for n in c._stage_notes))

    # ---- 6: mapping keeps CATALOG_ONLY, uses portal URL, copies fields verbatim
    def test_mapping_uses_portal_url_and_catalog_only(self):
        rec = M.registry_entry_to_catalog_record(
            "villages",
            _sample_registry()["villages"],
            retrieved_at="2026-09-06T00:00:00Z")
        self.assertEqual(rec["stage"], M.CATALOG_ONLY)
        self.assertEqual(rec["dataset_key"], "villages")
        self.assertEqual(rec["admin_level"], "VILLAGE")
        self.assertEqual(rec["purpose"], "village identity and codes")
        # directory_url = the verified LGD download portal (never a guessed file).
        self.assertEqual(
            rec["directory_url"],
            "https://lgdirectory.gov.in/demo/downloadDirectory.do")
        # honesty: mapping never emits a coordinate or numeric value.
        self.assertNotIn("latitude", rec)
        self.assertNotIn("geometry", rec)

    def test_mapping_shares_portal_url_across_datasets(self):
        recs = M.registry_to_catalog_records(_sample_registry())
        self.assertEqual(len(recs), 2)
        urls = {r["directory_url"] for r in recs}
        # Like GSI, every dataset shares ONE verified portal URL; dataset_key is
        # what keeps the rows distinct (never an invented per-dataset URL).
        self.assertEqual(len(urls), 1)
        self.assertEqual({r["dataset_key"] for r in recs},
                         {"districts", "villages"})

    # ---- 7: reingest is idempotent on (source, dataset_key, directory_url) ----
    def test_reingest_is_idempotent(self):
        reg = _sample_registry()
        LgdCollector(verified=True, registry=reg).run()
        LgdCollector(verified=True, registry=reg).run()
        self.assertEqual(len(repo.lgd_directory_recent()), 2,
                         "re-cataloging the same datasets must not duplicate rows")


if __name__ == "__main__":
    unittest.main()
