from pathlib import Path

import pytest
import yaml

from chatbot import PersonaError, build_system_prompt, list_personas, load_persona

ROOT = Path(__file__).resolve().parents[1] / "personas"


def test_list_hides_template():
    keys = list_personas(ROOT)
    assert "socratic_tutor" in keys
    assert "_template" not in keys


@pytest.mark.parametrize("key", list_personas(ROOT) + ["_template"])
def test_all_personas_load(key):
    p = load_persona(ROOT / key)
    assert p.principles


def test_prompt_contains_principles_and_examples_in_priority_order():
    p = load_persona(ROOT / "socratic_tutor")
    sp = build_system_prompt(p)
    assert "<principles>" in sp and "<examples>" in sp
    pos = [sp.index(f'id="{x.id}"') for x in p.principles]
    assert pos == sorted(pos)
    for ex in p.examples:
        for t in ex.turns:
            assert t.user.splitlines()[0] in sp


def _write(tmp_path, principles, examples):
    (tmp_path / "principles.yaml").write_text(yaml.safe_dump(principles, allow_unicode=True), encoding="utf-8")
    (tmp_path / "examples.yaml").write_text(yaml.safe_dump(examples, allow_unicode=True), encoding="utf-8")


BASE = {"name": "t", "role": "r", "principles": [{"id": "a", "rule": "x"}]}


def test_unknown_applies_id_rejected(tmp_path):
    _write(tmp_path, BASE, {"examples": [{"applies": ["nope"], "turns": [{"user": "u", "assistant": "a"}]}]})
    with pytest.raises(PersonaError, match="nope"):
        load_persona(tmp_path)


def test_duplicate_principle_id_rejected(tmp_path):
    bad = dict(BASE, principles=[{"id": "a", "rule": "x"}, {"id": "a", "rule": "y"}])
    _write(tmp_path, bad, {"examples": []})
    with pytest.raises(PersonaError, match="중복"):
        load_persona(tmp_path)


def test_xml_escaped(tmp_path):
    _write(tmp_path, dict(BASE, role="<b>&"), {"examples": []})
    sp = build_system_prompt(load_persona(tmp_path))
    assert "&lt;b&gt;&amp;" in sp
