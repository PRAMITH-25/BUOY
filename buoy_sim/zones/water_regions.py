"""
Simulation Water Regions for Lake Erie (Cleveland/Euclid Nearshore).
Defines clearly-labeled simulation zones, baseline water quality ranges,
Lake Erie shoreline boundary restriction, and deterministic sensor value generation.

DISCLAIMER: This is a digital simulation. These regional water traits are
defined simulation models for educational/digital-twin demonstration,
not verified scientific pollution boundaries or live hardware readings.
"""

from typing import Dict, Any, List, Tuple
import math

# Shoreline trace along Lake Erie (Lat, Lon) derived from OpenStreetMap tile geometry:
# South of this line (lower latitude) is LAND (Cleveland, Bratenahl, Euclid).
# North of this line (higher latitude) is LAKE ERIE WATER.
LAKE_ERIE_SHORELINE: List[Tuple[float, float]] = [
    (41.54418, -81.64490),
    (41.54610, -81.63803),
    (41.54829, -81.63391),
    (41.54829, -81.62979),
    (41.54983, -81.62430),
    (41.54880, -81.62018),
    (41.55548, -81.61606),
    (41.55869, -81.61057),
    (41.56088, -81.60645),
    (41.56319, -81.60233),
    (41.56858, -81.59821),
    (41.57333, -81.59271),
    (41.57398, -81.58859),
    (41.57950, -81.58310),
    (41.58412, -81.57623),
    (41.58707, -81.57211),
    (41.58874, -81.56799),
    (41.59375, -81.56387),
    (41.59940, -81.55701),
    (41.60274, -81.55289),
    (41.60736, -81.54739),
    (41.61044, -81.54327),
    (41.61288, -81.53915),
    (41.61583, -81.53366),
    (41.61737, -81.52954),
    (41.61608, -81.52542),
    (41.61955, -81.52130),
    (41.62070, -81.51718),
    (41.62263, -81.51306),
    (41.62571, -81.50620),
    (41.62789, -81.50208),
    (41.63097, -81.49658),
    (41.63777, -81.49109),
    (41.63700, -81.48148),
]


def get_lake_erie_shoreline_lat(lon: float) -> float:
    """Return the latitude of the Lake Erie shoreline at a given longitude."""
    if lon <= LAKE_ERIE_SHORELINE[0][1]:
        return LAKE_ERIE_SHORELINE[0][0]
    if lon >= LAKE_ERIE_SHORELINE[-1][1]:
        return LAKE_ERIE_SHORELINE[-1][0]
    for i in range(len(LAKE_ERIE_SHORELINE) - 1):
        lat1, lon1 = LAKE_ERIE_SHORELINE[i]
        lat2, lon2 = LAKE_ERIE_SHORELINE[i + 1]
        if lon1 <= lon <= lon2:
            return lat1 + (lon - lon1) * (lat2 - lat1) / (lon2 - lon1)
    return LAKE_ERIE_SHORELINE[-1][0]


def is_point_in_lake_erie(lat: float, lon: float) -> bool:
    """Check if coordinate is in the water (north of the shoreline and in demo bounds)."""
    shore_lat = get_lake_erie_shoreline_lat(lon)
    return lat >= (shore_lat + 0.0006) and (lat <= 41.660) and (-81.650 <= lon <= -81.480)


def snap_to_lake_erie_water(lat: float, lon: float) -> Tuple[float, float]:
    """Snap a coordinate to valid Lake Erie water if it falls on land or out of bounds."""
    clamped_lon = max(-81.635, min(-81.490, lon))
    shore_lat = get_lake_erie_shoreline_lat(clamped_lon)
    # Ensure point is in the water (north of the shoreline)
    min_water_lat = shore_lat + 0.0008
    clamped_lat = max(lat, min_water_lat)
    clamped_lat = min(clamped_lat, 41.648)
    return round(clamped_lat, 5), round(clamped_lon, 5)


