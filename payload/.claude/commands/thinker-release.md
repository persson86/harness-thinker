---
description: Publica uma nova versão de qualquer projeto versionado pela sequência versão e documentação, testes, commit, tag, push, reinstalação e verificação. Use quando o usuário pedir release, nova versão, publicar ou lançar uma versão de um projeto, ou quando a conversa falar de versão nova de passagem; menção implícita só mostra o plano. Commit ou push do próprio vault não é release.
argument-hint: "[projeto ou repositório; versão, se o usuário escolheu]"
---

Execute a operação RELEASE para: $ARGUMENTS

Siga `harness/operations/release.md`. Sem argumento, use o projeto da conversa. Leia a receita `RELEASE.md` do repositório (e `RELEASE.local.md`, se houver). A versão sobe no último número (`X.Y.Z` → `X.Y.(Z+1)`), sem pré-lançamento; minor e major só a pedido. Pedido explícito autoriza a sequência completa depois do plano; menção implícita mostra o plano e para.
