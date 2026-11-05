"""
Servidor MCP no estilo comunidade: clima e dicas de refeição.

Em ambiente de aula, troque MCP_COMMUNITY_URL pela URL pública do mural.
Este processo local permite rodar o projeto só com o README.
"""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from fastmcp import FastMCP

mcp = FastMCP("comunidade-clima-refeicoes")

# Clima simulado por cidade (determinístico para testes)
_WEATHER = {
    "recife": {"temp_c": 29, "condition": "ensolarado", "humidity": 70},
    "sao paulo": {"temp_c": 22, "condition": "nublado", "humidity": 65},
    "curitiba": {"temp_c": 16, "condition": "frio e úmido", "humidity": 80},
    "brasilia": {"temp_c": 26, "condition": "seco", "humidity": 35},
    "rio de janeiro": {"temp_c": 31, "condition": "quente", "humidity": 75},
}


@mcp.tool
def get_weather(city: str = "Recife") -> str:
    """Retorna clima atual (simulado) de uma cidade brasileira para planejar refeições."""
    key = city.strip().lower()
    data = _WEATHER.get(key)
    if not data:
        known = ", ".join(sorted(_WEATHER))
        return (
            f"Cidade '{city}' não encontrada na base simulada. "
            f"Disponíveis: {known}."
        )
    tip = "prefira pratos leves e gelados"
    if data["temp_c"] <= 18:
        tip = "prefira sopas e pratos quentes"
    elif data["temp_c"] <= 24:
        tip = "pratos mornas ou refeições equilibradas funcionam bem"
    return (
        f"Clima em {city.title()}: {data['temp_c']}°C, {data['condition']}, "
        f"umidade {data['humidity']}%. Sugestão: {tip}."
    )


@mcp.tool
def meal_timing_tip(city: str = "Recife") -> str:
    """Sugere horário e tipo de refeição com base no horário local e no clima."""
    now = datetime.now(ZoneInfo("America/Recife"))
    hour = now.hour
    weather = get_weather(city)
    if 5 <= hour < 11:
        slot = "café da manhã / brunch"
    elif 11 <= hour < 15:
        slot = "almoço"
    elif 15 <= hour < 18:
        slot = "lanche da tarde"
    else:
        slot = "jantar"
    return f"Agora são {now.strftime('%H:%M')}. Faixa sugerida: {slot}. {weather}"


@mcp.resource("resource://comunidade/cidades")
def cidades() -> str:
    """Lista de cidades com clima simulado."""
    return "Cidades: " + ", ".join(sorted(c.title() for c in _WEATHER))


@mcp.prompt
def planejar_pelo_clima(cidade: str = "Recife") -> str:
    """Instruções para planejar refeição considerando o clima."""
    return (
        f"Consulte get_weather('{cidade}') e meal_timing_tip('{cidade}'). "
        "Combine o clima com o estoque do usuário e sugira uma refeição adequada."
    )


if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8001, show_banner=False)
