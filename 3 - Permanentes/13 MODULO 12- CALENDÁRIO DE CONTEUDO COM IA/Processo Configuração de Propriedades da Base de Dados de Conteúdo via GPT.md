# Processo Configuração de Propriedades da Base de Dados de Conteúdo via GPT

## 🎯 Categoria
Processo

## �� Sumário Executivo
Este processo descreve como configurar as propriedades (colunas) de uma base de dados de conteúdo dentro de um template, alinhando-as com a estrutura de dados que é retornada pelo GPT de calendário. Envolve a vinculação da base de dados de conteúdo, a limpeza/ocultação de propriedades desnecessárias e a configuração das propriedades essenciais como título, canal, formato, data de publicação, linha editorial, etapa do funil e tipo de conteúdo, garantindo que o calendário gerado pelo GPT possa ser facilmente integrado e visualizado.

## 📝 Descricao
A configuração das propriedades da base de dados de conteúdo é um passo crucial para integrar eficazmente o calendário gerado por um GPT em um template de gestão. Inicialmente, vincula-se a base de dados de conteúdo ao template de estratégia utilizando a função de "vinculação de base de dados". Após a vinculação, a base de dados apresentará todas as suas propriedades existentes.

O processo então se concentra em "limpar" essa base de dados, ajustando suas propriedades para corresponder exatamente às colunas que o GPT de calendário irá retornar. As propriedades que o GPT tipicamente gera e que devem ser mantidas/configuradas incluem:
*   **Título do conteúdo**
*   **Canal** (onde o conteúdo será publicado)
*   **Formato** (da publicação)
*   **Data da publicação**
*   **Linha editorial**
*   **Etapa do funil**
*   **Tipo de conteúdo** (com opções como atração, conexão, conversão e reconversão, além de "ideia")

Propriedades que não são geradas pelo GPT ou que são redundantes (como "links", "responsável", "criado por" e a propriedade de "cliente", que será tratada por um filtro forçado) devem ser ocultadas para manter a clareza e evitar informações duplicadas. A propriedade "fase" é mantida, pois é considerada útil para o gerenciamento interno.

Adicionalmente, é configurado um filtro avançado para automaticamente forçar a associação do cliente atual a cada novo item de conteúdo criado. Por exemplo, ao criar uma nova página de conteúdo, ela já virá automaticamente com a propriedade relacionada ao cliente específico (e.g., "Rafael Weiner"), eliminando a necessidade de atribuição manual.

## Complexidade
Intermediario

## ⏱️ Templo de implementação
10-15 min para entender | 1-2 horas para aplicar

## ⚡Como Aplicar
1.  **Vincular a Base de Dados de Conteúdo:** Dentro da página da estratégia, clique na barra e selecione "vinculação de base de dados". Escolha a base de dados de conteúdo (ex: "Sá, FSM, conteúdo, suporte, teste") para vinculá-la.
2.  **Identificar Propriedades do GPT:** Consulte o GPT de calendário para entender quais são as propriedades (colunas) que ele irá retornar em sua tabela de calendário (e.g., Título, Canal, Formato, Data de Publicação, Linha Editorial, Etapa do Funil, Tipo de Conteúdo).
3.  **Limpar/Ocultar Propriedades na Base de Dados:** Na visualização da base de dados de conteúdo vinculada, oculte ou remova as propriedades que não são relevantes ou que não correspondem às que o GPT gera (e.g., "links", "responsável", "cliente" – pois este será forçado por filtro, "criado por"). Mantenha a propriedade "fase" se for útil.
4.  **Configurar Propriedades Essenciais:** Garanta que as propriedades essenciais retornadas pelo GPT estejam presentes e configuradas corretamente para receber os dados (e.g., "Título do conteúdo", "Canal", "Formato", "Data da publicação", "Linha editorial", "Etapa do funil", "Tipo de conteúdo").
5.  **Forçar Vinculação de Cliente:** Adicione um filtro avançado à base de dados de conteúdo que force a propriedade "cliente" a ser o nome do cliente da estratégia atual (ex: "cliente contém Rafael Weiner"). Isso fará com que todo novo conteúdo criado já venha com essa associação.
6.  **Configurar Ordenação Padrão:** Opcionalmente, adicione uma ordenação por data de publicação em ordem crescente para que o conteúdo mais recente apareça primeiro.
7.  **Criar Filtros por Canal (Opcional):** Para melhor organização, crie visões separadas ou filtros adicionais para canais específicos (ex: um filtro para "Canais contém Instagram" e outro para "Canais contém YouTube") caso o template não os tenha por padrão.

## 💡 Exemplos Práticos
*   Após vincular a base de dados de conteúdo, observa-se que ela possui propriedades como "Criado por", "Links" e "Responsável". Essas são ocultadas.
*   O GPT de calendário indica que retornará uma coluna "Formato". A propriedade "Formato" na base de dados de conteúdo é ajustada para ser um tipo de "Select" ou "Multi-select" com as opções esperadas (vídeo, imagem, texto, etc.).
*   Ao criar uma nova entrada de conteúdo, um filtro configurado previamente com "Cliente contém Rafael Weiner" assegura que a propriedade "Cliente" dessa nova entrada já esteja preenchida com "Rafael Weiner", sem a necessidade de seleção manual.

## ⚠️ Armadilhas Comuns
*   Não alinhar as propriedades da base de dados com as colunas geradas pelo GPT, resultando em dados desalinhados ou não preenchidos após a cópia.
*   Ocultar propriedades que são úteis para o gerenciamento interno (como "fase"), pensando apenas no output do GPT.
*   Esquecer de configurar o filtro avançado para forçar a vinculação do cliente, o que exige atribuição manual para cada novo item de conteúdo.
*   Erro ao identificar qual é a base de dados correta de conteúdo a ser vinculada, especialmente se houver múltiplas bases de dados similares.

## �� Metricas/Resultados
Nao se aplica

## 🔧 Ferramentas Necessarias
*   Notion (para a gestão da base de dados e templates)
*   GPT de Calendário (para gerar o conteúdo com as propriedades definidas)

## Consideracoes
É fundamental que a estrutura das propriedades da base de dados de conteúdo reflita a saída do GPT para garantir uma integração fluida. A automação da vinculação de clientes através de filtros avançados poupa tempo e reduz erros. A propriedade "fase" é um exemplo de informação interna que deve ser mantida, mesmo que não seja gerada pelo GPT, pois agrega valor ao processo de gestão.

## Entidades
Propriedades da base de dados, GPT de calendário, Base de dados de conteúdo, Clientes, Canais

## Pré-requisitos
*   Processo Vinculação da Base de Dados de Cliente em Template de Estratégia
*   Conceito GPT de Calendário de Conteúdo

## 🔗Conhecimentos Relacionados
-   [[Conceito GPT de Calendário de Conteúdo]]
-   [[Técnica Geração de Calendário em Formato de Tabela]]
-   [[Técnica Forçar Vinculação Automática de Cliente ao Conteúdo]]
-   [[Processo Vinculação da Base de Dados de Cliente em Template de Estratégia]]
-   [[Processo Organização de Calendário por Canais Digitais (Instagram, YouTube)]]
-   [[Conceito Template de Gestão de Conteúdo]]
-   [[Estratégia Integração de Templates de Gestão]]

## 📚Fonte
**Documento:** 03 INTEGRANDO O GEC COM O GEST - By @xEistibus ❤️‍🔥 2 13. MÓDULO 12- CALENDÁRIO DE CONTEÚDO C 79 audio.txt
**Pagina/Secao:** Nao se aplica

## ��️ Tags
#processo #notion #conteudo #gpt #calendario