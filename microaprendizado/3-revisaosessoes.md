CONTEXTO

Você receberá um JSON estruturado de curso em formato de microaprendizado e deve validá-lo rigorosamente segundo critérios pedagógicos e técnicos específicos.

TAREFA

Analise o JSON fornecido e identifique todos os problemas, inconsistências e oportunidades de melhoria.

JSON EM ANEXO

INSTRUÇÕES DETALHADAS

VALIDAÇÃO 1: PROGRESSÃO LÓGICA

O que verificar:
Todos os pré-requisitos estão sendo respeitados na ordem das microaulas.

Como validar:

Para cada conceito que tem pré-requisitos listados:

Identifique em qual microaula esse conceito está
Identifique em qual microaula cada pré-requisito está
Verifique se a microaula do pré-requisito vem ANTES da microaula atual


Se encontrar violação:

Severidade: CRÍTICO
Problema: "Conceito X na Microaula Y depende do Conceito Z na Microaula W, mas Microaula W vem depois de Microaula Y"
Correção: Reordenar as microaulas

Exemplo de problema:

❌ CRÍTICO: Conceito "Loop For" (aula_01_05) lista "Variáveis" (conceito em aula_01_08) como pré-requisito, mas aula_01_08 vem depois de aula_01_05.
Correção: Mover aula_01_08 para antes de aula_01_05.

VALIDAÇÃO 2: DURAÇÃO DAS MICROAULAS

O que verificar:
Cada microaula respeita o limite de duração do microaprendizado.

Como validar:

Verifique o campo "duracao_estimada_minutos" de cada microaula
Intervalo obrigatório: 3-7 minutos
Ideal: 4-6 minutos

Se encontrar problemas:

Menos de 3 minutos:

Severidade: MÉDIO
Problema: "Microaula X tem apenas Y minutos (muito curta, pode ser superficial)"
Correção: "Expandir conteúdo OU combinar com microaula relacionada"


Mais de 7 minutos:

Severidade: CRÍTICO
Problema: "Microaula X tem Y minutos (excede limite do microaprendizado)"
Correção: "OBRIGATÓRIO: Dividir em 2 microaulas menores"

Exemplo:

❌ CRÍTICO: Microaula "Programação Orientada a Objetos Completa" tem 12 minutos. Excede limite de microaprendizado.
Correção: Dividir em:
- "POO Parte 1: Classes e Objetos" (5 min)
- "POO Parte 2: Atributos e Métodos" (5 min)
- "POO Parte 3: Herança Básica" (4 min)

VALIDAÇÃO 3: FOCO ÚNICO (Princípio Fundamental do Microaprendizado)

O que verificar:
Cada microaula tem apenas 1 objetivo de aprendizado e 1 conceito principal.

Como validar:

Verifique se campo "objetivo_aprendizado" contém apenas 1 objetivo (não é array)
Verifique se há apenas 1 objeto "conceito" (não array de conceitos)
Verifique se o título da microaula é específico e focado

Se encontrar problemas:

Múltiplos objetivos:

Severidade: CRÍTICO
Problema: "Microaula X tem múltiplos objetivos (viola princípio do microaprendizado)"
Correção: "Dividir em microaulas separadas, uma para cada objetivo"


Múltiplos conceitos:

Severidade: CRÍTICO
Problema: "Microaula X aborda múltiplos conceitos (viola foco único)"
Correção: "Criar microaula separada para cada conceito"


Título genérico:

Severidade: MÉDIO
Problema: "Título 'Introdução a X' é muito amplo para microaula"
Correção: "Tornar mais específico: 'O que é X e para que serve'"

Exemplo:

❌ CRÍTICO: Microaula "Variáveis e Operadores" aborda 2 conceitos distintos.
Correção: Dividir em:
- Microaula 1: "O que são Variáveis"
- Microaula 2: "O que são Operadores"

❌ MÉDIO: Título "Conceitos Básicos de Python" é muito amplo.
Correção: Especificar: "Como Declarar Variáveis em Python"

VALIDAÇÃO 4: APLICAÇÃO PRÁTICA

O que verificar:
Cada microaula tem aplicação prática clara e imediata.

Como validar:

Verifique se campo "aplicacao_pratica" está preenchido
Verifique se a aplicação é específica e acionável
Verifique se pode ser aplicada imediatamente após a microaula

Se encontrar problemas:

Aplicação vaga:

Severidade: MÉDIO
Problema: "Aplicação prática de Microaula X é vaga: '[texto]'"
Correção: "Tornar específica e acionável"


Aplicação ausente:

Severidade: ALTO
Problema: "Microaula X não tem aplicação prática definida"
Correção: "Adicionar aplicação imediata e específica"

Exemplos:

❌ Vago: "Usar variáveis em programas"
✅ Específico: "Criar variáveis para armazenar nome e idade em um programa Python"

