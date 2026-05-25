"""Phone-OTP auth state machine for the Fuse Energy mobile API.

Stateless functions. Callers pass what's needed and persist what comes back.
The module does NOT touch HA's config entry store — that's the config flow's
and coordinator's job.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Union


class FuseEnergyAuthError(Exception):
    """Authentication failed in a way the user must act on (wrong code,
    expired token, additional-info mismatch, refresh revoked)."""

    def __init__(self, message: str, *, error_code: str = "unknown") -> None:
        super().__init__(message)
        self.error_code = error_code


class FuseEnergyAuthTransient(Exception):
    """5xx, network, or other recoverable failures — caller can retry."""


@dataclass(frozen=True, slots=True)
class TokenPair:
    access_token: str
    refresh_token: str


@dataclass(frozen=True, slots=True)
class Question:
    key: str    # e.g. "DATE_OF_BIRTH"
    title: str  # display label served by Fuse
    type: str   # "DATE" | "TEXT" (server-defined; treat unknowns as TEXT)


@dataclass(frozen=True, slots=True)
class AuthorizedResult:
    tokens: TokenPair


@dataclass(frozen=True, slots=True)
class AdditionalInfoResult:
    auth_flow_token: str
    title: str
    subtitle: str
    questions: list[Question]


AuthStepResult = Union[AuthorizedResult, AdditionalInfoResult]


import aiohttp

from .const import FUSE_API_BASE_URL, FUSE_WEB_BASE_URL, FUSE_WEB_APP_VERSION


_TIMEOUT = aiohttp.ClientTimeout(total=15)


async def _post_mobile_auth(
    session: aiohttp.ClientSession,
    body: dict,
    *,
    device_id: str,
    bearer: str | None = None,
) -> dict:
    """POST to api.fuseenergy.com/api/v3/auth. Returns the parsed JSON body
    on 2xx; raises FuseEnergyAuthError on 4xx, FuseEnergyAuthTransient on
    5xx / network."""
    headers = {"Content-Type": "application/json", "Device-Id": device_id}
    if bearer is not None:
        headers["Authorization"] = f"Bearer {bearer}"
    try:
        async with session.post(
            f"{FUSE_API_BASE_URL}/api/v3/auth",
            json=body, headers=headers, timeout=_TIMEOUT,
        ) as r:
            payload = await r.json()
            if 200 <= r.status < 300:
                return payload
            if 500 <= r.status:
                raise FuseEnergyAuthTransient(
                    f"server {r.status} from /api/v3/auth: {payload}"
                )
            code = (payload or {}).get("status_string", "unknown")
            raise FuseEnergyAuthError(
                f"HTTP {r.status}: {payload}", error_code=code,
            )
    except aiohttp.ClientError as e:
        raise FuseEnergyAuthTransient(f"network: {e}") from e


async def async_send_otp(
    session: aiohttp.ClientSession, *, device_id: str, phone_number: str,
) -> str:
    """Two API calls:

    1) POST api.fuseenergy.com/api/v3/auth INITIAL phone — returns the
       auth_flow_token JWT we need for the verify step. Does NOT dispatch
       SMS on its own.
    2) POST www.fuseenergy.com/api/trpc/phoneSignIn — triggers the SMS
       dispatch.

    Returns the auth_flow_token from step 1 for use in async_verify_otp.
    Raises FuseEnergyAuthError on 4xx (with error_code), FuseEnergyAuthTransient
    on 5xx / network.
    """
    # 1) Mobile INITIAL
    mobile = await _post_mobile_auth(
        session,
        {
            "challenge_type": "INITIAL",
            "data": {
                "method": "PHONE",
                "data": {"phone_number": phone_number, "prelude_dispatch_id": None},
            },
        },
        device_id=device_id,
    )
    flow_token = mobile.get("auth_flow_token")
    if not flow_token:
        raise FuseEnergyAuthError(
            "mobile INITIAL returned no auth_flow_token",
            error_code="bad_response",
        )

    # 2) Web phoneSignIn (server-side SMS dispatch)
    headers = {
        "Content-Type": "application/json",
        "x-fuse-app-version": FUSE_WEB_APP_VERSION,
    }
    try:
        async with session.post(
            f"{FUSE_WEB_BASE_URL}/api/trpc/phoneSignIn",
            json={"phone": phone_number}, headers=headers, timeout=_TIMEOUT,
        ) as r:
            if 200 <= r.status < 300:
                return flow_token
            if 500 <= r.status:
                raise FuseEnergyAuthTransient(
                    f"web phoneSignIn returned {r.status}"
                )
            payload = await r.json()
            code = (payload or {}).get("error", {}).get("code") or "dispatch_failed"
            raise FuseEnergyAuthError(
                f"web phoneSignIn rejected: {payload}", error_code=str(code),
            )
    except aiohttp.ClientError as e:
        raise FuseEnergyAuthTransient(f"network: {e}") from e
