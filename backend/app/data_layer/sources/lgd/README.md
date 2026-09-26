# SIH 26192 — Local Government Directory (LGD) Administrative Layer

LGD is the Government of India's authoritative directory for local-government administrative units.

Target hierarchy for SIH:
India -> State/UT -> District -> Sub-district/Tehsil -> Development Block -> Village / Urban Local Body -> Ward

Verified official LGD download portal:
https://lgdirectory.gov.in/demo/downloadDirectory.do

The portal provides downloadable directories for districts, sub-districts, villages, PRI local bodies, urban local bodies, wards and development blocks.

Important engineering distinction:
The LGD directory is authoritative for administrative identity/codes and hierarchy. Do not assume the directory download itself is a complete polygon-geometry source. Geometry should come from an authoritative GIS boundary product where available, then be linked to LGD codes.

Recommended internal keys:
- lgd_state_code
- lgd_district_code
- lgd_subdistrict_code
- lgd_block_code
- lgd_village_code
- lgd_urban_local_body_code
- lgd_ward_code

Never use village/ward names as primary keys because names can repeat or change.
