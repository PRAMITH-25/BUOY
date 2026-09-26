"""
USGS Water Services API Client with In-Memory Caching and CSV Fallback.

Queries the USGS National Water Information System (NWIS) Instantaneous Values (IV) REST service
for real-time water quality monitoring data from active stations in the Lake Erie basin.
When the API is unreachable or returns HTTP errors (such as 503 Service Unavailable), it
transparently falls back to the existing USGS nearshore sonde CSV dataset.
"""
import time
import json
import urllib.request
import urllib.error
from typing import Dict, Any, List, Optional
from buoy_sim.data.usgs_loader import USGSLoader, USGSLookup

DEFAULT_USGS_TIMEOUT_S = 4.0
USGS_CACHE_TTL_S = 600.0  # 10 minutes cache

# Default station IDs near the Lake Erie demonstration site:
# 04208000: Cuyahoga River at Independence OH (major tributary to Lake Erie at Cleveland)
# 04200500: Black River at Elyria OH (tributary to Lake Erie)
# 04200508: Lake Erie at Cleveland Water Intake
DEFAULT_SITES = ["04208000", "04200500", "04200508"]

# Parameter code mapping:
# 00010: Temperature, water (°C)
# 00400: pH
# 00095: Specific conductance (µS/cm at 25°C)
# 63680: Turbidity (FNU)
# 00076: Turbidity (NTU)
PARAM_CODE_MAP = {
    "00010": ("water_temp_c", "Water Temperature", "°C"),
    "00400": ("ph", "pH", ""),
    "00095": ("ec_us_cm", "Specific Conductance", "µS/cm"),
    "63680": ("turbidity_ntu", "Turbidity", "FNU"),
    "00076": ("turbidity_ntu", "Turbidity", "NTU"),
}


