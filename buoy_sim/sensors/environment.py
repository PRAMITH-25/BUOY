"""
Virtual Lake Environment simulation.
Generates realistic lake ground truth with diurnal cycles, weather effects (rain runoff),
solar elevation, and surface wave motion.

USGS Integration (June 2019 Lake Erie dataset):
    Water quality ground-truth (pH, EC, turbidity, water temperature) is sourced
    from real USGS sonde measurements via KNN-IDW lookup keyed on buoy latitude/longitude.
    The synthetic spatial field is retained for zone classification, flow vectors, and
    visual rendering, but does NOT override the USGS water-quality baseline.
    All USGS-derived values are clearly labelled 'USGS HISTORICAL DATA'.
"""
import math
from typing import Dict, Any, Optional, Tuple
from buoy_sim.core.config import BASE_LAKE_PARAMS
from buoy_sim.sensors.spatial_field import (
    SpatialEnvironmentField, DEFAULT_BUOY_X, DEFAULT_BUOY_Y,
    ZONE_NORMAL, ZONE_NAMES
)
from buoy_sim.data.usgs_loader import (
    USGSLoader, USGSLookup, map_xy_to_usgs_latlon, LAT_MIN, LAT_MAX, LON_MIN, LON_MAX
)

class WeatherState:
    CLEAR = "CLEAR"
    CLOUDY = "CLOUDY"
    RAIN_RUNOFF = "RAIN_RUNOFF"

