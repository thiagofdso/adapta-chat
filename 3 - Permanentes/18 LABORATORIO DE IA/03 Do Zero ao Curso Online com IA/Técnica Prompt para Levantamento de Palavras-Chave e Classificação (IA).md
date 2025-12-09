# Técnica Prompt para Levantamento de Palavras-Chave e Classificação (IA)

## 🎯 Categoria
Técnica

## 📌 Sumário Executivo
Estrutura de prompt para IA que solicita uma lista extensa das principais palavras-chave de um nicho de curso online, classificando-as em categorias (Problemas, Soluções, Jornada, Desejos, Impeditivos e Expectativas) para uma melhor compreensão da persona.

## 📝 Descricao
A "Técnica Prompt para Levantamento de Palavras-Chave e Classificação (IA)" é uma abordagem para automatizar a investigação dos interesses de uma persona utilizando inteligência artificial, especificamente o modo Deep Research do ChatGPT. O processo envolve a formulação de um prompt detalhado que instrui a IA a identificar palavras-chave relevantes para um nicho específico de curso online, com volume de pesquisa existente. Mais do que apenas listar, a técnica exige que a IA classifique essas palavras-chave em categorias predefinidas para fornecer insights aprofundados sobre a audiência.

As categorias de classificação são:
*   **Problemas:** Quando a palavra-chave revela as dores e desafios enfrentados pela persona.
*   **Soluções:** Quando a palavra-chave indica as tentativas ou soluções que a persona busca para resolver suas dores ou problemas.
*   **Jornada:** Refere-se ao nível de consciência da persona em relação à solução, ou seja, se ela já conhece a solução ou o curso em questão.
*   **Desejos:** Quando a palavra-chave demonstra os sonhos, objetivos ou aspirações da persona.
*   **Impedimentos:** Quando a palavra-chave exibe algum obstáculo que impede a persona de alcançar seus desejos ou objetivos.
*   **Expectativas:** Quando a palavra-chave sugere o que a persona espera ter ou encontrar em um produto ou serviço dentro do mercado do curso.

Para aplicar essa técnica, o prompt deve incluir as informações sobre o curso online (tema, problema que resolve e público-alvo) e as definições claras de cada categoria. A IA deve retornar uma tabela de duas colunas, sendo a primeira a palavra-chave e a segunda a sua classificação. Este método fornece insumos cruciais para a construção do perfil da persona, revelando o que o público pesquisa, suas dores e interesses. A IA pode fazer perguntas de refinamento sobre a audiência (internacional ou não), idioma, e o tipo de termos a serem focados (cauda longa, genéricos ou ambos).

## Complexidade
Intermediário

## ⏱️ Templo de implementação
5-10 min para entender | 30-60 min para aplicar

## ⚡Como Aplicar
1.  **Acesse o ChatGPT com modo Deep Research:** Inicie um novo chat no ChatGPT, garantindo que o modo Deep Research esteja ativado para permitir que a IA investigue na web.
2.  **Formule o Prompt Inicial:** Elabore um prompt que solicite à IA uma lista extensa das principais palavras-chave do nicho do seu curso online, com foco em termos que possuam volume de pesquisa.
3.  **Defina as Categorias de Classificação:** No mesmo prompt, instrua a IA a classificar cada palavra-chave em uma das seguintes categorias, fornecendo a definição de cada uma:
    *   **Problemas:** Palavra-chave revela dores e problemas da persona.
    *   **Soluções:** Palavra-chave revela as soluções que a persona recorre para resolver a dor ou problema.
    *   **Jornada:** Palavra-chave diz respeito ao nível de consciência da persona (se já conhece a solução ou não).
    *   **Desejos:** Palavra-chave mostra os sonhos e objetivos da persona.
    *   **Impedimentos:** Palavra-chave exibe algum impeditivo que afasta a persona de alcançar seus desejos.
    *   **Expectativas:** Palavra-chave exibe uma possível tendência do que a persona espera ter ou encontrar em um produto do seu mercado.
4.  **Forneça o Contexto do Curso:** Inclua no prompt informações detalhadas sobre o seu curso online, como o tema principal, o problema que ele resolve e quem são as pessoas que têm esse problema.
5.  **Solicite o Formato da Tabela:** Peça à IA para apresentar a lista em uma tabela de duas colunas, sendo a primeira a "Keyword" e a segunda a "Classificação da Keyword".
6.  **Interaja com a IA para Refinamento:** A IA pode fazer perguntas adicionais sobre a audiência (internacional ou não), o idioma (apenas português), e o foco das palavras-chave (cauda longa, termos genéricos ou ambos). Responda a essas perguntas para direcionar a pesquisa.

## 💡 Exemplos Práticos
**Exemplo de Prompt Base:**
"Eu quero que você faça uma lista extensa das principais palavras-chave do nicho do meu curso online. Traga essa lista em tabela, classificando a keyword em uma das categorias abaixo.

