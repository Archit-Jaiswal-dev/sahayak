# Contributing to Sahayak

## Development Setup

```bash
# Install dependencies
pip install -r requirements.txt -r requirements-dev.txt
pip install faster-whisper edge-tts
playwright install chromium

# Run tests
python -m pytest tests/ -q

# Start dev server
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Code Style

- Python 3.14+ (match existing codebase)
- Type hints on all functions
- Pydantic models for all API request/response
- Async/await for all I/O operations
- No comments unless asked

## Testing

- All tests in `tests/`
- Use `pytest-asyncio` for async tests
- Provider tests use mocking (no real API calls in CI)
- Conversation flow tests use `ScriptedLLM` with canned responses

```bash
# Run full suite
python -m pytest tests/ -q

# Run with verbose output
python -m pytest tests/ -v

# Run specific test
python -m pytest tests/test_conversation_flow.py -k "test_happy_path"
```

## Project Layout

```
app/
├── api/          # HTTP endpoints (thin, delegate to services)
├── services/     # Business logic (conversation state machine)
├── providers/    # External service adapters (LLM, STT, TTS)
├── rpa/          # CPGRAMS browser automation
└── watchdog/     # Post-filing SLA tracking
```

**Rules:**
- `api/` layer: only request parsing, response formatting, error mapping
- `services/` layer: business logic, no HTTP concerns
- `providers/` layer: external service adapters, implement abstract base classes
- `rpa/` layer: Playwright automation, all portal-specific code

## Adding a New Provider

1. Implement the abstract base class in `app/providers/__init__.py`
2. Add factory logic in the corresponding `get_*_provider()` function
3. Add config fields in `app/config.py`
4. Add tests in `tests/`

## Commit Messages

- Use present tense: "Add feature" not "Added feature"
- Keep under 72 characters
- Reference issues when applicable: "Fix #123"

## Security

- Never commit `.env` or secrets
- All CPGRAMS credentials are encrypted at rest (AES-256-GCM)
- CAPTCHA/OTP are always human-in-the-loop (never automated)
