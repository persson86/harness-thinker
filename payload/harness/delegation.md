# Delegação — uso e limites

A interface principal é a conversa descrita em [operations/delegate.md](operations/delegate.md). Este manual reúne os comandos de apoio. A extensão é distribuída com o harness, mas começa OFF e usa apenas Python 3 e as CLIs já instaladas.

## Começar

```bash
python3 harness/scripts/delegate.py status
python3 harness/scripts/delegate.py doctor
python3 harness/scripts/delegate.py --session MINHA-SESSAO on
```

Use um ID exclusivo por conversa. `on --mode auto` permite ao principal decidir quando delegar dentro do pedido; não amplia escopo ou autorizações. `on --model sonnet` fixa preferência desta sessão. `--model` em `submit` sempre vence essa preferência. `set-default --task git --model luna --reason "Pedido explícito do usuário"` altera o padrão persistente apenas quando solicitado.

Os perfis iniciais são Luna low para Git e contexto delimitado; Sol High para transcrições e revisão; Sonnet High para drafts. Esses defaults só escolhem o modelo depois que o principal decide delegar; não obrigam delegação por tipo de tarefa. Terra, Astra, Fable, Opus e Grok também têm perfis. Fable usa o alias de assinatura `fable`; o acesso e o ID efetivamente servido dependem da CLI/conta e não são presumidos pelo nome. IDs específicos podem ser informados junto de `--provider`.

`doctor` verifica flags, versão e login por assinatura quando a CLI expõe esse diagnóstico, sem chamada de geração. `doctor --all-profiles` repete a verificação para cada perfil e mantém `model_access: not_tested`; acesso ao modelo e retorno precisam de teste real. As ferramentas do colaborador são removidas/restritas; ele devolve texto/Markdown/HTML como proposta para o principal. Implementação arbitrária com ferramentas de escrita não está habilitada nestes adaptadores.

## Arquivos e estado

O estado operacional fica, por vault, em uma pasta privada sob `~/.local/state/harness-thinker/` (ou base XDG suportada pelo runtime). Não entra na wiki, no índice ou no Git do vault. `--state-dir` permite um laboratório em diretório privado separado; não aponte para raw ou uma pasta compartilhada.

Os jobs contêm o brief e snapshots selecionados para permitir retomada. Logs brutos das CLIs são descartados após normalização. Relatórios não incluem essas cópias nem raciocínio interno. Não há coleta de sessões antigas, sincronização de memórias entre provedores ou upload de histórico pelo Thinker. Cada CLI ainda tem o comportamento de conta e retenção de seu provedor.

Contexto aceito: Markdown/texto UTF-8 dentro do vault, com limites de arquivos e tamanho; sem traversal, symlinks e caminhos de configuração/credenciais. Arquivos de contexto são copiados e identificados por hash. O colaborador não edita o MD vivo. `accept` cria exclusivamente `drafts/delegation/JOB.md`; se a entrada mudou, a proposta recebe aviso de versão antiga. Nunca há sobrescrita automática do original.

Não apagar estados automaticamente: isso perderia entregas e histórico. Limpeza/retention e eventual publicação dos aprendizados precisam de escopo próprio. O install/update preserva os estados externos e preferências; código do runtime é gerado pela instalação.

## Comandos de uso

```bash
# Brief preparado pelo principal e contexto mínimo selecionado
python3 harness/scripts/delegate.py --session S --json submit --task draft --model opus --brief drafts/brief.md --file drafts/proposta.md --reason "Revisar a clareza da tese" --timeout 300
python3 harness/scripts/delegate.py --session S inbox
python3 harness/scripts/delegate.py --session S wait JOB --seconds 20
python3 harness/scripts/delegate.py --session S result JOB
python3 harness/scripts/delegate.py --session S accept JOB
python3 harness/scripts/delegate.py --session S ack JOB
python3 harness/scripts/delegate.py --session S feedback JOB --value useful --note "Perguntas aproveitadas após revisão"
python3 harness/scripts/delegate.py --session S record --task context --reason "Contexto já disponível; resolvido no principal"
python3 harness/scripts/delegate.py --session S run start --kind chain --objective "Comparar uma tese" --principal-provider codex --principal-model gpt-6-astra --principal-effort high
python3 harness/scripts/delegate.py --session S run quota RUN --when before --metric quota_remaining --value 75 --unit percent
python3 harness/scripts/delegate.py --session S --json submit --task draft --model sol --brief drafts/brief.md --reason "Primeira formulação" --run RUN --stage 1 --role author --handoff full
python3 harness/scripts/delegate.py --session S --json submit --task review --model sonnet --brief drafts/handoff.md --reason "Crítica por deltas" --run RUN --stage 2 --role reviewer --handoff delta --parent-job JOB-1
python3 harness/scripts/delegate.py --session S run show RUN
python3 harness/scripts/delegate.py --session S run finish RUN --final-job JOB-FINAL
python3 harness/scripts/delegate.py --session S run feedback RUN --value accepted --note "Resultado aproveitado após revisão"
python3 harness/scripts/delegate.py --session S history --export
python3 harness/scripts/delegate.py --session S cancel JOB
python3 harness/scripts/delegate.py --session S off
python3 harness/scripts/delegate.py off --all
```

