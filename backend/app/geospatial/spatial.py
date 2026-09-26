"""
Pure-Python geospatial primitives for the Track A portable core.

No shapely / GEOS available in the portable environment, so we implement the
handful of operations the pipeline actually needs:
  - point-in-polygon (ray casting), incl. multipolygon + holes
  - bounding box of a GeoJSON geometry
  - centroid (representative point) of a polygon
  - haversine distance (m) for nearest-station / distance-to-river
  - point-in-polygon spatial join with bbox pre-filter

In Track B these are replaced by PostGIS ST_Contains / ST_Distance etc. The
function signatures are kept deliberately simple so callers are storage-agnostic.

Coordinates are (lon, lat) in WGS84 (GeoJSON order), degrees.
"""
from __future__ import annotations

import math
from typing import Iterable, Sequence

Coord = tuple[float, float]  # (lon, lat)


# --------------------------------------------------------------------------
# Bounding box
# --------------------------------------------------------------------------
def _iter_rings(geom: dict) -> Iterable[list]:
    t = geom.get("type")
    c = geom.get("coordinates")
    if t == "Polygon":
        for ring in c:
            yield ring
    elif t == "MultiPolygon":
        for poly in c:
            for ring in poly:
                yield ring
    else:
        raise ValueError(f"Unsupported geometry type for rings: {t}")


def bbox(geom: dict) -> tuple[float, float, float, float]:
    """Return (minx, miny, maxx, maxy) in lon/lat."""
    xs: list[float] = []
    ys: list[float] = []
    for ring in _iter_rings(geom):
        for x, y in ring:
            xs.append(x)
            ys.append(y)
    if not xs:
        raise ValueError("empty geometry")
    return min(xs), min(ys), max(xs), max(ys)


def in_bbox(lon: float, lat: float,
            minx: float, miny: float, maxx: float, maxy: float) -> bool:
    return (minx <= lon <= maxx) and (miny <= lat <= maxy)


# --------------------------------------------------------------------------
# Point in polygon (ray casting)
# --------------------------------------------------------------------------
def _point_in_ring(lon: float, lat: float, ring: Sequence[Coord]) -> bool:
    """Ray-casting test for a single ring. Ring is list of [lon,lat]."""
    inside = False
    n = len(ring)
    j = n - 1
    for i in range(n):
        xi, yi = ring[i][0], ring[i][1]
        xj, yj = ring[j][0], ring[j][1]
        # does the horizontal ray at `lat` cross edge (i,j)?
        intersect = ((yi > lat) != (yj > lat)) and \
            (lon < (xj - xi) * (lat - yi) / ((yj - yi) or 1e-15) + xi)
        if intersect:
            inside = not inside
        j = i
    return inside


def point_in_polygon(lon: float, lat: float, geom: dict) -> bool:
    """
    True if point is inside the (multi)polygon. Handles holes: a point inside
    an outer ring but inside a hole ring counts as outside.
    """
    t = geom.get("type")
    coords = geom.get("coordinates")
    polys = coords if t == "MultiPolygon" else [coords] if t == "Polygon" else None
    if polys is None:
        raise ValueError(f"Unsupported geometry type: {t}")
    for poly in polys:
        if not poly:
            continue
        outer = poly[0]
        if _point_in_ring(lon, lat, outer):
            in_hole = any(_point_in_ring(lon, lat, hole) for hole in poly[1:])
            if not in_hole:
                return True
    return False


# --------------------------------------------------------------------------
# Centroid (area-weighted for polygon outer ring; good enough as rep. point)
# --------------------------------------------------------------------------
def polygon_centroid(geom: dict) -> Coord:
    """Representative interior point. Uses outer-ring area centroid; falls back
    to vertex mean for degenerate rings."""
    if geom.get("type") == "MultiPolygon":
        # pick the largest polygon by bbox area
        best = None
        best_area = -1.0
        for poly in geom["coordinates"]:
            ring = poly[0]
            xs = [p[0] for p in ring]
            ys = [p[1] for p in ring]
            a = (max(xs) - min(xs)) * (max(ys) - min(ys))
            if a > best_area:
                best_area, best = a, ring
        ring = best
    else:
        ring = geom["coordinates"][0]

    a = 0.0
    cx = 0.0
    cy = 0.0
    n = len(ring)
    for i in range(n - 1):
        x0, y0 = ring[i]
        x1, y1 = ring[i + 1]
        cross = x0 * y1 - x1 * y0
        a += cross
        cx += (x0 + x1) * cross
        cy += (y0 + y1) * cross
    a *= 0.5
    if abs(a) < 1e-12:  # degenerate -> vertex mean
        xs = [p[0] for p in ring]
        ys = [p[1] for p in ring]
        return sum(xs) / len(xs), sum(ys) / len(ys)
    return cx / (6 * a), cy / (6 * a)


# --------------------------------------------------------------------------
# Distances
# --------------------------------------------------------------------------
_EARTH_R = 6_371_000.0  # m


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlmb / 2) ** 2
    return 2 * _EARTH_R * math.asin(math.sqrt(a))


def nearest(lon: float, lat: float,
            candidates: Sequence[tuple[float, float, object]]) -> tuple[object, float] | None:
    """candidates: (lon, lat, payload). Returns (payload, distance_m) or None."""
    best = None
    best_d = float("inf")
    for clon, clat, payload in candidates:
        d = haversine_m(lon, lat, clon, clat)
        if d < best_d:
            best_d, best = d, payload
    return (best, best_d) if best is not None else None


# --------------------------------------------------------------------------
# Spatial join: locate which location polygon contains a point
# --------------------------------------------------------------------------
def locate_point(lon: float, lat: float, locations: Sequence[dict]) -> dict | None:
    """
    locations: dicts with bbox_* and geometry_geojson (already parsed to dict
    under key 'geometry'). Bbox pre-filter then exact PIP. Returns the location
    dict or None. This is the Track A analogue of a PostGIS point-in-polygon
    spatial join.
    """
    for loc in locations:
        bx = loc.get("bbox_minx")
        if bx is not None:
            if not in_bbox(lon, lat, loc["bbox_minx"], loc["bbox_miny"],
                           loc["bbox_maxx"], loc["bbox_maxy"]):
                continue
        geom = loc.get("geometry")
        if geom and point_in_polygon(lon, lat, geom):
            return loc
    return None
