# .claude/memory/ — snapshot da memória

A memória **viva** do agente fica fora deste repo, em `~/.claude/projects/<este-vault>/memory/` (path derivado pelo Claude Code do caminho do vault). Esta pasta é um **snapshot point-in-time** versionado para backup — não é lida pelo agente e diverge assim que a memória viva muda.

Re-sincronizar manualmente quando quiser atualizar o backup:

```bash
cp -R ~/.claude/projects/<este-vault>/memory/* .claude/memory/
```
