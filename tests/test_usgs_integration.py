"""
Unit Tests for USGS Lake Erie Dataset Integration.

Verifies:
1. CSV Loading & parsing safety with real column names
2. Missing-value handling (-999.9 sentinel exclusion)
3. Geographic bounds derivation and verification
4. Deterministic nearest-neighbor / KNN-IDW spatial lookup
5. Buoy movement and location-dependent lookup updates
6. Real-data value retrieval (pH, EC, turbidity, temperature; no dissolved oxygen)
7. Virtual X/Y <-> WGS84 Latitude/Longitude coordinate mapping and roundtrip
8. Environmental baseline integration in LakeEnvironment
"""
import os
import unittest
import math
from buoy_sim.data.usgs_loader import (
    USGSLoader, USGSLookup, map_xy_to_usgs_latlon, usgs_latlon_to_map_xy,
    LAT_MIN, LAT_MAX, LON_MIN, LON_MAX, INVALID_SENTINEL,
    MAP_WIDTH_METERS, MAP_HEIGHT_METERS
)
from buoy_sim.sensors.environment import LakeEnvironment
from buoy_sim.esp32.system import BuoySystem


class TestUSGSIntegration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.loader = USGSLoader()
        cls.lookup = USGSLookup(cls.loader, k=5)

    def setUp(self):
        self.env = LakeEnvironment()
        self.system = BuoySystem()

    # -------------------------------------------------------------
    # 1. CSV Loading Tests
    # -------------------------------------------------------------
    def test_csv_loading_row_counts(self):
        """Verify the USGS CSV loads successfully with expected record counts."""
        self.assertGreater(self.loader.raw_row_count, 0)
        self.assertEqual(self.loader.raw_row_count, 20811)
        self.assertEqual(len(self.loader.valid_records), 18679)
        self.assertEqual(self.loader.invalid_row_count, 2132)

    def test_csv_required_fields_present(self):
        """Verify all valid records contain the four required parameters plus lat/lon/timestamp."""
        required_keys = {"latitude", "longitude", "ph", "ec_us_cm", "turbidity_ntu", "water_temp_c", "timestamp"}
        first_record = self.loader.valid_records[0]
        for key in required_keys:
            self.assertIn(key, first_record)

    def test_dissolved_oxygen_excluded(self):
        """Verify dissolved oxygen is strictly excluded from parsed records (Req 5)."""
        for record in self.loader.valid_records[:100]:
            self.assertNotIn("dissolved_oxygen", record)
            self.assertNotIn("DO_mg_L", record)
            self.assertNotIn("do_mgl", record)

    # -------------------------------------------------------------
    # 2. Missing-Value Handling Tests
    # -------------------------------------------------------------
    def test_missing_value_sentinel_exclusion(self):
        """Verify no valid record contains the -999.9 invalid sentinel."""
        for rec in self.loader.valid_records:
            self.assertNotEqual(rec["ph"], INVALID_SENTINEL)
            self.assertNotEqual(rec["ec_us_cm"], INVALID_SENTINEL)
            self.assertNotEqual(rec["turbidity_ntu"], INVALID_SENTINEL)
            self.assertNotEqual(rec["water_temp_c"], INVALID_SENTINEL)
            self.assertNotEqual(rec["latitude"], INVALID_SENTINEL)
            self.assertNotEqual(rec["longitude"], INVALID_SENTINEL)

    def test_parse_row_rejects_invalid_values(self):
        """Verify _parse_row returns None when any required field has -999.9 or bad data."""
        bad_row_ph = {
            "Latitude_WGS84": "41.58", "Longitude_WGS84": "-81.58",
            "Temp_C": "22.5", "SpCond_uS_cm": "300.0", "pH": "-999.9", "Turbidity_NTU": "5.0"
        }
        self.assertIsNone(USGSLoader._parse_row(bad_row_ph))

        bad_row_corrupt = {
            "Latitude_WGS84": "N/A", "Longitude_WGS84": "-81.58",
            "Temp_C": "22.5", "SpCond_uS_cm": "300.0", "pH": "8.2", "Turbidity_NTU": "5.0"
        }
        self.assertIsNone(USGSLoader._parse_row(bad_row_corrupt))

    # -------------------------------------------------------------
    # 3. Geographic Bounds Tests
    # -------------------------------------------------------------
    def test_geographic_bounds_exactness(self):
        """Verify dataset geographic bounding box matches Lake Erie nearshore bounds."""
        bounds = self.loader.geo_bounds
        self.assertAlmostEqual(bounds["lat_min"], LAT_MIN, places=5)
        self.assertAlmostEqual(bounds["lat_max"], LAT_MAX, places=5)
        self.assertAlmostEqual(bounds["lon_min"], LON_MIN, places=5)
        self.assertAlmostEqual(bounds["lon_max"], LON_MAX, places=5)

        # Every valid record must fall strictly within the bounds
        for rec in self.loader.valid_records:
            self.assertGreaterEqual(rec["latitude"], bounds["lat_min"])
            self.assertLessEqual(rec["latitude"], bounds["lat_max"])
            self.assertGreaterEqual(rec["longitude"], bounds["lon_min"])
            self.assertLessEqual(rec["longitude"], bounds["lon_max"])

    # -------------------------------------------------------------
    # 4. Deterministic Lookup Tests (KNN-IDW)
    # -------------------------------------------------------------
    def test_deterministic_spatial_lookup(self):
        """Verify identical queries return exactly identical results (no randomness)."""
        test_coords = [
            (41.5750, -81.5850),
            (41.5660, -81.5990),
            (41.5930, -81.5600),
            (41.5800, -81.5750),
        ]
        for lat, lon in test_coords:
            r1 = self.lookup.query_by_latlon(lat, lon)
            r2 = self.lookup.query_by_latlon(lat, lon)
            r3 = self.lookup.query_by_latlon(lat, lon)

            self.assertEqual(r1["ph"], r2["ph"])
            self.assertEqual(r1["ph"], r3["ph"])
            self.assertEqual(r1["ec_us_cm"], r2["ec_us_cm"])
            self.assertEqual(r1["ec_us_cm"], r3["ec_us_cm"])
            self.assertEqual(r1["turbidity_ntu"], r2["turbidity_ntu"])
            self.assertEqual(r1["water_temp_c"], r2["water_temp_c"])
            self.assertEqual(r1["nearest_record_timestamp"], r2["nearest_record_timestamp"])

    def test_exact_match_lookup(self):
        """Querying at the exact coordinate of a record returns that record's values."""
        sample = self.loader.valid_records[42]
        res = self.lookup.query_by_latlon(sample["latitude"], sample["longitude"])
        self.assertAlmostEqual(res["ph"], sample["ph"], places=3)
        self.assertAlmostEqual(res["ec_us_cm"], sample["ec_us_cm"], places=1)
        self.assertAlmostEqual(res["turbidity_ntu"], sample["turbidity_ntu"], places=3)
        self.assertAlmostEqual(res["water_temp_c"], sample["water_temp_c"], places=3)

    # -------------------------------------------------------------
    # 5. Virtual X/Y <-> Lat/Lon Mapping Tests
    # -------------------------------------------------------------
    def test_xy_to_latlon_mapping_corners(self):
        """Verify corners of the virtual lake map map cleanly to dataset bounds."""
        lat_sw, lon_sw = map_xy_to_usgs_latlon(0.0, 0.0)
        self.assertAlmostEqual(lat_sw, LAT_MIN, places=5)
        self.assertAlmostEqual(lon_sw, LON_MIN, places=5)

        lat_ne, lon_ne = map_xy_to_usgs_latlon(MAP_WIDTH_METERS, MAP_HEIGHT_METERS)
        self.assertAlmostEqual(lat_ne, LAT_MAX, places=5)
        self.assertAlmostEqual(lon_ne, LON_MAX, places=5)

    def test_xy_latlon_roundtrip_consistency(self):
        """Verify mapping X/Y -> Lat/Lon -> X/Y preserves coordinates within rounding error."""
        test_points = [(100.0, 150.0), (500.0, 300.0), (850.0, 420.0), (0.0, 0.0), (1000.0, 600.0)]
        for orig_x, orig_y in test_points:
            lat, lon = map_xy_to_usgs_latlon(orig_x, orig_y)
            rec_x, rec_y = usgs_latlon_to_map_xy(lat, lon)
            self.assertAlmostEqual(orig_x, rec_x, delta=0.5)
            self.assertAlmostEqual(orig_y, rec_y, delta=0.5)

    # -------------------------------------------------------------
    # 6. Real-Data Value Retrieval & Range Validation
    # -------------------------------------------------------------
    def test_real_data_values_in_valid_ranges(self):
        """Verify looked-up values fall within established dataset physical ranges."""
        ranges = self.loader.param_ranges
        for x, y in [(100, 100), (500, 300), (900, 500), (250, 450)]:
            res = self.lookup.query_by_map_xy(x, y)
            self.assertGreaterEqual(res["ph"], ranges["ph"]["min"])
            self.assertLessEqual(res["ph"], ranges["ph"]["max"])

            self.assertGreaterEqual(res["ec_us_cm"], ranges["ec_us_cm"]["min"])
            self.assertLessEqual(res["ec_us_cm"], ranges["ec_us_cm"]["max"])

            self.assertGreaterEqual(res["turbidity_ntu"], ranges["turbidity_ntu"]["min"])
            self.assertLessEqual(res["turbidity_ntu"], ranges["turbidity_ntu"]["max"])

            self.assertGreaterEqual(res["water_temp_c"], ranges["water_temp_c"]["min"])
            self.assertLessEqual(res["water_temp_c"], ranges["water_temp_c"]["max"])

            self.assertEqual(res["data_source_label"], "USGS HISTORICAL DATA")

    # -------------------------------------------------------------
    # 7. Buoy Movement & Location-Dependent Integration Tests
    # -------------------------------------------------------------
    def test_buoy_movement_updates_usgs_lookups(self):
        """Moving the buoy to different locations queries different USGS locations."""
        pos1 = self.env.set_buoy_position(200.0, 150.0)
        gt1 = self.env.update(3600.0 * 10)
        usgs1 = gt1["usgs"]

        pos2 = self.env.set_buoy_position(800.0, 500.0)
        gt2 = self.env.update(3600.0 * 10)
        usgs2 = gt2["usgs"]

        # Different locations must have different USGS latitudes and longitudes
        self.assertNotEqual(usgs1["latitude"], usgs2["latitude"])
        self.assertNotEqual(usgs1["longitude"], usgs2["longitude"])
        self.assertEqual(gt1["data_source_label"], "USGS HISTORICAL DATA")
        self.assertEqual(gt2["data_source_label"], "USGS HISTORICAL DATA")

    def test_buoy_system_step_with_usgs_baseline(self):
        """Verify BuoySystem step produces sensor telemetry driven by USGS ground truth."""
        self.system.set_buoy_position(500.0, 300.0)
        snap = self.system.step(1.0)

        # Ground truth has real USGS data
        gt = snap["ground_truth"]
        self.assertIn("usgs", gt)
        self.assertEqual(gt["data_source_label"], "USGS HISTORICAL DATA")
        self.assertIn("usgs_latitude", gt)
        self.assertIn("usgs_longitude", gt)

        # Sensors sample the water with noise, ADC conversion, and filtering
        sensors = snap["sensors"]
        filtered = sensors["filtered"]
        self.assertGreater(filtered["ph"], 6.0)
        self.assertLess(filtered["ph"], 10.0)
        self.assertGreater(filtered["ec_us_cm"], 100.0)
        self.assertGreater(filtered["turbidity_ntu"], 0.0)
        self.assertGreater(filtered["temp_c"], 10.0)

    def test_dataset_info_metadata_structure(self):
        """Verify loader.get_info() returns complete metadata for dashboard (Req 16)."""
        info = self.loader.get_info()
        self.assertEqual(info["source"], "USGS")
        self.assertIn("Lake Erie", info["dataset"])
        self.assertEqual(info["total_rows"], 20811)
        self.assertEqual(info["valid_rows"], 18679)
        self.assertEqual(info["invalid_rows"], 2132)
        self.assertIn("geo_bounds", info)
        self.assertIn("param_ranges", info)
        self.assertEqual(info["data_source_label"], "USGS HISTORICAL DATA")


if __name__ == "__main__":
    unittest.main()