SIMULATION_ZONES: Dict[str, Dict[str, Any]] = {
    "open_lake": {
        "id": "open_lake",
        "name": "OPEN LAKE — SIMULATION ZONE",
        "short_name": "OPEN LAKE",
        "description": "Normal/stable simulated conditions in offshore open lake waters",
        "color": "#0284c7",
        "fill_color": "#38bdf8",
        "fill_opacity": 0.22,
        "baseline": {
            "ph": 8.15,
            "ph_range": (7.8, 8.4),
            "ec_us_cm": 290.0,
            "ec_range": (250.0, 330.0),
            "turbidity_ntu": 1.25,
            "turbidity_range": (0.5, 2.0),
            "water_temp_c": 23.0,
            "temp_range": (20.0, 26.0),
        },
        # Offshore Lake Erie deep water zone (strictly north of all nearshore zones)
        "polygon": [
            [41.6500, -81.6350],
            [41.6500, -81.4900],
            [41.6420, -81.4900],
            [41.6250, -81.5250],
            [41.6140, -81.5550],
            [41.6020, -81.5850],
            [41.5950, -81.6350],
        ],
    },
    "urban_nearshore": {
        "id": "urban_nearshore",
        "name": "URBAN NEARSHORE — SIMULATION ZONE",
        "short_name": "URBAN NEARSHORE",
        "description": "Moderately elevated simulated EC and turbidity near urban shoreline",
        "color": "#d97706",
        "fill_color": "#f59e0b",
        "fill_opacity": 0.25,
        "baseline": {
            "ph": 7.95,
            "ph_range": (7.6, 8.3),
            "ec_us_cm": 350.0,
            "ec_range": (300.0, 400.0),
            "turbidity_ntu": 4.0,
            "turbidity_range": (2.0, 6.0),
            "water_temp_c": 23.5,
            "temp_range": (20.0, 27.0),
        },
        # Water zone off Bratenahl / Gordon park, southern boundary strictly follows shoreline in water
        "polygon": [
            [41.5950, -81.6350],
            [41.6020, -81.5850],
            [41.57859, -81.5850],
            [41.57467, -81.59056],
            [41.57139, -81.59611],
            [41.56505, -81.60167],
            [41.56147, -81.60722],
            [41.55840, -81.61278],
            [41.55280, -81.61833],
            [41.55073, -81.62389],
            [41.54939, -81.62944],
            [41.54871, -81.6350],
        ],
    },
    "river_inflow": {
        "id": "river_inflow",
        "name": "RIVER INFLOW — SIMULATION ZONE",
        "short_name": "RIVER INFLOW",
        "description": "Higher simulated turbidity and changing EC from tributary inflow",
        "color": "#dc2626",
        "fill_color": "#ef4444",
        "fill_opacity": 0.28,
        "baseline": {
            "ph": 7.75,
            "ph_range": (7.4, 8.1),
            "ec_us_cm": 385.0,
            "ec_range": (320.0, 450.0),
            "turbidity_ntu": 10.0,
            "turbidity_range": (5.0, 15.0),
            "water_temp_c": 21.5,
            "temp_range": (18.0, 25.0),
        },
        # Water delta off Euclid Creek mouth, strictly north of shoreline in water
        "polygon": [
            [41.6020, -81.5850],
            [41.6140, -81.5550],
            [41.60203, -81.5550],
            [41.59931, -81.55833],
            [41.59656, -81.56167],
            [41.59338, -81.5650],
            [41.58960, -81.56833],
            [41.58825, -81.57167],
            [41.58600, -81.5750],
            [41.58371, -81.57833],
            [41.58146, -81.58167],
            [41.57859, -81.5850],
        ],
    },
    "runoff_zone": {
        "id": "runoff_zone",
        "name": "INDUSTRIAL / STORMWATER RUNOFF — SIMULATION ZONE",
        "short_name": "RUNOFF ZONE",
        "description": "Elevated simulated turbidity and EC from surface runoff drainage",
        "color": "#7c3aed",
        "fill_color": "#8b5cf6",
        "fill_opacity": 0.26,
        "baseline": {
            "ph": 7.65,
            "ph_range": (7.3, 8.0),
            "ec_us_cm": 425.0,
            "ec_range": (350.0, 500.0),
            "turbidity_ntu": 14.0,
            "turbidity_range": (8.0, 20.0),
            "water_temp_c": 22.0,
            "temp_range": (18.0, 26.0),
        },
        # Water zone off east Collinwood / west Euclid shore, strictly north of shoreline in water
        "polygon": [
            [41.6140, -81.5550],
            [41.6250, -81.5250],
            [41.61743, -81.5250],
            [41.61799, -81.52833],
            [41.61757, -81.53167],
            [41.61611, -81.5350],
            [41.61432, -81.53833],
            [41.61239, -81.54167],
            [41.61015, -81.5450],
            [41.60757, -81.54833],
            [41.60476, -81.55167],
            [41.60203, -81.5550],
        ],
    },
    "reference_zone": {
        "id": "reference_zone",
        "name": "REFERENCE CLEAN WATER — SIMULATION ZONE",
        "short_name": "REFERENCE ZONE",
        "description": "Relatively stable simulated baseline water quality reference site",
        "color": "#059669",
        "fill_color": "#10b981",
        "fill_opacity": 0.22,
        "baseline": {
            "ph": 8.10,
            "ph_range": (7.8, 8.4),
            "ec_us_cm": 285.0,
            "ec_range": (250.0, 320.0),
            "turbidity_ntu": 1.10,
            "turbidity_range": (0.5, 2.0),
            "water_temp_c": 22.5,
            "temp_range": (20.0, 26.0),
        },
        # Eastern nearshore-to-offshore water off Euclid / Lake County, strictly in water
        "polygon": [
            [41.6250, -81.5250],
            [41.6420, -81.4900],
            [41.63868, -81.4900],
            [41.63530, -81.49389],
            [41.63130, -81.49778],
            [41.62912, -81.50167],
            [41.62705, -81.50556],
            [41.62526, -81.50944],
            [41.62350, -81.51333],
            [41.62169, -81.51722],
            [41.62060, -81.52111],
            [41.61743, -81.5250],
        ],
    },
}


