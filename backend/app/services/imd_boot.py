"""
IMD boot probe (Track B) — makes IMD's runtime status HONEST and verifiable.

Mirrors gpm_boot / smap_boot. Phase 1 (replay) never touches IMD, so without
this probe the `imd` source would be absent from source_health and nothing would
ever issue a request. That would make it impossible to runtime-verify:
  * IMD reported as NOT_CONFIGURED when a token is required but absent,
  * IMD reported as ERROR when verified=false in the registry,
  * a real IMD fetch when the source is configured — landing real numeric
    values in imd_observations ONLY (never rainfall_observations).

On boot we construct the ImdCollector straight from config/data_sources.yml and
run it exactly once. The collector itself decides the honest outcome:

  verified=false in yaml            -> refuses to fetch          -> ERROR
  verified=true, token required+missing -> no fetch, no rows     -> NOT_CONFIGURED
  verified=true, configured         -> real IMD fetch            -> LIVE

Unlike GPM/SMAP (discovery-only), IMD returns REAL numbers, so a successful run
DOES store values — but into imd_observations, keyed by IMD's own area id, with
codes/colors preserved verbatim and NO fabricated coordinate. It NEVER writes
rainfall_observations, so a district figure can never masquerade as a village
value in the ML feature pipeline. Replay stays the known-good default and is
completely unaffected.

Toggle with IMD_FETCH_ON_BOOT (default "1"). Set "0" to skip the probe entirely.

IMPORTANT (import ordering): this module imports the IMD collector, which binds
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


# Kept in lockstep with the identical lists in seed_prod.py, main.py, gpm_boot.py
# and smap_boot.py. If imd_boot is invoked DIRECTLY in a Track B environment, the
# PostGIS swap normally performed by seed_prod has NOT happened; the standalone
# entrypoint installs the swap itself, and this list lets it fail loudly if a
# consumer was imported too early (which would make the swap a silent no-op).
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
            "imd_boot: repositories_prod swap would be ineffective; these DAL "
            f"consumers were imported before the swap: {already}. Do not import "
            "collectors/services before calling _install_prod_repositories().")
    from app.database import repositories_prod
    sys.modules["app.database.repositories"] = repositories_prod


def _load_imd_entry() -> dict[str, Any]:
    """Read the `imd` block from the source registry. Returns {} if PyYAML or the
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
    return ((reg.get("sources") or {}).get("imd") or {})


def run_boot_probe() -> dict:
    """Run the one-shot IMD probe. Returns a small summary dict for logging.
    Safe and idempotent: upserts are on the (source, record_type, area_id,
    observed_at, warning_day) natural key, so re-booting will not duplicate rows."""
    if os.environ.get("IMD_FETCH_ON_BOOT", "1") != "1":
        print("[imd_boot] IMD_FETCH_ON_BOOT=0 -> skipped IMD probe")
        return {"ran": False, "reason": "disabled_by_env"}

    entry = _load_imd_entry()
    if not entry:
        print("[imd_boot] no imd entry in data_sources.yml -> skipped")
        return {"ran": False, "reason": "no_config"}

    # Imported here (not at module top) so it binds to whatever DAL the caller
    # already installed under app.database.repositories (Track B: PostGIS).
    from app.collectors.imd_collector import ImdCollector
    from app.database import repositories as repo

    verified = bool(entry.get("verified", False))
    # auth_env_var may be null in the registry (public IMD endpoints). Honour
    # that: None -> collector considers itself configured without a token.
    auth_env_var = entry.get("auth_env_var", "IMD_API_TOKEN")
    if auth_env_var in ("", "null", "none", "None"):
        auth_env_var = None
    has_token = bool(os.environ.get(auth_env_var)) if auth_env_var else False

    # Optional area lists from the registry (stations/districts to poll). Nothing
    # is invented: if absent, the collector queries the default endpoints.
    stations = entry.get("stations") or []
    districts = entry.get("districts") or []

    collector = ImdCollector(
        verified=verified,
        auth_env_var=auth_env_var,
        stations=list(stations),
        districts=list(districts),
    )

    try:
        res = collector.run()
    except Exception as e:  # noqa: BLE001 — verified=false path refuses to fetch
        print(f"[imd_boot] IMD probe raised (expected if verified=false): "
              f"{type(e).__name__}: {e}")
        health = repo.get_source_health("imd") or {}
        return {"ran": True, "status": health.get("status"), "error": str(e)}

    health = repo.get_source_health("imd") or {}
    status = health.get("status")
    stored = len(repo.imd_recent(limit=100))
    print(f"[imd_boot] IMD probe done: status={status} "
          f"has_token={has_token} imd_records={stored} "
          f"stored_this_run={res.stored}")
    for note in getattr(collector, "_stage_notes", []):
        print(f"[imd_boot]   stage: {note}")
    return {"ran": True, "status": status, "has_token": has_token,
            "imd_records": stored, "stored": res.stored,
            "stage_notes": list(getattr(collector, "_stage_notes", []))}


def _main() -> None:
    """Standalone entrypoint (python -m app.services.imd_boot)."""
    if _looks_like_postgres():
        _install_prod_repositories()
        print("[imd_boot] DATABASE_URL is PostGIS -> installed repositories_prod "
              "swap for direct invocation")
    run_boot_probe()


if __name__ == "__main__":
    _main()
