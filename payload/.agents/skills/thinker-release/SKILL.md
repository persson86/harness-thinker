---
name: thinker-release
description: Publicar uma nova versão de qualquer projeto versionado pela sequência testes, versão e documentação, commit, tag, push, reinstalação e verificação. Use quando o usuário pedir release, nova versão, publicar ou lançar uma versão, ou quando a conversa falar de versão nova de passagem. Menção implícita só apresenta o plano; commit, tag e push exigem pedido explícito. Publicação de conhecimento do vault segue o helper do vault.
---

# Release de projeto

Leia `harness/operations/release.md` no root do vault e siga a operação. Use o projeto da conversa e a receita `RELEASE.md` do repositório (e `RELEASE.local.md`, se houver).

A versão sobe no último número (`X.Y.Z` → `X.Y.(Z+1)`), sem pré-lançamento; minor e major só a pedido. Pedido explícito autoriza a sequência completa depois do plano; menção implícita mostra o plano e para. Nunca force push nem tag movida.
