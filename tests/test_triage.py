"""Unit tests for the AI-output parser and the mock provider.

These don't need the DB - they test the pure logic that keeps bad AI output
from corrupting our data.
"""
import pytest

from app.schemas.triage import TriageResult
from app.services.hashing import compute_content_hash
from app.services.llm import MockProvider
from app.services.triage_parser import TriageParseError, parse_triage


def test_parse_clean_json():
    raw = '{"category":"billing","urgency_score":8,"summary":"double charge","suggested_reply":"Sorry about that, refund coming."}'
    result = parse_triage(raw)
    assert result.category.value == "billing"
    assert result.urgency_score == 8


def test_parse_json_with_prose_and_fences():
    raw = 'Sure! Here is the JSON:\n```json\n{"category":"bug","urgency_score":5,"summary":"app crash","suggested_reply":"We are on it."}\n```'
    result = parse_triage(raw)
    assert result.category.value == "bug"


def test_urgency_is_clamped():
    raw = '{"category":"other","urgency_score":99,"summary":"x","suggested_reply":"y"}'
    result = parse_triage(raw)
    assert result.urgency_score == 10  # clamped down from 99


def test_invalid_category_raises():
    raw = '{"category":"nonsense","urgency_score":3,"summary":"x","suggested_reply":"y"}'
    with pytest.raises(TriageParseError):
        parse_triage(raw)


def test_empty_response_raises():
    with pytest.raises(TriageParseError):
        parse_triage("")


def test_content_hash_is_stable_and_normalized():
    a = compute_content_hash("Hello ", "  World")
    b = compute_content_hash("hello", "world")
    assert a == b  # normalization: trim + lowercase


async def test_mock_provider_classifies_billing():
    provider = MockProvider()
    resp = await provider.classify("Charged twice", "I see two charges on my card")
    result = parse_triage(resp.text)
    assert result.category.value == "billing"
    assert 1 <= result.urgency_score <= 10
