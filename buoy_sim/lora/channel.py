"""
LoRa Physical RF Channel Model.
Accurately models:
- Free-space & Log-Distance Path Loss over open water
- RSSI (Received Signal Strength Indicator) in dBm
- SNR (Signal-to-Noise Ratio) in dB
- LoRa Airtime calculation based on SF, BW, CR, and payload length
- Packet loss probability function
"""
import math
from typing import Dict, Any, Tuple
from buoy_sim.core.config import LORA_DEFAULT_CONFIG
from buoy_sim.core.seed import global_rng

class LoRaChannelModel:
    def __init__(self, config: Dict[str, Any] = LORA_DEFAULT_CONFIG):
        self.config = dict(config)
        self.fault_forced_packet_loss = False

    def calculate_airtime_ms(self, payload_bytes: int) -> float:
        """
        Calculate precise LoRa packet airtime in milliseconds according to Semtech SX126x/SX127x specs.
        """
        sf = self.config["spreading_factor"]
        bw_hz = self.config["bandwidth_khz"] * 1000.0
        cr_map = {"4/5": 1, "4/6": 2, "4/7": 3, "4/8": 4}
        cr = cr_map.get(self.config.get("coding_rate", "4/5"), 1)

        t_sym_ms = (2**sf / bw_hz) * 1000.0
        # Preamble duration: (N_preamble + 4.25) * T_sym
        n_preamble = 8
        t_preamble_ms = (n_preamble + 4.25) * t_sym_ms

        # Payload symbols
        de = 1 if (sf >= 11 and bw_hz <= 125000) else 0  # Low data rate optimize
        h = 0  # explicit header
        num = 8 * payload_bytes - 4 * sf + 28 + 16 - 20 * h
        denom = 4 * (sf - 2 * de)
        payload_sym_nb = 8 + max(math.ceil(num / denom) * (cr + 4), 0)
        t_payload_ms = payload_sym_nb * t_sym_ms

        return t_preamble_ms + t_payload_ms

    def simulate_transmission(self, payload_bytes: int) -> Dict[str, Any]:
        """
        Simulate RF propagation over water, computing RSSI, SNR, latency, and packet loss.
        """
        rng = global_rng.np
        dist_km = self.config["distance_km"]
        tx_power = self.config["tx_power_dbm"]

        # Path loss over open freshwater lake: n ~ 2.4, log-distance model
        # PL(d) = 20*log10(4*pi*d0/lambda) + 10*n*log10(d/d0)
        freq_mhz = 868.1
        wavelength = 3e8 / (freq_mhz * 1e6)
        pl_d0 = 20.0 * math.log10(4.0 * math.pi * 100.0 / wavelength)  # at 100m
        path_loss_db = pl_d0 + 10.0 * 2.4 * math.log10(max(100.0, dist_km * 1000.0) / 100.0)
        # Shadow fading over water (Gaussian ~2.0 dB)
        fading = float(rng.normal(0.0, 1.8))
        total_path_loss = path_loss_db + fading

        # Received RSSI (dBm)
        antenna_gain_tx = 2.15  # dBi dipole
        antenna_gain_rx = 5.0   # dBi shore colinear
        rssi_dbm = tx_power + antenna_gain_tx + antenna_gain_rx - total_path_loss
        rssi_dbm = max(-135.0, min(-50.0, rssi_dbm))

        # Thermal noise floor at 125kHz BW: -174 + 10*log10(125000) + NF(6dB) ~ -117 dBm
        noise_floor_dbm = -117.0 + float(rng.normal(0.0, 1.0))
        snr_db = rssi_dbm - noise_floor_dbm
        snr_db = max(-20.0, min(15.0, snr_db))

        # Airtime
        airtime_ms = self.calculate_airtime_ms(payload_bytes)
        # Propagation delay (light speed) + gateway processing delay (~15ms)
        propagation_delay_ms = (dist_km * 1000.0 / 3e5) + 15.0
        round_trip_latency_ms = (2.0 * airtime_ms) + propagation_delay_ms + float(rng.uniform(5.0, 15.0))

        # Packet Loss Probability
        # Base loss + SNR penalty when SNR approaches LoRa demodulation threshold (-7.5 dB for SF7)
        threshold_snr = -7.5
        snr_margin = snr_db - threshold_snr
        loss_prob = self.config["packet_loss_base_rate"]
        if snr_margin < 3.0:
            loss_prob += (3.0 - snr_margin) * 0.12
        loss_prob = min(0.95, max(0.01, loss_prob))

        if self.fault_forced_packet_loss:
            is_lost = True
        else:
            is_lost = bool(rng.uniform(0.0, 1.0) < loss_prob)

        return {
            "packet_lost": is_lost,
            "rssi_dbm": round(rssi_dbm, 1),
            "snr_db": round(snr_db, 1),
            "airtime_ms": round(airtime_ms, 1),
            "round_trip_latency_ms": round(round_trip_latency_ms, 1),
            "distance_km": dist_km,
            "loss_probability": round(loss_prob, 3),
        }
