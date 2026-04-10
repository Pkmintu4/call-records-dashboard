# Deploy Guide (Free + Simple)

This guide deploys the full project with minimal ops overhead:
- Backend + built frontend in one Render service
- Managed Postgres on Neon/Supabase free tier
- Google Drive ingest + audio transcription + strict intent summary

## 1. Prerequisites

- GitHub repo with latest code pushed
- Render account
- Neon or Supabase Postgres connection string
- Google Cloud project with:
  - Drive API enabled
  - Speech-to-Text API enabled
  - Service account JSON key
  - Shared Drive folder access for service-account email
- OpenAI API key
- Optional: Gemini API key

## 2. Security first (required)

Rotate old keys before production use:
- Google service account key
- OpenAI key
- Any OAuth refresh token/client secret previously exposed

Never commit credential JSON files.

## 3. Deploy backend+frontend on Render

This repo already includes `render.yaml` for blueprint deploy.

Steps:
1. Render Dashboard -> New + -> Blueprint
2. Select this GitHub repo
3. Confirm service settings from `render.yaml`
4. Set all required environment variables below
5. Deploy

## 4. Required env vars (Render)

Core:
- `APP_ENV=prod`
- `DATABASE_URL=<postgres connection string>`
- `CORS_ORIGINS=["https://<your-render-service>.onrender.com"]`

Google auth (service account recommended):
- `GOOGLE_SERVICE_ACCOUNT_JSON=<full json as one-line string>`
- or `GOOGLE_SERVICE_ACCOUNT_FILE=<path inside container>` (not recommended on Render free)
- `GOOGLE_SERVICE_ACCOUNT_SUBJECT=` (optional)
- `GOOGLE_DRIVE_FOLDER_ID=<folder id>`
- `GOOGLE_REDIRECT_URI=https://<your-render-service>.onrender.com/api/google/callback`

Transcription:
- `AUDIO_INGEST_ENABLED=true`
- `TRANSCRIPTION_PROVIDER=google_speech` (or `gemini` to use AI Studio key)
- `GOOGLE_SPEECH_LANGUAGE_CODES=["en-US","hi-IN","te-IN"]`
- `GOOGLE_SPEECH_MODEL=phone_call`
- `GOOGLE_SPEECH_USE_ENHANCED=true`
- `ALLOWED_TRANSCRIPT_LANGUAGES=["en","hi","te"]`
- `TRANSCRIPTION_TIMEOUT_SECONDS=180`
- `TRANSCRIPTION_POLL_INTERVAL_SECONDS=2`
- `TRANSCRIPTION_LONG_RUNNING_THRESHOLD_SECONDS=55`
- `TRANSCRIPTION_NORMALIZE_AUDIO=true`
- `TRANSCRIPTION_MAX_AUDIO_MB=25`
- `GEMINI_TRANSCRIPTION_MODEL=gemini-1.5-flash` (when using `TRANSCRIPTION_PROVIDER=gemini`)
- `GEMINI_TRANSCRIPTION_INLINE_MAX_MB=18` (when using `TRANSCRIPTION_PROVIDER=gemini`)

LLM analysis:
- `OPENAI_API_KEY=<openai key>`
- `OPENAI_MODEL=gpt-4.1-mini`

Optional Gemini classifier:
- `GEMINI_ENABLED=false` (or true)
- `GEMINI_API_KEY=<gemini key>`
- `GEMINI_MODEL=gemini-1.5-flash`
- `GEMINI_TIMEOUT_SECONDS=60`

Ingest behavior:
- `AUTO_INGEST_ENABLED=false` (recommended for free tier)

## 5. Verify deployment

Run these after deploy:

```powershell
Invoke-RestMethod https://<your-render-service>.onrender.com/health
```

```powershell
Invoke-RestMethod -Method Post "https://<your-render-service>.onrender.com/api/ingest/run?limit=5"
```

```powershell
Invoke-RestMethod "https://<your-render-service>.onrender.com/api/dashboard/calls?limit=10"
```

Expected:
- `/health` returns status ok
- ingest returns processed/skipped counters
- calls endpoint returns rows with `intent_category` and `summary`

## 6. Optional frontend-only Vercel deploy

Not required if you use Render single-service mode (already serves frontend).

If you still want Vercel frontend:
- Root directory: `frontend`
- Build command: `npm run build`
- Output dir: `dist`
- Set `VITE_API_BASE_URL=https://<your-render-service>.onrender.com`

## 7. Production notebook

Use:
- `operations/production_pipeline.ipynb`

Set env vars before running notebook:
- `CALL_RECORDS_API_BASE`
- `CALL_RECORDS_DRIVE_FOLDER` (optional)
- `CALL_RECORDS_INGEST_LIMIT` (optional)

The notebook executes health, ingest, and call-summary verification steps.
