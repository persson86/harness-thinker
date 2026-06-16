# Bridge Thinker ↔ Builder (pessoal)

Convenção pessoal que liga este vault ao workspace de desenvolvimento (harness-builder).
**Fora do payload** — o payload publicado é genérico e não menciona Builder. Versionada
aqui, fora do README. A ativação no vault é manual (ver abaixo): o payload instalado não
carrega esta convenção.

## Direção secundária (silenciosa): Thinker → Builder

Em QUERY e DREAM, quando a síntese/digest for diretamente acionável em um projeto ativo
em Builder, indicar ao final: "Potencial para Builder: [projeto] — [uma frase]." Só
quando o link for concreto; omitir quando for abstrato.

- QUERY: após "Vale salvar esta síntese como um insight?"
- DREAM: junto ao contrato (o DREAM só propõe; este flag também é só sugestão).

## Direção primária: Builder → Thinker

Definida do lado do Builder — ver `harness-builder/personal/bridge.md`.

## Ativação no vault

O payload instalado não carrega esta convenção. Para ativá-la no vault
(`~/Thinker/second-brain`), numa sessão Thinker registrar via `/memory` uma nota de
comportamento equivalente ao bloco "Direção secundária" acima. O installer nunca
sobrescreve `.claude/memory/` nem `vault.config.json`, então a ativação sobrevive a
`install.sh --update`.
