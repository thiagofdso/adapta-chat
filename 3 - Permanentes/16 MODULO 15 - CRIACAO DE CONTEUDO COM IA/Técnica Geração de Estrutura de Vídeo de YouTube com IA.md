# Técnica Geração de Estrutura de Vídeo de YouTube com IA

## 🎯 Categoria
Técnica

## 📌 Sumário Executivo
Utiliza um prompt para que a IA atue como contentwriter e crie uma estrutura detalhada de vídeo de YouTube (10-15 minutos) com base em uma headline e seguindo a estrutura AIDA, definindo sessões, subseções, tópicos e subtópicos, sem roteirizar narração ou sugerir elementos audiovisuais. Inclui a adaptação do prompt para fornecer contexto adicional e especificar minutagem por seção.

## 📝 Descricao
A "Técnica Geração de Estrutura de Vídeo de YouTube com IA" envolve a utilização de prompts específicos no ChatGPT (ou IA similar) para elaborar o esqueleto de um vídeo de YouTube. Esta técnica é a primeira parte de um processo de duas etapas para a criação de conteúdo longo, onde a estrutura é gerada antes da redação do texto completo do roteiro.

O prompt inicial instrui a IA a atuar como um "contentwriter" e a criar uma estrutura com sessões, sub-sessões, tópicos e subtópicos para um vídeo de YouTube, com duração especificada (por exemplo, entre 10 e 15 minutos). A estrutura deve ser baseada em uma headline fornecida e seguir a metodologia AIDA (Atenção, Interesse, Desejo, Ação).

Regras cruciais são incorporadas ao prompt para guiar a IA:
*   **Foco na Estrutura Textual**: A IA deve focar exclusivamente na criação da estrutura textual, sem roteirizar a narração ou fazer sugestões audiovisuais (como "nessa sessão coloque uma imagem assim ou grave assado").
*   **Formatação Clara**: As sessões e sub-sessões devem ser divididas com títulos e tamanhos de títulos diferentes para facilitar a visualização e organização.
*   **Contexto Adicional**: É fundamental fornecer um contexto adicional se a headline por si só não for suficiente para a IA entender o conteúdo a ser abordado. Isso garante que a IA não "adivinhe" o tema principal.
*   **Minutagem por Seção**: A inclusão de um `time code` (código de tempo) para cada sessão permite que a IA direcione o tamanho e a profundidade do conteúdo a ser abordado em cada parte, alinhando-o com a minutagem desejada do vídeo.

O processo é iterativo. Após a geração da estrutura inicial, ela é revisada e pode ser refinada com prompts adicionais, solicitando alterações, inclusões de informações extras (como listas de dietas específicas) ou ajustes na organização, até que a estrutura esteja otimizada para o vídeo.

## Complexidade
Intermediario

## ⏱️ Templo de implementação
10-15 min para entender | 3-5 horas para aplicar

## ⚡Como Aplicar

1.  **Definir a Headline e Contexto**: Escolha a headline principal do vídeo do YouTube. Se a headline for muito genérica ou não detalhar completamente o tema (ex: "A simples mudança..."), forneça um contexto adicional claro. Por exemplo, para a headline "Conheça a simples mudança que pode eliminar de vez os seus sintomas da menopausa", o contexto adicional pode ser "como a redução do açúcar e a adoção de uma dieta anti-inflamatória pode reduzir drasticamente os sintomas da menopausa".
2.  **Elaborar o Prompt Inicial para a Estrutura**: Crie um prompt instruindo a IA a atuar como um "contentwriter". Solicite a criação de uma estrutura detalhada (sessões, sub-sessões, tópicos, subtópicos) para um vídeo de YouTube com uma duração específica (ex: entre 10 e 15 minutos), com base na headline e no contexto fornecidos, e seguindo a metodologia AIDA (Atenção, Interesse, Desejo, Ação).
3.  **Adicionar Regras e Formatação no Prompt**:
    *   Inclua a instrução explícita: "Foque apenas em criar a estrutura textual do vídeo, sem a necessidade de roteirizar a narração ou fazer sugestões audiovisuais do conteúdo."
    *   Adicione a regra para formatação visual: "Divida as subseções e sessões com títulos e tamanhos diferentes de títulos para ficar mais fácil a visualização."
    *   Incorpore a minutagem esperada para cada sessão (ex: "Atenção: 0-2 minutos") para guiar a IA sobre a extensão de cada parte da estrutura.
    *   Forneça um exemplo de como a estrutura deve ser formatada (ex: "Primeira Sessão (Atenção): Subseção - Tópicos - Subtópicos").
