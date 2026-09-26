"""
Deterministic 2D Spatial Environmental Field Model for Lake/River Water Quality.
Provides spatially varying water quality properties (pH, EC, turbidity, water temperature)
over a virtual 2D lake/river body with distinct hydrological zones, water flow vectors,
GPS coordinate mapping, and reproducible time-dependent dynamics.
"""
import math
from typing import Dict, Any, Tuple
from buoy_sim.core.config import DEFAULT_LATITUDE, DEFAULT_LONGITUDE

MAP_WIDTH_METERS = 1000.0
MAP_HEIGHT_METERS = 600.0
DEFAULT_BUOY_X = 500.0
DEFAULT_BUOY_Y = 300.0

# Zone identifier constants
ZONE_NORMAL = "normal"
ZONE_RUNOFF = "runoff"
ZONE_HIGH_COND = "high_conductivity"
ZONE_MIXING = "mixing"

ZONE_NAMES = {
    ZONE_NORMAL: "Normal Water (Main Lake Basin)",
    ZONE_RUNOFF: "Runoff Region (High Turbidity)",
    ZONE_HIGH_COND: "Higher-Conductivity Inflow Region",
    ZONE_MIXING: "Recovery & Mixing Region",
}


def map_xy_to_lat_lon(
    x: float, y: float,
    origin_x: float = DEFAULT_BUOY_X,
    origin_y: float = DEFAULT_BUOY_Y,
    origin_lat: float = DEFAULT_LATITUDE,
    origin_lon: float = DEFAULT_LONGITUDE
) -> Tuple[float, float]:
    """Convert local lake map coordinates (meters) to GPS Latitude/Longitude aligned with Lake Erie USGS dataset."""
    from buoy_sim.data.usgs_loader import map_xy_to_usgs_latlon
    return map_xy_to_usgs_latlon(x, y)


def lat_lon_to_map_xy(
    lat: float, lon: float,
    origin_x: float = DEFAULT_BUOY_X,
    origin_y: float = DEFAULT_BUOY_Y,
    origin_lat: float = DEFAULT_LATITUDE,
    origin_lon: float = DEFAULT_LONGITUDE
) -> Tuple[float, float]:
    """Convert GPS Latitude/Longitude back to local lake map coordinates (meters) aligned with Lake Erie USGS dataset."""
    from buoy_sim.data.usgs_loader import usgs_latlon_to_map_xy
    return usgs_latlon_to_map_xy(lat, lon)


