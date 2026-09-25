"""
ADS1115 16-Bit I2C ADC Emulator.
Accurately models:
- 16-bit Delta-Sigma quantization (-32768 to 32767)
- Programmable Gain Amplifier (PGA: +/-4.096V, +/-2.048V, etc.)
- LSB resolution (125 uV for +/-4.096V range)
- Conversion noise and quantization error
- I2C communication fault injection
"""
import math
from typing import Dict, Any, Tuple
from buoy_sim.core.config import (
    ADS1115_PGA_FSR_V, ADS1115_RESOLUTION_BITS, ADS1115_LSB_V
)
from buoy_sim.core.seed import global_rng

class ADS1115Emulator:
    def __init__(self, pga_fsr_v: float = ADS1115_PGA_FSR_V):
        self.pga_fsr_v = pga_fsr_v
        self.lsb_v = pga_fsr_v / 32768.0  # 125 uV
        self.i2c_address = 0x48
        self.fault_i2c_bus_hang = False

    def read_channel_raw(self, channel: int, input_voltage: float) -> Tuple[int, float]:
        """
        Perform 16-bit ADC conversion on specified channel.
        Returns: (raw_adc_code_16bit, digitized_voltage_v)
        """
        if self.fault_i2c_bus_hang:
            raise IOError("ADS1115 I2C Bus Error: Device NACK / Bus Hang")

        # Clamp input voltage to PGA full scale range
        clamped_v = max(-self.pga_fsr_v, min(self.pga_fsr_v, input_voltage))

        # Add internal analog thermal/quantization noise (RMS ~1.2 LSB)
        noise = float(global_rng.np.normal(0.0, 1.2 * self.lsb_v))
        noisy_v = clamped_v + noise

        # 16-bit signed quantization
        raw_code = int(round(noisy_v / self.lsb_v))
        raw_code = max(-32768, min(32767, raw_code))

        # Reconstructed digital voltage from ADC code
        digitized_v = raw_code * self.lsb_v

        return raw_code, digitized_v

    def sample_all_channels(self, analog_voltages: Dict[str, float]) -> Dict[str, Any]:
        """
        Sample AIN0 (pH), AIN1 (EC), AIN2 (Turbidity).
        """
        if self.fault_i2c_bus_hang:
            return {"error": "I2C_NACK_ERROR", "success": False}

        raw_ph, v_ph = self.read_channel_raw(0, analog_voltages["v_ph"])
        raw_ec, v_ec = self.read_channel_raw(1, analog_voltages["v_ec"])
        raw_turb, v_turb = self.read_channel_raw(2, analog_voltages["v_turbidity"])

        return {
            "success": True,
            "error": None,
            "raw_codes": {
                "ph": raw_ph,
                "ec": raw_ec,
                "turbidity": raw_turb,
            },
            "voltages": {
                "v_ph": v_ph,
                "v_ec": v_ec,
                "v_turbidity": v_turb,
            },
            "lsb_resolution_v": self.lsb_v,
        }
