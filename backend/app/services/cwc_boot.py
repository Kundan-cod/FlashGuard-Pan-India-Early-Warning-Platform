"""
CWC/NWIC boot probe (Track B) — makes CWC's runtime status HONEST and verifiable.

Mirrors gpm_boot / smap_boot / mosdac_boot / bhuvan_boot / gsi_boot. Phase 1
(replay) never touches CWC, so without this probe the `cwc` source would be absent
from source_health and nothing would ever build the dataset catalog. That would
make it impossible to runtime-verify:
  * CWC reported LIVE once the verified NWDP dataset catalog is written,
  * the catalog run inserts nothing into river_observations / rainfall_observations
    (catalog-only honesty),
  * every cwc_resources row is stage='CATALOG_ONLY' with no numeric hydro value.

On boot we construct the CwcCollector straight from config/data_sources.yml and
run it exactly once. Cataloging the verified registry is an OFFLINE operation over
verified static metadata (the NWDP portal is hard-coded and public in the vendored
config), so the honest outcome is:

  verified=false in yaml   -> refuses to catalog                 -> ERROR
  verified=true            -> catalogs the verified registry     -> LIVE

This NEVER runs the ML pipeline and NEVER writes observation tables — catalog rows
go only to cwc_resources. Replay stays the known-good default and is completely
unaffected: this probe runs after seed + replay and only reports health / stores
the verified dataset catalog.

Toggle with CWC_CATALOG_ON_BOOT (default "1"). Set "0" to skip the probe.

IMPORTANT (import ordering): this module imports the CWC collector, which binds
`from app.database import repositories as repo`. It must be imported AFTER the
repositories_prod swap (seed_prod installs the swap first), or the probe would
write to the wrong DAL. seed_prod imports it lazily for that reason.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "data_sources.yml"


# Kept in lockstep with the identical lists in seed_prod.py, main.py, gpm_boot.py,
# smap_boot.py, imd_boot.py, mosdac_boot.py, bhuvan_boot.py and gsi_boot.py. If
# cwc_boot is invoked DIRECTLY in a Track B environment, the PostGIS swap normally
# performed by seed_prod has NOT happened; the standalone entrypoint installs the
# swap itself, and this list lets it fail loudly if a consumer was imported too
# early (silent no-op swap).
_CONSUMER_MODULES = (
    "app.database.repositories", "app.features.engineer",
    "app.services.seed", "app.services.replay_driver",
    "app.services.prediction_service", "app.collectors.replay_collector",
    "app.collectors.http_source_collector", "app.collectors.gpm_collector",
    "app.collectors.smap_collector", "app.collectors.imd_collector",
    "app.collectors.mosdac_collector", "app.collectors.bhuvan_collector",
    "app.collectors.gsi_collector", "app.collectors.cwc_collector",
    "app.collectors.lgd_collector", "app.collectors.historical_collector",
    "app.collectors.ndem_collector",
)


def _looks_like_postgres() -> bool:
    url = (os.environ.get("DATABASE_URL") or "").lower()
    return url.startswith("postgres") or "postgresql" in url


def _install_prod_repositories() -> None:
    already = [m for m in _CONSUMER_MODULES if m in sys.modules]
    if already:
        raise RuntimeError(
            "cwc_boot: repositories_prod swap would be ineffective; these DAL "
            f"consumers were imported before the swap: {already}. Do not import "
            "collectors/services before calling _install_prod_repositories().")
    from app.database import repositories_prod
    sys.modules["app.database.repositories"] = repositories_prod


def _load_cwc_entry() -> dict[str, Any]:
    """Read the `cwc` block from the source registry. Returns {} if PyYAML or the
    file is unavailable so the probe degrades to a no-op instead of crashing
    boot."""
    try:
        import yaml  # PyYAML is a Track B runtime dep (requirements.txt)
    except Exception:  # noqa: BLE001
        return {}
    try:
        with open(_YAML_PATH, "r", encoding="utf-8") as fh:
            reg = yaml.safe_load(fh) or {}
    except OSError:
        return {}
    return ((reg.get("sources") or {}).get("cwc") or {})


def run_boot_probe() -> dict:
    """Run the one-shot CWC probe. Returns a small summary dict for logging.
    Safe and idempotent: catalog upserts are on the (source, dataset_key,
    dataset_url) natural key, so re-booting the stack will not duplicate rows."""
    if os.environ.get("CWC_CATALOG_ON_BOOT", "1") != "1":
        print("[cwc_boot] CWC_CATALOG_ON_BOOT=0 -> skipped CWC probe")
        return {"ran": False, "reason": "disabled_by_env"}

    entry = _load_cwc_entry()
    if not entry:
        print("[cwc_boot] no cwc entry in data_sources.yml -> skipped")
        return {"ran": False, "reason": "no_config"}

    # Imported here (not at module top) so it binds to whatever DAL the caller
    # already installed under app.database.repositories (Track B: PostGIS).
    from app.collectors.cwc_collector import CwcCollector
    from app.database import repositories as repo

    verified = bool(entry.get("verified", False))

    # Cataloging needs no credentials: the verified NWDP portal is public and
    # hard-coded. verified=true alone is enough to build the catalog.
    collector = CwcCollector(verified=verified)

    try:
        res = collector.run()
    except Exception as e:  # noqa: BLE001 — verified=false path refuses to catalog
        print(f"[cwc_boot] CWC probe raised (expected if verified=false): "
              f"{type(e).__name__}: {e}")
        health = repo.get_source_health("cwc") or {}
        return {"ran": True, "status": health.get("status"), "error": str(e)}

    health = repo.get_source_health("cwc") or {}
    status = health.get("status")
    cataloged = len(repo.cwc_resources_recent(limit=100))
    print(f"[cwc_boot] CWC probe done: status={status} "
          f"verified={verified} catalog_records={cataloged} "
          f"stored_this_run={res.stored}")
    for note in getattr(collector, "_stage_notes", []):
        print(f"[cwc_boot]   stage: {note}")
    return {"ran": True, "status": status, "verified": verified,
            "catalog_records": cataloged, "stored": res.stored,
            "stage_notes": list(getattr(collector, "_stage_notes", []))}


def _main() -> None:
    """Standalone entrypoint (python -m app.services.cwc_boot)."""
    if _looks_like_postgres():
        _install_prod_repositories()
        print("[cwc_boot] DATABASE_URL is PostGIS -> installed "
              "repositories_prod swap for direct invocation")
    run_boot_probe()


if __name__ == "__main__":
    _main()
