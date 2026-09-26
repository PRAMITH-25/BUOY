# Solar-Powered Autonomous Lake Water Quality Monitoring Buoy
## Digital Simulation & Software Prototype — Geographic Digital Twin

A comprehensive digital software prototype for the planned solar-powered autonomous lake-water quality monitoring buoy, developed before physical hardware implementation. Now upgraded to a **real geographic digital twin** anchored to Lake Erie (Cleveland / Euclid Nearshore) with live external API data.

---

### Data Source Legend

| Badge | Meaning |
|---|---|
| 🟢 REAL DATA | Live API response (Open-Meteo weather, USGS streamgages) |
| 🔵 HISTORICAL | USGS CSV dataset (KNN-IDW spatial interpolation) |
| 🟡 SIMULATED | ESP32-S3 / sensor / LoRa / chamber — physically modelled |
| ⚫ CACHED | Stale real-API data used as offline fallback |

---

### System Architecture & Confirmed Specifications

- **Water Quality Sensing**: pH (analog op-amp model), EC/TDS (temperature-compensated conductivity cell), Turbidity (nephelometric optical infrared model), Water Temperature (DS18B20 digital thermistor).
- **Other Sensing**: NEO-6M GPS (orbital mooring drift, NMEA strings, HDOP, satellites) and MPU6050 6-DOF IMU (accelerometer, gyroscope, lake surface wave pitch/roll/heave).
- **Processing**: ESP32-S3 microcontroller logical architecture + ADS1115 external 16-bit Delta-Sigma ADC.
- **Communication**: LoRa buoy node (SX1262) + LoRa shore gateway with cryptographic authentication (HMAC-SHA256 MIC) and encryption.
- **Power Subsystem**: Monocrystalline solar panel (10W MPPT model) + rechargeable LiFePO4 / Li-ion battery (4400 mAh, 3.7V) + BMS protection + DC regulation.

---

### Five Implementation Stages

#### Stage 1 — Foundation
- **Virtual Sensors**: Realistic ground-truth lake environment with diurnal cycle (solar radiation, photosynthesis-driven pH variation, water temperature lag, wave dynamics) and storm rain runoff events.
- **ADS1115 16-Bit ADC Emulator**: 16-bit quantization (-32768 to 32767), Programmable Gain Amplifier (PGA +/-4.096V), 125 µV LSB resolution, and I2C error handling.
- **Navigation & IMU**: NEO-6M GPS position drift within mooring anchor circle, NMEA sentence generation; MPU6050 6-DOF wave tilt and heave.
- **Signal Processing**: Median filter + Moving Average filter, outlier/bubble spike rejection, calibrated physical conversions, and statistical noise comparison (mean, standard deviation, peak-to-peak amplitude, SNR).
- **Reproducible Seed**: Deterministic random number generator (`ReproducibleRNG`) with fixed seed for exact reproducibility.

#### Stage 2 — Main Function: Flow-Through Measurement Concept
- **State Machine**:
  `LAKE_MONITORING → CHAMBER_FILL → STABILIZE → MEASURE → FLUSH → LAKE_MONITORING`
- **Chamber Dynamics**: Micro-pump hydraulic fill, dark opaque enclosure blocking 100% of ambient solar optical flicker, quiescent settling eliminating turbulence and microbubbles, precision multi-sample measurement, and purge flush.

#### Stage 3 — Complete System
- **Power Model**: Diurnal solar irradiance curve with angle of incidence and thermal derating; battery coulomb counting, nonlinear Open-Circuit Voltage (OCV) curve, internal resistance drop, and BMS cutoffs.
- **ESP32-S3 Logical Architecture**: 6 independent conceptual tasks:
  `SensorTask`, `ChamberTask`, `ProcessingTask`, `GPSTask`, `LoRaTask`, `PowerTask`.
- **Software Watchdog & Reliability**: 10-second watchdog timer, task heartbeats, task freeze detection, auto-reset, crash logs, and deliberate fault injection (sensor disconnect, I2C hang, pump stall, LoRa loss, GPS loss).
- **LoRa Communication & Shore Gateway**: Structured binary-like frame format, AES-CTR encrypted payload, truncated HMAC-SHA256 Message Integrity Code (4 bytes), monotonic frame counter for replay defense, RF path loss model, round-trip latency, and remote commands (trigger measurement, change interval, request status, initiate chamber cycle, low power mode).

