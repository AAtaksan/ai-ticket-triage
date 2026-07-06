"""Turn raw LLM text into a validated TriageResult.

LLMs sometimes wrap JSON in prose or ```json fences. We extract the JSON object
and validate it with Pydantic. Any failure raises, so the worker retries.
"""
import json
import re

from app.schemas.triage import TriageResult

_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class TriageParseError(ValueError):
    """Raised when the LLM output can't be parsed into a TriageResult."""


def parse_triage(raw_text: str) -> TriageResult:
    if not raw_text or not raw_text.strip():
        raise TriageParseError("empty LLM response")

    match = _JSON_OBJECT_RE.search(raw_text)
    if not match:
        raise TriageParseError(f"no JSON object found in: {raw_text[:200]!r}")

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        raise TriageParseError(f"invalid JSON: {exc}") from exc

    try:
        return TriageResult.model_validate(data)
    except Exception as exc:  # pydantic ValidationError
        raise TriageParseError(f"schema validation failed: {exc}") from exc
