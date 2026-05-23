"""Smoke tests for custom_components.fuse_energy."""
from __future__ import annotations


def test_const_exposes_domain() -> None:
    from custom_components.fuse_energy.const import DOMAIN

    assert DOMAIN == "fuse_energy"


def test_manifest_is_valid_json_with_required_keys() -> None:
    import json
    from pathlib import Path

    manifest_path = Path("custom_components/fuse_energy/manifest.json")
    manifest = json.loads(manifest_path.read_text())

    assert manifest["domain"] == "fuse_energy"
    assert manifest["name"] == "Fuse Energy"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "cloud_polling"
    assert manifest["version"] == "0.0.1"
    assert manifest["codeowners"] == []


def test_api_module_exposes_expected_surface() -> None:
    from unittest.mock import MagicMock

    import aiohttp

    from custom_components.fuse_energy import api

    # Dataclass
    sample = api.FuseEnergyData(energy_total_kwh=1.0, cost_total_gbp=2.0)
    assert sample.energy_total_kwh == 1.0
    assert sample.cost_total_gbp == 2.0

    # Exception hierarchy
    assert issubclass(api.FuseEnergyApiAuthError, api.FuseEnergyApiError)

    # Constructor (use a mock session to avoid needing a running event loop;
    # the stub doesn't touch the session, so a placeholder is sufficient).
    session = MagicMock(spec=aiohttp.ClientSession)
    client = api.FuseEnergyApiClient(session=session, access_token="x")
    assert isinstance(client, api.FuseEnergyApiClient)
