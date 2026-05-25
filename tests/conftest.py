"""Shared test fixtures for the fuse_energy integration."""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


def _install_broken_module_stubs() -> None:
    """Pre-populate sys.modules with minimal stubs for submodules that are
    temporarily broken during the incremental reauth refactor.

    __init__.py was repaired in Task 12; api.py in Task 7-9.  config_flow.py
    and version_resolver.py still reference old constants and are repaired in
    Tasks 13-18.  We always stub the still-broken submodules so that HA's
    integration loader (which calls importlib.import_module directly) never
    encounters an ImportError while loading them.

    The real submodules (auth, const, coordinator, sensor, …) are NOT stubbed
    so they load from source as normal.
    """
    _PKG = "custom_components.fuse_energy"

    # Ensure the package namespace exists in sys.modules so that relative
    # submodule imports resolve correctly.
    if _PKG not in sys.modules:
        try:
            __import__(_PKG)
        except ImportError:
            # Package init is still broken — create a minimal namespace stub.
            pkg_stub = types.ModuleType(_PKG)
            pkg_stub.__path__ = [  # type: ignore[attr-defined]
                str(Path(__file__).resolve().parent.parent / "custom_components" / "fuse_energy")
            ]
            pkg_stub.__package__ = _PKG
            sys.modules[_PKG] = pkg_stub

            import custom_components as _cc_pkg  # noqa: PLC0415
            if not hasattr(_cc_pkg, "fuse_energy"):
                _cc_pkg.fuse_energy = pkg_stub  # type: ignore[attr-defined]

    # Stub out the currently-broken submodules so that any import attempt
    # (including from an executor thread via HA's loader) returns a no-op
    # module rather than an ImportError.

    for submod in ("version_resolver",):
        fq = f"{_PKG}.{submod}"
        if fq not in sys.modules:
            stub = types.ModuleType(fq)
            stub.__package__ = _PKG
            sys.modules[fq] = stub


_install_broken_module_stubs()


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
def enable_custom_integrations(enable_custom_integrations):  # noqa: PT004
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
