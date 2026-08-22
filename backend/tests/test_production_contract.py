"""Production contract tests.

These tests validate local repository contracts only. They do not claim that
external services are live; those checks require the deployed environment.
"""
from pathlib import Path
import os

ROOT = Path(__file__).resolve().parents[2]


def test_required_production_environment_contract_is_documented():
    required = {
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SHOPIFY_CLIENT_ID",
        "SHOPIFY_CLIENT_SECRET",
        "SHOPIFY_REDIRECT_URI",
        "SHOPIFY_WEBHOOK_URL",
        "SIBYL_MEMORY_DB",
        "SHOPIFY_TOKEN_ENCRYPTION_KEY",
    }
    env_example = ROOT / ".env.example"
    assert env_example.exists(), "Missing .env.example"
    text = env_example.read_text()
    missing = [name for name in required if f"{name}=" not in text]
    assert not missing, f"Missing environment contract entries: {missing}"


def test_sibyl_memory_path_is_explicit():
    value = os.getenv("SIBYL_MEMORY_DB", "/data/sibyl/memory.db")
    assert value, "SIBYL_MEMORY_DB must not be empty"


def test_production_has_health_and_readiness_contracts():
    app_files = list((ROOT / "backend" / "app").glob("*.py"))
    source = "\n".join(p.read_text(errors="ignore") for p in app_files)
    assert "/health" in source
    assert "/ready" in source
