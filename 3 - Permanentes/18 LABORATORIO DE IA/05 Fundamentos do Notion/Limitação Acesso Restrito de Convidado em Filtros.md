# Limitação Acesso Restrito de Convidado em Filtros

## 🎯 Categoria
Técnica

## 📌 Sumário Executivo
No Notion, convidados com permissão de "pode comentar" possuem uma restrição quanto ao uso de filtros: eles podem adicionar filtros temporários, mas são impedidos de criar ou remover filtros da base principal de dados. Essa limitação garante que o convidado não consiga visualizar informações além do que foi originalmente definido pelos filtros da página compartilhada.

## 📝 Descricao
Um convidado com permissão de 'pode comentar' tem uma limitação importante: ele pode gerar filtros adicionais, mas não pode criar ou remover filtros da base principal. Isso impede que veja mais do que o determinado pelos filtros originais. Dessa forma, mesmo que um convidado tente manipular os filtros de uma visualização, ele não conseguirá alterar a configuração padrão que rege o acesso à informação, garantindo a privacidade e o controle sobre o conteúdo exibido. Esta funcionalidade é crucial para manter a segurança das informações compartilhadas, assegurando que o convidado acesse apenas o escopo pré-determinado pelo proprietário da página ou workspace.

## Complexidade
Intermediario

## ⏱️ Templo de implementação
5-10 min para entender | Nao se aplica para aplicar

## ⚡Como Aplicar
Nao se aplica

## 💡 Exemplos Práticos
Um exemplo prático dessa limitação é quando um usuário com permissão de "pode comentar" tenta acessar as regras de filtro de uma base de dados compartilhada. Ele poderá ver as opções de filtros, mas não conseguirá abrir a opção de "regras" para criar ou remover filtros. Ele pode gerar um filtro adicional para a sua própria visualização temporária ("eu posso filtrar mais"), mas não poderá alterar os filtros já aplicados à base principal ("mas eu não posso criar um filtro, ou tirar um filtro"). Essa restrição garante que, mesmo que o convidado tente ver além do permitido, ele estará limitado pelas configurações originais da página, que já está filtrada na base principal.

## ⚠️ Armadilhas Comuns
A principal armadilha seria assumir que um convidado pode alterar as visualizações filtradas de forma permanente, o que não é o caso. Proprietários de workspaces devem estar cientes de que a visualização original que é compartilhada já deve ter os filtros de privacidade e acesso configurados, pois o convidado não poderá desativá-los.

## 📊 Metricas/Resultados
Nao se aplica

## �� Ferramentas Necessarias
Notion

## Consideracoes
É fundamental que o acesso principal dado ao convidado já esteja devidamente filtrado na base de dados, pois a limitação impede que o convidado altere esses filtros predefinidos. Essa medida de segurança evita que informações sensíveis ou de outros clientes sejam acessadas indevidamente.

## Entidades
Convidado, Filtros, Base de Dados, Permissões

## Pré-requisitos
Conceito Diferença entre Convidado e Membro no Notion, Recurso Filtros e Ordenação de Bases de Dados

## 🔗Conhecimentos Relacionados
-   [[Conceito Diferença entre Convidado e Membro no Notion]]
-   [[Recurso Filtros e Ordenação de Bases de Dados]]
-   [[Técnica Aplicação de Filtros em Calendários de Conteúdo]]
-   [[Processo Compartilhamento de Bases de Dados Específicas com Clientes no Notion]]

## 📚Fonte
**Documento:** 1. Fundamentos do Notion - By @xEistibus ❤️‍🔥 LABORATÓRIO DE IA =LABORATÓRIO DE IA ==05. Funda_129_audio.txt
**Pagina/Secao:** Nao se aplica

## 🏷️ Tags
#notion #acessorestrito #filtros #convidado #permissões