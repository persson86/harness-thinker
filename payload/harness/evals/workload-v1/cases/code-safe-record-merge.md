# Screening de texto sintético delimitado

Escreva código Python 3 usando somente a biblioteca padrão e explique brevemente suas decisões. Entregue o texto do código e exemplos de testes; não execute o código.

Implemente merge_scores(existing, incoming), que recebe duas listas de dicionários e retorna uma nova lista. Cada registro tem exatamente as chaves id e score. id deve ser string não vazia composta apenas por letras ASCII minúsculas, dígitos e hífen, começando por letra. score deve ser número int ou float finito entre 0 e 4 inclusive; bool não é aceito. Não normalize espaços ou maiúsculas. Qualquer registro inválido deve causar ValueError e nenhum argumento deve ser alterado.

IDs duplicados em existing são inválidos. Em incoming, IDs duplicados são inválidos mesmo se o conteúdo repetir. Entre as duas listas, o ID pode coincidir: incoming substitui score mantendo a posição original. IDs novos são acrescentados na ordem de incoming. A lista de retorno e seus dicionários devem ser independentes dos argumentos.

Exemplo válido:
existing = [{"id":"a-1","score":2}, {"id":"b","score":3}]
incoming = [{"id":"b","score":4}, {"id":"c","score":0}]

Inclua exemplos de testes que cubram substituição, independência das estruturas e pelo menos dois limites de validação relevantes. Preserve a interface solicitada.

Responda em português, com até 700 palavras.
