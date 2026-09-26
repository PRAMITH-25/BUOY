import json
import pytest
from buoy_sim.web.app import app


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestWebEndpoints:
    def test_index_page(self, client):
        """Index page loads and contains required sections and honest labels."""
        response = client.get("/")
        assert response.status_code == 200
        html = response.data.decode("utf-8")
        assert "Solar-Powered Autonomous Lake Water Quality Monitoring Buoy" in html
        assert "SIMULATION" in html
        assert "NOT LIVE HARDWARE" in html
        assert "USGS Lake Erie Nearshore Sonde Dataset" in html
        assert "HISTORICAL DATA" in html
        assert "NOT LIVE MEASUREMENTS" in html
        assert "LoRa COMMUNICATION" in html
        assert "PROTOCOL SIMULATION" in html
        assert "Interactive Water Body &amp; USGS Spatial Heatmap" in html
        assert "Flow-Through Measurement Chamber" in html
        assert "Power Subsystem" in html
        assert "Flow-Through vs Continuous Exposure" in html

    def test_status_endpoint(self, client):
        """Status endpoint returns ground truth, sensors, chamber, power, lora."""
        response = client.get("/api/status")
        assert response.status_code == 200
        data = response.get_json()
        assert "sim_time_s" in data
        assert "ground_truth" in data
        assert "sensors" in data
        assert "chamber" in data
        assert "power" in data
        assert "lora" in data

    def test_power_endpoint(self, client):
        """Power endpoint returns compact power status."""
        response = client.get("/api/power")
        assert response.status_code == 200
        data = response.get_json()
        assert "solar_power_mw" in data
        assert "soc_pct" in data
        assert "voltage_v" in data
        assert "load_power_mw" in data
        assert "power_mode" in data
        assert "estimated_endurance_days" in data
        assert "chamber_cycle_energy_mwh" in data

    def test_draggable_buoy_position(self, client):
        """Moving buoy updates coordinates and returns position-dependent water quality."""
        # Initial position
        res1 = client.post("/api/control/buoy_position", json={"x": 200.0, "y": 150.0})
        assert res1.status_code == 200
        data1 = res1.get_json()
        assert data1["buoy_x"] == 200.0
        assert data1["buoy_y"] == 150.0
        assert "usgs_data" in data1
        val_turb1 = data1["usgs_data"]["turbidity_ntu"]

        # Move to different location
        res2 = client.post("/api/control/buoy_position", json={"x": 800.0, "y": 450.0})
        assert res2.status_code == 200
        data2 = res2.get_json()
        assert data2["buoy_x"] == 800.0
        assert data2["buoy_y"] == 450.0
        assert "usgs_data" in data2
        # Position updates should yield valid water-quality readings
        assert 0.0 <= data2["usgs_data"]["turbidity_ntu"] <= 35.0
        assert 6.0 <= data2["usgs_data"]["ph"] <= 10.0

    def test_usgs_contributors_endpoint(self, client):
        """Returns K contributing nearest USGS observations."""
        response = client.get("/api/usgs/contributors?x=500&y=300")
        assert response.status_code == 200
        data = response.get_json()
        assert "contributors" in data
        assert len(data["contributors"]) >= 3
        for pt in data["contributors"]:
            assert "turbidity_ntu" in pt
            assert "distance_m" in pt
            assert "weight_pct" in pt

    def test_usgs_grid_endpoint(self, client):
        """Returns 2D interpolated grid of real USGS measurements."""
        response = client.get("/api/usgs/grid?param=turbidity_ntu&cols=20&rows=10")
        assert response.status_code == 200
        data = response.get_json()
        assert "parameter" in data
        assert "grid" in data
        assert len(data["grid"]) == 10
        assert len(data["grid"][0]) == 20

    def test_lora_command(self, client):
        """LoRa command endpoint processes remote commands."""
        # Trigger measurement command
        response = client.post("/api/control/command", json={"command": "trigger_measurement"})
        assert response.status_code == 200
        data = response.get_json()
        assert "status" in data
        assert "ack" in data

        # Low-power mode command
        res_lp = client.post("/api/control/command", json={"command": "enter_low_power_mode"})
        assert res_lp.status_code == 200

        # Change sampling interval
        res_ci = client.post("/api/control/command", json={"command": "change_sampling_interval", "arg": 180})
        assert res_ci.status_code == 200

    def test_experiment_defaults(self, client):
        """Returns configurable experiment defaults."""
        response = client.get("/api/experiment/defaults")
        assert response.status_code == 200
        data = response.get_json()
        assert "fill_time_s" in data
        assert "stabilize_time_s" in data
        assert "flush_time_s" in data
        assert "measure_duration_s" in data
        assert "residual_turbidity_factor" in data

    def test_experiment_run_configurable(self, client):
        """Experiment run accepts custom simulation parameters."""
        payload = {
            "duration_s": 60.0,
            "fill_time_s": 25.0,
            "stabilize_time_s": 45.0,
            "flush_time_s": 15.0,
            "measure_duration_s": 6.0,
            "noise_scale": 1.2,
        }
        response = client.post("/api/experiment/run", json=payload)
        assert response.status_code == 200
        summary = response.get_json()
        assert "open_water_system_a" in summary
        assert "chamber_system_b" in summary
        assert "comparison_delta" in summary
        assert "validation_note" in summary
        assert "simulation_params_used" in summary
        assert summary["simulation_params_used"]["fill_time_s"] == 25.0
        assert summary["simulation_params_used"]["stabilize_time_s"] == 45.0

    def test_csv_exports(self, client):
        """CSV export endpoints return valid CSV files."""
        res_tel = client.get("/api/export/telemetry.csv")
        assert res_tel.status_code == 200
        assert "text/csv" in res_tel.content_type

        res_comp = client.get("/api/export/comparison.csv")
        assert res_comp.status_code == 200
        assert "text/csv" in res_comp.content_type
