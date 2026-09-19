# Sahayak

**"Sahayak" (सहायक) — A voice-powered grievance filing assistant for Indian citizens.**

Sahayak eliminates the barriers that prevent ordinary citizens from using [CPGRAMS](https://pgportal.gov.in), India's national grievance portal. Speak your complaint in your own language, and Sahayak handles the rest — drafting, filing, tracking, and escalating.

---

## Table of Contents

- [What is Sahayak](#what-is-sahayak)
- [Problem It Solves](#problem-it-solves)
- [How It Works](#how-it-works)
- [Architecture](#architecture)
- [Tech Stack](#tech-stack)
- [Features](#features)
- [Conversation Flow](#conversation-flow)
- [Example Conversation](#example-conversation)
- [API Reference](#api-reference)
- [Setup](#setup)
- [Configuration](#configuration)
- [Project Structure](#project-structure)
- [Providers](#providers)
- [CPGRAMS Filing](#cpgrams-filing)
- [Watchdog](#watchdog)
- [Security](#security)
- [Mobile App](#mobile-app)
- [Deployment](#deployment)
- [Hardware Requirements](#hardware-requirements)
- [Testing](#testing)
- [Troubleshooting](#troubleshooting)
- [License](#license)

---

## What is Sahayak

Sahayak is a **voice-first grievance drafting and filing assistant** for Indian citizens. It lets citizens report problems — broken water pipes, power outages, road damage, sanitation issues, and more — through a natural voice conversation in Hindi (or 10 other Indian languages).

A multi-turn conversation extracts all required complaint details through simple follow-up questions. Once the report is complete, Sahayak automatically files it on [CPGRAMS](https://pgportal.gov.in) (the Centralized Public Grievance Redress and Monitoring System) via browser automation (RPA). After filing, the built-in **Watchdog** monitors SLA deadlines and auto-escalates overdue complaints with formal Hindi appeal letters — without the citizen ever having to check back.

**Key Innovation:** Sahayak eliminates three critical barriers simultaneously:
- **Digital literacy** — citizens speak naturally instead of filling forms
- **Language barriers** — supports Hindi, English, Bengali, Telugu, Tamil, Marathi, Gujarati, Kannada, Malayalam, Punjabi, and more
- **Follow-up burden** — the Watchdog tracks deadlines and escalates automatically

---

## Problem It Solves

India's CPGRAMS portal ([pgportal.gov.in](https://pgportal.gov.in)) handles millions of complaints annually, but it requires citizens to:

1. **Digital literacy** — navigate a complex web portal with multi-step forms
2. **Language skills** — the portal primarily operates in English and Hindi text
3. **Ministry knowledge** — correctly route complaints to one of 75+ government ministries
4. **Manual follow-up** — remember SLA deadlines and file escalation requests personally

These barriers disproportionately affect rural citizens, elderly users, and those with limited education — the people who need grievance redressal the most. Sahayak solves all four problems by letting citizens speak their complaint in their own language and handling every technical step automatically.

---

## How It Works

Sahayak operates as a **10-step pipeline** from voice input to tracked complaint:

```
+-----------+     +------+     +------+     +----------+     +---------+
| 1. Voice  |---->| 2.   |---->| 3.   |---->| 4. Multi |---->| 5. Evi- |
|    Input  |     | STT  |     | LLM  |     | Turn     |     | dence   |
| (record)  |     |(Whis-|     |(Gemi-|     | Conver-  |     | Collect |
|           |     | per) |     | ni)  |     | sation   |     | (PDF)   |
+-----------+     +------+     +------+     +----------+     +---------+
                                                               |
                                                               v
+-----------+     +------+     +----------+     +---------+  +--------+
| 10. Auto  |<----| 9.   |<----| 8. Reg   |<----| 7. CPA- |<| 6. Con |
| Escalation|     |Watch-|     | ID       |     | GRAMS   |  | firm   |
| (appeal)  |     | dog  |     | Scraped  |     | Filing  |  |        |
|           |     |Record|     |          |     | (RPA)   |  |        |
+-----------+     +------+     +----------+     +---------+  +--------+
```

1. **Voice Input** — Mobile app records the citizen's audio via microphone
2. **STT** — Local Whisper model (`large-v3-turbo`) transcribes audio to text
3. **LLM** — Gemini extracts structured fields from the transcript
4. **Multi-Turn Conversation** — Follow-up questions are asked one at a time until all 7 required fields are filled (max 6 turns)
5. **Evidence Collection** — Optional PDF upload (max 4MB) for supporting documents
6. **Confirmation** — LLM reads back the complete report; citizen confirms or requests corrections
7. **CPGRAMS Filing** — Playwright automates form submission on pgportal.gov.in
8. **Registration ID** — The complaint's unique registration number is scraped from the confirmation page
9. **Watchdog Recording** — The grievance is tracked with its SLA deadline
10. **Auto-Escalation** — If the deadline passes, a formal Hindi appeal is auto-drafted and filed

---

## Architecture

```
+------------------------------------------------------------------+
|                      Mobile App (Flutter)                         |
|  Voice Record -> STT -> API Call -> TTS Playback                 |
+-----------------+------------------------+------------------------+
                  |                        |
                  v                        v
+--------------------------+    +-----------------------------+
|    STT Provider          |    |     TTS Provider            |
|   (faster-whisper)       |    |   (Microsoft Edge TTS)      |
|   Local GPU/CPU          |    |   Remote, free              |
+--------------------------+    +-----------------------------+
                  |                        ^
                  v                        |
+------------------------------------------------------------------+
|                     FastAPI Backend (API Layer)                   |
|                                                                  |
|  +-----------+   +-----------+   +-----------+   +-----------+  |
|  | Sessions  |   |  Audio    |   |  Filing   |   |  CPGRAMS  |  |
|  | (create,  |   |  (STT/TTS |   |  (submit  |   |  (session |  |
|  |  turn,    |   |   bridge) |   |   to      |   |   life-   |  |
|  |  state)   |   |           |   |  CPGRAMS) |   |   cycle)  |  |
|  +-----+-----+   +-----------+   +-----+-----+   +-----+-----+  |
|        |                               |               |         |
|        v                               v               v         |
|  +-----------+                  +-----------+   +-----------+    |
|  | Conversa- |                  |  CPGRAMS  |   |  Watchdog |    |
|  | tion      |                  |  RPA      |   |  (SLA     |    |
|  | Service   |                  |  (Play-   |   |   track,  |    |
|  | (slot     |                  |  wright)  |   |  escalate)|    |
|  |  fill)    |                  |           |   |           |    |
|  +-----+-----+                  +-----------+   +-----------+    |
|        |                                                            |
|        v                                                            |
|  +-----------+                                                      |
|  | Gemini    |                                                      |
|  | LLM       |                                                      |
|  | (struct-  |                                                      |
|  | ured JSON)|                                                      |
|  +-----------+                                                      |
+------------------------------------------------------------------+
```

---

## Tech Stack

### Backend

| Component     | Technology                    | Purpose                                   |
|---------------|-------------------------------|-------------------------------------------|
| **Framework** | FastAPI + Uvicorn             | REST API server                           |
| **LLM**       | Google Gemini 3.5 Flash       | Structured conversation + slot filling    |
| **STT**       | faster-whisper (large-v3-turbo) | Speech-to-text, local GPU/CPU           |
| **TTS**       | Microsoft Edge TTS            | Text-to-speech, remote neural voices      |
| **RPA**       | Playwright (Chromium)         | CPGRAMS browser automation                |
| **Encryption**| AES-256-GCM                   | Session + credential storage              |
| **Validation**| Pydantic v2                   | Request/response schemas                  |
| **Language**  | Python 3.14                   | Runtime                                   |

### Mobile App

| Component     | Technology             | Purpose                              |
|---------------|------------------------|--------------------------------------|
| **Framework** | Flutter (Dart)         | Cross-platform mobile                |
| **Audio**     | record + audioplayers  | Voice recording + playback           |
| **WebView**   | webview_flutter        | CPGRAMS session linking              |
| **Location**  | geolocator             | GPS geotagging                       |
| **Storage**   | shared_preferences     | Local profile persistence            |
| **Files**     | file_picker            | PDF evidence upload                  |
| **Links**     | url_launcher           | WhatsApp draft sharing               |

---

## Features

### 1. Conversation Engine

The core multi-turn slot-filling system collects all required complaint details through natural dialogue.

- **7 Required Slots:** category, ministry, description, location, date, name, contact
- **Priority Ordering:** Fields are asked in a fixed priority order; name and contact are always last
- **Structured JSON Output:** Gemini enforces a strict JSON schema on every response — no free-text parsing
- **Max 6 Turns:** If all fields are not collected within 6 conversation turns, the session closes gracefully with a callback message
- **Correction Support:** Citizens can correct any previously entered field at any time
- **Female Voice Persona:** The assistant speaks with a feminine voice and uses feminine self-forms in Hindi ("main aapki madad kar sakti hoon")

### 2. GPS Geotagging

When the citizen is at the location of the incident:

1. The assistant asks: "Kya aap abhi usi jagah par hain jahan yeh hua?"
2. If yes, the app requests location permission and captures GPS coordinates
3. GPS data is sent as a `[LOCATION: lat, lng]` marker
4. The backend stores both the address text and coordinates
5. If the citizen is not at the location, a text address is collected instead

### 3. Evidence Upload

- Citizens can attach a **single PDF file** (max 4MB)
- The upload is validated for file type and size
- The evidence filename is recorded in the complaint record
- Optional — the flow proceeds without evidence if the citizen declines

### 4. CPGRAMS Auto-Filing

Full browser automation against [pgportal.gov.in](https://pgportal.gov.in):

- **Session Validation:** Verifies stored session authenticates before each filing
- **Auto-Renewal:** Re-logins from stored credentials when session expires
- **Form Navigation:** Walks the V7 guided questionnaire step by step
- **Ministry Selection:** Matches the AI-routed ministry against the live portal catalog
- **Category Walk:** Progressively selects nested category dropdowns
- **Form Fill:** Populates description, personal details, address, pincode
- **CAPTCHA:** Human-in-the-loop — the citizen solves it in-app
- **Registration ID:** Scraped from the confirmation page after submission

### 5. Ministry Fuzzy Matching

- **75+ Ministries** from the live CPGRAMS catalog (`data/cpgrams_orgs.json`)
- **Exact Match** — normalized string comparison
- **Prefix Match** — handles "Ministry of" / "Dept of" variations
- **Fuzzy Match** — `SequenceMatcher` with a **0.55 similarity threshold**
- Falls back to "State Governments/Others" when no match is found

### 6. Watchdog (Escalation System)

Post-filing monitoring that fights for the citizen automatically:

- **SLA Tracking** — per-category deadlines (30-60 days)
- **Auto-Draft Appeals** — formal Hindi letters when deadlines pass
- **Reconcile** — background scan flags overdue grievances
- **Escalate** — citizen confirms the appeal, it is filed and the citizen is notified
- **Citizen Notification** — SMS + voice call hooks (pluggable gateway)
- **Dedup Protection** — 7-day window, SHA-256 fingerprint of category+location+description

### 7. Security

- **AES-256-GCM Encryption** — all sessions and credentials encrypted at rest
- **Authenticated Encryption** — tamper detection via GCM auth tag
- **24-Hour TTL** — sessions auto-expire; re-linking required
- **Atomic Writes** — write-to-temp-then-rename pattern prevents corruption
- **File Permissions** — `0600` on all sensitive data files
- **No Plaintext Secrets** — API keys and passwords only in `.env` (gitignored)
- **Key Rotation** — encryption key is a 32-byte base64 value, regenerable

---

## Conversation Flow

The conversation engine follows a strict state machine:

```
                +--------+
                | CREATE |  (session initialized)
                +----+---+
                     |
                     v
              +------------+
              | COLLECTING | <--- Citizen speaks, LLM extracts fields
              | (turns 1-6)|      Each turn: extract -> ask next question
              +-----+------+
                    |
                    | All 7 fields filled
                    v
              +------------+
              |  EVIDENCE  | <--- "Do you have supporting documents?"
              |            |      Yes -> upload PDF (max 4MB)
              +-----+------+      No  -> skip
                    |
                    v
              +------------+
              |   ASSIST   | <--- "Do you need help with anything else?"
              |            |      Yes -> one more collecting turn
              +-----+------+      No  -> proceed
                    |
                    v
              +------------+
              | CONFIRMING | <--- LLM reads back full report
              |            |      Citizen says "haan" -> done
              +-----+------+      Citizen says "nahi" -> back to collecting
                    |
                    v
              +------------+
              |    DONE    | <--- Grievance ready for filing
              +------------+

  If 6 turns pass without all fields -> CLOSED (callback message)
```

**Turn Processing Pipeline:**

```
Citizen audio/text
       |
       v
  +---------+     +----------+     +---------+     +----------+
  |  STT    |---->| Trim     |---->| Build   |---->| Gemini   |
  | (Whis-  |     | history  |     | system  |     | complete |
  |  per)   |     | (max 6)  |     | prompt  |     | (JSON)   |
  +---------+     +----------+     +---------+     +-----+----+
                                                      |
                                                      v
                                               +-----------+
                                               | Merge     |
                                               | slots +   |
                                               | validate  |
                                               +-----+-----+
                                                     |
                                                     v
                                               +-----------+
                                               | Return    |
                                               | TurnResult|
                                               +-----------+
```

---

## Example Conversation

A citizen reports a water supply problem in Hindi. The assistant collects all 7 fields across 5 turns:

```
Citizen: [recorded audio]
  STT: "मेरे मोहल्ले में पानी की बहुत समस्या है। तीन दिन से नल में पानी नहीं आ रहा।"

Assistant: "नमस्ते! मैं सहायक हूँ। आपकी शिकायत दर्ज करने में आपकी मदद करूँगी।
           आप बता सकते हैं कि यह समस्या किस जगह पर है?"

Citizen: [recorded audio]
  STT: "यह गांधी नगर, ब्लॉक C की बात हो रही है, दिल्ली।"

Assistant: "ठीक है। यह समस्या कब से चल रही है?"

Citizen: [recorded audio]
  STT: "पिछले तीन दिन से। 17 सितंबर से पानी नहीं आ रहा।"

Assistant: "समझ गई। आपका पूरा नाम क्या है?"

Citizen: [recorded audio]
  STT: "राम प्रसाद शर्मा"

Assistant: "और आपका मोबाइल नंबर?"

Citizen: [recorded audio]
  STT: "9876543210"

Assistant: "क्या आपके पास कोई दस्तावेज़ है, जैसे फ़ोटो या बिल?"

Citizen: "nahi"

Assistant: "ठीक है। क्या आपको किसी और चीज़ में मदद चाहिए?"

Citizen: "nahi"

Assistant: [reads back full report]
  "आपकी शिकायत इस प्रकार है:
   - श्रेणी: पानी
   - विभाग: Ministry of Jal Shakti
   - विवरण: तीन दिन से नल में पानी नहीं आ रहा
   - स्थान: गांधी नगर, ब्लॉक C, दिल्ली
   - तारीख: 17-09-2026
   - नाम: राम प्रसाद शर्मा
   - संपर्क: 9876543210

   क्या यह रिपोर्ट सही है? हाँ या ना?"

Citizen: "haan bilkul sahi hai"

Assistant: "बहुत अच्छा! आपकी शिकायत दर्ज हो गई है।
           पंजीकरण संख्या CPGRAMS-20260919123456 है।"
```

---

## API Reference

Base URL: `http://localhost:8000`

### Sessions

#### POST /v1/sessions — Create Session

```json
// Request
{
  "name": "Ram Prasad Sharma",
  "contact": "9876543210",
  "language": "hi"
}

// Response (201)
{
  "session_id": "a1b2c3d4e5f6",
  "question": "नमस्ते! मैं सहायक हूँ। आपकी शिकायत दर्ज करने में आपकी मदद करूँगी। बताइए, आपकी शिकायत किस बारे में है?"
}
```

#### POST /v1/sessions/{session_id}/turn — Process Turn

```json
// Request
{
  "transcript": "मेरे मोहल्ले में पानी की बहुत समस्या है।"
}

// Response (200)
{
  "session_id": "a1b2c3d4e5f6",
  "status": "collecting",
  "question": "ठीक है। यह समस्या किस जगह पर है?",
  "filled": ["category"],
  "missing": ["ministry", "description", "location", "date", "name", "contact"],
  "report_text": null,
  "message": null,
  "request_geotag": false,
  "request_evidence": false
}
```

#### GET /v1/sessions/{session_id} — Get Session State

```json
// Response (200)
{
  "session_id": "a1b2c3d4e5f6",
  "status": "collecting",
  "turn_count": 3,
  "slots": {
    "category": "pani",
    "ministry": "Ministry of Jal Shakti",
    "description": "तीन दिन से नल में पानी नहीं आ रहा",
    "location": "गांधी नगर, ब्लॉक C, दिल्ली",
    "date": "17-09-2026",
    "name": null,
    "contact": null
  },
  "filled": ["category", "ministry", "description", "location", "date"],
  "missing": ["name", "contact"],
  "report_text": null
}
```

#### POST /v1/sessions/{session_id}/evidence — Upload Evidence

```bash
# Request (multipart/form-data)
curl -X POST http://localhost:8000/v1/sessions/a1b2c3d4e5f6/evidence \
  -F "file=@evidence.pdf"
```

```json
// Response (201)
{
  "session_id": "a1b2c3d4e5f6",
  "filename": "a1b2c3d4_evidence.pdf",
  "size_bytes": 524288
}
```

### Audio

#### POST /v1/audio/tts — Text-to-Speech

```json
// Request
{
  "text": "नमस्ते! मैं सहायक हूँ।",
  "language": "hi"
}

// Response (200)
{
  "audio": "<base64-encoded MP3 audio>",
  "mime_type": "audio/mpeg"
}
```

#### POST /v1/audio/stt — Speech-to-Text

```bash
# Request (multipart/form-data)
curl -X POST http://localhost:8000/v1/audio/stt \
  -F "file=@recording.wav" \
  -F "language=hi"
```

```json
// Response (200)
{
  "transcript": "मेरे मोहल्ले में पानी की बहुत समस्या है।"
}
```

### Filing

#### POST /v1/filing/file — File Grievance

```json
// Request
{
  "session_id": "a1b2c3d4e5f6",
  "account_key": "mobile-9876543210"
}

// Response (200)
{
  "session_id": "a1b2c3d4e5f6",
  "registration_id": "CPGRAMS-20260919123456",
  "account_key": "mobile-9876543210"
}
```

### CPGRAMS

#### POST /v1/cpgrams/link — Import Session from WebView

```json
// Request
{
  "account_key": "mobile-9876543210",
  "cookies": [
    {
      "name": "ASP.NET_SessionId",
      "value": "abc123...",
      "domain": "pgportal.gov.in",
      "path": "/"
    }
  ]
}

// Response (200)
{
  "account_key": "mobile-9876543210",
  "linked": true,
  "expires_at": "2026-09-20T12:00:00Z",
  "message": "CPGRAMS session linked successfully."
}
```

#### GET /v1/cpgrams/status — Check Session Status

```bash
curl "http://localhost:8000/v1/cpgrams/status?account_key=mobile-9876543210"
```

```json
// Response (200)
{
  "account_key": "mobile-9876543210",
  "linked": true,
  "valid": true,
  "expires_at": "2026-09-20T12:00:00Z",
  "reason": ""
}
```

#### GET /v1/cpgrams/profile — Fetch Citizen Profile

```bash
curl "http://localhost:8000/v1/cpgrams/profile?account_key=mobile-9876543210"
```

```json
// Response (200)
{
  "account_key": "mobile-9876543210",
  "name": "Ram Prasad Sharma",
  "gender": "M",
  "email": "ram@example.com",
  "mobile": "9876543210",
  "phone": "",
  "address_lines": ["Gandhi Nagar Block C"],
  "state": "Delhi",
  "district": "Central Delhi",
  "country": "India",
  "pincode": "110031"
}
```

#### POST /v1/cpgrams/credentials — Store Login for Auto-Renewal

```json
// Request
{
  "account_key": "mobile-9876543210",
  "username": "ram@example.com",
  "password": "securepassword"
}

// Response (200)
{
  "account_key": "mobile-9876543210",
  "stored": true,
  "message": "Credentials stored for automatic re-login."
}
```

#### POST /v1/cpgrams/renew — Server-Side Re-Login

```json
// Request
{
  "account_key": "mobile-9876543210"
}

// Response (200) — Success
{
  "account_key": "mobile-9876543210",
  "renewed": true,
  "expires_at": "2026-09-20T12:00:00Z",
  "reason": "",
  "challenge": "",
  "token": "",
  "image_b64": ""
}

// Response (200) — CAPTCHA challenge
{
  "account_key": "mobile-9876543210",
  "renewed": false,
  "challenge": "captcha",
  "token": "abc123...",
  "image_b64": "<base64 CAPTCHA image>",
  "reason": "Enter the characters shown in the image to finish renewing."
}
```

#### POST /v1/cpgrams/renew/resolve — Resume After CAPTCHA/OTP

```json
// Request
{
  "token": "abc123...",
  "answer": "X7K9"
}

// Response (200)
{
  "account_key": "mobile-9876543210",
  "renewed": true,
  "expires_at": "2026-09-20T12:00:00Z"
}
```

#### POST /v1/cpgrams/unlink — Delete Session + Credentials

```json
// Request
{
  "account_key": "mobile-9876543210"
}

// Response (200)
{
  "account_key": "mobile-9876543210",
  "unlinked": true,
  "message": "CPGRAMS session removed. No stored session remains for this account."
}
```

### Watchdog

#### GET /v1/watchdog/grievances — List All Grievances

```bash
curl http://localhost:8000/v1/watchdog/grievances
```

```json
// Response (200)
[
  {
    "registration_id": "CPGRAMS-20260919123456",
    "ministry": "Ministry of Jal Shakti",
    "category": "pani",
    "description": "तीन दिन से नल में पानी नहीं आ रहा",
    "location": "गांधी नगर, ब्लॉक C, दिल्ली",
    "name": "Ram Prasad Sharma",
    "contact": "9876543210",
    "filed_at": "2026-09-19T10:30:00Z",
    "deadline": "2026-10-19T10:30:00Z",
    "sla_days": 30,
    "status": "open",
    "overdue_days": 0,
    "appeal_draft": null,
    "appeal_filed_at": null,
    "resolved_at": null
  }
]
```

#### GET /v1/watchdog/grievances/{registration_id} — Get One Grievance

```bash
curl http://localhost:8000/v1/watchdog/grievances/CPGRAMS-20260919123456
```

#### POST /v1/watchdog/grievances/{registration_id}/resolve — Mark Resolved

```bash
curl -X POST http://localhost:8000/v1/watchdog/grievances/CPGRAMS-20260919123456/resolve
```

#### POST /v1/watchdog/grievances/{registration_id}/escalate — Escalate Overdue

```bash
curl -X POST http://localhost:8000/v1/watchdog/grievances/CPGRAMS-20260919123456/escalate
```

#### POST /v1/watchdog/reconcile — Scan for Overdue

```bash
curl -X POST http://localhost:8000/v1/watchdog/reconcile
```

```json
// Response (200)
{
  "open": 5,
  "overdue": 2,
  "escalated": 1,
  "drafted_appeals": ["CPGRAMS-20260815001", "CPGRAMS-20260820002"]
}
```

### Root / Health

```bash
curl http://localhost:8000/
# {"service":"sahayak-api","status":"ok"}

curl http://localhost:8000/health
# {"status":"ok"}
```

---

## Setup

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.12+ | 3.14 recommended |
| NVIDIA GPU | Optional | CUDA-capable for fast STT; falls back to CPU |
| Gemini API key | Required | Free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |
| CPGRAMS account | Optional | Needed only for auto-filing |
| Chromium | Required | Installed via Playwright |

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
# Edit .env with your API keys and credentials
```

### 3. Generate encryption key

```bash
python -m app.rpa.session_store --gen-key
# Copy the output into SAHAYAK_SESSION_ENCRYPTION_KEY in .env
```

### 4. Start the server

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

On first boot, the Whisper model is downloaded (~1.6 GB for `large-v3-turbo`) and loaded into memory. This takes 30-60 seconds on first run. Subsequent boots are fast because the model is cached.

### 5. Verify

```bash
curl http://localhost:8000/
# {"service":"sahayak-api","status":"ok"}

curl http://localhost:8000/health
# {"status":"ok"}
```

### 6. Link CPGRAMS (optional)

```bash
python -m scripts.file_grievance --link --account-key alice
```

This opens a Chromium browser, navigates to pgportal.gov.in, and walks through the login with you (you solve the CAPTCHA). The session is stored encrypted and reused for future filings.

### 7. Smoke test providers

```bash
python -m scripts.smoke_test stt samples/test.wav
python -m scripts.smoke_test tts "नमस्ते"
python -m scripts.smoke_test llm
```

---

## Configuration

All configuration is via environment variables (`.env` file). Copy `.env.example` to `.env` and fill in your values.

| Variable | Default | Required | Description |
|----------|---------|----------|-------------|
| `GEMINI_API_KEY` | — | **Yes** | Google Gemini API key ([get one](https://aistudio.google.com/apikey)) |
| `GEMINI_MODEL` | `gemini-3.5-flash` | No | Gemini model with native JSON schema support |
| `STT_PROVIDER` | `local` | No | STT engine. Only `local` is supported |
| `LOCAL_STT_MODEL` | `large-v3-turbo` | No | Whisper model size. Options: tiny, base, small, medium, large-v3, large-v3-turbo |
| `LOCAL_STT_LANGUAGE` | `auto` | No | Source language hint (`auto` detects automatically) |
| `LOCAL_STT_DEVICE` | `auto` | No | `auto`, `cpu`, or `cuda` |
| `LOCAL_STT_COMPUTE_TYPE` | — | No | `int8` for CPU, `int8_float16` for GPU. Auto-detected if empty |
| `LOCAL_STT_CPU_THREADS` | `4` | No | Number of CPU threads for Whisper |
| `LOCAL_STT_BEAM_SIZE` | `1` | No | Beam search size for Whisper |
| `TTS_PROVIDER` | `edge` | No | TTS engine. Only `edge` is supported |
| `EDGE_TTS_VOICE` | — | No | Override voice (default: `hi-IN-SwaraNeural`) |
| `CPGRAMS_EMAIL` | — | No | CPGRAMS login email (for server-side auto-renewal) |
| `CPGRAMS_PASSWORD` | — | No | CPGRAMS password (for server-side auto-renewal) |
| `SAHAYAK_SESSION_ENCRYPTION_KEY` | — | **Yes** | AES-256 key (base64, 32 bytes). Generate: `python -m app.rpa.session_store --gen-key` |
| `SAHAYAK_SESSION_TTL_HOURS` | `24` | No | How long a linked session is trusted before re-linking |
| `SAHAYAK_DEFAULT_ACCOUNT` | `default` | No | Default account key for the filing endpoint |

---

## Project Structure

```
sahayak/
├── app/                              # Backend core
│   ├── __init__.py                   # Package marker
│   ├── main.py                       # FastAPI app + lifespan (STT warmup, provider init)
│   ├── config.py                     # Settings via pydantic-settings (.env loading)
│   ├── schemas.py                    # Pydantic models: SlotUpdate, AssistantTurn, etc.
│   ├── prompts.py                    # LLM system prompts + language rules
│   ├── api/                          # HTTP endpoint routers
│   │   ├── __init__.py
│   │   ├── audio.py                  # POST /v1/audio/tts, POST /v1/audio/stt
│   │   ├── sessions.py               # POST /v1/sessions, turns, state, evidence
│   │   ├── filing.py                 # POST /v1/filing/file (CPGRAMS submission)
│   │   ├── cpgrams.py                # Session lifecycle: link, status, renew, credentials
│   │   └── watchdog.py               # Grievance tracking: list, resolve, escalate
│   ├── services/
│   │   ├── __init__.py
│   │   └── conversation.py           # ConversationService: multi-turn slot-filling state machine
│   ├── providers/                    # External service adapters
│   │   ├── __init__.py               # ABC interfaces: SttProvider, TtsProvider, LLMProvider
│   │   ├── gemini.py                 # Google Gemini LLM (JSON schema enforcement, retry)
│   │   ├── local_stt.py              # faster-whisper STT (auto device detection, VAD)
│   │   └── edge_tts.py              # Microsoft Edge TTS (12 language voices, free)
│   ├── rpa/                          # CPGRAMS browser automation
│   │   ├── __init__.py
│   │   ├── submitter.py              # CPGRAMSSubmitter: login, filing, session management
│   │   ├── selectors.py              # CSS/XPath selectors for pgportal.gov.in DOM
│   │   ├── session_store.py          # AES-256-GCM encrypted session storage
│   │   ├── credential_store.py       # AES-256-GCM encrypted credential storage
│   │   ├── models.py                 # GrievancePayload, category normalization
│   │   ├── catalog.py                # Ministry catalog + fuzzy matching (75+ ministries)
│   │   ├── human.py                  # HumanVerifier ABC: CAPTCHA/OTP human-in-the-loop
│   │   └── notifier.py              # AlertNotifier ABC: RPA failure alerts
│   └── watchdog/                     # Post-filing monitoring
│       ├── __init__.py
│       ├── service.py                # WatchdogService: record, reconcile, escalate, notify
│       ├── store.py                  # GrievanceRecord persistence (JSON files)
│       ├── deadlines.py              # SLA days per category, deadline calculation
│       ├── appeal.py                 # Formal Hindi appeal letter template + generation
│       └── notifier.py              # CitizenNotifier ABC: SMS + voice call hooks
├── mobile/                           # Flutter Android app
│   ├── lib/
│   │   ├── main.dart                 # App entry, route definitions, startup screen
│   │   ├── api_client.dart           # HTTP client for all backend endpoints
│   │   ├── audio_service.dart        # Mic recording + audio playback
│   │   ├── models.dart               # Dart data models matching backend schemas
│   │   ├── profile_store.dart        # Local profile persistence (shared_preferences)
│   │   ├── app_log.dart              # Structured logging for debugging
│   │   ├── app_languages.dart        # 11 supported languages with native names
│   │   ├── cpgrams_renewal.dart      # CPGRAMS session renewal flow
│   │   └── screens/
│   │       ├── consent_screen.dart   # First-open consent dialog
│   │       ├── language_screen.dart  # Language selection (11 options)
│   │       ├── login_screen.dart     # Profile creation (name + mobile)
│   │       ├── home_screen.dart      # Main dashboard: mic button, services, deadlines
│   │       ├── conversation_screen.dart # Voice/text chat with assistant
│   │       ├── cpgrams_webview_screen.dart # In-app CPGRAMS login WebView
│   │       ├── grievances_screen.dart # Filed complaints list with SLA status
│   │       ├── profile_screen.dart   # Account details + CPGRAMS link status
│   │       └── logs_screen.dart      # Debug logs viewer
│   ├── pubspec.yaml                  # Flutter dependencies (v1.2.0)
│   └── test/                         # Flutter tests
├── tests/                            # Python test suite (10 test files)
│   ├── test_conversation_flow.py     # Multi-turn conversation logic
│   ├── test_prompts.py               # System prompt generation
│   ├── test_watchdog.py              # SLA tracking + escalation
│   ├── test_rpa_catalog.py           # Ministry fuzzy matching
│   ├── test_rpa_models.py            # GrievancePayload normalization
│   ├── test_session_store.py         # Encrypted session storage
│   ├── test_credential_store.py      # Encrypted credential storage
│   ├── test_local_providers.py       # STT provider logic
│   ├── test_edge_tts.py              # TTS provider logic
│   └── test_cpgrams_profile.py       # Profile scraping
├── scripts/                          # CLI utilities
│   ├── file_grievance.py             # Link/check/file from command line
│   ├── smoke_test.py                 # Quick provider health checks
│   ├── chat.py                       # Terminal chat with the assistant
│   ├── probe_cframs.py               # Portal DOM inspector
│   ├── capture_orgs.py               # Ministry catalog scraper
│   └── diagnose_login.py             # Login troubleshooting
├── data/                             # Runtime data (gitignored except catalog)
│   ├── cpgrams_orgs.json             # Live ministry catalog (75+ entries)
│   ├── sessions/                     # Encrypted session files
│   ├── credentials/                  # Encrypted credential files
│   └── watchdog/                     # Grievance tracking records
├── samples/                          # Test fixtures and sample audio
├── .env.example                      # Environment variable template
├── .gitignore                        # Git exclusions
├── requirements.txt                  # Python dependencies
├── requirements-dev.txt              # Dev/test dependencies
├── pytest.ini                        # Pytest configuration
├── Dockerfile                        # Container build (Python 3.12 + Playwright)
└── README.md                         # This file
```

---

## Providers

### STT: Local Whisper

Speech-to-text runs locally using [faster-whisper](https://github.com/SYSTRAN/faster-whisper) (CTranslate2 backend with OpenAI Whisper weights).

- **Default model:** `large-v3-turbo` — pruned large-v3 with ~same accuracy, ~8x faster
- **Auto device detection:** CUDA float16 when a GPU is available, CPU int8 otherwise
- **Lazy loading:** Model loads on first transcription (not at boot); warmup preloads in background
- **Audio normalization:** Any input format (WAV, MP3, raw PCM) is resampled to 16kHz mono float32
- **VAD filter:** Voice Activity Detection skips silence for faster processing

**Performance by hardware:**

| Hardware | Model | Compute Type | Speed (10s audio) |
|----------|-------|--------------|---------------------|
| NVIDIA GPU (4GB+) | large-v3-turbo | float16 | ~0.5s |
| NVIDIA GPU (8GB+) | large-v3 | float16 | ~1.5s |
| CPU (4 cores) | large-v3-turbo | int8 | ~3-5s |
| CPU (8 cores) | large-v3-turbo | int8 | ~2-3s |

### TTS: Microsoft Edge TTS

Text-to-speech uses [edge-tts](https://github.com/rany2/edge-tts) (Microsoft's neural TTS, free, no API key needed).

**Supported languages and voices:**

| Language | Code | Voice | Gender |
|----------|------|-------|--------|
| Hindi | `hi` | `hi-IN-SwaraNeural` | Female |
| English | `en` | `en-IN-NeerjaNeural` | Female |
| Bengali | `bn` | `bn-IN-TanishaaNeural` | Female |
| Telugu | `te` | `te-IN-ShrutiNeural` | Female |
| Tamil | `ta` | `ta-IN-PallaviNeural` | Female |
| Marathi | `mr` | `mr-IN-AarohiNeural` | Female |
| Gujarati | `gu` | `gu-IN-DhwaniNeural` | Female |
| Kannada | `kn` | `kn-IN-SapnaNeural` | Female |
| Malayalam | `ml` | `ml-IN-SobhanaNeural` | Female |
| Odia | `or` | `or-IN-SubhasiniNeural` | Female |
| Punjabi | `pa` | `pa-IN-CharleenNeural` | Female |
| Urdu | `ur` | `ur-PK-UzmaNeural` | Female |

All voices are **female** for a consistent assistant persona. Output is MP3 (~1-2s latency for short utterances). Falls back to the default Hindi voice when a language-specific voice is unavailable.

### LLM: Google Gemini

The LLM provider uses [Google Gemini 3.5 Flash](https://ai.google.dev/) with native JSON schema enforcement.

- **Model:** `gemini-3.5-flash` (configurable via `GEMINI_MODEL`)
- **JSON enforcement:** `response_mime_type=application/json` + `response_schema` (Pydantic model)
- **Temperature:** 0.1 (deterministic extraction)
- **Retry logic:** Exponential backoff on 429/5xx errors (up to 6 retries, max 30s delay)
- **Response parsing:** Validates output against Pydantic model; never parses free text
- **Rate limit handling:** Honors server-suggested retry delay from 429 messages

---

## CPGRAMS Filing

### Session Lifecycle

1. **Link (one-time):** Citizen logs into CPGRAMS via the in-app WebView. Cookies are exported to the backend, replayed into a fresh Playwright browser context to prove they authenticate, then stored encrypted with AES-256-GCM.

2. **Auto-Renewal:** When the stored session expires or is rejected, the server re-logins from stored credentials (if the citizen opted in). CAPTCHA/OTP challenges are paused and sent to the citizen to solve in-app.

3. **Filing:** The submitter loads the stored session into a fresh Playwright browser, navigates through the V7 guided questionnaire (terms -> org -> category levels -> details -> CAPTCHA -> submit), and scrapes the registration ID from the confirmation page.

### Dedup Protection

Before filing, the system checks for duplicate complaints:

- **Window:** 7 days
- **Fingerprint:** SHA-256 of normalized `category|location|description`
- **Behavior:** Returns HTTP 409 with the existing registration ID if a match is found

### Portal DOM

All CSS/XPath selectors are centralized in `app/rpa/selectors.py`. CPGRAMS changes its DOM without notice, so selectors are verified against the live portal and marked with verification dates.

---

## Watchdog

### SLA Deadlines

| Category | SLA (days) | Urgency Tier | Examples |
|----------|------------|--------------|----------|
| Water (pani) | 30 | Essential services | Broken pipes, no supply |
| Electricity (bijli) | 30 | Essential services | Power cuts, billing errors |
| Road (sadak) | 45 | Infrastructure | Potholes, construction |
| Cleanliness (swachhata) | 30 | Sanitation | Garbage, sanitation |
| Government (sarkari) | 60 | Administrative | RTO, ration card |
| Other | 60 | General | Default fallback |

### Lifecycle

1. **Record:** On filing, the grievance is persisted with its registration ID, SLA deadline, and category
2. **Reconcile:** Periodic background scan flags any grievance past its deadline as "overdue" and drafts an appeal
3. **Escalate:** Citizen confirms the appeal via the app; the status moves to "escalated" and the citizen is notified (SMS + voice call hooks)
4. **Resolve:** Citizen (or portal) marks the grievance as resolved; status moves to "resolved"

### Appeal Template

When a grievance becomes overdue, Sahayak drafts a formal Hindi appeal letter:

```
Aadaraneeya Prabhari Mahoday,

Vishay: Shikayat {reg_id} par anumodit samay (SLA) ke andar samadhan na
hone par doosri appeal.

Maine {ministry} mein nimn shikayat darj ki thi:
Shikayat varnan: {description}
Sthaan: {location}
Shikayat darj karne ki tithi: {filed}
Nirdhaarit samay-seema ({sla_days} din) is tithi ko samapt ho gayi: {deadline}.
Aaj tak samadhan nahi mila hai, aur yeh shikayat ab {overdue} din overdue hai.

Kripya is shikayat ki karvaai mein tejee laayein aur jald se jald samadhan
sure karein. Anya kisi prakar ke prashn ke liye mujhse sampark karein.

Shikayatkarta: {name}, {contact}
Mool shikayat pankjiyan sankhya: {reg_id}
```

---

## Security

### Encryption

- **Algorithm:** AES-256-GCM (Authenticated Encryption with Associated Data)
- **Key:** 32-byte base64-encoded key (`SAHAYAK_SESSION_ENCRYPTION_KEY`)
- **AAD:** Additional authenticated data (`sahayak-session-v1` for sessions, `sahayak-credentials-v1` for credentials)
- **Nonce:** 12-byte random nonce per encryption operation
- **Tamper detection:** GCM auth tag ensures integrity; tampered blobs are auto-dropped

### Session Management

- **TTL:** 24 hours (configurable via `SAHAYAK_SESSION_TTL_HOURS`)
- **Auto-expire:** Expired sessions are deleted on read
- **Atomic writes:** Write to `.tmp` then `os.replace()` to prevent corruption
- **File permissions:** `0600` (owner read/write only)

### What Is Encrypted

| Data | Encrypted | Storage |
|------|-----------|---------|
| CPGRAMS session cookies | Yes | `data/sessions/` |
| CPGRAMS login credentials | Yes | `data/credentials/` |
| Grievance records | No | `data/watchdog/` (public complaint data) |
| API keys | No | `.env` (gitignored, never in code) |
| Conversation history | No | In-memory only (lost on restart) |
| Evidence PDFs | No | `data/evidence/` (local files) |

---

## Mobile App

### Build

```bash
cd mobile
flutter pub get
flutter build apk
```

The release APK is output to `build/app/outputs/flutter-apk/app-release.apk`.

Pre-built APKs are also available in the project root:
- `Sahayak-v1.2.0.apk`
- `Sahayak-v1.2.1.apk`
- `Sahayak-v1.2.2.apk`

### App Flow

1. **Consent** — First-open data consent dialog
2. **Language** — Select from 11 supported languages (Hindi, English, Bengali, Telugu, Tamil, Marathi, Gujarati, Kannada, Malayalam, Punjabi, Urdu)
3. **Login** — Create local profile (name + mobile number)
4. **Home** — Dashboard with mic button, CPGRAMS link status, grievance list
5. **Conversation** — Voice or text chat with the assistant; TTS plays responses
6. **CPGRAMS WebView** — In-app login to link CPGRAMS account (cookies exported to backend)
7. **File** — Submit the drafted complaint; registration ID returned
8. **Track** — View filed grievances, SLA deadlines, escalation status

### Screens

| Screen | Route | Purpose |
|--------|-------|---------|
| Consent | `/consent` | First-open data consent |
| Language | `/language` | Language selection (11 options) |
| Login | `/login` | Profile creation (name + mobile) |
| Home | `/home` | Main dashboard, mic button, services |
| Conversation | `/conversation` | Voice/text chat with assistant |
| CPGRAMS WebView | `/cpgrams` | In-app CPGRAMS login |
| Grievances | `/grievances` | Filed complaints list with SLA status |
| Profile | `/profile` | Account details + CPGRAMS link status |
| Logs | `/logs` | Debug logs viewer |

### Flutter Dependencies

| Package | Purpose |
|---------|---------|
| `record` | Microphone recording |
| `audioplayers` | Audio playback (TTS responses) |
| `webview_flutter` | In-app CPGRAMS login |
| `geolocator` | GPS location capture |
| `shared_preferences` | Local profile storage |
| `file_picker` | PDF evidence upload |
| `url_launcher` | WhatsApp draft sharing |
| `http` | Backend API communication |

---

## Deployment

### Local + Cloudflare Tunnel

```bash
# Start backend
uvicorn app.main:app --host 0.0.0.0 --port 8000

# Expose via tunnel (for mobile app access)
cloudflared tunnel run sahayak
```

### Docker

```bash
docker build -t sahayak .
docker run -p 8000:8000 --env-file .env sahayak
```

The Dockerfile uses Python 3.12-slim, installs all dependencies + Playwright Chromium, and exposes port 8000.

### Cloud (Free Tier Options)

| Provider | Specs | Fit | Notes |
|----------|-------|-----|-------|
| Oracle Cloud A1 (free forever) | 4 OCPU, 24GB RAM | Best | Runs everything including GPU-like STT |
| Hugging Face Spaces | 2 vCPU, 16GB RAM | Works | Sleeps on idle; STT runs on CPU |
| Your PC + cloudflared | Varies | Current setup | Development/testing |

### Resource Usage

| Resource | Idle | Under Load (STT + LLM) |
|----------|------|-------------------------|
| RAM | ~500MB | ~3-4GB (Whisper model) |
| CPU | <5% | 50-80% (STT processing) |
| Disk | ~2GB (model cache) | ~2.5GB |
| Network | Minimal | Outbound to Gemini + Edge TTS |

---

## Hardware Requirements

| Tier | CPU | RAM | GPU | Storage | Use Case |
|------|-----|-----|-----|---------|----------|
| **Minimum** | 4 cores | 8GB | None (CPU int8) | 10GB | Development, testing, low volume |
| **Recommended** | 4+ cores | 16GB | NVIDIA 4GB+ VRAM | 20GB | Production, fast STT (~0.5s) |
| **Cloud** | 4 OCPU | 24GB | Optional | 20GB | Oracle A1 free tier, HF Spaces |

**Notes:**
- STT is the most resource-intensive component. GPU acceleration reduces transcription from ~3-5s to ~0.5s per utterance.
- The Gemini LLM and Edge TTS are cloud-based; they require internet but no local compute.
- The Playwright browser automation uses ~200MB RAM per filing session.

---

## Testing

### Run Tests

```bash
# Run all tests
python -m pytest tests/ -q

# Run with verbose output
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_conversation_flow.py -v

# Run specific test
python -m pytest tests/test_conversation_flow.py::test_collects_all_fields -v
```

### Smoke Test Providers

```bash
# Test STT
python -m scripts.smoke_test stt samples/test.wav

# Test TTS
python -m scripts.smoke_test tts "नमस्ते"

# Test LLM
python -m scripts.smoke_test llm
```

### Test Coverage

| Test File | What It Tests |
|-----------|---------------|
| `test_conversation_flow.py` | Multi-turn conversation logic, slot filling, state transitions |
| `test_prompts.py` | System prompt generation, language rules, field descriptions |
| `test_watchdog.py` | SLA deadline calculation, overdue detection, appeal drafting |
| `test_rpa_catalog.py` | Ministry fuzzy matching, exact/prefix/similarity matching |
| `test_rpa_models.py` | GrievancePayload normalization, category key mapping |
| `test_session_store.py` | AES-256-GCM encryption, atomic writes, TTL expiry |
| `test_credential_store.py` | Credential encryption, tamper detection, file permissions |
| `test_local_providers.py` | STT provider initialization, device detection |
| `test_edge_tts.py` | TTS voice selection, language fallback |
| `test_cpgrams_profile.py` | Profile scraping logic, field extraction |

---

## Troubleshooting

### 1. STT Error: "int8_float16" not supported

**Symptom:** `RuntimeError: int8_float16 backend is not supported`

**Solution:** Set `LOCAL_STT_COMPUTE_TYPE=int8` for CPU or `LOCAL_STT_COMPUTE_TYPE=float16` for GPU. The value `int8_float16` is not a valid compute type. If left empty, the system auto-detects the best option.

### 2. CUDA Error: "libcublas not found"

**Symptom:** `OSError: libcublas.so.12: cannot open shared object file`

**Solution:** Install CUDA toolkit or run on CPU. The system auto-preloads CUDA libraries from pip packages (`nvidia-cublas-cu12`, `nvidia-cudnn-cu12`), but if those are not installed, it falls back to CPU int8 automatically. Alternatively:
```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

### 3. Slow First Boot (30-60 seconds)

**Symptom:** First API call hangs for ~30 seconds while "Transcribing..."

**Solution:** This is normal. The Whisper model (~1.6GB) loads lazily on first use. The server preloads it in a background thread during startup, but the first real request may still wait if the preload has not finished. Subsequent requests are fast. To avoid this, wait 30 seconds after starting the server before making requests.

### 4. Cloudflare Tunnel Error 530

**Symptom:** HTTP 530 when accessing via Cloudflare tunnel

**Solution:** The tunnel is not connected or the backend is not running. Check:
```bash
# Is the backend running?
curl http://localhost:8000/health

# Is the tunnel active?
cloudflared tunnel run sahayak
```

---

## License

Private — All rights reserved.
