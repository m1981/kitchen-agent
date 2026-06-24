"""
tests/test_provider_endpoints.py
=================================
Tests for the two new provider-catalogue endpoints:

  GET  /api/providers         — list all providers + their model catalogues
  GET  /api/providers/active  — server default provider + model

TDD: these tests are written against the *interface contract* defined in the
frontend integration doc before the implementation exists.

Covers
------
- GET /api/providers returns a list with at least "gemini" and "anthropic"
- Each provider entry has: id, label, default_model, models[]
- Each model entry has: id, label, context_k (int > 0)
- GET /api/providers/active returns the server-configured default
- Active provider mirrors settings.llm_provider and matching *_model setting
- Switching settings.llm_provider changes the active response
- Model catalog is non-empty for both providers
- HTTP 200 for both endpoints
"""
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/providers
# ---------------------------------------------------------------------------

def test_list_providers_returns_200(client: TestClient) -> None:
    resp = client.get("/api/providers")
    assert resp.status_code == 200


def test_list_providers_is_list(client: TestClient) -> None:
    data = client.get("/api/providers").json()
    assert isinstance(data, list)


def test_list_providers_contains_gemini_and_anthropic(client: TestClient) -> None:
    ids = {p["id"] for p in client.get("/api/providers").json()}
    assert "gemini" in ids
    assert "anthropic" in ids


def test_provider_entry_has_required_fields(client: TestClient) -> None:
    for provider in client.get("/api/providers").json():
        assert "id"            in provider, f"missing id in {provider}"
        assert "label"         in provider, f"missing label in {provider}"
        assert "default_model" in provider, f"missing default_model in {provider}"
        assert "models"        in provider, f"missing models in {provider}"
        assert isinstance(provider["models"], list)


def test_provider_models_non_empty(client: TestClient) -> None:
    for provider in client.get("/api/providers").json():
        assert len(provider["models"]) > 0, f"empty models for provider {provider['id']}"


def test_model_entry_has_required_fields(client: TestClient) -> None:
    for provider in client.get("/api/providers").json():
        for model in provider["models"]:
            assert "id"        in model, f"missing id in model {model}"
            assert "label"     in model, f"missing label in model {model}"
            assert "context_k" in model, f"missing context_k in model {model}"
            assert isinstance(model["context_k"], int)
            assert model["context_k"] > 0


def test_provider_default_model_is_in_models_list(client: TestClient) -> None:
    """default_model must be one of the ids in the models[] list."""
    for provider in client.get("/api/providers").json():
        model_ids = {m["id"] for m in provider["models"]}
        assert provider["default_model"] in model_ids, (
            f"default_model '{provider['default_model']}' not found in models "
            f"for provider '{provider['id']}': {model_ids}"
        )


def test_provider_labels_are_non_empty_strings(client: TestClient) -> None:
    for provider in client.get("/api/providers").json():
        assert isinstance(provider["label"], str)
        assert len(provider["label"]) > 0
        for model in provider["models"]:
            assert isinstance(model["label"], str)
            assert len(model["label"]) > 0


# ---------------------------------------------------------------------------
# GET /api/providers/active
# ---------------------------------------------------------------------------

def test_active_provider_returns_200(client: TestClient) -> None:
    resp = client.get("/api/providers/active")
    assert resp.status_code == 200


def test_active_provider_has_required_fields(client: TestClient) -> None:
    data = client.get("/api/providers/active").json()
    assert "provider" in data
    assert "model"    in data
    assert isinstance(data["provider"], str)
    assert isinstance(data["model"],    str)
    assert len(data["provider"]) > 0
    assert len(data["model"])    > 0


def test_active_provider_matches_settings_gemini(client: TestClient) -> None:
    """When settings.llm_provider == 'gemini', active reflects gemini defaults."""
    import src.config as cfg
    with patch.object(cfg.settings, "llm_provider", "gemini"), \
         patch.object(cfg.settings, "gemini_model",  "gemini-2.5-flash"):
        data = TestClient(app).get("/api/providers/active").json()
    assert data["provider"] == "gemini"
    assert data["model"]    == "gemini-2.5-flash"


def test_active_provider_matches_settings_anthropic(client: TestClient) -> None:
    """When settings.llm_provider == 'anthropic', active reflects anthropic defaults."""
    import src.config as cfg
    with patch.object(cfg.settings, "llm_provider",    "anthropic"), \
         patch.object(cfg.settings, "anthropic_model", "claude-sonnet-4-5"):
        data = TestClient(app).get("/api/providers/active").json()
    assert data["provider"] == "anthropic"
    assert data["model"]    == "claude-sonnet-4-5"


def test_active_provider_is_one_of_listed_providers(client: TestClient) -> None:
    """The active provider id must appear in GET /api/providers."""
    listed_ids = {p["id"] for p in client.get("/api/providers").json()}
    active     = client.get("/api/providers/active").json()
    assert active["provider"] in listed_ids
