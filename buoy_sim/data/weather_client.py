"""
Open-Meteo Weather API Client with In-Memory Caching and Offline Fallback.

Fetches current weather conditions (temperature, precipitation, wind, cloud cover, solar radiation)
for the buoy's geographic coordinates. Used as real environmental inputs to drive the digital twin
(e.g., rainfall driving runoff events, solar irradiance driving solar panel model, wind driving waves).
"""
import time
import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

DEFAULT_TIMEOUT_SECONDS = 5.0
CACHE_TTL_SECONDS = 600.0  # 10 minutes cache


class WeatherClient:
    """Fetches real weather data from Open-Meteo with caching and graceful offline fallback."""

    def __init__(self, cache_ttl_s: float = CACHE_TTL_SECONDS, timeout_s: float = DEFAULT_TIMEOUT_SECONDS):
        self.cache_ttl_s = cache_ttl_s
        self.timeout_s = timeout_s
        self._cache: Dict[str, Any] = {}
        self._cache_time: float = 0.0
        self._last_error: Optional[str] = None

    def get_weather(self, latitude: float, longitude: float, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Retrieve current weather for the specified coordinates.

        Returns a dictionary containing:
        - air_temperature_c
        - relative_humidity_pct
        - precipitation_mm
        - rain_mm
        - wind_speed_m_s
        - wind_direction_deg
        - cloud_cover_pct
        - shortwave_radiation_w_m2
        - observation_time
        - status: 'REAL_API_DATA' | 'CACHED_DATA' | 'OFFLINE_FALLBACK'
        - source: description of the data source
        """
        now = time.time()
        cache_age = now - self._cache_time

        # Check if fresh cached data is available for approximately same location (within ~1 km)
        if not force_refresh and self._cache and cache_age < self.cache_ttl_s:
            cached_lat = self._cache.get("latitude", 0.0)
            cached_lon = self._cache.get("longitude", 0.0)
            if abs(cached_lat - latitude) < 0.01 and abs(cached_lon - longitude) < 0.01:
                res = dict(self._cache)
                res["status"] = "CACHED_DATA"
                res["cache_age_s"] = round(cache_age, 1)
                return res

        # Attempt to fetch live from Open-Meteo API
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={latitude:.5f}&longitude={longitude:.5f}&"
            f"current=temperature_2m,relative_humidity_2m,precipitation,rain,"
            f"wind_speed_10m,wind_direction_10m,cloud_cover,shortwave_radiation"
        )

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BuoyDigitalTwin/2.0 (WaterQualityResearch; Open-Meteo Client)"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                if response.status == 200:
                    raw_data = json.loads(response.read().decode("utf-8"))
                    parsed = self._parse_open_meteo_response(raw_data, latitude, longitude)
                    self._cache = dict(parsed)
                    self._cache_time = now
                    self._last_error = None
                    parsed["status"] = "REAL_API_DATA"
                    parsed["cache_age_s"] = 0.0
                    return parsed
        except Exception as exc:
            self._last_error = str(exc)

        # If cache exists (even if stale), return it with CACHED_DATA status
        if self._cache:
            res = dict(self._cache)
            res["status"] = "CACHED_DATA"
            res["cache_age_s"] = round(now - self._cache_time, 1)
            res["warning"] = f"Live API unavailable ({self._last_error}). Using cached data."
            return res

        # Otherwise, return offline fallback estimates
        return self._build_fallback(latitude, longitude, error_msg=self._last_error)

    def _parse_open_meteo_response(self, data: Dict[str, Any], lat: float, lon: float) -> Dict[str, Any]:
        curr = data.get("current", {})
        # Convert wind speed km/h to m/s if units specify km/h
        units = data.get("current_units", {})
        raw_wind = float(curr.get("wind_speed_10m", 3.0))
        wind_unit = units.get("wind_speed_10m", "km/h")
        wind_speed_m_s = round(raw_wind / 3.6, 2) if "km" in wind_unit else round(raw_wind, 2)

        return {
            "latitude": lat,
            "longitude": lon,
            "air_temperature_c": float(curr.get("temperature_2m", 18.0)),
            "relative_humidity_pct": float(curr.get("relative_humidity_2m", 65.0)),
            "precipitation_mm": float(curr.get("precipitation", 0.0)),
            "rain_mm": float(curr.get("rain", 0.0)),
            "wind_speed_m_s": wind_speed_m_s,
            "wind_direction_deg": float(curr.get("wind_direction_10m", 0.0)),
            "cloud_cover_pct": float(curr.get("cloud_cover", 20.0)),
            "shortwave_radiation_w_m2": float(curr.get("shortwave_radiation", 0.0)),
            "observation_time": curr.get("time", time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())),
            "source": "Open-Meteo Weather Forecast API",
            "is_real_api": True,
            "disclaimer": "Atmospheric input driving the digital twin simulation.",
        }

    def _build_fallback(self, lat: float, lon: float, error_msg: Optional[str] = None) -> Dict[str, Any]:
        """Synthetic seasonal/diurnal baseline used when external weather API is unreachable."""
        return {
            "latitude": lat,
            "longitude": lon,
            "air_temperature_c": 19.5,
            "relative_humidity_pct": 68.0,
            "precipitation_mm": 0.0,
            "rain_mm": 0.0,
            "wind_speed_m_s": 2.8,
            "wind_direction_deg": 45.0,
            "cloud_cover_pct": 25.0,
            "shortwave_radiation_w_m2": 450.0,
            "observation_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source": "OFFLINE FALLBACK MODEL",
            "status": "OFFLINE_FALLBACK",
            "is_real_api": False,
            "cache_age_s": None,
            "warning": f"Weather API unreachable ({error_msg}). Operating with offline baseline.",
            "disclaimer": "Estimated atmospheric baseline for simulation.",
        }


# Global singleton instance for the app
_weather_client_instance = WeatherClient()


def get_weather_client() -> WeatherClient:
    return _weather_client_instance
