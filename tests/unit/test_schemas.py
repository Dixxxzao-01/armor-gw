"""ChatRequest 字段 clamp：越界值必须抛 ValidationError，合法值通过。"""
import pytest
from pydantic import ValidationError

from app.schemas import ChatRequest


def _payload(**overrides):
    base = {
        "model": "test",
        "messages": [{"role": "user", "content": "hi"}],
    }
    base.update(overrides)
    return base


def test_temperature_below_range_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(**_payload(temperature=-5))


def test_temperature_above_range_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(**_payload(temperature=99))


def test_max_tokens_zero_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(**_payload(max_tokens=0))


def test_max_tokens_above_range_rejected():
    with pytest.raises(ValidationError):
        ChatRequest(**_payload(max_tokens=100000))


def test_valid_request_passes():
    req = ChatRequest(**_payload(temperature=0.7, max_tokens=4096))
    assert req.temperature == 0.7
    assert req.max_tokens == 4096
    assert req.model == "test"
    assert req.messages[0].role == "user"
    assert req.stream is False
