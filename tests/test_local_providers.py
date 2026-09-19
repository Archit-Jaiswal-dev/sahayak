from __future__ import annotations

import pytest

from app.config import settings
from app.providers import get_stt_provider, get_tts_provider


def test_stt_factory_returns_local():
    from app.providers.local_stt import LocalSttProvider

    assert isinstance(get_stt_provider(requested="local"), LocalSttProvider)


def test_stt_factory_rejects_unknown():
    with pytest.raises(ValueError):
        get_stt_provider(requested="nonsense")


def test_local_stt_model_config_default():
    from app.providers.local_stt import LocalSttProvider

    p = LocalSttProvider()
    assert p.model == settings.local_stt_model
    assert p.language == settings.local_stt_language
    assert p.device == settings.local_stt_device


def test_tts_factory_returns_edge():
    from app.providers.edge_tts import EdgeTtsProvider

    assert isinstance(get_tts_provider(requested="edge"), EdgeTtsProvider)


def test_tts_factory_rejects_unknown():
    with pytest.raises(ValueError):
        get_tts_provider(requested="nonsense")
