"""Forgiving extractor for the first balanced JSON object inside free-form text.

Local models (and even Claude occasionally) like to wrap JSON in code fences
or sprinkle a sentence of preamble. We don't want to fail the whole analysis
because of that — just walk braces.
"""
from __future__ import annotations

import json
from typing import Any


def extract_json_object(text: str) -> dict[str, Any]:
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object found in response")
    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                snippet = text[start : i + 1]
                return json.loads(snippet)
    raise ValueError("unterminated JSON object in response")
