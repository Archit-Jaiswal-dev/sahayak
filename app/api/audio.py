from __future__ import annotations

import base64

from fastapi import APIRouter, HTTPException, Request, UploadFile

from app.providers import ProviderError
from pydantic import BaseModel

router = APIRouter(prefix="/v1/audio", tags=["audio"])


class TTSRequest(BaseModel):
    text: str
    language: str | None = None


class TTSResponse(BaseModel):
    audio: str  # base64
    mime_type: str


class STTResponse(BaseModel):
    transcript: str


def _providers(request: Request):
    """Lazily constructed STT/TTS provider singletons.

    STT = local faster-whisper; TTS = edge-tts. Both cached on app.state.
    """
    if getattr(request.app.state, "stt_provider", None) is None:
        from app.providers import get_stt_provider

        request.app.state.stt_provider = get_stt_provider()
    if getattr(request.app.state, "tts_provider", None) is None:
        from app.providers import get_tts_provider

        request.app.state.tts_provider = get_tts_provider()
    return request.app.state


@router.post("/tts", response_model=TTSResponse)
async def tts(body: TTSRequest, request: Request) -> TTSResponse:
    try:
        audio = await _providers(request).tts_provider.synthesize(
            body.text, language=body.language
        )
    except ProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    # edge-tts returns MP3; the local Indic-TTS engine returns WAV.
    provider = _providers(request).tts_provider
    mime = "audio/wav"
    if provider.__class__.__name__.lower().startswith("edge"):
        mime = "audio/mpeg"
    return TTSResponse(
        audio=base64.b64encode(audio).decode(),
        mime_type=mime,
    )


@router.post("/stt", response_model=STTResponse)
async def stt(file: UploadFile, request: Request, language: str | None = None) -> STTResponse:
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file")
    try:
        transcript = await _providers(request).stt_provider.transcribe(
            audio_bytes, mime_type=file.content_type or "audio/wav", language=language
        )
    except ProviderError as e:
        raise HTTPException(status_code=503, detail=str(e))
    return STTResponse(transcript=transcript)
