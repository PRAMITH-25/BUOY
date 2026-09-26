"""
Geographic Location Configuration for the Autonomous Lake Water Quality Monitoring Buoy.

Provides a configurable demonstration site anchored to real geographic coordinates,
used for the real Leaflet map, GPS simulation, weather API, and USGS station searches.
"""
import os
from typing import Dict, Any, List

# Default demonstration location: Lake Erie Nearshore Sonde Transect (Cleveland/Euclid, OH)
# Matches the geographic extent of the USGS June 2019 nearshore water quality dataset.
DEFAULT_LOCATION_CONFIG: Dict[str, Any] = {
    "water_body_name": "Lake Erie (Cleveland / Euclid Nearshore)",
    "region": "Ohio, USA",
    "latitude": float(os.environ.get("BUOY_DEMO_LAT", 41.57963)),
    "longitude": float(os.environ.get("BUOY_DEMO_LON", -81.57919)),
    "zoom": int(os.environ.get("BUOY_DEMO_ZOOM", 13)),
    "bounds": {
        "lat_min": 41.565827,
        "lat_max": 41.593431,
        "lon_min": -81.599167,
        "lon_max": -81.559214,
    },
    "description": (
        "Demonstration site located along the southern shore of Lake Erie, "
        "anchored to the USGS nearshore water-quality sonde transect dataset (June 2019)."
    )
}

# Catalog of known real USGS monitoring stations in the surrounding region
NEARBY_MONITORING_STATIONS: List[Dict[str, Any]] = [
    {
        "station_id": "04208000",
        "station_name": "Cuyahoga River at Independence OH",
        "latitude": 41.385055,
        "longitude": -81.628741,
        "water_body": "Cuyahoga River (Lake Erie Tributary)",
        "agency": "USGS",
        "parameters_available": [
            {"code": "00010", "name": "Water Temperature", "unit": "°C"},
            {"code": "00400", "name": "pH", "unit": ""},
            {"code": "00095", "name": "Specific Conductance", "unit": "µS/cm"},
            {"code": "63680", "name": "Turbidity", "unit": "FNU"},
        ],
        "is_active": True,
    },
    {
        "station_id": "04200500",
        "station_name": "Black River at Elyria OH",
        "latitude": 41.365322,
        "longitude": -82.106819,
        "water_body": "Black River (Lake Erie Tributary)",
        "agency": "USGS",
        "parameters_available": [
            {"code": "00010", "name": "Water Temperature", "unit": "°C"},
            {"code": "00400", "name": "pH", "unit": ""},
            {"code": "00095", "name": "Specific Conductance", "unit": "µS/cm"},
            {"code": "63680", "name": "Turbidity", "unit": "FNU"},
        ],
        "is_active": True,
    },
    {
        "station_id": "04200508",
        "station_name": "Lake Erie at Cleveland Water Intake Crib",
        "latitude": 41.533333,
        "longitude": -81.750000,
        "water_body": "Lake Erie Central Basin",
        "agency": "USGS / NOAA GLERL",
        "parameters_available": [
            {"code": "00010", "name": "Water Temperature", "unit": "°C"},
            {"code": "00095", "name": "Specific Conductance", "unit": "µS/cm"},
            {"code": "63680", "name": "Turbidity", "unit": "FNU"},
        ],
        "is_active": True,
    },
    {
        "station_id": "04199500",
        "station_name": "Vermilion River near Vermilion OH",
        "latitude": 41.382828,
        "longitude": -82.355167,
        "water_body": "Vermilion River",
        "agency": "USGS",
        "parameters_available": [
            {"code": "00010", "name": "Water Temperature", "unit": "°C"},
            {"code": "00400", "name": "pH", "unit": ""},
            {"code": "00095", "name": "Specific Conductance", "unit": "µS/cm"},
        ],
        "is_active": True,
    },
]

# Active location state (can be modified at runtime if user selects a different location)
_current_location = dict(DEFAULT_LOCATION_CONFIG)


def get_location_config() -> Dict[str, Any]:
    """Return the current active demonstration location configuration."""
    return dict(_current_location)


def set_location_config(lat: float, lon: float, name: str = None) -> Dict[str, Any]:
    """Update demonstration coordinates and water body name."""
    _current_location["latitude"] = float(lat)
    _current_location["longitude"] = float(lon)
    if name:
        _current_location["water_body_name"] = str(name)
    return dict(_current_location)


def get_nearby_stations() -> List[Dict[str, Any]]:
    """Return catalog of nearby monitoring stations with distance calculation."""
    from math import radians, cos, sin, asin, sqrt

    buoy_lat = _current_location["latitude"]
    buoy_lon = _current_location["longitude"]

    def haversine_km(lat1, lon1, lat2, lon2):
        # Haversine formula to compute great-circle distance
        r = 6371.0
        dlat = radians(lat2 - lat1)
        dlon = radians(lon2 - lon1)
        a = sin(dlat / 2)**2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2)**2
        return 2 * r * asin(sqrt(a))

    stations = []
    for s in NEARBY_MONITORING_STATIONS:
        st_copy = dict(s)
        dist = haversine_km(buoy_lat, buoy_lon, s["latitude"], s["longitude"])
        st_copy["distance_km"] = round(dist, 2)
        stations.append(st_copy)

    # Sort by distance
    stations.sort(key=lambda x: x["distance_km"])
    return stations
