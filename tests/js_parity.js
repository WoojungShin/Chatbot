// web/demo.html의 JS 검사기가 chatbot/controller.py와 같은 판정을 내리는지 확인한다.
//   node tests/js_parity.js
// 두 블록(시연·재생 / 직접 대화)의 thirdPartyMind를 꺼내서 같은 케이스로 돌린다.
const fs = require("fs");
const path = require("path");

const HTML = path.join(__dirname, "..", "web", "demo.html");
const blocks = [...fs.readFileSync(HTML, "utf8").matchAll(/<script>([\s\S]*?)<\/script>/g)]
  .map((m) => m[1]);

// [문장, P6 위반인가] — tests/test_controller.py의 test_third_party_mind_by_case_marker와 같은 집합
const CASES = [
  ["상대방의 마음은 이미 떠난 것으로 보여요.", true],
  ["상대방이 무슨 의도로 그랬는지 뻔하네요.", true],
  ["상대방 마음이 식은 것 같아요.", true],
  ["그는 당신을 소중히 여기지 않는 것 같네요.", true],
  ["그런 사람에게 뭐라고 하실 건가요?", true],
  ["상대방에게 물어보고 싶은 마음은 있으세요?", false],
  ["상대방을 대하는 본인의 태도나 마음에 달라진 게 있으세요?", false],
  ["그 마음을 안고 기다리실 수도 있어요.", false],
  ["상대방이 무슨 생각인지는 아직 확인된 게 아니에요.", false],
  ["“저한테 질린 것 같다”는 떠오른 생각이고요.", false],
];

let failed = 0;

blocks.forEach((body, bi) => {
  const opened = body
    .replace(/^\s*\(function\s*\(\)\s*\{/, "")
    .replace(/\}\)\(\);?\s*$/, "");
  const labelName = bi === 0 ? "THIRD_PARTY_MIND_LABEL" : "THIRD_PARTY_LABEL";
  const src = `
    var document = new Proxy(function () {}, {
      get: () => () => ({ style: {}, appendChild() {}, addEventListener() {},
                          classList: { add() {}, remove() {} } }),
      apply: () => ({}),
    });
    var window = { addEventListener() {}, location: {} };
    try { ${opened} } catch (e) {}
    return typeof thirdPartyMind === "function"
      ? { f: thirdPartyMind, L: ${labelName} }
      : null;
  `;

  let api = null;
  try {
    api = new Function(src)();
  } catch (e) {
    console.log(`블록${bi}: 실행 실패 — ${e.message}`);
    failed++;
    return;
  }
  if (!api) {
    console.log(`블록${bi}: thirdPartyMind를 꺼내지 못했다`);
    failed++;
    return;
  }

  let bad = 0;
  for (const [text, expected] of CASES) {
    const got = api.f(text, api.L);
    if (got !== expected) {
      console.log(`  블록${bi} 불일치 — 기대 ${expected}, 결과 ${got} | ${text}`);
      bad++;
    }
  }
  console.log(`블록${bi}: ${CASES.length - bad}/${CASES.length} 일치`);
  failed += bad;
});

process.exit(failed ? 1 : 0);
