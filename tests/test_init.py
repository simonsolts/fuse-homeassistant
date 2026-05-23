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
    CONF_APP_AUTH,
    CONF_PREMISES_FID,
    CONF_SESSION_ID,
    DOMAIN,
)

_DATA = {CONF_SESSION_ID: "sid", CONF_APP_AUTH: "aa", CONF_PREMISES_FID: "pfid"}


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
    assert manifest["version"] == "0.0.2"
    assert manifest["codeowners"] == []


def test_const_exposes_new_config_keys_and_stat_templates() -> None:
    spec = importlib.util.spec_from_file_location(
        "fuse_const",
        Path(__file__).parent.parent / "custom_components/fuse_energy/const.py",
    )
    const = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(const)  # type: ignore[union-attr]

    assert const.CONF_SESSION_ID == "session_id"
    assert const.CONF_APP_AUTH == "app_auth"
    assert const.CONF_PREMISES_FID == "premises_fid"

    assert const.FUSE_BASE_URL == "https://www.fuseenergy.com"
    assert const.FUSE_TRPC_PATH == "/api/trpc"

    # UUID-format fids contain hyphens which are invalid in HA statistic_ids;
    # the helpers must sanitize them to underscores.
    fid = "abc12345-1234-1234-1234-abcdef123456"
    assert const.stat_id_consumption(fid) == "fuse_energy:elec_consumption_abc12345_1234_1234_1234_abcdef123456"
    assert const.stat_id_cost(fid) == "fuse_energy:elec_cost_abc12345_1234_1234_1234_abcdef123456"

    assert isinstance(const.FALLBACK_APP_VERSION, str) and const.FALLBACK_APP_VERSION


async def test_setup_and_unload_entry(
    recorder_mock, hass: HomeAssistant, auto_enable_custom_integrations
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN, data=_DATA, unique_id="fuse_energy_singleton"
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
