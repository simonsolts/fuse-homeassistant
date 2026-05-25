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


@pytest.fixture
def primed_flow(hass, auto_enable_custom_integrations):
    """Helper: drive the user step to land on the OTP step with state set."""
    async def _drive():
        first = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": "user"}
        )
        with patch.object(auth_mod, "async_send_otp", AsyncMock(return_value="FLOW")):
            return await hass.config_entries.flow.async_configure(
                first["flow_id"],
                user_input={CONF_PHONE_NUMBER: "+447700900000"},
            )
    return _drive


async def test_otp_step_authorized_creates_entry_with_one_premises(
    hass: HomeAssistant, auto_enable_custom_integrations, primed_flow,
) -> None:
    from custom_components.fuse_energy.api import Premises
    from custom_components.fuse_energy.auth import AuthorizedResult, TokenPair

    landed = await primed_flow()
    assert landed["step_id"] == "otp"

    with (
        patch.object(
            auth_mod, "async_verify_otp",
            AsyncMock(return_value=AuthorizedResult(tokens=TokenPair("AT", "RT"))),
        ),
        patch(
            "custom_components.fuse_energy.config_flow."
            "FuseEnergyApiClient.async_list_premises",
            AsyncMock(return_value=[Premises(fid="pfid-1")]),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            landed["flow_id"], user_input={"verification_code": "123456"},
        )

    assert result["type"] == FlowResultType.CREATE_ENTRY
    assert result["title"] == "Fuse Energy"
    data = result["data"]
    assert data[CONF_PHONE_NUMBER] == "+447700900000"
    assert data["access_token"] == "AT"
    assert data["refresh_token"] == "RT"
    assert data["premises_fid"] == "pfid-1"
    assert data["device_id"]  # non-empty UUID generated by the user step


async def test_otp_step_additional_info_advances_to_step(
    hass, auto_enable_custom_integrations, primed_flow,
) -> None:
    from custom_components.fuse_energy.auth import (
        AdditionalInfoResult, Question,
    )

    landed = await primed_flow()

    with patch.object(
        auth_mod, "async_verify_otp",
        AsyncMock(return_value=AdditionalInfoResult(
            auth_flow_token="FLOW2",
            title="Verify your date of birth",
            subtitle="Let's make sure this is the right account",
            questions=[Question(key="DATE_OF_BIRTH", title="Date of birth", type="DATE")],
        )),
    ):
        result = await hass.config_entries.flow.async_configure(
            landed["flow_id"], user_input={"verification_code": "123456"},
        )

    assert result["type"] == FlowResultType.FORM
    assert result["step_id"] == "additional_info"


async def test_otp_step_invalid_code(
    hass, auto_enable_custom_integrations, primed_flow,
) -> None:
    landed = await primed_flow()
    with patch.object(
        auth_mod, "async_verify_otp",
        AsyncMock(side_effect=auth_mod.FuseEnergyAuthError(
            "nope", error_code="invalid_code",
        )),
    ):
        result = await hass.config_entries.flow.async_configure(
            landed["flow_id"], user_input={"verification_code": "000000"},
        )
    assert result["errors"] == {"base": "invalid_code"}


async def test_otp_step_aborts_on_multi_premises(
    hass, auto_enable_custom_integrations, primed_flow,
) -> None:
    from custom_components.fuse_energy.api import Premises
    from custom_components.fuse_energy.auth import AuthorizedResult, TokenPair

    landed = await primed_flow()
    with (
        patch.object(
            auth_mod, "async_verify_otp",
            AsyncMock(return_value=AuthorizedResult(tokens=TokenPair("AT", "RT"))),
        ),
        patch(
            "custom_components.fuse_energy.config_flow."
            "FuseEnergyApiClient.async_list_premises",
            AsyncMock(return_value=[Premises(fid="a"), Premises(fid="b")]),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            landed["flow_id"], user_input={"verification_code": "123456"},
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "multi_premises"


async def test_otp_step_aborts_on_no_premises(
    hass, auto_enable_custom_integrations, primed_flow,
) -> None:
    from custom_components.fuse_energy.auth import AuthorizedResult, TokenPair

    landed = await primed_flow()
    with (
        patch.object(
            auth_mod, "async_verify_otp",
            AsyncMock(return_value=AuthorizedResult(tokens=TokenPair("AT", "RT"))),
        ),
        patch(
            "custom_components.fuse_energy.config_flow."
            "FuseEnergyApiClient.async_list_premises",
            AsyncMock(return_value=[]),
        ),
    ):
        result = await hass.config_entries.flow.async_configure(
            landed["flow_id"], user_input={"verification_code": "123456"},
        )
    assert result["type"] == FlowResultType.ABORT
    assert result["reason"] == "no_premises"
