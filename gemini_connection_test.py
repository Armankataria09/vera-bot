"""Verify that the local Gemini API key and configured free-tier model can answer."""
from __future__ import annotations

import os
from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
key = os.getenv("GEMINI_API_KEY")
model = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
print(f"Gemini model: {model}")
print("Gemini key: LOADED" if key else "Gemini key: MISSING")

if not key:
    raise SystemExit(1)

client = genai.Client(
    api_key=key,
    http_options=types.HttpOptions(timeout=15000),
)
try:
    response = client.models.generate_content(
        model=model,
        contents="Reply with exactly GEMINI_OK",
        config=types.GenerateContentConfig(
            max_output_tokens=64,
            thinking_config=types.ThinkingConfig(thinking_level="low"),
        ),
    )
    text = (response.text or "").strip()
    if not text:
        print("Gemini returned no visible text.")
        print(f"Response object: {response!r}")
        candidates = getattr(response, "candidates", None) or []
        for i, candidate in enumerate(candidates):
            print(f"Candidate {i}: {candidate!r}")
finally:
    client.close()

print(f"Gemini response: {text}")
if text != "GEMINI_OK":
    raise SystemExit(1)
print("Gemini connection: PASS")