#### Stage 4 — Results Interface & Web Dashboard
- **Interactive Chamber Visualizer**: Dynamic animated canvas rendering fluid level, valves, pump rotation, optical shield status, countdown timer, and state badges.
- **Live Telemetry & Diagnostics**: Real-time cards for pH, EC/TDS, Turbidity, Temperature, GPS coordinates, IMU wave heave, Battery SOC %, and Solar mW.
- **Noise Analyzer**: Real-time table comparing raw ADC samples vs filtered values, noise standard deviation (σ), and SNR improvement.
- **LoRa Shore Gateway Terminal**: Packet inspector, MIC check, remote command issuance, and live security test buttons ("Test Tampered Packet", "Test Replay Attack").
- **Historical Multi-Parameter Charts**: Real-time Chart.js graphs for water quality time series and power generation/consumption.
- **Main Research Experiment Panel**: Side-by-side comparative analysis of Conventional Continuous Open Water Exposure vs Flow-Through Chamber Measurement with quantitative metrics and CSV exports.

#### Stage 5 — Geographic Digital Twin Upgrade *(New)*
- **Real Leaflet.js GIS Map**: Interactive satellite + street tile map anchored to real Lake Erie (Cleveland / Euclid Nearshore) coordinates (41.57963° N, -81.57919° W). Draggable virtual buoy updates all sensor values.
- **Open-Meteo Live Weather** (`/api/weather`): Real-time air temperature, wind speed/direction, precipitation, and solar irradiance fetched from the Open-Meteo API with 30-minute cache and offline fallback.
- **USGS Streamgage Network** (`/api/stations`, `/api/water_data`): Real USGS Water Services API integration for live discharge, stage, temperature, specific conductance, and turbidity at nearby Lake Erie monitoring stations. Falls back to USGS CSV dataset on network failure.
- **USGS KNN-IDW Spatial Interpolation**: When the buoy is dragged on the map, the virtual lat/lon maps to the historical USGS dataset and interpolates realistic water-quality values using K-Nearest Neighbour Inverse Distance Weighting.
- **Unified Buoy State**: A single authoritative buoy state (lat/lon ↔ virtual x/y ↔ USGS observation) ensures that all dashboard panels — Leaflet map, heatmap canvas, sensor cards, GPS readout — are synchronized.
- **Dual Map Mode**: Switch between the geographic Leaflet GIS map and the environmental heatmap canvas with a single button.
- **Data-Source Badges**: Every panel clearly labels whether the displayed value is REAL (live API), HISTORICAL (USGS CSV), or SIMULATED (virtual sensor model).

---

### New REST API Endpoints (Stage 5)

| Endpoint | Description |
|---|---|
| `GET /api/map` | Geographic anchor point, USGS dataset bounds, water-body name |
| `GET /api/weather` | Live Open-Meteo weather (air temp, wind, rain, solar) + data-source status |
| `GET /api/water-data` | Live/cached USGS streamgage water-quality readings for nearby stations |
| `GET /api/stations` | Catalogue of real USGS monitoring stations near Lake Erie |
| `GET /api/environment` | Spatial-field state (flow speed, storm flag, weather context) |
| `GET /api/location_config` | Full location configuration (lat/lon, bounds, zoom level) |
| `POST /api/buoy/position` | Accept `{lat, lon}` from Leaflet drag event; updates all sensor values |

---

### Validation Boundary

> [!IMPORTANT]
> **Scientific Validation Disclaimer**:
> This simulation validates software architecture, algorithms, state transitions, communication protocol, power-model assumptions, data processing and experimental methodology.
> It cannot prove actual pump flow rate, chamber flushing effectiveness, real sensor drift, real biofouling reduction or real-world measurement accuracy. Those require physical hardware testing.

> [!NOTE]
> **Data Transparency**: All live API data (Open-Meteo weather, USGS readings) is clearly labelled "REAL DATA" in the UI. ESP32/sensor/LoRa/chamber telemetry is explicitly marked "SIMULATED". The physical buoy hardware does not yet exist.

---

### Installation & Quick Start

#### 1. Requirements
Ensure Python 3.10+ is installed:
```bash
pip install -r requirements.txt
```
Required packages: `Flask>=2.3.0`, `numpy>=1.24.0`, `scipy>=1.10.0`, `pandas>=2.0.0`, `gunicorn>=21.2.0`

#### 2. Running Unit Tests
Execute the 63 automated tests covering all modules including the geographic digital twin:
```bash
python -m pytest tests/ -v
```

#### 3. Running the Web Dashboard
Launch the interactive web prototype:
```bash
python run_web.py --port 5000
```
Open your browser at `http://127.0.0.1:5000` to interact with the digital twin, control chamber cycles, inject faults, test LoRa security, view live weather, and explore the geographic GIS map.

#### 4. Running the CLI Simulation
Run a headless batch simulation or comparative research trial:
```bash
# Run 10-minute simulation with live terminal telemetry
python run_sim.py --duration 600

# Run side-by-side Conventional vs Flow-Through comparison and export CSV
python run_sim.py --duration 1800 --compare --export-csv comparison_results.csv
```

#### 5. Deployment (Render / Gunicorn)
```bash
gunicorn "buoy_sim.web.app:create_app()" --bind 0.0.0.0:$PORT --workers 1
```
The project is ready for deployment on Render.com using `gunicorn` as configured in `render.yaml`.