class LakeEnvironment:
    def __init__(self, base_params: Optional[Dict[str, float]] = None):
        self.params = dict(BASE_LAKE_PARAMS)
        if base_params:
            self.params.update(base_params)

        self.weather = WeatherState.CLEAR
        self.rain_intensity = 0.0      # 0.0 to 1.0
        self.cloud_cover = 0.15        # 0.0 (clear) to 1.0 (overcast)
        self.wind_speed_m_s = 2.5      # Baseline gentle lake breeze
        self.wave_height_m = 0.12      # Baseline wave height

        # 2D Spatial Lake/River Environment Field (retained for zones, flow, visuals)
        self.spatial_field = SpatialEnvironmentField()
        self.buoy_x = DEFAULT_BUOY_X
        self.buoy_y = DEFAULT_BUOY_Y
        self.current_zone_id = ZONE_NORMAL
        self.current_zone_name = ZONE_NAMES[ZONE_NORMAL]

        # USGS real-data integration
        # Loader and lookup are shared (loaded once at startup)
        self._usgs_loader: Optional[USGSLoader] = None
        self._usgs_lookup: Optional[USGSLookup] = None
        self._usgs_load_error: Optional[str] = None
        self._init_usgs()
        self._last_usgs_result: Dict[str, Any] = {}

        # Real online weather & water data inputs
        self.real_weather_data: Optional[Dict[str, Any]] = None
        self.real_water_data: Optional[Dict[str, Any]] = None
        self.real_solar_irradiance: Optional[float] = None

    def _init_usgs(self) -> None:
        """Load the USGS dataset once; store error string on failure (never crashes)."""
        try:
            self._usgs_loader = USGSLoader()
            self._usgs_lookup = USGSLookup(self._usgs_loader)
        except Exception as exc:
            self._usgs_load_error = str(exc)
            self._usgs_loader = None
            self._usgs_lookup = None

    @property
    def usgs_info(self) -> Dict[str, Any]:
        """Return USGS dataset summary for dashboard display."""
        if self._usgs_loader is not None:
            return self._usgs_loader.get_info()
        return {"error": self._usgs_load_error, "data_source_label": "USGS DATA UNAVAILABLE"}

    def get_usgs_conditions(self, x: float, y: float) -> Dict[str, Any]:
        """
        Query the USGS dataset for real water-quality values at virtual (x, y).

        The virtual coordinates are converted to USGS lat/lon via the
        documented linear mapping in buoy_sim.data.usgs_loader.
        Returns a dict with pH, EC, turbidity, temperature, lat, lon,
        and data-source metadata. Deterministic: same (x, y) -> same result.
        """
        if self._usgs_lookup is None:
            lat, lon = map_xy_to_usgs_latlon(x, y)
            return USGSLookup._fallback(lat, lon)
        return self._usgs_lookup.query_by_map_xy(x, y)

    def get_spatial_grid(self, param: str = "turbidity_ntu", cols: int = 50, rows: int = 30) -> Dict[str, Any]:
        """Return 2D interpolated grid of real USGS measurements across the lake map."""
        if self._usgs_lookup is not None:
            return self._usgs_lookup.generate_spatial_grid(param, cols, rows)
        return {"error": "USGS lookup not initialized", "grid": []}

    def set_buoy_position(self, x: float, y: float) -> Tuple[float, float]:
        """Set virtual buoy coordinates, clamping to valid lake boundaries."""
        cx, cy = self.spatial_field.clamp_position(x, y)
        self.buoy_x = cx
        self.buoy_y = cy
        weights = self.spatial_field.compute_weights(cx, cy, 0.0)
        z_id, z_name = self.spatial_field.classify_zone(cx, cy, weights)
        self.current_zone_id = z_id
        self.current_zone_name = z_name
        return cx, cy

    def get_current_zone_name(self) -> str:
        return self.current_zone_name

    def get_spatial_conditions(self, x: float, y: float, sim_time_s: float, use_usgs: bool = False) -> Dict[str, Any]:
        """
        Compute deterministic conditions at specific (x, y, sim_time_s).

        By default, returns the spatial field conditions with zone classification,
        flow vectors, and synthetic spatial gradients (preserving existing zone tests).
        If use_usgs=True, overrides water-quality parameters with real USGS data.
        In both cases, attaches real USGS observation data under 'usgs'.
        """
        cx, cy = self.spatial_field.clamp_position(x, y)

        hour_of_day = (sim_time_s / 3600.0) % 24.0
        temp_diurnal_offset = 2.2 * math.sin(math.pi * (hour_of_day - 9.5) / 12.0)
        ph_diurnal_offset = 0.35 * math.sin(math.pi * (hour_of_day - 7.0) / 12.0) if 6.0 <= hour_of_day <= 19.0 else -0.15
        dilution_factor = 1.0 - 0.18 * self.rain_intensity
        turbidity_spike = 95.0 * self.rain_intensity

        base_diurnal = {
            "water_temp_c": self.params["temperature_c"] + temp_diurnal_offset - 1.5 * self.rain_intensity,
            "ph": self.params["ph"] + ph_diurnal_offset - 0.25 * self.rain_intensity,
            "ec_us_cm": self.params["ec_us_cm"] * dilution_factor,
            "turbidity_ntu": self.params["turbidity_ntu"] + turbidity_spike,
        }
        res = self.spatial_field.compute_conditions(cx, cy, sim_time_s, base_diurnal, self.rain_intensity)

        usgs = self.get_usgs_conditions(cx, cy)
        res["usgs"] = usgs
        if use_usgs:
            res["water_temp_c"]  = usgs["water_temp_c"]
            res["ph"]            = usgs["ph"]
            res["ec_us_cm"]      = usgs["ec_us_cm"]
            res["tds_ppm"]       = round(usgs["ec_us_cm"] * 0.50, 1)
            res["turbidity_ntu"] = usgs["turbidity_ntu"]
        return res

    def update(self, sim_time_s: float, x: Optional[float] = None, y: Optional[float] = None) -> Dict[str, Any]:
        """
        Update lake ground truth according to time of day, weather, and buoy spatial position.
        sim_time_s is elapsed simulation time in seconds.

        Water quality (pH, EC, turbidity, water_temp_c) uses the USGS historical
        dataset as the environmental baseline via deterministic KNN-IDW lookup.
        When clear (rain_intensity == 0.0), water-quality values match the USGS
        measurements exactly. Solar, wave, zone, and flow values are computed
        by the existing synthetic model.
        """
        if x is not None:
            self.buoy_x = float(x)
        if y is not None:
            self.buoy_y = float(y)
        self.buoy_x, self.buoy_y = self.spatial_field.clamp_position(self.buoy_x, self.buoy_y)

        hour_of_day = (sim_time_s / 3600.0) % 24.0

        # 1. Solar irradiance (uses real shortwave radiation if available, otherwise diurnal calculation)
        if self.real_solar_irradiance is not None and self.real_solar_irradiance > 0.0:
            solar_irradiance_w_m2 = round(self.real_solar_irradiance, 1)
        else:
            solar_angle = math.sin(math.pi * (hour_of_day - 6.0) / 12.0) if 6.0 <= hour_of_day <= 18.0 else 0.0
            base_irradiance_w_m2 = max(0.0, 1000.0 * solar_angle)
            attenuation = (1.0 - 0.75 * self.cloud_cover) * (1.0 - 0.5 * self.rain_intensity)
            solar_irradiance_w_m2 = base_irradiance_w_m2 * attenuation

        # 2. Weather effect deltas
        rain_cooling = -1.5 * self.rain_intensity
        ph_rain_effect = -0.25 * self.rain_intensity
        dilution_factor = 1.0 - 0.18 * self.rain_intensity
        turbidity_spike = 95.0 * self.rain_intensity

        base_diurnal = {
            "water_temp_c": self.params["temperature_c"] + rain_cooling,
            "ph": self.params["ph"] + ph_rain_effect,
            "ec_us_cm": self.params["ec_us_cm"] * dilution_factor,
            "turbidity_ntu": max(0.5, self.params["turbidity_ntu"] + turbidity_spike),
        }

        # 3. Spatial field -- zone classification and flow vectors
        spatial_res = self.spatial_field.compute_conditions(
            self.buoy_x, self.buoy_y, sim_time_s, base_diurnal, self.rain_intensity
        )
        self.current_zone_id = spatial_res["zone_id"]
        self.current_zone_name = spatial_res["zone_name"]

        # 4. Real USGS water-quality baseline via deterministic KNN-IDW lookup
        usgs = self.get_usgs_conditions(self.buoy_x, self.buoy_y)
        self._last_usgs_result = usgs

        # Weather modulation on top of USGS environmental baseline
        # When clear (rain_intensity == 0.0), exactly equals the USGS measurements
        water_temp_c = round(usgs["water_temp_c"] + rain_cooling, 2)
        ph = round(max(4.0, min(10.0, usgs["ph"] + ph_rain_effect)), 2)
        ec_us_cm = round(max(10.0, usgs["ec_us_cm"] * dilution_factor), 1)
        tds_ppm = round(ec_us_cm * 0.50, 1)
        turbidity_ntu = round(max(0.0, usgs["turbidity_ntu"] + turbidity_spike), 2)

        # 5. Lake surface wave dynamics (synthetic, unchanged)
        wave_agitation = 1.0 + 2.5 * self.rain_intensity
        effective_wave_height = self.wave_height_m * wave_agitation
        wave_period_s = 2.6 - 0.5 * min(1.0, self.rain_intensity)

        return {
            "hour_of_day":           hour_of_day,
            "solar_irradiance_w_m2": solar_irradiance_w_m2,
            # --- Water quality (USGS historical baseline modulated by weather) ---
            "water_temp_c":          water_temp_c,
            "ph":                    ph,
            "ec_us_cm":              ec_us_cm,
            "tds_ppm":               tds_ppm,
            "turbidity_ntu":         turbidity_ntu,
            # --- Raw USGS observations (unmodulated) ---
            "usgs_ph":               usgs["ph"],
            "usgs_ec":               usgs["ec_us_cm"],
            "usgs_turbidity":        usgs["turbidity_ntu"],
            "usgs_water_temp_c":     usgs["water_temp_c"],
            # --- Location & Metadata (from USGS mapping) ---
            "usgs_latitude":         usgs["latitude"],
            "usgs_longitude":        usgs["longitude"],
            "data_source_label":     "USGS HISTORICAL DATA",
            "usgs":                  usgs,
            "real_weather":          self.real_weather_data,
            # --- Synthetic / hardware model fields (unchanged) ---
            "wave_height_m":         effective_wave_height,
            "wave_period_s":         wave_period_s,
            "weather":               self.weather,
            "rain_intensity":        self.rain_intensity,
            "cloud_cover":           self.cloud_cover,
            "buoy_x":                self.buoy_x,
            "buoy_y":                self.buoy_y,
            "zone_id":               spatial_res["zone_id"],
            "zone_name":             spatial_res["zone_name"],
            "flow_speed_m_s":        spatial_res["flow_speed_m_s"],
            "flow_direction_deg":    spatial_res["flow_direction_deg"],
            "weights":               spatial_res["weights"],
        }

    def apply_weather_data(self, w: Dict[str, Any]) -> None:
        """Apply real Open-Meteo weather parameters to the digital twin simulation."""
        self.real_weather_data = dict(w)
        # Precipitation / Rain drives simulated runoff intensity
        precip = max(float(w.get("precipitation_mm", 0.0)), float(w.get("rain_mm", 0.0)))
        if precip > 0.05:
            # Scaled so that 5 mm/h = 1.0 (heavy rain runoff)
            self.rain_intensity = min(1.0, max(0.05, precip / 5.0))
            self.weather = WeatherState.RAIN_RUNOFF
        else:
            self.rain_intensity = 0.0
            self.weather = WeatherState.CLEAR

        if "cloud_cover_pct" in w:
            self.cloud_cover = min(1.0, max(0.0, float(w["cloud_cover_pct"]) / 100.0))

        if "wind_speed_m_s" in w:
            self.wind_speed_m_s = max(0.5, float(w["wind_speed_m_s"]))
            self.wave_height_m = max(0.05, min(1.2, 0.08 + 0.035 * self.wind_speed_m_s))

        if "shortwave_radiation_w_m2" in w and w["shortwave_radiation_w_m2"] is not None:
            self.real_solar_irradiance = float(w["shortwave_radiation_w_m2"])

    def trigger_rain_runoff(self, intensity: float = 0.85):
        """Trigger simulated storm rain runoff event."""
        self.weather = WeatherState.RAIN_RUNOFF
        self.rain_intensity = min(1.0, max(0.0, intensity))
        self.cloud_cover = 0.90
        self.wind_speed_m_s = 7.5

    def clear_weather(self):
        """Restore clear sunny weather conditions."""
        self.weather = WeatherState.CLEAR
        self.rain_intensity = 0.0
        self.cloud_cover = 0.15
        self.wind_speed_m_s = 2.5
        self.real_solar_irradiance = None

