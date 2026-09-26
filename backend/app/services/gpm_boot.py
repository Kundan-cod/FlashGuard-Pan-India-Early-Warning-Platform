"""
GPM boot probe (Track B) — makes GPM's runtime status HONEST and verifiable.

Phase 1 (replay) never touches GPM, so without this probe the `gpm` source would
simply be absent from source_health and nothing would ever issue a discovery
request. That would make it impossible to runtime-verify:
  * point 4 — GPM reported as NOT_CONFIGURED when no Earthdata token exists,
  * point 5 — a discovery-only run inserts nothing into rainfall_observations,
  * point 13 — a real discovery request when a token IS present.

So on boot we construct the GpmCollector straight from config/data_sources.yml
and run it exactly once. The collector itself decides the honest outcome:

  verified=false in yaml  -> refuses to fetch            -> ERROR
  verified=true, NO token -> no fetch, no rows written   -> NOT_CONFIGURED
  verified=true, token    -> real PMM discovery request  -> NRT (discovery-only;
                             numeric_value stays NULL unless the gated raster
                             stage downloads+parses+samples a real product)

This NEVER runs the ML pipeline and NEVER writes rainfall_observations at the
discovery stage — discovery records go only to gpm_discovery. Replay stays the
known-good default and is completely unaffected: this probe runs after seed +
replay and only reports health / stores discovery metadata.

Toggle with GPM_DISCOVERY_ON_BOOT (default "1"). Set "0" to skip the probe
entirely (e.g. a pure-replay demo with no outbound network at all).

IMPORTANT (import ordering): this module imports the GPM collector, which binds
`from app.database import repositories as repo`. It must therefore be imported
AFTER the repositories_prod swap (seed_prod installs the swap first), or the
probe would write to the wrong DAL. seed_prod imports it lazily for that reason.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any


_YAML_PATH = Path(__file__).resolve().parents[1] / "config" / "data_sources.yml"


# Modules that bind `from app.database import repositories as repo` at import
# time. If gpm_boot is invoked DIRECTLY (python -m app.services.gpm_boot) in a
# Track B environment, the PostGIS swap normally performed by seed_prod has NOT
# happened, so repo would be the Track A SQLite module and the probe would crash
# with "no such table: source_health". The standalone entrypoint below installs
# the swap itself; this list lets it fail loudly if a consumer was imported too
# early (which would make the swap a silent no-op). Kept in lockstep with the
# identical lists in seed_prod.py and main.py.
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
    """True when the runtime is configured for the Track B PostGIS backend.
    Detected from DATABASE_URL so a pure Track A / SQLite run (no DATABASE_URL,
    or a sqlite:// URL) never triggers the swap and keeps its own DAL."""
    url = (os.environ.get("DATABASE_URL") or "").lower()
    return url.startswith("postgres") or "postgresql" in url


def _install_prod_repositories() -> None:
    """Bind the DAL name the shared layers import to the PostGIS implementation,
    exactly as seed_prod does. Fails loudly if a consumer was already imported
    (the swap would otherwise be an ineffective no-op). Only called from the
    standalone __main__ path in a Postgres environment — the normal boot goes
    through seed_prod, which has already installed this swap, so run_boot_probe()
    itself never touches sys.modules."""
    already = [m for m in _CONSUMER_MODULES if m in sys.modules]
    if already:
        raise RuntimeError(
            "gpm_boot: repositories_prod swap would be ineffective; these DAL "
            f"consumers were imported before the swap: {already}. Do not import "
            "collectors/services before calling _install_prod_repositories().")
    from app.database import repositories_prod
    sys.modules["app.database.repositories"] = repositories_prod


def _load_gpm_entry() -> dict[str, Any]:
    """Read the `gpm` block from the source registry. Returns {} if PyYAML or the
    file is unavailable so the probe degrades to a no-op instead of crashing boot."""
    try:
        import yaml  # PyYAML is a Track B runtime dep (requirements.txt)
    except Exception:  # noqa: BLE001
        return {}
    try:
        with open(_YAML_PATH, "r", encoding="utf-8") as fh:
            reg = yaml.safe_load(fh) or {}
    except OSError:
        return {}
    return ((reg.get("sources") or {}).get("gpm") or {})


def run_boot_probe() -> dict:
    """Run the one-shot GPM probe. Returns a small summary dict for logging.
    Safe and idempotent: discovery upserts are on the (item_id, download_url)
    natural key, so re-booting the stack will not duplicate rows."""
    if os.environ.get("GPM_DISCOVERY_ON_BOOT", "1") != "1":
        print("[gpm_boot] GPM_DISCOVERY_ON_BOOT=0 -> skipped GPM probe")
        return {"ran": False, "reason": "disabled_by_env"}

    entry = _load_gpm_entry()
    if not entry:
        print("[gpm_boot] no gpm entry in data_sources.yml -> skipped")
        return {"ran": False, "reason": "no_config"}

    # Imported here (not at module top) so it binds to whatever DAL the caller
    # already installed under app.database.repositories (Track B: PostGIS).
    from app.collectors.gpm_collector import GpmCollector
    from app.database import repositories as repo

    verified = bool(entry.get("verified", False))
    auth_env_var = entry.get("auth_env_var", "NASA_EARTHDATA_TOKEN")
    has_token = bool(os.environ.get(auth_env_var))

    # GPM_ENABLE_RASTER (default "1") only PERMITS the gated raster stage; the
    # stage still runs solely if rasterio is importable AND the discovered
    # payload is a scientific raster. Set "0" to force discovery-only even on the
    # ML image. In the default minimal image rasterio is absent, so this is a
    # no-op there regardless — the honest default we verify.
    enable_raster = os.environ.get("GPM_ENABLE_RASTER", "1") == "1"
    collector = GpmCollector(
        verified=verified,
        auth_env_var=auth_env_var,
        enable_raster=enable_raster,
        product=str((entry.get("products") or "precip_1d")).split(",")[0].strip()
                if entry.get("products") else "precip_1d",
        limit=10,
    )

    try:
        res = collector.run()
    except Exception as e:  # noqa: BLE001 — verified=false path refuses to fetch
        # The collector already recorded an ERROR health row; surface it in logs
        # but never crash the boot — replay must stay up regardless.
        print(f"[gpm_boot] GPM probe raised (expected if verified=false): "
              f"{type(e).__name__}: {e}")
        health = repo.get_source_health("gpm") or {}
        return {"ran": True, "status": health.get("status"), "error": str(e)}

    health = repo.get_source_health("gpm") or {}
    status = health.get("status")
    discovered = len(repo.gpm_discovery_recent(limit=100))
    print(f"[gpm_boot] GPM probe done: status={status} "
          f"has_token={has_token} discovery_records={discovered} "
          f"stored_this_run={res.stored}")
    for note in getattr(collector, "_stage_notes", []):
        print(f"[gpm_boot]   stage: {note}")
    return {"ran": True, "status": status, "has_token": has_token,
            "discovery_records": discovered, "stored": res.stored,
            "stage_notes": list(getattr(collector, "_stage_notes", []))}


def _main() -> None:
    """Standalone entrypoint (python -m app.services.gpm_boot).

    Normal boot never comes through here — seed_prod imports run_boot_probe()
    lazily AFTER it has installed the PostGIS swap. This path exists so the probe
    can be invoked directly (e.g. by the runtime-verification script) and still
    talk to the correct backend. In a Track B/PostGIS environment we install the
    same repositories_prod swap seed_prod uses, BEFORE importing anything that
    binds the DAL, so the probe hits PostGIS instead of an empty SQLite file.
    In a Track A/SQLite environment we do nothing and the default DAL is used."""
    if _looks_like_postgres():
        _install_prod_repositories()
        print("[gpm_boot] DATABASE_URL is PostGIS -> installed repositories_prod "
              "swap for direct invocation")
    run_boot_probe()


if __name__ == "__main__":
    _main()
