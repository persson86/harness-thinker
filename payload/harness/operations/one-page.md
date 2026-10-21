# Operação ONE-PAGE

Uma página que um colega do usuário, que não estava na sala, lê em dois minutos e sai sabendo o contexto, o problema, as apostas e o que precisa ser descoberto. Serve para assunto profissional: cliente, projeto, reunião ou tema de trabalho. Não é ata, não é source da wiki e não substitui `transcript`. A análise completa fica na wiki; a One Page carrega só o que move o leitor.

Não escreve em `wiki/`, índice ou log. O rascunho vai para `drafts/one-page/`; exportações, para `output/one-page-<slug>/`.

## 1. Juntar o contexto

- **Argumento:** assunto, cliente, projeto, página, caminho de transcrição ou "isso" (a conversa atual). Sem argumento, use o assunto da conversa; se não houver, pergunte uma vez.
- **No vault:** `python3 .claude/scripts/build-index.py search <termos>` (`context.md` > Localizar páginas). Leia inteiras a página viva do projeto ou cliente e as sources do assunto; página-hub com mais de ~5 mil palavras, só o resumo e as seções do assunto. Sem página viva, as 3 a 6 sources mais recentes. Transcrição bruta ainda não ingerida: leia inteira, sem ingerir. Pare quando a tese estiver sustentada.
- **Recorte:** a página é sobre um **assunto** e reflete o estado de hoje. Se o argumento é uma reunião, o assunto é o que ela abriu; traga o que o vault registra depois dela, ou diga no cabeçalho "até {data}" e nas Notas que não há registro posterior. Reunião com vários temas: o que o argumento indica. Material (deck, proposta): a decisão que ele prepara. Dois temas fortes sem indicação: pergunte qual, em uma linha, com sua recomendação.
- Páginas de perfil, mapas de pessoas e leituras de bastidor calibram tom e "com quem", nunca conteúdo.

## 2. Filtro da sala

Pergunta-guia: **eu leria isto em voz alta numa reunião com todos os citados presentes, cliente incluído?** Se não, sai. Público padrão: o time interno do usuário, então preço, margem e estratégia comercial podem entrar. Se o pedido indicar cliente ou prospect, saem também nomes internos, preço, margem e leitura sobre o próprio cliente.

Fica fora, sempre:
- juízo sobre pessoas e leitura de poder, alinhamento ou motivação ("X conduz", "Y é contraponto", "o cliente é lento");
- o que a source marca como sigilo, confidencial, discrição alta ou "não oficial"; movimento de pessoas não oficial; conflito interno; crítica ao trabalho de um colega;
- **conversa privada como origem.** Em 1:1 e conversa de bastidor, mesmo com três ou quatro pessoas, a pessoa não vira autoridade no corpo ("como a diretora defende") e a conversa não entra em base nem Fontes. Se o conteúdo importa, entra como fato que outro material sustenta ou como pergunta sem dono. Isso inclui não usar a posição de alguém para desempatar uma discussão interna: se a decisão pedida coincide com um debate que só aparece em conversa privada, formule as opções de modo neutro e avise na Nota. Fórum é ritual de time (reunião de contas, daily, comitê) ou reunião com cliente: entra como fórum e data ("reunião com o cliente, 17/set"). Gravação pessoal do usuário não vai para Fontes;
- trecho de transcrição sinalizado e não ouvido como fato; dado pessoal; caminhos e vocabulário do vault ("source", "delta", "ledger").

Posição sobre o **assunto** dita num fórum entra atribuída ("a líder de produto propõe separar piloto de escala"). Um aviso de "discrição alta" vale para os itens que lista, não para a conversa toda. Conversa enquadrada como confidencial do começo ao fim não deixa rastro: estrutura que só ela sustenta entra como "a confirmar" ou fica fora.

**Sanitizar não é esvaziar.** O filtro tira pessoas e bastidor, não substância. Página que ficou genérica volta ao material atrás de números, objetos, posições sobre o assunto e a tensão como pergunta. O que o filtro cortou e muda a leitura vai para as Notas, nunca para o corpo.

## 3. Achar a tese antes de escrever

