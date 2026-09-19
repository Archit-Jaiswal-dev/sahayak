from __future__ import annotations

from abc import ABC, abstractmethod

import httpx

from app.config import settings


def get_stt_provider(*, requested: str | None = None):
    """Construct the STT provider (local faster-whisper only)."""
    choice = (requested or settings.stt_provider or "local").lower()
    if choice == "local":
        from app.providers.local_stt import LocalSttProvider

        return LocalSttProvider()
    raise ValueError(f"Unknown STT_PROVIDER {choice!r}. Only 'local' is supported.")


def get_tts_provider(*, requested: str | None = None):
    """Construct the TTS provider (edge-tts only)."""
    choice = (requested or settings.tts_provider or "edge").lower()
    if choice == "edge":
        from app.providers.edge_tts import EdgeTtsProvider

        return EdgeTtsProvider(voice=settings.edge_tts_voice or None)
    raise ValueError(f"Unknown TTS_PROVIDER {choice!r}. Only 'edge' is supported.")


class SttProvider(ABC):
    """Transcribes spoken audio into text in the target language."""

    @abstractmethod
    async def transcribe(
        self, audio_bytes: bytes, mime_type: str, language: str | None = None
    ) -> str:
        """Return the transcript. `audio_bytes` is the raw recording.
        `language` is an optional ISO code override (e.g. 'hi', 'en')."""


class TtsProvider(ABC):
    """Synthesizes speech from text in the target language."""

    @abstractmethod
    async def synthesize(self, text: str, language: str | None = None) -> bytes:
        """Return the synthesized audio bytes (wav/mp3)."""


class LLMProvider(ABC):
    """Structured LLM interface. Always returns validated Pydantic models."""

    @abstractmethod
    async def complete(
        self,
        *,
        system_prompt: str,
        history: list[dict],
        response_model: type,
    ):
        """Chat completion constrained to `response_model`'s JSON schema.

        `history` is a list of {"role": "user"|"model", "parts": [{"text": ...}]}.
        Returns an instance of `response_model` (never free text).
        """


class ProviderError(RuntimeError):
    """Raised when a provider call fails (network, auth, bad payload)."""


def get_llm_provider(*, requested: str | None = None):
    """Construct the LLM provider (Gemini only)."""
    from app.providers.gemini import GeminiProvider
    return GeminiProvider()


async def _request(
    client: httpx.AsyncClient,
    *,
    url: str,
    headers: dict,
    payload: dict,
) -> dict:
    try:
        resp = await client.post(url, json=payload, headers=headers, timeout=60.0)
    except httpx.HTTPError as e:
        raise ProviderError(f"provider request failed: {e}") from e
    if resp.status_code != 200:
        raise ProviderError(
            f"provider returned HTTP {resp.status_code}: {resp.text[:500]}"
        )
    try:
        return resp.json()
    except ValueError as e:
        raise ProviderError(f"provider returned non-JSON body: {resp.text[:500]}") from e
