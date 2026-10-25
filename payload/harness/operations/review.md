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
3. Levantar candidatas por dois bracos, sempre os dois:
   - **Referencia e literal:** `python3 .claude/scripts/build-index.py review <slug> --literal "<trecho>"` na pagina vigente e, quando houver, na fonte substituida. Passe como `--literal` (repetivel) os trechos distintivos da afirmacao anterior: datas, numeros, versoes, nomes, identificadores. A saida une wikilinks, `sources:` e paginas que repetem o trecho sem linkar, com a linha.
   - **Parafrase:** `python3 .claude/scripts/build-index.py search` com o fato reescrito em 2 a 6 termos e variantes. Literal nao acha parafrase, e BM25 nao garante acha-la.
   A saida e uma lista de candidatas; conexao pode ser contexto ou contraditorio, nao necessariamente derivacao. Repetir para paginas intermediarias apenas quando a leitura justificar propagacao transitiva. Registrar os trechos e termos usados para o relato do passo 8.
4. Ler as candidatas pertinentes e classificar: precisa correcao, precisa sinalizacao historica, permanece valida ou depende de evidencia adicional. Uma comparacao antiga entre A/B nao se torna falsa porque surgiu C. Mencionar o mesmo assunto nao e repetir a afirmacao: na duvida, ler antes de classificar. Numa pagina viva que apenas repete o fato, prefira trocar a afirmacao por referencia a pagina vigente a reescrever o fato em mais um lugar. Sem pagina vigente identificavel, parar e relatar; nao escolher sucessor por inferencia.
5. Sob autorizacao de escrita, corrigir corpo e `summary:` conjuntamente. Preservar cronologia e atribuicao. Usar os campos opcionais `knowledge_status`, `as_of`, `superseded_by` quando ajudarem a distinguir estado passado e vigente; validar o destino. Nao converter edicao recente em confirmacao de todo o conteudo.
6. Em correcao de interpretacao do usuario, explicitar qual leitura do agente foi corrigida. Nao inventar fala literal, motivacao ou preferencia permanente.
7. Quando REVIEW for a operacao principal, registrar `review` no log; quando aninhada em INGEST/TRANSCRIPT, descrever as correcoes e dependencias revisadas na entrada da operacao-pai, sem exigir entrada duplicada. Regenerar indice quando aplicavel e executar os gates do contrato. Nunca editar a mao os indices gerados.
8. Relatar o que mudou, o que foi preservado e o que segue incerto. Em analise read-only, devolver os destinos e ajustes propostos.

## Criterio de conclusao

A correcao chegou aos trechos e resumos afetados identificados no escopo; registros historicos continuam recuperaveis; pendencias, trechos e termos buscados e limites da busca foram explicitados. Referencias diretas, literais e busca nao garantem que todas as dependencias implicitas tenham sido encontradas.
