# Fuse Energy

Custom Home Assistant integration for Fuse Energy (UK).

**Status:** scaffold only. The API client is a stub that raises a clear error on first refresh. Once the Fuse API is reverse-engineered, the client will be filled in and the integration will report real energy and cost data.

## What you get today
- A UI config flow that accepts an access token.
- Two sensors (energy in kWh, cost in £) wired to the Energy dashboard. Both will appear unavailable until the API is implemented.

## Install
Add this repository as a HACS custom repository, then add the "Fuse Energy" integration via *Settings → Devices & Services*.
