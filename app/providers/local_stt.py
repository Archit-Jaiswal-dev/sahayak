from __future__ import annotations

import asyncio
import io
import logging
import os
import wave
from dataclasses import dataclass, field

from app.config import settings
from app.providers import ProviderError, SttProvider

logger = logging.getLogger(__name__)

MODEL_SIZES = ("tiny", "base", "small", "medium", "large-v3", "large-v3-turbo", "distil-large-v3", "distil-medium.en", "distil-small.en")


def _site_packages() -> str:
    import sysconfig

    return sysconfig.get_paths().get("purelib") or sysconfig.get_paths().get("platlib")


@dataclass
class LocalSttProvider(SttProvider):
    """Speech-to-text with faster-whisper (OpenAI Whisper weights on CTranslate2).

    - Best model: ``large-v3-turbo`` by default (pruned large-v3: ~same accuracy,
      ~8x faster, fits a 4GB GPU).
    - Auto device: CUDA float16 when a usable GPU exists, else CPU int8.
    - Model is downloaded only on first use; LazyWhisperModel defers the heavy
      load until the first ``transcribe`` call.
    - Returns Devanagari-script text when the source language is Hindi.
    """

    model: str = field(default_factory=lambda: settings.local_stt_model)
    language: str = field(default_factory=lambda: settings.local_stt_language)
    compute_type: str = field(default_factory=lambda: settings.local_stt_compute_type)
    device: str = field(default_factory=lambda: settings.local_stt_device)
    cpu_threads: int = field(default_factory=lambda: settings.local_stt_cpu_threads)

    def __post_init__(self):
        if self.model not in MODEL_SIZES:
            raise ProviderError(f"Unsupported STT model {self.model!r}. Pick one of {MODEL_SIZES}")

    @property
    def _whisper_model(self):
        if getattr(self, "_model_obj", None) is None:
            self._model_obj = LazyWhisperModel(
                model=self.model,
                device=self.device,
                compute_type=self.compute_type,
                cpu_threads=self.cpu_threads,
            )
        return self._model_obj

    def warmup(self) -> None:
        """Load the whisper model eagerly (no audio) so the first STT call
        skips the lazy ~30s load. Uses the public _ensure path."""
        self._whisper_model._ensure()

    async def transcribe(self, audio_bytes: bytes, mime_type: str, language: str | None = None) -> str:
        lang = (language or self.language or "").strip().lower()
        try:
            return await self._whisper_model.transcribe(
                audio_bytes, language=lang or None
            )
        except ProviderError:
            raise
        except Exception as e:
            raise ProviderError(f"Local STT failed: {e}") from e


class _AudioInput:
    """Normalize any in-memory audio to 16 kHz mono float32 using PyAV
    (already a faster-whisper dependency; no scipy/soundfile needed)."""

    @staticmethod
    def to_pcm(audio_bytes: bytes, mime_type_hint: str) -> tuple[object, int]:
        import numpy as np

        try:
            import av
        except ImportError:
            # Generic fallback for callers who hand us raw 16-bit PCM already.
            data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
            return data, 16000

        try:
            container = av.open(io.BytesIO(audio_bytes))
        except av.error.InvalidDataError as e:
            # Some recorders (Android `record` package stream mode) emit raw
            # 16-bit PCM with no container. Detect it and treat as raw PCM.
            if _looks_like_raw_pcm(audio_bytes):
                return _raw_pcm(audio_bytes, 16000)
            raise ProviderError(
                f"Could not decode audio ({mime_type_hint!r}): {e}"
            ) from e
        try:
            stream = container.streams.audio[0]
        except (IndexError, KeyError):
            raise ProviderError("No audio stream found in the file.") from None

        # Gather raw audio frames, resample to 16 kHz mono in AV.
        resampler = av.AudioResampler(format="fltp", layout="mono", rate=16000)
        frames: list[av.AudioFrame] = []
        for frame in container.decode(stream):
            for out in resampler.resample(frame):
                frames.append(out)
        flushed = resampler.resample(None)
        if flushed:
            frames.extend(flushed)
        container.close()

        if not frames:
            raise ProviderError("Decoded audio contained no frames.")
        blocks: list[np.ndarray] = []
        for frame in frames:
            arr = np.asarray(frame.to_ndarray(), dtype=np.float32)
            if arr.ndim > 1:
                arr = arr.reshape(-1)
            if arr.size:
                blocks.append(arr)
        if not blocks:
            raise ProviderError("Decoded audio contained no frames.")
        data = np.concatenate(blocks)
        return np.asarray(data, dtype=np.float32).reshape(-1), 16000


