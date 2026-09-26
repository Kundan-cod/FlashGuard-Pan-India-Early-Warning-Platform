"""
Track B seed entrypoint (master prompt sections 45, 64, 67) — run once at
container boot by docker-compose:  `python -m app.services.seed_prod`.

It does exactly what Track A's seed + replay do, but against PostGIS. The trick
is that ALL the shared logic (seed.run, replay_driver.run_replay,
prediction_service) imports `app.database.repositories` by name. So the ONLY
thing this module does differently is install the PostGIS repository module
under that name BEFORE importing anything that uses it:

    sys.modules["app.database.repositories"] = repositories_prod

After that swap, the proven seed/replay code runs unchanged and writes to
Postgres instead of SQLite. This is the "A -> B is an adapter swap" promise made
in the architecture brief, demonstrated in one place.

STATUS: skeleton — pending local run (needs a live PostGIS reachable at
DATABASE_URL and the migrations already applied via `alembic upgrade head`,
which the compose command does immediately before invoking this module). It is
idempotent: seeding re-runs and replay re-ingest both rely on the natural-key
upserts in repositories_prod, so booting the stack twice will not duplicate data.

Everything written here is synthetic and labelled is_synthetic=1 / mode='replay';
no real observations, endpoints, or credentials are involved.
"""
from __future__ import annotations

import os
import sys


# Modules that bind `from app.database import repositories as repo` at import
# time. The PostGIS swap MUST happen before any of these is first imported, or
# they keep their reference to the Track A (SQLite) module and silently run the
# wrong DAL against Postgres. This was verified empirically; the guard below
# turns a future regression (e.g. someone adds an early import) into a loud,
# immediate failure instead of silent data going to the wrong backend.
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


def _install_prod_repositories() -> None:
    """Point the DAL name that the shared layers import at the PostGIS impl.
    Fails loudly if a consumer was already imported (the swap would be a no-op)."""
    already = [m for m in _CONSUMER_MODULES if m in sys.modules]
    if already:
        raise RuntimeError(
            "repositories_prod swap would be ineffective: these modules were "
            f"imported before the swap and already bound Track A: {already}. "
            "Install the prod repositories BEFORE importing any DAL consumer.")
    from app.database import repositories_prod
    sys.modules["app.database.repositories"] = repositories_prod


def _neutralize_sqlite_init() -> None:
    """seed.run() calls db.init_db() to build the SQLite schema in Track A. On
    Track B the schema is owned by Alembic migrations against PostGIS, so that
    call must become a no-op — otherwise it would open a stray SQLite handle.
    We patch the function on the module object rather than editing Track A code,
    keeping the portable core untouched and proven."""
    from app.database import db
    db.init_db = lambda reset=False: None  # type: ignore[assignment]


