"""
Unit Tests for 2D Interactive Virtual Lake/River Spatial Environment.
Verifies:
- Buoy position changes and GPS synchronization
- Spatially varying sensor value changes (pH, EC, turbidity, temperature) across zones
- Exact mathematical reproducibility at identical (position, time) queries
- Map boundary validation and coordinate clamping
"""
import math
import unittest
from buoy_sim.esp32.system import BuoySystem
from buoy_sim.sensors.environment import LakeEnvironment
from buoy_sim.sensors.spatial_field import (
    SpatialEnvironmentField, map_xy_to_lat_lon, lat_lon_to_map_xy,
    MAP_WIDTH_METERS, MAP_HEIGHT_METERS,
    ZONE_NORMAL, ZONE_RUNOFF, ZONE_HIGH_COND, ZONE_MIXING
)
from buoy_sim.core.config import DEFAULT_LATITUDE, DEFAULT_LONGITUDE

class TestSpatialEnvironment(unittest.TestCase):
    def setUp(self):
        self.field = SpatialEnvironmentField()
        self.env = LakeEnvironment()
        self.system = BuoySystem()

    def test_buoy_position_changes(self):
        """Verify moving the buoy updates coordinates, GPS anchor, and system state."""
        # Initial position should be at default center
        self.assertEqual(self.system.buoy_x, 500.0)
        self.assertEqual(self.system.buoy_y, 300.0)

        # Move buoy to northwest runoff area
        pos_info = self.system.set_buoy_position(160.0, 130.0)
        self.assertEqual(self.system.buoy_x, 160.0)
        self.assertEqual(self.system.buoy_y, 130.0)
        self.assertEqual(pos_info["buoy_x"], 160.0)
        self.assertEqual(pos_info["buoy_y"], 130.0)
        self.assertEqual(pos_info["zone_id"], ZONE_RUNOFF)

        # Verify GPS coordinates updated to match the new location
        expected_lat, expected_lon = map_xy_to_lat_lon(160.0, 130.0)
        self.assertAlmostEqual(self.system.gps.anchor_lat, expected_lat, places=4)
        self.assertAlmostEqual(self.system.gps.anchor_lon, expected_lon, places=4)

        # Execute a simulation step and verify snapshot contains updated spatial metadata
        snap = self.system.step(1.0)
        self.assertIn("spatial", snap)
        self.assertEqual(snap["spatial"]["buoy_x"], 160.0)
        self.assertEqual(snap["spatial"]["buoy_y"], 130.0)
        self.assertEqual(snap["spatial"]["zone_id"], ZONE_RUNOFF)
        self.assertIn("flow_speed_m_s", snap["spatial"])
        self.assertIn("flow_direction_deg", snap["spatial"])

    def test_spatial_sensor_value_changes(self):
        """Verify that pH, EC, turbidity, and water temp change distinctly across regions."""
        sim_time = 3600.0 * 12.0  # Solar noon

        # 1. Normal Water Basin (Pelagic deep water)
        cond_normal = self.env.get_spatial_conditions(800.0, 300.0, sim_time)
        self.assertEqual(cond_normal["zone_id"], ZONE_NORMAL)

        # 2. Runoff Region (High Turbidity, cooler, lower pH)
        cond_runoff = self.env.get_spatial_conditions(160.0, 130.0, sim_time)
        self.assertEqual(cond_runoff["zone_id"], ZONE_RUNOFF)
        # Turbidity should spike massively in runoff plume
        self.assertGreater(cond_runoff["turbidity_ntu"], cond_normal["turbidity_ntu"] + 30.0)
        # Water temp should be cooler from tributary runoff
        self.assertLess(cond_runoff["water_temp_c"], cond_normal["water_temp_c"])
        # pH should be slightly more acidic due to runoff
        self.assertLess(cond_runoff["ph"], cond_normal["ph"])

        # 3. Higher-Conductivity Region (Mineral Inflow, elevated EC, warmer, higher pH)
        cond_high_ec = self.env.get_spatial_conditions(175.0, 480.0, sim_time)
        self.assertEqual(cond_high_ec["zone_id"], ZONE_HIGH_COND)
        # EC should be significantly higher
        self.assertGreater(cond_high_ec["ec_us_cm"], cond_normal["ec_us_cm"] + 200.0)
        # TDS should be proportionally higher
        self.assertGreater(cond_high_ec["tds_ppm"], cond_normal["tds_ppm"] + 100.0)
        # pH should be slightly elevated
        self.assertGreater(cond_high_ec["ph"], cond_normal["ph"])
        # Water temp should be slightly warmer
        self.assertGreater(cond_high_ec["water_temp_c"], cond_normal["water_temp_c"])

        # 4. Recovery & Mixing Region (Confluence intermediate values)
        cond_mix = self.env.get_spatial_conditions(540.0, 310.0, sim_time)
        self.assertEqual(cond_mix["zone_id"], ZONE_MIXING)
        # Intermediate turbidity between normal and plume core
        self.assertGreater(cond_mix["turbidity_ntu"], cond_normal["turbidity_ntu"])
        self.assertLess(cond_mix["turbidity_ntu"], cond_runoff["turbidity_ntu"])
        # Intermediate EC between normal and mineral inflow
        self.assertGreater(cond_mix["ec_us_cm"], cond_normal["ec_us_cm"])
        self.assertLess(cond_mix["ec_us_cm"], cond_high_ec["ec_us_cm"])

    def test_reproducibility_same_position_and_time(self):
        """Verify that identical (x, y, t) queries produce deterministic, reproducible results."""
        test_points = [
            (500.0, 300.0, 3600.0 * 8.0),
            (160.0, 130.0, 3600.0 * 12.0),
            (175.0, 480.0, 3600.0 * 15.5),
            (540.0, 310.0, 3600.0 * 20.0),
        ]

        for x, y, t in test_points:
            run1 = self.env.get_spatial_conditions(x, y, t)
            run2 = self.env.get_spatial_conditions(x, y, t)
            run3 = self.env.get_spatial_conditions(x, y, t)

            self.assertEqual(run1["ph"], run2["ph"])
            self.assertEqual(run1["ph"], run3["ph"])
            self.assertEqual(run1["ec_us_cm"], run2["ec_us_cm"])
            self.assertEqual(run1["ec_us_cm"], run3["ec_us_cm"])
            self.assertEqual(run1["turbidity_ntu"], run2["turbidity_ntu"])
            self.assertEqual(run1["turbidity_ntu"], run3["turbidity_ntu"])
            self.assertEqual(run1["water_temp_c"], run2["water_temp_c"])
            self.assertEqual(run1["water_temp_c"], run3["water_temp_c"])
            self.assertEqual(run1["zone_id"], run2["zone_id"])
            self.assertEqual(run1["flow_speed_m_s"], run2["flow_speed_m_s"])
            self.assertEqual(run1["flow_direction_deg"], run2["flow_direction_deg"])

    def test_valid_map_boundaries(self):
        """Verify coordinates outside the 1000m x 600m lake map are clamped safely without errors."""
        # Negative bounds clamping
        cx, cy = self.field.clamp_position(-50.0, -100.0)
        self.assertEqual(cx, 0.0)
        self.assertEqual(cy, 0.0)

        # Exceeding bounds clamping
        cx, cy = self.field.clamp_position(1500.0, 950.0)
        self.assertEqual(cx, MAP_WIDTH_METERS)
        self.assertEqual(cy, MAP_HEIGHT_METERS)

        # LakeEnvironment clamping
        ex, ey = self.env.set_buoy_position(-10.0, 800.0)
        self.assertEqual(ex, 0.0)
        self.assertEqual(ey, MAP_HEIGHT_METERS)
        self.assertEqual(self.env.buoy_x, 0.0)
        self.assertEqual(self.env.buoy_y, MAP_HEIGHT_METERS)

        # BuoySystem clamping
        sys_pos = self.system.set_buoy_position(2000.0, -500.0)
        self.assertEqual(sys_pos["buoy_x"], MAP_WIDTH_METERS)
        self.assertEqual(sys_pos["buoy_y"], 0.0)
        self.assertEqual(self.system.buoy_x, MAP_WIDTH_METERS)
        self.assertEqual(self.system.buoy_y, 0.0)

        # Verify conditions at extreme boundary points evaluate cleanly
        for bx, by in [(0.0, 0.0), (1000.0, 0.0), (0.0, 600.0), (1000.0, 600.0)]:
            cond = self.env.get_spatial_conditions(bx, by, 3600.0 * 10.0)
            self.assertGreater(cond["water_temp_c"], 0.0)
            self.assertGreater(cond["ph"], 0.0)
            self.assertGreater(cond["ec_us_cm"], 0.0)
            self.assertGreater(cond["turbidity_ntu"], 0.0)
            self.assertFalse(math.isnan(cond["ph"]))
            self.assertFalse(math.isnan(cond["turbidity_ntu"]))

    def test_lat_lon_conversion_roundtrip(self):
        """Verify map coordinate to GPS lat/lon and inverse conversion."""
        origin_x, origin_y = 500.0, 300.0
        lat, lon = map_xy_to_lat_lon(origin_x, origin_y)
        self.assertAlmostEqual(lat, DEFAULT_LATITUDE, places=4)
        self.assertAlmostEqual(lon, DEFAULT_LONGITUDE, places=4)

        rx, ry = lat_lon_to_map_xy(lat, lon)
        self.assertAlmostEqual(rx, origin_x, places=1)
        self.assertAlmostEqual(ry, origin_y, places=1)
