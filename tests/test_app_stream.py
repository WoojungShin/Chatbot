"""스트리밍 중 재진입으로 응답이 유실되던 문제에 대한 회귀 테스트.

입력창이 열려 있으면 스트리밍 중에 들어온 입력이 스크립트를 다시 돌리고,
진행 중이던 st.write_stream이 중단되어 응답이 세션에 저장되지 않았다.
"""
from __future__ import annotations

import types
from pathlib import Path

import anthropic
import pytest
from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parent.parent / "app.py")
CHUNKS = ["2주 전을 기점으로 ", "연락이 줄었다는 거네요. ", "그 무렵 다른 일이 있었나요?"]
SLOTS = {"relationship_type": "연애 중", "duration": "1년", "concern": "연락", "goal": "정리"}


REPLY = "".join(CHUNKS)


def _usage():
    return types.SimpleNamespace(
        input_tokens=100, output_tokens=40,
        cache_read_input_tokens=0, cache_creation_input_tokens=0,
    )


class _Stream:
    text_stream = CHUNKS

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def get_final_message(self):
        return types.SimpleNamespace(usage=_usage())


def _create(**kw):
    block = types.SimpleNamespace(type="text", text=REPLY)
    return types.SimpleNamespace(content=[block], usage=_usage())


@pytest.fixture
def at(monkeypatch):
    monkeypatch.setattr(
        anthropic, "Anthropic",
        lambda *a, **k: types.SimpleNamespace(
            messages=types.SimpleNamespace(stream=lambda **kw: _Stream(), create=_create)),
    )
    t = AppTest.from_file(APP, default_timeout=60)
    t.secrets["ANTHROPIC_API_KEY"] = "sk-ant-test"
    t.run()
    t.session_state["intake_done"] = True
    t.session_state["state"].slots = dict(SLOTS)
    t.run()
    return t


def test_reply_is_stored_whole(at):
    at.chat_input[0].set_value("2주 전부터 연락이 줄었어요").run()
    msgs = at.session_state["messages"]
    assert len(msgs) == 2
    assert msgs[1]["content"] == REPLY  # 중간에 잘리지 않는다
    assert at.session_state["turns_used"] == 1


def test_streaming_mode_stores_same_reply(at):
    """스트리밍을 켜도 같은 응답이 온전히 저장된다."""
    box = [c for c in at.checkbox if c.label == "스트리밍"][0]
    box.set_value(True).run()
    at.chat_input[0].set_value("2주 전부터 연락이 줄었어요").run()
    assert at.session_state["messages"][1]["content"] == REPLY


def test_input_reopens_after_reply(at):
    at.chat_input[0].set_value("2주 전부터 연락이 줄었어요").run()
    assert at.session_state["pending"] is False
    assert at.chat_input[0].proto.disabled is False


def test_stale_pending_flag_is_cleared(at):
    """응답까지 끝난 상태에 pending이 남아 있으면 입력창이 영구히 잠긴다."""
    at.chat_input[0].set_value("2주 전부터 연락이 줄었어요").run()
    at.session_state["pending"] = True
    at.run()
    assert at.session_state["pending"] is False
    assert at.chat_input[0].proto.disabled is False


def test_no_duplicate_user_message(at):
    """같은 발화가 두 줄로 쌓이지 않는다."""
    at.chat_input[0].set_value("저한테 질린 것 같아요").run()
    at.chat_input[0].set_value("연락이 줄은 것 자체가 계기인 것 같아요").run()
    roles = [m["role"] for m in at.session_state["messages"]]
    assert roles == ["user", "assistant", "user", "assistant"], roles
