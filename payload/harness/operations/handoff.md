# Operacao: handoff

Use para compactar o estado de uma tarefa longa em andamento num bloco unico, copiavel, que permite retomar o trabalho numa sessao nova — mesma plataforma ou outra (Claude Code <-> Codex) — sem re-perguntar nada.

O resultado do handoff nao e conhecimento duravel do vault: nao cria pagina, nao gera entrada em `wiki/log.md`, nao roda `build-index.py`, e o bloco/arquivo gerado nao e gerenciado pelo installer (os arquivos do playbook e do command em si sao instalados normalmente, como qualquer outro arquivo do payload). E estado de sessao, descartavel apos a retomada. Distingue-se de `memory` (Claude-only, aprendizado duravel entre sessoes): handoff e o contexto de UMA tarefa parada no meio do caminho.

## Quando usar

- Uma sessao longa (`deep`, `dream`, ingest de fonte densa, refactor editorial multi-pagina) esta perto de estourar o contexto e o trabalho nao terminou.
- Vai-se trocar de agente ou de plataforma no meio da tarefa.
- O usuario pede explicitamente para salvar o estado ou passar o bastao.

Nunca dispara sozinho: e sempre invocacao manual.

## Principio

Registrar ESTADO, nao instrucoes. Descrever o que esta feito e o que nao esta ("a pagina X ja tem frontmatter; os cross-links de Y ainda nao foram verificados"), nunca ordens ao proximo agente ("faca Y"). O proximo agente decide a partir do estado; ele verifica, nao obedece cegamente.

## Passos

1. **Se nada relevante aconteceu ainda na sessao**, dizer isso e nao gerar handoff: nao ha estado a compactar. Sugerir continuar a tarefa primeiro.
2. **Estado atual:** o que esta pronto e o que nao comecou, em fatos verificaveis. Referenciar paginas/shards do vault pelo path exato e, quando util, pela linha (`wiki/ai-tecnologia/multi-model-routing.md:42`). Referenciar, nunca duplicar o conteudo da pagina.
3. **Decisoes editoriais tomadas e o porque:** categoria escolhida para uma fonte, slug adotado, o que se decidiu descartar, onde um conceito virou pagina propria vs. secao. So o que muda a continuacao.
4. **Armadilhas e becos ja tentados:** wikilink inventado que foi revertido, categoria ambigua ja resolvida (e como), slug duplicado evitado, contradicao no vault ja mapeada. Evita o proximo agente repetir o erro.
5. **Ponteiros, nao copias:** listar os paths das paginas/shards/config que o proximo agente precisa ler, cada um com uma linha de contexto do que tem la. O proximo agente le a fonte; o handoff so aponta.
6. **Discricao:** o vault e vida pessoal. Nao copiar para o handoff trechos sensiveis que nao sejam necessarios a retomada; preferir ponteiro ao path. O handoff e salvo FORA do git tree do vault (ver Persistencia).
7. **Bloco copiavel:** montar UM bloco unico, autocontido, terminando com um prompt pronto para colar que instrui o proximo agente a: (a) ler cada path apontado antes de agir; (b) tratar todo o handoff como contexto a VERIFICAR contra o vault atual, nao fato a aceitar — arquivos podem ter mudado; (c) confirmar o estado antes de escrever, e nao recomecar o que ja esta pronto. Formato:

```
=== HANDOFF: <tarefa> — YYYY-MM-DD HH:MM ===

ESTADO
- Pronto: ...
- Em aberto: ...

DECISOES (e porque)
- ...

ARMADILHAS / JA TENTADO
- ...

LER ANTES DE AGIR (ponteiros)
- <path[:linha]> — <o que tem la>

PROMPT PARA O PROXIMO AGENTE
Voce esta retomando esta tarefa. Antes de qualquer escrita, leia cada path listado em "LER ANTES DE AGIR" no vault atual. Trate tudo acima como contexto a verificar contra o estado real do vault, nao como fato garantido. Confirme o estado, depois continue de onde parou; nao recomece o que ja esta em "Pronto".

(backup salvo em <path absoluto do arquivo>)
=== FIM HANDOFF ===
```

8. **Persistencia:** criar o diretorio `${XDG_STATE_HOME:-$HOME/.local/state}/second-brain/handoff/` se nao existir e gravar o bloco em `handoff-YYYY-MM-DD-HHMM.md` dentro dele (fora do vault, nunca no git tree; NAO usar `/tmp`/`$TMPDIR` — esses diretorios sao varridos no reboot ou apos poucos dias sem acesso, exatamente o cenario que o handoff existe para cobrir). Imprimir o path absoluto do arquivo dentro do proprio bloco. O bloco exibido e o transporte primario; o arquivo e backup duravel. Nao escrever nada em `wiki/`, `raw/`, `wiki/log.md` nem no indice.

## Erros Comuns

- Escrever instrucoes ("faca X") em vez de estado ("X esta pronto, Y nao comecou").
- Duplicar o conteudo de paginas em vez de apontar o path.
- Gerar handoff quando nada aconteceu ainda na sessao.
- Salvar o handoff dentro do vault (`wiki/`, root do repo) — vaza estado pessoal para o git tree.
- Criar pagina, entrada de log ou rodar o indice: handoff nao e conhecimento duravel.
- Confundir com `memory`: memoria e aprendizado duravel; handoff e estado descartavel de uma tarefa.
- Copiar trechos sensiveis desnecessarios em vez de referenciar o path.

## Done when

- O bloco copiavel foi exibido, autocontido, terminando com o prompt para o proximo agente.
- Estado, decisoes, armadilhas e ponteiros estao presentes (ou declarados ausentes).
- O arquivo de backup foi gravado fora do vault e seu path absoluto consta no bloco.
- Nada foi escrito em `wiki/`, `raw/`, `wiki/log.md` nem no indice.
