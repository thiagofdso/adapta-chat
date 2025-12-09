# Estratégia Mapeamento de Ensinantes com Deep Research

## 🎯 Categoria
Estratégia

## 📌 Sumário Executivo
Estratégia que emprega ferramentas de Inteligência Artificial (IA), como o ChatGPT com Deep Research, para identificar, analisar e catalogar os principais players ("ensinantes") e concorrentes em um nicho de mercado. O objetivo é compreender não apenas quem vende produtos similares, mas também quem disputa a atenção do público através da criação de conteúdo, mapeando suas características, públicos e ofertas para embasar a criação de um novo curso online.

## 📝 Descricao
Esta estratégia visa realizar uma investigação aprofundada do mercado para além dos concorrentes diretos, abrangendo também os "ensinantes" — indivíduos ou instituições que criam conteúdo sobre o tema central do curso, disputando a atenção do mesmo público-alvo. Utiliza-se IA, como o ChatGPT com a funcionalidade de Deep Research, para coletar dados detalhados. A metodologia inclui duas fases principais:

1.  **Mapeamento de Ensinantes (Conteúdo)**: Nesta fase, a IA é utilizada para identificar criadores de conteúdo que atuam no nicho do curso, mesmo que não vendam diretamente produtos idênticos. A distinção entre "ensinantes" e "concorrentes" é crucial; ensinantes são pessoas que habitam o mercado em termos de conteúdo, enquanto concorrentes são aqueles que vendem produtos. O prompt para a IA solicita uma investigação do mercado em que o curso online está situado e uma lista dos principais players, explicitando que estes não precisam ser concorrentes diretos que vendem soluções como a sua, mas também criadores de conteúdo que disputam a atenção. A IA deve retornar uma tabela com dados como: nome do player, natureza (pessoa ou instituição), se é infoprodutor, link do principal canal digital, assunto principal que aborda, público-alvo para quem fala e se direciona, pontos fortes e pontos fracos desse ensinante. A pesquisa pode ser configurada para atuar apenas no Brasil e em português, e incluir outros players que falam sobre temas correlatos (ex: produtividade, organização, gestão de equipe).

2.  **Análise de Concorrentes (Cursos/Produtos)**: Esta fase foca no levantamento dos principais cursos e produtos similares existentes no mercado. O processo é dividido em duas etapas:
    *   **Levantamento Inicial**: Um prompt é enviado à IA para investigar o nicho do curso online e listar os principais concorrentes, ou seja, outros cursos similares. A IA é solicitada a gerar uma tabela que liste esses concorrentes, exibindo características como: nome do produto, professor/expert do produto, formato do produto (curso, mentoria, e-book, masterclass, grupo, comunidade, ferramenta ou consultoria), URL da página do produto, URL do Reclame Aqui (se disponível) e o ticket/preço em reais. É fundamental instruir a IA a ser criteriosa, selecionando apenas concorrentes que de fato se mostrem relevantes e grandes em termos de número de alunos e impacto no mercado.
    *   **Análise Aprofundada Individual**: Para cada concorrente relevante identificado, o link da página do curso é fornecido à IA. A IA é então instruída a acessar a página e trazer uma análise detalhada em formato de tabela horizontal com quatro colunas: "Ensino" (o que o curso online objetivamente ensina), "Problema" (qual é o problema que esse curso online resolve), "Transformação" (qual é a maior transformação que esse curso online entrega) e "Promessa" (o que esse curso online promete em termos de entrega e resultado).

Essa abordagem detalhada permite uma compreensão abrangente do cenário competitivo e do ecossistema de conteúdo do nicho, fornecendo insumos valiosos para o desenvolvimento do próprio curso online.

## Complexidade
Avançado

## ⏱️ Templo de implementação
30-60 min para entender | 4-8 horas para aplicar

