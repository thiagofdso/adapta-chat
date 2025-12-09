# Processo Compartilhamento de Bases de Dados Específicas com Clientes no Notion

## 🎯 Categoria
Processo

## 📌 Sumário Executivo
Este processo detalha a forma segura e eficiente de compartilhar bases de dados específicas (como Clientes, Conteúdos e Linhas Editoriais) com clientes no Notion. Ele abrange a configuração de permissões restritas e a estratégia de agrupar estas bases em uma única página para facilitar o acesso do cliente e, ao mesmo tempo, proteger informações internas e de produção.

## 📝 Descricao
O compartilhamento de bases de dados específicas com clientes no Notion envolve um conjunto de passos para garantir que o cliente tenha acesso às informações relevantes sem comprometer a segurança ou a privacidade de outros dados. Inicialmente, é necessário conceder acesso a bases de dados específicas como "Clientes", "Conteúdos" e "Linhas Editoriais". As permissões devem ser cuidadosamente configuradas, sendo "pode comentar" ou "pode visualizar" as opções recomendadas para evitar que o cliente realize edições não autorizadas ou acesse informações sensíveis. É fundamental que o cliente seja adicionado como "convidado" e nunca como "membro", para controlar os custos da assinatura do Notion e limitar o acesso ao workspace geral.

Uma característica importante é que, como convidado, o cliente não terá acesso à funcionalidade de filtros da base de dados principal, ou seja, ele verá apenas o conteúdo pré-filtrado e não poderá alterar essas configurações para visualizar outros dados. Para simplificar o processo de compartilhamento e melhorar a experiência do cliente, sugere-se a criação de uma única página que agrupe todas as bases de dados essenciais que serão compartilhadas. Dessa forma, em vez de enviar múltiplos links, apenas um link é compartilhado, direcionando o cliente para uma área organizada que contém todas as informações necessárias para ele, sem expor o restante do sistema ou os conteúdos em produção.

Adicionalmente, é crucial que, após o compartilhamento, o acesso do cliente a qualquer página de "gestão de conteúdo" ou áreas de produção seja removido para que ele não visualize os trabalhos internos da equipe. A utilização de um e-mail de teste é altamente recomendada para simular a experiência do cliente e garantir que as permissões e visualizações estejam corretas.

## Complexidade
Intermediario

## ⏱️ Templo de implementação
15-20 min para entender | 1-2 horas para aplicar

## ⚡Como Aplicar
1.  **Identificar Bases Essenciais:** Determine quais bases de dados são cruciais para o cliente visualizar (e.g., Clientes, Conteúdos, Linhas Editoriais).
2.  **Convidar o Cliente:** Compartilhe cada uma dessas bases individualmente com o e-mail do cliente, concedendo permissão de "pode comentar" ou "pode visualizar". Certifique-se de não aprová-lo como "membro".
3.  **Verificar Acessos Internos:** Acesse a "gestão de conteúdo" ou páginas internas de produção e verifique se o login do cliente aparece nos convidados. Se sim, remova-o para evitar que ele veja conteúdos em desenvolvimento.
4.  **Criar Página de Agrupamento (Opcional, mas Recomendado):** Para simplificar, crie uma nova página e arraste as três bases de dados essenciais para dentro dela.
5.  **Compartilhar a Página Agrupada:** Compartilhe esta nova página única com o cliente, novamente com permissões restritas.
6.  **Fornecer o Link Direto:** Copie o link direto da página específica do cliente (ou da página agrupada) e envie-o. Recomende que o cliente favorite esta página.
7.  **Manter Filtros Seguros:** Lembre-se de que os filtros são essenciais para limitar o que o cliente vê. Ele não terá acesso para alterar ou visualizar os filtros da base principal.

## 💡 Exemplos Práticos
*   Um cliente pode visualizar o status de seus projetos na base de "Conteúdos" e as diretrizes da marca em "Linhas Editoriais", sem ter acesso ao pipeline completo de produção ou a informações de outros clientes.
*   Um segundo e-mail de teste pode ser usado para simular a visão do cliente e verificar as permissões.

## ⚠️ Armadilhas Comuns
*   Não remover o cliente da "gestão de conteúdo", permitindo que ele veja o processo de produção.
*   Aprovar um cliente como "membro", gerando cobranças desnecessárias e acesso excessivo.
*   Não fornecer o link direto da página específica do cliente, fazendo com que ele não consiga acessar o conteúdo filtrado.
*   O cliente pode solicitar acesso de membro; é crucial não aprovar.

## 📊 Metricas/Resultados
Nao se aplica

## 🔧 Ferramentas Necessarias
Notion

## Consideracoes
*   Utilizar um e-mail de teste para verificar a experiência do cliente antes de compartilhar.
*   A filtragem é a chave para a segurança e privacidade do que é exibido ao cliente.
*   A funcionalidade de "acesso completo" para edição da equipe exige o plano Plus.

## Entidades
Cliente, Bases de Dados, Permissões, Compartilhamento, Filtros

## Pré-requisitos
Nao se aplica

## 🔗Conhecimentos Relacionados
-   [[Recurso Filtros e Ordenação de Bases de Dados]]
-   [[Conceito Diferença entre Convidado e Membro no Notion]]
-   [[Técnica Agrupar Bases de Dados para Compartilhamento Simplificado com Clientes no Notion]]
-   [[Limitação Acesso Restrito de Convidado em Filtros]]
-   [[Dica Não Aprovar Convidado como Membro para Evitar Custos Indevidos]]
-   [[Dica Como o Cliente Acessa Páginas Compartilhadas no Notion]]
-   [[Conceito Diferença entre Visão do Cliente e Visão Interna no Notion]]

## 📚Fonte
**Documento:** Fundamentos do Notion - By @xEistibus ❤️‍🔥 LABORATÓRIO DE IA =LABORATÓRIO DE IA ==05. Funda_130_audio.txt
**Pagina/Secao:** Nao se aplica

## 🏷️ Tags
#processo #notion #compartilhamento #clientes #permissões