# Call Recordings Sentiment Dashboard (React + FastAPI)

This project ingests `.txt` transcript files and audio call recordings from a Google Drive folder, transcribes audio to text, performs sentiment analysis, applies strict admission intent classification, stores results in PostgreSQL, and shows analytics in a React dashboard.

## Stack

- Frontend: React (Vite) + Recharts
- Backend: FastAPI + SQLAlchemy
- Database: PostgreSQL
- Integrations: Google Drive API (Service Account or OAuth refresh token), Google Speech-to-Text, OpenAI API, optional Gemini API

## Project structure

- `frontend/` React dashboard
- `backend/` FastAPI API server
- `.env.example` environment variables
- `docker-compose.yml` PostgreSQL service

## 1) Prerequisites

- Python 3.11+
- Node.js 18+
- Docker Desktop (for PostgreSQL)

## 2) Database options

### Option A: Run with local SQLite (default)

No extra setup is required. If `DATABASE_URL` is not set, backend uses:

```text
sqlite:///./call_records.db
```

### Option B: Use PostgreSQL via Docker

```bash
docker compose up -d
```

## 3) Configure environment

Copy `.env.example` to `.env` in the workspace root and fill values.

Important notes:
- Google auth mode: Service Account (recommended) or OAuth refresh token.
- Ensure `GOOGLE_DRIVE_FOLDER_ID` points to the folder with `.txt` transcripts.
- Audio discovery scans nested subfolders by default (`DRIVE_SCAN_RECURSIVE=true`).
- Set `OPENAI_API_KEY`.
- Set `DATABASE_URL` only if you want PostgreSQL instead of default SQLite.

### Google auth mode A: Service Account (recommended)

Set either:
- `GOOGLE_SERVICE_ACCOUNT_FILE` to an absolute path of your JSON key file, or
- `GOOGLE_SERVICE_ACCOUNT_JSON` with full JSON content.

Optional:
- `GOOGLE_SERVICE_ACCOUNT_SUBJECT` for Google Workspace domain-wide delegation impersonation.

If using a personal/shared Drive folder, share that folder with the service-account email from the JSON file.

### Google auth mode B: OAuth refresh token

### Get Google refresh token quickly (helper endpoints)