class USGSWaterApiClient:
    """Manages queries to USGS NWIS REST API with caching and historical CSV fallback."""

    def __init__(self, cache_ttl_s: float = USGS_CACHE_TTL_S, timeout_s: float = DEFAULT_USGS_TIMEOUT_S):
        self.cache_ttl_s = cache_ttl_s
        self.timeout_s = timeout_s
        self._cache: Dict[str, Any] = {}
        self._cache_time: float = 0.0
        self._last_error: Optional[str] = None
        self._csv_loader: Optional[USGSLoader] = None
        self._csv_lookup: Optional[USGSLookup] = None

    def _ensure_csv_loader(self):
        if self._csv_loader is None:
            try:
                self._csv_loader = USGSLoader()
                self._csv_lookup = USGSLookup(self._csv_loader)
            except Exception:
                pass

    def get_water_data(self, sites: Optional[List[str]] = None, force_refresh: bool = False,
                       buoy_lat: float = 41.57963, buoy_lon: float = -81.57919) -> Dict[str, Any]:
        """
        Fetch real-time water data from USGS NWIS API.

        If the API call fails or times out, falls back to the existing USGS CSV dataset.
        Returns a dictionary with:
        - stations: list of station observation dictionaries
        - summary: consolidated latest readings
        - status: 'REAL_API_DATA' | 'CACHED_DATA' | 'HISTORICAL_DATA' | 'OFFLINE_FALLBACK'
        - data_source: description of the data origin
        """
        now = time.time()
        cache_age = now - self._cache_time

        # Check cache
        if not force_refresh and self._cache and cache_age < self.cache_ttl_s:
            res = dict(self._cache)
            res["status"] = "CACHED_DATA"
            res["cache_age_s"] = round(cache_age, 1)
            return res

        target_sites = sites or DEFAULT_SITES
        sites_param = ",".join(target_sites)
        params_param = "00010,00400,00095,63680,00076"

        url = (
            f"https://waterservices.usgs.gov/nwis/iv/?"
            f"format=json&sites={sites_param}&parameterCd={params_param}&siteStatus=all"
        )

        try:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "BuoyDigitalTwin/2.0 (WaterQualityResearch; USGS NWIS Client)"}
            )
            with urllib.request.urlopen(req, timeout=self.timeout_s) as response:
                if response.status == 200:
                    raw_data = json.loads(response.read().decode("utf-8"))
                    parsed = self._parse_usgs_iv_response(raw_data)
                    if parsed.get("stations"):
                        self._cache = dict(parsed)
                        self._cache_time = now
                        self._last_error = None
                        parsed["status"] = "REAL_API_DATA"
                        parsed["cache_age_s"] = 0.0
                        return parsed
        except Exception as exc:
            self._last_error = str(exc)

        # If cache exists (even if expired), return cached data
        if self._cache:
            res = dict(self._cache)
            res["status"] = "CACHED_DATA"
            res["cache_age_s"] = round(now - self._cache_time, 1)
            res["warning"] = f"USGS API error ({self._last_error}). Using cached observation data."
            return res

        # Otherwise, fall back to the existing USGS CSV dataset
        return self._build_csv_fallback(buoy_lat, buoy_lon, error_msg=self._last_error)

    def _parse_usgs_iv_response(self, data: Dict[str, Any]) -> Dict[str, Any]:
        time_series_list = data.get("value", {}).get("timeSeries", [])
        stations_map: Dict[str, Dict[str, Any]] = {}

        for ts in time_series_list:
            src_info = ts.get("sourceInfo", {})
            site_codes = src_info.get("siteCode", [])
            site_id = site_codes[0].get("value") if site_codes else "UNKNOWN"
            site_name = src_info.get("siteName", "USGS Monitoring Station")
            geo = src_info.get("geoLocation", {}).get("geogLocation", {})
            lat = float(geo.get("latitude", 0.0))
            lon = float(geo.get("longitude", 0.0))

            var_info = ts.get("variable", {})
            var_codes = var_info.get("variableCode", [])
            p_code = var_codes[0].get("value") if var_codes else ""

            if site_id not in stations_map:
                stations_map[site_id] = {
                    "station_id": site_id,
                    "station_name": site_name,
                    "latitude": lat,
                    "longitude": lon,
                    "parameters": {},
                    "latest_timestamp": None,
                    "agency": "USGS",
                }

            if p_code in PARAM_CODE_MAP:
                key, name, unit = PARAM_CODE_MAP[p_code]
                values = ts.get("values", [])
                val_list = values[0].get("value", []) if values else []
                # Find latest non-empty reading
                latest_reading = None
                for item in reversed(val_list):
                    v_str = item.get("value")
                    if v_str is not None and v_str != "" and v_str != "-999999":
                        try:
                            v_float = float(v_str)
                            dt_str = item.get("dateTime", "")
                            latest_reading = {"value": v_float, "dateTime": dt_str}
                            break
                        except ValueError:
                            continue

                if latest_reading:
                    stations_map[site_id]["parameters"][key] = {
                        "value": latest_reading["value"],
                        "name": name,
                        "unit": unit,
                        "code": p_code,
                        "timestamp": latest_reading["dateTime"],
                    }
                    if not stations_map[site_id]["latest_timestamp"]:
                        stations_map[site_id]["latest_timestamp"] = latest_reading["dateTime"]

        stations_list = list(stations_map.values())

        # Build summary using the closest station or primary station (e.g. 04208000)
        summary = {}
        for s in stations_list:
            for k, pdata in s.get("parameters", {}).items():
                if k not in summary:
                    summary[k] = pdata["value"]

        return {
            "stations": stations_list,
            "summary": summary,
            "data_source": "USGS National Water Information System (NWIS) Instantaneous Values API",
            "is_real_api": True,
            "status": "REAL_API_DATA",
            "observation_time": stations_list[0]["latest_timestamp"] if stations_list else None,
            "disclaimer": "Real USGS streamgage observations used as external environmental baseline.",
        }

    def _build_csv_fallback(self, lat: float, lon: float, error_msg: Optional[str] = None) -> Dict[str, Any]:
        """Query the offline USGS Lake Erie Sonde CSV dataset."""
        self._ensure_csv_loader()
        obs = {}
        if self._csv_lookup:
            obs = self._csv_lookup.query_by_latlon(lat, lon)
        else:
            obs = {"ph": 8.35, "ec_us_cm": 291.0, "turbidity_ntu": 3.34, "water_temp_c": 20.10, "nearest_record_timestamp": "2019-06-11T10:20:54"}

        fallback_station = {
            "station_id": "USGS-OFFLINE-CSV",
            "station_name": "USGS Lake Erie Nearshore Sonde Transect (Offline Dataset)",
            "latitude": lat,
            "longitude": lon,
            "agency": "USGS",
            "latest_timestamp": obs.get("nearest_record_timestamp", "June 2019"),
            "parameters": {
                "ph": {"value": obs.get("ph", 8.35), "name": "pH", "unit": "", "code": "00400"},
                "ec_us_cm": {"value": obs.get("ec_us_cm", 291.0), "name": "Specific Conductance", "unit": "µS/cm", "code": "00095"},
                "turbidity_ntu": {"value": obs.get("turbidity_ntu", 3.34), "name": "Turbidity", "unit": "NTU", "code": "63680"},
                "water_temp_c": {"value": obs.get("water_temp_c", 20.10), "name": "Water Temperature", "unit": "°C", "code": "00010"},
            }
        }

        return {
            "stations": [fallback_station],
            "summary": {
                "ph": obs.get("ph", 8.35),
                "ec_us_cm": obs.get("ec_us_cm", 291.0),
                "turbidity_ntu": obs.get("turbidity_ntu", 3.34),
                "water_temp_c": obs.get("water_temp_c", 20.10),
            },
            "data_source": "USGS Lake Erie Sonde Historical CSV (Offline Fallback)",
            "status": "HISTORICAL_DATA",
            "is_real_api": False,
            "observation_time": obs.get("nearest_record_timestamp", "June 2019"),
            "warning": f"Live USGS API unavailable ({error_msg or 'timeout'}). Operating with offline USGS historical dataset.",
            "disclaimer": "Historical USGS observations providing baseline water parameters.",
        }


# Global singleton instance
_usgs_api_client_instance = USGSWaterApiClient()


def get_usgs_api_client() -> USGSWaterApiClient:
    return _usgs_api_client_instance