class SpatialEnvironmentField:
    """
    Deterministic 2D environmental field over a 1000m x 600m lake/river water body.
    Features:
    - Normal water pelagic basin
    - Runoff plume with elevated turbidity and cooler, slightly acidic runoff
    - Higher-conductivity mineral stream with elevated EC and TDS
    - Confluence / recovery mixing zone with transitional parameters
    - Continuous, smooth spatial gradients (no sharp steps)
    - Reproducible deterministic values at any (x, y, t)
    - Gradual time-dependent hydrodynamic evolution
    """

    def __init__(self, width: float = MAP_WIDTH_METERS, height: float = MAP_HEIGHT_METERS):
        self.width = width
        self.height = height

        # Plume Source 1: Runoff / Turbid Creek (Northwest)
        self.src_runoff_x = 160.0
        self.src_runoff_y = 130.0
        self.runoff_theta_rad = math.radians(26.0)  # Flowing ESE

        # Plume Source 2: Mineral / High-Conductivity Inflow (Southwest)
        self.src_cond_x = 175.0
        self.src_cond_y = 480.0
        self.cond_theta_rad = math.radians(-22.0)  # Flowing ENE

        # Confluence / Mixing Center (Mid-Lake)
        self.mix_center_x = 540.0
        self.mix_center_y = 310.0

    def clamp_position(self, x: float, y: float) -> Tuple[float, float]:
        """Clamp coordinates within valid map bounds."""
        cx = max(0.0, min(self.width, float(x)))
        cy = max(0.0, min(self.height, float(y)))
        return cx, cy

    def compute_weights(self, x: float, y: float, sim_time_s: float) -> Dict[str, float]:
        """
        Compute continuous influence weights for each environmental zone at (x, y, sim_time_s).
        Uses anisotropic oriented Gaussian dispersion with slow time pulsation.
        """
        cx, cy = self.clamp_position(x, y)

        # 1. Slow temporal hydrodynamic pulsation (~30 min & ~40 min cycles)
        time_factor_runoff = 1.0 + 0.06 * math.sin(2.0 * math.pi * sim_time_s / 1800.0)
        time_factor_cond = 1.0 + 0.05 * math.cos(2.0 * math.pi * sim_time_s / 2400.0)

        # 2. Runoff plume dispersion (rotated coordinates along flow angle)
        dx_r = cx - self.src_runoff_x
        dy_r = cy - self.src_runoff_y
        cos_r = math.cos(self.runoff_theta_rad)
        sin_r = math.sin(self.runoff_theta_rad)
        u_r = dx_r * cos_r + dy_r * sin_r
        v_r = -dx_r * sin_r + dy_r * cos_r

        sigma_u_r = 240.0 if u_r >= 0 else 85.0
        sigma_v_r = 105.0
        dist_sq_r = (u_r / sigma_u_r) ** 2 + (v_r / sigma_v_r) ** 2
        w_runoff = math.exp(-0.5 * dist_sq_r) * time_factor_runoff

        # 3. High-conductivity plume dispersion
        dx_c = cx - self.src_cond_x
        dy_c = cy - self.src_cond_y
        cos_c = math.cos(self.cond_theta_rad)
        sin_c = math.sin(self.cond_theta_rad)
        u_c = dx_c * cos_c + dy_c * sin_c
        v_c = -dx_c * sin_c + dy_c * cos_c

        sigma_u_c = 230.0 if u_c >= 0 else 80.0
        sigma_v_c = 100.0
        dist_sq_c = (u_c / sigma_u_c) ** 2 + (v_c / sigma_v_c) ** 2
        w_cond = math.exp(-0.5 * dist_sq_c) * time_factor_cond

        # 4. Mixing / Confluence zone
        dx_m = (cx - self.mix_center_x) / 160.0
        dy_m = (cy - self.mix_center_y) / 130.0
        w_mix_spatial = math.exp(-0.5 * (dx_m ** 2 + dy_m ** 2))
        # Mixing zone is naturally strongest where runoff and mineral plumes meet
        w_mix = max(w_mix_spatial * 0.65, min(1.0, 1.8 * (w_runoff * w_cond) ** 0.5))

        return {
            "w_runoff": max(0.0, min(1.2, w_runoff)),
            "w_cond": max(0.0, min(1.2, w_cond)),
            "w_mix": max(0.0, min(1.0, w_mix)),
        }

    def classify_zone(self, x: float, y: float, weights: Dict[str, float]) -> Tuple[str, str]:
        """Classify (x, y) into a distinct zone identifier and human-readable name."""
        w_r = weights["w_runoff"]
        w_c = weights["w_cond"]
        w_m = weights["w_mix"]

        if w_r > 0.35 and w_r >= w_c:
            z_id = ZONE_RUNOFF
        elif w_c > 0.35:
            z_id = ZONE_HIGH_COND
        elif w_m > 0.28 or (w_r > 0.18 and w_c > 0.18):
            z_id = ZONE_MIXING
        else:
            z_id = ZONE_NORMAL

        return z_id, ZONE_NAMES[z_id]

    def compute_flow_vector(self, x: float, y: float, weights: Dict[str, float]) -> Tuple[float, float]:
        """
        Compute local water flow velocity vector (speed in m/s, direction in degrees 0-360).
        0° = East (downstream towards right of map), 90° = South.
        """
        w_r = weights["w_runoff"]
        w_c = weights["w_cond"]

        # Base lake eastward drift
        vx = 0.18
        vy = 0.02

        # Runoff stream flow contribution (ESE)
        vx += w_r * 0.38 * math.cos(self.runoff_theta_rad)
        vy += w_r * 0.38 * math.sin(self.runoff_theta_rad)

        # High-cond stream flow contribution (ENE)
        vx += w_c * 0.34 * math.cos(self.cond_theta_rad)
        vy += w_c * 0.34 * math.sin(self.cond_theta_rad)

        speed_m_s = round(float(math.hypot(vx, vy)), 3)
        direction_deg = round(float((math.degrees(math.atan2(vy, vx)) + 360.0) % 360.0), 1)

        return speed_m_s, direction_deg

    def compute_conditions(
        self,
        x: float,
        y: float,
        sim_time_s: float,
        base_diurnal: Dict[str, float],
        rain_intensity: float = 0.0
    ) -> Dict[str, Any]:
        """
        Calculate complete deterministic ground-truth water quality at (x, y, sim_time_s).
        Returns spatially modulated water_temp_c, ph, ec_us_cm, tds_ppm, turbidity_ntu,
        along with zone classification and water-flow vectors.
        """
        cx, cy = self.clamp_position(x, y)
        weights = self.compute_weights(cx, cy, sim_time_s)
        w_r = weights["w_runoff"]
        w_c = weights["w_cond"]
        w_m = weights["w_mix"]

        z_id, z_name = self.classify_zone(cx, cy, weights)
        flow_speed_m_s, flow_dir_deg = self.compute_flow_vector(cx, cy, weights)

        # Base values from diurnal baseline
        base_temp = base_diurnal.get("water_temp_c", 21.5)
        base_ph = base_diurnal.get("ph", 7.65)
        base_ec = base_diurnal.get("ec_us_cm", 380.0)
        base_turb = base_diurnal.get("turbidity_ntu", 8.5)

        # 1. Turbidity: massive elevation in runoff plume, mild in mineral stream, intermediate in mixing
        turbidity_delta = (
            w_r * (62.0 + 35.0 * rain_intensity) +
            w_c * 7.5 +
            w_m * 14.0
        )
        turbidity_ntu = round(max(0.5, base_turb + turbidity_delta), 2)

        # 2. Electrical Conductivity (EC) & TDS:
        # High in mineral inflow (+480 uS/cm), slight dilution in pure runoff (-75 uS/cm), intermediate in mixing
        ec_delta = (
            w_c * 490.0 -
            w_r * 78.0 +
            w_m * 135.0
        )
        ec_us_cm = round(max(20.0, base_ec + ec_delta), 1)
        tds_ppm = round(ec_us_cm * 0.50, 1)

        # 3. Water pH:
        # Rain/soil organic runoff lowers pH (-0.48), mineral stream raises it (+0.42), mixing buffers
        ph_delta = (
            -w_r * 0.48 +
            w_c * 0.42 -
            w_m * 0.06
        )
        ph = round(max(4.0, min(10.0, base_ph + ph_delta)), 2)

        # 4. Water Temperature:
        # Cool mountain creek runoff lowers temp (-2.2 °C), mineral stream is slightly warmer (+1.4 °C)
        temp_delta = (
            -w_r * 2.2 +
            w_c * 1.4 -
            w_m * 0.3
        )
        water_temp_c = round(max(1.0, min(42.0, base_temp + temp_delta)), 2)

        return {
            "buoy_x": cx,
            "buoy_y": cy,
            "zone_id": z_id,
            "zone_name": z_name,
            "water_temp_c": water_temp_c,
            "ph": ph,
            "ec_us_cm": ec_us_cm,
            "tds_ppm": tds_ppm,
            "turbidity_ntu": turbidity_ntu,
            "flow_speed_m_s": flow_speed_m_s,
            "flow_direction_deg": flow_dir_deg,
            "weights": weights,
        }

