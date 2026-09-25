"""
CSV Exporter for Telemetry Logs and Experimental Comparison Results.
Allows downloading and persisting simulated measurements and research data.
"""
import csv
import io
from typing import List, Dict, Any

class TelemetryExporter:
    @staticmethod
    def export_telemetry_csv(records: List[Dict[str, Any]]) -> str:
        """
        Generate CSV string for telemetry historical measurements.
        """
        output = io.StringIO()
        if not records:
            return "No telemetry data recorded."

        fieldnames = [
            "timestamp", "seq_num", "ph", "ec_us_cm", "turbidity_ntu", "temp_c",
            "soc_pct", "solar_power_mw", "latitude", "longitude",
            "chamber_state", "quality_flag"
        ]
        writer = csv.DictWriter(output, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for r in records:
            writer.writerow(r)

        return output.getvalue()

    @staticmethod
    def export_comparison_csv(logs_a: List[Dict[str, Any]], logs_b: List[Dict[str, Any]]) -> str:
        """
        Generate CSV string comparing System A (Open Water) vs System B (Chamber).
        """
        output = io.StringIO()
        fieldnames = [
            "sim_time_s", "hour_of_day",
            "sys_a_ph", "sys_a_turbidity_ntu", "sys_a_ec_us_cm", "sys_a_temp_c", "sys_a_power_mw", "sys_a_soc_pct",
            "sys_b_chamber_state", "sys_b_ph", "sys_b_turbidity_ntu", "sys_b_ec_us_cm", "sys_b_temp_c", "sys_b_power_mw", "sys_b_soc_pct"
        ]
        writer = csv.writer(output)
        writer.writerow(fieldnames)

        min_len = min(len(logs_a), len(logs_b))
        for i in range(min_len):
            a = logs_a[i]
            b = logs_b[i]
            writer.writerow([
                a.get("sim_time_s", 0),
                round(a.get("hour_of_day", 0), 2),
                a.get("ph", ""),
                a.get("turbidity_ntu", ""),
                a.get("ec_us_cm", ""),
                a.get("temp_c", ""),
                a.get("power_mw", ""),
                a.get("soc_pct", ""),
                b.get("chamber_state", ""),
                b.get("ph", ""),
                b.get("turbidity_ntu", ""),
                b.get("ec_us_cm", ""),
                b.get("temp_c", ""),
                b.get("power_mw", ""),
                b.get("soc_pct", ""),
            ])

        return output.getvalue()
