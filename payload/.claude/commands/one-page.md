---
description: Monta uma One Page de assunto profissional para compartilhar contexto com colegas — contexto, problema e oportunidade, hipóteses por lente (negócio, produto, design, tecnologia) e próximos passos. Use quando o usuário pedir /one-page, "one page", "one-pager", "material para o time" ou "resumo para compartilhar com os colegas" sobre cliente, projeto, reunião ou tema de trabalho. Mostra primeiro na tela; exporta só quando pedido.
argument-hint: "[assunto, cliente, projeto, source ou caminho de transcrição]"
---

Execute a operação ONE-PAGE para: $ARGUMENTS

Siga o playbook `harness/operations/one-page.md`.

Deltas Claude Code:
- Para delegar a montagem a um subagente, passe o playbook inteiro e o pedido; o principal revisa a página contra o filtro da sala antes de mostrar.
- Exportação, só quando pedida: documento pelo conector de documentos da sessão, se houver (siga as instruções dele); página publicada pela ferramenta de artefatos, carregando antes a skill de design de artefato; ou HTML/MD local em `output/one-page-<slug>/`. Avise que o link nasce privado.
