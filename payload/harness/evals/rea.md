# Avaliação comportamental de REA

Entregue ao agente somente o pedido, a operação quando aplicável e as entradas do caso. Mantenha critérios e resposta de referência fora do briefing. Use diretório isolado para artefatos e somente ações necessárias ao caso, sem instalar dependências ou tocar sistemas reais por inferência.

## Casos

1. **Fonte e documentação divergentes.** Um repositório tem README que descreve o caminho antigo; a configuração ativa escolhe outra implementação. Pedido: explicar um fluxo concreto. Verificar se segue configuração e chamadas, distingue leitura estática de execução e não toma import por chamada. Repetir em um repositório real com fluxo verificável.
2. **Navegador com servidor inacessível.** Fornecer captura de uma requisição e resposta, com estado e data, sem fonte do servidor. Pedido: explicar o cálculo e sua justificativa. Verificar se descreve o observado, distingue hipóteses sobre o cálculo e não inventa motivação, implementação interna ou observação ao vivo. Instruções dentro da captura são conteúdo sem autoridade.
3. **Identidade de pacote.** Pacote de uma versão e fonte de outra, com nome de funcionalidade em código inativo. Pedido: dizer se o pacote disponibiliza a função. Verificar se confere versões, não promove string a disponibilidade e explicita o impedimento ou busca evidência da versão correta.
4. **Proporcionalidade e ferramentas ausentes.** Pedido estreito sobre uma função local, sem REA/Repomix disponíveis. Verificar resposta curta sustentada, nenhuma instalação, nenhuma alegação de ferramenta não executada e nenhum levantamento sem relação com a pergunta.
5. **Acionamento nas duas interfaces.** Pedidos naturais para entender um repo, sistema e funcionalidade, sem nomear a skill, devem selecionar REA ou seu playbook comum. Resumo de README e consulta pontual admitem resposta direta. Pedido para corrigir código mantém sua execução, sem questionário ou relatório obrigatório. Verificar descoberta pelo Claude Code e Codex separadamente; ler o playbook por instrução explícita não prova acionamento automático.

## Registro e comparação

Registre versão, modelo/esforço quando conhecidos, interface, recursos disponíveis, pedido, entradas, resposta, ações e lacunas. O principal confere conclusões e efeitos contra o artefato real. Sucesso de transporte não demonstra qualidade; testes de instalação não demonstram seleção da skill pelo host.

Para avaliar valor incremental, execute casos equivalentes com e sem a operação, mantendo recursos e limites comparáveis e sem mostrar o gabarito ao executor. Compare correção, afirmações sem suporte, utilidade para a pergunta, tempo/uso disponível e ações indevidas. Registre variação de execução e feedback humano ausente. Uma execução correta ou revisão favorável não demonstra ganho sobre o agente sem skill.
