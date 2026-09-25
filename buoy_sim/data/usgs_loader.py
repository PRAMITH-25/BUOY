"""
USGS Lake Erie Water Quality Dataset Loader and Spatial Lookup Engine.

Source dataset:
    USGS Lake Erie nearshore water-quality measurements
    File:  data/EC2019_QWsonde_surface_GIS_edited.csv
    Date:  June 2019
    CRS:   WGS-84

This module provides:
    1. USGSLoader  — loads the CSV, strips invalid (-999.9) rows, exposes
                     summary statistics and geographic bounds.
    2. USGSLookup  — deterministic K-nearest-neighbour (KNN) spatial lookup:
                     given a (lat, lon) query it returns the inverse-distance-
                     weighted average of the K nearest valid observations.

Coordinate-mapping contract (X/Y -> Lat/Lon):
    The virtual lake canvas uses a 1000 m x 600 m coordinate space.
    The USGS dataset spans:
        Lat: 41.565827 - 41.593431 N   (approx 3,062 m N-S extent)
        Lon: -81.599167 - -81.559214 W (approx 3,565 m E-W extent)

    Mapping is a linear normalisation:
        norm_x = x / MAP_WIDTH_METERS       -> 0.0 ... 1.0
        norm_y = y / MAP_HEIGHT_METERS      -> 0.0 ... 1.0

        lat = LAT_MIN + norm_y * (LAT_MAX - LAT_MIN)
        lon = LON_MIN + norm_x * (LON_MAX - LON_MIN)

    And the inverse:
        norm_x = (lon - LON_MIN) / (LON_MAX - LON_MIN)
        norm_y = (lat - LAT_MIN) / (LAT_MAX - LAT_MIN)

        x = norm_x * MAP_WIDTH_METERS
        y = norm_y * MAP_HEIGHT_METERS

    This mapping is documented and used exclusively in map_xy_to_usgs_latlon
    and usgs_latlon_to_map_xy (below).

Usage:
    from buoy_sim.data.usgs_loader import USGSLoader, USGSLookup

    loader = USGSLoader()                  # loads from default path
    lookup = USGSLookup(loader)

    result = lookup.query_by_latlon(41.58, -81.58)
    # -> {'ph': 8.37, 'ec_us_cm': 290.1, 'turbidity_ntu': 2.4,
    #     'water_temp_c': 23.1, 'latitude': 41.58, 'longitude': -81.58, ...}
"""

import os
import csv
import math
from typing import Dict, Any, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INVALID_SENTINEL = -999.9          # USGS flag for invalid / missing readings
DEFAULT_CSV_RELPATH = os.path.join(
    os.path.dirname(__file__),     # buoy_sim/data/
    "..", "..", "data",            # -> project_root/data/
    "EC2019_QWsonde_surface_GIS_edited.csv"
)

# Virtual lake map dimensions (mirrors spatial_field.py)
MAP_WIDTH_METERS = 1000.0
MAP_HEIGHT_METERS = 600.0

# Geographic bounds derived from the valid-row analysis (documented above)
LAT_MIN = 41.565827
LAT_MAX = 41.593431
LON_MIN = -81.599167
LON_MAX = -81.559214

# Default number of neighbours for KNN lookup (K=3 preserves local hydrological gradients)
DEFAULT_K = 3


# ---------------------------------------------------------------------------
# Coordinate mapping helpers
# ---------------------------------------------------------------------------

def map_xy_to_usgs_latlon(x: float, y: float) -> Tuple[float, float]:
    """
    Convert virtual lake map coordinates (metres) to USGS dataset lat/lon.

    The X axis maps linearly to longitude (West -> East).
    The Y axis maps linearly to latitude  (South -> North).

    Example:
        (0,    0  ) -> (LAT_MIN, LON_MIN)  -- SW corner
        (1000, 600) -> (LAT_MAX, LON_MAX)  -- NE corner
        (500,  300) -> midpoint of the dataset bounding box
    """
    norm_x = max(0.0, min(1.0, x / MAP_WIDTH_METERS))
    norm_y = max(0.0, min(1.0, y / MAP_HEIGHT_METERS))
    lat = LAT_MIN + norm_y * (LAT_MAX - LAT_MIN)
    lon = LON_MIN + norm_x * (LON_MAX - LON_MIN)
    return round(lat, 6), round(lon, 6)


