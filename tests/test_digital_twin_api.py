import pytest
from buoy_sim.web.app import app
from buoy_sim.core.location import get_location_config, set_location_config, get_nearby_stations
from buoy_sim.data.weather_client import WeatherClient
from buoy_sim.data.usgs_api_client import USGSWaterApiClient


@pytest.fixture
def client():
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


class TestDigitalTwinIntegrations:
    def test_location_configuration(self):
        """Demonstration location can be queried and updated."""
        loc = get_location_config()
        assert "water_body_name" in loc
        assert "latitude" in loc
        assert "longitude" in loc
        assert "bounds" in loc

        # Test updating location
        updated = set_location_config(41.58, -81.58, "Lake Erie - Euclid Sector")
        assert updated["latitude"] == 41.58
        assert updated["longitude"] == -81.58
        assert updated["water_body_name"] == "Lake Erie - Euclid Sector"

        # Restore default
        set_location_config(41.57963, -81.57919, "Lake Erie (Cleveland / Euclid Nearshore)")

    def test_nearby_stations_catalog(self):
        """Nearby stations list includes valid USGS monitoring sites with distance."""
        stations = get_nearby_stations()
        assert len(stations) >= 3
        for st in stations:
            assert "station_id" in st
            assert "station_name" in st
            assert "latitude" in st
            assert "longitude" in st
            assert "distance_km" in st
            assert st["distance_km"] >= 0.0
            assert "parameters_available" in st

    def test_weather_client_fallback_and_parsing(self):
        """Weather client handles offline fallback and parses response dictionary."""
        w_client = WeatherClient(timeout_s=0.01)  # tiny timeout triggers fallback if needed
        res = w_client.get_weather(41.57963, -81.57919)
        assert "air_temperature_c" in res
        assert "wind_speed_m_s" in res
        assert "precipitation_mm" in res
        assert "cloud_cover_pct" in res
        assert res["status"] in ["REAL_API_DATA", "CACHED_DATA", "OFFLINE_FALLBACK"]
        assert "source" in res
        assert "disclaimer" in res

    def test_usgs_water_client_fallback_and_parsing(self):
        """USGS Water client returns valid water parameters with offline CSV fallback."""
        usgs_client = USGSWaterApiClient(timeout_s=0.01)  # small timeout ensures fallback path works cleanly
        res = usgs_client.get_water_data(buoy_lat=41.57963, buoy_lon=-81.57919)
        assert "stations" in res
        assert "summary" in res
        assert "data_source" in res
        assert res["status"] in ["REAL_API_DATA", "CACHED_DATA", "HISTORICAL_DATA", "OFFLINE_FALLBACK"]
        summary = res["summary"]
        assert "ph" in summary
        assert "ec_us_cm" in summary
        assert "turbidity_ntu" in summary
        assert "water_temp_c" in summary

    def test_map_endpoint(self, client):
        """Endpoint /api/map returns center, bounds, buoy coordinates, and tile provider."""
        response = client.get("/api/map")
        assert response.status_code == 200
        data = response.get_json()
        assert "center" in data
        assert "buoy" in data
        assert "latitude" in data["buoy"]
        assert "longitude" in data["buoy"]
        assert "tile_provider" in data
        assert "openstreetmap" in data["tile_provider"]["url"]
        assert data["status"] == "REAL_MAP_ACTIVE"

    def test_environment_endpoint(self, client):
        """Endpoint /api/environment returns weather, water baseline, and location."""
        response = client.get("/api/environment")
        assert response.status_code == 200
        data = response.get_json()
        assert "location" in data
        assert "weather" in data
        assert "water_baseline" in data
        assert "buoy_position" in data
        assert "simulation_note" in data

    def test_weather_endpoint(self, client):
        """Endpoint /api/weather returns weather variables and honest status."""
        response = client.get("/api/weather")
        assert response.status_code == 200
        data = response.get_json()
        assert "air_temperature_c" in data
        assert "wind_speed_m_s" in data
        assert "status" in data
        assert data["status"] in ["REAL_API_DATA", "CACHED_DATA", "OFFLINE_FALLBACK"]

    def test_water_data_endpoint(self, client):
        """Endpoint /api/water-data returns observation parameters and status."""
        response = client.get("/api/water-data")
        assert response.status_code == 200
        data = response.get_json()
        assert "summary" in data
        assert "status" in data
        assert "data_source" in data

    def test_stations_endpoint(self, client):
        """Endpoint /api/stations returns nearby stations with coordinates and parameters."""
        response = client.get("/api/stations")
        assert response.status_code == 200
        data = response.get_json()
        assert "count" in data
        assert data["count"] >= 3
        assert "stations" in data

    def test_buoy_position_lat_lon_update(self, client):
        """POST /api/control/buoy_position accepts geographic lat/lon from Leaflet drag."""
        payload = {"latitude": 41.5810, "longitude": -81.5750}
        response = client.post("/api/control/buoy_position", json=payload)
        assert response.status_code == 200
        data = response.get_json()
        assert data["status"] == "POSITION_UPDATED"
        assert abs(data["latitude"] - 41.5810) < 0.005
        assert abs(data["longitude"] - (-81.5750)) < 0.005
        assert "usgs_data" in data

    def test_location_config_endpoint(self, client):
        """Endpoint /api/location/config allows GET and POST."""
        res_get = client.get("/api/location/config")
        assert res_get.status_code == 200
        assert "water_body_name" in res_get.get_json()

        res_post = client.post("/api/location/config", json={"latitude": 41.57963, "longitude": -81.57919})
        assert res_post.status_code == 200
        assert res_post.get_json()["status"] == "LOCATION_UPDATED"
