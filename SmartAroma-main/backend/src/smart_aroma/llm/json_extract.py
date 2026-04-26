"""Extract a JSON object from model output (handles markdown fences)."""

from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel

TModel = TypeVar("TModel", bound=BaseModel)


def extract_json_object(text: str) -> str:
    """Return the substring that parses as a single JSON object."""
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw, re.IGNORECASE)
    if fence:
        raw = fence.group(1).strip()

    start = raw.find("{")
    if start == -1:
        raise ValueError("No JSON object start '{' found in model output")

    depth = 0
    in_str = False
    escape = False
    quote = ""
    for i in range(start, len(raw)):
        ch = raw[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                in_str = False
        else:
            if ch in "\"'":
                in_str = True
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    candidate = raw[start : i + 1]
                    json.loads(candidate)  # validate
                    return candidate

    raise ValueError("Unbalanced braces; could not extract JSON object")


def parse_aroma_plan(text: str, model_cls: type[TModel]) -> TModel:
    """Extract JSON from *text* and validate as *model_cls* (e.g. AromaPlan)."""
    blob = extract_json_object(text)
    return model_cls.model_validate_json(blob)
