"""
Unit tests for Lake Erie Simulation Water Regions geometry, shoreline constraints,
and buoy snapping behavior.
"""

import unittest
from buoy_sim.zones.water_regions import (
    SIMULATION_ZONES,
    get_zone_from_lat_lon,
    get_zone_water_conditions,
    snap_to_lake_erie_water,
    get_lake_erie_shoreline_lat,
    is_point_in_lake_erie,
    point_in_polygon,
)
from buoy_sim.esp32.system import BuoySystem


class TestWaterRegionsGeometry(unittest.TestCase):
    """Test suite covering the 8 geometry requirements."""

    def test_1_all_five_zones_exist(self):
        """1. All five zones exist."""
        expected_zones = {
            "open_lake",
            "urban_nearshore",
            "river_inflow",
            "runoff_zone",
            "reference_zone",
        }
        self.assertEqual(set(SIMULATION_ZONES.keys()), expected_zones)

    def test_2_all_five_zones_have_valid_geographic_coordinates(self):
        """2. All five zones have valid geographic coordinates."""
        for zid, zone in SIMULATION_ZONES.items():
            self.assertIn("polygon", zone)
            poly = zone["polygon"]
            self.assertGreaterEqual(len(poly), 3, f"Zone {zid} polygon must have at least 3 vertices")
            for pt in poly:
                lat, lon = pt
                # Coordinates must be in Lake Erie Cleveland/Euclid regional bounds
                self.assertTrue(41.53 <= lat <= 41.66, f"Lat {lat} out of bounds in zone {zid}")
                self.assertTrue(-81.65 <= lon <= -81.48, f"Lon {lon} out of bounds in zone {zid}")

    def test_3_zone_geometry_constrained_to_water_boundary(self):
        """3. Zone geometry is constrained to the water boundary (ZERO land coverage)."""
        for zid, zone in SIMULATION_ZONES.items():
            poly = zone["polygon"]
            for pt in poly:
                lat, lon = pt
                shore_lat = get_lake_erie_shoreline_lat(lon)
                # Every polygon vertex must be strictly in the water (north of the shoreline)
                self.assertGreaterEqual(
                    lat,
                    shore_lat,
                    f"Vertex ({lat}, {lon}) in zone {zid} is south of shoreline {shore_lat} (ON LAND)!"
                )

    def test_4_valid_water_coordinate_identifies_correct_zone(self):
        """4. A valid water coordinate identifies the correct zone."""
        test_points = {
            "open_lake": (41.6350, -81.5650),
            "urban_nearshore": (41.5750, -81.6100),
            "river_inflow": (41.5950, -81.5700),
            "runoff_zone": (41.6180, -81.5400),
            "reference_zone": (41.6320, -81.5050),
        }
        for expected_zone, (lat, lon) in test_points.items():
            zone = get_zone_from_lat_lon(lat, lon)
            self.assertEqual(
                zone["id"],
                expected_zone,
                f"Coord ({lat}, {lon}) expected {expected_zone} but got {zone['id']}"
            )

    def test_5_land_coordinate_cannot_become_buoy_position(self):
        """5. A land coordinate cannot become the buoy position (snapped to water)."""
        land_coords = [
            (41.5300, -81.6350),  # Gordon Park land / I-90
            (41.5400, -81.6100),  # Bratenahl neighborhoods
            (41.5600, -81.5800),  # Collinwood streets
            (41.5800, -81.5600),  # Euclid Creek inland
            (41.6000, -81.5300),  # Euclid neighborhoods
            (41.6100, -81.5000),  # Willowick inland
        ]
        for land_lat, land_lon in land_coords:
            snapped_lat, snapped_lon = snap_to_lake_erie_water(land_lat, land_lon)
            shore_lat = get_lake_erie_shoreline_lat(snapped_lon)
            # Snapped coordinate MUST be in the water
            self.assertGreater(
                snapped_lat,
                shore_lat,
                f"Land point ({land_lat}, {land_lon}) snapped to ({snapped_lat}, {snapped_lon}) which is still on land!"
            )

    def test_6_moving_buoy_between_valid_zones_changes_active_zone(self):
        """6. Moving the buoy between valid zones changes the active zone."""
        system = BuoySystem()
        # Move to urban_nearshore
        system.set_buoy_lat_lon(41.5750, -81.6100)
        zone1 = get_zone_from_lat_lon(system.gps.latitude, system.gps.longitude)
        self.assertEqual(zone1["id"], "urban_nearshore")

        # Move to river_inflow
        system.set_buoy_lat_lon(41.5950, -81.5700)
        zone2 = get_zone_from_lat_lon(system.gps.latitude, system.gps.longitude)
        self.assertEqual(zone2["id"], "river_inflow")

        # Move to open_lake
        system.set_buoy_lat_lon(41.6350, -81.5650)
        zone3 = get_zone_from_lat_lon(system.gps.latitude, system.gps.longitude)
        self.assertEqual(zone3["id"], "open_lake")

    def test_7_moving_buoy_between_zones_changes_water_quality(self):
        """7. Moving the buoy between zones changes pH/EC/turbidity/temperature."""
        wq_open = get_zone_water_conditions("open_lake", 41.6350, -81.5650, 0.0)
        wq_inflow = get_zone_water_conditions("river_inflow", 41.5950, -81.5700, 0.0)
        wq_runoff = get_zone_water_conditions("runoff_zone", 41.6180, -81.5400, 0.0)

        # Turbidity in river inflow & runoff should be noticeably higher than open lake
        self.assertGreater(wq_inflow["turbidity_ntu"], wq_open["turbidity_ntu"])
        self.assertGreater(wq_runoff["turbidity_ntu"], wq_open["turbidity_ntu"])
        # EC in runoff should be significantly higher than open lake
        self.assertGreater(wq_runoff["ec_us_cm"], wq_open["ec_us_cm"])
        # pH differs between open lake and runoff
        self.assertNotEqual(wq_open["ph"], wq_runoff["ph"])

    def test_8_existing_apis_continue_to_work(self):
        """8. Existing APIs continue to work."""
        from buoy_sim.web.app import app
        with app.test_client() as client:
            # Check /api/zones
            res_zones = client.get("/api/zones")
            self.assertEqual(res_zones.status_code, 200)
            data_zones = res_zones.get_json()
            self.assertEqual(len(data_zones["zones"]), 5)

            # Check /api/buoy/position with a land coordinate -> must snap to water
            res_pos = client.post("/api/buoy/position", json={"latitude": 41.5300, "longitude": -81.6350})
            self.assertEqual(res_pos.status_code, 200)
            data_pos = res_pos.get_json()
            shore_lat = get_lake_erie_shoreline_lat(data_pos["longitude"])
            self.assertGreater(data_pos["latitude"], shore_lat)

            # Check /api/status
            res_status = client.get("/api/status")
            self.assertEqual(res_status.status_code, 200)
            data_status = res_status.get_json()
            self.assertIn("sim_zone", data_status)
            self.assertIn("water_quality", data_status)


if __name__ == "__main__":
    unittest.main()
