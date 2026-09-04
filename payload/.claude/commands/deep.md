Execute a operação DEEP — análise de alta intensidade — para: $ARGUMENTS

Siga o playbook `harness/operations/deep.md`. Deltas Claude Code:

1. **Perfil:** leia a memória viva do projeto (`~/.claude/projects/<este-vault>/memory/`), começando pelo índice `MEMORY.md` e os arquivos de perfil do usuário que ele aponta. Não use dados hardcoded — o perfil muda.
2. **Delegação relativa:** se houver, via Agent, um modelo mais forte que o da sessão, monte o prompt completo (perfil + conteúdo integral das páginas selecionadas + a pergunta + instrução explícita de máximo rigor, ceticismo, separação fato/inferência/opinião, sem bajulação) e delegue. Se o modelo da sessão já for o mais forte disponível, **execute in-process com o mesmo protocolo — não rebaixe a análise delegando**.
3. Integre fielmente o resultado e explicite limites. Proponha registro somente com delta durável e fechamento oportuno; autorização vigente para este resultado e escopo dispensa repeti-la.
