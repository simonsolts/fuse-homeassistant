"""Tests for the Fuse Energy config flow."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries, data_entry_flow
from homeassistant.core import HomeAssistant

from custom_components.fuse_energy.const import CONF_ACCESS_TOKEN, DOMAIN


@pytest.fixture(name="mock_client")
def mock_client_fixture():
    """Patch the FuseEnergyApiClient used inside the config flow.

    Also patches ``aiohttp_client.async_get_clientsession`` at the config flow's
    namespace so the flow doesn't spin up a real aiohttp/pycares session (which
    would leave a lingering daemon thread and trip the test runner's leak check).
    """
    with patch(
        "custom_components.fuse_energy.config_flow.FuseEnergyApiClient",
        autospec=True,
    ) as mock_cls, patch(
        "custom_components.fuse_energy.config_flow.aiohttp_client.async_get_clientsession"
    ) as mock_session:
        mock_session.return_value = object()
        instance = mock_cls.return_value
        instance.async_get_data = AsyncMock(return_value=None)
        yield instance


async def test_user_flow_happy_path(
    hass: HomeAssistant, auto_enable_custom_integrations, mock_client
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "user"
    assert result["errors"] in (None, {})

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ACCESS_TOKEN: "valid-token"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "Fuse Energy"
    assert result["data"] == {CONF_ACCESS_TOKEN: "valid-token"}


async def test_user_flow_invalid_auth(
    hass: HomeAssistant, auto_enable_custom_integrations, mock_client
) -> None:
    from custom_components.fuse_energy.api import FuseEnergyApiAuthError

    mock_client.async_get_data.side_effect = FuseEnergyApiAuthError("nope")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ACCESS_TOKEN: "bad-token"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_auth"}


async def test_user_flow_cannot_connect(
    hass: HomeAssistant, auto_enable_custom_integrations, mock_client
) -> None:
    from custom_components.fuse_energy.api import FuseEnergyApiError

    mock_client.async_get_data.side_effect = FuseEnergyApiError("boom")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ACCESS_TOKEN: "any-token"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_user_flow_rejects_duplicate_entry(
    hass: HomeAssistant, auto_enable_custom_integrations, mock_client
) -> None:
    """Adding the integration twice should abort with single_instance_allowed."""
    # First entry — succeeds
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ACCESS_TOKEN: "valid-token"},
    )
    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY

    # Second entry — should abort
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_stub_NotImplementedError_does_not_block_setup(
    hass: HomeAssistant, auto_enable_custom_integrations, mock_client
) -> None:
    """While the API is stubbed, NotImplementedError must not prevent entry creation.

    Rationale: until reverse-engineering lands, the API client raises
    NotImplementedError on every call. The config flow treats that as
    'accepted' so users can still add the integration and watch it fail
    visibly via UpdateFailed.
    """
    mock_client.async_get_data.side_effect = NotImplementedError("stub")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        user_input={CONF_ACCESS_TOKEN: "valid-token"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
