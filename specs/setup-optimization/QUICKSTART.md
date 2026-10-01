# Operar a candidata no laboratório

Use somente conteúdo sintético e caminhos de laboratório. Não instalar no vault real. Os exemplos partem do repositório-fonte e não ativam modelos.

## Preparar

Escolha uma raiz nova, canônica e externa ao workspace protegido. `prepare` exige macOS com execução protegida funcional e verifica tanto escrita permitida no laboratório quanto escrita negada em sentinela descartável. Uma falha desse controle impede o preparo protegido.

```sh
python3 scripts/setup-lab.py --root /absolute/laboratory prepare \
  --protected-root /absolute/protected-workspace
```

O resultado inclui targets `baseline` e `candidate`, separados do workspace protegido. O runner não é um sandbox universal: o modo autenticado usa login existente e o chamador precisa configurar os provedores sem ferramentas. Não executar modelos se essa fronteira não estiver comprovada.

## Criar e retomar

Defina `TASK_WORKSPACE` como o target sintético `candidate` e `TASK_STATE` como um diretório privado irmão, fora do target. Execute a CLI instalada:

```sh
python3 "$TASK_WORKSPACE/harness/scripts/task.py" \
  --workspace "$TASK_WORKSPACE" --state-dir "$TASK_STATE" \
  create --title "Revisar proposta sintética" --objective "Identificar decisão vigente e próximo passo"
```

Guarde o `task_id` e a revisão retornada. Crie um arquivo JSON de checkpoint fora do target; exemplos de schema estão em `tests/fixtures/tasks/`. Use apenas referências que existam no target sintético. Em seguida:

```sh
python3 "$TASK_WORKSPACE/harness/scripts/task.py" \
  --workspace "$TASK_WORKSPACE" --state-dir "$TASK_STATE" \
  checkpoint "$TASK_ID" --expected-revision 1 --request-id checkpoint-1 --file "$CHECKPOINT_FILE"

python3 "$TASK_WORKSPACE/harness/scripts/task.py" \
  --workspace "$TASK_WORKSPACE" --state-dir "$TASK_STATE" \
  resume "$TASK_ID" --budget-bytes 32768
```

Correções usam novo ID e `supersedes`; uma declaração antiga não é substituída por recência. Atualizações exigem a revisão corrente. Reapresentar uma evidência é reconciliação explícita com seus bytes atuais. A CLI não avalia a verdade do conteúdo.

## Consultar a superfície

```sh
python3 "$TASK_WORKSPACE/harness/scripts/task.py" \
  --workspace "$TASK_WORKSPACE" --state-dir "$TASK_STATE" snapshot > "$SNAPSHOT_FILE"

python3 "$TASK_WORKSPACE/harness/scripts/task-surface.py" --snapshot "$SNAPSHOT_FILE"
```

`SNAPSHOT_FILE` deve ficar no laboratório, fora do target protegido. Abra o endereço completo emitido, incluindo o fragmento após `#`. Selecione explicitamente uma tarefa. Atualizar a tela relê o arquivo; não recompila as tarefas nem acompanha agentes. Gere novo snapshot após uma alteração. Encerrar o servidor não encerra agentes.

## Medir uso

Use um laboratório por comparação: primeiro fluxo atual versus tarefa/retomada; depois tarefa/retomada versus tarefa/retomada com interface. Não misture as duas comparações no mesmo relatório.

```sh
python3 scripts/setup-pilot.py --lab /absolute/laboratory start \
  --pair continuity-01 --condition baseline --session session-1 --actor human
python3 scripts/setup-pilot.py --lab /absolute/laboratory finish "$ATTEMPT_ID" \
  --quality pass --corrections 0 --useful unknown
python3 scripts/setup-pilot.py --lab /absolute/laboratory report
```

O cronômetro começa antes da preparação e termina após revisão. Pause somente espera sem atenção; registre falhas e abandonos. `human` só se aplica a uma pessoa realmente executando o caso; ensaio do agente usa `simulation`. Utilidade é resposta explícita da pessoa, nunca inferência do agente. O gate de tempo e qualidade exige oito pares, quatro sessões, até 14 dias, ausência de falhas críticas e os limiares do protocolo. Manutenção e preferência humana continuam decisões separadas.

## Verificar e reverter

`python3 -B -m unittest discover -s tests -p 'test_task_release.py'` executa instalação, update, exportação e rollback em target descartável. Para uma reversão manual, siga [RELEASE.md](RELEASE.md): preflight dos arquivos extras contra os manifestos, reinstalação da baseline, remoção somente de extras gerenciados sem mudanças locais e preservação do handoff. Não apagar o namespace de tarefas.
