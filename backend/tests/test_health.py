"""Tests for the health endpoint."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_returns_expected_response(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "healthy",
        "application": "MindVault",
        "version": "1.0.0",
    }


def test_health_is_present_in_openapi_schema(client: TestClient) -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/health" in response.json()["paths"]
