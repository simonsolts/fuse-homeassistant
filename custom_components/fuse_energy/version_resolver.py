"""Discover the live x-fuse-app-version by scraping the Fuse JS bundle.

Fuse's tRPC server rejects every authenticated call whose
``x-fuse-app-version`` header doesn't match the currently-deployed UI
version (returns HTTP 500 with ``____reloadRequired: true``). This
module fetches the public homepage, gathers all ``_next/static/chunks``
script URLs, and greps them for the literal ``"x-fuse-app-version":"…"``
that the tRPC client config inlines. First match wins.
"""
from __future__ import annotations

import asyncio
import re
from typing import Final

import aiohttp

from .const import FUSE_BASE_URL

_SCRIPT_SRC_RE: Final = re.compile(
    r'<script[^>]+src="(/_next/static/chunks/[^"]+\.js)"'
)
_VERSION_RE: Final = re.compile(r'"x-fuse-app-version":"([^"]+)"')


class AppVersionUnavailable(RuntimeError):
    """Could not discover the live x-fuse-app-version value."""


class AppVersionResolver:
    """Cached discoverer of x-fuse-app-version.

    Thread-safety: not safe for concurrent calls into the same instance.
    The coordinator only ever calls this from the HA event loop, so this
    is fine.
    """

    def __init__(self, session: aiohttp.ClientSession) -> None:
        self._session = session
        self._cached: str | None = None

    def invalidate(self) -> None:
        """Drop the cached value; next resolve() will refetch."""
        self._cached = None

    async def async_resolve(self) -> str:
        """Return the cached version, fetching it first if needed."""
        if self._cached is not None:
            return self._cached
        self._cached = await self._discover()
        return self._cached

    async def _discover(self) -> str:
        chunk_paths = await self._fetch_chunk_paths()
        if not chunk_paths:
            raise AppVersionUnavailable("no script chunks found on homepage")

        async def _grep(path: str) -> str | None:
            async with self._session.get(f"{FUSE_BASE_URL}{path}") as resp:
                if resp.status != 200:
                    return None
                body = await resp.text()
            match = _VERSION_RE.search(body)
            return match.group(1) if match else None

        results = await asyncio.gather(
            *(_grep(p) for p in chunk_paths), return_exceptions=True
        )
        for result in results:
            if isinstance(result, str):
                return result
        exceptions = [r for r in results if isinstance(r, Exception)]
        if exceptions:
            raise AppVersionUnavailable(
                "failed to fetch one or more JS chunks while discovering version"
            ) from exceptions[0]
        raise AppVersionUnavailable(
            "x-fuse-app-version literal not found in any loaded chunk"
        )

    async def _fetch_chunk_paths(self) -> list[str]:
        async with self._session.get(f"{FUSE_BASE_URL}/") as resp:
            if resp.status != 200:
                raise AppVersionUnavailable(
                    f"homepage returned {resp.status} while discovering version"
                )
            html = await resp.text()
        return _SCRIPT_SRC_RE.findall(html)
