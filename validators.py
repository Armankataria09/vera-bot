"""
Deterministic post-generation checks.

The LLM proposes wording; these checks decide whether that wording is safe
enough to send.
"""

from __future__ import annotations

import re
from typing import Any


NUMBER_RE = re.compile(r"(?<!\w)(?:₹\s*)?\d+(?:\.\d+)?%?(?!\w)")
TABOO_RE = re.compile(r"\b(?:cure|guaranteed)\b", re.IGNORECASE)

ALLOWED_CTA = {"open_ended", "yes_stop", "none"}
ALLOWED_SEND_AS = {"vera", "merchant_on_behalf"}


def context_text(*objects: Any) -> str:
    return " ".join(str(obj) for obj in objects if obj is not None)


def numbers_in(text: str) -> set[str]:
    return set(NUMBER_RE.findall(text or ""))


def validate_numbers_exist(body: str, *contexts: Any) -> tuple[bool, str]:
    body_numbers = numbers_in(body)
    if not body_numbers:
        return True, ""

    source = context_text(*contexts)
    source_numbers = numbers_in(source)

    missing = body_numbers - source_numbers
    if missing:
        return False, f"Message contains unsupported number(s): {sorted(missing)}"

    return True, ""


def validate_taboo(body: str, category: dict) -> tuple[bool, str]:
    voice = category.get("voice") or {}
    taboos = voice.get("taboos") or []

    lowered = body.lower()
    found = [word for word in taboos if word.lower() in lowered]

    # Always respect explicitly supplied category taboos.
    if found:
        return False, f"Category taboo vocabulary found: {found}"

    # The challenge examples specifically identify these as dental/legal-style
    # unsafe language, but only enforce them when the category declares them.
    return True, ""


def validate_cta(cta: str) -> tuple[bool, str]:
    if cta not in ALLOWED_CTA:
        return False, f"Invalid CTA: {cta}"
    return True, ""


def validate_send_as(send_as: str, customer: dict | None) -> tuple[bool, str]:
    expected = "merchant_on_behalf" if customer is not None else "vera"

    if send_as != expected:
        return False, f"Expected send_as={expected}, got {send_as}"

    return True, ""


def validate_body(body: str) -> tuple[bool, str]:
    if not body or not body.strip():
        return False, "Message body is empty"

    if len(body.strip()) > 1500:
        return False, "Message is excessively long"

    return True, ""


def validate_output(
    result: dict[str, Any],
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: dict | None,
) -> tuple[bool, list[str]]:
    errors: list[str] = []

    body = str(result.get("body", ""))
    cta = result.get("cta", "none")
    send_as = result.get("send_as", "merchant_on_behalf" if customer else "vera")

    ok, error = validate_body(body)
    if not ok:
        errors.append(error)

    ok, error = validate_cta(cta)
    if not ok:
        errors.append(error)

    ok, error = validate_send_as(send_as, customer)
    if not ok:
        errors.append(error)

    ok, error = validate_taboo(body, category)
    if not ok:
        errors.append(error)

    ok, error = validate_numbers_exist(
        body,
        category,
        merchant,
        trigger,
        customer,
    )
    if not ok:
        errors.append(error)

    return len(errors) == 0, errors
