# Workload sintético v1

Esta suíte é **screening de texto sintético delimitado**. Seus 12 casos cobrem
retrieval, ingestion, analysis, research, code e communication, com um caso
development e um holdout por família. Não contém dados de um vault real.

Ela avalia respostas úteis, raciocínio apoiado nas fontes e respeito às
restrições. Não qualifica execução de ferramentas, ingestão real, pesquisa
ao vivo, código em produção, interação com aplicativos ou qualidade visual.
Mesmo uma resposta excelente permanece evidência de desempenho neste recorte.

`suite.json` descreve os casos e limites. `cases/` contém somente o material
visível ao candidato; `rubrics/` contém critérios e notas reservados ao
avaliador. Nunca concatenar rubrica ou notas ao prompt do candidato. Os
critérios orientam avaliação humana ou independente, não pontuação automática
por palavras-chave nem comparação literal com uma resposta modelo.

Os casos development servem para exploração e o piloto. Selecionar holdout
exige decisão explícita; após exposição, ele perde o papel de confirmação
independente. Congelar arquivos e rubricas antes das chamadas. Uma repetição
do mesmo caso não cria um caso independente.

Por família há somente dois casos. Isso fica abaixo do mínimo padrão de três
casos independentes para qualificação; resultados desta suíte são provisórios.
Os limites são até 450 palavras, ou 700 em code; communication usa 180 e 160.
Fontes de research são trechos
fictícios fornecidos e fixos; não exigem nem autorizam navegação externa.
