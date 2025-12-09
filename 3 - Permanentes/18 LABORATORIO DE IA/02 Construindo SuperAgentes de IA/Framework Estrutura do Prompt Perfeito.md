# Framework Estrutura do Prompt Perfeito

## 🎯 Categoria
Framework

## 📌 Sumário Executivo
A Estrutura do Prompt Perfeito é um framework de oito partes para a construção de prompts eficazes para IAs, visando obter resultados precisos e alinhados às expectativas. Suas componentes são: Persona, Contexto, Instrução Principal, Objetivo, Diretrizes, Dados de Entrada, Formato de Resposta e Restrições.

## 📝 Descricao
A Estrutura do Prompt Perfeito é uma metodologia dividida em oito componentes essenciais que, quando seguidos, permitem estruturar um prompt de forma clara e abrangente para uma Inteligência Artificial, garantindo que a IA entenda e execute a tarefa exatamente como desejado.

As oito partes são:

1.  **Persona**: Define o papel ou a função que se deseja que a IA assuma. É crucial que a persona seja tangível (ex: analista de dados, copywriter) para que a IA possa utilizar seu vasto repertório de forma análoga e eficaz, agindo como um especialista na área designada.
2.  **Contexto**: Fornece todas as informações relevantes e necessárias para que a IA leve em consideração ao gerar o resultado. Isso garante que a resposta esteja alinhada com a situação ou cenário específico.
3.  **Instrução Principal**: É a explicação clara e direta da tarefa que se espera que a IA desempenhe. Deve detalhar o que a IA precisa fazer.
4.  **Objetivo**: Especifica qual o resultado final esperado da tarefa. O objetivo deve ser tangível e mensurável, descrevendo o efeito desejado da ação da IA.
5.  **Diretrizes**: Estabelece como a IA deve se comportar e quais passos ou metodologias deve seguir para gerar a resposta. Inclui orientações sobre estilo, tom e a utilização de frameworks específicos (ex: AIDA, The Godfather, PAS).
6.  **Dados de Entrada**: Lista todas as informações que serão fornecidas à IA, incluindo a base de conhecimento. Deve-se instruir a IA sobre como usar cada dado para gerar a resposta.
7.  **Formato de Resposta**: Define como a IA deve entregar a resposta. Pode ser um formato específico como tabela, relatório, código, texto em Markdown, ou blocos separados por sessão, garantindo a organização da saída. Também pode incluir "exemplos" ou "shots" de como a resposta final deve parecer.
8.  **Restrições**: Informa à IA quais ações ou comportamentos são proibidos ou não desejados. Serve para delimitar a atuação da IA e evitar respostas inadequadas ou fora do escopo.

## Complexidade
Intermediario

## ⏱️ Templo de implementação
30-60 min para entender | 1-2 horas para aplicar

## ⚡Como Aplicar
1.  **Defina a Persona**: Indique o papel específico e tangível que a IA deve assumir (ex: "Atue como um copywriter especializado em lançamentos digitais").
2.  **Estabeleça o Contexto**: Forneça informações cruciais sobre o projeto, produto, público-alvo, e o objetivo geral que a IA deve considerar (ex: "Este prompt é para criar uma apostila que resume a CPL do lançamento e engaja os leads, aumentando a percepção de valor do evento").
3.  **Descreva a Instrução Principal**: Comunique claramente a tarefa que a IA deve realizar, detalhando as etapas e subpassos se necessário, preferencialmente usando a estrutura [[Framework EPS (Etapa, Passos e Subpassos)]] (ex: "A IA deve seguir exatamente o processo detalhado abaixo para criar a apostila...").
4.  **Defina o Objetivo**: Especifique o resultado final desejado de forma mensurável e tangível (ex: "O resultado final é que os leads se engajem mais no lançamento, compareçam mais nas aulas e tenham uma percepção de valor maior do evento, aumentando minhas chances de conversão").
5.  **Crie Diretrizes**: Oriente a IA sobre o comportamento desejado, incluindo restrições de estilo e a aplicação de frameworks (ex: "Evitar jargão publicitário e comunicação muito comercial. Utilizar frameworks de conteúdo como AIDA").
6.  **Liste os Dados de Entrada**: Apresente todas as informações que a IA deve usar, como base de conhecimento ou dados específicos, e instrua como utilizá-los (ex: "Tenho uma base de conhecimento com apostilas antigas do ensinante que devem ser usadas como referência").
7.  **Especifique o Formato de Resposta**: Determine a estrutura e a apresentação do output da IA (ex: "A resposta deve ser em blocos separados por sessão, de forma modular").
8.  **Adicione Exemplos (Shots)**: Forneça um ou mais exemplos de como a resposta esperada deve ser, para guiar a IA.
9.  **Estabeleça Restrições**: Inclua proibições ou limitações específicas para a IA (ex: "Não exceder 8 mil caracteres no prompt total").

