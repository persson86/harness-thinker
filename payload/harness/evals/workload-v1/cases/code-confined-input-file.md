# Screening de texto sintético delimitado

Forneça código Python 3, biblioteca padrão, para validate_input_file(root, relative). Entregue código e exemplos de testes, sem executar nada. A função retorna pathlib.Path do arquivo resolvido ou lança ValueError.

root representa um diretório local existente. relative deve ser string não vazia em sintaxe POSIX, relativa a root. Rejeite caminho absoluto, barra invertida, componentes vazios, ponto, ponto-ponto e qualquer componente com dois-pontos. Não normalize entradas inválidas para torná-las válidas.

O arquivo final precisa existir, ser regular e estar dentro de root. Não aceite symlinks em nenhum componente percorrido de relative, inclusive o arquivo final, mesmo quando apontam para dentro de root. O root pode ser fornecido através de symlink; nesse caso sua resolução define a raiz confiável. Erros de tipo, permissão ou inexistência devem virar ValueError com uma mensagem útil. Não abra nem leia conteúdo do arquivo.

O chamador usará o resultado mais tarde. Não foi prometido que o sistema de arquivos ficará imóvel entre validação e uso. Explique o alcance dessa limitação.

Inclua exemplos de testes para arquivo normal, escape lexical, symlink interno e diretório no lugar de arquivo. Os nomes nos exemplos devem ser relativos e os diretórios de teste devem ser temporários.

Responda em português, com até 700 palavras.
