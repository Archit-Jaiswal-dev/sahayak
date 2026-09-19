from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from pathlib import Path


class HumanVerifier(ABC):
    """The only human steps in RPA filing: CAPTCHA and OTP.

    These cannot (and must not) be automated — they belong to the citizen.
    Implementations adapt to the client: terminal prompt, API round-trip
    (web/mobile), etc.
    """

    @abstractmethod
    async def solve_captcha(self, image_bytes: bytes) -> str:
        """Return the characters shown in the CAPTCHA image."""

    @abstractmethod
    async def provide_otp(self, hint: str) -> str:
        """Return the OTP the citizen received (sent to their phone)."""


class CliHumanVerifier(HumanVerifier):
    """Terminal-based verifier for script usage.

    Saves the CAPTCHA image to /tmp so the user can open and read it.
    """

    def __init__(self, out_dir: Path | None = None):
        self._out = out_dir or Path("/tmp")
        self._captcha_counter = 0

    async def solve_captcha(self, image_bytes: bytes) -> str:
        self._captcha_counter += 1
        path = (self._out / f"sahayak_captcha_{self._captcha_counter}.png").resolve()
        path.write_bytes(image_bytes)
        await asyncio.to_thread(print, f"[human] OPEN THIS CAPTCHA IMAGE: {path}")
        while True:
            value = await asyncio.to_thread(
                input, "[human] Enter the CAPTCHA characters: "
            )
            if value.strip():
                return value.strip()

    async def provide_otp(self, hint: str) -> str:
        while True:
            value = await asyncio.to_thread(input, f"[human] {hint}: ")
            if value.strip():
                return value.strip()