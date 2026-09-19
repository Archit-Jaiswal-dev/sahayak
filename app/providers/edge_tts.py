from __future__ import annotations

import io
import logging

from app.providers import ProviderError, TtsProvider

logger = logging.getLogger(__name__)

# Microsoft neural voices (very human sounding, free, no key needed).
# "Neural" voices are the natural ones; keep a per-language mapping with
# fallbacks so any supported language degrades gracefully.
# All default voices are FEMALE so the assistant always sounds consistent;
# the spoken script also uses feminine self-forms (see prompts.py).
VOICES: dict[str, str] = {
    "hi": "hi-IN-SwaraNeural",  # Swara = natural female; Madhur = male
    "en": "en-IN-NeerjaNeural",
    "bn": "bn-IN-TanishaaNeural",
    "te": "te-IN-ShrutiNeural",
    "ta": "ta-IN-PallaviNeural",
    "mr": "mr-IN-AarohiNeural",
    "gu": "gu-IN-DhwaniNeural",
    "kn": "kn-IN-SapnaNeural",
    "ml": "ml-IN-SobhanaNeural",
    "or": "or-IN-SubhasiniNeural",
    "pa": "pa-IN-CharleenNeural",
    "ur": "ur-PK-UzmaNeural",
    "default": "hi-IN-SwaraNeural",
}


class EdgeTtsProvider(TtsProvider):
    """Microsoft Edge neural TTS (edge-tts).

    Cloud-based and free: no API key, natural multilingual voices, ~1-2s
    latency for short utterances. Output is MP3 (audioplayers auto-detects).
    Requires internet access from the server.

    Set TTS_PROVIDER=edge in .env to use. Falls back to the local Indic-TTS
    engine via TTS_PROVIDER=local if the cloud is unreachable.
    """

    def __init__(self, *, voice: str | None = None, rate: str = "+0%"):
        self._voice_override = voice
        self._rate = rate

    def _voice_for(self, language: str | None) -> str:
        # An explicit language always wins (intro / per-language speech): pick
        # the best neural voice for that language, ignoring the global
        # override which is a single default voice. Without a language, fall
        # back to the configured override, else the default voice.
        if language:
            lang = language.strip().lower().split("-")[0]
            return VOICES.get(lang, VOICES["default"])
        if self._voice_override:
            return self._voice_override
        return VOICES["default"]

    async def _available_voices_async(self) -> set[str]:
        import edge_tts

        try:
            voices = await edge_tts.list_voices()
            return {v["ShortName"] for v in voices}
        except Exception:
            return set()

    async def synthesize(self, text: str, language: str | None = None) -> bytes:
        import edge_tts

        voice = self._voice_for(language)
        # Prefer a voice actually present in this edge-tts deployment. An
        # explicit-language request that maps to a missing voice falls back to
        # the default voice instead of erroring (e.g. pa on old deployments).
        available = await self._available_voices_async()
        if available and voice not in available:
            if language:
                logger.warning(
                    "Voice %s unavailable for language %s; falling back to default",
                    voice, language,
                )
            voice = VOICES["default"]

        try:
            buf = io.BytesIO()
            comm = edge_tts.Communicate(text, voice, rate=self._rate)
            async for chunk in comm.stream():
                if chunk["type"] == "audio":
                    buf.write(chunk["data"])
        except Exception as e:
            raise ProviderError(f"Edge TTS failed: {e}") from e
        if not buf.getvalue():
            raise ProviderError("Edge TTS returned no audio.")
        return buf.getvalue()

    async def aclose(self) -> None:
        pass