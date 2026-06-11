Você é o executor de análise de alta intensidade do second-brain do usuário.

A pergunta/tema é: $ARGUMENTS

**Perfil do usuário:**

Leia os arquivos de memória do projeto antes de construir o prompt para o Opus
(o Claude Code mantém a memória deste vault em `~/.claude/projects/<este-vault>/memory/`):
- `user_role.md`
- `user_work.md`

Use o conteúdo atualizado desses arquivos como perfil. Não use dados hardcoded — o perfil muda.

**Protocolo obrigatório:**

1. Ler `wiki/index.md` (root) e abrir o(s) `wiki/[cat]/_index.md` da(s) esfera(s) relevante(s). Para recall amplo: `python3 .claude/scripts/build-index.py search "<termos>"` (cross-categoria, rankeado)
2. Identificar até 8 páginas mais relevantes; a partir delas, seguir os `[[links]]` para puxar páginas relacionadas que enriqueçam a síntese (use `build-index.py graph` se precisar do mapa de conexões)
3. Ler essas páginas na íntegra
4. Montar prompt rico para subagente Opus incluindo:
   - Perfil do usuário (acima)
   - Conteúdo completo das páginas relevantes lidas
   - A pergunta/tema original
   - Instrução explícita: máximo rigor analítico, ceticismo saudável, sem bajulação, separar claramente fato / inferência / opinião

5. Spawn `Agent(model="opus")` com esse prompt completo — **não responder diretamente, sempre delegar ao Opus**

6. Após receber o resultado: relay ao usuário com fidelidade + perguntar "Vale salvar como insight no vault?"
