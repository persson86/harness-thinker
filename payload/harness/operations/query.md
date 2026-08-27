# Operacao: query

Use quando o usuario fizer pergunta que deve ser respondida com base no conhecimento acumulado.

Se a pergunta for sobre agenda, calendario, compromisso, reuniao do dia, disponibilidade ou planejamento de horario do usuario, siga `harness/operations/agenda.md` nas duas fontes ao vivo **antes** de consultar o vault. Vault nao substitui Calendar.

## Passos

1. Ler `wiki/index.md` e `vault.config.json`.
2. Abrir shards relevantes `wiki/[categoria]/_index.md`; para recall amplo, usar `python3 .claude/scripts/build-index.py search "<termos>"`.
3. Ler ate 5 paginas de conteudo mais relevantes, salvo pedido explicito de analise ampla.
4. Quando o dominio justificar (estrategia, produto, negocio, decisao, investimento, filosofia, posicionamento), procurar pagina de personas/lentes no vault e selecionar 2-4 lentes com base suficiente. Pular em pergunta factual simples ou execucao tecnica pura.
5. Responder com citacoes reais: "segundo [[slug]]..." ou "de acordo com [[slug]] e [[slug2]]...".
6. Separar fato do vault, inferencia e perspectiva externa.
7. Se nao houver cobertura, declarar ausencia explicitamente em vez de fingir.
8. Encerrar perguntando: "Vale salvar esta sintese como um insight?"

## Personas

Personas sao conteudo do vault, nao payload. Se existirem, leia a pagina de mapa e as fontes/entity pages necessarias. Conflitos entre lentes sao apresentados sem resolucao; o usuario decide.

## Nunca

- Inventar wikilink.
- Responder consulta de wiki sem ler o indice.
- Usar persona sem base suficiente no vault.
- Responder pedido de agenda so com o vault ou so com uma das duas fontes (Gmail pessoal / Calendar do Mac profissional).
