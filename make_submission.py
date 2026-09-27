"""
Generate submission.jsonl from a canonical test-pair file.

Expected input:
test_pairs.json containing:
[
  {"test_id":"T01","category":{...},"merchant":{...},"trigger":{...},"customer":null},
  ...
]

If the portal supplies a different test-pair format, adapt only this script.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from compose import compose


def generate(input_path: str = "test_pairs.json", output_path: str = "submission.jsonl") -> None:
    pairs = json.loads(Path(input_path).read_text(encoding="utf-8"))

    with Path(output_path).open("w", encoding="utf-8") as f:
        for pair in pairs:
            result = compose(
                category=pair["category"],
                merchant=pair["merchant"],
                trigger=pair["trigger"],
                customer=pair.get("customer"),
            )

            result.setdefault("send_as", "merchant_on_behalf" if pair.get("customer") else "vera")
            result.setdefault("suppression_key", pair["trigger"].get("suppression_key", ""))
            result.setdefault("cta", "open_ended")
            result.setdefault("rationale", "Composed from supplied challenge contexts.")

            row = {
                "test_id": pair["test_id"],
                **result,
            }

            f.write(json.dumps(row, ensure_ascii=False) + "\n")

    print(f"Wrote {len(pairs)} submission rows to {output_path}")


if __name__ == "__main__":
    generate(*(sys.argv[1:3] if len(sys.argv) > 1 else []))
