# Verified LGD facts

The Government of India's Local Government Directory is the authoritative administrative directory used to maintain up-to-date information on local-government units.

The official LGD download portal provides directories for:
- Districts
- Sub-districts
- Villages
- PRI local bodies
- Urban local bodies
- Wards
- Development blocks

Official portal:
https://lgdirectory.gov.in/demo/downloadDirectory.do

## SIH spatial architecture

Administrative identity:
LGD code -> hierarchy -> geometry join -> risk aggregation.

The model should predict on a consistent spatial grid first where appropriate, then aggregate/intersect the risk field to village/ward polygons.

Use LGD codes as stable join keys. Names are display fields only.

## Geometry warning

Do not assume LGD directory tables are themselves polygon datasets. Boundary geometry must be sourced from an authoritative GIS boundary product and versioned separately. The two datasets should be joined using LGD codes or an explicit maintained crosswalk.

## Change management

Administrative boundaries and names can change. Store:
- source_version
- ingestion_timestamp
- effective_date when available
- LGD codes
- parent codes
- active/inactive status

This allows historical replay without silently rewriting old predictions.
