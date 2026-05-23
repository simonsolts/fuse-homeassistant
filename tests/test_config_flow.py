"""Tests for the Fuse Energy config flow."""
from __future__ import annotations

from unittest.mock import patch

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fuse_energy.api import (
    FuseEnergyApiAuthError,
    FuseEnergyApiError,
)
from custom_components.fuse_energy.const import (
    CONF_APP_AUTH,
    CONF_PREMISES_FID,
    CONF_SESSION_ID,
    DOMAIN,
)


_VALID_INPUT = {
    CONF_SESSION_ID: "sid",
    CONF_APP_AUTH: "aa",
    CONF_PREMISES_FID: "pfid",
}


async def test_user_step_form_shown(
    hass: HomeAssistant, auto_enable_custom_integrations
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_successful_submission_creates_entry(
    hass: HomeAssistant, auto_enable_custom_integrations
) -> None:
    with patch(
        "custom_components.fuse_energy.config_flow.FuseEnergyApiClient.async_fetch_day",
        return_value=[],
    ):
        first = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            first["flow_id"], user_input=_VALID_INPUT,
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Fuse Energy"
    assert result["data"] == _VALID_INPUT


async def test_invalid_auth_surfaces_field_error(
    hass: HomeAssistant, auto_enable_custom_integrations
) -> None:
    with patch(
        "custom_components.fuse_energy.config_flow.FuseEnergyApiClient.async_fetch_day",
        side_effect=FuseEnergyApiAuthError("bad"),
    ):
        first = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            first["flow_id"], user_input=_VALID_INPUT,
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_network_error_surfaces_cannot_connect(
    hass: HomeAssistant, auto_enable_custom_integrations
) -> None:
    with patch(
        "custom_components.fuse_energy.config_flow.FuseEnergyApiClient.async_fetch_day",
        side_effect=FuseEnergyApiError("boom"),
    ):
        first = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        result = await hass.config_entries.flow.async_configure(
            first["flow_id"], user_input=_VALID_INPUT,
        )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_single_instance_blocks_second_entry(
    hass: HomeAssistant, auto_enable_custom_integrations
) -> None:
    MockConfigEntry(domain=DOMAIN, data=_VALID_INPUT, unique_id="fuse_energy_singleton").add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"
