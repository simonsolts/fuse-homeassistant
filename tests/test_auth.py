"""Tests for the Fuse Energy auth module."""
from __future__ import annotations

from custom_components.fuse_energy.auth import (
    AdditionalInfoResult,
    AuthorizedResult,
    FuseEnergyAuthError,
    FuseEnergyAuthTransient,
    Question,
    TokenPair,
)


def test_tokenpair_is_frozen_with_expected_fields() -> None:
    t = TokenPair(access_token="a", refresh_token="r")
    assert t.access_token == "a"
    assert t.refresh_token == "r"


def test_question_carries_key_title_type() -> None:
    q = Question(key="DATE_OF_BIRTH", title="Date of birth", type="DATE")
    assert q.key == "DATE_OF_BIRTH"


def test_authorized_result_wraps_tokens() -> None:
    r = AuthorizedResult(tokens=TokenPair("a", "r"))
    assert r.tokens.access_token == "a"


def test_additional_info_result_fields() -> None:
    r = AdditionalInfoResult(
        auth_flow_token="jwt",
        title="Verify your date of birth",
        subtitle="Let's make sure",
        questions=[Question(key="DOB", title="DOB", type="DATE")],
    )
    assert r.auth_flow_token == "jwt"
    assert r.questions[0].key == "DOB"


def test_auth_error_carries_error_code() -> None:
    e = FuseEnergyAuthError("nope", error_code="invalid_code")
    assert e.error_code == "invalid_code"


def test_exception_hierarchy() -> None:
    assert issubclass(FuseEnergyAuthError, Exception)
    assert issubclass(FuseEnergyAuthTransient, Exception)


import pytest
from unittest.mock import AsyncMock, MagicMock, call

import aiohttp

from custom_components.fuse_energy import auth as auth_mod


def _resp(status: int, json_body):
    """Build an aiohttp-style async-context-manager response mock."""
    resp = MagicMock()
    resp.status = status
    resp.json = AsyncMock(return_value=json_body)
    resp.__aenter__ = AsyncMock(return_value=resp)
    resp.__aexit__ = AsyncMock(return_value=False)
    return resp


def _session_with_posts(*responses):
    """A MagicMock(aiohttp.ClientSession) whose .post() returns the given
    responses in order."""
    session = MagicMock(spec=aiohttp.ClientSession)
    session.post = MagicMock(side_effect=list(responses))
    return session


async def test_send_otp_returns_flow_token_from_mobile_initial() -> None:
    mobile_resp = _resp(200, {
        "auth_flow_token": "FLOW_JWT",
        "challenge_type": "PHONE_OTP",
        "data": {"phone_number": "+447777"},
    })
    web_resp = _resp(200, {"result": {"data": {"challenge_type": "PHONE_OTP"}}})
    session = _session_with_posts(mobile_resp, web_resp)

    token = await auth_mod.async_send_otp(
        session, device_id="dev-1", phone_number="+447777",
    )

    assert token == "FLOW_JWT"
    assert session.post.call_count == 2

    # Call 1: mobile INITIAL
    args1, kwargs1 = session.post.call_args_list[0]
    assert args1[0] == "https://api.fuseenergy.com/api/v3/auth"
    assert kwargs1["json"] == {
        "challenge_type": "INITIAL",
        "data": {
            "method": "PHONE",
            "data": {"phone_number": "+447777", "prelude_dispatch_id": None},
        },
    }
    assert kwargs1["headers"]["Device-Id"] == "dev-1"
    assert "Authorization" not in kwargs1["headers"]

    # Call 2: web phoneSignIn
    args2, kwargs2 = session.post.call_args_list[1]
    assert args2[0] == "https://www.fuseenergy.com/api/trpc/phoneSignIn"
    assert kwargs2["json"] == {"phone": "+447777"}
    assert kwargs2["headers"]["x-fuse-app-version"] == "5.314"


