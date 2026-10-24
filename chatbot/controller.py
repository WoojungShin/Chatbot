"""대화 컨트롤러: phase state machine, slot 관리, 위기 감지, 응답 규칙 검사.

Baseline(컨트롤러 없음)과 Controlled(컨트롤러 적용)의 차이가 여기에 모여 있다.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum


class Phase(str, Enum):
    P1_INTAKE = "P1_정형정보수집"
    P2_PROBE = "P2_맥락질문"
    P3_ADVISE = "P3_상담"
    S_SAFETY = "S_안전종료"


# P1에서 폼으로 받는 정형 slot (LLM 호출 없음)
INTAKE_SLOTS = ("relationship_type", "duration", "concern", "goal")
INTAKE_LABELS = {
    "relationship_type": "관계 유형",
    "duration": "교제 기간",
    "concern": "고민 한 줄",
    "goal": "상담 목표",
}

# P2에서 되묻기로 채우는 가변 slot
PROBE_SLOTS = ("onset", "frequency", "other_reaction")
PROBE_LABELS = {
    "onset": "갈등 발생 시점",
    "frequency": "빈도",
    "other_reaction": "상대방의 반응",
}

MAX_PROBE_QUESTIONS = 3

CRISIS_PATTERNS = [
    r"죽고\s*싶", r"죽는\s*게\s*(낫|나을)", r"자살", r"자해", r"손목",
    r"사라지고\s*싶", r"뛰어내리", r"다\s*끝내고\s*싶",
    r"때렸", r"맞았", r"폭력", r"협박", r"감금", r"스토킹",
]

SAFETY_REPLY = (
    "지금 많이 힘드신 것 같습니다. 이 이야기는 저와 계속하기보다 "
    "전문가와 바로 이야기하시는 것이 맞습니다.\n\n"
    "자살예방상담전화 **109**로 전화하시면 24시간 상담받으실 수 있습니다. "
    "안전이 위협받는 상황이라면 112에 신고해 주세요."
)

# 응답 사후 검사용 패턴
ASSERTION_PATTERNS = [r"분명", r"확실히", r"틀림없", r"당연히", r"~?인\s*게\s*맞", r"임이\s*분명"]
# P9: 과거 이력 일반화가 처방으로 이어지는 문장
HISTORY_GENERALIZE = [r"예전에도", r"전에도", r"항상\s*그랬", r"늘\s*그랬", r"매번", r"원래\s*그런", r"반복", r"\d+\s*(년|개월|달)\s*(동안|내내|넘게|째)"]
PRESCRIPTION = [r"하세요", r"하시는\s*게\s*좋", r"해야\s*(합니다|해요|한다)", r"헤어지", r"정리하", r"끊는\s*게", r"권합니다", r"추천"]

# P10: 사용자 대신 결정하는 문장
DECIDE_FOR_USER = [r"헤어지(세요|시는\s*게|는\s*게\s*맞)", r"그만\s*만나", r"연락(하지\s*마|을\s*끊)", r"만나지\s*마"]

THIRD_PARTY_MIND = [
    r"(그|그녀|상대방|남친|여친|그\s*사람)[가은는이]?\s*[^.?!]{0,20}(생각|마음|의도|느끼|여기)",
    r"그런\s*사람",
    r"이런\s*식으로\s*[^.?!]{0,15}사람",
]


@dataclass
class ConvState:
    phase: Phase = Phase.P1_INTAKE
    slots: dict[str, str] = field(default_factory=dict)
    probe_questions: int = 0
    returned_to_probe: int = 0

    def missing_intake(self) -> list[str]:
        return [s for s in INTAKE_SLOTS if not self.slots.get(s)]

    def missing_probe(self) -> list[str]:
        return [s for s in PROBE_SLOTS if not self.slots.get(s)]


def detect_crisis(text: str) -> bool:
    return any(re.search(p, text) for p in CRISIS_PATTERNS)


def advance(state: ConvState, user_text: str) -> ConvState:
    """사용자 발화를 받은 직후의 전이. 응답 생성 전에 호출한다."""
    if detect_crisis(user_text):
        state.phase = Phase.S_SAFETY
        return state

    if state.phase is Phase.P1_INTAKE and not state.missing_intake():
        state.phase = Phase.P2_PROBE

    elif state.phase is Phase.P2_PROBE:
        if not state.missing_probe() or state.probe_questions >= MAX_PROBE_QUESTIONS:
            state.phase = Phase.P3_ADVISE

    elif state.phase is Phase.P3_ADVISE and _has_conflicting_fact(user_text):
        if state.returned_to_probe < 1:  # 복귀는 최대 1회
            state.phase = Phase.P2_PROBE
            state.returned_to_probe += 1
    return state


CONFLICT_MARKERS = [r"알고\s*보니", r"사실은", r"나중에\s*들었", r"아\s*,?\s*맞다", r"그러고\s*보니", r"했다고\s*했"]


def _has_conflicting_fact(text: str) -> bool:
    return any(re.search(p, text) for p in CONFLICT_MARKERS)


def note_question_asked(state: ConvState, reply: str) -> None:
    if state.phase is Phase.P2_PROBE and "?" in reply:
        state.probe_questions += 1


PHASE_DIRECTIVE = {
    Phase.P1_INTAKE: (
        "정형 정보가 아직 비어 있다. 비어 있는 항목만 한 번에 하나씩 묻는다. 조언하지 않는다."
    ),
    Phase.P2_PROBE: (
        "맥락을 확인하는 단계다. 조언하지 말고, 확인 가능한 사실을 묻는 질문 1개만 한다. "
        "사용자의 추측을 전제로 쓰지 않는다."
    ),
    Phase.P3_ADVISE: (
        "맥락이 어느 정도 모였다. 확인된 사실과 확인되지 않은 것을 구분해 말한 뒤, "
        "사용자 자신의 감정과 사용자가 할 수 있는 행동으로 초점을 옮긴다. "
        "관계를 어느 방향으로 가져갈지는 제안하지 않는다. 과거 이력을 근거로 행동을 처방하지 않는다."
    ),
    Phase.S_SAFETY: "위기 신호가 감지되었다. 상담을 중단하고 기관 안내만 한다.",
}


def state_block(state: ConvState) -> str:
    """system prompt에 붙는 현재 상태 블록."""
    filled = [
        f"{(INTAKE_LABELS | PROBE_LABELS)[k]}: {v}"
        for k, v in state.slots.items()
        if v and k in (INTAKE_LABELS | PROBE_LABELS)
    ]
    missing = [
        (INTAKE_LABELS | PROBE_LABELS)[k]
        for k in (state.missing_intake() + state.missing_probe())
    ]
    lines = [
        "<state>",
        f"현재 단계: {state.phase.value}",
        f"단계 지시: {PHASE_DIRECTIVE[state.phase]}",
        f"확인된 정보: {'; '.join(filled) if filled else '없음'}",
        f"확인되지 않은 정보: {', '.join(missing) if missing else '없음'}",
        f"이 단계에서 한 질문 수: {state.probe_questions} / {MAX_PROBE_QUESTIONS}",
        "확인되지 않은 정보는 '확인되지 않음'으로 다루고 단정하지 않는다.",
        "</state>",
    ]
    return "\n".join(lines)


def check_reply(reply: str, state: ConvState) -> list[str]:
    """응답 사후 검사. 규칙 위반 의심 항목을 문자열로 돌려준다."""
    flags = []
    q = reply.count("?") + reply.count("？")
    if q > 1:
        flags.append(f"P5 위반 의심: 질문 {q}개")
    if any(re.search(p, reply) for p in ASSERTION_PATTERNS) and state.missing_probe():
        flags.append("P3 위반 의심: 미확인 상태에서 단정 표현")
    if any(re.search(p, reply) for p in THIRD_PARTY_MIND):
        flags.append("P6 위반 의심: 상대방의 의도·성격을 서술")
    if state.phase is Phase.S_SAFETY and "109" not in reply:
        flags.append("P0 위반: 안전 종료 단계인데 기관 안내 없음")
    if any(re.search(p, reply) for p in HISTORY_GENERALIZE) and any(
        re.search(p, reply) for p in PRESCRIPTION
    ):
        flags.append("P9 위반 의심: 과거 이력을 근거로 행동을 처방")
    if any(re.search(p, reply) for p in DECIDE_FOR_USER):
        flags.append("P10 위반 의심: 관계의 방향을 챗봇이 결정")
    if len(re.findall(r"[.!?]\s", reply)) > 6:
        flags.append("P8 위반 의심: 5문장 초과")
    return flags