def point_in_polygon(lat: float, lon: float, polygon: List[List[float]]) -> bool:
    """Ray casting algorithm to determine if point (lat, lon) is inside polygon."""
    n = len(polygon)
    if n < 3:
        return False
    inside = False
    p1_lat, p1_lon = polygon[0]
    for i in range(1, n + 1):
        p2_lat, p2_lon = polygon[i % n]
        if min(p1_lon, p2_lon) < lon <= max(p1_lon, p2_lon):
            if p1_lon != p2_lon:
                lat_inters = (lon - p1_lon) * (p2_lat - p1_lat) / (p2_lon - p1_lon) + p1_lat
                if lat <= lat_inters:
                    inside = not inside
        p1_lat, p1_lon = p2_lat, p2_lon
    return inside


def get_zone_from_lat_lon(lat: float, lon: float) -> Dict[str, Any]:
    """
    Determine which simulation zone contains the given GPS coordinates.
    If the coordinate is on land, it is snapped to the nearest valid Lake Erie water coordinate.
    Priority check: Specialized zones first (River Inflow, Runoff, Urban, Reference),
    defaulting to Open Lake.
    """
    lat, lon = snap_to_lake_erie_water(lat, lon)
    check_order = ["river_inflow", "runoff_zone", "urban_nearshore", "reference_zone", "open_lake"]
    for zone_id in check_order:
        zone = SIMULATION_ZONES[zone_id]
        if point_in_polygon(lat, lon, zone["polygon"]):
            return zone

    # Fallback to Open Lake
    return SIMULATION_ZONES["open_lake"]


def get_zone_water_conditions(
    zone_id: str,
    lat: float = 0.0,
    lon: float = 0.0,
    sim_time_s: float = 0.0
) -> Dict[str, Any]:
    """
    Generate deterministic, reproducible water-quality values for the specified zone,
    adhering strictly to configured simulation baseline and bounds.
    """
    zone = SIMULATION_ZONES.get(zone_id, SIMULATION_ZONES["open_lake"])
    base = zone["baseline"]

    # Deterministic spatial micro-perturbation (+/- 10% of span)
    h = math.sin(lat * 800.0) * math.cos(lon * 800.0)
    t_phase = math.sin((sim_time_s / 3600.0) * (2.0 * math.pi / 24.0)) * 0.05

    ph_min, ph_max = base["ph_range"]
    ec_min, ec_max = base["ec_range"]
    turb_min, turb_max = base["turbidity_range"]
    temp_min, temp_max = base["temp_range"]

    ph_span = (ph_max - ph_min) * 0.12
    ec_span = (ec_max - ec_min) * 0.12
    turb_span = (turb_max - turb_min) * 0.12
    temp_span = (temp_max - temp_min) * 0.12

    ph = max(ph_min, min(ph_max, base["ph"] + h * ph_span + t_phase * 0.05))
    ec = max(ec_min, min(ec_max, base["ec_us_cm"] + h * ec_span + t_phase * 3.0))
    turb = max(turb_min, min(turb_max, base["turbidity_ntu"] + abs(h) * turb_span + t_phase * 0.1))
    temp = max(temp_min, min(temp_max, base["water_temp_c"] + h * temp_span + t_phase * 0.4))

    return {
        "ph": round(ph, 2),
        "ec_us_cm": round(ec, 1),
        "turbidity_ntu": round(turb, 2),
        "water_temp_c": round(temp, 2),
        "tds_ppm": round(ec * 0.50, 1),
        "zone_id": zone["id"],
        "zone_name": zone["name"],
        "short_name": zone["short_name"],
        "description": zone["description"],
        "simulation_disclaimer": "SIMULATED SENSOR DATA — NOT LIVE HARDWARE",
    }


def generate_sensor_readings(
    lat: float,
    lon: float,
    sim_time_s: float = 0.0
) -> Dict[str, Any]:
    """Convenience pipeline: GPS -> Snap to Water -> Zone -> Water Conditions."""
    lat, lon = snap_to_lake_erie_water(lat, lon)
    zone = get_zone_from_lat_lon(lat, lon)
    return get_zone_water_conditions(zone["id"], lat, lon, sim_time_s)


def get_all_zones_geojson() -> List[Dict[str, Any]]:
    """Return list of simulation zones formatted for frontend Leaflet layer rendering."""
    result = []
    for z in SIMULATION_ZONES.values():
        result.append({
            "id": z["id"],
            "name": z["name"],
            "short_name": z["short_name"],
            "description": z["description"],
            "color": z["color"],
            "fill_color": z["fill_color"],
            "fill_opacity": z["fill_opacity"],
            "polygon": z["polygon"],
            "baseline": z["baseline"],
        })
    return result