async def test_send_otp_raises_on_mobile_initial_4xx() -> None:
    bad = _resp(400, {"status_string": "phone_not_recognised"})
    session = _session_with_posts(bad)
    with pytest.raises(auth_mod.FuseEnergyAuthError) as ei:
        await auth_mod.async_send_otp(session, device_id="d", phone_number="+1")
    assert ei.value.error_code == "phone_not_recognised"


async def test_send_otp_raises_transient_on_5xx() -> None:
    bad = _resp(503, {})
    session = _session_with_posts(bad)
    with pytest.raises(auth_mod.FuseEnergyAuthTransient):
        await auth_mod.async_send_otp(session, device_id="d", phone_number="+1")


async def test_send_otp_raises_transient_on_web_dispatch_failure() -> None:
    mobile_ok = _resp(200, {"auth_flow_token": "FLOW", "challenge_type": "PHONE_OTP"})
    web_bad = _resp(500, {})
    session = _session_with_posts(mobile_ok, web_bad)
    with pytest.raises(auth_mod.FuseEnergyAuthTransient):
        await auth_mod.async_send_otp(session, device_id="d", phone_number="+1")


async def test_verify_otp_returns_authorized_result() -> None:
    resp = _resp(200, {
        "auth_flow_token": "FLOW",
        "challenge_type": "AUTHORIZED",
        "data": {
            "access_token": "AT", "refresh_token": "RT",
            "is_new_user_created": False,
        },
    })
    session = _session_with_posts(resp)

    result = await auth_mod.async_verify_otp(
        session, device_id="d", auth_flow_token="FLOW_IN", code="123456",
    )

    assert isinstance(result, auth_mod.AuthorizedResult)
    assert result.tokens == auth_mod.TokenPair("AT", "RT")

    # Auth carriage MUST be Authorization: Bearer <flow_token>
    args, kwargs = session.post.call_args_list[0]
    assert args[0] == "https://api.fuseenergy.com/api/v3/auth"
    assert kwargs["headers"]["Authorization"] == "Bearer FLOW_IN"
    assert kwargs["headers"]["Device-Id"] == "d"
    assert kwargs["json"] == {
        "challenge_type": "PHONE_OTP",
        "data": {"code": "123456"},
    }


async def test_verify_otp_returns_additional_info_result() -> None:
    resp = _resp(200, {
        "auth_flow_token": "FLOW_NEW",
        "challenge_type": "ADDITIONAL_INFO",
        "data": {
            "title": "Verify your date of birth",
            "subtitle": "Let's make sure this is the right account",
            "questions": [
                {"key": "DATE_OF_BIRTH", "title": "Date of birth", "type": "DATE"},
            ],
        },
    })
    session = _session_with_posts(resp)

    result = await auth_mod.async_verify_otp(
        session, device_id="d", auth_flow_token="FLOW_IN", code="123456",
    )

    assert isinstance(result, auth_mod.AdditionalInfoResult)
    assert result.auth_flow_token == "FLOW_NEW"
    assert result.title == "Verify your date of birth"
    assert result.questions == [
        auth_mod.Question(key="DATE_OF_BIRTH", title="Date of birth", type="DATE"),
    ]


async def test_verify_otp_raises_on_wrong_code() -> None:
    resp = _resp(400, {"status_string": "invalid_code"})
    session = _session_with_posts(resp)
    with pytest.raises(auth_mod.FuseEnergyAuthError) as ei:
        await auth_mod.async_verify_otp(
            session, device_id="d", auth_flow_token="F", code="000000",
        )
    assert ei.value.error_code == "invalid_code"


async def test_verify_otp_raises_transient_on_5xx() -> None:
    resp = _resp(503, {})
    session = _session_with_posts(resp)
    with pytest.raises(auth_mod.FuseEnergyAuthTransient):
        await auth_mod.async_verify_otp(
            session, device_id="d", auth_flow_token="F", code="000000",
        )