## ⚡Como Aplicar
1.  **Definir o Tema Central**: Iniciar com um tema central claro para o curso online, o problema que ele resolve e o público-alvo que ele atinge (ex: "criação de processos com o Notion").
2.  **Mapear Ensinantes com IA (Primeiro Prompt)**:
    *   Formular um prompt detalhado para a IA, por exemplo: "Eu quero que você faça uma investigação do mercado que o meu curso online está situado e me traga uma lista dos principais players desse mercado. Esses players não necessariamente precisam ser concorrentes diretos que vendem soluções como a minha. Criadores de conteúdo que disputam a atenção comigo também se encaixam. Essa lista deve ser uma tabela que engloba os seguintes pontos: Nome (do player), Natureza (se posiciona como uma pessoa ou uma instituição), Infoprodutor (sim ou não), Link do principal canal digital, Assunto principal (qual assunto aborda), Público-alvo (para quem fala e se direciona), Pontos fortes (do player), Pontos fracos (do player). Meu curso online é sobre [Tema do Curso, Problema que o curso resolve, Pessoas com esse problema]."
    *   Definir parâmetros adicionais como "Atua apenas no Brasil ou também em mercados internacionais?" (ex: "Apenas Brasil"), "Seu curso é oferecido em português ou em inglês?" (ex: "Apenas português"), e se deve "Incluir outros players (ex: produtividade, organização, gestão de equipe)".
3.  **Analisar Concorrentes com IA (Segundo Prompt - Levantamento Inicial)**:
    *   Formular um prompt para a IA para levantar os concorrentes diretos: "Eu quero que você investigue o meu nicho do meu curso online e me traga os principais concorrentes. Isso é outros cursos similares com o meu no mercado. Gere uma tabela que me liste esses concorrentes, exibindo as seguintes características: Nome do produto, Professor do produto (nome do professor/expert do produto), Formato do produto (curso, mentoria, e-book, masterclass, grupo, comunidade, ferramenta ou consultoria), URL da página do produto, URL do reclame aqui (se tiver) e o Ticket do produto (preço em reais em número). Seja criterioso ao selecionar os concorrentes. Não selecione cursos aleatórios. Apenas aqueles que, de fato, se mostrarem relevantes e grandes em termos de aluno e impacto no mercado. O meu curso online é sobre o tema [Tema do Curso, Problema que o curso resolve, Pessoas com esse problema]."
4.  **Análise Aprofundada Individual dos Concorrentes (Terceiro Prompt - Análise de cada URL)**:
    *   Para cada URL de concorrente relevante obtida na etapa anterior, envie um novo prompt para a IA: "Eu irei te enviar o link do curso de um curso online, que é meu concorrente. Eu quero que você acesse a página que será enviada, e traga uma análise em formato de tabela, online e no próprio chat, com os seguintes elementos: Ensino (O que o curso online objetivamente ensina?), Problema (Qual é o problema que esse curso online resolve?), Transformação (Qual é a maior transformação que esse curso online entrega?), Promessa (O que esse curso online promete em termos de entrega e resultado?). A tabela deve ser horizontal, com quatro colunas. Podemos começar? [URL do curso concorrente]"
5.  **Compilar e Refinar Dados**: Reúna e organize todas as tabelas e análises geradas pela IA. Faça uma revisão crítica dos dados para identificar inconsistências, informações desatualizadas ou irrelevantes. Use essas informações para identificar lacunas no mercado, oportunidades de diferenciação e entender o posicionamento de outros players.

## 💡 Exemplos Práticos
*   **Mapeamento de Ensinantes (Conteúdo)**: Para um curso sobre "Criação de Processos com Notion", a IA pode identificar players como "Mago do Noção" ou "Gabriela Brasil" que, embora possam não vender um curso idêntico, criam muito conteúdo sobre o Notion, produtividade e organização, disputando a atenção do público. A tabela gerada indicaria seus principais canais, o que ensinam, seu público-alvo e seus pontos fortes e fracos.
*   **Análise de Concorrentes (Cursos/Produtos)**: A IA pode listar cursos como "Notion Lab", "Noção da Almoçada", "Curso de Notion Productive Me" ou "Mentoria Notion Proglober Dourado". Para o curso "Café com o Ocean" (exemplo), a análise aprofundada pode revelar:
    *   **Ensino**: "Ensina a usar o Notion do básico ao avançado, criação de template pessoal e profissional, automação, fórmulas, botões, bloco de anotar."
    *   **Problema**: "Resolve a falta de organização pessoal e profissional, disposição de formação e monetizar o uso do Nojo."
    *   **Transformação**: "Transforma a forma como você organiza a sua vida e trabalha, tudo centralizado."
    *   **Promessa**: "Promete dominar o Notion como ferramenta principal para organizar, criar templates profissionais, somados a fluxo."

