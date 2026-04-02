# Call Recordings Sentiment Dashboard (React + FastAPI)

This project ingests `.txt` transcript files from a Google Drive folder, performs sentiment analysis using OpenAI API, stores results in PostgreSQL, and shows analytics in a React dashboard.

## Stack

- Frontend: React (Vite) + Recharts
- Backend: FastAPI + SQLAlchemy
- Database: PostgreSQL
- Integrations: Google Drive API (OAuth refresh token), OpenAI API

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
- Use a Google OAuth **refresh token** from your user account.
- Ensure `GOOGLE_DRIVE_FOLDER_ID` points to the folder with `.txt` transcripts.
- Set `OPENAI_API_KEY`.
- Set `DATABASE_URL` only if you want PostgreSQL instead of default SQLite.

### Get Google refresh token quickly (helper endpoints)

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

## 6) Use the dashboard

1. Click **Fetch from Drive**.
2. Backend lists `.txt` files from Google Drive and skips already ingested `drive_file_id` values.
3. Backend runs sentiment analysis for new files and stores:
   - score (`-1` to `1`)
   - label (`positive`, `neutral`, `negative`)
   - explanation and keywords
4. Dashboard refreshes trend/distribution/per-call views.

Filtering applied during ingest:
- only `.txt` files
- filename must contain `transcript` (configurable via `TRANSCRIPT_FILENAME_KEYWORD`)
- minimum content length enforced via `TRANSCRIPT_MIN_CHARS` (default `30`)

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
- `GET /api/dashboard/calls`
- `GET /api/dashboard/calls/{transcript_id}`

## 7) Cloud deploy (Render)

This repo includes `render.yaml` for one-service cloud deployment where FastAPI serves both API and the built React app.

### Steps

1. Push your latest changes to GitHub.
2. In Render, choose **New +** -> **Blueprint**.
3. Select your GitHub repository.
4. Render reads `render.yaml` and creates:
    - one web service (`call-records-dashboard`)
    - one Postgres database (`call-records-db`)
5. Set secret environment variables in Render service settings:
    - `GOOGLE_CLIENT_ID`
    - `GOOGLE_CLIENT_SECRET`
    - `GOOGLE_REFRESH_TOKEN`
    - `GOOGLE_DRIVE_FOLDER_ID`
    - `GOOGLE_REDIRECT_URI`
    - `OPENAI_API_KEY`
    - `CORS_ORIGINS`

### Important values for Render

- Set `GOOGLE_REDIRECT_URI` to:
   - `https://<your-render-service-domain>/api/google/callback`
- Set `CORS_ORIGINS` to JSON array, e.g.:
   - `["https://<your-render-service-domain>"]`

After deploy, open `https://<your-render-service-domain>/health` and then the root URL to access the dashboard.
