# Principle Chatbot — 연애 상담 컨트롤러

**원칙(principles)** 과 **예시(examples)** 를 YAML로 정의하면, 그 두 조건에 맞춰 대화하는 Claude 기반 챗봇.

## 실행

```bash
pip install -r requirements.txt
cp .env.example .env        # ANTHROPIC_API_KEY 입력
streamlit run app.py
```

## 구조

```
app.py                     Streamlit UI
chatbot/
  persona.py               YAML 로딩 + 검증 (id 중복, applies 참조 오류 등)
  prompt.py                persona -> system prompt (XML 구조)
  client.py                Claude API streaming + prompt caching
personas/
  socratic_tutor/          샘플 persona
    principles.yaml
    examples.yaml
  _template/               새 persona 템플릿 ('_' 폴더는 UI에 안 보임)
tests/
```

## 새 persona 만들기

```bash
cp -r personas/_template personas/my_bot
```

- `principles.yaml` — `role`, `principles[]` (`id`, `rule`, `priority`, `rationale`)
- `examples.yaml` — `examples[]` (`situation`, `turns[]`, `applies`, `note`)

앱 실행 중 YAML을 수정했다면 사이드바의 **YAML 다시 읽기**를 누르면 됩니다.
사이드바 **System prompt 미리보기**에서 실제로 모델에 들어가는 prompt를 확인할 수 있습니다.

## 설계 메모

- 예시는 가짜 대화 turn이 아니라 system prompt 안의 `<examples>` 블록으로 넣음 → 실제 대화 기록과 섞이지 않고, system prompt 전체가 prompt caching 대상이 됨
- `rationale`을 함께 넣어 모델이 규칙의 의도를 이해하고 애매한 상황에서도 일관되게 판단하도록 함
- 원칙 충돌 시 `priority`가 작은 것 우선

## 테스트

```bash
pytest -q
```


## 연애 상담 컨트롤러 (Team Task)

```bash
streamlit run app.py
```

- `personas/relationship_counselor/` — 원칙 11개(P0~P10)와 예시 4개
- `chatbot/controller.py` — phase state machine, slot, 위기 감지, 응답 규칙 검사
- 사이드바 **화면**에서 두 모드 선택
  - **직접 대화** — 실제 모델 호출. Baseline / Controlled 전환, phase·slot·system prompt 확인, 대화 로그 JSONL 내려받기
  - **시연 · 재생** — 구성한 대화를 한 턴씩 재생. 모델을 호출하지 않아 API key 없이도 동작 (`chatbot/scenarios.py`)

Phase 전이: Phase1(폼, LLM 호출 없음) → Phase2(질문 1개씩, 최대 3회) → **Phase2R(정리 확인)** → Phase3(상담) → S(위기 시 안전 종료).
Phase3에서 충돌하는 사실이 나오면 Phase2로 1회 복귀한다. 단계는 Phase, 대화 규칙은 P0~P10으로 구분해서 쓴다.

### P4 — 정리 확인 (Phase2R)

조언 전에 들은 내용을 **"일어난 일" / "느낀 마음" / "떠오른 생각"** 세 묶음으로 나눠 보여주고 맞는지 묻는다.
느낌과 생각을 한 칸에 묶으면 사용자가 "서운하다"(감정)와 "질린 것 같다"(추측)를 같은 것으로 보게 되므로 칸을 나눴다.
완충 표현("쯤", "정도", "~것 같다")은 지우지 않는다. 판정은 세 가지다.

1. Phase3 첫 응답 직전 턴에 정리가 있는가 — 정리 응답에 사실/느낌/생각 구분 어구가 있는지 검사
2. 정리에 사용자가 하지 않은 말이 0개인가 — 큰따옴표 인용이 사용자 발화에 있는지 검사 (`unsupported_quotes`)
3. 사용자가 확인한 뒤에 전이했는가 — `recap_confirmed` 없이 Phase3 응답이 나오면 위반

2번은 근사 판정이다. 한국어는 인용하며 어미와 인칭이 바뀌므로("왔어요" → "왔다", "저를" → "나를") 앞부분 60%가 겹치면 같은 말로 본다. 어미만 다른 인용은 통과하고, 앞부분부터 다른 말은 잡힌다.

### 팀원 피드백 반영 (11/11)

조원 4명의 Individual Reflection에서 나온 수정 사항.

