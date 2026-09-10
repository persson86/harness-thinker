# Knowledge mini v1

Oito casos sinteticos curtos para screening de revisao de conhecimento, incluindo dois controles corretos. Reusa `thinker-model-eval`, sem servico, nova skill, toggle permanente ou chamadas automaticas.

1. Siga `harness/operations/model-eval.md`: declare modelos/effort, limites, concorrencia, timeout, retries e parada.
2. Copie `case.md`, `spec.json` e `rubric.md` para `drafts/model-eval/ID/` e registre hashes antes das respostas.
3. Envie SOMENTE `case.md` aos candidatos; spec e rubric ficam com o avaliador. Nao passe a pasta inteira nem reutilize agente que leu o gabarito.
4. Rode cada perfil no mesmo caso sem ferramentas de escrita; registre diferencas entre host nativo e CLI externa. Cada perfil recebe apenas uma chamada no screening; nenhuma repeticao ou substituicao silenciosa.
5. Valide cada resposta com o validador existente:

```bash
python3 harness/scripts/model_eval_validate.py --spec drafts/model-eval/ID/spec.json --response drafts/model-eval/ID/response.json
```

6. Confira `action_matches/action_total`, nao apenas exit code. Depois aplique a rubrica semantica caso a caso. Registre outcome, trajetoria, eficiencia e feedback humano separadamente em `drafts/model-eval/ID/report.md`.
7. Confira jobs terminais/inbox. Preserve estado privado; nenhum resultado ou contexto real vai ao repositorio-fonte automaticamente. Nao mudar defaults a partir deste screening.

Ausencia de modelo efetivamente reportado, tokens ou tempo de execucao nativa verificavel deve aparecer como indisponivel. Duracao entre spawn e retorno e intervalo observado pelo principal, nao tempo de inferencia comparavel ao supervisor externo. Falha de transporte nao e nota semantica zero; fixture ambigua interrompe a comparacao.
