# Conceito Diferença entre Visão do Cliente e Visão Interna no Notion

## 🎯 Categoria
Conceito

## 📌 Sumário Executivo
No Notion, é fundamental que a visão do cliente seja restrita apenas ao que ele precisa ver, ocultando conteúdos em produção ou informações internas, para garantir privacidade e evitar confusões.

## �� Descricao
A distinção entre a visão do cliente e a visão interna dentro do Notion é um pilar fundamental para a gestão eficaz e segura de projetos e informações. A visão interna é o ambiente completo de trabalho da equipe, onde se tem acesso irrestrito a todas as bases de dados, conteúdos em desenvolvimento, ferramentas de filtragem avançada e configurações de automação. Este é o espaço onde a produção acontece e onde todas as informações são gerenciadas.

Por outro lado, a visão do cliente é uma versão meticulosamente controlada e restrita, criada especificamente para que o cliente tenha acesso apenas ao que é estritamente necessário e relevante para ele. O principal objetivo é ocultar conteúdos em produção, discussões internas, detalhes de outras bases de dados ou qualquer outra informação que não diga respeito diretamente ao cliente ou que possa gerar confusão. Esta restrição é implementada através de níveis de permissão (como "pode comentar" ou "pode visualizar") e, mais crucialmente, pela aplicação de filtros rigorosos nas bases de dados. Esses filtros garantem que o cliente não consiga, por exemplo, visualizar a base de dados em sua totalidade ou alterar suas propriedades e configurações internas.

A segurança dessa abordagem reside no fato de que, mesmo que o cliente consiga gerar novos filtros em sua visualização, ele não terá acesso aos filtros originais da base de dados interna, impedindo-o de "descobrir" informações não destinadas a ele. O acesso do cliente é sempre feito através de um link direto para uma página específica, já filtrada para exibir apenas o seu conteúdo relevante, assegurando que ele não interfira nem tenha ciência do fluxo de trabalho interno ou de outros clientes.

## Complexidade
Intermediario

## ⏱️ Templo de implementação
10-15 min para entender | 1-2 horas para aplicar

## ⚡Como Aplicar
Nao se aplica

## 💡 Exemplos Práticos
Ao compartilhar o progresso de um projeto com um cliente, a equipe interna pode ter uma base de dados completa com "Linhas Editoriais", "Conteúdos" e "Clientes", onde vê todas as etapas de produção e os detalhes de todos os projetos. Para o cliente, no entanto, é configurada uma página que, via filtros específicos, mostra apenas os conteúdos e as linhas editoriais que são de sua responsabilidade, e em um status já definido para sua visualização.

Um exemplo claro da diferença de visão é quando o usuário demonstra o acesso de um cliente a uma página. A visão do cliente mostra apenas o conteúdo filtrado e relevante para ele, enquanto a visão interna da equipe inclui uma "gestão de conteúdo" completa, com todas as produções em andamento. Se o acesso do cliente à "gestão de conteúdo" não for removido, ele poderá ver toda a produção interna, o que é indesejado.

Para o acesso, o cliente receberá um link direto para a sua página personalizada. Mesmo que a equipe tenha concedido acesso a bases de dados específicas como "Clientes", "Conteúdos" e "Linhas Editoriais" com permissões limitadas, o cliente não conseguirá ver a base de dados completa. A segurança é tal que, se não for fornecido o link específico da sua página (que já vem com os filtros aplicados), o cliente não conseguiria nem acessar a sua própria página dentro do sistema devido à filtragem rigorosa por "nome vazio" ou outras propriedades que garantem que ele não "enxergue" outras informações.

## ⚠️ Armadilhas Comuns
*   **Exposição de Conteúdo em Produção:** Não remover o acesso do cliente à "gestão de conteúdo" ou páginas de produção interna pode fazer com que ele visualize trabalhos inacabados ou informações confidenciais.
*   **Publicação Inadequada de Bases de Dados:** A tentativa de publicar uma base de dados inteira na web, em vez de compartilhar uma página específica com filtros, pode expor dados sensíveis e internos da sua operação.
*   **Custos Adicionais por Aprovação Indevida:** Aprovar um cliente como "membro" em vez de mantê-lo como "convidado" pode gerar custos desnecessários no plano pago do Notion, uma vez que o preço é cobrado por membro.
*   **Falta de Filtros Apropriados:** Não configurar filtros robustos nas visualizações compartilhadas pode permitir que o cliente veja mais informações do que o desejado ou que ele tente manipular a base de dados, mesmo sem ter permissão de edição.

## 📊 Metricas/Resultados
Nao se aplica

## 🔧 Ferramentas Necessarias
Notion

## Consideracoes
A implementação correta da diferenciação entre a visão do cliente e a visão interna no Notion é vital para manter a privacidade, segurança e a integridade dos seus dados e processos internos. Garante que o cliente tenha uma experiência focada, recebendo apenas as informações essenciais para ele, enquanto a equipe mantém total controle sobre o ambiente de trabalho e as informações estratégicas. É uma questão de lógica e segurança que evita que o cliente acesse filtros da base de dados principal, permitindo que ele "enxergue" somente o necessário e não tenha acesso à sua produção interna.

## Entidades
Visão do Cliente, Visão Interna, Filtros, Bases de Dados, Conteúdo em Produção

## Pré-requisitos
*   [[Conceito Diferença entre Convidado e Membro no Notion]]
*   [[Recurso Filtros e Ordenação de Bases de Dados]]
*   [[Processo Compartilhamento de Bases de Dados Específicas com Clientes no Notion]]

## 🔗Conhecimentos Relacionados
-   [[Conceito Diferença entre Convidado e Membro no Notion]]
-   [[Limitação Acesso Restrito de Convidado em Filtros]]
-   [[Limitação Publicação de Bases de Dados na Web]]
-   [[Dica Não Aprovar Convidado como Membro para Evitar Custos Indevidos]]
-   [[Processo Compartilhamento de Bases de Dados Específicas com Clientes no Notion]]
-   [[Dica Como o Cliente Acessa Páginas Compartilhadas no Notion]]
-   [[Técnica Agrupar Bases de Dados para Compartilhamento Simplificado com Clientes no Notion]]

## 📚Fonte
**Documento:** Fundamentos do Notion - By @xEistibus ❤️‍🔥 LABORATÓRIO DE IA =LABORATÓRIO DE IA ==05. Funda_130_audio.txt
**Pagina/Secao:** Nao se aplica

## 🏷️ Tags
#Conceito #Notion #GestaoDeConteudo #Seguranca #Privacidade