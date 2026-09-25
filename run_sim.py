"""
Solar-Powered Autonomous Lake Water Quality Monitoring Buoy
Command-Line Interface (CLI) Simulation Runner.

Usage:
  python run_sim.py --duration 600 --step 2.0 --compare
  python run_sim.py --help
"""
import argparse
import time
import sys
from buoy_sim.esp32.system import BuoySystem
from buoy_sim.experiments.comparison import ComparisonExperiment
from buoy_sim.experiments.exporter import TelemetryExporter

def main():
    parser = argparse.ArgumentParser(
        description="Solar-Powered Autonomous Lake Water Quality Monitoring Buoy — Digital Simulation"
    )
    parser.add_argument("--duration", type=float, default=600.0, help="Simulation duration in seconds (default: 600s)")
    parser.add_argument("--step", type=float, default=2.0, help="Simulation time step in seconds (default: 2.0s)")
    parser.add_argument("--compare", action="store_true", help="Run side-by-side Conventional vs Flow-Through comparison")
    parser.add_argument("--export-csv", type=str, default="", help="Path to export results CSV file")
    args = parser.parse_args()

    print("=" * 80)
    print(" SOLAR-POWERED AUTONOMOUS LAKE WATER QUALITY MONITORING BUOY")
    print(" Digital Simulation & Engineering Verification Prototype")
    print("=" * 80)
    print(f"[*] Configuration: Duration={args.duration}s | Step={args.step}s | Compare={args.compare}")
    print("[*] Sensors: pH, EC/TDS, Turbidity, Water Temperature | ADS1115 16-Bit ADC")
    print("[*] Processing: ESP32-S3 Logical Architecture | Power: Solar Panel + LiFePO4 BMS")
    print("[*] Communication: LoRa Node + Shore Gateway with HMAC-SHA256 MIC & Anti-Replay")
    print("-" * 80)

    if args.compare:
        print("")
        print("[+] Running Comparative Research Trial (Conventional Open Water vs Chamber)...")
        exp = ComparisonExperiment(duration_s=args.duration, step_s=args.step)
        summary = exp.run()

        delta = summary["comparison_delta"]
        sa = summary["open_water_system_a"]
        sb = summary["chamber_system_b"]

        print("")
        print("=" * 80)
        print(" RESEARCH EXPERIMENT SUMMARY RESULTS")
        print("=" * 80)
        print(f"| {'Metric':<30} | {'Conventional (A)':<18} | {'Chamber (B)':<18} | {'Advantage':<18} |")
        print("|" + "-" * 32 + "|" + "-" * 20 + "|" + "-" * 20 + "|" + "-" * 20 + "|")

        turb_reduct = f"{delta['noise_reduction_pct']['turbidity']}% less noise"
        ph_reduct = f"{delta['noise_reduction_pct']['ph']}% less variance"
        energy_sav = f"{delta['energy_savings_pct']}% energy saved"
        batt_mult = f"{delta['battery_life_multiplier']}x endurance"

        print(f"| {'Turbidity Noise (Std Dev)':<30} | {sa['statistics']['turbidity']['std']:<18.4f} | {sb['statistics']['turbidity']['std']:<18.4f} | {turb_reduct:<18} |")
        print(f"| {'pH Noise (Std Dev)':<30} | {sa['statistics']['ph']['std']:<18.4f} | {sb['statistics']['ph']['std']:<18.4f} | {ph_reduct:<18} |")
        print(f"| {'Energy Per Cycle (mWh)':<30} | {sa['energy_per_cycle_mwh']:<18.2f} | {sb['energy_per_cycle_mwh']:<18.2f} | {energy_sav:<18} |")
        print(f"| {'Estimated Battery Life (days)':<30} | {sa['estimated_battery_endurance_days']:<18.1f} | {sb['estimated_battery_endurance_days']:<18.1f} | {batt_mult:<18} |")
        print(f"| {'Packets Transmitted':<30} | {sa['packets_transmitted']:<18} | {sb['packets_transmitted']:<18} | {delta['comm_overhead_reduction_pct']}% less RF load   |")
        print("=" * 80)

        print("")
        print("[!] VALIDATION BOUNDARY NOTICE:")
        print("   " + summary["disclaimer"])

        if args.export_csv:
            csv_content = TelemetryExporter.export_comparison_csv(exp.logs_a, exp.logs_b)
            with open(args.export_csv, "w", encoding="utf-8") as f:
                f.write(csv_content)
            print("")
            print(f"[+] Exported comparative data to CSV: {args.export_csv}")

    else:
        print("")
        print("[+] Initializing Autonomous Buoy System Simulation...")
        system = BuoySystem()
        steps = int(args.duration / args.step)
        print(f"[+] Stepping through {steps} simulation ticks...")
        print("")

        header = f"{'Sim Time':<10} | {'Chamber State':<16} | {'pH':<6} | {'Turb(NTU)':<10} | {'EC(uS)':<8} | {'Temp(C)':<8} | {'SOC(%)':<7} | {'Solar(mW)':<10}"
        print(header)
        print("-" * len(header))

        for i in range(steps):
            snap = system.step(args.step)
            if i % max(1, steps // 20) == 0:
                st = snap["chamber"]["current_state"]
                f = snap["sensors"]["filtered"]
                p = snap["power"]
                t_str = time.strftime("%H:%M:%S", time.gmtime(snap["sim_time_s"]))
                print(f"{t_str:<10} | {st:<16} | {f['ph']:<6.2f} | {f['turbidity_ntu']:<10.1f} | {f['ec_us_cm']:<8.0f} | {f['temp_c']:<8.1f} | {p['battery']['soc_pct']:<7.1f} | {p['solar_power_mw']:<10.1f}")

        print("")
        print("[+] Simulation run completed successfully.")
        print(f"[*] Total Chamber Cycles Completed: {system.chamber.total_cycles_completed}")
        print(f"[*] LoRa Packets Sent: {system.lora_node.total_transmitted} | ACKed: {system.lora_node.total_acked}")
        print(f"[*] Gateway Accepted: {system.gateway.total_packets_accepted} | Rejected: {system.gateway.total_packets_rejected}")

        if args.export_csv:
            csv_content = TelemetryExporter.export_telemetry_csv(system.gateway.telemetry_history)
            with open(args.export_csv, "w", encoding="utf-8") as f:
                f.write(csv_content)
            print(f"[+] Telemetry exported to CSV: {args.export_csv}")

if __name__ == "__main__":
    main()
