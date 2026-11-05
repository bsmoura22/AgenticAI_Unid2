---
name: planejar-refeicoes
description: Use quando o usuário quiser planejar duas ou mais refeições em sequência, combinar estoque com clima, ou verificar se um cardápio cabe no inventário sem alterar o estoque real.
---

# Planejar refeições consecutivas

Siga este fluxo multi-etapa (não pule ferramentas):

1. Confirme o estoque atual com `get_inventory` (ou o snapshot já no contexto).
2. Se a cidade/clima for relevante, chame `get_weather` ou `meal_timing_tip`.
3. Escolha candidatas com `search_recipes` (respeite o tempo máximo pedido).
4. Valide a sequência com `simulate_meal_plan` passando os ids separados por vírgula.
5. Se algum passo falhar por falta de ingrediente:
   - tente `find_substitution` para o item faltante; ou
   - troque a ordem/receita e simule de novo.
6. Responda em português com: cardápio final, o que cada refeição consome, e o inventário simulado ao final.
7. Não chame `update_inventory` só por planejar — a simulação não altera o estoque real.
