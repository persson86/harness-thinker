# Operacao: transcript

Use para ingerir transcricao de reuniao real do usuario quando o vault tiver uma esfera adequada para contexto profissional, projetos ou trabalho.

Objetivo duplo: capturar conhecimento de projeto/cliente e destilar padroes de metodo, tom, linguagem, jogadas e pontos cegos do usuario.

## Entrada

- Arquivo em `queue/` ou caminho fornecido.
- Texto de transcricao colado na conversa.

## Passos

1. Ler a transcricao inteira antes de sintetizar.
2. Ler `vault.config.json`; escolher a categoria cujo escopo cobre trabalho/reunioes/projetos. Se nao existir, pedir confirmacao antes de criar qualquer pagina.
3. Identificar o engajamento e mapear para pagina existente; se for novo, criar `entity`.
4. Criar nota `source` em `wiki/[categoria]/sources/[YYYY-MM-DD]-[projeto]-[topico].md`.
5. Incluir secoes:
   - **O que rolou**
   - **Decisoes**
   - **Jogadas de metodo observadas**
   - **Conexoes**
6. Atualizar pagina de projeto com deltas relevantes.
7. Refrescar pagina de perfil profissional se ela existir no vault:
   - reconfirmar padroes existentes;
   - adicionar padrao novo nitido;
   - alimentar tensoes/pontos cegos, nao apenas forcas;
   - se em duvida, anotar para rebuild em vez de forcar deduplicacao.
8. Garantir frontmatter e `summary:`.
9. Rodar `python3 .claude/scripts/build-index.py generate`.
10. Registrar em `wiki/log.md`:

```markdown
## YYYY-MM-DD transcript | titulo da reuniao
- Source criada: [[slug]]
- Projeto atualizado: [[slug]]
- Perfil refrescado: [...]
```

11. Se a reuniao evidenciar que uma pagina do vault alimentou decisao/entregavel real, propor uma linha `applied` com evidencia citada. Registrar apenas com confirmacao do usuario.
12. Se veio de arquivo, mover para `queue/processed/[YYYY-MM-DD]/` e pedir revisao antes de deletar.

## Rebuild Periodico

Quando solicitado ou apos lote suficiente de reunioes, recomputar o perfil a partir de todas as notas `source` da categoria apropriada. A sintese do perfil fica no agente-pai; sumarizacao de blocos pode ser paralelizada se a plataforma permitir.

## Erros Comuns

- Resumir a partir de leitura parcial.
- Fazer so relato factual e perder metodo/pontos cegos.
- Atualizar perfil so com qualidades.
- Deletar bruto sem revisao.
- Criar projeto duplicado.
- Inventar `applied` sem evidencia citavel.
