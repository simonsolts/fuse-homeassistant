"""Tests for the dynamic x-fuse-app-version discovery."""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

from custom_components.fuse_energy.version_resolver import (
    AppVersionResolver,
    AppVersionUnavailable,
)


def _mock_response(status: int, text: str) -> MagicMock:
    """Build an aiohttp-style response mock supporting `async with`."""
    resp = MagicMock()
    resp.status = status
    resp.text = AsyncMock(return_value=text)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _session_with_pages(pages: dict[str, tuple[int, str]]) -> MagicMock:
    """Build an aiohttp.ClientSession mock that returns the supplied pages by URL."""
    session = MagicMock()
    def _get(url: str, **_kwargs):
        if url not in pages:
            return _mock_response(404, "")
        status, body = pages[url]
        return _mock_response(status, body)
    session.get = MagicMock(side_effect=_get)
    return session


HOMEPAGE_HTML_TEMPLATE = """
<html><head>
<script src="/_next/static/chunks/abc-111.js"></script>
<script src="/_next/static/chunks/def-222.js"></script>
<script src="/_next/static/chunks/ghi-333.js"></script>
</head></html>
"""


async def test_resolves_version_from_chunk() -> None:
    session = _session_with_pages({
        "https://www.fuseenergy.com/": (200, HOMEPAGE_HTML_TEMPLATE),
        "https://www.fuseenergy.com/_next/static/chunks/abc-111.js": (200, "irrelevant chunk"),
        "https://www.fuseenergy.com/_next/static/chunks/def-222.js": (200, 'foo "x-fuse-app-version":"5.999" bar'),
        "https://www.fuseenergy.com/_next/static/chunks/ghi-333.js": (200, "also irrelevant"),
    })
    resolver = AppVersionResolver(session)

    assert await resolver.async_resolve() == "5.999"


async def test_resolve_caches_after_first_call() -> None:
    session = _session_with_pages({
        "https://www.fuseenergy.com/": (200, HOMEPAGE_HTML_TEMPLATE),
        "https://www.fuseenergy.com/_next/static/chunks/abc-111.js": (200, '"x-fuse-app-version":"5.42"'),
        "https://www.fuseenergy.com/_next/static/chunks/def-222.js": (200, ""),
        "https://www.fuseenergy.com/_next/static/chunks/ghi-333.js": (200, ""),
    })
    resolver = AppVersionResolver(session)

    assert await resolver.async_resolve() == "5.42"
    session.get.reset_mock()
    assert await resolver.async_resolve() == "5.42"
    assert session.get.call_count == 0


async def test_invalidate_forces_refetch() -> None:
    session = _session_with_pages({
        "https://www.fuseenergy.com/": (200, HOMEPAGE_HTML_TEMPLATE),
        "https://www.fuseenergy.com/_next/static/chunks/abc-111.js": (200, '"x-fuse-app-version":"5.1"'),
        "https://www.fuseenergy.com/_next/static/chunks/def-222.js": (200, ""),
        "https://www.fuseenergy.com/_next/static/chunks/ghi-333.js": (200, ""),
    })
    resolver = AppVersionResolver(session)
    await resolver.async_resolve()

    # Next discovery yields a different version
    session.get.side_effect = _session_with_pages({
        "https://www.fuseenergy.com/": (200, HOMEPAGE_HTML_TEMPLATE),
        "https://www.fuseenergy.com/_next/static/chunks/abc-111.js": (200, '"x-fuse-app-version":"5.2"'),
        "https://www.fuseenergy.com/_next/static/chunks/def-222.js": (200, ""),
        "https://www.fuseenergy.com/_next/static/chunks/ghi-333.js": (200, ""),
    }).get.side_effect

    resolver.invalidate()
    assert await resolver.async_resolve() == "5.2"


async def test_raises_when_no_chunk_matches() -> None:
    session = _session_with_pages({
        "https://www.fuseenergy.com/": (200, HOMEPAGE_HTML_TEMPLATE),
        "https://www.fuseenergy.com/_next/static/chunks/abc-111.js": (200, "nothing here"),
        "https://www.fuseenergy.com/_next/static/chunks/def-222.js": (200, "nor here"),
        "https://www.fuseenergy.com/_next/static/chunks/ghi-333.js": (200, "also nope"),
    })
    resolver = AppVersionResolver(session)

    with pytest.raises(AppVersionUnavailable):
        await resolver.async_resolve()


async def test_raises_when_homepage_fails() -> None:
    session = _session_with_pages({
        "https://www.fuseenergy.com/": (503, "")
    })
    resolver = AppVersionResolver(session)

    with pytest.raises(AppVersionUnavailable):
        await resolver.async_resolve()


async def test_chunks_all_failing_raises_with_network_context() -> None:
    """If every chunk fetch raises, the user should see a network-flavored error,
    not the "literal not found" message which implies the JS shape changed."""
    homepage_resp = _mock_response(200, HOMEPAGE_HTML_TEMPLATE)
    session = MagicMock()

    def _get(url: str, **_kwargs):
        if url == "https://www.fuseenergy.com/":
            return homepage_resp
        raise aiohttp.ClientError(f"boom fetching {url}")

    session.get = MagicMock(side_effect=_get)
    resolver = AppVersionResolver(session)

    with pytest.raises(AppVersionUnavailable) as exc_info:
        await resolver.async_resolve()
    assert exc_info.value.__cause__ is not None
    assert isinstance(exc_info.value.__cause__, aiohttp.ClientError)