| 규칙 | 지적 | 수정 |
| --- | --- | --- |
| P9 | "기억하세요?"가 처방으로 잡힘 | 물음표로 끝나는 문장은 처방에서 제외 (`_is_question_sentence`) |
| P3 · P6 · P9 | 사용자 말을 인용한 부분이 챗봇의 서술로 잡힘 | 세 검사 모두 `strip_quotes` 적용 후 판정 |
| P6 | P4가 요구하는 인용("…는 떠오른 생각이고요")이 상대 내면 서술로 잡힘 | 사용자에게 귀속한 문장은 제외 (`ATTRIBUTION_MARKERS`) |
| P4 | "떠오른 생각"이 해석 칸으로 인식되지 않음 | `RECAP_INTERP_MARKERS` 확장 + 정리를 세 칸으로 |
| P6 | "상대방에게 물어보고 싶은 마음", "상대방을 대하는 본인의 마음"이 상대 내면 서술로 잡힘 | 어휘 매칭을 버리고 **조사로 격을 읽어** 판정 (아래) |
| P9 | "정리하면"(요약)이 처방으로 잡힘 | `(관계\|만남\|둘 사이)를 정리`로 좁힘 |
| P10 | 방법을 물어도 되묻기만 해서 사용자가 막막해짐 | 방향(유지/종료/연락)은 사용자, 방법(문장·순서)은 구체적으로 돕도록 규칙과 Phase3 지시 수정 |

마지막 항목이 규칙 자체를 바꾼 것이고, 나머지 넷은 검사기의 오탐이다.
"결정권을 존중한다"는 것이 "모든 구체적 조언을 거절한다"는 뜻은 아니라는 지적을 그대로 받았다.

### P6 — 조사로 격을 읽는다

오탐이 네 번 연속 같은 원인에서 나왔다. 조사와 어미를 무시하고 어휘만 봤던 것이다.

| 걸린 표현 | 어휘만 보면 | 실제 |
| --- | --- | --- |
| `기억하세요?` | `하세요` → 명령 | 의문 어미 |
| `정리하면` | `정리하` → 관계를 정리 | 요약 |
| `그 마음` | `그` → 3인칭 | 관형사 |
| `상대방에게 ... 싶은 마음` | 상대방 + 마음 | 여격, 사용자의 마음 |
| `상대방을 대하는 본인의 마음` | 상대방 + 마음 | 목적격, 사용자의 마음 |

그래서 P6은 패턴에 예외를 덧붙이는 대신 판정 구조를 바꿨다.
3인칭 명사 **바로 뒤의 조사로 격을 읽고**, 상대방이 마음의 주체인 경우만 본다.

```
주격·주제격·소유격, 또는 조사 없음  → 상대방이 마음의 주체  (위반)
  "상대방의 마음은 떠났어요", "상대방이 무슨 의도로", "상대방 마음이 식었"
목적격·여격 (을/를/에게/한테/께/에)  → 상대방은 행동의 대상  (위반 아님)
  "상대방에게 물어보고 싶은 마음", "상대방을 대하는 본인의 마음"
```

관형사 '그'와 3인칭 '그'는 조사로 구분한다 — `그가`, `그는`만 3인칭으로 본다.
그 뒤에 (1) 모른다고 밝힌 문장, (2) 마음의 주인이 사용자라고 표시한 문장(`본인`, `떠오른 생각`,
`싶은 마음`)을 제외한다.

`tests/test_controller.py::test_third_party_mind_by_case_marker`가 양쪽 10개를 검사하고,
`node tests/js_parity.js`가 웹 페이지의 JS 구현이 같은 판정을 내리는지 확인한다.

목표는 관계 개선이 아니라 (1) 사용자의 주의를 자기 감정·자기 행동으로 옮기는 것과
(2) 관계의 방향을 사용자가 직접 정하게 하는 것이다.

## 웹 버전

- `web/demo.html` — 한 페이지에 두 모드. **시연·재생**(Baseline vs Controlled, API 불필요)과 **직접 대화**(실제 호출).
- `web/live.html` — 직접 대화만 있는 구버전 단독 페이지 (Phase2R 미반영). claude.ai 아티팩트로 배포하면 페이지가 직접 Claude를 호출한다.
  위기 신호(P0)는 모델 호출 전에 JS에서 가로채고, 응답 후 규칙 검사 결과를 칩으로 표시한다.

