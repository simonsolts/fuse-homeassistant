"""Smoke tests for custom_components.fuse_energy."""
from __future__ import annotations

import importlib.util
import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

import aiohttp
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fuse_energy.api import HourlyBar
from custom_components.fuse_energy.const import (
    CONF_ACCESS_TOKEN,
    CONF_DEVICE_ID,
    CONF_PHONE_NUMBER,
    CONF_PREMISES_FID,
    CONF_REFRESH_TOKEN,
    DOMAIN,
)

_DATA = {
    CONF_DEVICE_ID: "dev-uuid",
    CONF_ACCESS_TOKEN: "AT",
    CONF_REFRESH_TOKEN: "RT",
    CONF_PREMISES_FID: "pfid",
}


def test_const_exposes_domain() -> None:
    from custom_components.fuse_energy.const import DOMAIN

    assert DOMAIN == "fuse_energy"


def test_manifest_is_valid_json_with_required_keys() -> None:
    manifest_path = Path("custom_components/fuse_energy/manifest.json")
    manifest = json.loads(manifest_path.read_text())

    assert manifest["domain"] == "fuse_energy"
    assert manifest["name"] == "Fuse Energy"
    assert manifest["config_flow"] is True
    assert manifest["iot_class"] == "cloud_polling"
    assert manifest["version"] == "0.4.6"
    assert manifest["codeowners"] == []


def test_const_exposes_new_config_keys_and_stat_templates() -> None:
    spec = importlib.util.spec_from_file_location(
        "fuse_const",
        Path(__file__).parent.parent / "custom_components/fuse_energy/const.py",
    )
    const = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(const)  # type: ignore[union-attr]

    assert const.CONF_DEVICE_ID == "device_id"
    assert const.CONF_ACCESS_TOKEN == "access_token"
    assert const.CONF_REFRESH_TOKEN == "refresh_token"
    assert const.CONF_PREMISES_FID == "premises_fid"

    assert const.FUSE_API_BASE_URL == "https://api.fuseenergy.com"
    assert const.FUSE_WEB_BASE_URL == "https://www.fuseenergy.com"

    # UUID-format fids contain hyphens which are invalid in HA statistic_ids;
    # the helpers must sanitize them to underscores.
    fid = "abc12345-1234-1234-1234-abcdef123456"
    assert const.stat_id_consumption(fid) == "fuse_energy:elec_consumption_abc12345_1234_1234_1234_abcdef123456"
    assert const.stat_id_cost(fid) == "fuse_energy:elec_cost_abc12345_1234_1234_1234_abcdef123456"


async def test_setup_and_unload_entry(
    recorder_mock, hass: HomeAssistant, auto_enable_custom_integrations
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_DATA, unique_id="fuse_energy_singleton", version=2,
    )
    entry.add_to_hass(hass)

    fake_session = MagicMock(spec=aiohttp.ClientSession)

    bar = HourlyBar(
        local_date=date.today(),
        local_hour=0,
        kwh=Decimal("0.5"),
        cost_gbp=Decimal("0.05"),
        is_realised=True,
    )

    with (
        patch(
            "custom_components.fuse_energy.aiohttp_client.async_get_clientsession",
            return_value=fake_session,
        ),
        patch(
            "custom_components.fuse_energy.api.FuseEnergyApiClient.async_fetch_day",
            return_value=[bar],
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.LOADED

        entities = hass.states.async_entity_ids("sensor")
        assert sum("fuse_energy" in eid for eid in entities) == 2

        assert await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
        assert entry.state == ConfigEntryState.NOT_LOADED


async def test_persist_tokens_callback_updates_entry_data(
    hass: HomeAssistant, auto_enable_custom_integrations,
) -> None:
    """Setting up the entry should wire a callback that writes new tokens
    into entry.data, leaving other keys untouched."""
    from custom_components.fuse_energy.auth import TokenPair

    entry = MockConfigEntry(domain=DOMAIN, data=_DATA, entry_id="e1", version=2)
    entry.add_to_hass(hass)

    fake_session = MagicMock(spec=aiohttp.ClientSession)
    with (
        patch(
            "custom_components.fuse_energy.aiohttp_client.async_get_clientsession",
            return_value=fake_session,
        ),
        patch(
            "custom_components.fuse_energy.coordinator."
            "FuseEnergyDataUpdateCoordinator.async_config_entry_first_refresh"
        ),
        patch(
            "custom_components.fuse_energy.FuseEnergyApiClient"
        ) as ClientCls,
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        # Grab the callback that __init__.py passed to the client.
        kwargs = ClientCls.call_args.kwargs
        cb = kwargs["on_tokens_refreshed"]

        await cb(TokenPair("AT_NEW", "RT_NEW"))

        assert entry.data[CONF_ACCESS_TOKEN] == "AT_NEW"
        assert entry.data[CONF_REFRESH_TOKEN] == "RT_NEW"
        assert entry.data[CONF_DEVICE_ID] == "dev-uuid"  # untouched
        assert entry.data[CONF_PREMISES_FID] == "pfid"   # untouched

        await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()