1. Que decisão ou conversa a página prepara, e para quem?
2. Qual é a tensão central — não o tema? ("o piloto reduziu o tempo pela metade, mas ninguém sabe se a conversão mudou" é tensão; "piloto de automação no cliente X" é tema.)
3. O que é contraintuitivo ou reenquadra o problema? É a linha mais valiosa; não sai no corte.
4. Quem pede, quem usa, quem paga e quem decide são as mesmas pessoas? Quando não são, isso costuma ser parte da tese.
5. Qual lente pesa mais? O que ninguém mediu?

Sem resposta para 1 e 2, diga isso ao usuário em vez de produzir página genérica.

## 4. Formato

**Orçamento: até 420 palavras**, contadas com `bash harness/scripts/one-page-count.sh <arquivo>` (antes de Fontes, sem sintaxe de tabela nem diagrama). Abaixo de ~330, provavelmente cortou ideia em vez de palavra. Até 450 só se cortar mais tiraria o achado; diga nas Notas.

```markdown
# {Assunto}: {tensão em até 8 palavras}
{data de hoje} · base: {materiais e fóruns compartilháveis} · para {público}

{Abertura em 2 frases. A 1ª diz o que está acontecendo, com um fato concreto. A 2ª é a decisão pedida: a escolha que o leitor precisa fazer ou levar adiante.}

## Em uma olhada
| | |
|---|---|
| **Contexto** | por que isso está na mesa agora; quem pede, quem paga e decide |
| **Problema** | a dor, com um número ou um episódio concreto |
| **Oportunidade** | o que se ganha daqui para frente — não o que já foi ganho |
| **{reenquadre}** | "O que não é IA", "O que não é o problema", "Custo"… (até 2 linhas, se houver duas críticas que mudam a leitura) |

{Diagrama opcional + 1 frase do que ele mostra}

## O que aprofundar, por lente
| Lente | Hipótese | O que descobrir | Com quem |
|---|---|---|---|
| **Negócio** | | 2–3 perguntas curtas; a 1ª é a que derrubaria a hipótese | |
| **Produto** | | | |
| **Design** | | | |
| **Tecnologia** | | | |

## Próximos passos   (opcional)
- [ ] ação — dono

## Fontes   (opcional)
| Material | O que tem | Onde está |
```

Dados, Conexões e Pesquisa adicional entram entre Lentes e Próximos passos, só se mudarem a leitura.

### Regras

1. **Específico ou nada.** Cada célula traz algo que só vale para este caso: nome, número, objeto, posição. Célula que caberia em qualquer projeto vira o específico ou "—". Lente sem pergunta leva "—" nas três células; as quatro ficam, porque mostram onde não há pergunta. A lente dominante pode ter células mais longas.
2. **Hipótese refutável**, uma por lente no máximo. "O que descobrir" começa pelo dado ou conversa que a derrubaria, com fonte ou ferramenta que existe no material; não nomeie sistema que você não viu.
3. **Um fato, um lugar.** Nenhum número ou episódio aparece duas vezes. A 2ª frase da abertura é a decisão pedida e não se repete adiante. Retomar o referente da tese (quem paga, a meta) numa hipótese ou pergunta não é repetição: a tese não se esconde para cumprir esta regra.
4. **Números:** só os que carregam a tese ou uma hipótese, cerca de 6 a 10 no corpo, em geral um por célula. Três números de bases diferentes para a mesma ideia confundem: fique com um e mande os outros para as Notas. Etapas de um mesmo funil (500 contratados, 80 ativos) podem ir juntas. Dois números lado a lado só quando divergem por origem ("11–12 semanas no fórum de contas; 14 segundo o time"); nunca funda em intervalo que ninguém disse. Número que é conta sua diz a base.
5. **Fidelidade ao modo.** "Pode ser contratada" não vira "vende"; "propõe" não vira "decidiu"; regra geral de alguém não vira posição sobre este caso. Relato leva "segundo X", inclusive em "Hipótese" e no Contexto; só o que foi mostrado ou está num material é fato. Lacuna é lacuna: "não encontramos meta escrita", não "não há meta". Data sem dono entra como "previsto".
6. **Papéis certos do ponto de vista do leitor e da decisão:** de que empresa a pessoa é (gerente de entrega da nossa empresa na conta, não "do cliente") e o que ela é na decisão (sócia da cliente, não "usuária"). Na dúvida, papel sem nome ou Nota.
7. **Siglas e jargão:** expanda na primeira vez ou troque por palavras ("régua" → "como medir o acerto"). Etapas citadas por número (Onda 2) pedem um diagrama ou uma linha que as nomeie.
8. **Reenquadre não é decisão.** Se contradiz a posição registrada de alguém do público, entra atribuído ou como pergunta.
9. **Com quem e donos:** nome e papel quando o material sustenta; papel específico sem nome serve ("analistas de pricing", não "Tecnologia"). Dono de próximo passo é nomeado no material, "sugerido: X — confirmar" ou "dono a definir". Prazo só se o material disser. O que você escolheu vai para as Notas.
10. **Diagrama** é o padrão quando o assunto é uma esteira, um fluxo ou uma sequência de ondas: ASCII de até 6 caixas, mais 1 frase. Na exportação vira diagrama de verdade.
11. **Opcionais:** Dados só com 2+ números que não estão em outra seção, cada um com origem; análise sua é "análise preliminar"; uma linha **Ainda não medido:** pode ficar sozinha. Conexões no máximo 2, se mudarem uma decisão. Pesquisa adicional só quando um dado externo muda uma hipótese: web, fonte e data, "(externo)", no máximo 2; por padrão não pesquise. Fontes só com o que o colega consegue abrir ou pedir (deck, planilha compartilhada, transcrição na ferramenta de reuniões), nunca caminho do vault.