**Categorias de Classificação:**
*   **Problemas:** Quando a keyword revela sobre as dores e problemas da persona.
*   **Soluções:** Quando a keyword revela sobre as soluções que a persona recorre para resolver a dor ou problema.
*   **Jornada:** Diz respeito ao nível de consciência da persona. Se ela já conhece a minha solução ou não.
*   **Desejos:** Quando a keyword mostra os sonhos e objetivos da persona.
*   **Impeditivos:** Quando a keyword exibe algum impeditivo que afasta a minha persona de alcançar os seus desejos.
*   **Expectativas:** Quando a keyword exibe uma possível tendência do que a persona espera ter ou encontrar em um produto do meu mercado.

Traga essa lista em uma tabela de duas colunas, sendo a primeira coluna a própria Keyword, e a segunda coluna, uma classificação da Keyword seguindo as categorias acima.

**Informações do meu curso online:**
*   **Tema:** Criação de sistemas e processos com o Notion.
*   **Problema que resolve:** Pessoas com processos caóticos, falta de organização e dificuldade em escalar suas operações.
*   **Pessoas que têm esse problema:** Empreendedores digitais, freelancers, líderes de equipe e profissionais que buscam otimizar suas rotinas e negócios.

**Exemplo de Temas de Curso:**
A técnica pode ser aplicada para nichos como:
*   Criação de sistemas e processos com o Notion.
*   Criação de cursos online com o Notion.

## ⚠️ Armadilhas Comuns
*   **Prompts pouco específicos:** Um prompt que não detalha o nicho, o problema e o público-alvo pode levar a resultados genéricos ou irrelevantes.
*   **Não fornecer as definições de categoria:** Sem as definições claras para cada categoria (Problemas, Soluções, etc.), a IA pode classificar as palavras-chave de forma inconsistente ou imprecisa.
*   **Ignorar as perguntas de refinamento da IA:** A IA geralmente faz perguntas para ajustar o escopo da pesquisa (audiência, idioma, tipo de termos). Não responder a elas pode comprometer a qualidade dos resultados.
*   **Dependência excessiva da IA:** Embora a IA automatize a coleta e classificação, a interpretação humana dos resultados ainda é crucial para contextualizar as palavras-chave e garantir a relevância para a persona.

## 📊 Metricas/Resultados
*   **Lista Estruturada de Palavras-Chave:** Obtenção de uma tabela com palavras-chave relevantes para o nicho, classificadas de acordo com as necessidades e comportamentos da persona.
*   **Compreensão Aprofundada da Audiência:** A técnica fornece insumos claros sobre os interesses, dores, desejos e nível de consciência do público-alvo, facilitando a criação de um perfil de persona mais preciso.
*   **Direcionamento para Criação de Conteúdo e Produtos:** As classificações das palavras-chave oferecem insights diretos para o desenvolvimento de conteúdo, produtos e estratégias de marketing mais alinhados com o que a audiência realmente busca.

## 🔧 Ferramentas Necessarias
*   ChatGPT (com modo Deep Research ativado)

## Consideracoes
Esta técnica é uma parte fundamental da investigação da persona, fornecendo dados "brutos" que, quando bem interpretados, são essenciais para a criação de um perfil de persona detalhado. A qualidade dos resultados dependerá diretamente da clareza e detalhamento do prompt inicial e da interação do usuário com as perguntas de refinamento da IA. A saída gerada pela IA servirá como um indicativo dos interesses do público, suas dores e o que estão pesquisando, sendo um insumo valioso para a próxima etapa de criação do perfil da persona.

## Entidades
*   Palavras-chave
*   Persona
*   Nicho
*   Deep Research
*   Categorias (Problemas, Soluções, Jornada, Desejos, Impeditivos, Expectativas)

## Pré-requisitos
*   Conhecimento do nicho do curso online.
*   Definição do problema que o curso resolve.
*   Identificação do público-alvo do curso.
*   Familiaridade com o uso do ChatGPT e suas funcionalidades de pesquisa.

## 🔗Conhecimentos Relacionados
-   [[Processo Investigação da Persona (Manual e Automatizada com IA)]]
-   [[Método Investigação dos Interesses da Persona]]
-   [[Técnica Uso de Deep Research do ChatGPT para Palavras-Chave de Persona]]
-   [[Ferramenta Deep Research do ChatGPT]]
-   [[Categoria Problemas da Persona]]
-   [[Categoria Soluções Buscadas pela Persona]]
-   [[Categoria Jornada da Persona]]
-   [[Categoria Desejos da Persona]]
-   [[Categoria Impeditivos da Persona]]
-   [[Categoria Expectativas da Persona]]
-   [[Processo Classificação de Relatos da Persona]]
-   [[Processo Geração e Estruturação do Perfil da Buyer Persona com IA]]
-   [[Critério Audiência Internacional (Pesquisa de Palavras-Chave)]]
-   [[Critério Idioma da Pesquisa de Palavras-Chave]]
-   [[Critério Foco em Cauda Longa e Termos Genéricos (Pesquisa de Palavras-Chave)]]
-   [[Critério Estratégia de SEO ou Ferramentas Utilizadas (Pesquisa de Palavras-Chave)]]

## ��Fonte
**Documento:** 11. Pesquisa - Investigação da Persona com IA - Likensina - By @xEistibus ❤️‍🔥 LABORATÓRIO DE _116_audio.txt
**Pagina/Secao:** Nao se aplica

## 🏷️ Tags
#tecnica #ia #chatgpt #persona #pesquisa #palavras-chave #marketingdigital