IDs de jobs podem ser abreviados se forem únicos. `--json` é opção global e vem antes do comando. O resultado normal mostra estado curto e caminhos de leitura. Uma entrada na inbox só é reconhecida com `ack`; consultar status não consome a entrega.

`off` desliga a sessão atual; `off --all` revoga todas as sessões e solicita cancelamento dos trabalhos da extensão. Uma nova ativação posterior habilita apenas a conversa escolhida. O histórico mostra até 30 registros recentes, com motivos, execução, esforço, duração observada e feedback separado; os registros anteriores permanecem no estado privado. Runs agrupam cadeias sem reconstruir relações antigas e sem somar tokens entre provedores. O principal é somente declarado; sua identidade não é confirmada e seu consumo aparece como indisponível. Snapshots manuais de quota são observações da conta, não consumo atribuído automaticamente à conversa.

## Runs e handoffs compactos

`run start` cria somente o envelope de auditoria; não inicia modelos. Uma cadeia é linear e cada `submit` recebe `--run`, `--stage`, `--role` e `--handoff`. A primeira etapa usa `full` e não tem parent. Etapas seguintes apontam para um job concluído e válido da etapa anterior e usam `delta` ou `synthesis`. O papel é um rótulo semântico: uma cadeia pode começar revisando um draft humano. A ordem é garantida por etapa, parent e handoff. Esses modos registram o contrato do handoff; o principal continua responsável por preparar e revisar o conteúdo compacto. Não existe truncamento ou resumo automático.

`run finish` escolhe uma vez o job final e materializa somente essa contribuição em `drafts/delegation/`. Intermediários continuam recuperáveis no estado privado e só são materializados por `accept` explícito. `principal-eval` também pode terminar com `--final-artifact` para registrar o caminho e hash de um MD existente dentro de `drafts/`, sem afirmar telemetria inexistente.

Jobs antigos continuam avulsos. Retry preserva run, etapa, papel, parent e modo de handoff. Desligar a feature impede novas mutações, preserva runs existentes e cancela os jobs conforme o lifecycle já documentado.

## Auth e controles por provedor

Somente login de assinatura já existente, conferido antes da submissão. Falta de login ou acesso ao Keychain recusa a chamada. Não existe opção de informar chave de API. O ambiente dos colaboradores não herda chaves de API, segredos GitHub ou configuração de execução de shell. Codex exige login ChatGPT, ignora config/rules do usuário e usa sandbox read-only com ferramentas de shell, apps, hooks, plugins e subagentes desabilitados. Claude usa safe-mode/restricted, nenhum tool e nenhum MCP. Nenhum adaptador usa bypass de permissões.

Grok usa read-only, nenhum tool, sem subagentes ou busca web. A integração preserva sua pasta de autenticação e desabilita plugins apenas na configuração privada do trabalho. Verifica OIDC, bloqueio de API keys, estabilidade das configurações e ausência de hooks/MCP/LSP externos aos plugins desabilitados. Configuração de endpoint ou autenticação alternativa é recusada.

