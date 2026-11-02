# Operação VISUAL

Representar com diagramas o que a explicação descreve como mecanismo: processo, ordem de interações, estados, causalidade, estrutura de um domínio ou posição relativa de atores. O diagrama vive como Mermaid no próprio texto; quando o usuário vai mostrar, apresentar ou enviar, ele vira cena Excalidraw editável e PNG no tema do vault.

## Acionamento

- Pedidos explícitos (`/thinker-visual`, "faz um diagrama", "desenha esse fluxo", "mostra isso visualmente") executam a operação.
- Por iniciativa própria, em qualquer operação: quando a resposta, a página ou o material descreve um mecanismo que o texto sozinho deixa difícil de seguir, proponha ou inclua um diagrama Mermaid. Um diagrama por ideia, ao lado do texto que ele explica; não substitui o argumento escrito.
- Não desenhe para enfeitar. Diagrama que só repete uma lista, uma hierarquia trivial ou uma única relação não entra. Se o mecanismo for incerto, desenhe o que está sustentado e marque o restante como hipótese (borda tracejada ou rótulo explícito), sem fechar o fluxo por estética.
- Se `vault-heuristics.md` tiver preferência visual, ela prevalece sobre estes defaults.

## Repertório: que pergunta, que diagrama

| Pergunta | Mermaid | Cuidado |
|---|---|---|
| Como o processo anda, com decisões? | `flowchart LR` ou `TD` | Losango só para decisão real; rótulo nas setas de saída. |
| Quem fala com quem, em que ordem? | `sequenceDiagram` | Participantes nomeados pelo papel; `Note over` para a regra que sustenta o fluxo. |
| Em que fases algo passa e o que muda de fase? | `stateDiagram-v2` | Estados são substantivos, transições são eventos. |
| Por que algo se reforça ou se freia? (sistema) | `flowchart LR` como laço causal | Setas com `+` (mesma direção) ou `−` (direção oposta); marque o laço como `R` (reforço) ou `B` (equilíbrio) e inclua o atraso quando existir. Leitura de sistema exige fechar o laço com evidência, não só listar fatores. |
| Como as partes de um domínio se relacionam? | `erDiagram` ou `classDiagram` | Cardinalidade só quando conhecida. |
| Onde os atores ou opções se posicionam? | `quadrantChart` | Eixos com polos nomeados; posição é julgamento, diga a base. |
| Quando as coisas acontecem? | `timeline` ou `gantt` | Datas absolutas. |
| Como o todo se divide? | `mindmap` | Só quando a decomposição for a mensagem. |

Escrita: `<br/>` quebra linha no rótulo; rótulo com parênteses, dois-pontos ou aspas vai entre aspas (`A["fase 1: análise"]`); ids curtos e rótulos legíveis. Ênfase usa classes do tema (`A:::destaque`) em vez de cor fixa no texto, para a página continuar neutra e a saída seguir a marca.

## Fonte e saída

- **Fonte:** bloco ` ```mermaid ` na página, rascunho ou resposta. É texto versionado e diffável; o Obsidian o renderiza sem plugin. Página da wiki recebe só o bloco Mermaid, nunca PNG nem `.excalidraw` (contrato: `wiki/` só aceita `.md`).
- **Saída:** cena `.excalidraw` editável e PNG em `output/visual-<slug>/`, ou na pasta `output/` da operação que pediu o material (One Page, deck, apresentação). Gere quando o usuário for mostrar, apresentar ou enviar, ou quando pedir; não a cada diagrama.
- **Tema:** `visual-theme.json` no root do vault é o padrão (conteúdo do usuário, nunca sobrescrito pelo installer). Ausente, vale o tema neutro. Cor escrita no próprio Mermaid (`classDef`, `style`) vence o tema; classes declaradas no tema são aplicadas a `:::nome` sem `classDef` correspondente.

## Executar

```bash
bash harness/scripts/visual.sh render <entrada> --out output/visual-<slug>/<nome>
bash harness/scripts/visual.sh check     # Node, navegador, versões e tema em uso
```

- `<entrada>`: `.mmd`, página `.md` (todos os blocos ` ```mermaid `, ou `--block N`), `.excalidraw` já editado (só renderiza) ou `-` (Mermaid pela entrada padrão).
- Opções: `--theme <arquivo>|none`, `--font sans|hand|code`, `--roughness 0|1|2`, `--scale N` (padrão 2), `--transparent`, `--no-png`.
- Pipeline: `@excalidraw/mermaid-to-excalidraw` (layout pelo Pele) → tema → `convertToExcalidrawElements` com o texto medido na fonte final → render local pela `@excalidraw/cli`. Exige Node 22+ e Chrome, Edge ou Chromium instalados (`THINKER_VISUAL_BROWSER` aponta outro).
- Na primeira execução de cada versão, o script instala as dependências fixadas do `package-lock.json` num cache fora do vault (`THINKER_VISUAL_HOME`, padrão `~/.cache/thinker-visual/`), com `npm ci --ignore-scripts`; isso usa a rede uma vez. Avise o usuário antes da primeira preparação. Não instale nada globalmente nem fora desse cache.
- Renderizar não usa conta nem chave. Comandos de workspace do Excalidraw+ ficam fora desta operação; se o usuário pedir, a chave vem de variável de ambiente ou gerenciador de segredos, nunca do chat nem de arquivo versionado.

## Verificar antes de entregar

Abra o PNG gerado e confira: rótulos legíveis e sem sobreposição, setas ligando o que o texto diz, ênfase no ponto certo e leitura em poucos segundos na escala em que será mostrado. Diagrama que precisa de explicação oral para fazer sentido volta para o Mermaid. Diga o que não foi verificado (por exemplo, o tipo de diagrama renderizado no Obsidian).

## Limites

- Viram elementos editáveis: fluxograma (inclusive swimlane), sequência, classe, ER e estado. Os demais tipos entram na cena como imagem.
- Alguns formatos do Mermaid perdem a forma (cilindro vira retângulo). O tema não muda a disposição do layout.
- O Obsidian embute a própria versão do Mermaid; tipos recentes podem não renderizar lá. Confira antes de depender deles numa página.
- Não gera página, entrada de log nem índice por si só; o diagrama entra pela operação que escreve o texto (ingest, query, one-page...).
- Casos de avaliação em `harness/evals/visual.md`, carregados ao avaliar a operação, não a cada uso.