## ⚠️ Armadilhas Comuns
*   **Falta de Critério na Seleção**: A IA pode trazer concorrentes ou ensinantes pouco relevantes se as instruções não forem claras sobre o critério de relevância (ex: "Seja criterioso em trazer somente quem de fato é relevante").
*   **Informações Desatualizadas**: A internet é dinâmica; URLs de cursos ou canais e seus conteúdos podem mudar rapidamente. É importante validar manualmente as informações mais críticas.
*   **Limitações da IA na Análise de URLs**: A IA pode ter dificuldades em acessar ou interpretar certas páginas, especialmente as que exigem login, têm conteúdo dinâmico complexo ou paywalls.
*   **Generalização Excessiva**: A IA pode generalizar aspectos de ensino ou promessa se a página do concorrente não for explícita ou tiver informações limitadas.
*   **Confundir Ensinantes e Concorrentes**: É essencial manter a distinção entre quem cria conteúdo (ensinantes) e quem vende cursos/produtos similares (concorrentes) para uma análise estratégica eficaz.

## �� Metricas/Resultados
*   Lista abrangente de ensinantes e concorrentes no nicho.
*   Tabelas detalhadas com características e análises de cada player (assunto principal, público-alvo, pontos fortes/fracos, ensino, problema resolvido, transformação, promessa).
*   Identificação de propostas de valor, lacunas e oportunidades de diferenciação no mercado.
*   Compreensão da dinâmica do mercado em termos de conteúdo e ofertas de produtos.

## 🔧 Ferramentas Necessarias
*   Inteligência Artificial (ex: ChatGPT com funcionalidade de Deep Research)
*   Editor de texto ou planilha para compilar e organizar as tabelas geradas e as análises.

## Consideracoes
*   A distinção entre "ensinantes" (criadores de conteúdo) e "concorrentes" (vendedores de cursos/produtos similares) é crucial para uma análise de mercado completa. Os "ensinantes" disputam a atenção do público, enquanto os concorrentes disputam vendas diretas.
*   A clareza dos prompts e a especificidade do tema do curso online são fundamentais para obter resultados precisos e relevantes da IA.
*   A investigação deve considerar a atuação dos players no Brasil e em português, a menos que o curso tenha foco internacional.
*   É importante validar manualmente as informações mais críticas, como URLs e preços, que podem ser voláteis.
*   A análise do "Reclame Aqui" pode oferecer insights sobre problemas e expectativas dos clientes com os concorrentes.

## Entidades
Deep Research, ChatGPT, Ensinantes, Concorrentes, Nicho de Mercado, Análise Competitiva, Curso Online.

## Pré-requisitos
*   [[Processo Definição do Tema Central para Curso Online]]
*   [[Metodologia CPP (Conhecimento, Problema, Pessoas)]]

## 🔗Conhecimentos Relacionados
-   [[Conceito Ensinantes no Nicho]]
-   [[Estratégia Uso de IA na Criação de Cursos Online]]
-   [[Técnica Prompt Detalhado para Mapeamento de Ensinantes (IA)]]
-   [[Artifact Tabela de Mapeamento de Ensinantes]]
-   [[Processo Análise de Concorrentes Detalhada em Duas Etapas com IA]]
-   [[Técnica Prompt para Levantamento de Concorrentes e Características (IA)]]
-   [[Formato Tabela de Levantamento de Concorrentes de Curso Online]]
-   [[Técnica Prompt para Análise Aprofundada de Curso Concorrente Individual (IA)]]
-   [[Formato Tabela de Análise Detalhada de Curso Concorrente]]
-   [[Conceito Critério de Relevância de Concorrentes]]
-   [[Processo Pesquisa de Mercado e Análise de Concorrência para Curso Online]]
-   [[Técnica Investigação de Conhecimentos com IA]]
-   [[Conceito Mercado Endereçável Disponível (SAM)]]
-   [[Processo Roteirização, Gravação e Edição de Aulas]]
-   [[Etapa Avaliação de Concorrência Paga por IA]]

## 📚Fonte
**Documento:** F112 9. Pesquisa com IA - Ensinantes no Nicho, F113 10. Pesquisa com IA - Concorrentes
**Pagina/Secao:** Nao se aplica

## 🏷️ Tags
#Estrategia #IA #PesquisaDeMercado #Concorrencia #Ensinantes #Infoprodutos #DeepResearch #Analise