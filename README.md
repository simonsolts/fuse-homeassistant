# fuse-homeassistant

A Home Assistant custom integration for [Fuse Energy](https://www.fuseenergy.com/) (UK). Pulls your half-hourly electricity usage and cost into Home Assistant so it can be used in the Energy dashboard.

> ⚠️ **Unofficial and unsupported.** This is a community project. It is not produced, sponsored, endorsed by, or affiliated with Fuse Energy in any way. It talks to Fuse's customer API the same way the official Fuse app does — that API is undocumented and may change or break at any time without notice. **Use at your own risk.** No warranty, no support guarantee; if it stops working, breaks your Home Assistant setup, or returns incorrect data, that's on you to deal with.

## Quickstart (HACS)

Prerequisites: a working Home Assistant install, [HACS](https://hacs.xyz/) installed, and a Fuse Energy account.

1. In Home Assistant, open **HACS → ⋮ (top right) → Custom repositories**.
2. Add `https://github.com/simon-solts/fuse-homeassistant` as a **Integration** repository.
3. Find **Fuse Energy** in the HACS integration list and click **Download**.
4. **Restart Home Assistant.**
5. Go to **Settings → Devices & Services → Add Integration**, search for **Fuse Energy**, and follow the prompts to sign in with your Fuse account.
6. Once configured, the integration creates energy and cost sensors that you can add to the **Energy dashboard** (Settings → Dashboards → Energy).

It can take up to an hour after setup for the first usage/cost data to land, since Fuse publishes consumption with a delay.

### Manual install (alternative)

1. Copy `custom_components/fuse_energy/` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Fuse Energy.**

## Development

This project uses [`uv`](https://docs.astral.sh/uv/) for environment and package management.

```bash
uv venv
uv sync --extra test
uv run pytest
```

The `custom_components/fuse_energy/` directory is the integration. Tests live in `tests/`.

## Trademarks and disclaimer

"Fuse" and "Fuse Energy" are trademarks of their respective owner (Fuse Energy Ltd). They are referenced here solely to describe what this integration connects to. This project is an independent, unofficial work by a Fuse customer and is **not affiliated with, authorized, maintained, sponsored, or endorsed by Fuse Energy or any of its affiliates or subsidiaries**. All product and company names are the property of their respective owners.

This software is provided "as is", without warranty of any kind. See [LICENSE](LICENSE) for full terms.
