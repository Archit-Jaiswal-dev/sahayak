from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.audio import router as audio_router
from app.api.cpgrams import router as cpgrams_router
from app.api.filing import router as filing_router
from app.api.sessions import router as sessions_router
from app.api.watchdog import router as watchdog_router
from app.providers import ProviderError, get_stt_provider
from app.services.conversation import ConversationService
from app.watchdog.service import WatchdogService


def _warm_stt(app: FastAPI):
    """Force the lazy whisper model to load so the first real user utterance
    is transcribed immediately instead of waiting ~30s for model load."""
    provider = getattr(app.state, "stt_provider", None)
    if provider is not None and hasattr(provider, "warmup"):
        try:
            provider.warmup()
        except ProviderError:
            pass


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Lazy: the API boots even without credentials; endpoints surface a clear
    # 503 until the relevant key is configured.
    app.state.conversation = None
    app.state.stt_provider = None  # lazy; created on first STT/TTS call
    app.state.tts_provider = None
    app.state.watchdog = WatchdogService()
    try:
        from app.providers.gemini import GeminiProvider
        app.state.conversation = ConversationService(GeminiProvider())
    except ProviderError:
        pass
    # Preload the STT model so the first user utterance doesn't pay a ~30s
    # lazy-load penalty ("Transcribing…" hangs). Delayed slightly so the API
    # reports healthy quickly; load happens in the background.
    app.state.stt_provider = get_stt_provider()
    import asyncio
    await asyncio.to_thread(_warm_stt, app)
    yield


app = FastAPI(
    title="Sahayak API",
    version="0.1.0",
    description="Voice-first grievance drafting assistant (Hindi). "
    "Stage A: conversation loop, STT/TTS bridge, RPA filing bridge.",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for production
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sessions_router)
app.include_router(audio_router)
app.include_router(filing_router)
app.include_router(cpgrams_router)
app.include_router(watchdog_router)


@app.get("/")
async def root():
    return {"service": "sahayak-api", "status": "ok"}


@app.get("/health")
async def health():
    return {"status": "ok"}