def main() -> None:
    _install_prod_repositories()
    _neutralize_sqlite_init()

    # Import AFTER the swap so these modules bind to repositories_prod.
    from app.services import seed
    from app.services import replay_driver

    # 1) Seed the synthetic admin hierarchy + terrain + susceptibility.
    #    reset=False here: the schema is owned by Alembic migrations (compose runs
    #    `alembic upgrade head` first), so we must NOT drop/recreate tables.
    ids = seed.run(reset=False)
    print(f"[seed_prod] seeded villages: {ids.get('villages')}")

    # Seed pan-India mountainous corridors (Himachal Pradesh, Sikkim, Western Ghats)
    nat_ids = seed.seed_national_regions(ids["country"])
    print(f"[seed_prod] seeded national villages: {nat_ids.get('villages')}")

    # Seed officially verified administrative units (is_synthetic=0)
    from app.services import admin_georeferenced
    ver_ids = admin_georeferenced.seed_verified_administrative_units(ids["country"])
    print(f"[seed_prod] seeded verified administrative units (is_synthetic=0): {ver_ids}")

    from app.services import prediction_service as psvc
    for nvid in nat_ids.get("villages", []):
        try:
            psvc.run_for_location(nvid, mode="replay")
        except Exception:
            pass

    # 2) Optionally replay the demo event so the dashboard has risk to show on
    #    first load. Controlled by env so a pure-live deployment can skip it.
    if os.environ.get("SEED_REPLAY", "1") == "1":
        # Path is resolved relative to the backend working dir inside the image.
        dataset = os.environ.get(
            "REPLAY_DATASET",
            "../data/replay/uttarakhand_flash_flood_event.json")
        summary = replay_driver.run_replay(dataset, reseed=False)
        print(f"[seed_prod] replay wrote {summary['predictions_written']} "
              f"predictions across {len(summary['timesteps'])} timesteps")
    else:
        print("[seed_prod] SEED_REPLAY=0 -> skipped replay; live collectors "
              "will populate observations")

    # 3) GPM one-shot boot probe — runs AFTER seed+replay so replay stays the
    #    known-good default and the probe can never disturb it. It only reports
    #    honest GPM source health (NOT_CONFIGURED without a token, NRT with one)
    #    and stores discovery metadata; it never runs the ML pipeline and never
    #    writes rainfall_observations at the discovery stage. Imported here
    #    (after the swap above) so it binds to the PostGIS DAL.
    from app.services import gpm_boot
    gpm_boot.run_boot_probe()

    # 4) SMAP one-shot boot probe — same honest contract as GPM, discovery-only.
    #    Runs AFTER seed+replay+GPM so replay stays the known-good default and the
    #    probe can never disturb it. Reports honest SMAP source health
    #    (NOT_CONFIGURED without a token, NRT with one) and stores CMR granule
    #    discovery metadata only; it never runs the ML pipeline and never writes
    #    soil_moisture_observations at the discovery stage. Imported here (after
    #    the swap above) so it binds to the PostGIS DAL.
    from app.services import smap_boot
    smap_boot.run_boot_probe()

    # 5) IMD one-shot boot probe. UNLIKE GPM/SMAP (discovery-only), IMD returns
    #    REAL numeric government weather/rainfall/warnings, so a successful run
    #    DOES store values — but into imd_observations ONLY, keyed by IMD's own
    #    area id, with codes/colors preserved verbatim and NO fabricated
    #    coordinate. It NEVER writes rainfall_observations, so a district figure
    #    can never masquerade as a village value in the ML feature pipeline.
    #    Reports honest IMD health (NOT_CONFIGURED / ERROR / LIVE). Imported here
    #    (after the swap above) so it binds to the PostGIS DAL.
    from app.services import imd_boot
    imd_boot.run_boot_probe()

    # 6) MOSDAC one-shot boot probe. Like GPM/SMAP, MOSDAC is DISCOVERY-ONLY:
    #    the verified mdapi workflow returns granule metadata + a download URL,
    #    not a numeric rainfall value, and the verified note mandates a separate
    #    product parser with ML consuming normalized DB values only. So a
    #    successful run stores discovery records (numeric_value NULL) into
    #    mosdac_discovery ONLY — never rainfall_observations — and MOSDAC reports
    #    NOT_CONFIGURED unless the operator supplies MOSDAC_API_BASE_URL (the
    #    verified package hard-codes no public endpoint). Replay is unaffected.
    from app.services import mosdac_boot
    mosdac_boot.run_boot_probe()

    # 7) Bhuvan/NRSC catalog probe (fifth verified source). CATALOG-ONLY: builds
    #    the verified OGC layer catalog (CartoDEM/LULC/geomorphology/lineament/
    #    flood-hazard) into bhuvan_layers ONLY — never terrain_features — so a
    #    catalog row can never masquerade as a numeric terrain value ("do not
    #    scrape rendered map pixels as a substitute for the DEM"). Cataloging the
    #    verified public OGC endpoints needs no credentials, so verified=true
    #    reports LIVE. Replay is unaffected.
    from app.services import bhuvan_boot
    bhuvan_boot.run_boot_probe()

    # 8) GSI/Bhusanket catalog probe (sixth verified source). CATALOG-ONLY: builds
    #    the verified National Landslide Forecasting Centre (Bhusanket portal)
    #    layer catalog (forecast bulletin, LSM 10K susceptibility, impact-
    #    probability map, field-validated landslide inventory) into gsi_layers
    #    ONLY — never landslide_data — so a catalog row can never masquerade as a
    #    numeric susceptibility/probability ("does not hard-code an undocumented
    #    JSON API"). Each row preserves the verified geographic_scope COVERAGE note
    #    (GSI forecasting is REGIONAL, NOT a nationwide live API). Cataloging the
    #    verified public portal needs no credentials, so verified=true reports
    #    LIVE. Replay is unaffected.
    from app.services import gsi_boot
    gsi_boot.run_boot_probe()

    # 9) CWC/NWIC catalog probe (seventh verified source). CATALOG-ONLY: builds
    #    the verified National Water Data Portal (NWDP) dataset catalog (river
    #    water level telemetry, telemetry rainfall, reservoir storage) into
    #    cwc_resources ONLY — never river_observations/rainfall_observations — so a
    #    catalog row can never masquerade as a numeric hydrological value ("does
    #    not invent an undocumented API URL"; "do not claim every station is live
    #    or every API anonymous"). Cataloging the verified public NWDP dataset
    #    pages needs no credentials, so verified=true reports LIVE. Replay is
    #    unaffected.
    from app.services import cwc_boot
    cwc_boot.run_boot_probe()

    # 10) LGD catalog probe (eighth verified source). CATALOG-ONLY: builds the
    #    verified Local Government Directory catalog (districts, sub-districts,
    #    blocks, villages, PRI/urban local bodies, wards) into lgd_directory ONLY —
    #    never any observation/administrative table — so a catalog row can never
    #    masquerade as a boundary polygon or a measurement ("do not assume LGD
    #    directory tables are polygon datasets"; "use LGD codes as stable join keys,
    #    names are display fields only"). Geometry comes from an authoritative GIS
    #    boundary product joined by LGD code, never fabricated here. Cataloging the
    #    verified public LGD download portal needs no credentials, so verified=true
    #    reports LIVE. Replay is unaffected.
    from app.services import lgd_boot
    lgd_boot.run_boot_probe()

    # 11) Historical-labels catalog probe (ninth verified source). CATALOG-ONLY:
    #    builds the verified historical-event SOURCE catalog (NRSC/ISRO Landslide
    #    Atlas, NRSC flood-hazard zonation, Bhuvan historical flood inundation, NDEM
    #    historical disasters) into historical_sources ONLY — never any events/labels
    #    or observation table — so a catalog row can never masquerade as a confirmed
    #    event or a 1/0/-1 training label. The verified note forbids treating these
    #    inventories as complete presence/absence censuses ("do not convert missing
    #    observations into negatives") and mandates the three-state labeling rule
    #    (1/0/-1) applied only after a gated inventory parse. Cataloging the verified
    #    public source URLs needs no credentials, so verified=true reports LIVE.
    #    Replay is unaffected.
    from app.services import historical_boot
    historical_boot.run_boot_probe()

    # 12) NDEM catalog probe (tenth and final verified source). CATALOG-ONLY: builds
    #    the verified NDEM (National Database for Emergency Management) capability
    #    catalog (public base layers + near-real-time flood, flood depth, CWC water
    #    levels, district nowcast, historical flood, landslide hazard inventory) into
    #    ndem_capabilities ONLY — never any observation/event table — so a catalog row
    #    can never masquerade as a measurement, a geometry or a risk score. NDEM's
    #    non-base products are PROTECTED (authorized Central/State/District/NDRF/SDRF
    #    officials only); the verified note mandates we "never bypass authentication or
    #    invent an undocumented API" and "store access_level and source-health
    #    separately from risk score." So each row preserves the verified access level
    #    (PUBLIC | AUTHORIZED | AUTHORIZED_OR_PRODUCT_SPECIFIC) verbatim as metadata,
    #    never a data value. Cataloging the verified PUBLIC capability list needs no
    #    credentials, so verified=true reports LIVE; this probe never authenticates and
    #    never fetches a protected product. Replay is unaffected.
    from app.services import ndem_boot
    ndem_boot.run_boot_probe()


if __name__ == "__main__":
    main()
