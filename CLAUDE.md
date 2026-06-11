# CLAUDE.md — repo-fonte do harness-thinker

Este é o **repo-fonte** do harness. **Não é um vault** — não há `wiki/`, `raw/` nem memória aqui. As constituições de vault (`payload/CLAUDE.md`, `payload/AGENTS.md`) são **payload instalável**, não governam sessões neste diretório.

## Regras

- **`payload/` e `templates/` são o que se edita.** Toda mudança de comportamento do harness é uma edição em `payload/`; o scaffold de vault novo vive em `templates/vault/`. `install.sh`, `VERSION` e `docs/` são a maquinaria do repo-fonte.
- **Nunca editar a cópia instalada num vault.** Edite aqui e rode `./install.sh <vault> --update`. O fluxo inverso é drift — o `verify.sh` no vault o detecta via `harness/.manifest`.
- **Categorias são config do vault**, não do harness: vivem em `vault.config.json` no repo de dados. O `build-index.py` as lê de lá; nunca hardcode categorias no script.
- **Sem dado pessoal no payload.** Este repo é público/genérico: nada de nomes próprios, paths absolutos de máquina, clientes ou referências a páginas específicas de um vault. Identidade do usuário é lida em runtime da memória; categorias, do config.
- **Bump de `VERSION`** a cada mudança de payload que valha rastrear; o installer grava essa versão em `harness/.version` no target.
- **Testar antes de publicar:**
  - `./install.sh --init "$(mktemp -d)/v"` → conferir scaffold + índice gerado + `verify.sh` verde.
  - `./install.sh "$(mktemp -d)"` (adotar) num dir com `wiki/` → conferir derivação de config.
  - Hooks rodam standalone com JSON sintético no stdin (`echo '{...}' | payload/.claude/hooks/protect-raw.sh`, com `CLAUDE_PROJECT_DIR` apontando para um vault de teste).

## Camadas fora do payload

Camadas opcionais de revisão deliberativa (ex.: peer-review cruzado entre modelos) dependem de agents e plugins user-level (`~/.claude/agents/`, plugins Codex) e **não** são embarcadas pelo harness — ficam no setup do usuário, fora deste repo.
