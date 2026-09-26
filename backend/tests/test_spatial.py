"""Pure-Python geospatial primitives (master prompt section 13)."""
import unittest
from _util import bootstrap
bootstrap()

from app.geospatial import spatial


def _square(cx, cy, d):
    return {"type": "Polygon", "coordinates": [[
        [cx - d, cy - d], [cx + d, cy - d], [cx + d, cy + d],
        [cx - d, cy + d], [cx - d, cy - d]]]}


class TestSpatial(unittest.TestCase):
    def test_bbox(self):
        b = spatial.bbox(_square(78, 30, 0.1))
        self.assertEqual(b, (77.9, 29.9, 78.1, 30.1))

    def test_point_in_polygon_inside(self):
        self.assertTrue(spatial.point_in_polygon(78.0, 30.0, _square(78, 30, 0.1)))

    def test_point_in_polygon_outside(self):
        self.assertFalse(spatial.point_in_polygon(79.0, 30.0, _square(78, 30, 0.1)))

    def test_point_in_polygon_hole(self):
        # outer square with a hole in the middle; point in hole => outside
        geom = {"type": "Polygon", "coordinates": [
            [[0, 0], [4, 0], [4, 4], [0, 4], [0, 0]],           # outer
            [[1, 1], [3, 1], [3, 3], [1, 3], [1, 1]],           # hole
        ]}
        self.assertTrue(spatial.point_in_polygon(0.5, 0.5, geom))   # in ring, not hole
        self.assertFalse(spatial.point_in_polygon(2.0, 2.0, geom))  # inside hole

    def test_multipolygon(self):
        geom = {"type": "MultiPolygon", "coordinates": [
            [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            [[[5, 5], [6, 5], [6, 6], [5, 6], [5, 5]]],
        ]}
        self.assertTrue(spatial.point_in_polygon(0.5, 0.5, geom))
        self.assertTrue(spatial.point_in_polygon(5.5, 5.5, geom))
        self.assertFalse(spatial.point_in_polygon(3.0, 3.0, geom))

    def test_centroid(self):
        cx, cy = spatial.polygon_centroid(_square(78, 30, 0.1))
        self.assertAlmostEqual(cx, 78.0, places=6)
        self.assertAlmostEqual(cy, 30.0, places=6)

    def test_haversine_one_degree_lat(self):
        # ~111 km per degree of latitude
        d = spatial.haversine_m(78.0, 30.0, 78.0, 31.0)
        self.assertTrue(110_000 < d < 112_000, d)

    def test_nearest(self):
        cands = [(78.0, 30.0, "A"), (78.5, 30.5, "B"), (79.0, 31.0, "C")]
        payload, dist = spatial.nearest(78.02, 30.01, cands)
        self.assertEqual(payload, "A")
        self.assertGreater(dist, 0)

    def test_locate_point_join(self):
        locs = [
            {"bbox_minx": 77.9, "bbox_miny": 29.9, "bbox_maxx": 78.1,
             "bbox_maxy": 30.1, "geometry": _square(78, 30, 0.1), "id": 1},
            {"bbox_minx": 78.9, "bbox_miny": 29.9, "bbox_maxx": 79.1,
             "bbox_maxy": 30.1, "geometry": _square(79, 30, 0.1), "id": 2},
        ]
        hit = spatial.locate_point(78.0, 30.0, locs)
        self.assertIsNotNone(hit)
        self.assertEqual(hit["id"], 1)
        miss = spatial.locate_point(50.0, 10.0, locs)
        self.assertIsNone(miss)


if __name__ == "__main__":
    unittest.main()