**Corte, quando passar de 420:** palavras antes de ideias (adjetivos, atribuições redundantes, frases que explicam a tabela). Depois: Conexões, Dados, Próximos passos, perguntas das lentes não dominantes. Nunca saem: o reenquadre, o achado contraintuitivo, a crítica mais forte ao próprio material e a decisão pedida.

## 5. Revisar antes de mostrar

Releia como o colega que não estava lá:
- [ ] A contagem está entre ~330 e 420? Algum fato aparece duas vezes?
- [ ] A abertura tem tensão com fato concreto e a 2ª frase é a escolha pedida?
- [ ] Cada nome tem papel certo, cada sigla se entende, cada número tem origem e cabe na memória?
- [ ] Algum verbo ficou mais forte que na fonte, algum relato virou fato, algum dono, prazo ou sistema foi inventado?
- [ ] Alguma frase falha no filtro da sala, inclusive por dedução de quem disse o quê em conversa privada?

## 6. Mostrar na tela

Sem preâmbulo:
1. A One Page em markdown.
2. `---` e **Notas para o usuário (fora da página)**, até 5 itens: o que o filtro cortou e muda a leitura; inferências suas (hipóteses, nomes em "com quem", donos); lacunas; a pergunta cuja resposta mais mudaria o texto.
3. Linha final com o caminho do rascunho e a oferta de exportar nos destinos que a sessão oferece.

Antes de mostrar, salve a página em `drafts/one-page/YYYY-MM-DD-<slug>.md` e as Notas em `drafts/one-page/YYYY-MM-DD-<slug>.notas.md`. As Notas nunca são exportadas. Em cada ajuste, reescreva os arquivos e mostre de novo só a página, ou só o trecho se a mudança for pontual.

## 7. Ajustes e exportação

- **Ajuste:** aplique exatamente o que o usuário pediu; texto dele entra literal. Não reabra a tese a cada ajuste.
- **Exportar só quando pedido**, do rascunho aprovado, sem reescrever e sem as Notas, no destino que o adaptador do host oferece (documento, página publicada, arquivo). Sem destino próprio, HTML ou MD local em `output/one-page-<slug>/`. Tabelas viram tabelas; o ASCII vira diagrama. Padrão de marca, se houver, vem da memória do usuário ou do vault.
- Publicar ou compartilhar continua com o usuário.

## Erros comuns

- Ata ("na reunião, fulano disse…") em vez de assunto.
- Simetria forçada: quatro lentes do mesmo tamanho com frases genéricas.
- Texto demais, o motivo mais comum de rejeição. Ou o oposto: tão cortada ou sanitizada que perde o achado.
- Vazar bastidor para parecer perspicaz, ou usar conversa privada como argumento.
- Hipótese que nada derruba ("a IA pode ajudar").
- Inventar dono, prazo, número, sistema ou nome para preencher célula.

## Calibração

Orçamento, filtro e regras saíram de quatro rodadas de teste em casos reais de consultoria, avaliadas às cegas por modelos de dois provedores contra uma página aprovada pelo usuário (~370 palavras, tabelas curtas, uma frase por célula). Os defeitos que mais voltaram: excesso de números, papel errado de pessoa, relato apresentado como fato e conversa privada usada como argumento.
