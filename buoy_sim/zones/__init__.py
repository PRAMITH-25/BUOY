"""Simulation Water Zones Package."""
from buoy_sim.zones.water_regions import (
    SIMULATION_ZONES,
    get_zone_from_lat_lon,
    get_zone_water_conditions,
    generate_sensor_readings,
    get_all_zones_geojson,
    is_point_in_lake_erie,
    snap_to_lake_erie_water,
    get_lake_erie_shoreline_lat,
    LAKE_ERIE_SHORELINE,
)

__all__ = [
    "SIMULATION_ZONES",
    "get_zone_from_lat_lon",
    "get_zone_water_conditions",
    "generate_sensor_readings",
    "get_all_zones_geojson",
    "is_point_in_lake_erie",
    "snap_to_lake_erie_water",
    "get_lake_erie_shoreline_lat",
    "LAKE_ERIE_SHORELINE",
]
