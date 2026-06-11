# Operacao: transcript

Use para ingestao de transcricao de reuniao em `vida-profissional`.

Esta operacao captura conhecimento de projeto e destila padroes do perfil profissional do usuario.

## Entrada

- Arquivo em `queue/transcricoes/` ou caminho fornecido.
- Texto de transcricao colado na conversa.

## Passos

1. Ler a transcricao inteira antes de sintetizar.
2. Identificar o engajamento e mapear para pagina existente em `wiki/vida-profissional/`.
3. Se for novo engajamento, criar pagina `entity`.
4. Criar nota `source` em `wiki/vida-profissional/sources/[YYYY-MM-DD]-[projeto]-[topico].md`.
5. Incluir secoes:
   - **O que rolou**
   - **Decisoes**
   - **Jogadas de metodo observadas**
   - **Conexoes**
6. Atualizar pagina de projeto com deltas relevantes.
7. Refrescar `[[perfil-profissional]]` com toque leve:
   - reconfirmar padroes existentes;
   - adicionar padrao novo nitido;
   - alimentar tensoes/pontos cegos, nao apenas forcas.
8. Garantir frontmatter e `summary:`.
9. Rodar `python3 .claude/scripts/build-index.py generate`.
10. Registrar em `wiki/log.md`:

```markdown
## YYYY-MM-DD transcript | titulo da reuniao
- Source criada: [[slug]]
- Projeto atualizado: [[slug]]
- Perfil refrescado: [...]
```

11. Se veio de arquivo, mover para `queue/processed/[YYYY-MM-DD]/` e pedir revisao antes de deletar.

## Rebuild periodico

Quando solicitado ou apos cerca de 10 reunioes novas, recomputar `perfil-profissional` a partir de todas as notas `source` de `vida-profissional`, preservando tensoes e pontos cegos com o mesmo rigor das forcas.
