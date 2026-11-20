# Reviewer

Use um modelo de fronteira de outro harness/provedor para contestar uma decisão, proposta ou entrega. A política comum, a escolha de modelos, os toggles e a admissão ficam em `harness/operations/consult.md`; transporte e quotas, em `delegate.md`. Opus, Sol, Fable, Astra e outros elegíveis são escolhas contextuais, não uma escada universal.

Defina o objeto e os critérios antes de convocar. O Reviewer não recebe o contexto inteiro do orquestrador para que o parecer saia com o mínimo de viés. O brief leva o problema, a solução proposta e as definições que geraram os testes (requisitos, critérios de aceite, casos-limite); nunca o raciocínio do orquestrador nem a resposta, o parecer ou as conclusões de outro modelo, inclusive de um Reviewer anterior. O Reviewer deriva das definições as próprias checagens e as reproduz; os testes existentes fazem parte do que ele revisa, não são prova. Quando o artefato vive num repositório, abra-o para leitura com `submit --repo CAMINHO` em vez de colar o diff inteiro: o Codex lê, roda comandos e escreve reproduções só no workspace descartável, com o shell sem rede e sem escrever no repositório; o Claude lê com Read, Grep e Glob, sem executar; o Grok não suporta. Com `--consult-role reviewer`, Codex e Claude também buscam na web e leem o vault por padrão (`--no-web`, `--no-vault-read` desligam), fora de `ai-memory/`, `drafts/reviewer/` e `drafts/delegation/`, onde ficam o diálogo do orquestrador, pareceres anteriores e propostas aceitas de outros modelos; o prompt também afasta os transcripts das CLIs e o estado da delegação. No Claude essa exclusão é regra de permissão; no Codex, que lê o disco inteiro para rodar comandos, é instrução do prompt. Quando útil, faça uma primeira leitura de problema, requisitos e evidências sem a conclusão do Orquestrador ou o parecer do Advisor. A revisão concreta precisa receber o artefato real: código/diff, documento, dados ou evidências de execução pertinentes. Não esconder o objeto para alegar revisão às cegas. Anexe só o necessário e preserve restrições de circulação.

Peça objeções priorizadas por consequência, evidência localizável, o que foi verificado, o que é inferência e o que não pôde conferir. Cada problema material deve permitir uma checagem ou indicar qual evidência resolveria a dúvida. Ausência de problemas é resposta válida; não fabricar discordância para parecer independente.

Depois da admissão externa, anuncie o papel e use `delegate.py submit` com campos de consulta. O colaborador não escreve nem executa por inferência e não chama novos colaboradores.

## Fallback no mesmo harness

Se o outro provedor estiver indisponível — quota `blocked`, `doctor` falhando, limite de uso ou falha de infraestrutura na tentativa externa desta entrega —, a revisão não é dispensada: um **agente novo do mesmo harness** assume como Reviewer de fallback. Pode ser qualquer modelo do host, inclusive o mesmo do Orquestrador (no Claude Code, Fable ou Opus; no Codex, Astra ou Sol). Modelo explicitamente pedido e indisponível não autoriza troca silenciosa; o fallback é de provedor, não de escolha do usuário.

"Agente novo" significa sem vícios da construção:

- spawn novo, sem herdar a conversa: nunca `fork`, retomada ou mensagem a um agente já existente;
- nunca a instância que atuou como Advisor nem outra que participou da solução;
- brief às cegas conforme `delegate.md`, com o artefato real a revisar e uma **lista de leitura permitida** (caminhos absolutos), em vez de só dizer o que não ler;
- isolamento das instruções do host quando o host permitir: no Claude Code, `subagent_type: thinker-blind-reader` (ver abaixo).

### Isolamento e lista de leitura

Um subagente nativo comum não herda a conversa, mas herda as instruções. No Claude Code:

- **Documentado:** um subagente comum carrega toda a hierarquia de `CLAUDE.md` da sessão; `omitClaudeMd: true` (Claude Code 2.1.271 ou mais novo) tira do **contexto inicial** os `CLAUDE.md` de usuário, projeto e local. Políticas gerenciadas continuam, e o `CLAUDE.md` de uma subpasta e as regras por caminho ainda carregam quando o agente lê arquivos ali. A documentação diz que a auto memory da conversa principal não chega a subagentes.
- **Observado** num teste com marcadores (vault real, Claude Code 2.1.327, 18/nov/2026): um subagente comum mostrou o `CLAUDE.md` do usuário e o índice `MEMORY.md` no contexto inicial, ao contrário do que a documentação diz sobre memória; um subagente com `omitClaudeMd: true` começou sem os dois. Instalado, o `thinker-blind-reader` chamado numa sessão interativa do vault começou sem o `CLAUDE.md` do projeto, sem o do usuário e sem o índice de memória. O snapshot do git status ainda chega. Comportamento de outras versões não foi testado.

O agente `thinker-blind-reader` (`.claude/agents/`, instalado pelo harness) declara `omitClaudeMd: true` e só `Read`, `Grep` e `Glob`. Como ele perde as regras do vault, só serve para leitura, e o brief repete o que importar (escopo, discrição, critérios). Escolha o modelo no spawn (`model`); a definição não fixa nenhum. Isso reduz o viés herdado; não prova isolamento.

"Não leia X" não basta: a wiki é densamente ligada, e uma página permitida pode resumir a conclusão vetada. Antes do spawn, monte a lista de leitura e procure nela o slug e as frases-chave do que deve ficar de fora (`grep -l <slug> <arquivos da lista>`). Arquivo que cita a conclusão sai da lista ou entra com a ressalva declarada no brief, e a entrega informa a contaminação conhecida. A busca só cobre a lista: instruções carregadas por caminho durante a leitura e o que o agente encontrar por conta própria ficam fora dela, então ausência de correspondência não prova isolamento. Peça ao leitor que avise contaminação, e concordância com uma conclusão vazada não conta como confirmação independente.

No Codex não há controle equivalente verificado: um relato público (issue #237 do projeto elephant-goldfish-model, Codex CLI 0.166.0) indica que o `AGENTS.md` do projeto e o do usuário chegam ao subagente mesmo sem herdar a conversa. Use a lista de leitura e declare a limitação.

### Teste de compreensão

Para documentos que precisam se sustentar sem o autor (BRD, one-page, spec, material para colegas), uma leitura opcional e barata antecede a crítica: o leitor cego recebe **só o documento**, colado no brief ou como único item da lista de leitura (vale também para artefato em `drafts/`), sem rubrica e sem fontes, e reconstrói o problema, o público, a decisão pedida e o que falta para agir. O Orquestrador compara a reconstrução com a intenção registrada antes do spawn; a diferença é o achado. Ela não substitui a revisão factual, que precisa das fontes. Ideia adaptada do estágio de compreensão do elephant-goldfish-model.

Admita com `consult admit --consult-role reviewer --fallback "<indisponibilidade observada>"` e siga `start`/`finish` como em qualquer consulta nativa. Anuncie como **Reviewer (fallback, mesmo provedor)** e informe na entrega que a independência é menor: modelos do mesmo provedor tendem a errar de forma correlacionada. Só use fallback quando a indisponibilidade foi observada, nunca para economizar o outro provedor.

O Orquestrador lê a entrega e confere cada objeção no objeto ou na fonte antes de aplicá-la. Concordância entre modelos não comprova funcionamento. Divergência pede evidência, teste ou decisão do usuário conforme sua natureza; não abre rodadas automáticas sem fim. Informe alterações e divergências materiais. A operação não ingere nem publica: drafts solicitados vão para `drafts/reviewer/`, e escrita durável segue sua própria autorização.