def usgs_latlon_to_map_xy(lat: float, lon: float) -> Tuple[float, float]:
    """Inverse of map_xy_to_usgs_latlon -- returns (x, y) in map metres."""
    lat_range = LAT_MAX - LAT_MIN
    lon_range = LON_MAX - LON_MIN
    if lat_range == 0.0 or lon_range == 0.0:
        return 500.0, 300.0
    norm_y = max(0.0, min(1.0, (lat - LAT_MIN) / lat_range))
    norm_x = max(0.0, min(1.0, (lon - LON_MIN) / lon_range))
    x = norm_x * MAP_WIDTH_METERS
    y = norm_y * MAP_HEIGHT_METERS
    return round(x, 2), round(y, 2)


# ---------------------------------------------------------------------------
# USGSLoader
# ---------------------------------------------------------------------------

class USGSLoader:
    """
    Load and validate the USGS Lake Erie nearshore sonde dataset.

    Records where any of the four required parameters (pH, SpCond_uS_cm,
    Turbidity_NTU, Temp_C) or either coordinate equals INVALID_SENTINEL
    (-999.9) are excluded from valid_records.

    Attributes
    ----------
    raw_row_count       : int   -- rows in CSV (excluding header)
    valid_records       : list  -- list of dicts, one per valid observation
    invalid_row_count   : int   -- rows removed due to -999.9 values
    geo_bounds          : dict  -- lat/lon min/max of valid records
    param_ranges        : dict  -- min/max/mean for each parameter
    """

    def __init__(self, csv_path: Optional[str] = None):
        if csv_path is None:
            csv_path = os.path.normpath(DEFAULT_CSV_RELPATH)

        self.csv_path: str = csv_path
        self.raw_row_count: int = 0
        self.valid_records: List[Dict[str, Any]] = []
        self.invalid_row_count: int = 0
        self.geo_bounds: Dict[str, float] = {}
        self.param_ranges: Dict[str, Dict[str, float]] = {}

        self._load()

    # ------------------------------------------------------------------
    def _load(self) -> None:
        """Read CSV, apply validity filter, compute summary statistics."""
        all_rows: List[Dict[str, Any]] = []

        with open(self.csv_path, newline="", encoding="utf-8-sig") as fh:
            reader = csv.DictReader(fh)
            for row in reader:
                self.raw_row_count += 1
                parsed = self._parse_row(row)
                if parsed is not None:
                    all_rows.append(parsed)

        self.invalid_row_count = self.raw_row_count - len(all_rows)
        self.valid_records = all_rows
        self._compute_statistics()

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_row(row: Dict[str, str]) -> Optional[Dict[str, Any]]:
        """
        Parse one CSV row.  Returns None if any required field is missing,
        non-numeric, or equals INVALID_SENTINEL (-999.9).
        """
        try:
            lat  = float(row["Latitude_WGS84"])
            lon  = float(row["Longitude_WGS84"])
            temp = float(row["Temp_C"])
            ec   = float(row["SpCond_uS_cm"])
            ph   = float(row["pH"])
            turb = float(row["Turbidity_NTU"])
        except (KeyError, ValueError, TypeError):
            return None

        # Reject if any required parameter is the USGS invalid sentinel
        for val in (lat, lon, temp, ec, ph, turb):
            if val == INVALID_SENTINEL:
                return None

        # Build ISO-like timestamp string from individual columns
        try:
            year   = int(row.get("Year",  2019))
            month  = int(row.get("Month",    1))
            day    = int(row.get("Day",      1))
            hour   = int(row.get("Hour",     0))
            minute = int(row.get("Min",      0))
            sec    = int(row.get("Sec",      0))
            timestamp = "%04d-%02d-%02dT%02d:%02d:%02d" % (
                year, month, day, hour, minute, sec
            )
        except (ValueError, TypeError):
            timestamp = "2019-01-01T00:00:00"

        return {
            "latitude":       lat,
            "longitude":      lon,
            "water_temp_c":   temp,
            "ec_us_cm":       ec,      # SpCond_uS_cm -> EC
            "ph":             ph,
            "turbidity_ntu":  turb,    # Turbidity_NTU -> turbidity
            "timestamp":      timestamp,
        }

    # ------------------------------------------------------------------
    def _compute_statistics(self) -> None:
        """Compute geographic bounds and parameter ranges over valid rows."""
        if not self.valid_records:
            self.geo_bounds = {}
            self.param_ranges = {}
            return

        lats = [r["latitude"]  for r in self.valid_records]
        lons = [r["longitude"] for r in self.valid_records]
        self.geo_bounds = {
            "lat_min": min(lats),
            "lat_max": max(lats),
            "lon_min": min(lons),
            "lon_max": max(lons),
        }

        for param in ("ph", "ec_us_cm", "turbidity_ntu", "water_temp_c"):
            vals = [r[param] for r in self.valid_records]
            self.param_ranges[param] = {
                "min":  min(vals),
                "max":  max(vals),
                "mean": sum(vals) / len(vals),
            }

    # ------------------------------------------------------------------
    def get_percentile(self, param: str, value: float) -> float:
        """Compute the percentile of value within valid historical observations."""
        if not self.valid_records:
            return 50.0
        if not hasattr(self, "_sorted_cache"):
            self._sorted_cache = {}
            for p in ("ph", "ec_us_cm", "turbidity_ntu", "water_temp_c"):
                self._sorted_cache[p] = sorted(r[p] for r in self.valid_records if p in r)
        arr = self._sorted_cache.get(param, [])
        if not arr:
            return 50.0
        import bisect
        idx = bisect.bisect_left(arr, value)
        pct = (idx / len(arr)) * 100.0
        return round(min(100.0, max(0.0, pct)), 1)

    def get_replay_record(self, index: int) -> Dict[str, Any]:
        """Return historical record at index for data replay with percentiles."""
        if not self.valid_records:
            return {}
        idx = max(0, min(index, len(self.valid_records) - 1))
        rec = dict(self.valid_records[idx])
        rec["index"] = idx
        rec["total_records"] = len(self.valid_records)
        rec["percentiles"] = {
            "ph": self.get_percentile("ph", rec["ph"]),
            "ec_us_cm": self.get_percentile("ec_us_cm", rec["ec_us_cm"]),
            "turbidity_ntu": self.get_percentile("turbidity_ntu", rec["turbidity_ntu"]),
            "water_temp_c": self.get_percentile("water_temp_c", rec["water_temp_c"]),
        }
        return rec

    def get_chronological_timeseries(self, param: str = "turbidity_ntu", start_idx: int = 0, count: int = 50) -> List[Dict[str, Any]]:
        """Return a chronological sequence of actual historical observations."""
        if not self.valid_records:
            return []
        start = max(0, min(start_idx, max(0, len(self.valid_records) - count)))
        end = min(start + count, len(self.valid_records))
        out = []
        for i in range(start, end):
            r = self.valid_records[i]
            out.append({
                "index": i,
                "timestamp": r.get("timestamp", ""),
                "value": r.get(param, 0.0),
                "ph": r.get("ph", 0.0),
                "ec_us_cm": r.get("ec_us_cm", 0.0),
                "turbidity_ntu": r.get("turbidity_ntu", 0.0),
                "water_temp_c": r.get("water_temp_c", 0.0),
                "latitude": r.get("latitude", 0.0),
                "longitude": r.get("longitude", 0.0),
            })
        return out

    # ------------------------------------------------------------------
    def get_info(self) -> Dict[str, Any]:
        """Return a summary dict suitable for dashboard display."""
        return {
            "source":              "USGS",
            "dataset":             "Lake Erie nearshore water-quality measurements (June 2019)",
            "csv_path":            self.csv_path,
            "total_rows":          self.raw_row_count,
            "invalid_rows":        self.invalid_row_count,
            "valid_rows":          len(self.valid_records),
            "geo_bounds":          self.geo_bounds,
            "param_ranges":        self.param_ranges,
            "data_source_label":   "USGS HISTORICAL DATA",
        }


