"""Gemini-backed, grounded message composition with a deterministic safety fallback."""
from __future__ import annotations

import json
import os
import re
from typing import Any

from dotenv import load_dotenv
from google import genai
from google.genai import types

load_dotenv()
from prompts import build_prompt, family_for_trigger

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def _extract_json(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = "\n".join(x for x in text.splitlines() if not x.strip().startswith("```"))
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        text = text[start:end + 1]
    result = json.loads(text)
    if not isinstance(result, dict):
        raise ValueError("Gemini response was not a JSON object")
    return result


def _payloads(trigger: dict) -> list[dict]:
    out = [trigger]
    p = trigger.get("payload")
    if isinstance(p, dict):
        out.append(p)
    return out


def _first(dcts: list[dict], *paths: str):
    for d in dcts:
        for path in paths:
            cur: Any = d
            for key in path.split("."):
                if not isinstance(cur, dict) or key not in cur:
                    cur = None
                    break
                cur = cur[key]
            if cur not in (None, "", []):
                return cur
    return None


def _decision_brief(category, merchant, trigger, customer) -> str:
    """Give GPT a compact, deterministic signal-selection hint."""
    tp = _payloads(trigger)
    kind = str(_first(tp, "kind", "trigger_kind") or "update")
    hints = [f"trigger family={family_for_trigger(kind)}", f"trigger kind={kind}"]

    perf = merchant.get("performance") or {}
    for label, paths in {
        "metric": ["metric", "headline_metric", "views", "orders", "bookings", "rating", "ctr"],
        "change": ["change", "delta", "change_pct", "growth_pct"],
        "benchmark": ["peer_median", "benchmark", "prior_period"],
    }.items():
        val = _first(tp, *paths) or _first([perf], *paths)
        if val not in (None, "", []):
            hints.append(f"{label}={val}")

    offer = _first(tp, "offer", "active_offer", "top_offer")
    if offer:
        hints.append(f"existing_offer={offer}")
    item = _first(tp, "top_item", "research_item", "digest_item", "headline", "title")
    if item:
        hints.append(f"trigger_asset={item}")

    if customer:
        ci = customer.get("identity") or {}
        if ci.get("name"):
            hints.append(f"customer_name={ci['name']}")
        history = customer.get("history") or customer.get("relationship")
        if history:
            hints.append(f"customer_history={history}")

    return "; ".join(hints)


def _fallback_compose(category, merchant, trigger, customer) -> dict[str, Any]:
    """Produce a useful message without inventing facts if Gemini is unavailable."""
    tp = _payloads(trigger)
    name = _first([merchant], "identity.name", "name") or "there"
    kind = str(_first(tp, "kind", "trigger_kind") or "update")
    anchor = _first(tp, "headline", "title", "message", "summary", "top_item.title", "research_item.title")
    offer = _first(tp, "offer.name", "offer.title", "active_offer.name", "active_offer.title")
    price = _first(tp, "offer.price", "active_offer.price")
    metric = _first(tp, "metric", "headline_metric", "views", "orders", "bookings", "ctr") or _first([merchant.get("performance") or {}], "metric", "views", "orders", "bookings", "ctr")
    change = _first(tp, "change", "delta", "change_pct", "growth_pct")
    value = _first(tp, "value", "current_value", "metric_value", "count")
    window_days = _first(tp, "window_days", "days", "period_days")

    if customer:
        cname = _first([customer], "identity.name", "name") or "there"
        preference = _first([customer], "preferences.preferred_time", "preference", "preferences.language")
        if anchor:
            body = f"Hi {cname}, {anchor}. Want to take the next step?"
        elif offer:
            suffix = f" at {price}" if price else ""
            body = f"Hi {cname}, {offer}{suffix} is available. Want to take the next step?"
        elif preference:
            body = f"Hi {cname}, I have a quick update for you. Does {preference} still work?"
        else:
            body = f"Hi {cname}, a quick update from {name}. Would you like me to help with the next step?"
        return {"body": body, "cta": "open_ended", "rationale": f"Customer-safe {family_for_trigger(kind)} message using supplied context only."}

    if anchor:
        body = f"{name}, {anchor}. Want me to turn this into the next step?"
    elif metric is not None and change is not None:
        body = f"{name}, your {metric} changed by {change}. Want me to help act on it?"
    elif metric is not None and value is not None and window_days is not None:
        body = f"{name}, your {metric} reached {value} in the last {window_days} days. Want me to help act on it?"
    elif metric is not None and value is not None:
        body = f"{name}, your {metric} reached {value} on the latest update. Want me to help act on it?"
    elif metric is not None:
        body = f"{name}, your {metric} has a latest update. Want me to help decide the next step?"
    elif offer:
        suffix = f" at {price}" if price else ""
        body = f"{name}, your existing offer {offer}{suffix} is ready to use. Want me to work from it?"
    else:
        body = f"{name}, there’s a {kind} update. Want me to help with the next step?"
    return {"body": body, "cta": "open_ended", "rationale": f"Used the strongest verified {family_for_trigger(kind)} signal; no unsupported facts added."}


def _call_gemini(prompt: str) -> dict[str, Any]:
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    client = genai.Client(
        api_key=key,
        http_options=types.HttpOptions(timeout=12000),
    )
    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                system_instruction=(
                    "You are Vera's production message composer. Follow the prompt exactly. "
                    "Return ONLY a JSON object with body, cta, rationale. "
                    "Never invent facts, numbers, offers, dates, actions, or customer details."
                ),
                response_mime_type="application/json",
                max_output_tokens=500,
                temperature=0.2,
            ),
        )
        text = response.text
        if not text:
            raise ValueError("Gemini returned no text")
    finally:
        client.close()
    return _extract_json(text)


def compose(category, merchant, trigger, customer=None, recent_turns=None):
    recent_turns = recent_turns or []
    brief = _decision_brief(category, merchant, trigger, customer)
    prompt = build_prompt(category, merchant, trigger, customer, recent_turns[-8:], brief)
    try:
        result = _call_gemini(prompt)
        if not isinstance(result.get("body"), str) or not result["body"].strip():
            raise ValueError("Gemini returned empty body")
        result.setdefault("cta", "open_ended")
        result.setdefault("rationale", "Grounded in supplied Vera contexts.")
        return result
    except Exception:
        return _fallback_compose(category, merchant, trigger, customer)