Use this only for OAuth mode (when `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, and `GOOGLE_REFRESH_TOKEN` are used).

After backend starts:

1. Open `http://localhost:8000/api/google/auth-url` and copy `auth_url`.
2. Open that URL in your browser and approve access.
3. Google redirects to your configured callback endpoint with a `code`.
4. The API responds with `refresh_token` (first consent may be required to receive it).
5. Put that value in `GOOGLE_REFRESH_TOKEN` in your `.env`.

## 4) Run backend

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -e .
set PYTHONPATH=.
uvicorn app.main:app --reload --port 8000
```

## 5) Run frontend

```bash
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`.

### Windows quick start (recommended)

From repository root:

```powershell
./scripts/dev-server.ps1 start
```

Useful commands:

```powershell
./scripts/dev-server.ps1 status
./scripts/dev-server.ps1 stop
```

This helper avoids common local issues where stale processes already occupy ports `8000` and `5173`.

### Manual frontend command (Windows)

If you start frontend manually, prefer:

```powershell
npx vite --host 127.0.0.1 --port 5173
```

This avoids npm argument parsing quirks that can happen with `npm run dev -- --host ... --port ...` in some shells.

## 6) Use the dashboard

1. Click **Fetch from Drive**.
2. Backend lists `.txt` files and supported audio files from Google Drive, then skips already ingested `drive_file_id` values.
3. For audio files, backend transcribes calls first and then analyzes the generated transcript.
4. Backend stores:
   - score (`-1` to `1`)
   - label (`positive`, `neutral`, `negative`)
   - intent category (`Interested`, `Not Interested`, `Follow-up Needed`, `Inquiry`, `Already Enrolled`, `Spam`, `IGNORE`)
   - explanation, summary, and keywords
5. Dashboard refreshes trend/distribution/per-call views.

Filtering applied during ingest:
- `.txt` transcript files (filename keyword match) and supported audio (`.mp3`, `.wav`, `.m4a`, `.flac`, `.ogg`, `.amr`, `.aac`)
- `.txt` filename must contain `transcript` (configurable via `TRANSCRIPT_FILENAME_KEYWORD`)
- minimum content length enforced via `TRANSCRIPT_MIN_CHARS` (default `30`)
- allowed transcript languages for audio are configurable via `ALLOWED_TRANSCRIPT_LANGUAGES` (default `en,hi,te`)

For re-transcribing existing call recordings with better quality:
- Enable `Force reprocess duplicates` in the dashboard.
- Enable `Process only audio files` to skip `.txt` files and speed up reruns.
- Or call `POST /api/ingest/run?limit=50&audio_only=true&force_reprocess=true`.

Audio transcription quality/performance knobs:
- `TRANSCRIPTION_PROVIDER` (`google_speech` or `gemini`)
- `GOOGLE_SPEECH_MODEL` (default `phone_call`)
- `GOOGLE_SPEECH_USE_ENHANCED` (default `true`)
- `TRANSCRIPTION_LONG_RUNNING_THRESHOLD_SECONDS` (switch to long-running STT above this duration)
- `TRANSCRIPTION_POLL_INTERVAL_SECONDS` (poll interval for long-running STT)
- `TRANSCRIPTION_NORMALIZE_AUDIO` (normalize audio to mono 16k FLAC before STT)
- `GEMINI_TRANSCRIPTION_MODEL` (used when `TRANSCRIPTION_PROVIDER=gemini`)
- `GEMINI_TRANSCRIPTION_INLINE_MAX_MB` (max inline audio size for Gemini request)

Use AI Studio key for transcription (no Speech API required):
- Set `TRANSCRIPTION_PROVIDER=gemini`
- Set `GEMINI_API_KEY=<your-ai-studio-key>`
- Keep Drive auth configured (`GOOGLE_SERVICE_ACCOUNT_JSON/FILE` or OAuth) for file listing/download

### Intent classifier output contract

The intent classifier stage follows a strict two-line format internally:

```text
INTENT: <Interested / Not Interested / Follow-up Needed / Inquiry / Already Enrolled / Spam / IGNORE>
SUMMARY: <Short English summary OR IGNORE>
```

Behavior rules:
- Summary is always normalized to English.
- If transcript content is not meaningful, output is forced to `IGNORE`/`IGNORE`.

## Fetch from a specific Google Drive folder path

You can ingest from either:
- a raw folder ID
- a full Google Drive folder URL

API example:

```bash
POST /api/ingest/run?folder=https://drive.google.com/drive/folders/1ABCDEF...&limit=25
```

Or:

```bash
POST /api/ingest/run?folder=1ABCDEF...&limit=25
```

If `folder` is omitted, backend uses `GOOGLE_DRIVE_FOLDER_ID` from `.env`.
If `limit` is omitted, backend uses `INGEST_DEFAULT_LIMIT` from `.env` (default `25`).

## API endpoints

- `GET /health`
- `GET /api/google/auth-url`
- `GET /api/google/callback`
- `POST /api/ingest/run`
- `GET /api/dashboard/trend`
- `GET /api/dashboard/distribution`
- `GET /api/dashboard/intent-distribution`
- `GET /api/dashboard/calls`
- `GET /api/dashboard/calls/{transcript_id}`

## Production operations notebook

Use `operations/production_pipeline.ipynb` to run health checks, trigger ingest batches, and verify top call intent/summary outputs against the deployed API.

## 7) Free cloud deploy (Render + free Postgres)

This repo includes `render.yaml` for a free one-service deploy where FastAPI serves both API and the built React app.

For a copy-ready checklist, see `README_DEPLOY.md`.

Use any free Postgres provider (Neon or Supabase) and paste its connection string into Render.

### Steps

1. Create a free Postgres database in Neon or Supabase.
2. Copy its connection string.
3. Push your latest changes to GitHub.
4. In Render, choose **New +** -> **Blueprint** and select your repo.
5. Render reads `render.yaml` and creates one free web service.
6. In Render service settings, set environment variables:
   - `DATABASE_URL` (from Neon/Supabase)
   - `GOOGLE_SERVICE_ACCOUNT_FILE` or `GOOGLE_SERVICE_ACCOUNT_JSON`
   - `GOOGLE_SERVICE_ACCOUNT_SUBJECT` (optional)
   - `GOOGLE_SPEECH_LANGUAGE_CODES` (example: `["en-US","hi-IN","te-IN"]`)
   - `GOOGLE_CLIENT_ID` (OAuth mode only)
   - `GOOGLE_CLIENT_SECRET` (OAuth mode only)
   - `GOOGLE_REFRESH_TOKEN` (OAuth mode only)
   - `GOOGLE_DRIVE_FOLDER_ID`
   - `GOOGLE_REDIRECT_URI`
   - `AUDIO_INGEST_ENABLED`
   - `ALLOWED_TRANSCRIPT_LANGUAGES` (example: `["en","hi","te"]`)
   - `TRANSCRIPTION_TIMEOUT_SECONDS`
   - `TRANSCRIPTION_MAX_AUDIO_MB`
   - `OPENAI_API_KEY`
   - `GEMINI_ENABLED` and `GEMINI_API_KEY` (optional strict intent classifier provider)
   - `CORS_ORIGINS`

### Important values

- `GOOGLE_REDIRECT_URI`
   - `https://<your-render-service-domain>/api/google/callback`
- `CORS_ORIGINS` (JSON array)
   - `["https://<your-render-service-domain>"]`

After deploy, open `https://<your-render-service-domain>/health` and then the root URL.