O build Grok `1.0.13 (5e9a58528b76) [stable]` tem uma limitação: `inspect` lista plugins descobertos como se estivessem ativos. Para esse build, a integração qualifica o desligamento pelo comportamento do [registro de plugins na fonte oficial](https://github.com/xai-org/grok-build/blob/72a61251fcffb464bcc687aeb5a998e5a98ec0c9/crates/codegen/xai-grok-agent/src/plugins/registry.rs#L158-L176), confere que o arquivo de configuração privado foi carregado e repete as checagens antes da chamada. O registro de qualificação deixa essa limitação explícita; não afirma que `inspect` atestou o estado ativo. Outro build exige nova qualificação. Python 3.9 usa o parser TOML incluído com licença MIT; não exige instalação adicional.

Se a assinatura atingir um limite ou o login falhar, a tarefa falha com diagnóstico; não há troca para API ou chave alternativa. As CLIs podem informar estimativas de uso: esses valores não são fatura nem comprovam cobrança avulsa.

## Git: plano revisável e execução serial

O helper funciona apenas em vaults Thinker instalados. O projeto-fonte harness-thinker tem seu próprio processo de release. No vault real, siga também o runbook de publicação disponível na sessão.

1. O principal confere pedido, repo, branch, destino, diff, autoria e arquivos. Relaciona todos os commits anteriores que alcançariam o remoto.
2. Se delegar a contribuição Git, usa `submit --task git` (Luna low por default; `--model sonnet` vence). O brief contém o diff/escopo necessário e pede revisão/mensagem, sem autorização de escrita ao colaborador.
3. O principal revisa o retorno, define mensagem e prepara o plano determinístico. `--job` vincula o modelo efetivamente executado ao plano. Sem job, o plano declara apenas a execução determinística; não inventa uso de Luna.
4. Depois de revisar o plano e confirmar que a autorização vigente cobre a operação, executa seu ID. Não pedir confirmação de novo se o usuário já autorizou esse conteúdo e ação.

```bash
# Exemplo de commit local: não faz fetch ou push
python3 harness/scripts/delegate.py --session S --json git prepare --action commit --authority-reference "Pedido de commit da conversa S" --authorize-commit --expected-branch main --expected-remote URL-ESPERADA --file wiki/categoria/pagina.md --file wiki/log.md --message "docs: registra decisão" --job JOB
python3 harness/scripts/delegate.py --session S --json git execute PLAN-ID
```

Para commit e push, usar `--action commit-push --authorize-commit --authorize-push`, somente com essa autorização. Push de commits existentes usa `--action push --authorize-push`. Informar cada SHA anterior autorizado com `--existing-commit SHA`; um push não pode incluir commits fora do escopo por acidente.

O plano captura HEAD, índice, conteúdo dos caminhos e remoto. Antes de mutar, revalida esse estado e executa checagens fixas de índice, vault, whitespace e raw. Staging é explícito. O índice compartilhado tem um único executor por vez; alterações externas invalidam o plano. Divergência, validação falha, symlink, raw, configurações protegidas, arquivo inesperado e conflito são recusados. Publicação confirma SHA local/remoto. Perda da resposta de rede exige reconciliação; não repetir cegamente.

Desligar impede próximas etapas controladas pela extensão. Uma operação Git já enviada pode ter concluído: informe o estado comprovado, sem fingir rollback. O plano persiste o commit criado antes do push, permitindo retomar sem duplicá-lo.

## O que a validação demonstra

Os testes determinísticos cobrem lifecycle, escopo, concorrência, cancelamento, flags, retorno incompleto, arquivos antigos, overrides e Git com remotos locais descartáveis. Testes de CLI real qualificam aquela combinação de versão, conta e modelo naquele momento. Nenhum desses testes certifica a verdade de uma síntese ou garante ausência de bugs. A revisão de conteúdo e a avaliação do esforço humano continuam no piloto.

No repo-fonte, `bash tests/run.sh` executa a suíte isolada, sem chamadas pagas. O teste real é separado e exige `--run` explícito:

```bash
python3 -B tests/live_delegation.py --run --model luna --model sonnet
python3 -B tests/live_delegation.py --run --model opus --scenario html
```

Ele usa um vault temporário com dados sintéticos, preserva o original, verifica retorno e materialização do draft e desliga a extensão no laboratório ao terminar. A chamada usa a assinatura existente e pode consumir seus limites. O relatório registra modelo solicitado e informação efetivamente devolvida pela CLI; não inventa um ID de modelo quando o provedor não o informa.
