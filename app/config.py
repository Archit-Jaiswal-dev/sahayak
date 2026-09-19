from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.5-flash"

    # STT: local faster-whisper. Only option.
    stt_provider: str = "local"
    local_stt_model: str = "large-v3-turbo"
    local_stt_language: str = "auto"
    local_stt_device: str = "auto"
    local_stt_compute_type: str = ""
    local_stt_cpu_threads: int = 4
    local_stt_beam_size: int = 1

    # TTS: edge-tts (Microsoft). Only option.
    tts_provider: str = "edge"
    edge_tts_voice: str = ""

    cpgrams_email: str = ""
    cpgrams_password: str = ""
    sahayak_session_encryption_key: str = ""
    sahayak_session_ttl_hours: float = 24.0
    sahayak_default_account: str = "default"


settings = Settings()
