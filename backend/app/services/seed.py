"""
Seed synthetic administrative locations + terrain + susceptibility for the demo
(master prompt sections 3, 45, 67). ALL synthetic and labelled is_synthetic=1.

This stands in for the verified admin-boundary + DEM + GSI layers until those
sources are supplied. It builds a small India->state->district->block->village
hierarchy over a hilly cluster so drill-down and spatial joins are demonstrable.
"""
from __future__ import annotations

from app.database import repositories as repo


def _square(lon, lat, d=0.05):
    return {"type": "Polygon", "coordinates": [[
        [lon - d, lat - d], [lon + d, lat - d], [lon + d, lat + d],
        [lon - d, lat + d], [lon - d, lat - d]]]}


# synthetic villages (name, lat, lon, elevation, slope, susceptibility)
VILLAGES = [
    ("Devgaon",        30.05, 78.05, 1450, 34, 0.72),
    ("Ranikhet-South", 30.07, 78.08, 1600, 41, 0.81),
    ("Talli",          30.03, 78.02, 1250, 22, 0.55),
    ("Bhoomiadhar",    30.09, 78.11, 1720, 47, 0.88),
]


def run(reset: bool = True) -> dict:
    from app.database import db
    if reset:
        db.init_db(reset=True)
    else:
        db.init_db(reset=False)

    country = repo.upsert_location({"ext_code": "IN", "name": "India",
                                    "level": "country", "is_synthetic": 1,
                                    "geometry": _square(80, 24, 12)})
    state = repo.upsert_location({"ext_code": "IN-UK", "name": "Uttarakhand",
                                  "level": "state", "parent_id": country,
                                  "state": "Uttarakhand", "is_synthetic": 1,
                                  "geometry": _square(78.1, 30.1, 0.6)})
    district = repo.upsert_location({"ext_code": "IN-UK-DD", "name": "Demo District",
                                     "level": "district", "parent_id": state,
                                     "state": "Uttarakhand", "district": "Demo District",
                                     "is_synthetic": 1, "geometry": _square(78.06, 30.06, 0.2)})
    block = repo.upsert_location({"ext_code": "IN-UK-DD-B1", "name": "Demo Block",
                                  "level": "block", "parent_id": district,
                                  "state": "Uttarakhand", "district": "Demo District",
                                  "block": "Demo Block", "is_synthetic": 1,
                                  "geometry": _square(78.06, 30.06, 0.12)})

    village_ids = []
    for idx, (name, lat, lon, elev, slope, susc) in enumerate(VILLAGES, start=1):
        vid = repo.upsert_location({
            "ext_code": f"IN-UK-DD-B1-{name}", "name": name, "level": "village",
            "parent_id": block, "state": "Uttarakhand", "district": "Demo District",
            "block": "Demo Block", "village": name, "is_synthetic": 1,
            "latitude": lat, "longitude": lon, "geometry": _square(lon, lat, 0.02),
        })
        repo.upsert_terrain(vid, {
            "elevation": elev, "slope": slope, "aspect": 180, "curvature": 0.15,
            "flow_accumulation": 800 + slope * 40, "drainage_density": 2.0,
            "distance_to_drainage": 120, "relative_relief": elev * 0.5,
            "is_synthetic": 1, "source": "synthetic_dem",
        })
        repo.upsert_susceptibility(vid, "synthetic_gsi", susc, is_synthetic=True)
        _seed_shelter_and_recipients(name, lat, lon, "Demo District", idx)
        village_ids.append(vid)

    return {"country": country, "state": state, "district": district,
            "block": block, "villages": village_ids}


