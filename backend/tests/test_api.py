"""Tests for the FastAPI backend endpoints."""

import io
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.main import app, filings, lifecycles

SAMPLE_CSV = Path(__file__).resolve().parent.parent.parent / "sample-data" / "sample_arr_filing.csv"

client = TestClient(app)


@pytest.fixture(autouse=True)
def clear_state():
    """Reset in-memory state between tests."""
    filings.clear()
    lifecycles.clear()
    yield
    filings.clear()
    lifecycles.clear()


def _upload_sample():
    """Helper: upload the sample CSV and return the response."""
    with open(SAMPLE_CSV, "rb") as f:
        return client.post(
            "/api/filings/upload",
            files={"file": ("sample.csv", f, "text/csv")},
            data={
                "filing_id": "TEST/ARR/API/2024",
                "licensee": "API Test DISCOM",
                "regulatory_commission": "AERC",
                "filing_type": "MYT",
                "licensee_code": "ATDCL",
                "state_province": "Test State",
                "unit_scale": "CRORE",
            },
        )


class TestHealth:
    def test_health_endpoint(self):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "healthy"
        assert data["service"] == "ies-rde-tool"


class TestFilingUpload:
    def test_upload_csv(self):
        resp = _upload_sample()
        assert resp.status_code == 200
        data = resp.json()
        assert data["filingId"] == "TEST/ARR/API/2024"
        assert data["licensee"] == "API Test DISCOM"
        assert data["fiscalYears"] == 2
        assert data["totalLineItems"] == 26
        assert data["validation"]["isValid"] is True
        assert len(data["payloadHash"]) == 64

    def test_upload_empty_file(self):
        resp = client.post(
            "/api/filings/upload",
            files={"file": ("empty.csv", io.BytesIO(b""), "text/csv")},
            data={
                "filing_id": "TEST/EMPTY",
                "licensee": "Test",
                "regulatory_commission": "Test",
            },
        )
        assert resp.status_code == 400

    def test_upload_invalid_csv(self):
        bad_csv = b"wrong_col1,wrong_col2\nval1,val2\n"
        resp = client.post(
            "/api/filings/upload",
            files={"file": ("bad.csv", io.BytesIO(bad_csv), "text/csv")},
            data={
                "filing_id": "TEST/BAD",
                "licensee": "Test",
                "regulatory_commission": "Test",
            },
        )
        assert resp.status_code == 422
        assert "Missing required columns" in resp.json()["detail"]


class TestFilingList:
    def test_list_empty(self):
        resp = client.get("/api/filings")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_list_after_upload(self):
        _upload_sample()
        resp = client.get("/api/filings")
        data = resp.json()
        assert len(data) == 1
        assert data[0]["filingId"] == "TEST/ARR/API/2024"
        assert data[0]["lifecycleStage"] == "NOT_STARTED"


class TestFilingDetail:
    def test_get_filing(self):
        upload_resp = _upload_sample()
        record_id = upload_resp.json()["id"]

        resp = client.get(f"/api/filings/{record_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["filingId"] == "TEST/ARR/API/2024"
        assert data["jsonld"]["objectType"] == "ARR_FILING"
        assert data["validation"]["isValid"] is True

    def test_get_nonexistent_filing(self):
        resp = client.get("/api/filings/nonexistent")
        assert resp.status_code == 404


class TestHashVerification:
    def test_verify_hash_valid(self):
        upload_resp = _upload_sample()
        record_id = upload_resp.json()["id"]

        resp = client.post(f"/api/filings/{record_id}/verify-hash")
        assert resp.status_code == 200
        data = resp.json()
        assert data["isValid"] is True
        assert data["storedHash"] == data["computedHash"]

    def test_verify_hash_nonexistent(self):
        resp = client.post("/api/filings/nonexistent/verify-hash")
        assert resp.status_code == 404