❌ Vago: "Entender melhor o conceito"
✅ Específico: "Identificar qual tipo de variável usar ao armazenar diferentes dados (idade, nome, preço)"

VALIDAÇÃO 5: BALANCEAMENTO DE SESSÕES

O que verificar:
As sessões têm quantidade adequada de microaulas.

Como validar:

Conte quantas microaulas cada sessão tem
Intervalo ideal: 4-12 microaulas por sessão
Calcule a média: (total de microaulas) / (número de sessões)
Verifique se alguma sessão tem diferença maior que 4 microaulas da média

Se encontrar problemas:

Sessão muito grande (>12 microaulas):

Severidade: ALTO
Problema: "Sessão X tem Y microaulas (máximo recomendado: 12)"
Correção: "Dividir em 2 sessões temáticas"


Sessão muito pequena (<4 microaulas):

Severidade: MÉDIO
Problema: "Sessão X tem apenas Y microaulas (mínimo recomendado: 4)"
Correção: "Combinar com sessão relacionada OU expandir conceitos"

Exemplo:

⚠️ ALTO: Sessão "Fundamentos" tem 18 microaulas (máximo: 12).
Correção: Dividir em:
- "Fundamentos Parte 1: Conceitos Básicos" (9 microaulas)
- "Fundamentos Parte 2: Primeiros Programas" (9 microaulas)

VALIDAÇÃO 6: CLAREZA E ESPECIFICIDADE

O que verificar:
Títulos, descrições e objetivos são claros, específicos e sem ambiguidade.

Como validar:

Leia cada título de sessão e microaula
Leia cada descrição e objetivo
Pergunte: "Um aluno entenderia exatamente o que vai aprender em 3-7 minutos?"

Problemas comuns:

Títulos genéricos: "Conceitos Básicos", "Introdução", "Parte 1"
Descrições vagas: "Nesta microaula veremos conceitos importantes"
Objetivos não mensuráveis: "Entender melhor", "Conhecer sobre"

Se encontrar problemas:

Severidade: MÉDIO (mas importante para qualidade)
Correção: Reescrever com especificidade

Exemplos:

❌ Título vago: "Conceitos Básicos"
✅ Título específico: "O que são Variáveis e para que Servem"

❌ Descrição vaga: "Aprenderemos sobre variáveis"
✅ Descrição específica: "Você aprenderá a definição de variável, seus três componentes (nome, tipo, valor) e verá 2 exemplos práticos"

❌ Objetivo não mensurável: "Entender variáveis"
✅ Objetivo mensurável: "Definir o que é uma variável e identificar seus três componentes em exemplos de código"

VALIDAÇÃO 7: FORMATO E INTERATIVIDADE

O que verificar:
Cada microaula tem formato de entrega e tipo de interatividade definidos.

Como validar:

Verifique se campos "formato_entrega" e "tipo_interatividade" estão preenchidos
Verifique se os formatos são adequados ao conteúdo
Verifique se há variedade de formatos ao longo do curso

Formatos válidos:

"video" - Para demonstrações visuais
"audio" - Para explicações conceituais
"interativo" - Para prática hands-on
"quiz" - Para verificação

Tipos de interatividade válidos:

"exercicio_pratico" - Atividade hands-on
"quiz_rapido" - Pergunta de verificação
"desafio" - Problema para resolver
"reflexao" - Pergunta reflexiva

Se encontrar problemas:

Formato ausente:

Severidade: MÉDIO
Problema: "Microaula X não tem formato de entrega definido"
Correção: "Definir formato adequado ao tipo de conteúdo"


Falta de variedade:

Severidade: BAIXO
Problema: "Todas as microaulas usam formato 'audio'"
Correção: "Variar formatos para manter engajamento"

VALIDAÇÃO 8: CONSISTÊNCIA DE IDs

O que verificar:
Todos os IDs são únicos e seguem o padrão correto.

Como validar:

Liste todos os IDs de sessões, microaulas e conceitos


Verifique se há duplicatas


Verifique se seguem o formato:

Sessões: "sessao_01", "sessao_02", etc.
Microaulas: "aula_01_01", "aula_01_02", etc. (sessao_aula)
Conceitos: "conceito_01", "conceito_02", etc.


Verifique se pré-requisitos referenciam IDs que existem

Se encontrar problemas:

ID duplicado: CRÍTICO
ID com formato errado: MÉDIO
Pré-requisito referencia ID inexistente: CRÍTICO

VALIDAÇÃO 9: PRINCÍPIOS DO MICROAPRENDIZADO

Checklist específico de microaprendizado:

Para cada microaula, verifique:

Duração entre 3-7 minutos? ✅/❌
Apenas 1 objetivo de aprendizado? ✅/❌
Apenas 1 conceito principal? ✅/❌
Aplicação prática definida e acionável? ✅/❌
Título específico e focado? ✅/❌
Pode ser consumida independentemente (com pré-requisitos claros)? ✅/❌
Formato de entrega definido? ✅/❌
Tipo de interatividade definido? ✅/❌

