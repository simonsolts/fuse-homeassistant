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


import pytest
from unittest.mock import AsyncMock

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed


async def test_coordinator_translates_auth_error_to_config_entry_auth_failed(
    hass: HomeAssistant,
) -> None:
    from custom_components.fuse_energy.api import (
        FuseEnergyApiAuthError,
        FuseEnergyApiClient,
    )
    from custom_components.fuse_energy.coordinator import (
        FuseEnergyDataUpdateCoordinator,
    )

    client = AsyncMock(spec=FuseEnergyApiClient)
    client.async_get_data.side_effect = FuseEnergyApiAuthError("bad token")

    coordinator = FuseEnergyDataUpdateCoordinator(hass, client)
    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_coordinator_translates_api_error_to_update_failed(
    hass: HomeAssistant,
) -> None:
    from custom_components.fuse_energy.api import (
        FuseEnergyApiClient,
        FuseEnergyApiError,
    )
    from custom_components.fuse_energy.coordinator import (
        FuseEnergyDataUpdateCoordinator,
    )

    client = AsyncMock(spec=FuseEnergyApiClient)
    client.async_get_data.side_effect = FuseEnergyApiError("boom")

    coordinator = FuseEnergyDataUpdateCoordinator(hass, client)
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()


async def test_coordinator_translates_not_implemented_to_update_failed(
    hass: HomeAssistant,
) -> None:
    from custom_components.fuse_energy.api import FuseEnergyApiClient
    from custom_components.fuse_energy.coordinator import (
        FuseEnergyDataUpdateCoordinator,
    )

    client = AsyncMock(spec=FuseEnergyApiClient)
    client.async_get_data.side_effect = NotImplementedError("stub")

    coordinator = FuseEnergyDataUpdateCoordinator(hass, client)
    with pytest.raises(UpdateFailed, match="not yet reverse-engineered"):
        await coordinator._async_update_data()


async def test_coordinator_returns_data_on_success(hass: HomeAssistant) -> None:
    from custom_components.fuse_energy.api import (
        FuseEnergyApiClient,
        FuseEnergyData,
    )
    from custom_components.fuse_energy.coordinator import (
        FuseEnergyDataUpdateCoordinator,
    )

    snapshot = FuseEnergyData(energy_total_kwh=12.5, cost_total_gbp=3.4)
    client = AsyncMock(spec=FuseEnergyApiClient)
    client.async_get_data.return_value = snapshot

    coordinator = FuseEnergyDataUpdateCoordinator(hass, client)
    result = await coordinator._async_update_data()
    assert result is snapshot
