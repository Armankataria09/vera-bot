"""Deterministic, replay-safe WhatsApp conversation policy."""
from __future__ import annotations
import re
from typing import Any

AUTO_REPLY_MARKERS = ("thank you for contacting", "thanks for contacting", "your message has been received", "our team will get back", "automated assistant", "this is an automated", "we have received your message", "thanks for the message", "thank you for the message", "thanks for reaching out", "thank you for reaching out", "thanks for getting in touch", "thank you for getting in touch")
NEGATIVE_MARKERS = ("not interested", "no thanks", "don't want", "do not want", "stop", "remove me", "not required", "leave it")
WAIT_MARKERS = ("later", "give me some time", "let me think", "call me later", "not now")
POSITIVE_MARKERS = ("let's do it", "lets do it", "go ahead", "yes", "do it", "please proceed", "i want to join", "join", "sign me up", "okay proceed", "send it", "send me")
OFF_TOPIC_MARKERS = (
    "gst filing", "income tax", "itr", "tax return", "personal loan", "loan application",
    "weather", "temperature", "forecast", "rain tomorrow", "will it rain",
    "cricket", "football", "soccer", "basketball", "match score",
    "movie", "movies", "netflix", "youtube", "instagram",
    "stock price", "share price", "bitcoin", "crypto",
    "politics", "election", "news today", "current affairs",
)

OFF_TOPIC_QUESTION_PATTERNS = (
    r"\bwhat(?:'s| is) the weather\b",
    r"\bweather (?:today|tomorrow|this week)\b",
    r"\bwill it rain\b",
    r"\bwhat(?:'s| is) the temperature\b",
    r"\bwho (?:won|is winning) (?:the )?(?:match|game)\b",
    r"\bwhat(?:'s| is) (?:the )?(?:score|news)\b",
)

def normalize(text: str) -> str:
    return " ".join(text.lower().split())

def looks_like_auto_reply(message: str, history: list[dict[str, Any]]) -> bool:
    msg = normalize(message)
    if any(x in msg for x in AUTO_REPLY_MARKERS):
        return True
    return sum(normalize(str(t.get("message", ""))) == msg for t in history if t.get("from") != "vera") >= 2

def classify_intent(message: str) -> str:
    msg = normalize(message)
    if any(x in msg for x in NEGATIVE_MARKERS): return "stop"
    if any(x in msg for x in WAIT_MARKERS): return "wait"
    if any(x in msg for x in POSITIVE_MARKERS): return "action"
    if any(x in msg for x in OFF_TOPIC_MARKERS): return "off_topic"
    if any(re.search(pattern, msg) for pattern in OFF_TOPIC_QUESTION_PATTERNS): return "off_topic"
    return "unknown"

def respond(conversation_id: str, message: str, history: list[dict[str, Any]]) -> dict[str, Any]:
    if looks_like_auto_reply(message, history):
        return {"action": "end", "rationale": "Detected a canned/repeated reply; ending to avoid an auto-reply loop."}
    intent = classify_intent(message)
    if intent == "stop":
        return {"action": "end", "rationale": "Explicit stop/negative intent detected; no further outreach."}
    if intent == "wait":
        return {"action": "wait", "wait_seconds": 1800, "rationale": "User asked for time; Vera backs off instead of pushing."}
    if intent == "off_topic":
        return {
            "action": "end",
            "rationale": "Detected a clearly unrelated request; do not invent an answer or continue the merchant outreach."
        }
    if intent == "action":
        return {"action": "send", "body": "Absolutely — I’ll move ahead using the details already in this chat. If anything is missing, I’ll ask for just that.", "cta": "open_ended", "rationale": "Explicit action intent detected; transition directly to execution without re-selling."}
    return {"action": "send", "body": "Got it. What’s the one thing you want to do next?", "cta": "open_ended", "rationale": "Ambiguous reply; asks one low-friction clarifier without inventing intent."}
