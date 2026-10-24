"""Persona(원칙 + 예시) 로딩 및 검증."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml


class PersonaError(ValueError):
    pass


@dataclass
class Principle:
    id: str
    rule: str
    priority: int = 100
    rationale: str = ""


@dataclass
class Turn:
    user: str
    assistant: str


@dataclass
class Example:
    situation: str
    turns: list[Turn]
    applies: list[str] = field(default_factory=list)
    note: str = ""


@dataclass
class Persona:
    key: str
    name: str
    role: str
    principles: list[Principle]
    examples: list[Example]
    description: str = ""


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise PersonaError(f"파일이 없습니다: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict):
        raise PersonaError(f"YAML 최상위는 mapping이어야 합니다: {path}")
    return data


def load_persona(persona_dir: str | Path) -> Persona:
    d = Path(persona_dir)
    p = _load_yaml(d / "principles.yaml")
    e = _load_yaml(d / "examples.yaml")

    for k in ("name", "role", "principles"):
        if not p.get(k):
            raise PersonaError(f"principles.yaml에 '{k}'가 필요합니다 ({d.name})")

    principles = []
    for i, raw in enumerate(p["principles"]):
        if not raw.get("id") or not raw.get("rule"):
            raise PersonaError(f"principles[{i}]에 id와 rule이 필요합니다 ({d.name})")
        principles.append(
            Principle(
                id=str(raw["id"]),
                rule=str(raw["rule"]).strip(),
                priority=int(raw.get("priority", 100)),
                rationale=str(raw.get("rationale", "")).strip(),
            )
        )
    ids = [x.id for x in principles]
    if len(ids) != len(set(ids)):
        raise PersonaError(f"principle id가 중복됩니다 ({d.name})")
    principles.sort(key=lambda x: x.priority)

    examples = []
    for i, raw in enumerate(e.get("examples") or []):
        turns_raw = raw.get("turns") or []
        if not turns_raw:
            raise PersonaError(f"examples[{i}]에 turns가 필요합니다 ({d.name})")
        turns = []
        for j, t in enumerate(turns_raw):
            if "user" not in t or "assistant" not in t:
                raise PersonaError(f"examples[{i}].turns[{j}]에 user와 assistant가 필요합니다 ({d.name})")
            turns.append(Turn(user=str(t["user"]).strip(), assistant=str(t["assistant"]).strip()))
        applies = [str(a) for a in (raw.get("applies") or [])]
        unknown = set(applies) - set(ids)
        if unknown:
            raise PersonaError(f"examples[{i}].applies에 없는 principle id: {sorted(unknown)} ({d.name})")
        examples.append(
            Example(
                situation=str(raw.get("situation", "")).strip(),
                turns=turns,
                applies=applies,
                note=str(raw.get("note", "")).strip(),
            )
        )

    return Persona(
        key=d.name,
        name=str(p["name"]),
        description=str(p.get("description", "")),
        role=str(p["role"]).strip(),
        principles=principles,
        examples=examples,
    )


def list_personas(root: str | Path) -> list[str]:
    """'_'로 시작하지 않고 principles.yaml이 있는 폴더 목록."""
    r = Path(root)
    return sorted(
        c.name
        for c in r.iterdir()
        if c.is_dir() and not c.name.startswith("_") and (c / "principles.yaml").exists()
    )
