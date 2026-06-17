"""Tests for the FastAPI web dashboard endpoints."""
import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.fixture
def client():
    from hardware_scraper.web.app import app
    return TestClient(app)


class TestDashboard:
    def test_index_returns_html(self, client):
        r = client.get("/")
        assert r.status_code == 200
        assert "text/html" in r.headers["content-type"]
        assert "HardwareScraper" in r.text

    def test_index_contains_scan_button(self, client):
        r = client.get("/")
        assert "Scan All" in r.text

    def test_index_contains_valuate_button(self, client):
        r = client.get("/")
        assert "Valuate" in r.text


class TestStatusEndpoint:
    def test_status_idle(self, client):
        # Reset job state
        from hardware_scraper.web import app as web_module
        web_module._job["running"] = False
        web_module._job["log"] = []

        r = client.get("/api/status")
        assert r.status_code == 200
        data = r.json()
        assert data["running"] is False
        assert isinstance(data["log"], list)


class TestResultsEndpoint:
    def test_results_returns_list(self, client):
        mock_engine = MagicMock()
        mock_session = MagicMock()
        mock_session.__enter__ = MagicMock(return_value=mock_session)
        mock_session.__exit__ = MagicMock(return_value=False)
        mock_session.query.return_value.join.return_value.join.return_value.join.return_value.order_by.return_value.all.return_value = []

        with patch("hardware_scraper.web.app.make_engine", return_value=mock_engine), \
             patch("hardware_scraper.web.app.Session", return_value=mock_session):
            r = client.get("/api/results")
        assert r.status_code == 200
        assert isinstance(r.json(), list)


class TestScrapeEndpoint:
    def test_scrape_conflicts_when_running(self, client):
        from hardware_scraper.web import app as web_module
        web_module._job["running"] = True
        r = client.post("/api/scrape")
        assert r.status_code == 409
        web_module._job["running"] = False

    def test_scrape_starts_job(self, client):
        from hardware_scraper.web import app as web_module
        web_module._job["running"] = False

        with patch("hardware_scraper.web.app.asyncio.create_task"):
            r = client.post("/api/scrape?source=offerup")
        assert r.status_code == 200
        assert r.json()["started"] is True


class TestBrowseEndpoint:
    def test_browse_conflicts_when_running(self, client):
        from hardware_scraper.web import app as web_module
        web_module._job["running"] = True
        r = client.post("/api/browse")
        assert r.status_code == 409
        web_module._job["running"] = False

    def test_browse_starts_job(self, client):
        from hardware_scraper.web import app as web_module
        web_module._job["running"] = False

        with patch("hardware_scraper.web.app.asyncio.create_task"):
            r = client.post("/api/browse?source=offerup")
        assert r.status_code == 200
        assert r.json()["started"] is True


class TestValuateEndpoint:
    def test_valuate_conflicts_when_running(self, client):
        from hardware_scraper.web import app as web_module
        web_module._job["running"] = True
        r = client.post("/api/valuate")
        assert r.status_code == 409
        web_module._job["running"] = False

    def test_valuate_starts_job(self, client):
        from hardware_scraper.web import app as web_module
        web_module._job["running"] = False

        with patch("hardware_scraper.web.app.asyncio.create_task"):
            r = client.post("/api/valuate")
        assert r.status_code == 200
        assert r.json()["started"] is True


class TestScanEndpoint:
    def test_scan_conflicts_when_running(self, client):
        from hardware_scraper.web import app as web_module
        web_module._job["running"] = True
        r = client.post("/api/scan")
        assert r.status_code == 409
        web_module._job["running"] = False

    def test_scan_starts_job(self, client):
        from hardware_scraper.web import app as web_module
        web_module._job["running"] = False

        with patch("hardware_scraper.web.app.asyncio.create_task"):
            r = client.post("/api/scan")
        assert r.status_code == 200
        assert r.json()["started"] is True
