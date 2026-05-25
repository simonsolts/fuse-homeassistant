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