class LazyWhisperModel:
    """Magnitude of the load (large-v3-turbo ≈ 1.6 GB) is only paid on first
    inference. Constructed by the provider object; the API boots instantly."""

    def __init__(self, *, model: str, device: str, compute_type: str, cpu_threads: int):
        self._model = model
        self._device = device
        self._compute_type = compute_type
        self._cpu_threads = cpu_threads
        self._backend = None

    @staticmethod
    def _add_cuda_runtime_paths():
        """ctranslate2 dynamically loads libcublas/libcudnn via dlopen, and the
        dynamic linker reads LD_LIBRARY_PATH only at process start. So when these
        libs come from pip wheels (nvidia-cublas-cu12 / nvidia-cudnn-cu12) we must
        preload them with ctypes so CUDA inference works without env vars."""
        import ctypes
        import glob

        site = _site_packages()
        candidates = []
        for pkg in ("cublas", "cudnn"):
            for d in ("lib", ""):
                candidates.append(os.path.join(site, "nvidia", pkg, d))
        loaded = False
        for cdir in candidates:
            for soname in ("libcublas.so*", "libcudnn.so*"):
                for lib in sorted(glob.glob(os.path.join(cdir, soname))):
                    try:
                        ctypes.CDLL(lib, mode=ctypes.RTLD_GLOBAL)
                        loaded = True
                    except OSError:
                        continue
        if loaded:
            logger.info("Preloaded CUDA runtime libraries for ctranslate2.")

    def _ensure(self):
        if self._backend is not None:
            return
        try:
            self._add_cuda_runtime_paths()
            from faster_whisper import WhisperModel
        except ImportError as e:
            raise ProviderError(
                "faster-whisper is not installed. Run: pip install faster-whisper"
            ) from e

        device, compute = self._resolve_device()
        logger.info("Whisper on %s (%s) model=%s", device, compute, self._model)
        self._backend = WhisperModel(
            self._model,
            device=device,
            compute_type=compute,
            cpu_threads=self._cpu_threads,
        )

    def _resolve_device(self) -> tuple[str, str]:
        import ctranslate2

        # Explicit device in config wins.
        dev = (self._device or "").lower()
        if dev in ("gpu",):
            return "cuda", self._compute_type or "float16"
        if dev == "cuda":
            if ctranslate2.get_cuda_device_count() == 0:
                logger.warning("CUDA requested but no GPU found; falling back to CPU.")
                return "cpu", self._compute_type or "int8"
            return "cuda", self._compute_type or "float16"
        if dev == "cpu":
            return "cpu", self._compute_type or "int8"
        if dev and dev != "auto":
            raise ProviderError(f"Unsupported STT device {dev!r}. Use auto|cpu|cuda.")

        # auto: probe sensible default
        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda", self._compute_type or "float16"
        return "cpu", self._compute_type or "int8"

    async def transcribe(self, audio_bytes: bytes, language: str) -> str:
        await asyncio.to_thread(self._ensure)

        # Normalize to 16k mono PCM (done in-process; faster-whisper takes
        # either raw float samples or a wav file path).
        data, _ = _AudioInput.to_pcm(audio_bytes, "audio/wav")
        segments, info = await asyncio.to_thread(
            self._backend.transcribe,
            data,
            language=language or None,
            vad_filter=True,
            beam_size=settings.local_stt_beam_size,
        )
        text_parts: list[str] = []
        for seg in segments:
            text_parts.append((seg.text or "").strip())
        text = " ".join(t for t in text_parts if t).strip()
        return text


def _looks_like_raw_pcm(audio_bytes: bytes) -> bool:
    """Heuristic: raw 16-bit mono PCM has no RIFF magic, is an even size, and
    its header bytes are plausible PCM samples (small int16 values)."""
    if len(audio_bytes) < 100:
        return False
    if audio_bytes[:4] == b"RIFF" or audio_bytes[:4] == b"OggS" or audio_bytes[:4] == b"fLaC":
        return False
    import numpy as np

    samples = np.frombuffer(audio_bytes[:4096], dtype=np.int16)
    if samples.size < 16:
        return False
    peak = float(np.abs(samples).max())
    return 0.0 < peak <= 32768.0


def _raw_pcm(audio_bytes: bytes, sample_rate: int):
    import numpy as np

    data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0
    return data.reshape(-1), sample_rate