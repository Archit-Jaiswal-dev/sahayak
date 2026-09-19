# Sahayak

**Voice-first grievance drafting and filing assistant for Indian citizens.**

Sahayak lets citizens report problems (broken water pipes, electricity issues, road damage, etc.) through a natural voice conversation in Hindi. It automatically files complaints on [pgportal.gov.in](https://pgportal.gov.in) (CPGRAMS) via browser automation and tracks SLA deadlines, escalating overdue grievances without the citizen having to follow up.

---

## What It Does

1. **Listens** — Citizen speaks their complaint in Hindi (or English, Bengali, Telugu, etc.)
2. **Understands** — LLM extracts complaint details through a natural multi-turn conversation
3. **Files** — Automatically submits the grievance on CPGRAMS via RPA (Playwright)
4. **Tracks** — Monitors SLA deadlines and escalates overdue complaints with formal appeals

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    Mobile App (Flutter)                  │
│  Voice Record → STT → API Call → TTS Playback          │
└──────────┬──────────────────────────────┬───────────────┘
           │                              │
           ▼                              ▼
┌──────────────────┐         ┌──────────────────────────┐
│   STT Provider   │         │    TTS Provider           │
│  (faster-whisper)│         │  (Microsoft Edge TTS)     │
│  Local GPU/CPU   │         │  Remote, free             │
└──────────────────┘         └──────────────────────────┘
           │                              ▲
           ▼                              │
┌─────────────────────────────────────────────────────────┐
│                  FastAPI Backend                         │
│                                                         │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────┐ │
│  │  Sessions    │  │  Audio API   │  │  Filing API   │ │
│  │  (create,    │  │  (STT/TTS    │  │  (submit to   │ │
│  │   turn,      │  │   bridge)    │  │   CPGRAMS)    │ │
│  │   state)     │  │              │  │               │ │
│  └──────┬──────┘  └──────────────┘  └───────┬───────┘ │
│         │                                    │         │
│         ▼                                    ▼         │
│  ┌─────────────┐                    ┌───────────────┐ │
│  │ Conversation │                    │  CPGRAMS RPA   │ │
│  │  Service     │                    │  (Playwright)  │ │
│  │  (slot fill) │                    │  Browser auto  │ │
│  └──────┬──────┘                    └───────┬───────┘ │
│         │                                    │         │
│         ▼                                    ▼         │
│  ┌─────────────┐                    ┌───────────────┐ │
│  │ Gemini LLM   │                    │  Watchdog      │ │
│  │ (structured  │                    │  (SLA track,   │ │
│  │  JSON output)│                    │   escalation)  │ │
│  └─────────────┘                    └───────────────┘ │
└─────────────────────────────────────────────────────────┘
```

---

## Tech Stack

### Backend

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | FastAPI + Uvicorn | REST API server |
| **LLM** | Google Gemini 3.5 Flash | Structured conversation + slot filling |
| **STT** | faster-whisper (large-v3-turbo) | Speech-to-text, local GPU/CPU |
| **TTS** | Microsoft Edge TTS | Text-to-speech, remote neural voices |
| **RPA** | Playwright (Chromium) | CPGRAMS browser automation |
| **Encryption** | AES-256-GCM | Session + credential storage |
| **Language** | Python 3.14 | Runtime |

### Mobile App

| Component | Technology | Purpose |
|-----------|-----------|---------|
| **Framework** | Flutter (Dart) | Cross-platform mobile |
| **Audio** | record + audioplayers | Voice recording + playback |
| **WebView** | webview_flutter | CPGRAMS session linking |
| **Location** | geolocator | GPS geotagging |
| **Storage** | shared_preferences | Local profile persistence |

---

## Features

### Conversation Engine
- Multi-turn slot-filling with 7 required fields (category, ministry, description, location, date, name, contact)
- Structured JSON output from Gemini (no free-text parsing)
- GPS geotagging when citizen is onsite
- PDF evidence upload (max 4MB)
- Hindi + English + 10 other Indian languages
- Female voice persona with feminine self-forms in Hindi

### CPGRAMS Filing
- Automated login + form filling + submission via Playwright
- Human-in-the-loop for CAPTCHA/OTP (never automated)
- Session import from mobile WebView
- Auto-renewal from stored credentials
- Ministry fuzzy matching (75+ ministries in catalog)

### Watchdog
- SLA tracking per category (30-60 days)
- Auto-draft formal Hindi appeal letters for overdue grievances
- Dedup protection (7-day window, SHA-256 fingerprint)
- Citizen notification hooks (SMS + voice call)

### Security
- All sessions/credentials encrypted at rest (AES-256-GCM)
- Short-lived sessions (24h TTL, auto-expire)
- Tampered/expired records auto-dropped
- No secrets in code (`.env` excluded from git)

---

## Conversation Flow

```
Create Session
      │
      ▼
┌─────────────┐
│  Collecting  │ ◄── Citizen speaks, LLM extracts fields
│  (turns 1-6) │     Each turn: extract fields → ask next question
└──────┬──────┘
       │ All 7 fields filled
       ▼
┌─────────────┐
│   Evidence   │ ◄── "Do you have supporting documents?"
│              │     Yes → upload PDF (max 4MB)
└──────┬──────┘     No  → skip
       │
       ▼
┌─────────────┐
│    Assist    │ ◄── "Do you need help with anything else?"
│              │     Yes → one more collecting turn
└──────┬──────┘     No  → proceed
       │
       ▼
┌─────────────┐
│  Confirming  │ ◄── LLM reads back full report
│              │     Citizen says yes → done
└──────┬──────┘     Citizen says no  → back to collecting
       │
       ▼
┌─────────────┐
│     Done     │ ◄── Grievance ready for filing
└─────────────┘

If 6 turns pass without all fields → Closed (callback message)
```

---

## Setup

### Prerequisites

- Python 3.12+
- NVIDIA GPU (optional, for fast STT — falls back to CPU)
- Gemini API key ([get one here](https://aistudio.google.com/apikey))

### 1. Clone and install

```bash
git clone https://github.com/your-username/sahayak.git
cd sahayak
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install faster-whisper edge-tts
playwright install chromium
```

### 2. Configure environment

```bash
cp .env.example .env
# Edit .env with your API keys
```

Key variables:
```
GEMINI_API_KEY=your-key-here
STT_PROVIDER=local
TTS_PROVIDER=edge
SAHAYAK_SESSION_ENCRYPTION_KEY=  # generate with: python -m app.rpa.session_store --gen-key
```

### 3. Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 4. Verify

```bash
curl http://localhost:8000/
# {"service":"sahayak-api","status":"ok"}
```

---

## API Reference

### Sessions

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/sessions` | Create new conversation |
| `POST` | `/v1/sessions/{id}/turn` | Process a citizen utterance |
| `GET` | `/v1/sessions/{id}` | Get session state |
| `POST` | `/v1/sessions/{id}/evidence` | Upload PDF evidence |

### Audio

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/audio/tts` | Text-to-speech (returns base64 MP3) |
| `POST` | `/v1/audio/stt` | Speech-to-text (accepts audio file) |

### Filing

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/filing/file` | File grievance to CPGRAMS |

### CPGRAMS

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/v1/cpgrams/link` | Import session from WebView |
| `GET` | `/v1/cpgrams/status` | Check session validity |
| `GET` | `/v1/cpgrams/profile` | Get citizen profile |
| `POST` | `/v1/cpgrams/credentials` | Store login for auto-renewal |
| `POST` | `/v1/cpgrams/renew` | Server-side re-login |
| `POST` | `/v1/cpgrams/renew/resolve` | Resume after CAPTCHA/OTP |
| `POST` | `/v1/cpgrams/unlink` | Delete session + credentials |

### Watchdog

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/v1/watchdog/grievances` | List all tracked grievances |
| `GET` | `/v1/watchdog/grievances/{id}` | Get one grievance |
| `POST` | `/v1/watchdog/grievances/{id}/resolve` | Mark resolved |
| `POST` | `/v1/watchdog/grievances/{id}/escalate` | Escalate overdue |
| `POST` | `/v1/watchdog/reconcile` | Scan for overdue |

---

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Google Gemini API key |
| `GEMINI_MODEL` | `gemini-3.5-flash` | Gemini model |
| `STT_PROVIDER` | `local` | STT engine (`local` only) |
| `LOCAL_STT_MODEL` | `large-v3-turbo` | Whisper model size |
| `LOCAL_STT_DEVICE` | `auto` | `auto` / `cpu` / `cuda` |
| `LOCAL_STT_COMPUTE_TYPE` | — | `int8` (CPU) / `int8_float16` (GPU) |
| `TTS_PROVIDER` | `edge` | TTS engine (`edge` only) |
| `EDGE_TTS_VOICE` | — | Override voice (default: `hi-IN-SwaraNeural`) |
| `SAHAYAK_SESSION_ENCRYPTION_KEY` | — | AES-256 key (base64) |
| `SAHAYAK_SESSION_TTL_HOURS` | `24` | Session expiry |
| `CPGRAMS_EMAIL` | — | CPGRAMS login |
| `CPGRAMS_PASSWORD` | — | CPGRAMS password |

---

## Project Structure

```
sahayak/
├── app/                     # Backend core
│   ├── main.py              # FastAPI app + lifespan
│   ├── config.py            # Settings (pydantic-settings)
│   ├── schemas.py           # Pydantic data models
│   ├── prompts.py           # LLM system prompts
│   ├── api/                 # HTTP endpoints
│   │   ├── audio.py         # STT + TTS
│   │   ├── sessions.py      # Session management
│   │   ├── filing.py        # CPGRAMS filing
│   │   ├── cpgrams.py       # Session lifecycle
│   │   └── watchdog.py      # Grievance tracking
│   ├── services/
│   │   └── conversation.py  # Slot-filling state machine
│   ├── providers/           # External service adapters
│   │   ├── gemini.py        # Google Gemini LLM
│   │   ├── local_stt.py     # faster-whisper STT
│   │   └── edge_tts.py      # Microsoft Edge TTS
│   ├── rpa/                 # CPGRAMS automation
│   │   ├── submitter.py     # Playwright RPA engine
│   │   ├── selectors.py     # Portal CSS selectors
│   │   ├── session_store.py # Encrypted session storage
│   │   ├── credential_store.py
│   │   ├── models.py        # Grievance payload
│   │   ├── catalog.py       # Ministry catalog + fuzzy match
│   │   ├── human.py         # CAPTCHA/OTP human-in-the-loop
│   │   └── notifier.py      # Alert hooks
│   └── watchdog/            # Post-filing monitoring
│       ├── service.py       # WatchdogService
│       ├── store.py         # Grievance records
│       ├── deadlines.py     # SLA per category
│       ├── appeal.py        # Hindi appeal drafts
│       └── notifier.py      # Citizen notifications
├── tests/                   # Test suite (59 tests)
├── scripts/                 # CLI utilities
├── mobile/                  # Flutter Android app
├── data/                    # Runtime data (encrypted)
├── samples/                 # Test fixtures
├── .env.example             # Environment template
├── requirements.txt         # Python dependencies
├── Dockerfile               # Container build
└── README.md                # This file
```

---

## Testing

```bash
# Run all tests
python -m pytest tests/ -q

# Run specific test file
python -m pytest tests/test_conversation_flow.py -v

# Smoke test providers
python -m scripts.smoke_test stt samples/test.wav
python -m scripts.smoke_test tts "नमस्ते"
python -m scripts.smoke_test llm
```

---

## Mobile App

The Flutter app is in `mobile/`. Build the APK:

```bash
cd mobile
flutter build apk
```

The APK is output to `build/app/outputs/flutter-apk/app-release.apk`.

### App Flow
1. Consent screen → Language selection (Hindi/English) → Login
2. Home screen → Start conversation
3. Voice record → Backend STT → LLM processes → TTS plays response
4. CPGRAMS WebView → Citizen logs in → Session exported to backend
5. File grievance → RPA submits → Registration ID returned
6. Watchdog tracks → Escalates if overdue

---

## Deployment

### Local + Cloudflare Tunnel

```bash
# Start backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Expose via tunnel
cloudflared tunnel run sahayak
```

### Docker

```bash
docker build -t sahayak .
docker run -p 8000:8000 --env-file .env sahayak
```

### Cloud (free tier)

| Provider | Specs | Fit |
|----------|-------|-----|
| Oracle Cloud A1 (free forever) | 4 OCPU, 24GB RAM | Best — runs everything |
| Hugging Face Spaces | 2 vCPU, 16GB RAM | Works, sleeps on idle |
| Your PC + cloudflared | Varies | Current setup |

---

## SLA Deadlines

| Category | Days | Examples |
|----------|------|---------|
| Water (pani) | 30 | Broken pipes, no supply |
| Electricity (bijli) | 30 | Power cuts, billing errors |
| Road (sadak) | 45 | Potholes, construction |
| Cleanliness (swachhata) | 30 | Garbage, sanitation |
| Government (sarkari) | 60 | RTO, ration card |
| Other | 60 | Default |

---

## License

Private — All rights reserved.
