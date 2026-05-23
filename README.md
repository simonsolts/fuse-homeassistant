# fuse-homeassistant

A Home Assistant custom integration for [Fuse Energy](https://www.fuseenergy.com/) (UK).

**Status:** scaffold. The Fuse Energy API has not been reverse-engineered yet. The integration loads, can be configured through the UI, and exposes two sensors — but the sensors are unavailable until the API client is implemented.

## Install

### HACS (preferred)
1. In HACS, open *Integrations → ⋮ → Custom repositories*.
2. Add this repository's URL with category **Integration**.
3. Install "Fuse Energy", then restart Home Assistant.
4. *Settings → Devices & Services → Add Integration → Fuse Energy*.

### Manual
1. Copy `custom_components/fuse_energy/` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. *Settings → Devices & Services → Add Integration → Fuse Energy*.

## Development

This project uses [`uv`](https://docs.astral.sh/uv/) for environment and package management.

```bash
uv venv
uv sync --extra test
uv run pytest
```

The `custom_components/fuse_energy/` directory is the integration. Tests live in `tests/`.

## What's next
Reverse-engineer the Fuse Energy customer API, implement `custom_components/fuse_energy/api.py`, and the sensors will start reporting real data.
