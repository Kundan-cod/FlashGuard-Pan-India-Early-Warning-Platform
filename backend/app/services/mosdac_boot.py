"""
MOSDAC boot probe (Track B) — makes MOSDAC's runtime status HONEST and verifiable.

Mirrors gpm_boot / smap_boot. Phase 1 (replay) never touches MOSDAC, so without
this probe the `mosdac` source would be absent from source_health and nothing
would ever issue a discovery request. That would make it impossible to
runtime-verify:
  * MOSDAC reported as NOT_CONFIGURED when no endpoint (MOSDAC_API_BASE_URL) is
    configured — the verified package hard-codes no public URL by design,
  * a discovery-only run inserts nothing into rainfall_observations,
  * a real mdapi granule discovery request when an endpoint IS configured.

On boot we construct the MosdacCollector straight from config/data_sources.yml
and run it exactly once. The collector itself decides the honest outcome:

  verified=false in yaml           -> refuses to fetch          -> ERROR
  verified=true, NO api_base_url   -> no fetch, no rows written -> NOT_CONFIGURED
  verified=true, api_base_url set  -> real mdapi granule search -> NRT (discovery-
                                     only; numeric_value stays NULL — there is no
                                     verified raster/HDF parse stage, so no
                                     rainfall value is ever fabricated).

This NEVER runs the ML pipeline and NEVER writes rainfall_observations at the
discovery stage — discovery records go only to mosdac_discovery. Replay stays the
known-good default and is completely unaffected: this probe runs after seed +
replay and only reports health / stores discovery metadata.

Toggle with MOSDAC_DISCOVERY_ON_BOOT (default "1"). Set "0" to skip the probe
entirely (e.g. a pure-replay demo with no outbound network at all).

IMPORTANT (import ordering): this module imports the MOSDAC collector, which
binds `from app.database import repositories as repo`. It must be imported AFTER
the repositories_prod swap (seed_prod installs the swap first), or the probe
would write to the wrong DAL. seed_prod imports it lazily for that reason.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "data_sources.yml"


# Kept in lockstep with the identical lists in seed_prod.py, main.py, gpm_boot.py,
# smap_boot.py and imd_boot.py. If mosdac_boot is invoked DIRECTLY in a Track B
# environment, the PostGIS swap normally performed by seed_prod has NOT happened;
# the standalone entrypoint installs the swap itself, and this list lets it fail
# loudly if a consumer was imported too early (silent no-op swap).
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
            "mosdac_boot: repositories_prod swap would be ineffective; these DAL "
            f"consumers were imported before the swap: {already}. Do not import "
            "collectors/services before calling _install_prod_repositories().")
    from app.database import repositories_prod
    sys.modules["app.database.repositories"] = repositories_prod


def _load_mosdac_entry() -> dict[str, Any]:
    """Read the `mosdac` block from the source registry. Returns {} if PyYAML or
    the file is unavailable so the probe degrades to a no-op instead of crashing
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
    return ((reg.get("sources") or {}).get("mosdac") or {})


def run_boot_probe() -> dict:
    """Run the one-shot MOSDAC probe. Returns a small summary dict for logging.
    Safe and idempotent: discovery upserts are on the (dataset_id, granule_id,
    download_url) natural key, so re-booting the stack will not duplicate rows."""
    if os.environ.get("MOSDAC_DISCOVERY_ON_BOOT", "1") != "1":
        print("[mosdac_boot] MOSDAC_DISCOVERY_ON_BOOT=0 -> skipped MOSDAC probe")
        return {"ran": False, "reason": "disabled_by_env"}

    entry = _load_mosdac_entry()
    if not entry:
        print("[mosdac_boot] no mosdac entry in data_sources.yml -> skipped")
        return {"ran": False, "reason": "no_config"}

    # Imported here (not at module top) so it binds to whatever DAL the caller
    # already installed under app.database.repositories (Track B: PostGIS).
    from app.collectors.mosdac_collector import MosdacCollector
    from app.database import repositories as repo

    verified = bool(entry.get("verified", False))
    # MOSDAC is configured when an endpoint (MOSDAC_API_BASE_URL) is present;
    # search is anonymous so credentials are NOT part of the gate.
    base_url_env_var = entry.get("auth_env_var", "MOSDAC_API_BASE_URL")
    has_endpoint = bool(os.environ.get(base_url_env_var)) if base_url_env_var else False

    # First documented dataset from the verified registry (e.g. 3RIMG_L2B_HEM).
    dataset_id = "3RIMG_L2B_HEM"
    products = entry.get("products") or ""
    for ds in ("3RIMG_L2B_HEM", "3SIMG_L2G_IMR", "3SIMG_L2G_GPI",
               "3SIMG_L3B_HEM"):
        if ds in products:
            dataset_id = ds
            break

    collector = MosdacCollector(
        verified=verified,
        base_url_env_var=base_url_env_var,
        dataset_id=dataset_id,
        count=10,
    )

    try:
        res = collector.run()
    except Exception as e:  # noqa: BLE001 — verified=false path refuses to fetch
        print(f"[mosdac_boot] MOSDAC probe raised (expected if verified=false): "
              f"{type(e).__name__}: {e}")
        health = repo.get_source_health("mosdac") or {}
        return {"ran": True, "status": health.get("status"), "error": str(e)}

    health = repo.get_source_health("mosdac") or {}
    status = health.get("status")
    discovered = len(repo.mosdac_discovery_recent(limit=100))
    print(f"[mosdac_boot] MOSDAC probe done: status={status} "
          f"has_endpoint={has_endpoint} discovery_records={discovered} "
          f"stored_this_run={res.stored}")
    for note in getattr(collector, "_stage_notes", []):
        print(f"[mosdac_boot]   stage: {note}")
    return {"ran": True, "status": status, "has_endpoint": has_endpoint,
            "discovery_records": discovered, "stored": res.stored,
            "stage_notes": list(getattr(collector, "_stage_notes", []))}


def _main() -> None:
    """Standalone entrypoint (python -m app.services.mosdac_boot)."""
    if _looks_like_postgres():
        _install_prod_repositories()
        print("[mosdac_boot] DATABASE_URL is PostGIS -> installed "
              "repositories_prod swap for direct invocation")
    run_boot_probe()


if __name__ == "__main__":
    _main()
