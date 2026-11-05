"""Servidor MCP próprio do FridgeChef — estoque e receitas."""

from __future__ import annotations

import copy
import json
from pathlib import Path

from fastmcp import FastMCP

ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data" / "recipes.json"
INVENTORY_PATH = Path(__file__).resolve().parent / "inventory.json"

mcp = FastMCP("fridgechef-estoque")


def _load_catalog() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def _always_available() -> set[str]:
    return set(_load_catalog().get("always_available", []))


def _recipes() -> dict:
    return _load_catalog()["recipes"]


def _substitutions() -> dict[tuple[str, str], dict]:
    out: dict[tuple[str, str], dict] = {}
    for row in _load_catalog().get("substitutions", []):
        out[(row["recipe_id"], row["ingredient"])] = {
            "substitute": row["substitute"],
            "ratio": row["ratio"],
            "note": row["note"],
        }
    return out


def _load_inventory() -> dict:
    if not INVENTORY_PATH.exists():
        return {}
    return json.loads(INVENTORY_PATH.read_text(encoding="utf-8"))


def _save_inventory(inv: dict) -> None:
    INVENTORY_PATH.write_text(
        json.dumps(inv, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _has_enough(inv: dict, item: str, qty: float) -> bool:
    if item in _always_available():
        return True
    info = inv.get(item.lower())
    if not info:
        return False
    return float(info.get("qty", 0)) >= float(qty)


@mcp.tool
def get_inventory() -> str:
    """Retorna todos os itens e quantidades do estoque atual da geladeira."""
    inv = _load_inventory()
    if not inv:
        return json.dumps({"inventory": {}, "message": "Estoque vazio."}, ensure_ascii=False)
    return json.dumps({"inventory": inv}, ensure_ascii=False)


@mcp.tool
def update_inventory(
    item: str,
    quantity: float,
    unit: str = "unidade",
    operation: str = "add",
) -> str:
    """Atualiza o estoque. operation: add, remove ou set."""
    item = item.lower().strip()
    inv = _load_inventory()
    current = float(inv.get(item, {}).get("qty", 0.0))
    op = operation.lower().strip()
    if op == "add":
        new_qty = current + float(quantity)
    elif op == "remove":
        new_qty = current - float(quantity)
    elif op == "set":
        new_qty = float(quantity)
    else:
        return json.dumps(
            {"ok": False, "error": f"operation inválida: {operation}. Use add|remove|set."},
            ensure_ascii=False,
        )
    if new_qty <= 0:
        inv.pop(item, None)
        new_qty = 0.0
    else:
        inv[item] = {"qty": new_qty, "unit": unit}
    _save_inventory(inv)
    return json.dumps(
        {"ok": True, "item": item, "qty": new_qty, "unit": unit, "operation": op},
        ensure_ascii=False,
    )


@mcp.tool
def search_recipes(max_time: int = 999) -> str:
    """Busca receitas realizáveis com o estoque atual e limite de tempo em minutos."""
    inv = _load_inventory()
    can_make = []
    near_complete = []
    for rid, recipe in _recipes().items():
        if int(recipe["time"]) > int(max_time):
            continue
        missing = []
        for ing, spec in recipe["ingredients"].items():
            if not _has_enough(inv, ing, spec["qty"]):
                missing.append(ing)
        entry = {
            "id": rid,
            "name": recipe["name"],
            "time": recipe["time"],
            "servings": recipe["servings"],
            "missing": missing,
        }
        if not missing:
            can_make.append(entry)
        elif len(missing) == 1:
            near_complete.append(entry)
    return json.dumps(
        {"can_make": can_make, "near_complete": near_complete, "max_time": max_time},
        ensure_ascii=False,
    )


@mcp.tool
def find_substitution(recipe_id: str, ingredient: str) -> str:
    """Encontra substituição cadastrada para um ingrediente em uma receita."""
    key = (recipe_id.strip(), ingredient.lower().strip())
    subs = _substitutions()
    if key in subs:
        payload = {"found": True, "recipe_id": key[0], "ingredient": key[1], **subs[key]}
        return json.dumps(payload, ensure_ascii=False)
    return json.dumps(
        {
            "found": False,
            "recipe_id": key[0],
            "ingredient": key[1],
            "message": "Nenhuma substituição cadastrada para esse par.",
        },
        ensure_ascii=False,
    )


@mcp.tool
def generate_shopping_list(recipe_id: str, servings: int | None = None) -> str:
    """Lista o que falta no estoque para preparar uma receita (escala por porções)."""
    recipes = _recipes()
    if recipe_id not in recipes:
        return json.dumps(
            {"ok": False, "error": f"Receita '{recipe_id}' não encontrada.", "available": list(recipes)},
            ensure_ascii=False,
        )
    recipe = recipes[recipe_id]
    base = int(recipe["servings"])
    target = int(servings) if servings else base
    scale = target / base
    inv = _load_inventory()
    missing = []
    for ing, spec in recipe["ingredients"].items():
        if ing in _always_available():
            continue
        need = float(spec["qty"]) * scale
        have = float(inv.get(ing, {}).get("qty", 0.0))
        if have < need:
            missing.append(
                {
                    "item": ing,
                    "need": need,
                    "have": have,
                    "buy": need - have,
                    "unit": spec["unit"],
                }
            )
    return json.dumps(
        {
            "ok": True,
            "recipe_id": recipe_id,
            "name": recipe["name"],
            "servings": target,
            "missing": missing,
        },
        ensure_ascii=False,
    )


@mcp.tool
def simulate_meal_plan(recipe_ids: str) -> str:
    """Simula consumo sequencial de receitas (ids separados por vírgula) sem alterar o estoque real."""
    recipes = _recipes()
    temp_inv = copy.deepcopy(_load_inventory())
    steps = []
    ids = [x.strip() for x in recipe_ids.split(",") if x.strip()]
    for rid in ids:
        if rid not in recipes:
            steps.append({"recipe_id": rid, "ok": False, "error": "receita não encontrada"})
            continue
        recipe = recipes[rid]
        missing = []
        for ing, spec in recipe["ingredients"].items():
            if not _has_enough(temp_inv, ing, spec["qty"]):
                missing.append(ing)
        if missing:
            steps.append(
                {
                    "recipe_id": rid,
                    "name": recipe["name"],
                    "ok": False,
                    "missing": missing,
                }
            )
            continue
        for ing, spec in recipe["ingredients"].items():
            if ing in _always_available():
                continue
            qty = float(temp_inv.get(ing, {}).get("qty", 0.0)) - float(spec["qty"])
            unit = temp_inv.get(ing, {}).get("unit", spec["unit"])
            if qty <= 0:
                temp_inv.pop(ing, None)
            else:
                temp_inv[ing] = {"qty": qty, "unit": unit}
        steps.append({"recipe_id": rid, "name": recipe["name"], "ok": True, "missing": []})
    return json.dumps(
        {"steps": steps, "inventory_after_simulation": temp_inv},
        ensure_ascii=False,
    )


@mcp.tool
def reset_inventory(items_json: str = "{}") -> str:
    """Redefine o estoque. items_json é um JSON {item: {qty, unit}}."""
    try:
        items = json.loads(items_json) if items_json else {}
    except json.JSONDecodeError as exc:
        return json.dumps({"ok": False, "error": f"JSON inválido: {exc}"}, ensure_ascii=False)
    normalized = {}
    for item, spec in items.items():
        normalized[item.lower()] = {
            "qty": float(spec.get("qty", 0)),
            "unit": spec.get("unit", "unidade"),
        }
    _save_inventory(normalized)
    return json.dumps({"ok": True, "inventory": normalized}, ensure_ascii=False)


@mcp.resource("resource://fridgechef/catalogo")
def catalogo() -> str:
    """Ficha do catálogo de receitas do FridgeChef."""
    recipes = _recipes()
    lines = [
        "Catálogo FridgeChef",
        f"Total de receitas: {len(recipes)}",
        "Itens sempre disponíveis: " + ", ".join(sorted(_always_available())),
        "",
    ]
    for rid, recipe in recipes.items():
        lines.append(f"- {rid}: {recipe['name']} ({recipe['time']} min, {recipe['servings']} porções)")
    return "\n".join(lines)


@mcp.prompt
def montar_jantar(tempo_max_minutos: int = 30) -> str:
    """Instruções para montar um jantar com o tempo disponível."""
    return (
        f"Monte um jantar usando no máximo {tempo_max_minutos} minutos. "
        "1) Chame get_inventory. 2) Chame search_recipes com max_time. "
        "3) Se faltar um item, tente find_substitution. "
        "4) Responda em português com a receita escolhida e o motivo."
    )


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000, show_banner=False)
