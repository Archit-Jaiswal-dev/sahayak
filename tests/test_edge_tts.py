"""Tests for the Edge TTS voice selection (app/providers/edge_tts.py)."""

import pytest

from app.providers.edge_tts import EdgeTtsProvider, VOICES


def test_explicit_language_picks_language_voice():
    """An explicit language must win over any global voice override."""
    provider = EdgeTtsProvider(voice="hi-IN-SwaraNeural")
    assert provider._voice_for("hi") == VOICES["hi"]
    assert provider._voice_for("bn") == VOICES["bn"]
    assert provider._voice_for("te") == VOICES["te"]
    assert provider._voice_for("mr") == VOICES["mr"]


def test_unknown_language_falls_back_to_default():
    provider = EdgeTtsProvider()
    assert provider._voice_for("zz") == VOICES["default"]


def test_language_prefix_ignores_region_suffix():
    provider = EdgeTtsProvider()
    assert provider._voice_for("en-IN") == VOICES["en"]


def test_no_language_uses_override_then_default():
    override = EdgeTtsProvider(voice="hi-IN-SwaraNeural")
    assert override._voice_for(None) == "hi-IN-SwaraNeural"

    plain = EdgeTtsProvider()
    assert plain._voice_for(None) == VOICES["default"]


@pytest.mark.asyncio
async def test_missing_voice_falls_back_to_default(monkeypatch):
    """A mapped voice absent from the deployment must degrade to the default
    voice instead of failing synthesis."""
    provider = EdgeTtsProvider()

    async def fake_available() -> set[str]:
        return {"hi-IN-MadhurNeural", "en-IN-PrabhatNeural"}

    monkeypatch.setattr(provider, "_available_voices_async", fake_available)
    # 'pa' maps to pa-IN-CharleenNeural which is NOT in the fake deployment.
    assert provider._voice_for("pa") == VOICES["pa"]

    import io

    calls: list[str] = []

    class FakeCommunicate:
        def __init__(self, text, voice, rate):
            calls.append(voice)

        async def stream(self):
            buf = io.BytesIO(b"fake-audio")
            yield {"type": "audio", "data": buf.getvalue()}

    import edge_tts

    monkeypatch.setattr(edge_tts, "Communicate", FakeCommunicate)
    audio = await provider.synthesize("test", language="pa")
    assert audio == b"fake-audio"
    assert calls == [VOICES["default"]]