4.  **Gerar a Estrutura**: Envie o prompt para a IA.
5.  **Revisar e Refinar Iterativamente**:
    *   Examine a estrutura gerada.
    *   Se houver lacunas ou necessidade de mais detalhes, envie prompts de feedback. Por exemplo, se a estrutura não incluiu tipos específicos de dietas anti-inflamatórias, você pode solicitar: "Gostei muito. No entanto, faça algumas alterações nessa estrutura. Em algum lugar, onde você achar mais pertinente, coloque um tópico ou subtópico para falar das principais dietas anti-inflamatórias. Além disso, pegue uma das dietas para expandir e transformar em um plano alimentar de 7 dias."
    *   Continue refinando até que a estrutura esteja completa e alinhada com os objetivos do vídeo.
6.  **Decupagem Humana**: Realize uma "lapidação" manual da estrutura. Este passo é crucial para garantir que a estrutura seja concreta, relevante e alinhada com o especialista que irá gravar o vídeo, adicionando nuances que a IA pode não ter capturado.

## �� Exemplos Práticos
Um exemplo prático detalhado da aplicação desta técnica, conforme descrito na fonte, é a criação da estrutura para um vídeo de YouTube sobre menopausa:

*   **Headline**: "Conheça a simples mudança que pode eliminar de vez os seus sintomas da menopausa."
*   **Contexto Adicional Fornecido à IA**: "sobre como a redução do açúcar e a adoção de uma dieta anti-inflamatória pode reduzir drasticamente os sintomas da menopausa."
*   **Prompt (adaptado)**: "Aja como um contentwriter e faça uma estrutura com sessões e sub-sessões, tópicos e subtópicos de vídeo de YouTube entre 10 e 15 minutos sobre como a redução do açúcar e a adoção de uma dieta anti-inflamatória pode reduzir drasticamente os sintomas da menopausa, com a headline 'Conheça a simples mudança que pode eliminar de vez os seus sintomas da menopausa', seguindo a estrutura AIDA. Foque apenas em criar a estrutura textual do vídeo sem a necessidade de roteirizar a narração ou fazer sugestões audiovisuais. Divida as subseções e sessões com títulos e tamanhos diferentes. Inclua time codes para cada seção."
*   **Estrutura Inicial Gerada (Excertos)**:
    *   **Atenção (0-2 minutos)**: Introdução chamativa, apresentação do problema (sintomas da menopausa), apelo ao público, introdução da solução (dieta anti-inflamatória e redução do açúcar).
    *   **Interesse**: Como o açúcar afeta os sintomas da menopausa (impacto na inflamação, desregulação hormonal).
    *   **Desejo**: O papel de uma dieta anti-inflamatória, exemplos práticos de implementação (alimentos a eliminar/reduzir, substituições), prova de funcionamento (estudos, histórias de sucesso).
    *   **Ação**: Estímulo para começar (desafio de 7 dias), recomendação de nutricionista.
*   **Refinamento Solicitado pela Iteração**:
    *   Pedido para adicionar um tópico ou subtópico sobre as "principais dietas anti-inflamatórias existentes".
    *   Pedido para expandir uma dessas dietas em um plano alimentar de 7 dias.
