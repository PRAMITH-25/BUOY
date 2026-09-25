"""
Core configuration constants and parameters for the Solar-Powered Lake Water Quality Monitoring Buoy.
"""
BUOY_DEVICE_ID = 0x0101
GATEWAY_DEVICE_ID = 0x0001
LORA_SYNC_WORD = 0x34
LORA_DEFAULT_FREQ_MHZ = 868.1

# Lake location (Lake Geneva, WI / representative temperate freshwater lake)
DEFAULT_LATITUDE = 42.5872
DEFAULT_LONGITUDE = -88.4334
MOORING_RADIUS_METERS = 5.0

# Base Lake Ground Truth
BASE_LAKE_PARAMS = {
    "temperature_c": 21.5,
    "ph": 7.65,
    "ec_us_cm": 380.0,
    "tds_ppm": 190.0,
    "turbidity_ntu": 8.5,
}

# ADS1115 ADC Parameters
ADS1115_PGA_FSR_V = 4.096
ADS1115_RESOLUTION_BITS = 16
ADS1115_LSB_V = ADS1115_PGA_FSR_V / 32768.0  # 125 uV

# Sensor Calibration Models
PH_CALIBRATION = {
    "v_neutral": 2.500,
    "slope_v_per_ph": -0.180,
    "min_valid_ph": 4.0,
    "max_valid_ph": 10.0,
}

EC_CALIBRATION = {
    "v_zero": 0.05,
    "v_to_ec_factor": 650.0,
    "temp_coefficient": 0.019,
    "tds_factor": 0.50,
    "min_valid_ec": 10.0,
    "max_valid_ec": 2500.0,
}

# Optical Turbidity Nephelometric Response:
# V(NTU) = V_clean - (V_clean - V_min) * (NTU / (NTU + K_half))
TURBIDITY_CALIBRATION = {
    "v_clean": 4.15,
    "v_min": 2.00,
    "k_half": 120.0,
    "min_valid_ntu": 0.0,
    "max_valid_ntu": 3000.0,
}

TEMP_CALIBRATION = {
    "min_valid_temp": 0.0,
    "max_valid_temp": 45.0,
}

BATTERY_SPECS = {
    "nominal_capacity_mah": 4400.0,
    "nominal_voltage_v": 3.70,
    "max_voltage_v": 4.20,
    "min_cutoff_voltage_v": 3.10,
    "internal_resistance_ohm": 0.08,
    "charge_efficiency": 0.94,
    "self_discharge_pct_per_day": 0.05,
}

SOLAR_SPECS = {
    "peak_power_w": 10.0,
    "voc_v": 7.20,
    "vmp_v": 6.00,
    "imp_a": 1.67,
    "mppt_efficiency": 0.88,
    "temp_coeff_pct_c": -0.40,
}

POWER_CONSUMPTION_MA = {
    "esp32_active": 65.0,
    "esp32_modem_sleep": 22.0,
    "esp32_light_sleep": 1.5,
    "esp32_deep_sleep": 0.015,
    "ads1115_active": 0.25,
    "sensors_analog_active": 32.0,
    "gps_active": 45.0,
    "gps_standby": 0.020,
    "mpu6050_active": 3.8,
    "pump_active_5v": 280.0,
    "lora_tx": 120.0,
    "lora_rx": 15.0,
    "lora_sleep": 0.001,
}

CHAMBER_DEFAULT_TIMING = {
    "lake_monitoring_interval_s": 300,
    "fill_duration_s": 12,
    "stabilize_duration_s": 15,
    "measure_duration_s": 8,
    "flush_duration_s": 12,
}

LORA_DEFAULT_CONFIG = {
    "spreading_factor": 7,
    "bandwidth_khz": 125.0,
    "coding_rate": "4/5",
    "tx_power_dbm": 14.0,
    "distance_km": 2.2,
    "packet_loss_base_rate": 0.04,
    "ack_timeout_s": 1.5,
    "max_retries": 3,
}

DEFAULT_PSK_HEX = "4a7f9b2c8e1d3a5f608192a3b4c5d6e7f8091a2b3c4d5e6f7a8b9c0d1e2f3a4b"
WATCHDOG_TIMEOUT_S = 10.0
