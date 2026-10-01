# Release e rollback

## Versões e autorização

A documentação tem versão `1.0.0`. O primeiro runtime terá `VERSION=7.23.0-rc.1` e tag anotada `v7.23.0-rc.1`, depois dos gates técnicos e do ensaio de rollback. O usuário autorizou implementação e testes em laboratório, além de versão/tag. A instalação no vault real está proibida nesta iniciativa. Push não é consequência automática da criação da tag: manter local até autorização de publicação.

A baseline é o commit apontado pela tag `v7.22.1`, conferido antes do teste. Registrar o SHA real; nunca mover uma tag publicada para ajustar resultado. Uma correção posterior cria `rc.2`. `7.23.0` só será candidata à estabilidade após avaliação comportamental e de uso, sem converter ausência de dados em aceite.

## Preparação

Criar diretório privado de laboratório fora do vault real e do payload. O manifesto local contém raízes baseline/candidato, estados, configurações descartáveis, fonte/SHAs, lista de raízes protegidas e modo de prevenção de escrita. Nenhum path pessoal entra na spec pública.

Antes de executar testes, comprovar a prevenção usando um diretório sentinela descartável equivalente. Não tentar escrever um arquivo de teste no vault protegido. Em macOS, um perfil `sandbox-exec` pode negar escrita nas raízes protegidas enquanto permite o laboratório; isso deve ser demonstrado no processo real usado para testes. Se a plataforma não oferecer essa proteção, restringir a execução a processos determinísticos sem ferramentas externas e declarar a limitação; não alegar sandbox universal.

Fixtures e resultados mantêm espaços separados. A rubrica fica fora do contexto de candidatos. Não importar histórico real, login ou configurações privadas para a fixture. O pipeline live tem seu próprio gate de autenticação e ferramentas.

## Gates antes da tag candidata

1. Spec e contratos reconciliados com implementação, sem requisitos obrigatórios silenciosamente omitidos.
2. Testes de tarefas, superfície e laboratório; suíte existente `bash tests/run.sh` e testes Python relevantes verdes.
3. Instalação nova e update de target sintético; verificação de versão e manifest.
4. Integridade de conteúdo e configuração sintéticos preservada após update.
5. Rollback candidato para baseline e retomada por handoff portátil exercitados.
6. Inspeção visual e navegação real; estados vazio, indisponível e fonte alterada verificados.
7. Diff sem dados privados, segredos, saídas de modelos ou artefatos de laboratório.
8. Changelog distingue o que funciona, o que foi testado e o que ainda não demonstrou valor.

## Ensaio de rollback

1. Na baseline sintética, criar conteúdo e configuração local e registrar hashes.
2. Atualizar o mesmo target sintético para candidato, mantendo o estado de delegação baseline separado do novo estado de tarefas.
3. Criar tarefa, checkpoint e correção; exportar handoff portátil fora do target.
4. Encerrar somente os processos iniciados pelo laboratório, por referências mantidas pelo runner. Não sinalizar PIDs recuperados de arquivo.
5. Reinstalar a baseline no target sintético, pelo installer daquela tag. Conferir versão, manifest e funcionamento dos comandos antigos. Se o installer não remover arquivos novos, registrar e aplicar uma rotina de remoção somente dos arquivos extras gerenciados, validada contra os dois manifestos.
6. Conferir hashes do conteúdo/configuração que deveriam ser preservados; campos de settings gerenciados pelo installer podem diferir de forma documentada, sem perda das entradas locais.
7. Ler o handoff exportado usando a baseline e demonstrar que objetivo, correção e pendência continuam disponíveis.
8. Preservar o namespace de tarefas para auditoria; baseline deve ignorá-lo. Não apagar ou converter destrutivamente estado experimental.

Uma reversão que apenas altera `VERSION` não passa. Recuperar código sem recuperar a continuidade também não passa.

## Interrupção e promoção

Falha de isolamento, perda de correção, corrupção ou duplicação de efeito interrompe o candidato. Não consertar automaticamente o vault real. Recuperar o laboratório pela baseline e registrar a falha no relatório.

Promoção técnica significa que o candidato pode participar de um piloto. Promoção funcional exige critérios de [VALIDATION.md](VALIDATION.md). Publicação remota e instalação real são ações distintas. A última continua bloqueada pelo escopo atual, mesmo com autorização de push futura.