*   **Resultado do Refinamento (Excertos)**: A estrutura foi atualizada para incluir uma seção sobre "Principais dietas inflamatórias" com exemplos (como a dieta cetogênica mencionada como protocolo) e um exemplo de plano alimentar.

## ⚠️ Armadilhas Comuns
*   **Falta de Contexto**: A IA pode gerar uma estrutura genérica se a headline não for suficientemente específica ou se não for complementada com contexto adicional claro, levando a um conteúdo desalinhado com a intenção.
*   **Inclusão de Elementos Indesejados**: Se as regras sobre o que *não* incluir (como roteirização de narração ou sugestões audiovisuais) não forem explícitas, a IA pode adicionar esses elementos, exigindo correção manual.
*   **Ausência de Minutagem**: Não especificar a duração de cada seção pode resultar em uma estrutura desequilibrada, com algumas partes muito longas e outras muito curtas para o tempo total do vídeo.
*   **"Alucinações" da IA**: Ao solicitar "histórias de sucesso" sem um input de dados reais, a IA pode "inventar" cenários, resultando em informações inverídicas que comprometem a credibilidade do conteúdo. É recomendado remover ou adaptar solicitações que dependam de dados não verificáveis.

## 📊 Metricas/Resultados
Nao se aplica

## 🔧 Ferramentas Necessarias
*   ChatGPT (ou outra plataforma de IA com capacidade de geração de texto)

## Consideracoes
*   A "decupagem humana" da estrutura gerada pela IA é um passo crucial. A IA fornece um esqueleto, mas a inteligência humana é necessária para refinar, dar concretude, adicionar nuances e garantir que o conteúdo seja relevante e autêntico para o especialista que o apresentará.
*   A especificação de `time codes` é uma técnica eficaz para guiar a IA na criação de seções com a profundidade e extensão adequadas, contribuindo para um vídeo bem ritmado.
*   A natureza iterativa do processo permite ajustes finos na estrutura, garantindo que o resultado final seja altamente personalizado e eficaz.
*   É importante ser muito específico nas instruções negativas (o que a IA *não* deve fazer) para evitar outputs indesejados.
*   Evitar solicitar à IA a invenção de dados ou depoimentos sem base real para manter a veracidade do conteúdo.

## Entidades
AI, ChatGPT, Estrutura de Vídeo, YouTube, Headline, AIDA

## Pré-requisitos
*   Conhecimento da estrutura AIDA (Atenção, Interesse, Desejo, Ação)
*   Compreensão dos princípios de [[Processo Criação de Conteúdo Longo com IA em Duas Etapas]]
*   Familiaridade com a [[Função da IA Contentwriter]]

## 🔗Conhecimentos Relacionados
-   [[Processo Criação de Conteúdo Longo com IA em Duas Etapas]]
-   [[Função da IA Contentwriter]]
-   [[Estrategia Criação de Conteúdo Estratégico com IA]]
-   [[Conceito Shot Prompts]]
-   [[Princípio Qualidade da Resposta da IA]]
-   [[Técnica Refinamento Iterativo da Estrutura de Conteúdo Longo com IA]]
-   [[Conceito Decupagem Humana no Processo de Criação de Conteúdo com IA]]
-   [[Estrategia Iteração de Prompts para Refinamento de Conteúdo]]
-   [[Tecnica Criação de Reels com ChatGPT (Estrutura AIDA)]]
-   [[Técnica Geração de Roteiro de Vídeo de YouTube com IA]]
-   [[Técnica Refinamento Iterativo de Roteiro de Vídeo para YouTube]]
-   [[Dica Prevenção de Alucinações da IA em Conteúdo Real]]

## 📚Fonte
**Documento:** 07. ESCREVENDO VÍDEOS DE YOUTUBE COM O CHAT GPT - By @xEistibus ❤️‍🔥_2 16. MÓDULO 15 - CRIAÇÃO_93_audio.txt
**Pagina/Secao:** Nao se aplica

## ��️ Tags
#geracaodeconteudo #youtube #videos #inteligenciaartificial #estrutura #aida