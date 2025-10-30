No Windows, certos caracteres não podem ser usados em nomes de arquivos e pastas porque têm significados especiais para o sistema operacional e podem causar erros. Esses caracteres são reservados e seu uso é bloqueado pelo sistema de arquivos NTFS.

### Caracteres não permitidos no Windows
Os seguintes caracteres são proibidos em nomes de arquivos e pastas:

```
\  /  :  *  ?  "  <  >  |
```

Esses símbolos são interpretados pelo sistema de forma especial:

- `\` (barra invertida): separa diretórios em um caminho  
- `/` (barra normal): usada em comandos e caminhos de rede  
- `:` (dois pontos): separa nome de unidade e fluxos de dados  
- `*` (asterisco): usado como curinga em buscas  
- `?` (interrogação): representa um caractere desconhecido em buscas  
- `"` (aspas duplas): delimitam strings e nomes  
- `<` e `>`: usados em redirecionamento de comandos  
- `|` (barra vertical): redireciona a saída de comandos entre programas [3][5][7][9]

### Outras restrições
- Os caracteres com valores ASCII de 0 a 31 também não são permitidos (caracteres de controle).  
- O nome do arquivo não pode terminar com espaço (` `) ou ponto (`.`).  
- Existem nomes reservados que não podem ser usados sozinhos, mesmo sem extensão, como:  
  `CON`, `PRN`, `AUX`, `NUL`, `COM1` até `COM9`, e `LPT1` até `LPT9`.[3][5]

### Exemplos válidos e inválidos

| Exemplo de nome | Válido? | Motivo |
|------------------|---------|--------|
| relatório.txt | Sim | Nome comum permitido |
| teste:log.txt | Não | Dois pontos não permitidos |
| backup\|2025.zip | Não | Uso de pipe (|) |
| dados_backup#10 | Sim | O símbolo # é aceito |
| ?temp*.log | Não | Contém curinga e interrogação |
