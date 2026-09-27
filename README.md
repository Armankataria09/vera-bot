# Magicpin Vera AI Challenge — Gemini Free-Tier Edition

Stateful FastAPI message engine for the Magicpin Vera AI Challenge.

Architecture:

`HTTP API → ContextStore → trigger routing → Gemini 3.8 Flash composer → deterministic validators → action`

## LLM configuration

This version uses Google's Gemini API through Google's official Gemini API. Google's current pricing documentation lists `gemini-3.8-flash` with a free tier.

Create a local `.env` file from `.env.example`:

```text
GEMINI_API_KEY=your_real_gemini_api_key
GEMINI_MODEL=gemini-3.8-flash
```

Never commit or submit `.env`.

## Windows setup

From the folder containing `requirements.txt`:

```powershell
python -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Verify the API key/model:

```powershell
python gemini_connection_test.py
```

Start the bot:

```powershell
uvicorn bot:app --host 0.0.0.0 --port 8000
```

Health:

`http://127.0.0.1:8000/v1/healthz`

Swagger:

`http://127.0.0.1:8000/docs`

## Challenge endpoints

- `POST /v1/context`
- `POST /v1/tick`
- `POST /v1/reply`
- `GET /v1/healthz`
- `GET /v1/metadata`
- `POST /v1/teardown` (optional)

## Design safeguards

- Versioned stateful context store.
- Trigger-family routing and deterministic signal selection.
- Grounded Gemini generation: no unsupported numbers, offers, dates, actions, or customer facts.
- Customer consent and merchant ownership checks.
- Suppression and conversation-level anti-repeat behavior.
- Deterministic reply handling for stop, wait, auto-reply and intent-transition cases.
- Deterministic fallback if Gemini is unavailable.
- Maximum 20 actions per tick.
- Public metadata identifies the configured model.

## Submission

Deploy the service and submit its public base URL to the challenge. Keep the deployment reachable during evaluation.
