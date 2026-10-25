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
  - **직접 대화** — 실제 모델 호출. Baseline / Controlled 전환, phase·slot·system prompt 확인, 대화 로그 JSONL 저장
  - **시연 · 재생** — 구성한 대화를 한 턴씩 재생. 모델을 호출하지 않아 API key 없이도 동작 (`chatbot/scenarios.py`)

Phase 전이: Phase1(폼, LLM 호출 없음) → Phase2(질문 1개씩, 최대 3회) → **Phase2R(정리 확인)** → Phase3(상담) → S(위기 시 안전 종료).
Phase3에서 충돌하는 사실이 나오면 Phase2로 1회 복귀한다. 단계는 Phase, 대화 규칙은 P0~P10으로 구분해서 쓴다.

### P4 — 정리 확인 (Phase2R)

조언 전에 들은 내용을 "일어난 일"과 "사용자의 해석"으로 나눠 보여주고 맞는지 묻는다. 판정은 세 가지다.

1. Phase3 첫 응답 직전 턴에 정리가 있는가 — 정리 응답에 사실/해석 구분 어구가 있는지 검사
2. 정리에 사용자가 하지 않은 말이 0개인가 — 큰따옴표 인용이 사용자 발화에 있는지 검사 (`unsupported_quotes`)
3. 사용자가 확인한 뒤에 전이했는가 — `recap_confirmed` 없이 Phase3 응답이 나오면 위반

2번은 근사 판정이다. 한국어는 인용하며 어미와 인칭이 바뀌므로("왔어요" → "왔다", "저를" → "나를") 앞부분 60%가 겹치면 같은 말로 본다. 어미만 다른 인용은 통과하고, 앞부분부터 다른 말은 잡힌다.

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
