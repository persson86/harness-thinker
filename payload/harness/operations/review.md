# Operacao: review

Use quando uma correcao, evidencia nova ou mudanca de decisao puder afetar conhecimento ja registrado. Revisao pode ser disparada durante outra operacao; nao exige um comando explicito do usuario.

## Autoridade

- Pedido de analisar/revisar: localizar e propor, sem escrever.
- Pedido de corrigir/atualizar, ou escopo de escrita ja autorizado: executar as correcoes pertinentes sem pedir a mesma autorizacao outra vez.
- Dependencia encontrada nao amplia o escopo por si so. Alteracoes com novas decisoes semanticas fora do pedido ficam como propostas.
- `raw/` permanece imutavel; preservar os originais de `queue/processed/`, as fontes historicas e o log anterior.

## Procedimento

1. Registrar a mudanca: fala/correcao direta, nova observacao, relato, inferencia ou decisao. Indicar o que ela sustenta e o que nao sustenta. Uma aprovacao de registro nao e confirmacao factual.
2. Localizar o trecho afetado e sua origem. Uma pagina source sintetizada nao substitui a fala original quando a atribuicao estiver em disputa.
3. Rodar `python3 .claude/scripts/build-index.py review <slug>` para levantar referencias diretas em wikilinks e `sources:`. A saida e uma lista de dependencias candidatas; conexao pode ser contexto ou contraditorio, nao necessariamente derivacao. Repetir para paginas intermediarias apenas quando a leitura justificar propagacao transitiva.
4. Ler as candidatas pertinentes e classificar: precisa correcao, precisa sinalizacao historica, permanece valida ou depende de evidencia adicional. Uma comparacao antiga entre A/B nao se torna falsa porque surgiu C.
5. Sob autorizacao de escrita, corrigir corpo e `summary:` conjuntamente. Preservar cronologia e atribuicao. Usar os campos opcionais `knowledge_status`, `as_of`, `superseded_by` quando ajudarem a distinguir estado passado e vigente; validar o destino. Nao converter edicao recente em confirmacao de todo o conteudo.
6. Em correcao de interpretacao do usuario, explicitar qual leitura do agente foi corrigida. Nao inventar fala literal, motivacao ou preferencia permanente.
7. Quando REVIEW for a operacao principal, registrar `review` no log; quando aninhada em INGEST/TRANSCRIPT, descrever as correcoes e dependencias revisadas na entrada da operacao-pai, sem exigir entrada duplicada. Regenerar indice quando aplicavel e executar os gates do contrato. Nunca editar a mao os indices gerados.
8. Relatar o que mudou, o que foi preservado e o que segue incerto. Em analise read-only, devolver os destinos e ajustes propostos.

## Criterio de conclusao

A correcao chegou aos trechos e resumos afetados identificados no escopo; registros historicos continuam recuperaveis; pendencias e limites da busca foram explicitados. Referencias diretas nao garantem que todas as dependencias implicitas tenham sido encontradas.
