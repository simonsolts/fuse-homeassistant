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


def test_const_exposes_new_config_keys_and_stat_templates() -> None:
    import importlib.util
    from pathlib import Path

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

    assert const.STAT_ID_CONSUMPTION_TEMPLATE == "fuse_energy:elec_consumption_{premises_fid}"
    assert const.STAT_ID_COST_TEMPLATE == "fuse_energy:elec_cost_{premises_fid}"

    assert isinstance(const.FALLBACK_APP_VERSION, str) and const.FALLBACK_APP_VERSION
