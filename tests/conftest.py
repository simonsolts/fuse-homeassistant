"""Shared test fixtures for the fuse_energy integration."""

from __future__ import annotations

from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


# Path to this project's custom_components/ directory. The hass test
# fixture sets `config_dir` to pytest-homeassistant-custom-component's
# `testing_config/`, which causes the loader to import `custom_components`
# from inside that package (turning it from a namespace package into a
# regular package whose `__path__` no longer includes our project tree).
# We extend `__path__` after hass has mounted things, so the HA loader
# can discover both the framework's stub integrations and ours.
_PROJECT_CUSTOM_COMPONENTS = (
    Path(__file__).resolve().parent.parent / "custom_components"
)


@pytest.fixture
def enable_custom_integrations(enable_custom_integrations):
    """Augment the upstream fixture to expose this project's components.

    Re-uses the upstream `enable_custom_integrations` fixture (which clears
    HA's cached custom-integration list so it re-discovers), then patches
    `custom_components.__path__` to include this project's directory.
    """
    import custom_components

    project_path = str(_PROJECT_CUSTOM_COMPONENTS)
    added = False
    if project_path not in list(custom_components.__path__):
        custom_components.__path__.append(project_path)
        added = True
    try:
        yield
    finally:
        if added:
            try:
                custom_components.__path__.remove(project_path)
            except ValueError:
                pass


@pytest.fixture
def auto_enable_custom_integrations(enable_custom_integrations):
    """Make custom_components/fuse_energy loadable in HA test instances."""
    yield