## Streamlit Community Cloud 배포

팀원이 링크만 열면 쓰게 하는 방법. API key는 저장소에 넣지 않고 Secrets에만 둔다.

1. 이 폴더를 GitHub 저장소로 올린다. `.gitignore`가 `.env`와 `.streamlit/secrets.toml`을 제외한다.
2. share.streamlit.io 에서 GitHub 계정으로 로그인하고 **New app** → 저장소와 `app.py` 선택.
3. **Advanced settings → Secrets** 에 아래 한 줄을 넣는다. (`.streamlit/secrets.toml.example` 참고)

   ```toml
   ANTHROPIC_API_KEY = "sk-ant-..."
   ```

4. Deploy를 누르면 `https://<앱이름>.streamlit.app` 주소가 나온다. 팀원에게 이 주소를 공유한다.

키를 바꾸려면 Settings → Secrets에서 수정하고 **Reboot app**을 누른다.
키가 저장소에 한 번이라도 올라갔다면 Console에서 폐기하고 새로 발급받는다.

### 응답이 중간에 잘리던 문제 (11/11 수정)

Streamlit은 스크립트를 중단할 때 `BaseException`(`StopException` / `RerunException`)을 던진다.
`except anthropic.APIError`로는 잡히지 않으므로, 중단된 응답은 화면에만 남고
`session_state`에는 저장되지 않는다. 그리고 그 중단은 **새 입력이 없어도** 일어난다 —
배포 환경에서 웹소켓이 한 번 끊기고 재연결되면 스크립트가 처음부터 다시 돌아간다.

구버전은 응답 생성이 `st.chat_input`의 반환값에만 매달려 있어서, 재실행되면 그 값이 비고
응답은 영구히 사라졌다. 사용자는 같은 말을 다시 보내야 했고, 그래서 로그에 발화가 두 줄로 쌓였다.

세 가지로 고쳤다.

1. **전송을 두 단계로** — 입력 시 사용자 메시지만 쌓고 `pending = True` 후 `st.rerun()`,
   다시 그린 화면에서 호출한다. 호출해야 할 일이 `session_state`에 남아 있으니
   어떤 이유로 재실행돼도 이어서 받는다. 이 동안 `st.chat_input(disabled=True)`로 입력을 막는다.
2. **스트리밍 선택** — 기본값은 끈 상태(`client.complete()`). 한 번에 받으므로
   중간에 끊겨 유실될 조각이 없다. 켜면 흐르듯 나오지만 연결이 끊기면 그 턴이 잘릴 수 있다.
3. **예외 범위** — `except Exception`으로 넓혀서 호출 실패가 조용히 사라지지 않게 했다.
   재실행 예외는 `BaseException`이라 그대로 통과한다.

`pending`이 남았는데 마지막 메시지가 사용자 발화가 아니면 플래그를 내려서,
입력창이 영구히 잠기는 상태를 막는다. `tests/test_app_stream.py`가 이 다섯 가지를 검사한다.

### 대화 로그

사이드바의 **대화 로그 내려받기**로 JSONL을 받는다. 배포 환경에서는 서버에 파일을 써도
컨테이너가 재시작되면 사라지므로, 로그는 브라우저로 직접 내려받는다.
미리보기 영역에서 복사해 노션에 붙여도 된다.

한 줄이 한 메시지이고, 챗봇 응답에는 `phase`와 `flags`(규칙 검사 결과)가 붙는다.

### 공용 키 보호 장치

`app.py` 상단 상수로 조절한다.

| 상수 | 기본값 | 의미 |
| --- | --- | --- |
| `MAX_TURNS` | 20 | 세션당 사용자 발화 수 |
| `MAX_INPUT_CHARS` | 600 | 한 번에 보낼 수 있는 길이 |
| `MAX_TOKENS_CAP` | 1024 | max_tokens 상한 |
| `SESSION_COST_CAP` | 0.20 | 세션당 추정 비용(USD) 상한 |

사이드바에 세션 누적 사용량과 추정 비용이 표시된다. 추정치는 공식 단가 기준이며 실제 청구액은 Console에서 확인한다.
브라우저 세션마다 상한이 따로 적용되므로, 링크가 넓게 퍼지면 전체 사용량은 Console의 usage 페이지에서 직접 봐야 한다.
