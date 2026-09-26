# Replay / demo data — **SYNTHETIC, clearly labelled**

Everything in this folder is **synthetic data generated for demonstration**
(master prompt sections 45, 64, 67). It is **not** real observation data from
NASA, IMD, ISRO, CWC, GSI, or any government source. It exists so the full
pipeline (collector → validation → normalization → PostGIS/SQLite → features →
model → risk → API → dashboard) can be demonstrated without depending on live
external APIs at judging time.

- `uttarakhand_flash_flood_event.json` — a synthetic rising-rainfall flash-flood
  scenario over a small hilly area, used for stepped historical replay. Records
  carry `"synthetic": true` and are stored with `realtime_class = "replay"`.

When real verified sources are connected, the identical pipeline ingests real
data; only the collector's `fetch()` changes.
