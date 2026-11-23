---
name: substituir-e-comprar
description: Use quando faltar ingrediente para uma receita, o usuário pedir substituições e/ou lista de compras escalada por porções.
---

# Substituir ingredientes e montar lista de compras

Fluxo multi-etapa:

1. Identifique a `recipe_id` desejada (use o catálogo / `search_recipes` se necessário).
2. Gere a lista do que falta com `generate_shopping_list` (ajuste `servings` se pedido).
3. Para cada item faltante, tente `find_substitution`.
4. Se a base cadastrada não tiver substituição, use os trechos de documentos já recuperados no contexto (guias de substituição/técnica). Não invente proporções fora dos docs ou da base.
5. Monte a resposta assim:
   - receita e porções;
   - substituições aplicáveis;
   - lista de compras final já convertida;
   - o que permanece faltando sem substituto.
6. Só sugira alterar estoque com `update_inventory` se o usuário pedir explicitamente para registrar compra ou consumo.
