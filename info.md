# Fuse Energy

A Home Assistant custom integration for Fuse Energy (UK). Pulls your half-hourly electricity usage and cost into Home Assistant so it can be used in the Energy dashboard.

> ⚠️ **Unofficial and unsupported.** This is a community project. It is not produced, sponsored, endorsed by, or affiliated with Fuse Energy in any way. **Use at your own risk.** No warranty, no support guarantee; if it stops working, breaks your Home Assistant setup, or returns incorrect data, that's on you to deal with.

## Quickstart

Prerequisites: a working Home Assistant install, HACS installed, and a Fuse Energy account.

1. Install **Fuse Energy** via HACS (click **Download** on this page).
2. **Restart Home Assistant.**
3. Go to **Settings → Devices & Services → Add Integration**, search for **Fuse Energy**, and follow the prompts to sign in with your Fuse account.
4. Once configured, add the energy and cost sensors to your **Energy dashboard** (Settings → Dashboards → Energy).

It can take up to an hour after setup for the first usage/cost data to land, since Fuse publishes consumption with a delay.

## Trademarks and disclaimer

"Fuse" and "Fuse Energy" are trademarks of their respective owner (Fuse Energy Ltd). They are referenced here solely to describe what this integration connects to. This project is an independent, unofficial work and is **not affiliated with, authorized, maintained, sponsored, or endorsed by Fuse Energy or any of its affiliates or subsidiaries**. All product and company names are the property of their respective owners.

This software is provided "as is", without warranty of any kind.
