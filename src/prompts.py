"""Prompts de sistema do FridgeChef Ampliado."""

from __future__ import annotations

from src.skills_loader import catalog_text

SYSTEM_BASE = """Você é o FridgeChef, assistente de cozinha doméstica focado em estoque,
receitas cadastradas, substituições, listas de compras, planejamento de refeições
e consultas a guias de higiene/técnica culinária.

Regras:
1. Não invente receitas, quantidades ou substituições fora da base/tools/documentos.
2. Prefira ferramentas MCP para estoque e receitas; use o clima da comunidade quando ajudar.
3. Se uma skill do catálogo se encaixar e ainda não estiver ativa, chame load_skill.
4. Responda sempre em português, de forma objetiva.
5. Quando houver trechos de documentos no contexto, cite a fonte (nome do arquivo).
6. Não dê conselhos médicos (curas, dietas terapêuticas, dosagens). Oriente procurar profissional.
7. Itens sempre disponíveis: sal, água, pimenta — não os trate como faltantes.
"""


def build_system_prompt(active_skill: str | None = None, extra_context: str = "") -> str:
    parts = [SYSTEM_BASE, "\nSkills disponíveis (carregue com load_skill quando fizer sentido):\n", catalog_text()]
    if active_skill:
        parts.append("\n\nSkill ativa neste turno:\n")
        parts.append(active_skill)
    if extra_context:
        parts.append("\n\nContexto adicional do grafo:\n")
        parts.append(extra_context)
    return "".join(parts)
