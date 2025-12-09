# Processo Mudança de Fase de Conteúdo via Filtros

## 🎯 Categoria
Processo

## 📌 Sumário Executivo
No Notion, a mudança da fase de um conteúdo (como de "Estratégia" para "Aprovação") é realizada através da manipulação de itens em visualizações de calendário ou quadro que são configuradas com filtros específicos para cada fase. Basta arrastar o conteúdo de um calendário para outro, e sua fase será automaticamente atualizada, facilitando a gestão do fluxo de trabalho.

## 📝 Descricao
A gestão do ciclo de vida de um conteúdo no Notion, em especial a mudança de sua fase, é um processo altamente dinâmico e eficiente, baseado na utilização de filtros em bases de dados. Em sistemas como o Formação 3, por exemplo, o conteúdo é organizado em calendários ou visualizações de quadro que representam diferentes etapas, como "Calendário de Estratégia" e "Calendário de Aprovação".

Cada um desses calendários é configurado com filtros que determinam quais conteúdos serão exibidos. Por exemplo, um item só aparecerá no "Calendário de Estratégia" se a propriedade "fase" do conteúdo estiver definida como "Estratégia". Da mesma forma, para aparecer no calendário de "Aprovação", a propriedade "fase" deve ser "Aprovação".

O processo de mudança de fase ocorre de maneira intuitiva:
1.  **Identificação da Fase Atual**: O conteúdo reside em uma visualização (um calendário, por exemplo) que corresponde à sua fase atual (e.g., "Estratégia").
2.  **Transição**: Para mudar o conteúdo para a próxima fase (e.g., "Aprovação"), o usuário simplesmente "pega, segura e arrasta" o item do calendário de "Estratégia" para o calendário de "Aprovação".
3.  **Atualização Automática**: Ao ser movido para a visualização de "Aprovação", a propriedade "fase" do conteúdo é automaticamente atualizada para "Aprovação", e ele deixa de aparecer na visualização de "Estratégia" (devido aos filtros).

Essa abordagem permite uma clara separação e visualização dos conteúdos por suas fases, sendo útil para gerenciar diferentes momentos da interação com o cliente, como a primeira estratégia, renovação de contrato ou aprovação de conteúdos diários.

## Complexidade
Intermediario

## ⏱️ Templo de implementação
5-10 min para entender | 30-60 min para aplicar

## ⚡Como Aplicar
1.  Acesse o sistema de gerenciamento de conteúdo no Notion (ex: Formação 3) que possua visualizações de calendário ou quadro para diferentes fases (ex: Estratégia, Aprovação).
2.  Identifique o conteúdo que precisa ter sua fase alterada.
3.  Localize a visualização (calendário/quadro) que representa a fase atual do conteúdo.
4.  Arraste o item do conteúdo da visualização atual para a visualização correspondente à nova fase desejada (ex: arraste de "Calendário de Estratégia" para "Calendário de Aprovação").
5.  Confirme que o conteúdo desapareceu da visualização anterior e apareceu na nova, indicando que a propriedade da fase foi atualizada automaticamente.
6.  Caso a visualização não exista ou não esteja visível, você pode criá-la ou ajustá-la com filtros apropriados.

## �� Exemplos Práticos
*   Um conteúdo que foi planejado e está no "Calendário de Estratégia" é aprovado internamente. O usuário o arrasta para o "Calendário de Aprovação" do cliente para que ele possa revisar.
*   Após a aprovação do cliente, o conteúdo é arrastado para um calendário de "Publicação" ou "Agendamento".
*   Em um processo de renovação de contrato, um conteúdo pode ser movido para uma fase de "Estratégia" renovada para revisão antes de ser enviado novamente para "Aprovação".

## ⚠️ Armadilhas Comuns
*   **Filtros Incorretos**: Se os filtros dos calendários não estiverem corretamente configurados para refletir as fases, o conteúdo pode não aparecer ou aparecer em visualizações erradas após ser arrastado.
*   **Não Salvar Filtros**: Ao criar ou ajustar filtros, esquecer de "Salvar para todos" fará com que as alterações sejam visíveis apenas para o usuário que as realizou, causando inconsistências para a equipe.
*   **Excluir Calendários de Fases Anteriores**: Apagar um calendário de estratégia, por exemplo, pode ser tentador. No entanto, ele pode ser necessário para futuras renovações de contrato ou revisões de projetos.

## 📊 Metricas/Resultados
Nao se aplica

## �� Ferramentas Necessarias
*   Notion (Plataforma)
*   Bases de Dados configuradas com propriedades de fase
*   Visualizações de calendário ou quadro com filtros por fase

## Consideracoes
A separação dos conteúdos por fases em calendários distintos (e gerenciamento via arrastar e soltar) é uma maneira eficaz de organizar o fluxo de trabalho e garantir que cada etapa do processo seja clara e visível. Manter calendários para diferentes fases (como Estratégia, Aprovação) é fundamental, pois cada um atende a um propósito distinto e pode ser relevante em diferentes momentos do ciclo de vida do cliente ou do projeto.

## Entidades
- Conteúdo
- Filtros
- Calendário de Estratégia
- Calendário de Aprovação
- Propriedade (Fase)

## Pré-requisitos
- [[Recurso Filtros e Ordenação de Bases de Dados]]
- [[Técnica Aplicação de Filtros em Calendários de Conteúdo]]
- [[Conceito Bases de Dados (Database) no Notion]]
- [[Tipos de Visualizações de Bases de Dados no Notion]]

## 🔗Conhecimentos Relacionados
- [[Recurso Filtros e Ordenação de Bases de Dados]]
- [[Técnica Aplicação de Filtros em Calendários de Conteúdo]]
- [[Dica Salvar Filtros para Todos no Notion]]
- [[Conceito Bases de Dados (Database) no Notion]]
- [[Tipos de Visualizações de Bases de Dados no Notion]]
- [[Artefato Formação 3 (Template Sistema Notion)]]
- [[Dica Usar Ctrl+Z para Desfazer Alterações no Notion]]

## 📚Fonte
**Documento:** 1. Fundamentos do Notion - By @xEistibus ❤️‍🔥 LABORATÓRIO DE IA =LABORATÓRIO DE IA ==05. Funda_129_audio.txt
**Pagina/Secao:** Nao se aplica

## 🏷️ Tags
#processo #notion #fluxodetrabalho #gestaodeconteudo