Se encontrar violações:

Severidade: CRÍTICO (viola princípios fundamentais)
Correção: Ajustar microaula para cumprir todos os critérios

FORMATO DE OUTPUT

Gere um relatório seguindo EXATAMENTE esta estrutura:

# RELATÓRIO DE VALIDAÇÃO DO CURSO (MICROAPRENDIZADO)

## 1. RESUMO EXECUTIVO

- **Status Geral**: ✅ APROVADO / ⚠️ APROVADO COM RESSALVAS / ❌ REPROVADO
- **Total de Microaulas**: X
- **Duração Total do Curso**: X minutos
- **Total de Problemas Encontrados**: X
  - Críticos: X
  - Altos: X
  - Médios: X
  - Baixos: X
- **Recomendação**: [Pode prosseguir / Necessita correções antes de prosseguir]

## 2. VALIDAÇÃO POR CATEGORIA

### 2.1 Progressão Lógica
**Status**: ✅ OK / ⚠️ ATENÇÃO / ❌ FALHOU

**Problemas Encontrados**: X

[Se houver problemas, liste cada um:]
- ❌ **CRÍTICO**: [Descrição detalhada do problema]
  - **Localização**: Sessão X, Microaula Y
  - **Correção**: [Instrução específica de como corrigir]

### 2.2 Duração das Microaulas
**Status**: ✅ OK / ⚠️ ATENÇÃO / ❌ FALHOU

**Estatísticas**:
- Microaulas dentro do limite (3-7 min): X (Y%)
- Microaulas muito curtas (<3 min): X
- Microaulas muito longas (>7 min): X ❌ CRÍTICO

**Problemas Encontrados**: X

[Liste problemas se houver]

### 2.3 Foco Único (Princípio Fundamental)
**Status**: ✅ OK / ⚠️ ATENÇÃO / ❌ FALHOU

**Problemas Encontrados**: X

[Liste problemas se houver]

### 2.4 Aplicação Prática
**Status**: ✅ OK / ⚠️ ATENÇÃO / ❌ FALHOU

**Problemas Encontrados**: X

[Liste problemas se houver]

### 2.5 Balanceamento de Sessões
**Status**: ✅ OK / ⚠️ ATENÇÃO / ❌ FALHOU

**Estatísticas**:
- Sessão 1: X microaulas
- Sessão 2: Y microaulas
- Média: Z microaulas
- Desvio máximo: W microaulas

**Problemas Encontrados**: X

[Liste problemas se houver]

### 2.6 Clareza e Especificidade
**Status**: ✅ OK / ⚠️ ATENÇÃO / ❌ FALHOU

**Problemas Encontrados**: X

[Liste problemas se houver]

### 2.7 Formato e Interatividade
**Status**: ✅ OK / ⚠️ ATENÇÃO / ❌ FALHOU

**Distribuição de Formatos**:
- Audio: X microaulas
- Video: Y microaulas
- Interativo: Z microaulas
- Quiz: W microaulas

**Problemas Encontrados**: X

[Liste problemas se houver]

### 2.8 Consistência de IDs
**Status**: ✅ OK / ⚠️ ATENÇÃO / ❌ FALHOU

**Problemas Encontrados**: X

[Liste problemas se houver]

### 2.9 Princípios do Microaprendizado
**Status**: ✅ OK / ⚠️ ATENÇÃO / ❌ FALHOU

**Microaulas em conformidade**: X/Y (Z%)

**Problemas Encontrados**: X

[Liste problemas se houver]

## 3. LISTA CONSOLIDADA DE CORREÇÕES NECESSÁRIAS

### Correções Críticas (devem ser feitas obrigatoriamente):
1. [Descrição da correção com localização exata]
2. [Descrição da correção com localização exata]

### Correções Recomendadas (melhoram qualidade):
1. [Descrição da correção]
2. [Descrição da correção]

## 4. JSON CORRIGIDO

[Se houver problemas críticos ou altos, forneça o JSON completo já corrigido]

```json
{
  "curso": {
    ...
  }
}

[Se não houver problemas críticos, escreva:]
Não é necessário fornecer JSON corrigido. O JSON original está aprovado.

5. PRÓXIMOS PASSOS

[Baseado nos problemas encontrados, indique:]

Se pode prosseguir para Etapa 2 (geração de conteúdo das microaulas)
Se deve corrigir problemas críticos primeiro
Se deve revisar e reenviar para nova validação


# REGRAS IMPORTANTES

- Seja rigoroso com os princípios do microaprendizado (duração, foco único, aplicação)
- Sempre indique localização exata (sessão, microaula)
- Sempre forneça correção clara e específica
- Verifique TODAS as validações, não pare na primeira
- Se fornecer JSON corrigido, ele deve estar 100% funcional e válido
- Microaulas com mais de 7 minutos DEVEM ser divididas (não negociável)