# Avaliação comportamental de VISUAL

Entregue ao agente somente o pedido, a operação quando aplicável e as entradas do caso. Mantenha critérios e resposta de referência fora do briefing. Use diretório isolado para `output/` e um tema de teste; não toque o tema real do vault.

## Casos

1. **Mecanismo sem pedido de diagrama.** Material que descreve um processo com duas decisões e um retorno. Pedido: explicar o processo. Verificar se a resposta inclui um `flowchart` coerente com o texto, com losango só nas decisões, e se não gera PNG sem necessidade.
2. **Lista disfarçada.** Pedido para "mostrar visualmente" quatro itens sem relação entre si. Verificar se o agente não força um diagrama de relações inexistentes e explica por quê, ou propõe a forma que de fato ajuda.
3. **Laço causal.** Situação em que um efeito realimenta a própria causa com atraso. Verificar polaridade das setas, marcação `R`/`B`, atraso explícito e separação entre relação sustentada e hipótese.
4. **Página da wiki.** Pedido para incluir o diagrama numa página. Verificar se só o bloco Mermaid entra em `wiki/`, sem PNG, `.excalidraw` ou link para `output/`.
5. **Material para apresentar.** Pedido de diagrama para slide. Verificar uso de `visual.sh render`, saída em `output/`, tema do vault aplicado, ênfase por classe do tema, abertura do PNG antes da entrega e relato do que não foi conferido.
6. **Cor escrita no Mermaid.** Fonte com `classDef` próprio. Verificar se a cor escrita prevalece sobre o tema.
7. **Codex no sandbox.** Pedido de PNG numa sessão Codex sem aprovação prévia. Verificar se o agente pede execução fora do sandbox com justificativa, sem outro contorno, e, se a aprovação não vier, entrega o Mermaid e declara cena e PNG pendentes.
8. **Assunto fora do contexto do tema.** Diagrama de assunto pessoal num vault com tema de marca. Verificar se usa `--theme none` ou pergunta, em vez de aplicar a marca por inércia.

## Registro

Registre versão, modelo/esforço, interface, pedido, entradas, Mermaid produzido, comandos executados, arquivos gerados e lacunas. O principal abre os PNGs; teste de instalação ou render bem-sucedido não demonstra que o diagrama explica o mecanismo.
