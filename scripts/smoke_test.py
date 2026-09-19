"""Smoke-test each provider independently with real credentials.

Usage:
    python -m scripts.smoke_test stt samples/<file>.wav
    python -m scripts.smoke_test tts "नमस्ते, कृपया अपनी शिकायत बताएं।"
    python -m scripts.smoke_test llm

Requires .env to be populated (see .env.example).
"""

from __future__ import annotations

import asyncio
import argparse
import sys
from pathlib import Path

from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.providers.gemini import GeminiProvider  # noqa: E402
from app.providers import get_stt_provider, get_tts_provider  # noqa: E402


class _LLMTarget(BaseModel):
    greeting: str


async def test_stt(path: Path) -> None:
    audio = path.read_bytes()
    stt = get_stt_provider()
    transcript = await stt.transcribe(audio, mime_type="audio/wav")
    print(f"TRANSCRIPT: {transcript}")


async def test_tts(text: str) -> None:
    tts = get_tts_provider()
    audio = await tts.synthesize(text)
    out = Path("samples/tts_output.mp3")
    out.write_bytes(audio)
    print(f"WROTE {len(audio)} bytes -> {out}")


async def test_llm() -> None:
    llm = GeminiProvider()
    result = await llm.complete(
        system_prompt="You are a helper. Respond only in valid JSON matching the schema.",
        history=[{"role": "user", "parts": [{"text": "Say hello in Hindi."}]}],
        response_model=_LLMTarget,
    )
    print(f"LLM: {result.model_dump()}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Smoke-test Sahayak providers")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_stt = sub.add_parser("stt", help="Test speech-to-text (local whisper)")
    p_stt.add_argument("audio", type=Path, help="path to a wav/mp3 Hindi audio sample")

    p_tts = sub.add_parser("tts", help="Test text-to-speech (edge-tts)")
    p_tts.add_argument("text", help="Hindi text to synthesize")

    sub.add_parser("llm", help="Test Gemini structured JSON output")

    args = parser.parse_args()
    if args.cmd == "stt":
        asyncio.run(test_stt(args.audio))
    elif args.cmd == "tts":
        asyncio.run(test_tts(args.text))
    elif args.cmd == "llm":
        asyncio.run(test_llm())


if __name__ == "__main__":
    main()
