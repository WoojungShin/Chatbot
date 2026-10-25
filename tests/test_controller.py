from chatbot.controller import (
    ConvState,
    is_confirmation,
    note_recap_given,
    unsupported_quotes,
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
    for ph in (Phase.PHASE1_INTAKE, Phase.PHASE2_PROBE, Phase.PHASE3_ADVISE):
        s = controlled_state(phase=ph)
        advance(s, "다 끝내고 싶어요. 죽는 게 나을 것 같아요")
        assert s.phase is Phase.SAFETY


def test_intake_to_probe_only_when_slots_full():
    s = ConvState(slots={"relationship_type": "연애 중"})
    advance(s, "안녕하세요")
    assert s.phase is Phase.PHASE1_INTAKE
    s.slots = dict(FULL_INTAKE)
    advance(s, "안녕하세요")
    assert s.phase is Phase.PHASE2_PROBE


def test_probe_goes_to_recap_not_advise():
    s = controlled_state(phase=Phase.PHASE2_PROBE, probe_questions=3)
    advance(s, "잘 모르겠어요")
    assert s.phase is Phase.PHASE2R_RECAP  # 바로 상담으로 가지 않는다


def test_return_to_probe_once_only():
    s = controlled_state(phase=Phase.PHASE3_ADVISE, recap_confirmed=True)
    advance(s, "알고 보니 입원 중이었대요")
    assert s.phase is Phase.PHASE2_PROBE
    s.phase = Phase.PHASE3_ADVISE
    advance(s, "알고 보니 회의 중이었대요")
    assert s.phase is Phase.PHASE3_ADVISE  # 복귀는 1회로 제한


def test_check_reply_catches_violations():
    s = controlled_state(phase=Phase.PHASE2_PROBE)
    flags = check_reply("그런 사람에게 뭐라고 하실 건가요? 언제부터 그랬나요?", s)
    assert any("P5" in f for f in flags)
    assert any("P6" in f for f in flags)


def test_check_reply_passes_clean_response():
    s = controlled_state(phase=Phase.PHASE2_PROBE)
    assert check_reply("기다리는 건 힘들었을 것 같아요. 평소에는 답장이 얼마나 걸렸나요?", s) == []


def test_safety_reply_must_carry_hotline():
    s = controlled_state(phase=Phase.SAFETY)
    assert any("P0" in f for f in check_reply("많이 힘드시겠어요. 조금 더 이야기해 주세요.", s))


def test_state_block_marks_unconfirmed():
    s = controlled_state(phase=Phase.PHASE2_PROBE)
    b = state_block(s)
    assert "확인되지 않은 정보" in b and "갈등 발생 시점" in b


def test_question_counter_only_in_probe():
    s = controlled_state(phase=Phase.PHASE2_PROBE)
    note_question_asked(s, "언제부터였나요?")
    assert s.probe_questions == 1
    s.phase = Phase.PHASE3_ADVISE
    note_question_asked(s, "어떻게 생각하세요?")
    assert s.probe_questions == 1


def test_detect_crisis_negative():
    assert not detect_crisis("요즘 너무 지치고 서운해요")


def test_p9_history_prescription():
    s = controlled_state(phase=Phase.PHASE3_ADVISE, recap_confirmed=True)
    flags = check_reply("1년 동안 반복됐으면 앞으로도 그럴 거예요. 이제 정리하시는 게 좋습니다.", s)
    assert any("P9" in f for f in flags)


def test_p9_allows_history_as_fact_question():
    s = controlled_state(phase=Phase.PHASE3_ADVISE, recap_confirmed=True)
    assert check_reply("예전에도 비슷한 적이 있었다고 하셨는데, 그때는 어떻게 넘어가셨어요?", s) == []


def test_p10_decides_for_user():
    s = controlled_state(phase=Phase.PHASE3_ADVISE, recap_confirmed=True)
    assert any("P10" in f for f in check_reply("지금은 그만 만나는 쪽이 낫습니다.", s))


def test_p10_allows_balanced_options():
    s = controlled_state(phase=Phase.PHASE3_ADVISE, recap_confirmed=True)
    r = "먼저 말을 꺼내는 쪽과 당분간 두는 쪽이 있어요. 어느 쪽이 더 감당할 만한가요?"
    assert check_reply(r, s) == []


# ---------- P4: 정리 확인 (Phase2R) ----------

RECAP = (
    '정리해 볼게요. 일어난 일은 "어제부터 답장이 없다", "평소엔 한두 시간이면 왔다"예요. '
    '"나를 무시한다"는 그때 받아들인 부분이고요. 제가 잘못 나눈 게 있을까요?'
)
SAID = ["어제부터 답장이 없어요. 저를 무시하는 거죠?", "평소엔 한두 시간이면 왔어요"]


def recap_state(**kw):
    s = controlled_state(phase=Phase.PHASE2R_RECAP, said=list(SAID))
    for k, v in kw.items():
        setattr(s, k, v)
    return s


def test_recap_requires_user_confirmation_before_advise():
    s = recap_state()
    advance(s, "아니요, 그건 제가 안 한 말이에요")
    assert s.phase is Phase.PHASE2R_RECAP and not s.recap_confirmed


def test_recap_confirmed_moves_to_advise():
    s = recap_state()
    advance(s, "아니요, 맞아요. 나눠 놓고 보니 바쁜 걸 수도 있겠네요.")
    assert s.phase is Phase.PHASE3_ADVISE and s.recap_confirmed


def test_recap_falls_back_to_probe_after_two_rounds():
    s = recap_state(recap_rounds=2)
    advance(s, "아니요, 그것도 틀렸어요")
    assert s.phase is Phase.PHASE2_PROBE


def test_good_recap_passes():
    assert check_reply(RECAP, recap_state()) == []


def test_recap_without_split_is_flagged():
    s = recap_state()
    flags = check_reply("지금까지 들은 걸 보면 상대가 바쁜 것 같네요. 맞나요?", s)
    assert any("일어난 일과 해석" in f for f in flags)


def test_recap_with_invented_quote_is_flagged():
    s = recap_state()
    bad = RECAP.replace('"평소엔 한두 시간이면 왔다"', '"상대가 일부러 피한다"')
    flags = check_reply(bad, s)
    assert any("하지 않은 말" in f for f in flags)


def test_recap_without_question_is_flagged():
    s = recap_state()
    no_ask = '일어난 일은 "어제부터 답장이 없다"예요. "나를 무시한다"는 받아들인 부분입니다.'
    assert any("확인하는 질문" in f for f in check_reply(no_ask, s))


def test_advise_without_confirmation_is_flagged():
    s = controlled_state(phase=Phase.PHASE3_ADVISE, recap_confirmed=False)
    assert any("정리 확인 없이" in f for f in check_reply("그러면 이렇게 보시면 좋겠어요.", s))


def test_advise_after_confirmation_is_clean():
    s = controlled_state(phase=Phase.PHASE3_ADVISE, recap_confirmed=True)
    assert check_reply("지금 남는 건 기다리는 동안의 서운함이네요. 그걸 전해본 적 있으세요?", s) == []


def test_unsupported_quotes_helper():
    assert unsupported_quotes('"어제부터 답장이 없다"만 썼어요', SAID) == []
    assert unsupported_quotes('"없는 말"을 넣었어요', SAID) == ["없는 말"]


def test_is_confirmation_handles_mixed_opening():
    assert is_confirmation("아니요, 맞아요")
    assert not is_confirmation("아니요, 그건 틀렸어요")
    assert not is_confirmation("음 잘 모르겠어요")


def test_note_recap_given_counts_only_in_recap():
    s = recap_state()
    note_recap_given(s, RECAP)
    assert s.recap_rounds == 1
    s.phase = Phase.PHASE3_ADVISE
    note_recap_given(s, RECAP)
    assert s.recap_rounds == 1


def test_state_block_lists_user_words_in_recap():
    b = state_block(recap_state())
    assert "사용자가 실제로 한 말" in b and SAID[0] in b