## 💡 Exemplos Práticos
Ao criar um agente de IA para gerar apostilas de CPL (Copy, Persuasão e Lançamento), a estrutura do prompt perfeito seria utilizada para definir:
*   **Persona**: "Copywriter especializado em lançamentos digitais".
*   **Contexto**: O agente agnóstico deve atuar para qualquer lançamento, escrevendo uma apostila que resuma a CPL do lançamento e engaje os leads, aumentando a percepção de valor do evento.
*   **Instrução Principal**: A IA deve seguir o processo detalhado de criação de apostila, que inclui etapas como planejamento, sessão de resumo e apresentação, sessão de fixação, sessão de aplicação, finalização e entrega ao designer.
*   **Objetivo**: Aumentar o engajamento dos leads no lançamento, a presença nas aulas e a percepção de valor do evento, elevando as chances de conversão.
*   **Diretrizes**: Evitar linguagem rebuscada, jargões publicitários e comunicação excessivamente comercial.
*   **Dados de Entrada**: Referências de apostilas antigas do "ensinante" devem ser consultadas como base.
*   **Formato de Resposta**: Blocos separados por sessão, garantindo modularidade.
*   **Restrições**: O prompt não deve ultrapassar 8 mil caracteres e a persona deve ser tangível.

## ⚠️ Armadilhas Comuns
*   **Persona Intangível**: Atribuir à IA um papel que não é uma função ou cargo real, dificultando a analogia e atuação da IA.
*   **Objetivos Vagos**: Definir objetivos de forma subjetiva, como "quero que o conteúdo fique criativo", em vez de "quero que o conteúdo gere X% de conversão".
*   **Prompt Excessivamente Longo**: Ultrapassar o limite de 8 mil caracteres pode afetar a performance e a compreensão da IA.
*   **Falta de Guia para Dados de Entrada**: Não instruir a IA sobre como usar cada item da base de conhecimento pode levar a resultados inconsistentes.
*   **Ausência de Execução Modular**: Tentar que a IA realize toda a tarefa de uma vez, em vez de dividi-la em etapas menores, pode gerar resultados menos precisos.

## �� Metricas/Resultados
Nao se aplica

## 🔧 Ferramentas Necessarias
Qualquer ferramenta ou plataforma que utilize prompts para interagir com Inteligências Artificiais, como o ChatGPT (OpenAI).

## Consideracoes
A aplicação da Estrutura do Prompt Perfeito é fundamental para otimizar a comunicação com a IA, garantindo que as instruções sejam compreendidas e executadas com a máxima precisão. Boas práticas incluem o uso de uma persona tangível, a incorporação de frameworks e referências na instrução principal, a definição de objetivos tangíveis e a execução modular da tarefa. É importante também atentar-se ao limite de caracteres e fornecer guias claros para o uso dos dados de entrada.

## Entidades
Persona, Contexto, Instrução Principal, Objetivo, Diretrizes, Dados de Entrada, Formato de Resposta, Restrições

## Pré-requisitos
Nao se aplica

## 🔗Conhecimentos Relacionados
-   [[Boas Práticas Criação de Prompts para IA]]
-   [[Agente de IA Superpronto]]
-   [[Processo Criação de GPT Personalizado (OpenAI)]]
-   [[Framework EPS (Etapa, Passos e Subpassos)]]

## 📚Fonte
**Documento:** 1. CONSTRUINDO SUPERAGENTES DE IA - By @xEistibus ❤️‍�� LABORATÓRIO DE IA =LABORATÓRIO DE IA ==_105_audio.txt
**Pagina/Secao:** Discussão sobre "estrutura do pronta perfeito" e detalhamento das 8 partes.

## 🏷️ Tags
#framework #prompt #ia #chatgpt #openai