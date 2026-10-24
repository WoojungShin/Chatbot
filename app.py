"""연애 상담 챗봇 데모 — Baseline vs Controlled.

실행: streamlit run app.py
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

import anthropic
import streamlit as st
from dotenv import load_dotenv

from chatbot import (
    BASELINE_SYSTEM,
    INTAKE_LABELS,
    INTAKE_SLOTS,
    SAFETY_REPLY,
    ChatClient,
    ConvState,
    GenConfig,
    Phase,
    PersonaError,
    advance,
    build_system_prompt,
    check_reply,
    detect_crisis,
    load_persona,
    note_question_asked,
    state_block,
)
from chatbot.client import default_model

load_dotenv()
ROOT = Path(__file__).parent
PERSONA_DIR = ROOT / "personas" / "relationship_counselor"
LOG_DIR = ROOT / "logs"

# ---------- 사용량 상한 (공용 API key 보호) ----------
MAX_TURNS = 20            # 세션당 사용자 발화 수
MAX_INPUT_CHARS = 600     # 한 번에 보낼 수 있는 길이
MAX_TOKENS_CAP = 1024     # max_tokens 상한
SESSION_COST_CAP = 0.20   # 세션당 추정 비용(USD) 상한
PRICE = {  # USD / 1M tokens, https://platform.claude.com/docs/en/about-claude/pricing
    "claude-sonnet-5": (2.0, 10.0),
    "claude-haiku-4-5": (1.0, 5.0),
}


def secret_api_key() -> str:
    """Streamlit Secrets → 환경변수 순으로 찾는다. 키는 화면에 표시하지 않는다."""
    try:
        v = st.secrets.get("ANTHROPIC_API_KEY", "")
        if v:
            return str(v)
    except Exception:
        pass
    return os.getenv("ANTHROPIC_API_KEY", "")


def estimate_cost(model: str, usage) -> float:
    inp, out = PRICE.get(model, PRICE["claude-sonnet-5"])
    cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
    cache_write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    return (
        usage.input_tokens * inp
        + cache_read * inp * 0.1
        + cache_write * inp * 1.25
        + usage.output_tokens * out
    ) / 1e6

st.set_page_config(page_title="연애 상담 챗봇 데모", page_icon="💬", layout="wide")

# ---------- 상태 초기화 ----------
if "messages" not in st.session_state:
    st.session_state.messages = []
    st.session_state.state = ConvState()
    st.session_state.flags = {}
    st.session_state.intake_done = False
    st.session_state.spent = 0.0
    st.session_state.turns_used = 0

try:
    persona = load_persona(PERSONA_DIR)
except PersonaError as e:
    st.error(f"Persona 로딩 실패: {e}")
    st.stop()

# ---------- 사이드바 ----------
with st.sidebar:
    st.header("설정")
    mode = st.radio(
        "모드",
        ["Controlled (컨트롤러 적용)", "Baseline (컨트롤러 없음)"],
        help="Baseline은 원칙·예시·phase 없이 일반 상담 프롬프트만 사용합니다.",
    )
    controlled = mode.startswith("Controlled")

    api_key = secret_api_key()
    if api_key:
        st.caption("API key: 서버 설정에서 불러옴")
    else:
        api_key = st.text_input("ANTHROPIC_API_KEY", type="password")
    model = st.selectbox(
        "Model",
        ["claude-sonnet-5", "claude-haiku-4-5"],
        index=0 if default_model() != "claude-haiku-4-5" else 1,
    )
    max_tokens = st.number_input("Max tokens", 64, MAX_TOKENS_CAP, 512, 64)

    if st.button("대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.session_state.state = ConvState()
        st.session_state.flags = {}
        st.session_state.intake_done = False
        st.session_state.turns_used = 0
        st.rerun()

    st.divider()
    cs: ConvState = st.session_state.state
    if controlled:
        st.subheader("컨트롤러 상태")
        st.metric("현재 phase", cs.phase.value)
        st.caption(f"P2 질문 {cs.probe_questions}/3 · P2 복귀 {cs.returned_to_probe}/1")
        st.write("**slot**")
        for k, label in INTAKE_LABELS.items():
            st.write(f"- {label}: {cs.slots.get(k) or '—'}")
        with st.expander("system prompt 보기"):
            st.code(build_system_prompt(persona, state_block(cs)), language="xml")
    else:
        st.subheader("Baseline")
        st.code(BASELINE_SYSTEM)

    st.divider()
    st.subheader("사용량")
    st.caption(
        f"이 세션 {st.session_state.turns_used}/{MAX_TURNS}턴 · "
        f"추정 ${st.session_state.spent:.4f} / ${SESSION_COST_CAP:.2f}"
    )
    st.progress(min(st.session_state.spent / SESSION_COST_CAP, 1.0))

    if st.session_state.messages and st.button("대화 로그 저장", use_container_width=True):
        LOG_DIR.mkdir(exist_ok=True)
        name = f"{'controlled' if controlled else 'baseline'}_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        with (LOG_DIR / name).open("w", encoding="utf-8") as f:
            for i, m in enumerate(st.session_state.messages):
                row = dict(m, idx=i, mode="controlled" if controlled else "baseline")
                if m["role"] == "assistant":
                    row["flags"] = st.session_state.flags.get(i, [])
                    row["phase"] = cs.phase.value
                f.write(json.dumps(row, ensure_ascii=False) + "\n")
        st.success(f"logs/{name}")

# ---------- 본문 ----------
st.title("연애 상담 챗봇")
st.caption(f"{'컨트롤러 적용' if controlled else '컨트롤러 없음 (baseline)'} · 시연용")

# P1: 정형 정보는 폼으로 받는다 (LLM 호출 없음)
if controlled and not st.session_state.intake_done:
    st.info("P1 단계 — 정형 정보는 대화 대신 폼으로 받습니다. 토큰을 쓰지 않습니다.")
    with st.form("intake"):
        c1, c2 = st.columns(2)
        rel = c1.selectbox(INTAKE_LABELS["relationship_type"], ["연애 중", "썸", "이별 후", "짝사랑", "기타"])
        dur = c2.text_input(INTAKE_LABELS["duration"], placeholder="예: 1년 2개월")
        concern = st.text_input(INTAKE_LABELS["concern"], placeholder="예: 연락 빈도 때문에 자주 다툼")
        goal = st.selectbox(
            INTAKE_LABELS["goal"], ["생각 정리", "대화 방법 찾기", "결정에 필요한 정보 얻기", "그냥 말하고 싶음"]
        )
        if st.form_submit_button("상담 시작"):
            st.session_state.state.slots = {
                "relationship_type": rel, "duration": dur, "concern": concern, "goal": goal,
            }
            st.session_state.intake_done = True
            st.session_state.state.phase = Phase.P2_PROBE
            st.rerun()
    st.stop()

for i, m in enumerate(st.session_state.messages):
    with st.chat_message(m["role"]):
        st.markdown(m["content"])
        for flag in st.session_state.flags.get(i, []):
            st.warning(flag, icon="⚠️")

if user_input := st.chat_input("메시지를 입력하세요"):
    if len(user_input) > MAX_INPUT_CHARS:
        st.warning(f"한 번에 {MAX_INPUT_CHARS}자까지 보낼 수 있습니다. 나눠서 보내주세요.")
        st.stop()
    if st.session_state.turns_used >= MAX_TURNS:
        st.warning(f"이 세션의 턴 상한({MAX_TURNS})에 도달했습니다. 대화를 초기화하면 이어서 쓸 수 있습니다.")
        st.stop()
    if st.session_state.spent >= SESSION_COST_CAP:
        st.warning(f"이 세션의 사용량 상한(${SESSION_COST_CAP:.2f})에 도달했습니다. 대화를 초기화해 주세요.")
        st.stop()

    st.session_state.messages.append({"role": "user", "content": user_input})
    with st.chat_message("user"):
        st.markdown(user_input)

    cs = st.session_state.state

    # 위기 감지는 컨트롤러 모드에서만 작동한다 (baseline과의 차이를 보여주는 지점)
    if controlled:
        advance(cs, user_input)
        if cs.phase is Phase.S_SAFETY:
            with st.chat_message("assistant"):
                st.markdown(SAFETY_REPLY)
            st.session_state.messages.append({"role": "assistant", "content": SAFETY_REPLY})
            st.stop()

    if not api_key:
        st.warning("ANTHROPIC_API_KEY를 .env 또는 사이드바에 입력하세요.")
        st.stop()

    system = build_system_prompt(persona, state_block(cs)) if controlled else BASELINE_SYSTEM
    client = ChatClient(api_key=api_key)
    cfg = GenConfig(model=model, max_tokens=int(max_tokens))

    with st.chat_message("assistant"):
        try:
            reply = st.write_stream(client.stream(system, st.session_state.messages, cfg))
        except anthropic.APIError as e:
            st.session_state.messages.pop()
            st.error(f"API 오류: {e}")
            st.stop()
        flags = check_reply(reply, cs) if controlled else []
        for flag in flags:
            st.warning(flag, icon="⚠️")

    idx = len(st.session_state.messages)
    st.session_state.messages.append({"role": "assistant", "content": reply})
    st.session_state.flags[idx] = flags
    st.session_state.turns_used += 1
    if client.last_usage:
        st.session_state.spent += estimate_cost(model, client.last_usage)
    if controlled:
        note_question_asked(cs, reply)
    st.rerun()
