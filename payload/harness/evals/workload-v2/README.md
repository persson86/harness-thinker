# Workload v2: tarefas completas em fixtures

Esta suíte exige ações reais no workspace descartável preparado pelo host.
Há 12 casos, seis famílias, um development e um holdout público por família.
O host/nativo usa ferramentas; a resposta textual não é aplicada como execução.
`finish` observa o disco, preserva cópias/hashes dos artefatos e executa checks
trusted fora do workspace. Rubricas, referências e testes ficam fora dele.

O workspace é um limite de escopo, não um sandbox de segurança do agente host.
Cada trial tem estado inicial limpo; replay não reseta uma tentativa. Código
candidato nunca roda no host: testes exigem gate explícito e Docker com imagem
já disponível, sem rede, mounts somente leitura e limites de recursos. Docker
ou imagem ausente permanece unavailable, sem fallback, instalação ou pull.

Checks JSON verificam invariantes objetivos, não qualidade por palavras-chave.
Texto presente não prova raciocínio útil nem resultado renderizado. Rubrica
semântica e auditoria observada são camadas independentes; trajetória e
identidade ausentes permanecem unknown. Comunicação produz documento Markdown,
sem qualificar qualidade visual de documentos, apresentações ou HTML.
Pesquisa usa somente fontes locais fictícias congeladas, sem internet.

`calibration.json` aponta referências good, bad e valid-alternative com mapas
de arquivos finais. Servem para calibrar o instrumento e o juiz; não são
resultados de modelos. Estilo/contagem têm gravidade menor por padrão.
Os holdouts públicos foram expostos ao desenho: não são secretos e não servem
como confirmação independente final. Criar novos casos privados, congelados
antes da rodada, para essa confirmação. Repetições não ampliam diversidade.
