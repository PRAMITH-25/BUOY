"""
NEO-6M GPS & MPU6050 6-DOF IMU Emulators.
Provides realistic buoy positioning, drift within mooring radius, NMEA sentences,
and wave-induced tilt/acceleration metrics.
"""
import math
from typing import Dict, Any
from buoy_sim.core.config import (
    DEFAULT_LATITUDE, DEFAULT_LONGITUDE, MOORING_RADIUS_METERS
)
from buoy_sim.core.seed import global_rng

class NEO6MGps:
    def __init__(self, lat: float = DEFAULT_LATITUDE, lon: float = DEFAULT_LONGITUDE):
        self.anchor_lat = lat
        self.anchor_lon = lon
        self.current_lat = lat
        self.current_lon = lon
        self.satellites = 8
        self.hdop = 1.2
        self.fix_type = "3D Fix"
        self.speed_knots = 0.05
        self.course_deg = 45.0
        self.fault_lock_lost = False

    @property
    def latitude(self) -> float:
        return self.current_lat

    @property
    def longitude(self) -> float:
        return self.current_lon

    def set_anchor(self, lat: float, lon: float):
        """Set the anchor coordinates corresponding to buoy map position."""
        self.anchor_lat = float(lat)
        self.anchor_lon = float(lon)
        self.current_lat = float(lat)
        self.current_lon = float(lon)

    def update(self, sim_time_s: float, wave_agitation: float = 1.0) -> Dict[str, Any]:
        """
        Update GPS location within mooring anchor radius.
        """
        rng = global_rng.np

        if self.fault_lock_lost:
            return {
                "fix_quality": 0,
                "fix_type": "No Fix",
                "satellites": 2,
                "hdop": 99.9,
                "latitude": 0.0,
                "longitude": 0.0,
                "speed_knots": 0.0,
                "nmea_rmc": "$GPRMC,,V,,,,,,,,,,N*53",
            }

        drift_angle = (sim_time_s * 0.05) % (2 * math.pi)
        drift_dist_m = (MOORING_RADIUS_METERS * 0.65) * (1.0 + 0.3 * math.sin(sim_time_s * 0.01))
        jitter_x = float(rng.normal(0.0, 0.8))
        jitter_y = float(rng.normal(0.0, 0.8))

        dx_meters = drift_dist_m * math.cos(drift_angle) + jitter_x
        dy_meters = drift_dist_m * math.sin(drift_angle) + jitter_y

        meters_per_deg_lat = 111132.95
        meters_per_deg_lon = 111412.84 * math.cos(math.radians(self.anchor_lat))

        self.current_lat = self.anchor_lat + (dy_meters / meters_per_deg_lat)
        self.current_lon = self.anchor_lon + (dx_meters / meters_per_deg_lon)

        self.satellites = int(max(5, min(12, 8 + rng.integers(-1, 2))))
        self.hdop = round(float(1.1 + rng.uniform(0.0, 0.4)), 2)
        self.speed_knots = round(float(abs(rng.normal(0.04, 0.02))), 2)
        self.course_deg = round(float((math.degrees(drift_angle) + 360) % 360), 1)

        nmea_rmc = (
            f"$GPRMC,120000.00,A,{abs(self.current_lat)*100:09.4f},N,"
            f"{abs(self.current_lon)*100:010.4f},W,{self.speed_knots:05.1f},"
            f"{self.course_deg:05.1f},240926,,,A*7A"
        )

        return {
            "fix_quality": 1,
            "fix_type": self.fix_type,
            "satellites": self.satellites,
            "hdop": self.hdop,
            "latitude": self.current_lat,
            "longitude": self.current_lon,
            "speed_knots": self.speed_knots,
            "course_deg": self.course_deg,
            "drift_distance_m": math.sqrt(dx_meters**2 + dy_meters**2),
            "nmea_rmc": nmea_rmc,
        }

class MPU6050Imu:
    def __init__(self):
        self.pitch_deg = 0.0
        self.roll_deg = 0.0
        self.accel_z_g = 1.0

    def update(self, sim_time_s: float, wave_height_m: float = 0.12, wave_period_s: float = 2.6) -> Dict[str, Any]:
        """
        Emulate 6-DOF IMU response to lake surface wave action.
        """
        rng = global_rng.np
        omega = 2.0 * math.pi / max(0.5, wave_period_s)

        max_tilt_deg = math.degrees(math.atan2(wave_height_m * 2.0, 3.5))
        pitch = max_tilt_deg * math.sin(omega * sim_time_s) + float(rng.normal(0.0, 0.3))
        roll = max_tilt_deg * 0.7 * math.cos(omega * sim_time_s + 0.6) + float(rng.normal(0.0, 0.3))

        heave_accel = 0.15 * (wave_height_m / 0.12) * math.sin(omega * sim_time_s)
        accel_x = math.sin(math.radians(pitch)) + float(rng.normal(0.0, 0.02))
        accel_y = math.sin(math.radians(roll)) + float(rng.normal(0.0, 0.02))
        accel_z = 1.0 + heave_accel + float(rng.normal(0.0, 0.02))

        gyro_x = max_tilt_deg * omega * math.cos(omega * sim_time_s) + float(rng.normal(0.0, 0.5))
        gyro_y = -max_tilt_deg * 0.7 * omega * math.sin(omega * sim_time_s + 0.6) + float(rng.normal(0.0, 0.5))
        gyro_z = float(rng.normal(0.0, 0.2))

        self.pitch_deg = pitch
        self.roll_deg = roll
        self.accel_z_g = accel_z

        return {
            "pitch_deg": round(pitch, 2),
            "roll_deg": round(roll, 2),
            "accel_x_g": round(accel_x, 3),
            "accel_y_g": round(accel_y, 3),
            "accel_z_g": round(accel_z, 3),
            "gyro_x_dps": round(gyro_x, 2),
            "gyro_y_dps": round(gyro_y, 2),
            "gyro_z_dps": round(gyro_z, 2),
        }
