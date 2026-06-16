# Bridge Thinker ↔ Builder (pessoal)

Convenção pessoal que liga este vault ao workspace de desenvolvimento (harness-builder).
**Fora do payload** — o payload publicado é genérico e não menciona Builder. Versionada
aqui, fora do README.

## Direção primária (ativa): Builder → Thinker, via queue

O Builder escreve insights direto no `queue/` do vault (tem permissão de escrita só
nessa pasta — deny rules no `~/Builder/.claude/settings.json`). Você processa depois
com `/feed` numa sessão Thinker: notas `[ts]-nota-<slug>.md` → INBOX (ou INGEST se
merecerem página). Detalhe do lado do Builder em `harness-builder/personal/bridge.md`.

## Direção secundária (ativa): Thinker → Builder, via specs

Quando uma sessão Thinker (QUERY/DREAM/INGEST…) produzir um insight **concretamente
acionável** num projeto Builder ativo, o agente:

1. **Sinaliza no chat:** "Potencial para Builder: [projeto] — [uma frase]. Registro como
   proposta em `specs/`?" Só quando o link for concreto; omitir quando abstrato.
2. Na confirmação, **escreve** `/Users/persson/Builder/specs/[YYYY-MM-DD]-from-thinker-<slug>.md`.

O vault é read-only fora dele, então a escrita em `Builder/specs/` **cai num prompt de
permissão** — esse prompt é o portão (você aprova). Não há lockdown; só `specs/` é o
destino. Nunca escrever em outro lugar do Builder; nunca auto-implementar — só a proposta.

**Formato da proposta** (espelha os specs existentes, ex. `harness-builder-quality-gates.md`):

```markdown
# Proposta: <título>

**Status:** proposta (origem: Thinker)
**Data:** YYYY-MM-DD
**Projeto Builder:** <projeto ou "workspace">

## Insight
<o aprendizado/decisão do vault, em 1-3 parágrafos>

## Ação sugerida no Builder
<o que fazer com isso — concreto>

## Origem no vault
[[slug-1]], [[slug-2]]
```

Depois, numa sessão Builder, você lê e decide implementar (fluxo spec-driven normal).
O sufixo `from-thinker` torna reconhecível.

## Ativação (numa sessão Thinker)

O payload instalado não carrega esta convenção (é comportamento do agente, não vai pro
repo público). Para ativar, numa sessão Thinker rodar `/memory` salvando a regra da
"Direção secundária" acima. Vive na memória viva (`~/.claude/projects/<vault>/memory/`),
sobrevive a `install.sh --update`.

**Opcional (frictionless):** para escrever em `specs/` sem prompt, adicionar
`Write(/Users/persson/Builder/specs/**)` ao allow de
`~/Thinker/second-brain/.claude/settings.local.json` (o installer nunca toca esse arquivo).
Recomendado deixar o prompt como portão — specs são raros e de maior peso.
