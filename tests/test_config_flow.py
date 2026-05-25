"""Tests for the Fuse Energy config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import aiohttp
import pytest
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.fuse_energy import auth as auth_mod
from custom_components.fuse_energy.const import CONF_PHONE_NUMBER, DOMAIN


@pytest.fixture(autouse=True)
def mock_aiohttp_session():
    fake = MagicMock(spec=aiohttp.ClientSession)
    with patch(
        "custom_components.fuse_energy.config_flow.aiohttp_client.async_get_clientsession",
        return_value=fake,
    ):
        yield fake


async def test_user_step_form_shown(
    hass: HomeAssistant, auto_enable_custom_integrations,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "user"


async def test_user_step_rejects_non_e164(
    hass: HomeAssistant, auto_enable_custom_integrations,
) -> None:
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    result = await hass.config_entries.flow.async_configure(
        first["flow_id"], user_input={CONF_PHONE_NUMBER: "07700912345"},  # no +
    )
    assert result["type"] == FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_phone"}


async def test_user_step_advances_to_otp_on_send_success(
    hass: HomeAssistant, auto_enable_custom_integrations,
) -> None:
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    with patch.object(auth_mod, "async_send_otp", AsyncMock(return_value="FLOW")):
        result = await hass.config_entries.flow.async_configure(
            first["flow_id"], user_input={CONF_PHONE_NUMBER: "+447700900000"},
        )
    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "otp"


async def test_user_step_surfaces_send_otp_error_code(
    hass: HomeAssistant, auto_enable_custom_integrations,
) -> None:
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    with patch.object(
        auth_mod, "async_send_otp",
        AsyncMock(side_effect=auth_mod.FuseEnergyAuthError(
            "nope", error_code="phone_not_recognised",
        )),
    ):
        result = await hass.config_entries.flow.async_configure(
            first["flow_id"], user_input={CONF_PHONE_NUMBER: "+447777777777"},
        )
    assert result["errors"] == {"base": "phone_not_recognised"}


async def test_user_step_transient_error_shows_cannot_connect(
    hass: HomeAssistant, auto_enable_custom_integrations,
) -> None:
    first = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": "user"}
    )
    with patch.object(
        auth_mod, "async_send_otp",
        AsyncMock(side_effect=auth_mod.FuseEnergyAuthTransient("net")),
    ):
        result = await hass.config_entries.flow.async_configure(
            first["flow_id"], user_input={CONF_PHONE_NUMBER: "+447777777777"},
        )
    assert result["errors"] == {"base": "cannot_connect"}
