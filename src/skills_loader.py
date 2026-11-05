"""Catálogo e carregamento sob demanda de skills."""

from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
SKILLS_DIR = ROOT / "skills"


def _parse_skill(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if text.startswith("---"):
        _, front, body = text.split("---", 2)
        meta = yaml.safe_load(front) or {}
        return {
            "name": meta.get("name", path.parent.name),
            "description": meta.get("description", ""),
            "body": body.strip(),
            "path": str(path),
        }
    return {
        "name": path.parent.name,
        "description": "",
        "body": text.strip(),
        "path": str(path),
    }


def list_skills() -> list[dict]:
    skills = []
    for skill_md in sorted(SKILLS_DIR.glob("*/SKILL.md")):
        skills.append(_parse_skill(skill_md))
    return skills


def catalog_text() -> str:
    lines = []
    for skill in list_skills():
        lines.append(f"- {skill['name']}: {skill['description']}")
    return "\n".join(lines) if lines else "(nenhuma skill)"


def load_skill(name: str) -> str:
    name = name.strip()
    for skill in list_skills():
        if skill["name"] == name:
            return f"# Skill: {skill['name']}\n\n{skill['body']}"
    available = ", ".join(s["name"] for s in list_skills())
    return f"Skill '{name}' não encontrada. Disponíveis: {available}"
