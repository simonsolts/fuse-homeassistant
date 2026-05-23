"""Shared test fixtures for the fuse_energy integration."""
from __future__ import annotations

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/fuse_energy loadable in HA test instances."""
    yield