# ---------------------------------------------------------------------------
# USGSLookup  --  deterministic K-nearest-neighbour spatial lookup
# ---------------------------------------------------------------------------

class USGSLookup:
    """
    Deterministic spatial lookup into the USGS Lake Erie dataset.

    Method: K-Nearest Neighbours with Inverse-Distance Weighting (IDW).
    - Distances are computed in degrees (Euclidean approximation; acceptable
      because the dataset spans only ~3 km, so degree-to-metre scaling is
      nearly constant).
    - For a query point closer than 1e-9 degrees to a record the record's
      values are returned directly (exact match).
    - The result is fully deterministic: identical (lat, lon) inputs always
      produce identical outputs.

    Parameters
    ----------
    loader : USGSLoader
    k      : int -- number of neighbours (default 3)
    """

    def __init__(self, loader: USGSLoader, k: int = DEFAULT_K):
        self.loader = loader
        self.k = max(1, k)
        self._records = loader.valid_records   # list of dicts (already filtered)

        # Pre-extract coordinate arrays for fast iteration
        self._lats = [r["latitude"]  for r in self._records]
        self._lons = [r["longitude"] for r in self._records]

        # Acceleration tree (scipy.spatial.cKDTree)
        self._kdtree = None
        self._grid_cache: Dict[Tuple[str, int, int], Dict[str, Any]] = {}
        try:
            from scipy.spatial import cKDTree
            import numpy as np
            if self._records:
                coords = np.column_stack((self._lats, self._lons))
                self._kdtree = cKDTree(coords)
        except Exception:
            self._kdtree = None

    # ------------------------------------------------------------------
    def query_by_latlon(self, lat: float, lon: float) -> Dict[str, Any]:
        """
        Return IDW-averaged water quality for the given (lat, lon).

        Returns
        -------
        dict with keys:
            ph, ec_us_cm, turbidity_ntu, water_temp_c,
            latitude, longitude,
            nearest_record_timestamp,
            data_source_label, k_used, lookup_method
        """
        if not self._records:
            return self._fallback(lat, lon)

        k_actual = min(self.k, len(self._records))

        # Fast path: use cKDTree if initialized
        if self._kdtree is not None:
            import numpy as np
            dists, indices = self._kdtree.query([lat, lon], k=k_actual)
            if isinstance(indices, (int, np.integer)):
                indices = [int(indices)]
                dists = [float(dists)]
            else:
                indices = [int(idx) for idx in indices]
                dists = [float(d) for d in dists]

            if dists[0] < 1e-9:
                rec = self._records[indices[0]]
                single_contrib = [{
                    "point_num": 1,
                    "index": int(indices[0]),
                    "latitude": round(rec["latitude"], 6),
                    "longitude": round(rec["longitude"], 6),
                    "ph": round(rec["ph"], 2),
                    "ec_us_cm": round(rec["ec_us_cm"], 1),
                    "turbidity_ntu": round(rec["turbidity_ntu"], 2),
                    "water_temp_c": round(rec["water_temp_c"], 2),
                    "timestamp": rec.get("timestamp", "2019-06-10"),
                    "distance_m": 0.0,
                    "weight_pct": 100.0,
                }]
                return self._build_result(
                    rec["ph"], rec["ec_us_cm"], rec["turbidity_ntu"], rec["water_temp_c"],
                    lat, lon, rec.get("timestamp", "2019-06-10"), k_actual, single_contrib
                )

            weights = [1.0 / max(d * d, 1e-30) for d in dists]
            total_w = sum(weights)
            norm_w = [w / total_w for w in weights]

            ph_avg = sum(norm_w[i] * self._records[indices[i]]["ph"] for i in range(k_actual))
            ec_avg = sum(norm_w[i] * self._records[indices[i]]["ec_us_cm"] for i in range(k_actual))
            turb_avg = sum(norm_w[i] * self._records[indices[i]]["turbidity_ntu"] for i in range(k_actual))
            temp_avg = sum(norm_w[i] * self._records[indices[i]]["water_temp_c"] for i in range(k_actual))

            contributors = []
            for i in range(k_actual):
                idx = indices[i]
                r = self._records[idx]
                d_lat = (lat - r["latitude"]) * 111132.95
                d_lon = (lon - r["longitude"]) * 111412.84 * math.cos(math.radians(lat))
                d_m = round(math.sqrt(d_lat**2 + d_lon**2), 1)
                contributors.append({
                    "point_num": i + 1,
                    "index": int(idx),
                    "latitude": round(r["latitude"], 6),
                    "longitude": round(r["longitude"], 6),
                    "ph": round(r["ph"], 2),
                    "ec_us_cm": round(r["ec_us_cm"], 1),
                    "turbidity_ntu": round(r["turbidity_ntu"], 2),
                    "water_temp_c": round(r["water_temp_c"], 2),
                    "timestamp": r.get("timestamp", "2019-06-10"),
                    "distance_m": d_m,
                    "weight_pct": round(norm_w[i] * 100.0, 1),
                })

            nearest_ts = self._records[indices[0]].get("timestamp", "2019-06-10")
            return self._build_result(ph_avg, ec_avg, turb_avg, temp_avg,
                                      lat, lon, nearest_ts, k_actual, contributors)

        # Fallback pure-Python path
        dists_sq = [
            (lat - rlat) ** 2 + (lon - rlon) ** 2
            for rlat, rlon in zip(self._lats, self._lons)
        ]
        indexed = sorted(enumerate(dists_sq), key=lambda t: t[1])[:k_actual]

        if indexed[0][1] < 1e-18:
            rec = self._records[indexed[0][0]]
            single_contrib = [{
                "point_num": 1,
                "index": int(indexed[0][0]),
                "latitude": round(rec["latitude"], 6),
                "longitude": round(rec["longitude"], 6),
                "ph": round(rec["ph"], 2),
                "ec_us_cm": round(rec["ec_us_cm"], 1),
                "turbidity_ntu": round(rec["turbidity_ntu"], 2),
                "water_temp_c": round(rec["water_temp_c"], 2),
                "timestamp": rec.get("timestamp", "2019-06-10"),
                "distance_m": 0.0,
                "weight_pct": 100.0,
            }]
            return self._build_result(
                rec["ph"], rec["ec_us_cm"], rec["turbidity_ntu"], rec["water_temp_c"],
                lat, lon, rec.get("timestamp", "2019-06-10"), k_actual, single_contrib
            )

        weights = [1.0 / max(d_sq, 1e-30) for _, d_sq in indexed]
        total_w = sum(weights)
        norm_w  = [w / total_w for w in weights]

        ph_avg   = sum(norm_w[i] * self._records[indexed[i][0]]["ph"] for i in range(k_actual))
        ec_avg   = sum(norm_w[i] * self._records[indexed[i][0]]["ec_us_cm"] for i in range(k_actual))
        turb_avg = sum(norm_w[i] * self._records[indexed[i][0]]["turbidity_ntu"] for i in range(k_actual))
        temp_avg = sum(norm_w[i] * self._records[indexed[i][0]]["water_temp_c"] for i in range(k_actual))

        contributors = []
        for i in range(k_actual):
            idx = indexed[i][0]
            r = self._records[idx]
            d_lat = (lat - r["latitude"]) * 111132.95
            d_lon = (lon - r["longitude"]) * 111412.84 * math.cos(math.radians(lat))
            d_m = round(math.sqrt(d_lat**2 + d_lon**2), 1)
            contributors.append({
                "point_num": i + 1,
                "index": int(idx),
                "latitude": round(r["latitude"], 6),
                "longitude": round(r["longitude"], 6),
                "ph": round(r["ph"], 2),
                "ec_us_cm": round(r["ec_us_cm"], 1),
                "turbidity_ntu": round(r["turbidity_ntu"], 2),
                "water_temp_c": round(r["water_temp_c"], 2),
                "timestamp": r.get("timestamp", "2019-06-10"),
                "distance_m": d_m,
                "weight_pct": round(norm_w[i] * 100.0, 1),
            })

        nearest_ts = self._records[indexed[0][0]].get("timestamp", "2019-06-10")
        return self._build_result(ph_avg, ec_avg, turb_avg, temp_avg,
                                  lat, lon, nearest_ts, k_actual, contributors)

    # ------------------------------------------------------------------
    def query_by_map_xy(self, x: float, y: float) -> Dict[str, Any]:
        """
        Convenience wrapper: convert virtual (x, y) -> USGS lat/lon, then look up.
        The coordinate mapping is documented in map_xy_to_usgs_latlon.
        """
        lat, lon = map_xy_to_usgs_latlon(x, y)
        result = self.query_by_latlon(lat, lon)
        result["map_x"] = x
        result["map_y"] = y
        return result

    # ------------------------------------------------------------------
    def generate_spatial_grid(
        self, param: str = "turbidity_ntu", cols: int = 50, rows: int = 30
    ) -> Dict[str, Any]:
        """
        Generate a 2D scalar field grid of real USGS observation-derived values
        across the virtual 1000m x 600m lake canvas.
        Results are cached in memory for zero-latency retrieval.
        """
        param_norm = param.lower().strip()
        alias_map = {
            "ph": "ph",
            "turbidity": "turbidity_ntu",
            "turbidity_ntu": "turbidity_ntu",
            "turb": "turbidity_ntu",
            "ec": "ec_us_cm",
            "spcond": "ec_us_cm",
            "spcond_us_cm": "ec_us_cm",
            "ec_us_cm": "ec_us_cm",
            "temp": "water_temp_c",
            "temperature": "water_temp_c",
            "temp_c": "water_temp_c",
            "water_temp_c": "water_temp_c",
        }
        actual_key = alias_map.get(param_norm, "turbidity_ntu")
        cache_key = (actual_key, cols, rows)
        if cache_key in self._grid_cache:
            return self._grid_cache[cache_key]

        meta = {
            "ph": {"label": "Water pH", "unit": ""},
            "turbidity_ntu": {"label": "Turbidity", "unit": "NTU"},
            "ec_us_cm": {"label": "Electrical Conductivity (EC)", "unit": "µS/cm"},
            "water_temp_c": {"label": "Water Temperature", "unit": "°C"},
        }.get(actual_key, {"label": actual_key, "unit": ""})

        dx = MAP_WIDTH_METERS / max(1, cols - 1)
        dy = MAP_HEIGHT_METERS / max(1, rows - 1)

        grid: List[List[float]] = []
        all_vals: List[float] = []

        for r in range(rows):
            row_y = r * dy
            row_vals: List[float] = []
            for c in range(cols):
                col_x = c * dx
                res = self.query_by_map_xy(col_x, row_y)
                val = float(res[actual_key])
                row_vals.append(val)
                all_vals.append(val)
            grid.append(row_vals)

        result = {
            "parameter": actual_key,
            "label": meta["label"],
            "unit": meta["unit"],
            "cols": cols,
            "rows": rows,
            "min_val": round(min(all_vals), 2),
            "max_val": round(max(all_vals), 2),
            "mean_val": round(sum(all_vals) / len(all_vals), 2),
            "cell_width_m": round(dx, 2),
            "cell_height_m": round(dy, 2),
            "grid": grid,
            "data_source_label": "USGS HISTORICAL DATA — ENVIRONMENTAL BASELINE",
        }
        self._grid_cache[cache_key] = result
        return result

    # ------------------------------------------------------------------
    @staticmethod
    def _build_result(ph, ec, turb, temp, lat, lon, ts, k, contributors=None) -> Dict[str, Any]:
        return {
            "ph":                       round(ph,   4),
            "ec_us_cm":                 round(ec,   2),
            "turbidity_ntu":            round(turb, 4),
            "water_temp_c":             round(temp, 4),
            "latitude":                 round(lat,  6),
            "longitude":                round(lon,  6),
            "nearest_record_timestamp": ts,
            "data_source_label":        "USGS HISTORICAL DATA",
            "lookup_method":            "KNN-IDW (K=%d)" % k,
            "k_used":                   k,
            "contributors":             contributors or [],
        }

    # ------------------------------------------------------------------
    @staticmethod
    def _fallback(lat: float, lon: float) -> Dict[str, Any]:
        """Returned only if the dataset is empty (should never happen)."""
        return {
            "ph":                       8.37,
            "ec_us_cm":                 292.6,
            "turbidity_ntu":            3.16,
            "water_temp_c":             22.98,
            "latitude":                 lat,
            "longitude":                lon,
            "nearest_record_timestamp": "N/A",
            "data_source_label":        "USGS HISTORICAL DATA (fallback)",
            "lookup_method":            "FALLBACK",
            "k_used":                   0,
        }
