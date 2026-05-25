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
