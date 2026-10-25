# Operação RELEASE

Publicar uma nova versão de um projeto versionado — harness, aplicativo, biblioteca, ferramenta ou site — sempre pela mesma sequência: versão e documentação, testes, commit, tag, push, reinstalação e verificação. O que muda de projeto para projeto fica na receita do próprio repositório; esta operação fixa a ordem, a política de versão e os limites.

## Acionamento e autorização

- **Pedido explícito** ("faz o release", "publica a nova versão", "lança a 3.4.1", `/thinker-release`): autoriza a sequência completa no projeto e no escopo da conversa — commit, tag, push da branch e da tag, reinstalação nos alvos da receita. Mostre o plano e siga sem pedir confirmação a cada passo. Pare e pergunte só quando a pré-checagem encontrar algo fora do escopo ou quando um passo falhar.
- **Menção implícita** (a conversa conclui uma mudança que pede versão nova, ou o usuário fala de versão ou release de passagem): apresente o plano com o que está pendente e pare. Nada de commit, tag ou push sem pedido explícito.
- **Push pedido num projeto com receita:** se os commits a enviar mudam o que é entregue e a versão não foi incrementada, apresente o plano de release antes do push. Push sem versão deixa instalações divergindo do que foi publicado.
- Commit isolado continua sendo só commit. Publicar conhecimento do vault segue o helper e o runbook do vault; não é release.

## Política de versão

- Cada release incrementa o **último número**: `X.Y.Z` → `X.Y.(Z+1)`. Uma skill nova, uma correção ou um ajuste de regra entram assim. Minor (`X.(Y+1).0`) e major (`(X+1).0.0`) só a pedido explícito do usuário.
- Sem versões de pré-lançamento (`-rc`, `-beta`, `-alpha`). Se a versão atual carrega um sufixo legado, a release seguinte é a mesma versão sem sufixo (`7.23.0-rc.14` → `7.23.0`).
- A versão nova é sempre maior que todas as já publicadas. Não reaproveite número antigo nem volte a numeração.
- Uma versão corresponde a um commit e a uma tag anotada `v<versão>`. Tag publicada não se move nem se apaga; erro descoberto depois do push vira nova versão.
- O número muda no mesmo commit em todos os lugares que o carregam (arquivo de versão, manifesto de pacote, metadados do app), conforme a receita.

## Receita do projeto

Cada repositório declara em `RELEASE.md`, na raiz:

- arquivo de versão e demais lugares que carregam o número;
- comando de teste;
- documentação a atualizar (changelog, README) e formato das mensagens de commit e de tag;
- remoto e branch de publicação;
- como reinstalar ou implantar, como verificar a instalação e como voltar à versão anterior.

Paths absolutos, nomes de máquina e alvos pessoais ficam em `RELEASE.local.md`, ignorado pelo git, quando o repositório é público ou compartilhado. Sem `RELEASE.md`, derive uma proposta do repositório (arquivo de versão, testes, changelog, installer, scripts de build), mostre ao usuário e use só depois de confirmada; a receita nova entra no commit da release.

## Sequência

Nos comandos, `<remoto>` e `<branch>` são os da receita.

1. **Pré-checagem, sem escrever.** Confirme repositório, remoto e branch, com `HEAD` na ponta da branch de publicação. Rode `git fetch <remoto>`; se o local estiver atrás ou divergente, pare. Liste o working tree e separe o que entra na release do que é alheio; o alheio fica fora do commit e é mencionado. Liste os commits em `<remoto>/<branch>..HEAD`; commit fora do pedido exige pergunta. Confira a versão atual, a maior tag publicada e que a tag nova ainda não existe no local nem no remoto.
2. **Plano.** Versão atual → nova; o que muda (commits e arquivos); testes; documentação; alvos de reinstalação; como voltar atrás. Curto, para leitura em segundos.
3. **Versão e documentação.** Incremente o número. Acrescente a entrada do changelog com data, o que mudou e o que não foi validado. Atualize o README quando mudarem instalação, uso, comandos ou comportamento visível; se o projeto mantém uma seção por versão no README, siga o padrão dele.
4. **Testes** da receita sobre a árvore final, já com versão e documentação. Falha interrompe a release; não ajuste teste para passar.
5. **Commit** só dos caminhos revisados, com pathspec explícito e a mensagem no formato do projeto, citando a versão. Confira `git show --stat HEAD`.
6. **Tag** anotada no commit da release: `git tag -a vX.Y.Z -m "vX.Y.Z — <resumo>"`. Antes do push, `git rev-parse HEAD`, `git rev-parse <branch>` e `git rev-parse vX.Y.Z^{}` precisam ser o mesmo SHA.
7. **Push** da branch e depois da tag, por refs completas e sem levar outras tags: `git -c push.followTags=false push <remoto> refs/heads/<branch>:refs/heads/<branch>` e `git push <remoto> refs/tags/vX.Y.Z`. Nunca `--tags` nem force push. Push recusado interrompe a release; não faça rebase nem force para passar.
8. **Reinstalação** em cada alvo da receita, a partir de uma árvore idêntica à tag. Se o clone tiver qualquer alteração pendente, instale de um worktree limpo (`git worktree add <tmp> vX.Y.Z`, depois `git worktree remove <tmp>`); installers costumam ler o working tree, não o commit. Outros clones do mesmo repositório declarados na receita recebem fast-forward quando limpos; sujos ou divergentes, avise.
9. **Verificação.** Versão instalada em cada alvo e checagem da receita (verify, manifesto, app abre, serviço responde). No remoto, `git ls-remote <remoto> refs/heads/<branch> 'refs/tags/vX.Y.Z^{}'` aponta para o commit da release nas duas refs.
10. **Relato.** Versão, SHA, tag, push, alvos reinstalados com resultado e o que ficou sem verificação.

## Falhas e volta

- **Antes do push**, tudo é local: corrija, refaça o commit ou recrie a tag local e repita os testes.
- **Depois do push**, não reescreva histórico nem mova a tag. Corrija numa nova versão.
- **Reinstalação ou verificação falhou:** reporte o estado exato de cada alvo. Alvo quebrado volta à versão anterior pelo procedimento da receita (em geral, instalar a partir de um worktree da tag anterior); a versão publicada continua publicada.

## Limites

- Registro público de pacotes, deploy de produção, GitHub Release e anúncios só entram quando a receita os declara.
- Release é gatilho de irreversibilidade: com mudança material, peça a revisão crítica antes do push conforme o escalonamento de `delegate.md` e `consult.md`, respeitando autonomia, orçamento e admissão. Uma revisão por entrega.
- Testes, versão e documentação não provam a qualidade em uso; o relato diz o que foi observado depois da instalação.
- Não gera página, entrada em `wiki/log.md` nem índice.
