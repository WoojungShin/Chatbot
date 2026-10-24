from chatbot.controller import (
    ConvState,
    Phase,
    advance,
    check_reply,
    detect_crisis,
    note_question_asked,
    state_block,
)

FULL_INTAKE = {"relationship_type": "연애 중", "duration": "1년", "concern": "연락 문제", "goal": "생각 정리"}


def controlled_state(**kw):
    s = ConvState(slots=dict(FULL_INTAKE))
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_crisis_from_any_phase():
    for ph in (Phase.P1_INTAKE, Phase.P2_PROBE, Phase.P3_ADVISE):
        s = controlled_state(phase=ph)
        advance(s, "다 끝내고 싶어요. 죽는 게 나을 것 같아요")
        assert s.phase is Phase.S_SAFETY


def test_intake_to_probe_only_when_slots_full():
    s = ConvState(slots={"relationship_type": "연애 중"})
    advance(s, "안녕하세요")
    assert s.phase is Phase.P1_INTAKE
    s.slots = dict(FULL_INTAKE)
    advance(s, "안녕하세요")
    assert s.phase is Phase.P2_PROBE


def test_probe_to_advise_by_question_cap():
    s = controlled_state(phase=Phase.P2_PROBE, probe_questions=3)
    advance(s, "잘 모르겠어요")
    assert s.phase is Phase.P3_ADVISE


def test_return_to_probe_once_only():
    s = controlled_state(phase=Phase.P3_ADVISE)
    advance(s, "알고 보니 입원 중이었대요")
    assert s.phase is Phase.P2_PROBE
    s.phase = Phase.P3_ADVISE
    advance(s, "알고 보니 회의 중이었대요")
    assert s.phase is Phase.P3_ADVISE  # 복귀는 1회로 제한


def test_check_reply_catches_violations():
    s = controlled_state(phase=Phase.P2_PROBE)
    flags = check_reply("그런 사람에게 뭐라고 하실 건가요? 언제부터 그랬나요?", s)
    assert any("P5" in f for f in flags)
    assert any("P6" in f for f in flags)


def test_check_reply_passes_clean_response():
    s = controlled_state(phase=Phase.P2_PROBE)
    assert check_reply("기다리는 건 힘들었을 것 같아요. 평소에는 답장이 얼마나 걸렸나요?", s) == []


def test_safety_reply_must_carry_hotline():
    s = controlled_state(phase=Phase.S_SAFETY)
    assert any("P0" in f for f in check_reply("많이 힘드시겠어요. 조금 더 이야기해 주세요.", s))


def test_state_block_marks_unconfirmed():
    s = controlled_state(phase=Phase.P2_PROBE)
    b = state_block(s)
    assert "확인되지 않은 정보" in b and "갈등 발생 시점" in b


def test_question_counter_only_in_probe():
    s = controlled_state(phase=Phase.P2_PROBE)
    note_question_asked(s, "언제부터였나요?")
    assert s.probe_questions == 1
    s.phase = Phase.P3_ADVISE
    note_question_asked(s, "어떻게 생각하세요?")
    assert s.probe_questions == 1


def test_detect_crisis_negative():
    assert not detect_crisis("요즘 너무 지치고 서운해요")


def test_p9_history_prescription():
    s = controlled_state(phase=Phase.P3_ADVISE)
    flags = check_reply("1년 동안 반복됐으면 앞으로도 그럴 거예요. 이제 정리하시는 게 좋습니다.", s)
    assert any("P9" in f for f in flags)


def test_p9_allows_history_as_fact_question():
    s = controlled_state(phase=Phase.P3_ADVISE)
    assert check_reply("예전에도 비슷한 적이 있었다고 하셨는데, 그때는 어떻게 넘어가셨어요?", s) == []


def test_p10_decides_for_user():
    s = controlled_state(phase=Phase.P3_ADVISE)
    assert any("P10" in f for f in check_reply("지금은 그만 만나는 쪽이 낫습니다.", s))


def test_p10_allows_balanced_options():
    s = controlled_state(phase=Phase.P3_ADVISE)
    r = "먼저 말을 꺼내는 쪽과 당분간 두는 쪽이 있어요. 어느 쪽이 더 감당할 만한가요?"
    assert check_reply(r, s) == []
