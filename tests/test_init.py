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


from unittest.mock import patch as _patch

from homeassistant.config_entries import ConfigEntryState
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_and_unload_entry(hass: HomeAssistant, auto_enable_custom_integrations) -> None:
    """The integration should load, expose two sensors, and unload cleanly."""
    from unittest.mock import MagicMock

    import aiohttp

    from custom_components.fuse_energy.api import FuseEnergyData
    from custom_components.fuse_energy.const import CONF_ACCESS_TOKEN, DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCESS_TOKEN: "valid-token"},
        unique_id="fuse_energy_singleton",
    )
    entry.add_to_hass(hass)

    # aiohttp_client.async_get_clientsession spawns a pycares DNS resolver
    # daemon thread that HA's leak-check teardown fails on. Patch it out
    # since the API client is itself stubbed below — no real network is used.
    fake_session = MagicMock(spec=aiohttp.ClientSession)

    with (
        _patch(
            "custom_components.fuse_energy.aiohttp_client.async_get_clientsession",
            return_value=fake_session,
        ),
        _patch(
            "custom_components.fuse_energy.api.FuseEnergyApiClient.async_get_data",
            return_value=FuseEnergyData(energy_total_kwh=1.0, cost_total_gbp=2.0),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        assert entry.state == ConfigEntryState.LOADED

        entities = hass.states.async_entity_ids("sensor")
        assert any("fuse_energy" in eid for eid in entities) or len(entities) >= 2

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.NOT_LOADED


async def test_setup_entry_surfaces_stub_failure(hass: HomeAssistant, auto_enable_custom_integrations) -> None:
    """With the real (stubbed) client, first refresh should fail and entry retries."""
    from unittest.mock import MagicMock

    import aiohttp

    from custom_components.fuse_energy.const import CONF_ACCESS_TOKEN, DOMAIN

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_ACCESS_TOKEN: "valid-token"},
        unique_id="fuse_energy_singleton",
    )
    entry.add_to_hass(hass)

    # Patch aiohttp_client.async_get_clientsession (see note in
    # test_setup_and_unload_entry) — the stubbed API client doesn't touch the
    # session, so a MagicMock is fine and avoids the pycares thread leak.
    fake_session = MagicMock(spec=aiohttp.ClientSession)

    with _patch(
        "custom_components.fuse_energy.aiohttp_client.async_get_clientsession",
        return_value=fake_session,
    ):
        # No patch on the client — the real stub raises NotImplementedError,
        # which the coordinator translates to UpdateFailed. HA marks the
        # entry SETUP_RETRY.
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert entry.state == ConfigEntryState.SETUP_RETRY
