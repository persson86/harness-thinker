# Bridge Thinker ↔ Builder (pessoal)

Convenção pessoal que liga este vault ao workspace de desenvolvimento (harness-builder).
**Fora do payload** — o payload publicado é genérico e não menciona Builder. Versionada
aqui, fora do README.

## Direção primária (ativa): Builder → Thinker, via queue

O Builder escreve insights direto no `queue/` do vault (tem permissão de escrita só
nessa pasta — deny rules no `~/Builder/.claude/settings.json`). Você processa depois
com `/feed` numa sessão Thinker: notas `[ts]-nota-<slug>.md` → INBOX (ou INGEST se
merecerem página). Detalhe do lado do Builder em `harness-builder/personal/bridge.md`.

## Direção secundária (parada): Thinker → Builder

Não ativada — decisão de focar numa direção. Se um dia quiser ativar: é um nudge de
comportamento (em QUERY/DREAM, sinalizar "Potencial para Builder: [projeto] — [frase]"
quando a síntese for concretamente acionável num projeto Builder). Por ser comportamento
do agente, o lar é `/memory` numa sessão Thinker — não o queue.
