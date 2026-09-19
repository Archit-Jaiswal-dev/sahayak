from __future__ import annotations

import json
import logging

from google import genai
from google.genai import types

from app.config import settings
from app.providers import LLMProvider, ProviderError

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Gemini chat with native JSON schema enforcement.

    The model is forced to produce output matching the caller's Pydantic
    `response_model` (response_mime_type=application/json + response_schema),
    so downstream code never parses free text.
    """

    def __init__(
        self,
        *,
        api_key: str = settings.gemini_api_key,
        model: str = settings.gemini_model,
    ):
        if not api_key:
            raise ProviderError(
                "Gemini API key not configured. Set GEMINI_API_KEY in .env "
                "(get one at https://aistudio.google.com/apikey)."
            )
        self._client = genai.Client(api_key=api_key)
        self._model = model

    async def complete(
        self,
        *,
        system_prompt: str,
        history: list[dict],
        response_model: type,
    ):
        contents = [types.Content(role=r["role"], parts=[types.Part(text=r["parts"][0]["text"])]) for r in history]
        if not contents:
            contents = [
                types.Content(
                    role="user",
                    parts=[types.Part(text="Citizen is ready. Begin the conversation.")],
                )
            ]
        config = types.GenerateContentConfig(
            system_instruction=system_prompt,
            response_mime_type="application/json",
            response_schema=response_model,
            temperature=0.1,
        )
        try:
            response = await self._call_with_retry(contents, config)
        except Exception as e:
            raise ProviderError(f"Gemini call failed: {e}") from e

        if response.parsed is not None:
            return response.parsed
        text = response.text
        if not text:
            raise ProviderError("Gemini returned empty response.")
        try:
            return response_model.model_validate(json.loads(text))
        except (ValueError, json.JSONDecodeError) as e:
            raise ProviderError(f"Gemini returned invalid JSON: {text[:500]}") from e

    async def _call_with_retry(self, contents: list, config: types.GenerateContentConfig):
        """Retry transient server errors (429 rate-limit, 503 high-demand are
        common on the free tier) with backoff. Config errors (400/404) fail
        immediately."""
        import asyncio
        import re

        from google.genai.errors import ClientError

        last_error: Exception | None = None
        for attempt in range(6):
            try:
                return await self._client.aio.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
            except ClientError as e:
                status = getattr(e, "status_code", None)
                if status not in (429, 500, 502, 503, 504):
                    raise
                last_error = e
                # Honor the server's suggested retry delay when present.
                delay = _retry_delay(e) or min(2**attempt, 30)
                logger.warning(
                    "Gemini transient error %s (attempt %d/6), backing off %.1fs",
                    status, attempt + 1, delay,
                )
            except Exception as e:
                last_error = e
                logger.warning(
                    "Gemini call error (attempt %d/6): %s", attempt + 1, e
                )
                delay = min(2**attempt, 30)
            await asyncio.sleep(delay)
        raise ProviderError(f"Gemini call failed after retries: {last_error}") from last_error


def _retry_delay(error: Exception) -> float | None:
    """Parse Google's 'Please retry in N.NNNNNNNNs.' from the 429 message."""
    import re

    msg = str(error)
    m = re.search(r"Please retry in ([0-9.]+)s", msg)
    if m:
        return float(m.group(1)) + 1.0
    return None