def _seed_shelter_and_recipients(name: str, lat: float, lon: float, district_name: str, idx: int) -> None:
    # 1. Verified demo evacuation centre
    repo.upsert_evacuation_centre({
        "name": f"{name} Community Relief Shelter [DEMO SHELTER]",
        "address": f"Higher Ridge Rd, Ward 2, {name}",
        "village": name,
        "ward": "Ward-02 (High Ground)",
        "district": district_name,
        "latitude": round(lat + 0.005, 4),
        "longitude": round(lon + 0.004, 4),
        "capacity": 350 + (idx % 5) * 100,
        "contact_number": f"+91 11-23438{idx:03d}",
        "accessibility": "Paved access, emergency power generator, clean water cistern",
        "verified": 1,
        "active": 1,
        "is_demo": 1,
    })

    # 2. Demo alert recipients (multi-language distribution)
    repo.upsert_alert_recipient({
        "name": f"Panchayat Secretary ({name})",
        "phone_number": f"+9198765{idx:02d}001",
        "village": name,
        "ward": "Ward-02",
        "district": district_name,
        "preferred_language": "en",
        "active": 1,
        "emergency_notification_enabled": 1,
        "is_demo": 1,
    })
    repo.upsert_alert_recipient({
        "name": f"ग्राम प्रधान ({name})",
        "phone_number": f"+9198765{idx:02d}002",
        "village": name,
        "ward": "Ward-01",
        "district": district_name,
        "preferred_language": "hi",
        "active": 1,
        "emergency_notification_enabled": 1,
        "is_demo": 1,
    })
    repo.upsert_alert_recipient({
        "name": f"Community Warden ({name})",
        "phone_number": f"+9198765{idx:02d}003",
        "village": name,
        "ward": "Ward-03",
        "district": district_name,
        "preferred_language": "ta",
        "active": 1,
        "emergency_notification_enabled": 1,
        "is_demo": 1,
    })


# Pan-India high-risk mountainous regions (Himachal, Sikkim, Western Ghats)
NATIONAL_REGIONS = [
    {
        "state_code": "IN-HP",
        "state_name": "Himachal Pradesh",
        "center": (77.10, 31.80),
        "district_code": "IN-HP-MD",
        "district_name": "Mandi & Kullu Basins",
        "block_code": "IN-HP-MD-B1",
        "block_name": "Beas Gorge Valley",
        "villages": [
            ("Pandoh", 31.67, 77.01, 1380, 32, 0.76),
            ("Aut-Larji", 31.75, 77.20, 1420, 39, 0.84),
            ("Manali-Vashisht", 32.24, 77.19, 2050, 44, 0.89),
            ("Dharamshala-Bhagsunag", 32.25, 76.35, 1750, 36, 0.78),
        ]
    },
    {
        "state_code": "IN-SK",
        "state_name": "Sikkim",
        "center": (88.55, 27.45),
        "district_code": "IN-SK-MG",
        "district_name": "Mangan & Gangtok Basins",
        "block_code": "IN-SK-MG-B1",
        "block_name": "Teesta River Corridor",
        "villages": [
            ("Chungthang", 27.60, 88.65, 1790, 42, 0.91),
            ("Mangan-Singhik", 27.50, 88.53, 1450, 38, 0.85),
            ("Dikchu", 27.39, 88.52, 920, 31, 0.73),
            ("Rangpo", 27.18, 88.53, 450, 24, 0.58),
        ]
    },
    {
        "state_code": "IN-KL",
        "state_name": "Western Ghats / Kerala",
        "center": (76.50, 10.50),
        "district_code": "IN-KL-WY",
        "district_name": "Wayanad & Idukki Hill Tracts",
        "block_code": "IN-KL-WY-B1",
        "block_name": "Debris Flow Corridors",
        "villages": [
            ("Meppadi-Chooralmala", 11.55, 76.13, 980, 38, 0.92),
            ("Mundakkai", 11.53, 76.15, 1050, 41, 0.94),
            ("Munnar-Pettimudi", 10.15, 77.02, 1620, 45, 0.90),
            ("Cheruthoni", 9.85, 76.97, 720, 28, 0.65),
        ]
    }
]


