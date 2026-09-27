"""
Magicpin Vera AI Challenge - integrated FastAPI server.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

import os

from fastapi import FastAPI
from pydantic import BaseModel, Field

from compose import compose
from replies import respond
from store import state
from validators import validate_output

START_TIME = time.time()

app = FastAPI(title="Magicpin Vera Bot", version="1.0.0")

ALLOWED_SCOPES = {"category", "merchant", "customer", "trigger"}


class ContextBody(BaseModel):
    scope: Literal["category", "merchant", "customer", "trigger"]
    context_id: str = Field(min_length=1)
    version: int = Field(ge=0)
    payload: dict[str, Any]
    delivered_at: str


class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class ReplyBody(BaseModel):
    conversation_id: str = Field(min_length=1)
    merchant_id: str | None = None
    customer_id: str | None = None
    from_role: str
    message: str
    received_at: str
    turn_number: int = Field(ge=1)


@app.get("/v1/healthz")
async def healthz() -> dict[str, Any]:
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START_TIME),
        "contexts_loaded": state.contexts.counts(),
    }


@app.get("/v1/metadata")
async def metadata() -> dict[str, Any]:
    return {
        "team_name": "Arman",
        "team_members": ["Arman Kataria"],
        "model": os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        "approach": "stateful context store + trigger-family routing + deterministic validation + conversation policy",
        "contact_email": "armankataria002@gmail.com",
        "version": "1.0.0",
        "submitted_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/context")
async def push_context(body: ContextBody) -> dict[str, Any]:
    if body.scope not in ALLOWED_SCOPES:
        return {
            "accepted": False,
            "reason": "invalid_scope",
            "details": f"Unsupported scope: {body.scope}",
        }

    accepted, reason, current_version = state.contexts.put(
        scope=body.scope,
        context_id=body.context_id,
        version=body.version,
        payload=body.payload,
        delivered_at=body.delivered_at,
    )

    if not accepted:
        return {
            "accepted": False,
            "reason": reason,
            "current_version": current_version,
        }

    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/v1/tick")
async def tick(body: TickBody) -> dict[str, Any]:
    actions: list[dict[str, Any]] = []

    for trigger_id in body.available_triggers:
        if len(actions) >= 20:
            break

        trigger = state.contexts.payload("trigger", trigger_id)
        if not trigger:
            continue

        # Trigger schemas in the brief may place IDs at top level or inside payload.
        trigger_payload = trigger.get("payload") or {}
        merchant_id = trigger.get("merchant_id") or trigger_payload.get("merchant_id")
        customer_id = trigger.get("customer_id") or trigger_payload.get("customer_id")

        if not merchant_id:
            continue

        merchant = state.contexts.payload("merchant", merchant_id)
        if not merchant:
            continue

        category_slug = merchant.get("category_slug")
        if not category_slug:
            continue

        category = state.contexts.payload("category", category_slug)
        if not category:
            continue

        customer = (
            state.contexts.payload("customer", customer_id)
            if customer_id
            else None
        )

        # Customer-scoped triggers require an existing customer context and
        # an explicit consent scope appropriate to the trigger family.
        trigger_scope = trigger.get("scope") or trigger_payload.get("scope")
        if trigger_scope == "customer":
            if not customer:
                continue
            if customer.get("merchant_id") and customer.get("merchant_id") != merchant_id:
                continue
            consent = customer.get("consent") or {}
            scopes = consent.get("scope") or consent.get("scopes") or []
            if isinstance(scopes, str):
                scopes = [scopes]
            kind = str(trigger.get("kind") or trigger_payload.get("kind") or "").lower()
            required_scope = "appointment_reminders" if any(x in kind for x in ("appointment", "booking")) else "recall_reminders" if any(x in kind for x in ("recall", "lapsed")) else None
            if required_scope and required_scope not in scopes:
                continue

        # Expired triggers are skipped.
        expires_at = trigger.get("expires_at")
        if expires_at:
            try:
                expiry = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
                now = datetime.fromisoformat(body.now.replace("Z", "+00:00"))
                if expiry <= now:
                    continue
            except ValueError:
                # If malformed, do not make a time-based assumption.
                continue

        suppression_key = str(trigger.get("suppression_key") or f"{merchant_id}:{trigger_id}")
        if state.suppression.seen_key(suppression_key):
            continue

        conversation_id = f"conv_{merchant_id}_{trigger_id}_{uuid4().hex[:8]}"

        result = compose(
            category=category,
            merchant=merchant,
            trigger=trigger,
            customer=customer,
            recent_turns=[],
        )

        result.setdefault("send_as", "merchant_on_behalf" if customer else "vera")
        result.setdefault("suppression_key", suppression_key)
        result.setdefault("cta", "open_ended")
        result.setdefault("rationale", "Composed from the available Vera contexts.")

        valid, errors = validate_output(
            result=result,
            category=category,
            merchant=merchant,
            trigger=trigger,
            customer=customer,
        )

        if not valid:
            # Never send an unverified LLM output.
            continue

        body_text = str(result["body"]).strip()
        if state.suppression.seen_body(conversation_id, body_text):
            continue

        state.suppression.mark_key(suppression_key)
        state.suppression.mark_body(conversation_id, body_text)

        actions.append(
            {
                "conversation_id": conversation_id,
                "merchant_id": merchant_id,
                "customer_id": customer_id,
                "send_as": result["send_as"],
                "trigger_id": trigger_id,
                "template_name": f"vera_{trigger.get('kind', 'generic')}_v1",
                "template_params": [merchant.get("identity", {}).get("name", "")],
                "body": body_text,
                "cta": result["cta"],
                "suppression_key": suppression_key,
                "rationale": result["rationale"],
            }
        )

        state.conversations.append(
            conversation_id,
            {
                "from": "vera",
                "message": body_text,
                "trigger_id": trigger_id,
                "timestamp": body.now,
            },
        )

    return {"actions": actions}


@app.post("/v1/reply")
async def reply(body: ReplyBody) -> dict[str, Any]:
    history = state.conversations.get(body.conversation_id)

    state.conversations.append(
        body.conversation_id,
        {
            "from": body.from_role,
            "message": body.message,
            "received_at": body.received_at,
            "turn_number": body.turn_number,
        },
    )

    result = respond(
        conversation_id=body.conversation_id,
        message=body.message,
        history=history,
    )

    if result["action"] == "send":
        state.conversations.append(
            body.conversation_id,
            {
                "from": "vera",
                "message": result["body"],
                "received_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    return result


@app.post("/v1/teardown")
async def teardown() -> dict[str, Any]:
    state.clear()
    return {"ok": True}


# Required by the challenge's standalone compose contract.
def compose_for_submission(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: dict | None = None,
) -> dict[str, Any]:
    result = compose(category, merchant, trigger, customer)

    result.setdefault("send_as", "merchant_on_behalf" if customer else "vera")
    result.setdefault("suppression_key", trigger.get("suppression_key", ""))
    result.setdefault("cta", "open_ended")
    result.setdefault("rationale", "Composed from supplied contexts.")

    return result


# Backward-compatible public name requested by the brief.
compose_submission = compose_for_submission
