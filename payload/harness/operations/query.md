# Operacao: query

Use quando o usuario fizer pergunta que deve ser respondida com base no conhecimento acumulado.

## Passos

1. Ler `wiki/index.md`.
2. Abrir shards relevantes `wiki/[categoria]/_index.md`.
3. Para recall amplo, usar `python3 .claude/scripts/build-index.py search "<termos>"`.
4. Ler ate 5 paginas de conteudo mais relevantes, salvo pedido explicito de analise ampla.
5. Selecionar personas — quando o dominio justificar (estrategia, produto, negocio, decisao, investimento, filosofia, posicionamento), consultar `[[vault-personas]]` para identificar quais lentes ativar e ler as paginas entity/source das personas selecionadas. As paginas de persona sao lidas **em adicao** ao teto de ~5 paginas de conteudo do passo 4 (nao competem por esse limite), respeitando o maximo de 4 personas por resposta. Pular este passo em perguntas factuais simples ou execucao tecnica pura.
6. Responder com citacoes reais: "segundo [[slug]]..." ou "de acordo com [[slug]] e [[slug2]]...", aplicando as lentes das personas ativas. Conflitos entre personas sao apresentados sem resolucao — o usuario decide.
7. Formato por numero de personas ativadas:
   - 0 (execucao tecnica): resposta direta, sem estrutura de personas.
   - 1-2: lentes integradas na narrativa, com citacao da fonte.
   - 3+: secao por persona + sintese de convergencias e tensoes.
   - Limite de 4 personas; priorizar cobertura Alta > Media > Stub e relevancia direta a pergunta.
8. Separar claramente fato do vault, inferencia e perspectiva externa.
9. Encerrar perguntando: "Vale salvar esta sintese como um insight em `ideias-pensamentos/`?"

O mapa de personas (dominio -> personas -> profundidade -> formato) e fonte unica em `[[vault-personas]]`. Nao duplicar a tabela aqui.

## Nunca

- Inventar wikilink.
- Fingir cobertura do vault quando nao existe.
- Responder consulta de wiki sem ler o indice.