def seed_national_regions(country_id: int) -> dict:
    """Seed additional high-risk mountain corridors across India (Himachal Pradesh,
    Sikkim, Western Ghats/Kerala) for pan-India scale demonstrations.
    All labelled is_synthetic=1."""
    national_village_ids = []
    for reg in NATIONAL_REGIONS:
        sc = reg["center"]
        st_id = repo.upsert_location({
            "ext_code": reg["state_code"], "name": reg["state_name"],
            "level": "state", "parent_id": country_id,
            "state": reg["state_name"], "is_synthetic": 1,
            "geometry": _square(sc[0], sc[1], 0.8),
        })
        dist_id = repo.upsert_location({
            "ext_code": reg["district_code"], "name": reg["district_name"],
            "level": "district", "parent_id": st_id,
            "state": reg["state_name"], "district": reg["district_name"],
            "is_synthetic": 1, "geometry": _square(sc[0], sc[1], 0.35),
        })
        blk_id = repo.upsert_location({
            "ext_code": reg["block_code"], "name": reg["block_name"],
            "level": "block", "parent_id": dist_id,
            "state": reg["state_name"], "district": reg["district_name"],
            "block": reg["block_name"], "is_synthetic": 1,
            "geometry": _square(sc[0], sc[1], 0.18),
        })
        for v_idx, (name, lat, lon, elev, slope, susc) in enumerate(reg["villages"], start=1):
            vid = repo.upsert_location({
                "ext_code": f"{reg['block_code']}-{name}", "name": name, "level": "village",
                "parent_id": blk_id, "state": reg["state_name"], "district": reg["district_name"],
                "block": reg["block_name"], "village": name, "is_synthetic": 1,
                "latitude": lat, "longitude": lon, "geometry": _square(lon, lat, 0.02),
            })
            repo.upsert_terrain(vid, {
                "elevation": elev, "slope": slope, "aspect": 180, "curvature": 0.15,
                "flow_accumulation": 900 + slope * 45, "drainage_density": 2.2,
                "distance_to_drainage": 100, "relative_relief": elev * 0.45,
                "is_synthetic": 1, "source": "synthetic_dem",
            })
            repo.upsert_susceptibility(vid, "synthetic_gsi", susc, is_synthetic=True)
            _seed_shelter_and_recipients(name, lat, lon, reg["district_name"], v_idx + 10)
            national_village_ids.append(vid)

    for idx, (name, lat, lon, dist) in enumerate(NATIONAL_CORRIDOR_VILLAGES, start=50):
        _seed_shelter_and_recipients(name, lat, lon, dist, idx)

    return {"villages": national_village_ids}


NATIONAL_CORRIDOR_VILLAGES = [
    ("Joshimath", 30.5564, 79.5658, "Chamoli"),
    ("Dharali", 31.0345, 78.7612, "Uttarkashi"),
    ("Govindghat", 30.625, 79.593, "Chamoli"),
    ("Kedarnath", 30.735, 79.066, "Rudraprayag"),
    ("Malana", 32.057, 77.265, "Kullu"),
    ("Kasol", 32.01, 77.315, "Kullu"),
    ("Sangla", 31.425, 78.265, "Kinnaur"),
    ("Manikaran", 32.027, 77.348, "Kullu"),
    ("Chungthang", 27.604, 88.647, "Mangan"),
    ("Lachen", 27.717, 88.558, "Mangan"),
    ("Lachung", 27.689, 88.743, "Mangan"),
    ("Mangan", 27.508, 88.533, "Mangan"),
    ("Munnar", 10.0889, 77.0595, "Idukki"),
    ("Cheruthoni", 9.8514, 76.9744, "Idukki"),
    ("Meppadi", 11.5512, 76.1265, "Wayanad"),
    ("Nilambur", 11.2764, 76.2268, "Malappuram"),
]


if __name__ == "__main__":
    ids = run(reset=True)
    nat = seed_national_regions(ids["country"])
    print("seeded core:", ids)
    print("seeded national:", nat)
